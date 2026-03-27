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
"""

from __future__ import annotations

import ast
import json
import re
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# LLM-based function body generator
# ---------------------------------------------------------------------------

# System prompt for generating PyTOD API function bodies
_FUNCTION_GEN_SYSTEM = """\
你是一名 Python 开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个意图（intent）的函数签名、描述以及业务背景，需要生成该函数的 **完整 Python 实现**。

## 要求

1. **保持函数签名不变**（包括参数名和默认值 None）
2. **包含真实的业务逻辑处理**，不要只是直接返回固定字符串
3. **输入参数处理**：对 None 值设置合理默认值，对金额/日期等做简单格式化
4. **业务计算**：根据意图语义，做相应计算（如确认利率、生成工单号、计算金额等）
5. **返回值**：包含所有 result_slots 字段和输入参数，以及 "status": "success"
6. **只输出函数体代码**，不要输出函数签名、不要输出说明文字、不要添加注释
7. 代码必须是合法 Python，可直接插入到函数定义之后
8. 使用 4 空格缩进
9. 可以 import 标准库（如 datetime, re, math），但不要 import 第三方库
10. 函数体要简洁（不超过 30 行）

## 输出格式

只输出函数体代码，例如：
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    ticket_id = f"COMP-{today}-001"
    return {
        "complaint_id": ticket_id,
        "status": "success",
    }
"""

_FUNCTION_GEN_USER_TEMPLATE = """\
## 业务背景
服务名称：{service_name}
服务描述：{service_description}

## 函数签名
def {func_name}({param_str}):
    \"\"\"{description}\"\"\"

## 槽位说明
{slot_descriptions}

## 需要返回的字段（result_slots）
{result_slots}

## 任务
请为上面的函数生成真实的业务逻辑函数体（只输出函数体，4空格缩进，不包含def行）。
"""


class PyTODApiCodeGenerator:
    """使用 LLM 为 PyTOD API 函数生成真实业务逻辑代码体。

    Args:
        llm_client: AdkLLMClient 实例。若为 None 则从环境变量加载。
        timeout_per_intent: 每个意图的 LLM 调用超时秒数（默认 60）。
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
        timeout_per_intent: int = 60,
    ) -> None:
        if llm_client is None:
            from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
            llm_client = AdkLLMClient(config=LLMConfig.from_env())
        self._llm = llm_client
        self.timeout_per_intent = timeout_per_intent

    def generate_function_body(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
    ) -> Optional[str]:
        """调用 LLM 生成单个意图函数的完整函数体代码（4空格缩进）。

        返回函数体字符串（可直接拼接到 def 行之后），失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        # Build slot descriptions section
        slot_desc_lines: List[str] = []
        for p in params:
            desc = all_slot_descs.get(p, p)
            slot_desc_lines.append(f"  - {p}: {desc}")
        slot_desc_text = "\n".join(slot_desc_lines) if slot_desc_lines else "  （无输入参数）"

        result_slots_text = (
            "\n".join(f"  - {rs}" for rs in intent.result_slots)
            if intent.result_slots
            else "  （无专用 result_slots，返回输入参数即可）"
        )

        user_msg = _FUNCTION_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            func_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            slot_descriptions=slot_desc_text,
            result_slots=result_slots_text,
        )

        messages = [
            {"role": "system", "content": _FUNCTION_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            body = _clean_llm_function_body(raw, intent.name, param_str)
            if body is None:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: LLM 响应无法解析为合法函数体，"
                    "将回退到 stub 生成"
                )
            return body
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: LLM 调用失败 ({exc})，"
                "将回退到 stub 生成"
            )
            return None

    def _chat_sync(self, messages: List[Dict[str, Any]]) -> str:
        """同步调用 LLM chat 接口。"""
        import asyncio
        import concurrent.futures

        async def _run() -> str:
            return await self._llm.chat_async(messages)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(asyncio.run, _run())
                return future.result()
        else:
            return asyncio.run(_run())


def _clean_llm_function_body(raw: str, func_name: str, param_str: str) -> Optional[str]:
    """从 LLM 响应中提取并验证函数体代码。

    处理以下常见情况：
    - LLM 返回了完整的函数定义（包含 def 行）
    - LLM 用 markdown 代码块包裹了输出
    - LLM 在函数体前后有多余文字

    返回经过验证的 4 空格缩进函数体字符串，或 None（无法解析）。
    """
    # Strip markdown code fences
    raw = raw.strip()
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    # If LLM included the def line, extract just the body
    if raw.startswith("def "):
        # Parse as full function, extract body
        try:
            tree = ast.parse(raw)
            func_def = None
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_def = node
                    break
            if func_def:
                lines = raw.splitlines()
                body_start = func_def.body[0].lineno - 1
                body_lines = lines[body_start:]
                raw = textwrap.dedent("\n".join(body_lines))
        except SyntaxError:
            pass

    # Normalize indentation to 4 spaces
    lines = raw.splitlines()
    # Remove common leading whitespace
    if lines:
        raw = textwrap.dedent("\n".join(lines))

    # Ensure 4-space indent by re-indenting (empty lines remain empty)
    indented_lines = ["    " + line if line.strip() else "" for line in raw.splitlines()]
    body = "\n".join(indented_lines)

    # Validate: wrap in a function def and parse
    full_src = f"def {func_name}({param_str}):\n{body}\n"
    try:
        ast.parse(full_src)
    except SyntaxError as exc:
        logger.debug(f"[_clean_llm_function_body] SyntaxError for {func_name}: {exc}")
        return None

    return body


class SchemaDataBuilder:
    """从 schema.json 预生成各算法所需的 companion 数据文件。

    Args:
        overwrite: 目标文件已存在时是否覆盖（默认 True）。
        llm_client: 可选的 AdkLLMClient 实例。提供时使用 LLM 为 PyTOD 函数生成
            真实业务逻辑；不提供时回退到基于规则的 stub 生成。
    """

    def __init__(self, overwrite: bool = True, llm_client: Optional[Any] = None) -> None:
        self.overwrite = overwrite
        self._llm_client = llm_client

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

    def build_pytod_apis(
        self,
        schema_path: Union[str, Path],
        schema: Optional[ServiceSchema] = None,
    ) -> Optional[Path]:
        """从 schema.json 生成 PyTOD ``*_pytod_apis.py`` companion 文件。

        生成的 Python 文件包含每个 intent 对应的函数定义，函数：
        - 签名参数 = required_slots + optional_slots（全部带默认值 None）
        - 函数体包含真实业务逻辑（若提供了 llm_client）或语义化 mock 值（fallback）

        当 ``SchemaDataBuilder`` 初始化时传入了 ``llm_client``，则调用
        :class:`PyTODApiCodeGenerator` 为每个意图生成有真实计算逻辑的函数体。
        若 LLM 调用失败，自动回退到基于规则的 stub 生成（保证文件始终生成）。

        文件可通过 ``load_pytod_api_module(schema_path)`` 加载，
        返回的函数直接注册到 ExecutionEngine。

        Args:
            schema_path: ``*_schema.json`` 文件路径。
            schema:      已加载的 ServiceSchema（传入可省略重复 IO）。

        Returns:
            写入成功时返回文件路径，否则返回 None。
        """
        schema_path = Path(schema_path)
        out_path = _companion_path(schema_path, "pytod_apis", suffix=".py")

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

        # Decide generation mode: LLM vs stub fallback
        use_llm = self._llm_client is not None
        llm_generator: Optional[PyTODApiCodeGenerator] = None
        if use_llm:
            try:
                llm_generator = PyTODApiCodeGenerator(llm_client=self._llm_client)
                logger.info(
                    f"[SchemaDataBuilder] 使用 LLM 为 {schema.service_name} 生成真实函数逻辑"
                )
            except Exception as exc:
                logger.warning(
                    f"[SchemaDataBuilder] LLM 初始化失败，回退到 stub 生成: {exc}"
                )
                llm_generator = None

        # Build slot description index for LLM context
        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}

        # File header
        mode_note = (
            "函数体包含 LLM 生成的真实业务逻辑。"
            if llm_generator
            else "函数体由规则引擎根据意图语义生成（含输入校验、工单号生成、布尔推导等计算逻辑）。"
        )
        lines: List[str] = [
            '"""',
            f'PyTOD API 函数集合 — 由 {schema_path.name} 生成',
            f'Service: {schema.service_name}',
            f'Generated at: {datetime.now(timezone.utc).isoformat()}',
            '',
            '每个函数对应 schema 中的一个意图（intent），函数签名参数来自',
            'required_slots + optional_slots，返回值包含 result_slots 字段。',
            mode_note,
            '这些函数由 SchemaDataBuilder 预生成，运行时通过 load_pytod_api_module()',
            '加载并注册到 ExecutionEngine，供 PyTOD AP 生成的程序调用。',
            '"""',
            '',
            'from __future__ import annotations',
            '',
        ]

        llm_success_count = 0
        stub_fallback_count = 0

        if schema.intents:
            for intent in schema.intents:
                # Try LLM generation first
                if llm_generator is not None:
                    llm_body = llm_generator.generate_function_body(intent, schema, all_slot_descs)
                    if llm_body is not None:
                        lines.extend(_function_def_header(intent))
                        # The llm_body is already 4-space indented
                        lines.extend(llm_body.splitlines())
                        lines.append('')
                        llm_success_count += 1
                        continue

                # Fallback: rule-based stub
                lines.extend(_generate_function_lines(intent))
                lines.append('')
                stub_fallback_count += 1
        else:
            # No intents — generate one generic function using all slots
            lines.extend(_generate_generic_function_lines(schema))
            lines.append('')

        # Trailing newline
        source = '\n'.join(lines)

        try:
            with open(out_path, "w", encoding="utf-8") as fh:
                fh.write(source)
            mode_str = (
                f"LLM生成 {llm_success_count} 个，规则fallback {stub_fallback_count} 个"
                if llm_generator
                else f"规则生成 {stub_fallback_count} 个"
            )
            logger.info(
                f"[SchemaDataBuilder] 已写入 PyTOD APIs: {out_path} "
                f"({len(schema.intents)} 个意图，{mode_str})"
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
        out_path = _companion_path(schema_path, "fnctod_domain", suffix=".json")

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

def _companion_path(schema_path: Path, kind: str, suffix: str = ".json") -> Path:
    """返回 companion 文件路径。

    ``schema/foo_schema.json`` → ``schema/foo_{kind}{suffix}``
    ``schema/myservice.json``  → ``schema/myservice_{kind}{suffix}``
    """
    stem = schema_path.stem
    base = stem[: -len("_schema")] if stem.endswith("_schema") else stem
    return schema_path.parent / f"{base}_{kind}{suffix}"


# ---------------------------------------------------------------------------
# 意图分类模式（用于规则化代码生成）
# ---------------------------------------------------------------------------

_INTENT_COMPLAINT = (
    "complain_", "complaint_", "dispute_", "reject_", "appeal_",
)
_INTENT_VERIFY = (
    "verify_", "confirm_", "acknowledge_", "validate_",
)
_INTENT_DECLINE = (
    "decline_", "refuse_", "close_", "end_", "cancel_",
)
_INTENT_SCHEDULE = (
    "schedule_", "book_", "reserve_", "arrange_",
)
_INTENT_INQUIRE = (
    "inquire_", "query_", "check_", "search_", "find_",
    "get_", "look_", "ask_",
)
_INTENT_INFORM = (
    "inform_", "express_", "suggest_", "notify_", "tell_",
)


def _generate_function_lines(intent: IntentDefinition) -> List[str]:
    """为单个 intent 生成含真实计算逻辑的 Python 函数定义行列表。

    根据意图名称前缀推断语义类型，生成对应的计算代码：

    - **complain_/dispute_**：生成工单号（格式 PREFIX-YYYYMMDD-001），记录处理期限
    - **verify_/confirm_**：根据必填参数是否齐全推导布尔结果
    - **decline_/close_/end_**：记录拒绝/结束状态并返回 True
    - **schedule_**：计算下一个工作日作为回调时间
    - **inquire_/query_**：带必填参数校验的信息查询
    - **通用**：必填参数校验 + 输入参数回传

    函数体均包含真实 Python 计算逻辑（非仅 ``return {}``），
    可被 PyTOD ExecutionEngine 正确调用并向 AP 返回有意义的数据。
    """
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    intent_lower = intent.name.lower()
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name

    header = [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]

    if any(intent_lower.startswith(p) for p in _INTENT_COMPLAINT):
        body = _complaint_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_VERIFY):
        body = _verify_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_DECLINE):
        body = _decline_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_SCHEDULE):
        body = _schedule_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_INQUIRE):
        body = _inquire_body(intent, params)
    elif any(intent_lower.startswith(p) for p in _INTENT_INFORM):
        body = _inform_body(intent, params)
    else:
        body = _generic_body(intent, params)

    return header + body


# ---------------------------------------------------------------------------
# 意图语义体生成器（各返回函数体行列表，4 空格缩进）
# ---------------------------------------------------------------------------

def _echo_params(params: List[str]) -> List[str]:
    """将所有输入参数回传到返回字典（供 AP 通过 say(xN.slot) 引用）。"""
    return [f'        "{slot}": {slot},' for slot in params]


def _complaint_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """complaint/dispute 意图体：生成工单号，返回受理信息。"""
    prefix = intent.name.upper()[:8].replace("_", "")
    lines = [
        "    import datetime as _dt",
        f"    _today = _dt.date.today().strftime('%Y%m%d')",
        f"    _ticket = f'{prefix}-{{_today}}-001'",
        "    return {",
    ]
    for rs in intent.result_slots:
        if any(kw in rs.lower() for kw in ("_id", "ticket", "number", "no_")):
            lines.append(f'        "{rs}": _ticket,')
        else:
            lines.append(f'        "{rs}": "已受理，将在3个工作日内处理",')
    lines += _echo_params(params)
    lines += [
        '        "ticket_id": _ticket,',
        '        "handling_days": 3,',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _verify_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """verify/confirm 意图体：依据必填参数是否存在推导布尔结果。"""
    req = list(intent.required_slots)
    if req:
        # All required slots must be non-None for the operation to succeed
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        lines = [f"    _ok = bool({check_expr})"]
    elif params:
        lines = [f"    _ok = ({params[0]} is not None)"]
    else:
        lines = ["    _ok = True"]

    lines += ["    return {"]
    for rs in intent.result_slots:
        rsl = rs.lower()
        if any(kw in rsl for kw in ("declined", "rejected", "refused", "failed", "denied")):
            lines.append(f'        "{rs}": not _ok,')
        else:
            lines.append(f'        "{rs}": _ok,')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _decline_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """decline/close/end 意图体：记录拒绝/结束操作并返回确认。"""
    lines = ["    return {"]
    for rs in intent.result_slots:
        lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "note": "操作已记录",',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _schedule_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """schedule 意图体：计算下一个工作日作为回调时间。"""
    lines = [
        "    import datetime as _dt",
        "    _d = _dt.date.today() + _dt.timedelta(days=1)",
        "    while _d.weekday() >= 5:",  # skip Saturday(5) and Sunday(6)
        "        _d += _dt.timedelta(days=1)",
        "    _callback_time = _d.strftime('%Y-%m-%d') + ' 10:00'",
        "    return {",
    ]
    for rs in intent.result_slots:
        rsl = rs.lower()
        if any(kw in rsl for kw in ("time", "date", "datetime", "schedule", "when")):
            lines.append(f'        "{rs}": _callback_time,')
        else:
            lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "callback_time": _callback_time,',
        '        "status": "success",',
        "    }",
    ]
    return lines


def _inquire_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """inquire/query 意图体：校验必填参数后返回查询结果。"""
    req = list(intent.required_slots)
    lines: List[str] = []
    if req:
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        missing_list = ", ".join(req)
        lines += [
            f"    if not ({check_expr}):",
            f'        return {{"status": "error", "message": "缺少必填参数: {missing_list}"}}',
        ]
    # Build result slot values using heuristics
    lines.append("    return {")
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _inform_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """inform/express/suggest 意图体：记录信息并回传所有输入参数。"""
    lines = ["    return {"]
    for rs in intent.result_slots:
        lines.append(f'        "{rs}": True,')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _generic_body(intent: IntentDefinition, params: List[str]) -> List[str]:
    """通用意图体：必填参数校验 + 语义化返回值。"""
    req = list(intent.required_slots)
    lines: List[str] = []
    if req:
        check_parts = [f"({p} is not None)" for p in req]
        check_expr = " and ".join(check_parts)
        missing_list = ", ".join(req)
        lines += [
            f"    if not ({check_expr}):",
            f'        return {{"status": "error", "message": "缺少必填参数: {missing_list}"}}',
        ]
    lines.append("    return {")
    for rs in intent.result_slots:
        val = _mock_value_for_result_slot(rs, intent)
        lines.append(f'        "{rs}": {val},')
    lines += _echo_params(params)
    lines += [
        '        "status": "success",',
        "    }",
    ]
    return lines


def _mock_value_for_result_slot(slot_name: str, intent: IntentDefinition) -> str:
    """为 result_slot 返回合理的 Python 字面量字符串表示（用于 inquire/generic 意图）。"""
    name_lower = slot_name.lower()
    intent_lower = intent.name.lower()

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

    # Info / content / detail / result slots
    if any(kw in name_lower for kw in ("info", "detail", "content", "description", "data", "result")):
        return f'"[{intent.name}执行成功]"'

    # Interest / rate slots
    if any(kw in name_lower for kw in ("interest", "rate", "ratio")):
        return '"年利率7.2%"'

    # Inquiry / query result slots (fallback)
    if any(intent_lower.startswith(p) for p in ("inquire_", "query_", "check_", "search_", "find_")):
        if "status" in name_lower:
            return '"处理中"'
        if "amount" in name_lower or "limit" in name_lower:
            return '"5000元"'
        return f'"[{intent.name}查询结果]"'

    # Default: slot is a named completion marker
    return f'"{intent.name}_completed"'


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


def _function_def_header(intent: IntentDefinition) -> List[str]:
    """返回函数 def 行 + docstring 行（不含函数体）。

    用于 LLM 生成模式：def 行和 docstring 由此函数生成，函数体由 LLM 提供。
    """
    params = list(dict.fromkeys(
        list(intent.required_slots) + list(intent.optional_slots)
    ))
    param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
    desc = intent.description.replace('"', '\\"') if intent.description else intent.name
    return [
        f"def {intent.name}({param_str}):",
        f'    """{desc}"""',
    ]
