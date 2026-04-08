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


_REFINE_SYSTEM = """\
你是一名任务型对话系统设计专家。你收到的是一份由多条对话分别提取、合并而成的 SGD 格式 ServiceSchema。
由于不同对话可能对同一概念使用不同命名，该 schema 中可能存在重复、相似或高度相近的槽位（slots）和意图（intents）。

你的任务是对该 schema 进行整合、精炼，输出一份干净、无冗余的最终 schema。

## 整合规则

### 槽位（slots）整合
- 若两个槽位描述的是**同一业务字段**（名称不同但含义相同，如 `customer_name` / `user_name` / `客户姓名`），合并为一个，保留语义最清晰的英文下划线名称
- 若两个槽位仅是**拼写变体或英文/中文对应**同一概念，合并为一个
- 若两个槽位描述**不同但相关的字段**（如 `loan_amount` 和 `repayment_amount`），保留为独立槽位
- 合并时，`description` 取两者中更完整的一个；`possible_values` 取两者并集；`is_categorical` 只要有一个为 true 则设为 true

### 意图（intents）整合
- 若两个意图描述的是**相同用户操作**（如 `verify_identity` / `confirm_identity` / `check_identity`），合并为一个，保留最常用/最清晰的名称
- 若两个意图描述**不同阶段或不同目的**（如 `query_loan_status` 和 `apply_for_loan`），保留为独立意图
- 合并时，`required_slots` / `optional_slots` / `result_slots` 取并集，但只保留 `slots[]` 中定义的槽位名
- `is_transactional`：只要有一个为 true 则设为 true

## 注意事项
- **保守合并**：如不确定是否同义，宁可保留两个独立条目，不要强行合并
- **不得无故删减**：只能合并，不能直接删除任何有意义的槽位或意图
- 整合后的槽位 name 和意图 name 须保持英文小写下划线风格，与 `required_slots` 等字段引用一致
- 只输出 JSON，不加任何说明或 markdown 代码块

## 输出格式（与输入格式相同）

{
  "service_name": "...",
  "description": "...",
  "slots": [...],
  "intents": [...]
}"""

_REFINE_USER_TEMPLATE = """\
## 业务场景

名称：{scene_name}
描述：{scene_description}

## 待整合的 schema（共 {n_slots} 个槽位、{n_intents} 个意图，来自 {n_dialogues} 条对话的合并结果）

```json
{schema_json}
```

请对上述 schema 进行整合精炼，输出最终干净的 ServiceSchema（只输出 JSON）："""


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


def _merge_service_list(items: List[Any]) -> Optional[Dict[str, Any]]:
    """将列表中所有 dict 元素合并为一个 schema dict。

    slots 和 intents 按 ``name`` 字段去重合并（后出现的覆盖先出现的），
    其余顶层字段取第一个非空元素的值。

    用于以下两种场景：
    1. LLM 将 schema 拆分为多个服务对象返回时的合并（在 ``_try_parse_json`` 中调用）。
    2. 多批次合成结果的合并（在 ``SchemaSynthesizer.synthesize`` 中调用）。
    """
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


def _try_parse_json(text: str) -> Optional[Dict[str, Any]]:
    """尝试从 LLM 响应中解析 JSON，支持 markdown 代码块包裹。

    若 LLM 将 schema 包裹在数组中（如 ``[{...}]``），将数组中所有 dict 元素合并为
    一个 schema dict：slots 和 intents 列表跨所有元素合并，其余字段取第一个元素的值。
    这能正确处理 LLM 将 100+ 个意图拆分到多个服务对象中的情况。
    """

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

    def _synthesize_one_pass(
        self,
        scene_name: str,
        scene_description: str,
        slot_counter: Counter,
        intent_counter: Counter,
        slot_sample_values: Dict[str, List[str]],
        intent_sample_descs: Dict[str, List[str]],
        n_dialogues: int,
        fact_counter: Counter,
        fact_sample_descs: Dict[str, List[str]],
        batch_label: str = "",
    ) -> Tuple[Dict[str, Any], int]:
        """单批次 LLM 合成调用，支持渐进式缩减重试。

        当输入条目数超出模型上下文窗口时，自动将每类最大条目数减半后重试，
        直到成功或降至最低下限 10。

        Args:
            batch_label: 批次标识（如 "批次 1/3"），用于日志显示；空串时不显示批次信息。

        Returns:
            ``(schema_dict, effective_max_items)``：合成结果与本次实际展示给 LLM 的
            每类最大条目数。当 ``effective_max_items < len(intent_counter)`` 时，
            说明部分意图未被展示，调用方应用剩余意图再次调用本方法。
        """
        max_items = 200
        response: Optional[str] = None
        last_exc: Optional[Exception] = None

        while max_items >= 10:
            slots_text = _format_discovery_items(slot_counter, slot_sample_values, max_items=max_items)
            intents_text = _format_discovery_items(intent_counter, intent_sample_descs, max_items=max_items)
            facts_text = _format_discovery_items(
                fact_counter, fact_sample_descs, max_items=max_items
            )

            n_shown_intents = min(len(intent_counter), max_items)
            n_shown_slots = min(len(slot_counter), max_items)
            n_shown_facts = min(len(fact_counter), max_items)
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

            label_suffix = f"（{batch_label}）" if batch_label else ""
            if max_items < 200:
                logger.info(
                    f"[SchemaSynthesizer] 调用 LLM 合成 ServiceSchema{label_suffix} …"
                    f"（每类最多 {max_items} 条，输入已缩减）"
                )
            else:
                logger.info(f"[SchemaSynthesizer] 调用 LLM 合成 ServiceSchema{label_suffix} …")

            try:
                response = self._chat_sync(messages)
                break  # 成功，退出重试循环
            except Exception as exc:
                error_str = str(exc).lower()
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
                        "超过",
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

        effective_max = min(len(intent_counter), max_items)
        return schema_dict, effective_max

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

        当意图数量超过单次 LLM 调用的上下文窗口时，自动拆分为多批次分别合成后合并，
        确保所有发现的意图（而非仅频次最高的 N 个）都能被纳入最终 schema。

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
        _fact_sample_descs = fact_sample_descs or {}

        # 多批次合成策略：
        # 1. 第一批次使用全部意图，若超出上下文则自动缩减至 effective_batch_size
        # 2. 剩余意图按 effective_batch_size 拆分为后续批次依次合成
        # 3. 所有批次结果通过 _merge_service_list 合并为最终 schema
        all_intents_ordered: List[Tuple[str, int]] = intent_counter.most_common()
        total_intents = len(all_intents_ordered)

        schema_parts: List[Dict[str, Any]] = []
        effective_batch_size = 200  # 初始批次大小，会根据第一次成功调用自动调整
        intent_idx = 0

        while intent_idx < total_intents or not schema_parts:
            # 构造当前批次的意图 Counter
            batch_pairs = all_intents_ordered[intent_idx: intent_idx + effective_batch_size]
            batch_intent_counter = Counter(dict(batch_pairs))

            batch_num = len(schema_parts) + 1
            # 仅当需要多批次时显示批次标签（第一批且覆盖全部意图则不显示）
            batch_label = ""
            if total_intents > effective_batch_size or batch_num > 1:
                remaining = total_intents - intent_idx
                total_batches = (total_intents + effective_batch_size - 1) // effective_batch_size
                batch_label = f"批次 {batch_num}/{total_batches}，意图 {intent_idx + 1}–{intent_idx + len(batch_pairs)}/{total_intents}"

            schema_dict, achieved_max = self._synthesize_one_pass(
                scene_name=scene_name,
                scene_description=scene_description,
                slot_counter=slot_counter,
                intent_counter=batch_intent_counter,
                slot_sample_values=slot_sample_values,
                intent_sample_descs=intent_sample_descs,
                n_dialogues=n_dialogues,
                fact_counter=_fact_counter,
                fact_sample_descs=_fact_sample_descs,
                batch_label=batch_label,
            )

            schema_parts.append(schema_dict)

            # achieved_max 是本次实际展示给 LLM 的意图数，用于推进索引
            intent_idx += achieved_max
            # 如果因为上下文限制批次变小，则后续批次也使用同样大小
            if achieved_max < effective_batch_size:
                effective_batch_size = achieved_max
                logger.info(
                    f"[SchemaSynthesizer] 上下文限制：后续批次大小调整为 {effective_batch_size} 个意图/批"
                )

            # 若第一批已覆盖所有意图，直接退出
            if intent_idx >= total_intents:
                break

        # 合并多批次结果（单批次时直接使用，避免不必要的合并）
        if len(schema_parts) == 1:
            merged = schema_parts[0]
        else:
            logger.info(
                f"[SchemaSynthesizer] 合并 {len(schema_parts)} 批次合成结果 …"
            )
            merged_result = _merge_service_list(schema_parts)
            if merged_result is None:
                merged_result = schema_parts[0]
            merged = merged_result

        # 补充 service_name 缺省值
        if not merged.get("service_name"):
            merged["service_name"] = re.sub(r"\s+", "_", scene_name)

        # 补充所有缺失字段的默认值
        merged = _fill_schema_defaults(merged, scene_name=scene_name)

        n_batches = len(schema_parts)
        batch_note = f"（{n_batches} 批次）" if n_batches > 1 else ""
        logger.info(
            f"[SchemaSynthesizer] ✓ 合成完成{batch_note} — "
            f"{len(merged.get('slots', []))} 个槽位，"
            f"{len(merged.get('intents', []))} 个意图"
        )
        return merged

    def refine(
        self,
        schema_dict: Dict[str, Any],
        scene_name: str,
        scene_description: str,
        n_dialogues: int = 0,
    ) -> Dict[str, Any]:
        """
        对合并后的 schema 进行整合精炼，消除跨对话产生的相似/重复槽位和意图。

        在多条对话各自合成 mini-schema、再通过名称去重合并之后调用本方法。
        此时 schema 中可能存在语义相近但命名不同的槽位（如 ``customer_name`` /
        ``user_name``）或意图（如 ``verify_identity`` / ``confirm_identity``）。
        本方法通过额外一次 LLM 调用，让模型识别并合并这类冗余，输出最终干净的
        schema。

        若 schema 本身已很精简（槽位 + 意图 ≤ 5 个），则跳过 LLM 调用直接返回。

        参数
        ----
        schema_dict:
            合并后的 schema dict（由 :func:`_merge_service_list` 或
            :meth:`synthesize` 返回）。
        scene_name:
            业务场景名称（中文）。
        scene_description:
            场景描述（一句话）。
        n_dialogues:
            参与本次处理的对话总条数（仅用于 prompt 说明）。

        返回
        ----
        整合精炼后的 schema dict。若 LLM 调用失败，原样返回输入 schema。
        """
        n_slots = len(schema_dict.get("slots", []))
        n_intents = len(schema_dict.get("intents", []))

        # 槽位 + 意图总数过少时，跳过精炼（无意义，且可能引入幻觉）
        if n_slots + n_intents <= 1:
            logger.info(
                f"[SchemaSynthesizer] schema 条目极少（{n_slots} 槽位 + {n_intents} 意图），跳过精炼"
            )
            return schema_dict

        logger.info(
            f"[SchemaSynthesizer] 开始整合精炼：{n_slots} 个槽位，{n_intents} 个意图 …"
        )

        schema_json = json.dumps(schema_dict, ensure_ascii=False, indent=2)
        user_msg = _REFINE_USER_TEMPLATE.format(
            scene_name=scene_name,
            scene_description=scene_description or scene_name,
            n_slots=n_slots,
            n_intents=n_intents,
            n_dialogues=n_dialogues,
            schema_json=schema_json,
        )
        messages = [
            {"role": "system", "content": _REFINE_SYSTEM},
            {"role": "user", "content": user_msg},
        ]

        try:
            response = self._chat_sync(messages)
        except Exception as exc:
            logger.warning(
                f"[SchemaSynthesizer] 精炼调用失败，跳过精炼步骤，返回原始 schema。原始错误: {exc}"
            )
            return schema_dict

        logger.debug(f"[SchemaSynthesizer] 精炼 LLM 原始响应（前 500 字）: {response[:500]}")

        refined = _try_parse_json(response)
        if refined is None:
            logger.warning(
                "[SchemaSynthesizer] 精炼结果无法解析为 JSON，返回原始 schema。"
                f"原始响应:\n{response[:400]}"
            )
            return schema_dict

        # 保留 service_name（LLM 可能改动）
        if not refined.get("service_name"):
            refined["service_name"] = schema_dict.get("service_name", re.sub(r"\s+", "_", scene_name))

        refined = _fill_schema_defaults(refined, scene_name=scene_name)

        n_slots_after = len(refined.get("slots", []))
        n_intents_after = len(refined.get("intents", []))

        # 精炼不应减少槽位或意图数量：若 LLM 错误地删除了条目，将精炼结果与原始 schema
        # 合并，把被丢弃的独立条目恢复回来（精炼合并的同义项仍保持合并后的名称）。
        if n_slots_after < n_slots or n_intents_after < n_intents:
            logger.warning(
                f"[SchemaSynthesizer] 精炼后条目数减少（槽位 {n_slots}→{n_slots_after}，"
                f"意图 {n_intents}→{n_intents_after}），合并回原始 schema 以恢复丢失条目"
            )
            restored = _merge_service_list([refined, schema_dict])
            if restored is not None:
                refined = _fill_schema_defaults(restored, scene_name=scene_name)
                n_slots_after = len(refined.get("slots", []))
                n_intents_after = len(refined.get("intents", []))
                logger.info(
                    f"[SchemaSynthesizer] 恢复后 — {n_slots_after} 个槽位，"
                    f"{n_intents_after} 个意图"
                )

        logger.info(
            f"[SchemaSynthesizer] ✓ 精炼完成 — "
            f"{n_slots} → {n_slots_after} 个槽位，"
            f"{n_intents} → {n_intents_after} 个意图"
        )
        return refined
