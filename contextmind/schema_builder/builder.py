"""
SchemaDataBuilder — 从 schema.json 预生成各算法 companion 数据文件

生成逻辑
--------

PyTOD companion (``*_pytod_apis.py``)
    对 schema 中的每个 intent，生成一个同名 Python 函数。函数：
    - 签名参数 = required_slots + optional_slots（全部带默认值 None）
    - 函数体包含**真实 Python 计算逻辑**（非空 stub），具体规则如下：

    **规则模式**（默认，无需 LLM）：
    根据意图名称前缀推断语义类型，自动生成对应的计算代码：

    +--------------------------+------------------------------------------+
    | 意图前缀                 | 生成的计算逻辑                           |
    +==========================+==========================================+
    | complain_/dispute_       | 生成工单号（PREFIX-YYYYMMDD-001）        |
    |                          | 返回受理信息和处理期限                   |
    +--------------------------+------------------------------------------+
    | verify_/confirm_         | 根据必填参数是否齐全推导布尔结果         |
    +--------------------------+------------------------------------------+
    | decline_/close_/end_     | 记录拒绝/结束状态，返回确认布尔值        |
    +--------------------------+------------------------------------------+
    | schedule_/book_          | 计算下一个工作日作为回调时间             |
    +--------------------------+------------------------------------------+
    | inquire_/query_/check_   | 校验必填参数后返回语义化查询结果         |
    +--------------------------+------------------------------------------+
    | inform_/express_         | 记录信息并回传所有输入参数               |
    +--------------------------+------------------------------------------+
    | 其他                     | 必填参数校验 + 语义化返回值              |
    +--------------------------+------------------------------------------+

    规则模式生成样例::

        def confirm_terms(loan_amount=None, monthly_payment=None,
                          current_credit_limit=None, total_interest=None, ...):
            \"\"\"确认账户额度和利息信息\"\"\"
            _ok = bool((loan_amount is not None) and (monthly_payment is not None) and
                       (current_credit_limit is not None) and (total_interest is not None))
            return {
                "confirmed_terms": _ok,
                "loan_amount": loan_amount,
                "monthly_payment": monthly_payment,
                "status": "success",
            }

        def complain_interest_rate(total_interest=None, daily_interest=None):
            \"\"\"用户认为利率偏高\"\"\"
            import datetime as _dt
            _today = _dt.date.today().strftime('%Y%m%d')
            _ticket = f'COMPLAININ-{_today}-001'
            return {
                "complaint_interest_rate": "已受理，将在3个工作日内处理",
                "total_interest": total_interest,
                "ticket_id": _ticket,
                "handling_days": 3,
                "status": "success",
            }

    **LLM 模式**（``--with-llm``，需配置 LLM API）：
    通过 :class:`PyTODApiCodeGenerator` 调用 LLM，根据意图描述、槽位说明
    和业务背景生成更贴近真实生产逻辑的函数体。LLM 失败时自动回退到规则模式。

FnCTOD companion (``*_fnctod_domain.json``)
    序列化 FunctionManager.add_domain_from_slots() 所需的 DomainSpec 字典，
    存储为可直接 json.load() 的格式，包含 domain_name / description / slots 等字段。

文件命名规则
------------
给定 ``schema/foo_schema.json``：
  - PyTOD companion  → ``schema/foo_pytod_apis.py``
  - FnCTOD companion → ``schema/foo_fnctod_domain.json``

模块结构
--------
本模块（``builder.py``）只包含 :class:`SchemaDataBuilder` 主协调器类。
其他职责已拆分到以下子模块：

- ``models.py``       — 数据类（:class:`~.models.TestCaseItem`、:class:`~.models.FuncValidation`）
- ``helpers.py``      — 生成文件共享工具函数模板（``SHARED_HELPERS``）
- ``prompts.py``      — LLM 提示词常量
- ``generator.py``    — LLM 代码生成器（:class:`~.generator.PyTODApiCodeGenerator`）
- ``rule_generator.py`` — 规则化函数体生成
- ``validator.py``    — 函数执行验证与报告（:func:`~.validator.validate_function`）
- ``utils.py``        — 路径工具（:func:`~.utils.companion_path`）
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict

# Sub-module imports
from .generator import PyTODApiCodeGenerator
from .helpers import SHARED_HELPERS
from .models import FuncValidation, TestCaseItem
from .rule_generator import (
    function_def_header,
    generate_function_lines,
    generate_generic_function_lines,
)
from .utils import companion_path
from .validator import validate_function, write_validation_report

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Backward-compatibility aliases for any code that still imports these names
# from this module directly.
# ---------------------------------------------------------------------------

#: Alias preserved for backward compatibility.
_FuncValidation = FuncValidation
#: Alias preserved for backward compatibility.
_SHARED_HELPERS = SHARED_HELPERS


class SchemaDataBuilder:
    """从 schema.json 预生成各算法所需的 companion 数据文件。

    Args:
        overwrite: 目标文件已存在时是否覆盖（默认 True）。
        llm_client: 可选的 AdkLLMClient 实例。提供时使用 LLM 为 PyTOD 函数生成
            真实业务逻辑；不提供时回退到基于规则的 stub 生成。
        dialogue_data_path: 可选的真实对话数据文件路径。在 LLM 模式下作为业务背景
            传给 LLM，帮助生成更贴近真实业务流程的函数实现。
            支持 chat_test_100.json / chat_test_500.json 格式。
        max_iterations: Phase 4 迭代优化的最大轮次（默认 3）。
            每个意图函数最多修复 ``max_iterations`` 轮以提升通过率。
        pass_rate_threshold: Phase 4 的通过率阈值（默认 0.9，即 90%）。
            当函数通过率 >= 阈值时停止迭代。
        max_test_cases_per_intent: Phase 2 每个意图最多生成的测试用例数（默认 5）。
        generate_report: 是否在 Phase 5 生成 ``*_validation_report.json``（默认 False）。
    """

    def __init__(
        self,
        overwrite: bool = True,
        llm_client: Optional[Any] = None,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_iterations: int = 3,
        pass_rate_threshold: float = 0.9,
        max_test_cases_per_intent: int = 5,
        generate_report: bool = False,
    ) -> None:
        self.overwrite = overwrite
        self._llm_client = llm_client
        self._dialogue_data_path = Path(dialogue_data_path) if dialogue_data_path else None
        self._max_iterations = max_iterations
        self._pass_rate_threshold = pass_rate_threshold
        self._max_test_cases = max_test_cases_per_intent
        self._generate_report = generate_report

    # ------------------------------------------------------------------
    # Public API
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

    def build_pytod_apis(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

        完整实现 plan.md 定义的 **5 阶段生成流程**：

        1. **Phase 1 — 解析 schema**：提取所有意图和槽位定义。
        2. **Phase 2 — 构建测试用例**（LLM 模式）：为每个意图调用 LLM 生成真实业务值
           的测试用例（``TestCaseItem``），可选加载真实对话数据提供业务背景。
           规则模式跳过此阶段。
        3. **Phase 3 — 初始函数生成**：对每个意图逐一调用 LLM，Prompt 包含意图描述、
           槽位说明及 Phase 2 生成的 few-shot 测试用例。LLM 不可用时回退到规则生成。
        4. **Phase 4 — 验证与迭代优化**（LLM 模式 + 有测试用例时）：对每个有测试用例
           的意图函数执行批量验证，计算通过率。通过率低于 ``pass_rate_threshold``
           时构造修复 Prompt（包含失败用例、错误信息）调用 LLM 重新生成，最多迭代
           ``max_iterations`` 轮。
        5. **Phase 5 — 生成最终文件**：组装完整 Python 文件（头部注释、共享工具函数、
           意图函数定义、``INTENT_REGISTRY``）。可选写入 ``*_validation_report.json``
           记录每个意图的初始通过率、最终通过率和迭代次数。

        生成模式（优先级从高到低）：

        - **LLM 全流程模式**（``llm_client`` 可用，Phase 2→4 完整运行）
        - **规则模式**（兜底，无 LLM 时使用意图名前缀语义推断函数体）

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = companion_path(schema_path, "pytod_apis", suffix=".py")

        if out_path.exists() and not self.overwrite:
            logger.debug(f"[SchemaDataBuilder] 跳过已存在文件: {out_path}")
            return None

        # ------------------------------------------------------------------
        # Phase 1: 解析 schema
        # ------------------------------------------------------------------
        if schema is None:
            try:
                with open(schema_path, encoding="utf-8") as fh:
                    schema = load_schema_from_dict(json.load(fh))
            except Exception as exc:
                logger.error(f"[SchemaDataBuilder] 加载 schema 失败: {schema_path} — {exc}")
                return None

        # Decide generation mode: LLM vs rule-based
        llm_generator: Optional[PyTODApiCodeGenerator] = None
        if self._llm_client is not None:
            try:
                llm_generator = PyTODApiCodeGenerator(llm_client=self._llm_client)
                logger.info(
                    f"[SchemaDataBuilder] Phase 1: 解析完成 — "
                    f"服务: {schema.service_name}, 意图数: {len(schema.intents)}, LLM 模式启用"
                )
            except Exception as exc:
                logger.warning(
                    f"[SchemaDataBuilder] LLM 初始化失败，回退到规则生成: {exc}"
                )
        else:
            logger.info(
                f"[SchemaDataBuilder] Phase 1: 解析完成 — "
                f"服务: {schema.service_name}, 意图数: {len(schema.intents)}, 规则模式"
            )

        # ------------------------------------------------------------------
        # Phase 2: 构建测试用例（LLM 模式）
        # ------------------------------------------------------------------
        test_cases_by_intent: Dict[str, List[TestCaseItem]] = {}
        if llm_generator is not None and schema.intents:
            logger.info(
                f"[SchemaDataBuilder] Phase 2: 为 {len(schema.intents)} 个意图生成测试用例 ..."
            )
            test_cases_by_intent = llm_generator.build_test_cases(
                schema,
                dialogue_data_path=self._dialogue_data_path,
                max_cases_per_intent=self._max_test_cases,
            )
            total_cases = sum(len(v) for v in test_cases_by_intent.values())
            logger.info(
                f"[SchemaDataBuilder] Phase 2: 完成 — "
                f"{len(test_cases_by_intent)} 个意图共 {total_cases} 条测试用例"
            )

        # ------------------------------------------------------------------
        # Phase 3: 初始函数生成（LLM 逐函数 + 测试用例 few-shot）
        # Phase 4: 验证与迭代优化
        # ------------------------------------------------------------------
        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
        intent_lines: List[str] = []
        validations: Dict[str, FuncValidation] = {}
        mode_str = ""

        if not schema.intents:
            intent_lines.extend(generate_generic_function_lines(schema))
            intent_lines.append('')
            mode_str = "通用函数（无意图定义）"

        elif llm_generator is not None:
            # LLM mode: per-function generation with test-case few-shot + iterative repair
            llm_count = 0
            rule_count = 0
            logger.info(
                f"[SchemaDataBuilder] Phase 3: 逐函数 LLM 生成（{len(schema.intents)} 个意图）..."
            )

            for intent in schema.intents:
                intent_test_cases = test_cases_by_intent.get(intent.name, [])

                # Phase 3: Initial LLM generation with few-shot test cases
                llm_body = llm_generator.generate_function_body(
                    intent, schema, all_slot_descs, test_cases=intent_test_cases
                )

                if llm_body is not None:
                    func_code = (
                        "\n".join(function_def_header(intent)) + "\n" + llm_body
                    )
                    llm_count += 1
                else:
                    # Rule-based fallback for this intent
                    func_code = "\n".join(generate_function_lines(intent))
                    rule_count += 1

                # Phase 4: Validate and iteratively repair (only when test cases exist)
                if intent_test_cases and llm_body is not None:
                    validation = validate_function(
                        intent, func_code, intent_test_cases, SHARED_HELPERS
                    )
                    logger.info(
                        f"[SchemaDataBuilder] Phase 4: {intent.name} — "
                        f"初始通过率: {validation.pass_rate:.1%} "
                        f"({validation.passed}/{validation.total})"
                    )

                    for iteration in range(1, self._max_iterations + 1):
                        if validation.pass_rate >= self._pass_rate_threshold:
                            break

                        logger.info(
                            f"[SchemaDataBuilder] Phase 4: {intent.name} — "
                            f"第 {iteration} 轮修复（通过率 {validation.pass_rate:.1%} "
                            f"< 阈值 {self._pass_rate_threshold:.1%}）..."
                        )
                        repaired_code = llm_generator.repair_function(
                            intent, schema, all_slot_descs,
                            current_code=func_code,
                            failures=validation.failures,
                            iteration=iteration,
                            total=validation.total,
                            passed=validation.passed,
                        )
                        if repaired_code is None:
                            logger.warning(
                                f"[SchemaDataBuilder] Phase 4: {intent.name} 修复失败，停止迭代"
                            )
                            break

                        new_validation = validate_function(
                            intent, repaired_code, intent_test_cases, SHARED_HELPERS
                        )
                        logger.info(
                            f"[SchemaDataBuilder] Phase 4: {intent.name} 第 {iteration} 轮后 "
                            f"通过率: {new_validation.pass_rate:.1%} "
                            f"({new_validation.passed}/{new_validation.total})"
                        )
                        # Accept if improved or equal.
                        # Equal pass rate is accepted because the repaired code may handle
                        # edge cases differently, and might improve further in the next round.
                        if new_validation.pass_rate >= validation.pass_rate:
                            func_code = repaired_code
                            validation = new_validation
                            validation.iterations = iteration

                    validations[intent.name] = validation
                else:
                    # No test cases or rule fallback: record empty validation
                    validations[intent.name] = FuncValidation(
                        intent_name=intent.name, total=0, passed=0
                    )

                intent_lines.extend(func_code.splitlines())
                intent_lines.append('')

            if llm_count > 0 and rule_count > 0:
                mode_str = f"LLM生成 {llm_count} 个，规则fallback {rule_count} 个"
            elif llm_count > 0:
                mode_str = f"LLM逐函数生成 {llm_count} 个意图"
            else:
                mode_str = f"规则生成 {rule_count} 个意图函数"

            if validations:
                validated = [v for v in validations.values() if v.total > 0]
                if validated:
                    avg_rate = sum(v.pass_rate for v in validated) / len(validated)
                    total_p = sum(v.passed for v in validated)
                    total_t = sum(v.total for v in validated)
                    mode_str += f"，测试验证 {total_p}/{total_t} ({avg_rate:.1%})"

        else:
            # Rule-based mode: no LLM
            rule_count = 0
            for intent in schema.intents:
                intent_lines.extend(generate_function_lines(intent))
                intent_lines.append('')
                rule_count += 1
            mode_str = f"规则引擎生成 {rule_count} 个意图函数"

        # ------------------------------------------------------------------
        # Phase 5: Build INTENT_REGISTRY + assemble file
        # ------------------------------------------------------------------
        n_dialogue = (
            f"（参考对话数据: {self._dialogue_data_path.name}）"
            if self._dialogue_data_path else ""
        )
        mode_info = (
            f"LLM 逐函数生成 + 迭代优化{n_dialogue}" if llm_generator
            else "规则引擎生成（含共享工具函数调用）"
        )
        header_lines: List[str] = [
            '"""',
            f'PyTOD API 函数集合 — 由 {schema_path.name} 生成',
            f'Service: {schema.service_name}',
            f'Generated at: {datetime.now(timezone.utc).isoformat()}',
            f'Generation mode: {mode_info}',
            '',
            '每个函数对应 schema 中的一个意图（intent），函数签名参数来自',
            'required_slots + optional_slots，返回值包含 result_slots 字段。',
            '文件头部定义了共享工具函数（_parse_amount、_ticket_id 等），',
            '意图函数通过调用这些工具函数实现真实计算逻辑。',
            '运行时通过 load_pytod_api_module() 加载并注册到 ExecutionEngine。',
            '"""',
            '',
            'from __future__ import annotations',
            '',
            SHARED_HELPERS,
        ]

        registry_lines: List[str] = [
            '',
            '# ---------------------------------------------------------------------------',
            '# INTENT_REGISTRY — intent 名称到函数的映射，供外部代码通过名称调用意图函数',
            '# ---------------------------------------------------------------------------',
            '',
            'INTENT_REGISTRY: dict = {',
        ]
        if schema.intents:
            for intent in schema.intents:
                registry_lines.append(f'    "{intent.name}": {intent.name},')
        else:
            registry_lines.append(f'    "{schema.service_name}": {schema.service_name},')
        registry_lines += [
            '}',
            '',
        ]

        source = '\n'.join(header_lines) + '\n'.join(intent_lines) + '\n'.join(registry_lines)

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(source)
            logger.info(
                f"[SchemaDataBuilder] Phase 5: 已写入 PyTOD APIs: {out_path} "
                f"({len(schema.intents)} 个意图，{mode_str})"
            )
        except Exception as exc:
            logger.error(f"[SchemaDataBuilder] 写入失败: {out_path} — {exc}")
            return None

        # Optional: write validation report
        if self._generate_report and test_cases_by_intent:
            write_validation_report(schema_path, validations, test_cases_by_intent)

        return out_path

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

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = companion_path(schema_path, "fnctod_domain", suffix=".json")

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
