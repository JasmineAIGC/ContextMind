"""
Schema 合成器

将 LLM 开放式发现阶段提取到的原始槽位 / 意图汇总，
通过第二次 LLM 调用合成一份干净、结构化的 SGD 格式 ServiceSchema。

合成 prompt 要求 LLM 输出：
    - service_name, description
    - slots[]：name / description / is_categorical / possible_values
    - intents[]：name / description / required_slots / optional_slots /
                 result_slots / is_transactional
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# 合成 prompt 模板
# ------------------------------------------------------------------

_SYNTHESIS_SYSTEM = """\
你是一名任务型对话系统设计专家，擅长将业务对话的原始知识整理为标准化的 ServiceSchema。

你需要根据从对话中自动发现的槽位（slots）和意图（intents），
合成一份可供 PyTOD 等任务型对话算法直接使用的 SGD 格式 ServiceSchema。

## 输出格式（严格 JSON，只输出 JSON，不加任何说明）

{
  "service_name": "<英文服务名，如 BankLoan_OutboundCall>",
  "description": "<一句话中文描述：服务目标和核心流程>",
  "slots": [
    {
      "name": "<slot 名称（英文或拼音下划线，如 customer_name）>",
      "description": "<中文描述，简洁说明该槽位含义>",
      "is_categorical": <true 或 false>,
      "possible_values": ["<仅当 is_categorical=true 时填写枚举值，否则留空列表 []>"]
    }
  ],
  "intents": [
    {
      "name": "<意图名称（英文动词短语，如 verify_identity）>",
      "description": "<中文描述，说明该意图的触发条件和目标>",
      "is_transactional": <true 或 false，true 表示执行后状态不可撤销（如提交、转账）>,
      "required_slots": ["<调用此意图必填的槽位名列表>"],
      "optional_slots": ["<可选槽位名列表>"],
      "result_slots": ["<API 返回后填充的槽位名列表>"]
    }
  ]
}

## 规范要求

- service_name：英文，CamelCase_下划线风格（如 AnYiHua_OutboundCall）
- 槽位 name：英文小写下划线，与意图中引用的名称保持一致
- is_categorical：只有当槽位的取值是有限枚举集时为 true（如 true/false、状态分类等），
  自由文本值（姓名、金额、日期等）设为 false
- is_transactional：只有当该意图会触发不可逆操作时为 true（如转账、提交工单）
- required_slots / optional_slots / result_slots 中引用的 slot 名必须与 slots[] 中定义的 name 完全一致
- **保留发现列表中的所有槽位和意图**，不得随意删减；仅当两个名称完全相同或拼写错误时才合并
- 允许将明显同义的发现项合并（如 available_credit / current_credit_limit 可合并为一个），
  但合并须保守，宁多勿少；合并后保留出现频次最高的名称作为标准名
- 只输出 JSON，不要加 markdown 代码块"""

_SYNTHESIS_USER_TEMPLATE = """\
## 业务场景

名称：{scene_name}
描述：{scene_description}

## 从 {n_dialogues} 条对话中自动发现的槽位（共 {n_slots} 个，按出现频次降序）

{slots_text}

## 从 {n_dialogues} 条对话中自动发现的意图（共 {n_intents} 个，按出现频次降序）

{intents_text}

## 从 {n_dialogues} 条对话中自动发现的关键事实（共 {n_facts} 个，按出现频次降序）

{facts_text}

**重要：上方共发现 {n_slots} 个槽位、{n_intents} 个意图，输出的 schema 必须包含全部（或绝大多数）发现项，不得随意删减。**

请合成标准 ServiceSchema（只输出 JSON）："""


# ------------------------------------------------------------------
# 辅助函数
# ------------------------------------------------------------------


def _format_discovery_items(
    counter: Counter,
    sample_values: Dict[str, List[str]],
    max_items: int = 200,
) -> str:
    """将 Counter 和样本值字典格式化为可读文本，供 prompt 使用。"""
    lines: List[str] = []
    for name, freq in counter.most_common(max_items):
        samples = sample_values.get(name, [])
        sample_str = ""
        if samples:
            shown = samples[:5]
            sample_str = f"  样本值: {', '.join(str(v) for v in shown)}"
        lines.append(f"- {name}（出现 {freq} 次）{sample_str}")
    return "\n".join(lines) if lines else "（无）"


def _fill_schema_defaults(
    schema_dict: Dict[str, Any],
    scene_name: str = "",
) -> Dict[str, Any]:
    """确保 schema dict 中所有必需字段都有值，缺失时填充默认值并记录警告。

    LLM 可能省略某些字段（如 ``description``、``is_categorical``、
    ``result_slots`` 等），此函数在解析后统一补全，避免下游模块
    因 KeyError / AttributeError 崩溃。
    """
    missing: List[str] = []

    # ── 顶层字段 ──────────────────────────────────────────────────────
    if not schema_dict.get("description"):
        schema_dict["description"] = scene_name or schema_dict.get("service_name", "")
        missing.append("description")

    # ── slots ─────────────────────────────────────────────────────────
    for slot in schema_dict.get("slots", []):
        slot_name = slot.get("name", "<unnamed>")
        if not slot.get("description"):
            slot["description"] = slot_name
            missing.append(f"slots[{slot_name!r}].description")
        if "is_categorical" not in slot or slot["is_categorical"] is None:
            slot["is_categorical"] = False
            missing.append(f"slots[{slot_name!r}].is_categorical")
        if not isinstance(slot.get("possible_values"), list):
            slot["possible_values"] = []
            missing.append(f"slots[{slot_name!r}].possible_values")

    # ── intents ───────────────────────────────────────────────────────
    for intent in schema_dict.get("intents", []):
        intent_name = intent.get("name", "<unnamed>")
        if not intent.get("description"):
            intent["description"] = intent_name
            missing.append(f"intents[{intent_name!r}].description")
        if "is_transactional" not in intent or intent["is_transactional"] is None:
            intent["is_transactional"] = False
            missing.append(f"intents[{intent_name!r}].is_transactional")
        for field in ("required_slots", "result_slots"):
            if not isinstance(intent.get(field), list):
                intent[field] = []
                missing.append(f"intents[{intent_name!r}].{field}")
        if "optional_slots" not in intent or intent["optional_slots"] is None:
            intent["optional_slots"] = []
            missing.append(f"intents[{intent_name!r}].optional_slots")

    if missing:
        logger.warning(
            f"[SchemaSynthesizer] LLM 输出缺少以下字段，已补充默认值: "
            + ", ".join(missing)
        )

    return schema_dict


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """尝试从 LLM 响应中解析 JSON，支持 markdown 代码块包裹。

    若 LLM 将 schema 包裹在数组中（如 ``[{...}]``），将数组中所有 dict 元素合并为
    一个 schema dict：slots 和 intents 列表跨所有元素合并，其余字段取第一个元素的值。
    这能正确处理 LLM 将 100+ 个意图拆分到多个服务对象中的情况。
    """

    def _merge_service_list(items: List[Any]) -> Optional[Dict[str, Any]]:
        """将列表中所有 dict 元素合并为一个 schema dict。"""
        dicts = [item for item in items if isinstance(item, dict)]
        if not dicts:
            return None
        # 深拷贝第一个 dict 避免修改 LLM 返回的原始数据
        merged: Dict[str, Any] = copy.deepcopy(dicts[0])

        def _merge_named_list(base: List[Dict], extra: List[Dict]) -> List[Dict]:
            """按 name 字段去重合并两个 dict 列表，后出现的覆盖先出现的。"""
            index = {item.get("name"): item for item in base if item.get("name")}
            for item in extra:
                if item.get("name"):
                    index[item.get("name")] = item
            return list(index.values())

        for d in dicts[1:]:
            merged["slots"] = _merge_named_list(merged.get("slots", []), d.get("slots", []))
            merged["intents"] = _merge_named_list(merged.get("intents", []), d.get("intents", []))
        return merged

    def _unwrap(obj: Any) -> Optional[Dict[str, Any]]:
        """若 obj 是 dict 则直接返回；若是非空 list 则合并所有 dict 元素。"""
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, list) and obj:
            return _merge_service_list(obj)
        return None

    # 尝试直接解析
    try:
        result = _unwrap(json.loads(text.strip()))
        if result is not None:
            return result
    except json.JSONDecodeError:
        pass
    # 去掉 markdown 代码块
    m = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", text)
    if m:
        try:
            result = _unwrap(json.loads(m.group(1)))
            if result is not None:
                return result
        except json.JSONDecodeError:
            pass
    # 提取第一个 { ... }
    m2 = re.search(r"\{[\s\S]+\}", text)
    if m2:
        try:
            result = _unwrap(json.loads(m2.group(0)))
            if result is not None:
                return result
        except json.JSONDecodeError:
            pass
    return None


# ------------------------------------------------------------------
# SchemaSynthesizer
# ------------------------------------------------------------------


class SchemaSynthesizer:
    """
    将开放式发现结果合成为干净的 SGD ServiceSchema。

    参数
    ----
    llm_client:
        :class:`contextmind.infra.llm_client.AdkLLMClient` 实例；
        若为 None，则从 ``.env`` 自动加载。
    """

    def __init__(self, llm_client: Optional[AdkLLMClient] = None) -> None:
        if llm_client is None:
            try:
                llm_client = AdkLLMClient(config=LLMConfig.from_env())
            except Exception as exc:
                raise RuntimeError(
                    "LLM 客户端初始化失败，请在 .env 中配置 LLM_API_KEY / "
                    f"LLM_BASE_URL / LLM_MODEL。原始错误: {exc}"
                ) from exc
        self._llm = llm_client

    # ------------------------------------------------------------------
    # 内部辅助
    # ------------------------------------------------------------------

    def _chat_sync(self, messages: List[Dict[str, Any]]) -> str:
        """以同步方式调用 LLM 的 chat_async（复用 generate 的 asyncio 模式）。"""
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

    def synthesize(
        self,
        scene_name: str,
        scene_description: str,
        slot_counter: Counter,
        intent_counter: Counter,
        slot_sample_values: Dict[str, List[str]],
        intent_sample_descs: Dict[str, List[str]],
        n_dialogues: int,
        fact_counter: Optional[Counter] = None,
        fact_sample_descs: Optional[Dict[str, List[str]]] = None,
    ) -> Dict[str, Any]:
        """
        调用 LLM 合成 SGD ServiceSchema dict。

        参数
        ----
        scene_name:
            业务场景名称（中文，如 "银行贷款外呼"）。
        scene_description:
            场景描述（中文一句话）。
        slot_counter:
            ``Counter({slot_name: 出现次数})``。
        intent_counter:
            ``Counter({intent_name: 出现次数})``。
        slot_sample_values:
            ``{slot_name: [sample_value, ...]}``，最多保留前 5 个样本值。
        intent_sample_descs:
            ``{intent_name: [description, ...]}``，最多保留前 3 条样本描述。
        n_dialogues:
            参与发现的对话条数。
        fact_counter:
            ``Counter({fact_label: 出现次数})``（可选）。
        fact_sample_descs:
            ``{fact_label: [description, ...]}``（可选）。

        返回
        ----
        SGD 格式的单服务 schema dict（不带顶层列表包裹）。
        """
        _fact_counter = fact_counter or Counter()

        # 渐进式缩减策略：当输入超出模型上下文窗口时，逐步减少每类最大条目数后重试。
        # 初始 max_items=200，每次减半，直到成功或降至最低下限 10。
        max_items = 200
        response: Optional[str] = None
        last_exc: Optional[Exception] = None

        while max_items >= 10:
            slots_text = _format_discovery_items(slot_counter, slot_sample_values, max_items=max_items)
            intents_text = _format_discovery_items(intent_counter, intent_sample_descs, max_items=max_items)
            facts_text = _format_discovery_items(
                _fact_counter, fact_sample_descs or {}, max_items=max_items
            )

            # n_shown_* 反映实际展示给 LLM 的条目数（max_items 缩减后可能小于发现总数），
            # 与 intents_text/slots_text 保持一致，避免 LLM 看到矛盾的数量提示。
            n_shown_intents = min(len(intent_counter), max_items)
            n_shown_slots = min(len(slot_counter), max_items)
            n_shown_facts = min(len(_fact_counter), max_items)
            user_msg = _SYNTHESIS_USER_TEMPLATE.format(
                scene_name=scene_name,
                scene_description=scene_description or scene_name,
                n_dialogues=n_dialogues,
                slots_text=slots_text,
                intents_text=intents_text,
                facts_text=facts_text,
                n_slots=n_shown_slots,
                n_intents=n_shown_intents,
                n_facts=n_shown_facts,
            )

            messages = [
                {"role": "system", "content": _SYNTHESIS_SYSTEM},
                {"role": "user", "content": user_msg},
            ]

            if max_items < 200:
                logger.info(
                    f"[SchemaSynthesizer] 调用 LLM 合成 ServiceSchema …"
                    f"（每类最多 {max_items} 条，输入已缩减）"
                )
            else:
                logger.info("[SchemaSynthesizer] 调用 LLM 合成 ServiceSchema …")

            try:
                response = self._chat_sync(messages)
                break  # 成功，退出重试循环
            except Exception as exc:
                error_str = str(exc).lower()
                # 检测 token 超限相关错误（litellm / openai / vLLM / qwen 均可能触发）
                is_context_error = any(
                    kw in error_str
                    for kw in (
                        "context_window_exceeded",
                        "context window",
                        "context length",
                        "maximum context length",
                        "input is too long",
                        "content too large",
                        "request too large",
                        "input length",
                        "max_tokens",
                        "tokens exceed",
                        "prompt is too long",
                        "超过",  # 中文错误消息中的"超过"
                    )
                )
                if is_context_error and max_items > 10:
                    max_items = max(10, max_items // 2)
                    logger.warning(
                        f"[SchemaSynthesizer] 输入超出模型上下文限制，"
                        f"缩减每类最大条目数至 {max_items} 后重试… 原始错误: {exc}"
                    )
                    last_exc = exc
                    continue
                if is_context_error:
                    # max_items 已降至最低下限仍超限，记录后退出循环
                    last_exc = exc
                    break
                raise RuntimeError(f"LLM 调用失败: {exc}") from exc

        if response is None:
            raise RuntimeError(
                f"输入数据过多，即使缩减至最低条目数（{max_items}）仍超出模型上下文限制。"
                f"原始错误: {last_exc}"
            )

        logger.debug(f"[SchemaSynthesizer] LLM 原始响应（前 500 字）: {response[:500]}")

        schema_dict = _try_parse_json(response)
        if schema_dict is None:
            raise ValueError(
                f"LLM 返回的 Schema 无法解析为 JSON。原始响应:\n{response[:800]}"
            )

        # 补充 service_name 缺省值
        if not schema_dict.get("service_name"):
            schema_dict["service_name"] = re.sub(r"\s+", "_", scene_name)

        # 补充所有缺失字段的默认值
        schema_dict = _fill_schema_defaults(schema_dict, scene_name=scene_name)

        logger.info(
            f"[SchemaSynthesizer] ✓ 合成完成 — "
            f"{len(schema_dict.get('slots', []))} 个槽位，"
            f"{len(schema_dict.get('intents', []))} 个意图"
        )
        return schema_dict
