"""
安逸花外呼 · 对话数据知识库构建 3 步管道

实现 docs/analysis/dialogue-to-knowledge-pipeline.md 中描述的完整流程：

  Step 1: Schema 发现（LLM 归纳）
    从少量抽样对话中通过 LLM 自动发现意图与槽位，
    使用 induce_schema_with_llm 归纳出候选 Schema。

  Step 2: Schema 合并精化
    将 Step 1 发现的 Schema 与预定义 Schema（resources/anyihua_sgd/schema.json）
    合并，产出包含两者信息的完整 merged_schema。

  Step 3: LLM 驱动的 SGD 全量转换（附 langextract 溯源对齐）
    对全量对话数据逐条调用 LLM 提取意图和槽位，然后将提取结果
    通过 langextract WordAligner 批量回溯对齐到对话原文的字符区间
    （char_interval），构建标准 SGD 格式，每条提取均有完整溯源。

langextract 使用说明（安逸花外呼对话特殊处理）：
  · 所有 LLM 调用通过 .env 中定义的 SimpleLLMClient，
    不使用 langextract 内置的 Gemini 模型。
  · 使用 langextract.data.Extraction / ExampleData / CharInterval / AlignmentStatus
    作为溯源数据的正式表示，使每个意图/槽位可追溯到原文字符区间。
  · 使用 langextract.resolver.WordAligner 和 langextract.tokenizer.UnicodeTokenizer
    将 extraction_text 批量回溯定位到对话原文。
  · extraction_text 必须是对话中出现过的原始文本片段（verbatim）：
    - 用户意图（intent）：extraction_text = 用户发言原话，意图编码放入 attributes["intent_name"]
    - 槽位值（slot_value）：extraction_text = 槽位的原始值文本，槽位名放入 attributes["slot_name"]
    - 系统意图（system_intent）：extraction_text = 坐席发言原话，方法名放入 attributes["method_name"]

典型使用::

    from pathlib import Path
    from contextmind.infra.llm_client import SimpleLLMClient
    from contextmind.scenarios.anyihua.schema_extraction.pipeline import run_pipeline

    llm = SimpleLLMClient()
    summary = run_pipeline(
        input_path=Path("resources/data/chat_test_100.json"),
        predefined_schema_path=Path("resources/anyihua_sgd/schema.json"),
        output_dir=Path("data/anyihua_sgd_pipeline"),
        llm_client=llm,
    )
    print(summary)
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# langextract — 溯源对齐核心依赖
# 用于将每一个意图/槽位提取结果回溯定位到对话原文的字符区间（char_interval），
# 实现完整的溯源可追踪性（provenance traceability）。
# 注意：仅使用 langextract 的数据结构与 WordAligner；
#       所有 LLM 调用仍通过 SimpleLLMClient（.env 配置），
#       不调用 langextract 内置的 Gemini 模型。
# ---------------------------------------------------------------------------
from langextract.data import AlignmentStatus, CharInterval, ExampleData, Extraction
from langextract.resolver import WordAligner
from langextract.tokenizer import UnicodeTokenizer

from contextmind.infra.logger import get_logger

from .llm_induction import induce_schema_with_llm
from .schema import PartialIntent, PartialServiceSchema, PartialSlot

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："
_SERVICE_NAME = "AnYiHua_1"

# SGD 允许的最大对话文件行数（遵循 SGD 规范约定的每文件 1000 条）
_DIALOGUES_PER_FILE = 1000

# 意图 → CRM API 方法名映射（Step 3 service_call 填充）
_INTENT_TO_API: Dict[str, Optional[str]] = {
    "verify_identity": "verify_customer",
    "explain_credit_limit": "query_account",
    "explain_interest_rate": "calculate_repayment",
    "calculate_repayment": "calculate_repayment",
    "explain_displayed_amount": "query_account",
    "handle_loan_dispute": "query_loan_records",
    "guide_loan_operation": "query_account",
    "escalate_to_human": None,
    "say_goodbye": None,
    "general_inquiry": None,
}


# ---------------------------------------------------------------------------
# langextract 对齐工具
# ---------------------------------------------------------------------------

#: 向后兼容的 AlignmentStatus 字符串别名（保持现有调用不受影响）
MATCH_EXACT: str = AlignmentStatus.MATCH_EXACT.value
MATCH_LESSER: str = AlignmentStatus.MATCH_LESSER.value
MATCH_FUZZY: str = AlignmentStatus.MATCH_FUZZY.value

#: 模块级 UnicodeTokenizer 单例（线程安全，可复用）
_TOKENIZER = UnicodeTokenizer()
#: 模块级 WordAligner 单例
_WORD_ALIGNER = WordAligner()


def _align_extractions(
    extractions: List[Extraction],
    source_text: str,
) -> List[Extraction]:
    """
    使用 langextract WordAligner 将一组 Extraction 回溯对齐到对话原文。

    每个 Extraction 的 ``char_interval`` 和 ``alignment_status`` 将被
    填充为对齐结果，使每条提取信息可精确追溯到原文字符区间（溯源）。

    参数:
        extractions:  待对齐的 Extraction 列表（extraction_text 必须是对话原文片段）
        source_text:  完整对话文本（含"坐席："/"用户："前缀）

    返回:
        对齐后的 Extraction 列表（char_interval / alignment_status 已填充）
    """
    if not extractions or not source_text:
        return extractions
    try:
        aligned_groups = _WORD_ALIGNER.align_extractions(
            [extractions],
            source_text,
            token_offset=0,
            char_offset=0,
            tokenizer_impl=_TOKENIZER,
        )
        if not aligned_groups:
            logger.warning("langextract WordAligner 返回空结果，溯源对齐跳过")
            return extractions
        return list(aligned_groups[0])
    except Exception as exc:
        logger.warning(f"langextract WordAligner 对齐失败，溯源对齐跳过: {exc}")
        return extractions


def _extraction_to_dict(ext: Extraction) -> Dict[str, Any]:
    """
    将 langextract Extraction 对象序列化为可 JSON 化的字典。

    注意：AlignmentStatus 枚举转换为字符串值，CharInterval 转换为
    {"start_pos": int, "end_pos": int} 字典，保持与旧版 dict 格式兼容。
    """
    char_interval: Optional[Dict[str, Any]] = None
    if ext.char_interval is not None:
        char_interval = {
            "start_pos": ext.char_interval.start_pos,
            "end_pos": ext.char_interval.end_pos,
        }
    return {
        "extraction_class": ext.extraction_class,
        "extraction_text": ext.extraction_text,
        "char_interval": char_interval,
        "alignment_status": ext.alignment_status.value if ext.alignment_status else None,
        "attributes": ext.attributes,
    }


def _example_data_to_dict(example: ExampleData) -> Dict[str, Any]:
    """
    将 langextract ExampleData 对象序列化为可 JSON 化的字典。

    输出格式与旧版 dict-based ``langextract_example`` 字段完全兼容，
    确保下游代码无需修改。
    """
    return {
        "text": example.text,
        "extractions": [_extraction_to_dict(e) for e in example.extractions],
    }


# ---------------------------------------------------------------------------
# 工具函数：对话文本处理
# ---------------------------------------------------------------------------


def _parse_dialogue_lines(raw_dialogue: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    将 chat_test 格式的对话历史解析为 (speaker, utterance) 列表。

    支持两种格式：
    - chat_test 格式：含 ``对话历史`` 字符串列表（如 "坐席：诶您好..."）
    - SGD 格式：含 ``turns`` 列表

    返回:
        List of (speaker, utterance) 元组，speaker 为 "SYSTEM" 或 "USER"
    """
    lines: List[Tuple[str, str]] = []

    if "对话历史" in raw_dialogue:
        for line in raw_dialogue.get("对话历史", []):
            line = str(line)
            if line.startswith(_AGENT_PREFIX):
                lines.append(("SYSTEM", line[len(_AGENT_PREFIX):]))
            elif line.startswith(_USER_PREFIX):
                lines.append(("USER", line[len(_USER_PREFIX):]))
            else:
                logger.warning(
                    f"对话行缺少角色前缀（期望'坐席：'或'用户：'），默认当作 USER 处理: {line[:40]!r}"
                )
                lines.append(("USER", line))
        # 追加参考坐席回复作为最后一个 SYSTEM turn
        reference_response = raw_dialogue.get("坐席回复", "")
        if reference_response:
            lines.append(("SYSTEM", reference_response))
    elif "turns" in raw_dialogue:
        for turn in raw_dialogue["turns"]:
            speaker_raw = turn.get("speaker", "USER")
            speaker = "SYSTEM" if speaker_raw == "SYSTEM" else "USER"
            lines.append((speaker, turn.get("utterance", "")))

    return lines


def _dialogue_to_text(lines: List[Tuple[str, str]]) -> str:
    """将 (speaker, utterance) 列表转换为带前缀的纯文本，用于 langextract 对齐。"""
    parts = []
    for speaker, utterance in lines:
        prefix = _AGENT_PREFIX if speaker == "SYSTEM" else _USER_PREFIX
        parts.append(f"{prefix}{utterance}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Step 1: Schema 发现
# ---------------------------------------------------------------------------


def discover_schema_step1(
    dialogues: List[Dict[str, Any]],
    llm_client: Any,
    sample_n: int = 50,
    service_name: str = _SERVICE_NAME,
    seed: int = 42,
) -> PartialServiceSchema:
    """
    Step 1：从抽样对话中通过 LLM 归纳候选 Schema。

    从全量对话中分层抽样（按对话长度：短/中/长各取约三分之一），
    调用 induce_schema_with_llm 归纳出意图和槽位定义。

    安逸花对话特殊处理：
    - 对话文本保留"坐席："/"用户："前缀，帮助 LLM 区分角色
    - 支持 chat_test 格式（``对话历史``）和 SGD 格式（``turns``）

    参数:
        dialogues:    对话列表（chat_test 或 SGD 格式）
        llm_client:   SimpleLLMClient 实例（从 .env 配置加载）
        sample_n:     抽样数量（默认 50）
        service_name: 服务名称（默认 "AnYiHua_1"）
        seed:         随机种子（默认 42，保证可重现）

    返回:
        PartialServiceSchema（通过 LLM 归纳）
    """
    rng = random.Random(seed)

    # 按对话长度分层
    def _dialogue_length(d: Dict[str, Any]) -> int:
        if "对话历史" in d:
            return len(d["对话历史"])
        return len(d.get("turns", []))

    sorted_dialogues = sorted(dialogues, key=_dialogue_length)
    n = len(sorted_dialogues)
    third = max(1, n // 3)

    short = sorted_dialogues[:third]
    mid = sorted_dialogues[third : 2 * third]
    long = sorted_dialogues[2 * third :]

    # 各层按比例抽样
    per_layer = max(1, sample_n // 3)
    sample: List[Dict[str, Any]] = []
    for layer in (short, mid, long):
        k = min(per_layer, len(layer))
        sample.extend(rng.sample(layer, k))

    logger.info(
        f"[Step 1] 从 {n} 条对话中抽样 {len(sample)} 条进行 Schema 归纳..."
    )

    schema = induce_schema_with_llm(sample, llm_client, service_name=service_name)
    logger.info(
        f"[Step 1] 归纳完成：{len(schema.intents)} 个意图，{len(schema.slots)} 个槽位"
    )
    return schema


# ---------------------------------------------------------------------------
# Step 2: Schema 合并
# ---------------------------------------------------------------------------


def merge_schemas_step2(
    discovered: PartialServiceSchema,
    predefined: PartialServiceSchema,
) -> PartialServiceSchema:
    """
    Step 2：将 LLM 发现的 Schema 与预定义 Schema 合并。

    合并规则：
    - 两者均有同名条目：保留描述更完整的版本，合并 possible_values
    - 仅预定义有：保留（标注 source: predefined）
    - 仅发现有：追加（标注 source: discovered）

    参数:
        discovered:  Step 1 归纳出的 PartialServiceSchema
        predefined:  预定义 Schema（如 resources/anyihua_sgd/schema.json 中的定义）

    返回:
        合并后的 PartialServiceSchema，description 来自 predefined
    """
    # ---------- 合并槽位 ----------
    merged_slots: Dict[str, PartialSlot] = {}

    # 先加入所有预定义槽位
    for slot in predefined.slots:
        merged_slots[slot.name] = slot

    # 合并发现的槽位
    for slot in discovered.slots:
        if slot.name in merged_slots:
            existing = merged_slots[slot.name]
            # 若发现的 possible_values 有新增，合并进去
            if slot.possible_values:
                existing_vals = set(existing.possible_values or [])
                new_vals = [v for v in slot.possible_values if v not in existing_vals]
                if new_vals:
                    combined = list(existing.possible_values or []) + new_vals
                    merged_slots[slot.name] = PartialSlot(
                        name=existing.name,
                        description=existing.description or slot.description,
                        is_categorical=existing.is_categorical if existing.is_categorical is not None else slot.is_categorical,
                        possible_values=combined,
                    )
        else:
            # 仅发现有：追加
            merged_slots[slot.name] = slot

    # ---------- 合并意图 ----------
    merged_intents: Dict[str, PartialIntent] = {}

    # 先加入所有预定义意图
    for intent in predefined.intents:
        merged_intents[intent.name] = intent

    # 合并发现的意图
    for intent in discovered.intents:
        if intent.name not in merged_intents:
            merged_intents[intent.name] = intent
        # 同名意图：保留预定义版本（更完整），可选合并 required_slots 等
        else:
            existing = merged_intents[intent.name]
            # 补全 required_slots（若预定义未定义）
            if not existing.required_slots and intent.required_slots:
                merged_intents[intent.name] = PartialIntent(
                    name=existing.name,
                    description=existing.description or intent.description,
                    is_transactional=existing.is_transactional if existing.is_transactional is not None else intent.is_transactional,
                    required_slots=intent.required_slots,
                    optional_slots=existing.optional_slots or intent.optional_slots,
                    result_slots=existing.result_slots or intent.result_slots,
                )

    description = predefined.description or discovered.description

    schema = PartialServiceSchema(
        service_name=predefined.service_name,
        description=description,
        slots=list(merged_slots.values()),
        intents=list(merged_intents.values()),
    )
    logger.info(
        f"[Step 2] 合并完成：{len(schema.slots)} 个槽位，{len(schema.intents)} 个意图"
        f"（预定义 {len(predefined.slots)}/{len(predefined.intents)}，"
        f"发现 {len(discovered.slots)}/{len(discovered.intents)}）"
    )
    return schema


# ---------------------------------------------------------------------------
# Step 3: LLM 驱动的 SGD 转换（含 langextract 对齐）
# ---------------------------------------------------------------------------


def _build_per_turn_extraction_prompt(
    dialogue_lines: List[Tuple[str, str]],
    schema: PartialServiceSchema,
) -> str:
    """
    构建逐轮信息提取 Prompt，输出严格 JSON 格式的逐轮标注。

    设计原则（安逸花外呼对话特殊处理）：
    - LLM 返回的意图名称必须来自 schema.intents
    - LLM 返回的槽位名称必须来自 schema.slots
    - 用户意图用 active_intent 字段，意图编码来自 schema
    - 槽位值是对话中出现的原始字符串（verbatim），以便后续 langextract 对齐

    参数:
        dialogue_lines: [(speaker, utterance), ...] 列表
        schema:         当前使用的 PartialServiceSchema

    返回:
        完整的 LLM Prompt 字符串
    """
    intent_names = [i.name for i in schema.intents]
    slot_names = [s.name for s in schema.slots]
    turn_count = len(dialogue_lines)

    # 格式化对话（带索引，方便 LLM 对应）
    dialogue_text = ""
    for idx, (speaker, utterance) in enumerate(dialogue_lines):
        prefix = _AGENT_PREFIX if speaker == "SYSTEM" else _USER_PREFIX
        dialogue_text += f"[{idx}] {prefix}{utterance}\n"

    # 构建 schema 描述
    intent_list = ", ".join(intent_names) if intent_names else "（无预定义意图）"
    slot_list = ", ".join(slot_names) if slot_names else "（无预定义槽位）"

    # 构建 API 方法映射说明
    api_mapping_lines = []
    for intent in schema.intents:
        api_method = _INTENT_TO_API.get(intent.name)
        if api_method:
            api_mapping_lines.append(f"  {intent.name} → {api_method}")
    api_mapping = "\n".join(api_mapping_lines) if api_mapping_lines else "  （无映射）"

    prompt = f"""你是安逸花外呼对话结构化标注助手。根据以下 Schema 定义，对每一轮对话进行精确标注。

业务背景：安逸花坐席主动致电老用户，目标是激活用户闲置的借款额度。
标准流程：核实身份 → 告知额度 → 解答疑问 → 引导借款 → 礼貌告别。

可用意图（valid_intents）：
{intent_list}

可用槽位（valid_slots）：
{slot_list}

意图 → API 方法映射（仅供 service_call_method 参考）：
{api_mapping}

对每一轮，你需要返回：
  SYSTEM 轮（坐席）：
    - service_call_method:  调用的 CRM API 方法名（仅核实身份/查询额度等轮次才填；无则填 null）
    - service_call_params:  方法调用参数 {{"slot_name": "在对话中出现的原始值文本"}}
  USER 轮（用户）：
    - active_intent:        用户当前意图（从 valid_intents 中选，用英文编码）
    - requested_slots:      用户疑问句中询问的槽位名称列表（无则填 []）
    - slot_values:          用户话语中提到或已确认的槽位值 {{"slot_name": "在对话中出现的原始值文本"}}

重要约束：
1. 所有槽位值必须是对话文本中真实出现过的原始字符串（如"六七八"、"高先生"、"二万一千九百"）。
2. 用户意图具有持续性：短回应（"嗯"、"对"、"好"）继承上一个明确的用户意图。
3. slot_values 跨轮累积：一旦确认的槽位值在后续轮次也要继续保留。
4. 只返回 JSON，不要有任何说明文字。

输出格式（严格 JSON，共 {turn_count} 轮，每轮必须对应）：
{{
  "turns": [
    {{
      "turn_index": 0,
      "speaker": "SYSTEM",
      "service_call_method": "verify_customer",
      "service_call_params": {{"name": "高先生", "phone_suffix": "六七八"}}
    }},
    {{
      "turn_index": 1,
      "speaker": "USER",
      "active_intent": "general_inquiry",
      "requested_slots": [],
      "slot_values": {{}}
    }}
  ]
}}

---
需要标注的完整对话（共 {turn_count} 轮）：

{dialogue_text}
请对所有 {turn_count} 轮逐一标注，返回严格 JSON。"""
    return prompt


def _parse_per_turn_response(
    llm_response: str,
    expected_turn_count: int,
) -> List[Dict[str, Any]]:
    """
    解析 LLM 返回的逐轮标注 JSON。

    失败时返回空列表（而不是抛出异常），供调用方降级处理。
    """
    text = llm_response.strip()

    # 尝试提取 JSON
    def _try_parse(s: str) -> Optional[Dict]:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return None

    data = _try_parse(text)
    if data is None:
        match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
        if match:
            data = _try_parse(match.group(1).strip())
    if data is None:
        match = re.search(r"\{[\s\S]*\}", text)
        if match:
            data = _try_parse(match.group())

    if not data or not isinstance(data, dict):
        return []

    turns = data.get("turns", [])
    if not isinstance(turns, list):
        return []

    return turns


def build_sgd_dialogue_step3(
    raw_dialogue: Dict[str, Any],
    schema: PartialServiceSchema,
    llm_client: Any,
) -> Dict[str, Any]:
    """
    Step 3（单条）：将原始安逸花对话转换为 SGD 格式，附 langextract 对齐信息。

    安逸花外呼对话特殊处理：
    - 对话文本保留"坐席："/"用户："前缀（用于 langextract WordAligner 对齐）
    - extraction_text 使用对话中实际出现的原始文本（verbatim），而非意图/方法编码
    - 意图编码放入 attributes["intent_name"]，服务调用方法放入 attributes["method_name"]
    - 所有 Extraction 先不做对齐，待全部收集完毕后由 langextract WordAligner
      一次性批量回溯对齐，填充 char_interval 和 alignment_status，实现溯源。

    参数:
        raw_dialogue: 原始对话条目（chat_test 或 SGD 格式）
        schema:       当前使用的 PartialServiceSchema（Step 2 合并后的）
        llm_client:   SimpleLLMClient 实例（从 .env 加载）

    返回:
        SGD 格式的 dialogue 字典，含 dialogue_id / services / turns / metadata
    """
    dialogue_id = raw_dialogue.get("session_id") or raw_dialogue.get("dialogue_id", "")
    lines = _parse_dialogue_lines(raw_dialogue)
    source_text = _dialogue_to_text(lines)

    if not lines:
        logger.warning(f"[Step 3] 空对话，跳过: {dialogue_id}")
        return {
            "dialogue_id": dialogue_id,
            "services": [schema.service_name],
            "turns": [],
            "metadata": {},
        }

    # ------------------------------------------------------------------
    # 调用 LLM 获取逐轮标注（用于填充 SGD turns 的 intent / slot_values）
    # ------------------------------------------------------------------
    prompt = _build_per_turn_extraction_prompt(lines, schema)
    try:
        _, llm_response = llm_client.generate(prompt)
        turn_annotations = _parse_per_turn_response(llm_response, len(lines))
    except Exception as exc:
        logger.warning(f"[Step 3] LLM 调用失败（{dialogue_id}）: {exc}，使用空标注")
        turn_annotations = []

    # 以 turn_index 为 key 建立查找表
    ann_by_index: Dict[int, Dict[str, Any]] = {
        ann.get("turn_index", i): ann
        for i, ann in enumerate(turn_annotations)
    }

    # ------------------------------------------------------------------
    # 逐轮构建 SGD turns，同时收集 langextract Extraction 对象（溯源）
    # 注意：Extraction 对象在此阶段尚未对齐（char_interval=None），
    #       全部收集完毕后由 WordAligner 批量回溯对齐（见下方）。
    # ------------------------------------------------------------------
    valid_intent_names = {intent.name for intent in schema.intents}
    valid_slot_names = {slot.name for slot in schema.slots}

    sgd_turns: List[Dict[str, Any]] = []
    # 收集未对齐的 Extraction 对象（langextract 数据类型）
    raw_extractions: List[Extraction] = []

    cumulative_slot_values: Dict[str, List[str]] = {}
    prev_user_intent = "general_inquiry"

    for turn_idx, (speaker, utterance) in enumerate(lines):
        ann = ann_by_index.get(turn_idx, {})

        if speaker == "USER":
            # 意图（从 LLM 标注取）：
            #   - 若 LLM 返回无效意图，降级到 prev_user_intent
            #   - 若 LLM 返回 "general_inquiry" 且已有更具体的意图上下文，
            #     则继承 prev_user_intent（避免短回应词重置意图）
            #   - 若 LLM 返回具体意图，则更新 prev_user_intent
            raw_intent = ann.get("active_intent", prev_user_intent)
            if raw_intent not in valid_intent_names:
                raw_intent = prev_user_intent
            if raw_intent == "general_inquiry" and prev_user_intent != "general_inquiry":
                # LLM 标注为通用意图，但已有更具体的历史意图，继承它
                active_intent = prev_user_intent
            else:
                active_intent = raw_intent
                if raw_intent != "general_inquiry":
                    prev_user_intent = raw_intent

            # 槽位值（过滤不在 schema 中的）
            raw_slots: Dict[str, str] = ann.get("slot_values", {}) or {}
            for slot_name, value in raw_slots.items():
                if slot_name in valid_slot_names and value:
                    cumulative_slot_values[slot_name] = [str(value)]

            requested_slots = [
                s for s in (ann.get("requested_slots") or [])
                if s in valid_slot_names
            ]

            # langextract Extraction（溯源）：
            #   extraction_text = 用户发言原话（verbatim，不是意图编码）
            #   char_interval / alignment_status 在批量对齐阶段由 WordAligner 填充
            if utterance and active_intent != "NONE":
                raw_extractions.append(Extraction(
                    extraction_class="intent",
                    extraction_text=utterance,
                    attributes={"intent_name": active_intent},
                    # char_interval & alignment_status 故意留空，由 _align_extractions() 批量填充
                ))

            # langextract Extraction（溯源）：
            #   extraction_text = 槽位的原始值文本（verbatim，不是槽位名）
            #   char_interval / alignment_status 在批量对齐阶段由 WordAligner 填充
            for slot_name, values in cumulative_slot_values.items():
                if values:
                    raw_extractions.append(Extraction(
                        extraction_class="slot_value",
                        extraction_text=values[0],
                        attributes={"slot_name": slot_name},
                        # char_interval & alignment_status 故意留空，由 _align_extractions() 批量填充
                    ))

            # 构建 USER frame
            user_actions = []
            for slot_name, values in cumulative_slot_values.items():
                user_actions.append({
                    "act": "INFORM",
                    "slot": slot_name,
                    "values": values,
                    "canonical_values": values,
                })

            frame: Dict[str, Any] = {
                "service": schema.service_name,
                "slots": [],
                "state": {
                    "active_intent": active_intent,
                    "requested_slots": requested_slots,
                    "slot_values": dict(cumulative_slot_values),
                },
                "actions": user_actions,
            }

        else:  # SYSTEM
            # 系统意图（service_call）
            method = ann.get("service_call_method") or None
            raw_params: Dict[str, str] = ann.get("service_call_params", {}) or {}
            # 过滤不在 schema slot 中的参数
            params = {k: v for k, v in raw_params.items() if k in valid_slot_names}

            # langextract Extraction（溯源）：
            #   extraction_text = 坐席发言原话（verbatim，不是方法名编码）
            #   char_interval / alignment_status 在批量对齐阶段由 WordAligner 填充
            if utterance and method:
                raw_extractions.append(Extraction(
                    extraction_class="system_intent",
                    extraction_text=utterance,
                    attributes={"method_name": method},
                    # char_interval & alignment_status 故意留空，由 _align_extractions() 批量填充
                ))

            # 系统动作
            system_actions: List[Dict[str, Any]] = []
            if method in ("verify_customer",):
                system_actions.append({
                    "act": "REQUEST",
                    "slot": "customer_name",
                    "values": [],
                    "canonical_values": [],
                })
            else:
                for slot_name, values in cumulative_slot_values.items():
                    system_actions.append({
                        "act": "INFORM",
                        "slot": slot_name,
                        "values": values,
                        "canonical_values": values,
                    })

            frame = {
                "service": schema.service_name,
                "slots": [],
                "actions": system_actions,
            }
            if method and params:
                frame["service_call"] = {"method": method, "parameters": params}
                # 用 CRM 提供的数据填充 service_results（若有）
                frame["service_results"] = [dict(params)]

        sgd_turns.append({
            "speaker": speaker,
            "utterance": utterance,
            "frames": [frame],
        })

    # ------------------------------------------------------------------
    # 批量回溯对齐（langextract WordAligner + UnicodeTokenizer）
    # 将所有 Extraction 的 extraction_text 定位到对话原文的字符区间，
    # 实现完整的溯源可追踪性（provenance traceability）。
    # ------------------------------------------------------------------
    aligned_extractions = _align_extractions(raw_extractions, source_text)

    # 构建 langextract ExampleData 对象（正式的溯源数据结构）
    example_data = ExampleData(text=source_text, extractions=aligned_extractions)

    # 对齐统计
    aligned_count = sum(
        1 for ex in aligned_extractions if ex.alignment_status is not None
    )
    total_extractions = len(aligned_extractions)

    metadata = {
        "user_info_raw": raw_dialogue.get("用户信息", ""),
        "reference_response": raw_dialogue.get("坐席回复", ""),
        "qc_label": raw_dialogue.get("人工校验", ""),
        # langextract 对齐统计（供质量审查）
        "langextract_stats": {
            "total_extractions": total_extractions,
            "aligned_count": aligned_count,
            "alignment_rate": round(aligned_count / total_extractions, 3) if total_extractions else 0.0,
        },
        # langextract ExampleData 序列化（可重新传入 lx.extract() 的 examples 参数）
        "langextract_example": _example_data_to_dict(example_data),
    }

    return {
        "dialogue_id": dialogue_id,
        "services": [schema.service_name],
        "turns": sgd_turns,
        "metadata": metadata,
    }




def _save_sgd_files(
    dialogues: List[Dict[str, Any]],
    schema: PartialServiceSchema,
    output_dir: Path,
    dialogues_per_file: int = _DIALOGUES_PER_FILE,
    save_alignment_data: bool = False,
) -> Dict[str, Any]:
    """
    将 SGD 数据保存到输出目录。

    输出结构：
        output_dir/
            schema.json                  # merged_schema 转换而来
            dialogues_001.json           # 对话数据（每文件 dialogues_per_file 条，纯 SGD 标准格式）
            dialogues_002.json           # ...
            extraction_summary.json      # 提取统计（含对齐率等）
            alignment_data_001.json      # 对齐元数据（仅当 save_alignment_data=True 时生成）
              └── 含 langextract_example（ExampleData 兼容格式）和 langextract_stats

    注意：对话数据文件（dialogues_*.json）不含 metadata 字段，
    以保持标准 SGD 格式兼容性。如需 langextract 对齐信息，
    请使用 ``save_alignment_data=True`` 生成 alignment_data_*.json。

    参数:
        dialogues:          SGD 对话列表（含 metadata）
        schema:             合并后的 PartialServiceSchema
        output_dir:         输出目录路径
        dialogues_per_file: 每文件最大对话数
        save_alignment_data: 是否额外保存包含 langextract 对齐数据的 alignment_data_*.json

    返回:
        汇总统计字典
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存 schema.json
    schema_path = output_dir / "schema.json"
    schema_path.write_text(
        json.dumps([schema.to_sgd_dict()], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[输出] schema.json 已保存: {schema_path}")

    # 保存 dialogues_*.json（metadata 字段不写入，保持 SGD 标准格式）
    # 如需 langextract 对齐数据，使用 save_alignment_data=True 生成 alignment_data_*.json
    n_files = 0
    for file_idx, start in enumerate(range(0, len(dialogues), dialogues_per_file), 1):
        chunk = dialogues[start : start + dialogues_per_file]
        # 写出时去掉 metadata（非标准 SGD 字段），保持与现有文件格式一致
        chunk_clean = [{k: v for k, v in d.items() if k != "metadata"} for d in chunk]
        file_path = output_dir / f"dialogues_{file_idx:03d}.json"
        file_path.write_text(
            json.dumps(chunk_clean, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        n_files += 1
        logger.info(f"[输出] {file_path.name} 已保存（{len(chunk)} 条对话）")

        # 可选：保存含 langextract 对齐信息的完整 metadata（供质量审查）
        if save_alignment_data:
            align_data = [
                {
                    "dialogue_id": d.get("dialogue_id"),
                    **d.get("metadata", {}),
                }
                for d in chunk
            ]
            align_file = output_dir / f"alignment_data_{file_idx:03d}.json"
            align_file.write_text(
                json.dumps(align_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[输出] {align_file.name} 已保存（含 langextract 对齐数据）")

    # 计算提取统计
    all_stats = [
        d.get("metadata", {}).get("langextract_stats", {}) for d in dialogues
    ]
    total_extractions = sum(s.get("total_extractions", 0) for s in all_stats)
    total_aligned = sum(s.get("aligned_count", 0) for s in all_stats)
    avg_alignment_rate = (
        round(total_aligned / total_extractions, 3) if total_extractions else 0.0
    )

    total_turns = sum(len(d.get("turns", [])) for d in dialogues)

    summary: Dict[str, Any] = {
        "pipeline": "anyihua_sgd_pipeline (3-step)",
        "dialogues": len(dialogues),
        "turns": total_turns,
        "services": [schema.service_name],
        "dialogue_files": n_files,
        "output_dir": str(output_dir),
        "schema_stats": {
            "intents": len(schema.intents),
            "slots": len(schema.slots),
        },
        "langextract_stats": {
            "total_extractions": total_extractions,
            "total_aligned": total_aligned,
            "alignment_rate": avg_alignment_rate,
        },
    }

    summary_path = output_dir / "extraction_summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"[输出] extraction_summary.json 已保存: {summary_path}")

    return summary


# ---------------------------------------------------------------------------
# 顶层管道入口
# ---------------------------------------------------------------------------


def run_pipeline(
    input_path: Path,
    predefined_schema_path: Path,
    output_dir: Path,
    llm_client: Any,
    sample_n: int = 50,
    limit: Optional[int] = None,
    skip_step1: bool = False,
    skip_step2: bool = False,
    discovered_schema_save_path: Optional[Path] = None,
    merged_schema_save_path: Optional[Path] = None,
    dialogues_per_file: int = _DIALOGUES_PER_FILE,
    save_alignment_data: bool = False,
) -> Dict[str, Any]:
    """
    运行完整的安逸花外呼数据 → SGD 知识库构建 3 步管道。

    管道步骤（对应 docs/analysis/dialogue-to-knowledge-pipeline.md）：
      Step 1: LLM Schema 发现（从抽样对话中归纳候选意图与槽位）
      Step 2: Schema 合并（预定义 + 发现合并）
      Step 3: LLM 全量 SGD 转换（每条对话 → SGD，含 langextract 对齐）

    所有 LLM 调用均通过 SimpleLLMClient（由 .env 配置加载），
    不直接使用 langextract 库的内置 Gemini 模型。

    安逸花外呼对话特殊处理（Step 3）：
      - extraction_text = 原话/原值（verbatim），意图/方法编码放入 attributes
      - 对齐基于 _align_text()（模拟 langextract WordAligner）

    参数:
        input_path:                  原始对话文件（chat_test 格式 JSON）
        predefined_schema_path:      预定义 Schema 文件路径
        output_dir:                  输出目录（SGD 文件写入此处）
        llm_client:                  SimpleLLMClient 实例
        sample_n:                    Step 1 抽样数量（默认 50）
        limit:                       仅转换前 N 条对话（默认全部）
        skip_step1:                  跳过 Step 1，直接使用 predefined schema 作为 discovered
        skip_step2:                  跳过 Step 2，仅使用 discovered schema（Step 1 结果）
        discovered_schema_save_path: Step 1 结果保存路径（可选）
        merged_schema_save_path:     Step 2 结果保存路径（可选）
        dialogues_per_file:          每个 dialogues_*.json 文件包含的对话数
        save_alignment_data:         是否额外保存 alignment_data_*.json（含 langextract 对齐数据，
                                     默认 False；设为 True 可供质量审查和调试）

    返回:
        汇总统计字典（与 extraction_summary.json 内容相同）
    """
    # ------------------------------------------------------------------
    # 加载原始数据
    # ------------------------------------------------------------------
    logger.info(f"[管道] 加载原始数据: {input_path}")
    raw_data: List[Dict[str, Any]] = json.loads(
        Path(input_path).read_text(encoding="utf-8")
    )
    if limit:
        raw_data = raw_data[:limit]
    logger.info(f"[管道] 共 {len(raw_data)} 条对话待处理")

    # ------------------------------------------------------------------
    # 加载预定义 Schema
    # ------------------------------------------------------------------
    from .extractor import schema_from_sgd_file

    logger.info(f"[管道] 加载预定义 Schema: {predefined_schema_path}")
    predefined_schema = schema_from_sgd_file(Path(predefined_schema_path))
    logger.info(
        f"[管道] 预定义 Schema：{len(predefined_schema.intents)} 个意图，"
        f"{len(predefined_schema.slots)} 个槽位"
    )

    # ------------------------------------------------------------------
    # Step 1: Schema 发现
    # ------------------------------------------------------------------
    if skip_step1:
        logger.info("[Step 1] 跳过，使用预定义 Schema 作为 discovered_schema")
        discovered_schema = predefined_schema
    else:
        logger.info(f"[Step 1] 开始 Schema 发现（抽样 {sample_n} 条）...")
        discovered_schema = discover_schema_step1(
            raw_data, llm_client, sample_n=sample_n,
            service_name=predefined_schema.service_name,
        )
        if discovered_schema_save_path:
            save_path = Path(discovered_schema_save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps([discovered_schema.to_sgd_dict()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[Step 1] 发现的 Schema 已保存: {save_path}")

    # ------------------------------------------------------------------
    # Step 2: Schema 合并
    # ------------------------------------------------------------------
    if skip_step2:
        logger.info("[Step 2] 跳过，使用 discovered_schema 直接进入 Step 3")
        merged_schema = discovered_schema
    else:
        logger.info("[Step 2] 开始 Schema 合并...")
        merged_schema = merge_schemas_step2(discovered_schema, predefined_schema)
        if merged_schema_save_path:
            save_path = Path(merged_schema_save_path)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            save_path.write_text(
                json.dumps([merged_schema.to_sgd_dict()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.info(f"[Step 2] 合并后的 Schema 已保存: {save_path}")

    # ------------------------------------------------------------------
    # Step 3: LLM 全量 SGD 转换
    # ------------------------------------------------------------------
    logger.info(f"[Step 3] 开始全量 SGD 转换（共 {len(raw_data)} 条）...")
    sgd_dialogues: List[Dict[str, Any]] = []

    for i, raw_dialogue in enumerate(raw_data, 1):
        dialogue_id = raw_dialogue.get("session_id") or raw_dialogue.get("dialogue_id", f"dlg_{i}")
        try:
            sgd = build_sgd_dialogue_step3(raw_dialogue, merged_schema, llm_client)
            sgd_dialogues.append(sgd)
            stats = sgd.get("metadata", {}).get("langextract_stats", {})
            if i % 10 == 0 or i == len(raw_data):
                logger.info(
                    f"[Step 3] 进度 {i}/{len(raw_data)} - "
                    f"最新对齐率: {stats.get('alignment_rate', 0.0):.1%}"
                )
        except Exception as exc:
            logger.error(f"[Step 3] 转换失败（{dialogue_id}）: {exc}", exc_info=True)

    # ------------------------------------------------------------------
    # 保存输出
    # ------------------------------------------------------------------
    logger.info(f"[管道] 保存 SGD 文件到: {output_dir}")
    summary = _save_sgd_files(
        sgd_dialogues,
        merged_schema,
        Path(output_dir),
        dialogues_per_file=dialogues_per_file,
        save_alignment_data=save_alignment_data,
    )

    logger.info(
        f"[管道] 完成！"
        f"共转换 {summary['dialogues']} 条对话，"
        f"总提取 {summary['langextract_stats']['total_extractions']} 条信息，"
        f"对齐率 {summary['langextract_stats']['alignment_rate']:.1%}"
    )
    return summary
