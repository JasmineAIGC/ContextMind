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
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger
from contextmind.modes.pytod.schemas import IntentDefinition, ServiceSchema, load_schema_from_dict

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data structures for test-case-driven generation (plan.md Phase 2 / 4)
# ---------------------------------------------------------------------------

@dataclass
class TestCaseItem:
    """一个意图函数的单条测试用例。

    Attributes:
        input_slots: 函数调用时传入的槽位值字典（slot_name → value）。
        expected_keys: 返回字典中必须包含的键名列表（默认包含 result_slots + "status"）。
        description: 测试场景的简短中文描述。
    """
    input_slots: Dict[str, Any]
    expected_keys: List[str] = field(default_factory=list)
    description: str = ""


@dataclass
class _FuncValidation:
    """单个意图函数的测试验证结果（plan.md Phase 4）。"""
    intent_name: str
    total: int
    passed: int
    failures: List[Dict[str, Any]] = field(default_factory=list)
    iterations: int = 0
    error: Optional[str] = None

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0


# ---------------------------------------------------------------------------
# Shared helper library — embedded into every generated *_pytod_apis.py
# ---------------------------------------------------------------------------

#: Template string that is inserted near the top of every generated file.
#: These helper functions are available to all intent API functions in the
#: same module, so generated code (both rule-based and LLM-based) can call
#: them instead of repeating boilerplate.
_SHARED_HELPERS = r'''
# ---------------------------------------------------------------------------
# 共享工具函数 — 由 SchemaDataBuilder 自动生成，所有 API 函数均可调用
# ---------------------------------------------------------------------------

import datetime as _dt
import math as _math
import re as _re


def _parse_amount(value) -> float:
    """将字符串金额（如 '21900元'、'两万一千九百'）解析为浮点数，无法解析时返回 0.0。"""
    if value is None:
        return 0.0
    s = _re.sub(r"[^\d.]", "", str(value).replace(",", "").replace("，", ""))
    try:
        return float(s)
    except ValueError:
        return 0.0


def _ticket_id(prefix: str = "TICKET") -> str:
    """生成工单编号，格式：{PREFIX}-YYYYMMDD-001。适用于投诉、申请、纠纷等意图。"""
    today = _dt.date.today().strftime("%Y%m%d")
    return f"{prefix}-{today}-001"


def _calc_monthly_payment(principal: float, annual_rate: float, months: int) -> float:
    """等额还款月供计算（PMT 公式）。

    Args:
        principal: 贷款本金（元）
        annual_rate: 年化利率（小数，如 0.24 表示 24%）
        months: 还款期数（月）
    """
    if principal <= 0 or months <= 0:
        return 0.0
    r = annual_rate / 12.0
    if r == 0:
        return principal / months
    return principal * r / (1.0 - (1.0 + r) ** (-months))


def _next_work_day() -> str:
    """返回下一个工作日日期字符串（格式 YYYY-MM-DD），跳过周末。"""
    d = _dt.date.today() + _dt.timedelta(days=1)
    while d.weekday() >= 5:   # 5=Saturday, 6=Sunday
        d += _dt.timedelta(days=1)
    return d.strftime("%Y-%m-%d")

'''


# ---------------------------------------------------------------------------
# LLM-based full-module generator
# ---------------------------------------------------------------------------

#: System prompt for generating the entire *_pytod_apis.py module in one call.
_MODULE_GEN_SYSTEM = """\
你是一名 Python 高级开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个服务的完整 Schema（意图列表、槽位定义）以及可选的真实对话示例。
你需要生成该服务对应的 **完整 Python 模块代码**，包含所有意图的函数实现。

## 生成要求

### 函数签名
- 每个意图对应一个函数，函数名 = 意图名（snake_case）
- 函数参数 = required_slots + optional_slots（全部带默认值 None）
- 函数必须包含 docstring（意图描述）

### 函数体（每个函数都必须有真实计算逻辑）
1. **输入处理**：对 None 值设置合理默认值；金额/日期字段做格式化
2. **业务计算**：根据意图语义做相应计算
   - `complain_*`/`dispute_*`：调用 `_ticket_id(prefix)` 生成工单号
   - `verify_*`/`confirm_*`：根据必填参数是否存在推导布尔结果
   - `schedule_*`/`book_*`：调用 `_next_work_day()` 计算回调时间
   - `inquire_*`/`query_*`：必填参数校验后返回查询结果
   - 财务计算意图：调用 `_calc_monthly_payment()` / `_parse_amount()`
3. **返回值**：包含所有 result_slots 字段 + 输入参数 + `"status": "success"`
4. 可以直接调用文件顶部已定义的 `_ticket_id()`、`_calc_monthly_payment()` 等工具函数

### 代码质量
- 每个函数体不超过 25 行
- 只使用 Python 标准库（不要 import 第三方库）
- 模块顶部已有 `from __future__ import annotations`
- **不要重复定义** `_parse_amount`、`_ticket_id`、`_calc_monthly_payment`、`_next_work_day`（已在文件头部定义）
- **不要添加 `INTENT_REGISTRY`**（由生成器自动追加，不需要在函数区中定义）

## 输出格式
直接输出 Python 代码，不要包含 markdown 代码块标记，不要包含解释文字。
输出从第一个 `def` 函数定义开始，不包含 import 语句和工具函数定义。
"""

_MODULE_GEN_USER_TEMPLATE = """\
## 服务信息
服务名称：{service_name}
服务描述：{service_description}

## 意图列表
{intents_summary}

## 槽位定义
{slots_summary}

{dialogue_context_section}## 任务
请为上述所有意图生成完整的 Python 函数实现（从第一个 def 开始，不包含 import）。
"""

_DIALOGUE_CONTEXT_SECTION = """\
## 真实对话示例（参考以下对话提炼业务细节）
{dialogue_samples}

"""


# ---------------------------------------------------------------------------
# Phase 2: Per-intent test case generation prompts
# ---------------------------------------------------------------------------

_TEST_CASE_GEN_SYSTEM = """\
你是一名任务型对话系统（ToD）的测试工程师，专门为意图函数生成高质量的单元测试用例。

你将收到一个意图函数的名称、描述和槽位定义，需要生成该函数的 **测试用例列表**。

## 测试用例要求
- 每条测试用例包含 "input_slots"（输入槽位值）和 "description"（测试场景描述）
- 输入槽位值要真实、多样，覆盖不同业务场景（正常流程、边界值等）
- 如果意图有 required_slots，每条用例都必须提供这些槽位的值
- 可选槽位（optional_slots）在部分用例中提供，在其他用例中省略
- 槽位值使用中文，符合真实对话系统的输入特征
- 金额类字段使用中文描述（如 "21900元"、"五千"）；日期类字段使用具体日期

## 输出格式
直接输出 JSON 数组，不要包含 markdown 代码块标记，不要包含解释文字。
格式：[{"input_slots": {"slot1": "value1", ...}, "description": "测试场景描述"}, ...]
"""

_TEST_CASE_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

意图：{intent_name}
描述：{intent_description}

函数签名：def {func_name}({param_str})

required_slots（必填，每个测试用例必须提供）：
{required_slots_desc}

optional_slots（可选）：
{optional_slots_desc}

result_slots（预期返回字段）：
{result_slots_desc}

{dialogue_hint}请生成 {max_cases} 条测试用例（JSON 数组）。
"""

# ---------------------------------------------------------------------------
# Phase 4: Function repair prompts
# ---------------------------------------------------------------------------

_REPAIR_SYSTEM = """\
你是一名 Python 高级开发专家，专门为任务型对话系统（ToD）修复 API 函数实现。

你将收到一个意图函数的完整代码以及测试失败信息，需要修复函数体使其通过测试。

## 修复要求
1. **保持函数签名不变**（参数名和默认值 None）
2. **修复错误**：根据失败信息分析问题根因，修改函数体逻辑
3. **返回值格式**：必须返回包含所有 result_slots 字段的字典，且含 "status": "success"
4. 可以直接调用文件中已定义的工具函数：`_parse_amount()`、`_ticket_id()`、
   `_calc_monthly_payment()`、`_next_work_day()`
5. 只使用 Python 标准库，函数体不超过 25 行
6. **不要重定义**已有的共享工具函数

## 输出格式
只输出完整的函数定义（包含 def 行和函数体），不包含 import 语句，不要 markdown 代码块。
"""

_REPAIR_USER_TEMPLATE = """\
## 意图信息
服务：{service_name}
意图：{intent_name}（{intent_description}）

result_slots（返回值中必须包含）：
{result_slots_desc}

## 当前函数代码（第 {iteration} 轮修复）
{current_code}

## 失败的测试用例（共 {fail_count} 条，通过率 {pass_rate}）
{failures_text}

## 任务
请修复上述函数，使所有测试用例通过（输出完整的函数定义，从 def 行开始）。
"""


class PyTODApiCodeGenerator:
    """使用 LLM 为 PyTOD API 模块生成真实业务逻辑代码。

    支持两种生成模式：

    1. **全模块生成**（推荐，:meth:`generate_module`）：一次 LLM 调用生成整个
       ``*_pytod_apis.py`` 模块，包含所有意图函数。可选传入真实对话数据文件路径
       （``dialogue_data_path``）使 LLM 参考真实业务流程生成更贴近生产环境的代码。

    2. **单函数生成**（:meth:`generate_function_body`）：逐个意图调用 LLM。
       用于 fallback 场景。

    Args:
        llm_client: AdkLLMClient 实例。若为 None 则从环境变量加载。
    """

    def __init__(
        self,
        llm_client: Optional[Any] = None,
    ) -> None:
        if llm_client is None:
            from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
            llm_client = AdkLLMClient(config=LLMConfig.from_env())
        self._llm = llm_client

    # ------------------------------------------------------------------
    # 全模块生成（首选方式）
    # ------------------------------------------------------------------

    def generate_module(
        self,
        schema: ServiceSchema,
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_dialogue_samples: int = 5,
    ) -> Optional[str]:
        """一次 LLM 调用生成整个 ``*_pytod_apis.py`` 模块的函数定义区（不含 import 和工具函数）。

        Args:
            schema: 服务 schema。
            dialogue_data_path: 可选，真实对话数据文件路径（JSON 格式）。
                支持 resources/data/chat_test_100.json 等格式。
                传入后 LLM 将参考真实业务流程生成更准确的函数体。
            max_dialogue_samples: 从对话数据中最多取几条样本（避免 prompt 过长）。

        Returns:
            包含所有函数定义的 Python 代码字符串，失败时返回 None。
        """
        # Build intents summary
        intents_lines: List[str] = []
        for intent in schema.intents:
            params = list(dict.fromkeys(
                list(intent.required_slots) + list(intent.optional_slots)
            ))
            param_str = ", ".join([f"{p}=None" for p in params]) if params else ""
            rs = ", ".join(intent.result_slots) if intent.result_slots else "（无）"
            intents_lines.append(
                f"- def {intent.name}({param_str})  # {intent.description or intent.name}"
            )
            intents_lines.append(f"  result_slots: {rs}")
        intents_summary = "\n".join(intents_lines)

        # Build slots summary
        slot_lines: List[str] = []
        for slot in schema.slots:
            vals = f"  可选值: {', '.join(slot.possible_values)}" if slot.possible_values else ""
            slot_lines.append(f"- {slot.name}: {slot.description}{vals}")
        slots_summary = "\n".join(slot_lines) if slot_lines else "（无槽位）"

        # Build dialogue context section
        dialogue_context_section = ""
        if dialogue_data_path:
            samples = self._load_dialogue_samples(
                dialogue_data_path, max_samples=max_dialogue_samples
            )
            if samples:
                formatted = "\n\n".join(
                    f"【对话 {i+1}】\n{s}" for i, s in enumerate(samples)
                )
                dialogue_context_section = _DIALOGUE_CONTEXT_SECTION.format(
                    dialogue_samples=formatted
                )
                logger.info(
                    f"[PyTODApiCodeGenerator] 已加载 {len(samples)} 条对话样本用于辅助生成"
                )

        user_msg = _MODULE_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            intents_summary=intents_summary,
            slots_summary=slots_summary,
            dialogue_context_section=dialogue_context_section,
        )

        messages = [
            {"role": "system", "content": _MODULE_GEN_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            cleaned = _clean_llm_module(raw, schema)
            if cleaned is None:
                logger.warning(
                    "[PyTODApiCodeGenerator] generate_module: LLM 响应无法解析为合法模块，"
                    "将回退到规则生成"
                )
            return cleaned
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] generate_module: LLM 调用失败 ({exc})，"
                "将回退到规则生成"
            )
            return None

    # ------------------------------------------------------------------
    # 单函数生成（带测试用例 few-shot）
    # ------------------------------------------------------------------

    def generate_function_body(
        self,
        intent: IntentDefinition,
        schema: ServiceSchema,
        all_slot_descs: Dict[str, str],
        test_cases: Optional[List[TestCaseItem]] = None,
    ) -> Optional[str]:
        """调用 LLM 生成单个意图函数的完整函数体代码（4空格缩进）。

        Args:
            intent: 意图定义。
            schema: 服务 schema。
            all_slot_descs: slot_name → description 映射。
            test_cases: 可选，该意图的测试用例列表（Phase 2 构建）。
                传入后 LLM 将把这些用例当作 few-shot 示例生成更准确的函数体。

        Returns:
            函数体字符串（可直接拼接到 def 行之后），失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

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

        # Build few-shot section from test cases
        few_shot_section = ""
        if test_cases:
            example_lines = ["## 参考测试用例（few-shot 示例，用于校准函数输出）"]
            for i, tc in enumerate(test_cases[:3], 1):
                example_lines.append(
                    f"示例 {i}（{tc.description or '典型输入'}）: "
                    f"输入 = {json.dumps(tc.input_slots, ensure_ascii=False)}"
                )
            few_shot_section = "\n".join(example_lines) + "\n\n"

        user_msg = _FUNCTION_GEN_USER_TEMPLATE.format(
            service_name=schema.service_name,
            service_description=schema.description or schema.service_name,
            func_name=intent.name,
            param_str=param_str,
            description=intent.description or intent.name,
            slot_descriptions=slot_desc_text,
            result_slots=result_slots_text,
            few_shot_section=few_shot_section,
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
                    f"[PyTODApiCodeGenerator] {intent.name}: LLM 响应无法解析，回退到规则生成"
                )
            return body
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: LLM 调用失败 ({exc})，回退到规则生成"
            )
            return None

    # ------------------------------------------------------------------
    # 对话数据加载
    # ------------------------------------------------------------------

    @staticmethod
    def _load_dialogue_samples(
        data_path: Union[str, Path],
        max_samples: int = 5,
    ) -> List[str]:
        """从对话数据文件中加载并格式化对话样本。

        支持以下 JSON 格式：
        - ``[{"session_id":..., "用户信息":..., "对话历史":[{"机器人":..., "用户":...},...]}]``
          （chat_test_100.json 格式）
        - ``[{"label":..., "query":{"用户信息":..., "对话历史":[...]}}]``
          （chat_test_500.json 格式）

        Returns:
            格式化后的对话文本列表（每条为一个对话的字符串表示）。
        """
        try:
            path = Path(data_path)
            if not path.exists():
                logger.warning(f"[PyTODApiCodeGenerator] 对话数据文件不存在: {path}")
                return []

            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)

            if not isinstance(data, list) or not data:
                return []

            samples: List[str] = []
            for item in data:
                if len(samples) >= max_samples:
                    break

                # Determine format and extract fields
                if "query" in item:
                    # chat_test_500 format: {label, query:{用户信息, 对话历史}}
                    q = item["query"]
                    user_info = q.get("用户信息", "")
                    history = q.get("对话历史", [])
                else:
                    # chat_test_100 format: {session_id, 用户信息, 对话历史}
                    user_info = item.get("用户信息", "")
                    history = item.get("对话历史", [])

                if not history:
                    continue

                lines: List[str] = []
                # Include a brief user info excerpt (first 3 fields)
                if user_info:
                    brief = "、".join(user_info.split("#")[1:4])
                    lines.append(f"[用户信息] {brief}")

                # Format dialogue turns
                for turn in history[:8]:  # limit to first 8 turns
                    if isinstance(turn, dict):
                        for speaker, text in turn.items():
                            lines.append(f"{speaker}：{text[:80]}")
                    elif isinstance(turn, str):
                        lines.append(turn[:100])

                if lines:
                    samples.append("\n".join(lines))

            return samples

        except Exception as exc:
            logger.warning(f"[PyTODApiCodeGenerator] 加载对话数据失败: {exc}")
            return []

    # ------------------------------------------------------------------
    # 内部 LLM 调用
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Phase 2: 测试用例构建
    # ------------------------------------------------------------------

    def build_test_cases(
        self,
        schema: "ServiceSchema",
        dialogue_data_path: Optional[Union[str, Path]] = None,
        max_cases_per_intent: int = 5,
    ) -> Dict[str, List[TestCaseItem]]:
        """Phase 2：为 schema 中的每个意图生成测试用例（LLM 驱动）。

        每个意图独立调用 LLM，生成 ``max_cases_per_intent`` 条包含真实业务值的
        测试用例。可选传入对话数据文件提供业务背景，使生成的槽位值更贴近真实对话。

        Args:
            schema: 服务 schema，包含意图和槽位定义。
            dialogue_data_path: 可选，真实对话数据文件路径（提供业务背景）。
            max_cases_per_intent: 每个意图最多生成的测试用例数。

        Returns:
            字典，key 为 intent_name，value 为 ``TestCaseItem`` 列表。
        """
        # Load dialogue hint (brief context, not the full samples)
        dialogue_hint = ""
        if dialogue_data_path:
            samples = self._load_dialogue_samples(dialogue_data_path, max_samples=2)
            if samples:
                brief = samples[0][:300]
                dialogue_hint = f"## 真实对话片段（参考提炼真实槽位值）\n{brief}\n\n"

        all_slot_descs: Dict[str, str] = {s.name: s.description for s in schema.slots}
        result: Dict[str, List[TestCaseItem]] = {}

        for intent in schema.intents:
            params_req = list(intent.required_slots)
            params_opt = list(intent.optional_slots)
            params_all = list(dict.fromkeys(params_req + params_opt))
            param_str = ", ".join([f"{p}=None" for p in params_all]) if params_all else ""

            req_desc = "\n".join(
                f"  - {p}: {all_slot_descs.get(p, p)}" for p in params_req
            ) or "  （无必填槽位）"
            opt_desc = "\n".join(
                f"  - {p}: {all_slot_descs.get(p, p)}" for p in params_opt
            ) or "  （无可选槽位）"
            rs_desc = "\n".join(
                f"  - {rs}" for rs in intent.result_slots
            ) or "  （无 result_slots，返回输入参数即可）"

            user_msg = _TEST_CASE_GEN_USER_TEMPLATE.format(
                service_name=schema.service_name,
                service_description=schema.description or schema.service_name,
                intent_name=intent.name,
                intent_description=intent.description or intent.name,
                func_name=intent.name,
                param_str=param_str,
                required_slots_desc=req_desc,
                optional_slots_desc=opt_desc,
                result_slots_desc=rs_desc,
                dialogue_hint=dialogue_hint,
                max_cases=max_cases_per_intent,
            )

            messages = [
                {"role": "system", "content": _TEST_CASE_GEN_SYSTEM},
                {"role": "user", "content": user_msg},
            ]

            try:
                raw = self._chat_sync(messages)
                cases = self._parse_test_cases(raw, intent)
                if cases:
                    result[intent.name] = cases
                    logger.info(
                        f"[PyTODApiCodeGenerator] {intent.name}: 生成 {len(cases)} 条测试用例"
                    )
                else:
                    logger.warning(
                        f"[PyTODApiCodeGenerator] {intent.name}: 测试用例解析失败，跳过"
                    )
            except Exception as exc:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 测试用例生成失败 ({exc})"
                )

        logger.info(
            f"[PyTODApiCodeGenerator] 测试用例构建完成: "
            f"{len(result)}/{len(schema.intents)} 个意图有测试用例"
        )
        return result

    @staticmethod
    def _parse_test_cases(
        raw: str,
        intent: "IntentDefinition",
    ) -> List[TestCaseItem]:
        """将 LLM 返回的 JSON 文本解析为 ``TestCaseItem`` 列表。"""
        raw = raw.strip()

        # Strip markdown code fences
        m = re.search(r"```(?:json|python)?\s*([\s\S]+?)\s*```", raw)
        if m:
            raw = m.group(1).strip()

        # Find first '[' — JSON array
        start = raw.find("[")
        end = raw.rfind("]")
        if start == -1 or end == -1:
            return []

        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return []

        if not isinstance(data, list):
            return []

        expected_keys = list(intent.result_slots) + ["status"]
        items: List[TestCaseItem] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            slots = entry.get("input_slots", {})
            if not isinstance(slots, dict):
                continue
            desc = entry.get("description", "")
            items.append(
                TestCaseItem(
                    input_slots=slots,
                    expected_keys=expected_keys,
                    description=desc,
                )
            )

        return items

    # ------------------------------------------------------------------
    # Phase 4: 函数修复
    # ------------------------------------------------------------------

    def repair_function(
        self,
        intent: "IntentDefinition",
        schema: "ServiceSchema",
        all_slot_descs: Dict[str, str],
        current_code: str,
        failures: List[Dict[str, Any]],
        iteration: int,
        total: int = 0,
        passed: int = 0,
    ) -> Optional[str]:
        """Phase 4：根据测试失败信息调用 LLM 修复函数体。

        Args:
            intent: 当前意图定义。
            schema: 服务 schema（提供上下文）。
            all_slot_descs: slot_name → description 映射。
            current_code: 当前（失败的）完整函数定义代码。
            failures: 失败用例列表，每条包含 input, expected, actual, error 字段。
            iteration: 当前修复轮次（从 1 开始）。
            total: 总测试用例数（用于显示通过率）。
            passed: 已通过的用例数。

        Returns:
            修复后的完整函数定义代码字符串，失败时返回 None。
        """
        params = list(dict.fromkeys(
            list(intent.required_slots) + list(intent.optional_slots)
        ))
        param_str = ", ".join([f"{p}=None" for p in params]) if params else ""

        rs_desc = "\n".join(
            f"  - {rs}: {all_slot_descs.get(rs, rs)}" for rs in intent.result_slots
        ) or "  （无专用 result_slots，返回输入参数即可）"

        # Format failure cases (limit to 5 for prompt length)
        fail_lines: List[str] = []
        for i, f in enumerate(failures[:5], 1):
            fail_lines.append(
                f"【失败 {i}】描述: {f.get('description', '')}  "
                f"输入: {json.dumps(f.get('input_slots', {}), ensure_ascii=False)}  "
                f"错误: {f.get('error', '返回值格式不符合预期')}"
            )
        pass_rate_str = f"{passed}/{total}" if total > 0 else "未知"

        user_msg = _REPAIR_USER_TEMPLATE.format(
            service_name=schema.service_name,
            intent_name=intent.name,
            intent_description=intent.description or intent.name,
            result_slots_desc=rs_desc,
            current_code=current_code,
            iteration=iteration,
            fail_count=len(failures),
            pass_rate=pass_rate_str,
            failures_text="\n".join(fail_lines),
        )

        messages = [
            {"role": "system", "content": _REPAIR_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            raw = self._chat_sync(messages)
            # Expect a full function definition
            cleaned = _clean_llm_function_body(raw, intent.name, param_str)
            if cleaned is None:
                logger.warning(
                    f"[PyTODApiCodeGenerator] {intent.name}: 修复响应无法解析（轮次 {iteration}）"
                )
                return None
            # Return as full function definition (header + body)
            header = "\n".join(_function_def_header(intent))
            return header + "\n" + cleaned
        except Exception as exc:
            logger.warning(
                f"[PyTODApiCodeGenerator] {intent.name}: 修复 LLM 调用失败 ({exc})"
            )
            return None


# Single-function fallback prompt (kept for generate_function_body)
_FUNCTION_GEN_SYSTEM = """\
你是一名 Python 开发专家，专门为任务型对话系统（ToD）编写 API 函数实现。

你将收到一个意图（intent）的函数签名、描述以及业务背景，需要生成该函数的 **完整函数体**。

## 要求
1. 保持函数签名不变（参数名和默认值 None）
2. 包含真实的业务逻辑处理，不要只是直接返回固定字符串
3. 可以直接调用文件中已定义的工具函数：`_parse_amount()`、`_ticket_id()`、
   `_calc_monthly_payment()`、`_next_work_day()`
4. 返回值包含所有 result_slots 字段和输入参数，以及 "status": "success"
5. 只输出函数体代码，不包含 def 行，4 空格缩进，不超过 25 行

## 输出格式
只输出函数体代码（4空格缩进），例如：
    _ok = bool(account_usage_status is not None)
    return {
        "verified_identity": _ok,
        "status": "success",
    }
"""

_FUNCTION_GEN_USER_TEMPLATE = """\
服务：{service_name}（{service_description}）

函数：def {func_name}({param_str}):
描述：{description}
输入槽位：
{slot_descriptions}
result_slots（必须在返回值中包含）：
{result_slots}
{few_shot_section}"""


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


def _clean_llm_module(raw: str, schema: ServiceSchema) -> Optional[str]:
    """从 LLM 响应中提取并验证完整模块的函数定义区。

    处理 markdown 代码块、多余说明文字、重复工具函数定义等常见问题。

    Returns:
        包含所有函数定义的 Python 代码字符串，或 None（无法解析为合法 Python）。
    """
    raw = raw.strip()

    # Strip markdown code fences
    m = re.search(r"```(?:python)?\s*([\s\S]+?)\s*```", raw)
    if m:
        raw = m.group(1).strip()

    # Remove any re-definition of shared helpers that LLM shouldn't emit
    helper_names = ("_parse_amount", "_ticket_id", "_calc_monthly_payment", "_next_work_day")
    lines = raw.splitlines()
    filtered: List[str] = []
    skip_block = False
    for line in lines:
        stripped = line.strip()
        # Detect start of a helper function re-definition
        if stripped.startswith("def ") and any(
            stripped.startswith(f"def {h}") for h in helper_names
        ):
            skip_block = True
        # Detect INTENT_REGISTRY block (we generate it ourselves)
        elif stripped.startswith("INTENT_REGISTRY"):
            skip_block = True
        elif skip_block and stripped and not stripped.startswith(" ") and not stripped.startswith("\t"):
            skip_block = False

        if not skip_block:
            filtered.append(line)

    raw = "\n".join(filtered).strip()

    # Find where the first 'def ' function starts (skip any leading prose)
    first_def = re.search(r"^def ", raw, re.MULTILINE)
    if first_def:
        raw = raw[first_def.start():]

    # Validate as Python source (wrap with minimal imports to satisfy ast.parse)
    minimal_preamble = "from __future__ import annotations\n"
    try:
        ast.parse(minimal_preamble + raw)
    except SyntaxError as exc:
        logger.debug(f"[_clean_llm_module] SyntaxError: {exc}")
        return None

    # Verify that expected intent functions are present
    expected = {intent.name for intent in schema.intents}
    found = set(re.findall(r"^def (\w+)\(", raw, re.MULTILINE))
    missing = expected - found
    if missing:
        logger.warning(
            f"[_clean_llm_module] LLM 生成的模块缺少以下函数: {missing}"
        )

    return raw


# ---------------------------------------------------------------------------
# Phase 4: 函数验证 — 使用测试用例执行并验证生成的函数
# ---------------------------------------------------------------------------

def _validate_function(
    intent: "IntentDefinition",
    func_code: str,
    test_cases: List[TestCaseItem],
    shared_helpers: str,
) -> _FuncValidation:
    """Phase 4：使用测试用例执行生成的函数并验证输出格式。

    验证标准（全部通过才算通过）：
    1. 函数执行无异常
    2. 返回值是一个 dict
    3. 返回值中 ``status`` 字段值为 ``"success"``
    4. 所有 ``expected_keys``（包含 result_slots）在返回值中都存在

    Args:
        intent: 意图定义（用于报告和 expected_keys 推断）。
        func_code: 完整的函数定义代码字符串（包含 def 行）。
        test_cases: 测试用例列表（Phase 2 构建）。
        shared_helpers: 共享工具函数代码（``_SHARED_HELPERS``），
            提供 ``_ticket_id`` 等工具给被测函数调用。

    Returns:
        ``_FuncValidation`` 对象，包含通过率和失败用例详情。
    """
    if not test_cases:
        return _FuncValidation(intent_name=intent.name, total=0, passed=0)

    # Compile shared helpers + function code into a namespace
    exec_source = "from __future__ import annotations\n" + shared_helpers + "\n" + func_code

    namespace: Dict[str, Any] = {}
    try:
        exec(compile(exec_source, "<generated>", "exec"), namespace)
    except SyntaxError as exc:
        return _FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"SyntaxError: {exc}",
        )
    except Exception as exc:
        return _FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"CompileError: {exc}",
        )

    func_obj = namespace.get(intent.name)
    if func_obj is None:
        return _FuncValidation(
            intent_name=intent.name,
            total=len(test_cases),
            passed=0,
            error=f"函数 {intent.name} 未在生成代码中找到",
        )

    passed = 0
    failures: List[Dict[str, Any]] = []

    for tc in test_cases:
        error_msg: Optional[str] = None
        result: Optional[Any] = None

        try:
            result = func_obj(**tc.input_slots)
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"

        # Validate result
        if error_msg is None:
            if not isinstance(result, dict):
                error_msg = f"返回值不是 dict，实际类型: {type(result).__name__}"
            elif result.get("status") != "success":
                error_msg = (
                    f"status != 'success'，实际值: {result.get('status')!r}  "
                    f"（完整返回: {json.dumps(result, ensure_ascii=False, default=str)[:200]}）"
                )
            else:
                missing = [k for k in tc.expected_keys if k not in result]
                if missing:
                    error_msg = (
                        f"返回值缺少字段: {missing}  "
                        f"（实际字段: {list(result.keys())}）"
                    )

        if error_msg is None:
            passed += 1
        else:
            failures.append({
                "description": tc.description,
                "input_slots": tc.input_slots,
                "error": error_msg,
            })

    return _FuncValidation(
        intent_name=intent.name,
        total=len(test_cases),
        passed=passed,
        failures=failures,
    )


# ---------------------------------------------------------------------------
# Phase 5: 验证报告写入
# ---------------------------------------------------------------------------

def _write_validation_report(
    schema_path: Path,
    validations: Dict[str, "_FuncValidation"],
    test_cases_by_intent: Dict[str, List[TestCaseItem]],
) -> Optional[Path]:
    """Phase 5：将验证结果写入 ``xxx_validation_report.json`` 文件。

    报告结构::

        {
          "schema": "anyihua_schema.json",
          "generated_at": "...",
          "summary": {"total_intents": 10, "validated": 8, "avg_pass_rate": 0.95},
          "intents": {
            "verify_identity": {
              "total_cases": 5, "passed": 5, "pass_rate": 1.0,
              "iterations": 0, "failures": []
            },
            ...
          }
        }

    Args:
        schema_path: schema 文件路径（用于命名报告文件和填充元数据）。
        validations: intent_name → ``_FuncValidation`` 映射。
        test_cases_by_intent: intent_name → ``TestCaseItem`` 列表映射。

    Returns:
        报告文件路径，写入失败时返回 None。
    """
    report_path = _companion_path(schema_path, "validation_report", suffix=".json")

    intent_report: Dict[str, Any] = {}
    for name, v in validations.items():
        intent_report[name] = {
            "total_cases": v.total,
            "passed": v.passed,
            "pass_rate": round(v.pass_rate, 4),
            "iterations": v.iterations,
            "error": v.error,
            "failures": v.failures[:3],   # keep at most 3 sample failures
        }

    total = len(validations)
    validated = sum(1 for v in validations.values() if v.total > 0)
    avg_rate = (
        sum(v.pass_rate for v in validations.values() if v.total > 0) / validated
        if validated > 0 else 0.0
    )

    report: Dict[str, Any] = {
        "schema": schema_path.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total_intents": total,
            "validated": validated,
            "skipped": total - validated,
            "avg_pass_rate": round(avg_rate, 4),
        },
        "intents": intent_report,
    }

    try:
        with open(report_path, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=2)
        logger.info(f"[SchemaDataBuilder] 已写入验证报告: {report_path}")
        return report_path
    except Exception as exc:
        logger.warning(f"[SchemaDataBuilder] 写入验证报告失败: {exc}")
        return None


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
        validations: Dict[str, _FuncValidation] = {}
        mode_str = ""

        if not schema.intents:
            intent_lines.extend(_generate_generic_function_lines(schema))
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
                        "\n".join(_function_def_header(intent)) + "\n" + llm_body
                    )
                    llm_count += 1
                else:
                    # Rule-based fallback for this intent
                    func_code = "\n".join(_generate_function_lines(intent))
                    rule_count += 1

                # Phase 4: Validate and iteratively repair (only when test cases exist)
                if intent_test_cases and llm_body is not None:
                    validation = _validate_function(
                        intent, func_code, intent_test_cases, _SHARED_HELPERS
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

                        new_validation = _validate_function(
                            intent, repaired_code, intent_test_cases, _SHARED_HELPERS
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
                    validations[intent.name] = _FuncValidation(
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
                intent_lines.extend(_generate_function_lines(intent))
                intent_lines.append('')
                rule_count += 1
            mode_str = f"规则生成 {rule_count} 个意图函数"

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
            _SHARED_HELPERS,
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
            _write_validation_report(schema_path, validations, test_cases_by_intent)

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
    """complaint/dispute 意图体：调用 _ticket_id() 生成工单号，返回受理信息。"""
    prefix = intent.name.upper()[:8].replace("_", "")
    lines = [
        f"    _ticket = _ticket_id('{prefix}')",
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
    """schedule 意图体：调用 _next_work_day() 计算下一个工作日作为回调时间。"""
    lines = [
        "    _callback_time = _next_work_day() + ' 10:00'",
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
