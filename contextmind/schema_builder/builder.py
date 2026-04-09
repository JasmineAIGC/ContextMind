"""
SchemaDataBuilder — 从 schema.json 预生成各算法 companion 数据文件

生成逻辑
--------

PyTOD companion (``*_pytod_apis.py``)
    对 schema 中的每个 intent，生成一个同名 Python 函数。函数：
    - 签名参数 = required_slots + optional_slots（全部带默认值 None）
    - 函数体返回含 result_slots 字段的语义化 mock 数据（不依赖 LLM）
    - 文件可直接被 importlib 加载，函数注册到 ExecutionEngine

    生成样例::

        def verify_identity(account_usage_status=None):
            \"\"\"核实用户身份信息\"\"\"
            return {
                "verified_identity": True,
                "account_usage_status": account_usage_status or "正常",
                "status": "success",
            }

FnCTOD companion (``*_fnctod_domain.json``)
    序列化 FunctionManager.add_domain_from_slots() 所需的 DomainSpec 字典，
    存储为可直接 json.load() 的格式，包含 domain_name / description / slots 等字段。

文件命名规则
------------
给定 ``data/foo_schema.json``：
  - PyTOD companion  → ``data/foo_pytod_apis.py``
  - FnCTOD companion → ``data/foo_fnctod_domain.json``
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict
from contextmind.schema_builder.pytod.shared.test_cache import test_cases_path_for_schema

logger = get_logger(__name__)


class SchemaDataBuilder:
    """从 schema.json 预生成各算法所需的 companion 数据文件。

    Args:
        overwrite:                 目标文件已存在时是否覆盖（默认 True）。
        llm_client:                可选的 AdkLLMClient 实例；提供时启用 LLM 生成流程。
        dialogue_data_path:        可选的真实对话数据文件路径（LLM 模式业务背景）。
        kb_dir:                    可选，KB 输出目录路径。
        output_dir:                可选，输出目录。指定时所有 companion 文件写入该目录，
                                   否则与 schema 文件同目录。
        max_iterations:            最大修复轮次（默认 3）。
        pass_rate_threshold:       通过率阈值（默认 0.9）。
        max_test_cases_per_intent: 每意图最多测试用例数（默认 5）。
        generate_report:           是否写入验证报告（默认 False）。
        verbose:                   是否输出详细进度信息，默认 False。
        generator:                 PyTOD 生成算法选择：
                                   ``"loop"``（默认）— 迭代修复流水线；
                                   ``"alpha"`` — AlphaCodium 风格 ACIA 合成器
                                   （反思 + 骨架约束生成 + 失败分析 + 收敛重启）；
                                   ``"sstar"`` — S*（Test Time Scaling，arXiv:2502.14382，2025）
                                   （并行草稿 + 执行追踪修复 + 区分性测试选择 + 精炼）；
                                   ``"ctree"`` — CodeTree（树形搜索，arXiv:2411.04329，2024/2025）
                                   （UCB 引导树搜索：根节点生成 + 逐失败用例扩展 + 最优路径选择）。
    """

    def __init__(
        self,
        overwrite: bool = True,
        llm_client: Optional[Any] = None,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        kb_dir: Optional[Union[str, Path]] = None,
        output_dir: Optional[Union[str, Path]] = None,
        max_iterations: int = 3,
        pass_rate_threshold: float = 0.9,
        max_test_cases_per_intent: int = 5,
        generate_report: bool = False,
        verbose: bool = False,
        generator: str = "loop",
    ) -> None:
        self.overwrite = overwrite
        self.llm_client = llm_client
        self.dialogue_data_path = dialogue_data_path
        self.kb_dir = kb_dir
        self.output_dir = Path(output_dir) if output_dir is not None else None
        if self.output_dir is not None:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        self.max_iterations = max_iterations
        self.pass_rate_threshold = pass_rate_threshold
        self.max_test_cases_per_intent = max_test_cases_per_intent
        self.generate_report = generate_report
        self.verbose = verbose
        self.generator = generator

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def build_all(self, data_dir: Union[str, Path]) -> List[Path]:
        """处理目录下所有 ``*_schema.json`` 文件，生成全部 companion 文件。

        Args:
            data_dir: 包含 ``*_schema.json`` 文件的目录路径。

        Returns:
            成功写入的文件路径列表。
        """
        data_dir = Path(data_dir)
        if not data_dir.is_dir():
            raise ValueError(f"data_dir 不是有效目录: {data_dir}")

        schema_files = sorted(data_dir.glob("*_schema.json"))
        if not schema_files:
            logger.warning(f"[SchemaDataBuilder] 未在 {data_dir} 找到任何 *_schema.json 文件")
            return []

        written: List[Path] = []
        for schema_path in schema_files:
            logger.info(f"[SchemaDataBuilder] 处理: {schema_path.name}")
            written.extend(self.build_single(schema_path))

        logger.info(
            f"[SchemaDataBuilder] 完成: 处理 {len(schema_files)} 个 schema，写入 {len(written)} 个文件"
        )
        return written

    def build_single(self, schema_path: Union[str, Path]) -> List[Path]:
        """处理单个 schema.json，生成 PyTOD + FnCTOD companion 文件。

        Args:
            schema_path: ``*_schema.json`` 文件路径。

        Returns:
            成功写入的文件路径列表（最多 2 个）。
        """
        schema_path = Path(schema_path)
        written: List[Path] = []

        try:
            with open(schema_path, encoding="utf-8") as fh:
                raw = json.load(fh)
            schema = load_schema_from_dict(raw)
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
            return []

        p = self.build_pytod_apis(schema_path, schema=schema)
        if p:
            written.append(p)

        p = self.build_fnctod_domain(schema_path, schema=schema)
        if p:
            written.append(p)

        return written

    def prebuild_test_cases(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """预生成测试用例并保存到 ``*_test_cases.json``，供所有生成器共享。

        只运行 Phase 2（LLM 驱动的测试用例生成），不进行代码生成。
        生成的测试用例文件位于 schema 文件同目录，命名规则同其他 companion 文件：

            schema/foo_schema.json  →  schema/foo_test_cases.json

        调用多个生成器（loop / alpha / sstar / ctree）前先运行一次本方法，
        即可保证所有生成器在完全相同的测试集上进行评测，结果具有可比性。

        如果目标文件已存在，直接返回其路径（不重新生成）。
        如需强制重新生成，请先手动删除文件，再调用本方法。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回测试用例文件路径，否则返回 None（无 LLM 或生成失败时）。
        """
        from contextmind.schema_builder.pytod.shared.test_cache import save_test_cases
        from contextmind.schema_builder.pytod.shared.generator import PyTODApiCodeGenerator

        schema_path = Path(schema_path)
        tc_path = test_cases_path_for_schema(schema_path)

        if tc_path.exists():
            logger.info(f"[prebuild] 测试用例文件已存在，跳过重新生成: {tc_path}")
            return tc_path

        if self.llm_client is None:
            logger.warning("[prebuild] 未提供 llm_client，无法生成测试用例")
            return None

        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[prebuild] 加载 schema 失败: {schema_path} — {exc}")
                return None

        if not schema.intents:
            logger.info(f"[prebuild] schema 无意图定义，跳过测试用例生成: {schema_path}")
            return None

        # 解析 KB 目录上下文（与各生成器逻辑一致）
        _dlg_path = Path(self.dialogue_data_path) if self.dialogue_data_path else None
        _sgd_dlg_path = None
        _discovery_path = None
        _summary_path = None
        if self.kb_dir is not None:
            kb_context = PyTODApiCodeGenerator.load_kb_context(self.kb_dir)
            if _dlg_path is None and kb_context.get("dialogues_path"):
                _sgd_dlg_path = kb_context["dialogues_path"]
            if kb_context.get("discovery_path"):
                _discovery_path = kb_context["discovery_path"]
            if kb_context.get("summary_path"):
                _summary_path = kb_context["summary_path"]

        gen = PyTODApiCodeGenerator(llm_client=self.llm_client)
        dialogue_hint = gen._prepare_dialogue_hint(
            dialogue_data_path=_dlg_path,
            sgd_dialogue_data_path=_sgd_dlg_path,
            discovery_data_path=_discovery_path,
            summary_data_path=_summary_path,
        )

        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
        cases_by_intent: Dict[str, Any] = {}
        total_intents = len(schema.intents)
        logger.info(f"[prebuild] 开始生成测试用例（共 {total_intents} 个意图）: {schema_path.name}")

        for idx, intent in enumerate(schema.intents, 1):
            logger.info(f"[prebuild]   {idx}/{total_intents}: {intent.name}")
            cases = gen.build_test_cases_for_intent(
                intent, schema, all_slot_descs, dialogue_hint, self.max_test_cases_per_intent
            )
            if cases:
                cases_by_intent[intent.name] = cases

        if not cases_by_intent:
            logger.warning("[prebuild] 未能生成任何测试用例")
            return None

        save_test_cases(cases_by_intent, tc_path)
        logger.info(
            f"[prebuild] 测试用例已保存（{len(cases_by_intent)}/{total_intents} 个意图）→ {tc_path}"
        )
        return tc_path

    def build_pytod_apis(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

        当实例携带 ``llm_client`` 时，委托给
        :func:`contextmind.schema_builder.pytod.loop.builder.build_pytod_apis`
        执行完整的 5 阶段 LLM 生成流程（plan.md）；
        否则使用内置规则引擎生成 mock stub 函数。

        文件可通过 ``load_pytod_api_module(schema_path)`` 加载，
        返回的函数直接注册到 ExecutionEngine。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        # 如果初始化时提供了 llm_client（或其他 LLM 相关参数），
        # 根据 generator 参数委托给对应的构建器。
        if self.llm_client is not None:
            if self.generator == "alpha":
                from contextmind.schema_builder.pytod.alpha.builder import build_pytod_apis_alpha as _build
                logger.info("[SchemaDataBuilder] 使用 ACIA 生成器（--generator alpha）")
            elif self.generator == "sstar":
                from contextmind.schema_builder.pytod.sstar.builder import build_pytod_apis_sstar as _build  # type: ignore[assignment]
                logger.info("[SchemaDataBuilder] 使用 S* 生成器（--generator sstar，arXiv:2502.14382）")
            elif self.generator == "ctree":
                from contextmind.schema_builder.pytod.ctree.builder import build_pytod_apis_ctree as _build  # type: ignore[assignment]
                logger.info("[SchemaDataBuilder] 使用 CodeTree 生成器（--generator ctree，arXiv:2411.04329）")
            else:  # "loop" 或未知值均回退到迭代修复流水线
                from contextmind.schema_builder.pytod.loop.builder import build_pytod_apis as _build  # type: ignore[assignment]
                logger.info("[SchemaDataBuilder] 使用迭代修复流水线（--generator loop）")
            # 自动计算测试用例缓存路径（与 schema 同目录，独立于 output_dir）
            tc_path = test_cases_path_for_schema(Path(schema_path))
            return _build(
                schema_path,
                schema=schema,
                overwrite=self.overwrite,
                llm_client=self.llm_client,
                dialogue_data_path=self.dialogue_data_path,
                kb_dir=self.kb_dir,
                output_dir=self.output_dir,
                max_iterations=self.max_iterations,
                pass_rate_threshold=self.pass_rate_threshold,
                max_test_cases_per_intent=self.max_test_cases_per_intent,
                generate_report=self.generate_report,
                verbose=self.verbose,
                test_cases_path=tc_path,
            )

        # ------- 规则模式（无 LLM）-------
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "pytod_apis", suffix=".py", output_dir=self.output_dir)

        if out_path.exists() and not self.overwrite:
            logger.debug(f"[SchemaDataBuilder] 跳过已存在文件: {out_path}")
            return None

        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
                return None

        lines: List[str] = [
            '"""',
            f'PyTOD API 函数集合 — 由 {schema_path.name} 生成',
            f'Service: {schema.service_name}',
            f'Generated at: {datetime.now(timezone.utc).isoformat()}',
            '',
            '每个函数对应 schema 中的一个意图（intent），函数签名参数来自',
            'required_slots + optional_slots，返回值包含 result_slots 字段。',
            '这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()',
            '加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。',
            '"""',
            '',
            'from __future__ import annotations',
            '',
        ]

        if schema.intents:
            for intent in schema.intents:
                lines.extend(_generate_function_lines(intent))
                lines.append('')
        else:
            # No intents — generate one generic function using all slots
            lines.extend(_generate_generic_function_lines(schema))
            lines.append('')

        # Trailing newline
        source = '\n'.join(lines)

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(source)
            logger.info(
                f"[SchemaDataBuilder] 已写入 PyTOD APIs: {out_path} ({len(schema.intents)} 个意图)"
            )
            return out_path
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 写入失败: {out_path} — {exc}")
            return None

    def build_fnctod_domain(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 FnCTOD ``*_fnctod_domain.json`` companion 文件。

        输出格式为标准 OpenAI Function Calling JSON Schema（FnCTOD 算法的原生格式）：

            {
              "_schema_source": "anyihua_schema.json",
              "_generated_at": "...",
              "name": "AnYiHua_OutboundCall",
              "description": "...",
              "parameters": {
                "type": "object",
                "properties": {
                  "slot_name": {
                    "type": "string",
                    "description": "slot_description"
                  },
                  "categorical_slot": {
                    "type": "string",
                    "description": "...",
                    "enum": ["val1", "val2", ...]
                  }
                },
                "required": ["required_slot_name", ...]
              }
            }

        对应 FunctionManager 中 ``DomainSpec.to_json_schema()`` 的输出格式，
        可通过 ``load_fnctod_domain_spec(path)`` 直接重建 DomainSpec 对象。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "fnctod_domain", suffix=".json", output_dir=self.output_dir)

        if out_path.exists() and not self.overwrite:
            logger.debug(f"[SchemaDataBuilder] 跳过已存在文件: {out_path}")
            return None

        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
                return None

        # Build properties dict: each slot → {type, description, enum?}
        properties: Dict[str, Any] = {}
        required_list: List[str] = []

        for slot in schema.slots:
            prop: Dict[str, Any] = {
                "type": "string",
                "description": slot.description,
            }
            if slot.is_categorical and slot.possible_values:
                prop["enum"] = slot.possible_values
            properties[slot.name] = prop
            if slot.is_required:
                required_list.append(slot.name)

        parameters_schema: Dict[str, Any] = {
            "type": "object",
            "properties": properties,
        }
        if required_list:
            parameters_schema["required"] = required_list

        domain_data: Dict[str, Any] = {
            "_schema_source": schema_path.name,
            "_generated_at": datetime.now(timezone.utc).isoformat(),
            "name": schema.service_name,
            "description": schema.description,
            "parameters": parameters_schema,
        }

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                json.dump(domain_data, fh, ensure_ascii=False, indent=2)
            logger.info(
                f"[SchemaDataBuilder] 已写入 FnCTOD domain: {out_path} ({len(properties)} 个槽位)"
            )
            return out_path
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 写入失败: {out_path} — {exc}")
            return None


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _companion_path(schema_path: Path, kind: str, suffix: str = ".json", *, output_dir: Optional[Path] = None) -> Path:
    """返回 companion 文件路径。

    ``data/foo_schema.json`` → ``data/foo_{kind}{suffix}``
    ``data/myservice.json``  → ``data/myservice_{kind}{suffix}``
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    parent = output_dir if output_dir is not None else schema_path.parent
    return parent / f"{base}_{kind}{suffix}"


def _mock_value_for_result_slot(slot_name: str, intent: IntentDefinition) -> str:
    """为 result_slot 返回合理的 Python 字面量字符串表示。"""
    name_lower = slot_name.lower()
    intent_lower = intent.name.lower()

    # ---- Intent-level semantics ----
    # Confirmation / verification intents → boolean result
    if any(intent_lower.startswith(p) for p in (
        "confirm_", "verify_", "close_", "decline_", "end_",
        "express_", "acknowledge_",
    )):
        if any(kw in name_lower for kw in ("declined", "rejected", "refused", "closed", "end")):
            return "False"
        return "True"

    # Complaint / dispute intents → acknowledgement string
    if any(intent_lower.startswith(p) for p in (
        "complain_", "complaint_", "dispute_", "reject_",
    )):
        return '"已记录，将在3个工作日内处理"'

    # Schedule intents
    if intent_lower.startswith("schedule_"):
        if "time" in name_lower or "date" in name_lower:
            return '"明天上午10:00"'
        return "True"

    # Inquiry / query intents
    if any(intent_lower.startswith(p) for p in ("inquire_", "query_", "check_", "search_", "find_")):
        # specific slot-name heuristics for query results
        if "status" in name_lower:
            return '"已发货"'
        if "info" in name_lower or "policy" in name_lower or "detail" in name_lower:
            return '"标准服务条款：退换货政策7天内有效。"'
        if "amount" in name_lower or "limit" in name_lower or "quota" in name_lower:
            return '"5000元"'
        if "rate" in name_lower or "interest" in name_lower:
            return '"年利率7.2%"'
        return f'"[{intent.name}查询结果]"'

    # ---- Slot-name semantics ----
    # Boolean-like result slots
    if any(kw in name_lower for kw in (
        "verified", "confirmed", "declined", "acknowledged",
        "informed", "accepted", "approved", "suggested",
    )):
        is_negative = any(kw in name_lower for kw in ("declined", "rejected", "refused"))
        return "False" if is_negative else "True"

    # ID / ticket slots
    if "complaint_id" in name_lower or name_lower.endswith("_id"):
        prefix = "".join(w[0].upper() for w in intent.name.split("_"))[:4]
        return f'"{prefix}-20240115-001"'

    if "number" in name_lower or "policy" in name_lower:
        return f'"{intent.name.upper()[:6]}-001"'

    # Status slots — domain-aware
    if name_lower.endswith("_status"):
        base = name_lower.replace("_status", "")
        status_map = {
            "order": '"已发货"',
            "refund": '"退款处理中"',
            "exchange": '"换货处理中"',
            "logistics": '"快递运输中"',
            "reset": '"密码重置成功"',
            "update": '"信息更新成功"',
            "payment": '"支付成功"',
            "repayment": '"还款成功"',
            "account": '"账户正常"',
        }
        for key, val in status_map.items():
            if key in base:
                return val
        return '"处理成功"'

    # Amount / money slots
    if any(kw in name_lower for kw in ("amount", "quota", "limit", "balance", "fee", "price")):
        return '"5000元"'

    # Date / time slots
    if any(kw in name_lower for kw in ("date", "time", "datetime", "schedule")):
        return '"2024-01-15"'

    # Info / content / detail slots
    if any(kw in name_lower for kw in ("info", "detail", "content", "description", "data", "result")):
        return f'"[{intent.name}执行成功]"'

    # Interest / rate slots
    if any(kw in name_lower for kw in ("interest", "rate", "ratio")):
        return '"年利率7.2%"'

    # Default: slot is a named completion marker
    return f'"{intent.name}_completed"'


def _generate_function_lines(intent: IntentDefinition) -> List[str]:
    """为单个 intent 生成 Python 函数定义行列表。"""
    # Build parameter list: required + optional, all with default None
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

    lines: List[str] = []
    lines.append(f"def {intent.name}({param_str}):")
    # Docstring
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    lines.append(f'    """{desc}"""')
    lines.append(f'    return {{')
    # result_slots first (output/computed fields with semantic mock values)
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    # Echo back ALL input parameters so AP can reference x1.slot_name in say()
    for slot in params:
        lines.append(f'        "{slot}": {slot},')
    # Always include status
    lines.append(f'        "status": "success",')
    lines.append(f'    }}')
    return lines


def _generate_generic_function_lines(schema: ServiceSchema) -> List[str]:
    """无意图定义时生成一个以 service_name 命名的通用函数。"""
    slot_names = [s.name for s in schema.slots]
    param_str = ", ".join([f"{p}=None" for p in slot_names]) if slot_names else ""
    lines: List[str] = []
    lines.append(f"def {schema.service_name}({param_str}):")
    desc = schema.description.replace('"', '\\"') if schema.description else schema.service_name
    lines.append(f'    """{desc}"""')
    lines.append(f'    args = {{k: v for k, v in locals().items() if v is not None}}')
    lines.append(f'    return {{"status": "success", **args}}')
    return lines
