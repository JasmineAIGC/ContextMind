"""
安逸花外呼 · 任务三（Schema Extraction）· 对话转 langextract 样本工具

从已标注的 SGD 格式对话数据中提取 langextract ExampleData-兼容样本，
以及从原始安逸花对话数据中提取部分字段 Schema（PartialServiceSchema）。

主要函数:
    dialogue_to_langextract_example:
        将单条 SGD 格式对话（dialogues_001.json 条目）转换为
        langextract ExampleData-兼容字典，包含槽位值和意图标注。

    dialogues_to_langextract_examples:
        批量处理多条 SGD 对话，返回样本字典列表。

    schema_from_sgd_file:
        从 SGD schema.json 文件加载 PartialServiceSchema。

    extract_partial_schema_from_dialogue:
        从单条原始安逸花对话中归纳出 PartialServiceSchema，
        只保留对话中出现过的槽位和意图（字段可能缺失）。

langextract 提取结果格式说明::

    langextract 的 ``lx.extract()`` 返回 ``AnnotatedDocument`` 对象列表，
    每个 ``AnnotatedDocument`` 含有若干 ``Extraction`` 对象。

    ``Extraction`` 的关键字段：
        extraction_class (str):
            提取类别，如 "slot_value"、"intent"、"system_intent"。
        extraction_text (str):
            从原文中提取的**原始文本片段**。这是原文定位的核心——
            langextract 使用 WordAligner（difflib）将此字段值回溯定位
            到 source text 中的精确位置。
        char_interval (CharInterval | None):
            字符级位置区间，含 ``start_pos``（含）和 ``end_pos``（不含）。
            若对齐失败则为 None。
        alignment_status (AlignmentStatus | None):
            对齐质量：
            - ``match_exact``：完全精确匹配
            - ``match_lesser``：部分精确匹配（提取文本长于匹配段）
            - ``match_fuzzy``：模糊匹配（满足 fuzzy_alignment_threshold）
            - ``None``：对齐失败（extraction_text 未在源文中找到）
        attributes (dict | None):
            附加元信息，如意图编码名称、槽位名称、描述等。

    **重要设计约束**：``extraction_text`` 必须是源文中出现过的原始文本，
    才能被 WordAligner 成功对齐。因此：
    - 槽位值（slot_value）：``extraction_text`` = 槽位的原始值文本（如"六七八"），
      直接出现在对话中，对齐成功率高。
    - 用户意图（intent）：``extraction_text`` = 触发该意图的用户原话，
      ``attributes["intent_name"]`` = 意图编码（如 "verify_identity"）。
      若将意图编码作为 ``extraction_text``，该编码不在中文对话中出现，
      对齐必然失败（``alignment_status=None``），失去原文定位的意义。
    - 系统意图（system_intent）：``extraction_text`` = 坐席对应发言，
      ``attributes["method_name"]`` = 服务调用方法名。

    输出示例（槽位值，对齐成功）::

        Extraction(
            extraction_class="slot_value",
            extraction_text="六七八",          # 原文中存在，可对齐
            char_interval=CharInterval(start_pos=42, end_pos=45),
            alignment_status=AlignmentStatus.MATCH_EXACT,
            attributes={"slot_name": "phone_suffix"},
        )

    输出示例（用户意图，使用触发原话作为 extraction_text）::

        Extraction(
            extraction_class="intent",
            extraction_text="我的尾号是六七八",  # 原文中存在，可对齐
            char_interval=CharInterval(start_pos=20, end_pos=32),
            alignment_status=AlignmentStatus.MATCH_EXACT,
            attributes={"intent_name": "verify_identity"},
        )

典型使用::

    from contextmind.scenarios.anyihua.schema_extraction import (
        dialogue_to_langextract_example,
        dialogues_to_langextract_examples,
        schema_from_sgd_file,
    )

    # 加载 SGD 对话数据
    import json
    dialogues = json.loads(Path("resources/anyihua_sgd/dialogues_001.json").read_text())
    schema = schema_from_sgd_file(Path("resources/anyihua_sgd/schema.json"))

    # 转换为 langextract 样本
    examples = dialogues_to_langextract_examples(dialogues, schema)

    # 不安装 langextract 时直接使用字典
    for ex in examples:
        print(ex["text"][:80])

    # 安装 langextract 后转换为原生对象
    import langextract as lx
    lx_examples = [
        lx.data.ExampleData(
            text=ex["text"],
            extractions=[
                lx.data.Extraction(
                    extraction_class=e["extraction_class"],
                    extraction_text=e["extraction_text"],
                    attributes=e.get("attributes"),
                )
                for e in ex["extractions"]
            ],
        )
        for ex in examples
    ]
    result = lx.extract(
        text_or_documents="<新对话文本>",
        prompt_description="从安逸花外呼对话中提取槽位值和意图触发原话",
        examples=lx_examples,
        model_id="gemini-2.5-flash",
    )
    # result 为 AnnotatedDocument，访问提取结果：
    for extraction in result.extractions:
        print(extraction.extraction_class)   # "slot_value" / "intent" / "system_intent"
        print(extraction.extraction_text)    # 原文文本片段（已对齐）
        print(extraction.char_interval)      # CharInterval(start_pos=..., end_pos=...)
        print(extraction.alignment_status)   # AlignmentStatus.MATCH_EXACT 等
        print(extraction.attributes)         # {"slot_name": ...} 或 {"intent_name": ...} 等
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import PartialIntent, PartialServiceSchema, PartialSlot

# SGD 对话角色前缀映射（转换为可读文本时使用）
_SPEAKER_PREFIX: Dict[str, str] = {
    "SYSTEM": "坐席：",
    "USER": "用户：",
}


# --------------------------------------------------------------------------- #
# 内部辅助函数
# --------------------------------------------------------------------------- #


def _dialogue_to_text(dialogue: Dict[str, Any]) -> str:
    """
    将 SGD 格式对话（含 turns 列表）转换为纯文本字符串。

    每轮发言以"坐席："或"用户："为前缀，轮次之间以换行符分隔。
    """
    lines: List[str] = []
    for turn in dialogue.get("turns", []):
        speaker = turn.get("speaker", "")
        prefix = _SPEAKER_PREFIX.get(speaker, f"{speaker}：")
        lines.append(f"{prefix}{turn.get('utterance', '')}")
    return "\n".join(lines)


def _extract_annotations(
    dialogue: Dict[str, Any],
    schema: Optional[PartialServiceSchema] = None,
) -> List[Dict[str, Any]]:
    """
    从 SGD 格式对话的 frames 中提取槽位值和意图标注，
    返回 langextract Extraction-兼容字典列表。

    提取规则：
    - USER 帧的 ``state.slot_values`` → 槽位值（extraction_class="slot_value"）
    - USER 帧的 ``state.active_intent`` → 意图（extraction_class="intent"）
    - SYSTEM 帧的 ``service_call.method`` → 系统意图（extraction_class="system_intent"）

    **关键设计：extraction_text 必须是原文中出现过的文本片段**

    langextract 的 WordAligner 会把每个 ``extraction_text`` 回溯定位到
    source text（即 ExampleData.text / 待提取对话文本）中的字符位置，
    填充 ``char_interval`` 和 ``alignment_status``。若 ``extraction_text``
    在原文中不存在（如意图编码 "verify_identity" 不会出现在中文对话里），
    则 ``char_interval=None``、``alignment_status=None``，对齐失败，
    完全失去原文定位的意义。

    因此：
    - 意图（intent）：``extraction_text`` = 用户当轮发言原话（可在文本中定位），
      意图编码放入 ``attributes["intent_name"]``。
    - 系统意图（system_intent）：``extraction_text`` = 坐席当轮发言原话，
      方法名放入 ``attributes["method_name"]``。
    - 若当轮 utterance 为空，则跳过该意图/系统意图提取（无法提供有效原文证据）。
    - 槽位值（slot_value）：``extraction_text`` = 槽位的原始值文本，
      本身就是对话中出现的原始字符串，对齐成功率高，不需要改动。

    允许部分字段缺失：
    - 若某帧不含 ``state`` 则跳过用户槽位/意图提取
    - 若 ``service_call`` 不存在则跳过系统意图提取
    - 槽位 description 等 schema 元信息在 attributes 中附加（若 schema 传入）
    """
    extractions: List[Dict[str, Any]] = []
    seen_slot_values: set = set()  # 去重：同一槽位值只记录一次

    for turn in dialogue.get("turns", []):
        speaker = turn.get("speaker", "")
        utterance = turn.get("utterance", "")

        for frame in turn.get("frames", []):
            state = frame.get("state")

            if speaker == "USER" and state:
                # 用户意图：extraction_text = 用户原话（原文中存在，可对齐）
                # 意图编码不出现在对话文本中，放入 attributes["intent_name"]
                active_intent = state.get("active_intent")
                if active_intent and active_intent != "NONE" and utterance:
                    attrs: Dict[str, Any] = {"intent_name": active_intent}
                    if schema:
                        intent_def = schema.get_intent(active_intent)
                        if intent_def and intent_def.description:
                            attrs["description"] = intent_def.description
                    extractions.append(
                        {
                            "extraction_class": "intent",
                            "extraction_text": utterance,
                            "attributes": attrs,
                        }
                    )

                # 用户槽位值：extraction_text = 槽位的原始值文本（直接出现在对话中）
                for slot_name, values in state.get("slot_values", {}).items():
                    if not values:
                        continue
                    value_text = values[0] if isinstance(values, list) else str(values)
                    key = (slot_name, value_text)
                    if key in seen_slot_values:
                        continue
                    seen_slot_values.add(key)

                    slot_attrs: Dict[str, Any] = {"slot_name": slot_name}
                    if schema:
                        slot_def = schema.get_slot(slot_name)
                        if slot_def:
                            if slot_def.description:
                                slot_attrs["description"] = slot_def.description
                            if slot_def.is_categorical is not None:
                                slot_attrs["is_categorical"] = str(
                                    slot_def.is_categorical
                                ).lower()
                    extractions.append(
                        {
                            "extraction_class": "slot_value",
                            "extraction_text": value_text,
                            "attributes": slot_attrs,
                        }
                    )

            # SYSTEM 帧：服务调用意图
            # extraction_text = 坐席发言原话（原文中存在，可对齐）
            # 方法名不出现在对话文本中，放入 attributes["method_name"]
            if speaker == "SYSTEM":
                service_call = frame.get("service_call")
                if service_call:
                    method = service_call.get("method")
                    if method and utterance:
                        sys_attrs: Dict[str, Any] = {"method_name": method}
                        if schema:
                            intent_def = schema.get_intent(method)
                            if intent_def and intent_def.description:
                                sys_attrs["description"] = intent_def.description
                        extractions.append(
                            {
                                "extraction_class": "system_intent",
                                "extraction_text": utterance,
                                "attributes": sys_attrs,
                            }
                        )

    return extractions


# --------------------------------------------------------------------------- #
# 公开 API
# --------------------------------------------------------------------------- #


def dialogue_to_langextract_example(
    dialogue: Dict[str, Any],
    schema: Optional[PartialServiceSchema] = None,
) -> Dict[str, Any]:
    """
    将单条 SGD 格式对话转换为 langextract ExampleData-兼容字典。

    返回字典结构::

        {
            "text": "<对话文本，坐席/用户前缀>",
            "extractions": [
                {
                    "extraction_class": "slot_value",
                    "extraction_text": "<槽位的原始值文本，直接出现在对话中>",
                    "attributes": {"slot_name": "...", "description": "...", ...}
                },
                {
                    "extraction_class": "intent",
                    "extraction_text": "<触发该意图的用户原话，直接出现在对话中>",
                    "attributes": {"intent_name": "<意图编码>", "description": "...", ...}
                },
                {
                    "extraction_class": "system_intent",
                    "extraction_text": "<坐席执行该意图时的发言，直接出现在对话中>",
                    "attributes": {"method_name": "<服务调用方法名>", "description": "..."}
                },
                ...
            ]
        }

    **extraction_text 与原文定位**：所有 ``extraction_text`` 均为对话文本中
    出现过的原始字符串，langextract 的 WordAligner 可将其精确定位到
    ``char_interval``（字符偏移区间）。这是保证原文对齐（source grounding）
    成功的前提条件。意图编码和方法名（不出现在中文对话文本中）统一放入
    ``attributes`` 而不作为 ``extraction_text``。

    部分字段可能缺失：
    - 若某轮 utterance 为空，则该轮的意图/系统意图提取被跳过；
    - 若对话中没有有效的槽位状态，``extractions`` 中槽位条目为空；
    - 若对话文本为空，返回的 ``text`` 为空字符串（不抛异常）。

    参数:
        dialogue: 单条 SGD 格式对话字典（含 "turns" 列表）
        schema:   可选的 PartialServiceSchema，用于在 attributes 中附加
                  槽位/意图的描述等元信息

    返回:
        langextract ExampleData-兼容字典
    """
    text = _dialogue_to_text(dialogue)
    extractions = _extract_annotations(dialogue, schema)
    return {"text": text, "extractions": extractions}


def dialogues_to_langextract_examples(
    dialogues: List[Dict[str, Any]],
    schema: Optional[PartialServiceSchema] = None,
) -> List[Dict[str, Any]]:
    """
    批量将 SGD 格式对话列表转换为 langextract ExampleData-兼容字典列表。

    空对话（无 turns 或 utterance 均为空）将被过滤掉。

    参数:
        dialogues: SGD 格式对话字典列表（如 dialogues_001.json 内容）
        schema:    可选的 PartialServiceSchema

    返回:
        langextract ExampleData-兼容字典列表
    """
    examples = []
    for dialogue in dialogues:
        example = dialogue_to_langextract_example(dialogue, schema)
        if example["text"].strip():
            examples.append(example)
    return examples


def schema_from_sgd_file(schema_path: Path) -> PartialServiceSchema:
    """
    从 SGD schema.json 文件加载第一个服务的 PartialServiceSchema。

    SGD schema.json 通常为服务列表（JSON 数组），取第一个服务条目。
    所有 schema 字段均允许缺失：is_categorical、possible_values 等
    若文件中不存在则对应字段为 None。

    参数:
        schema_path: SGD schema.json 文件路径

    返回:
        PartialServiceSchema 实例

    抛出:
        FileNotFoundError: 文件不存在时
        ValueError:        JSON 内容为空列表时
    """
    data = json.loads(schema_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        if not data:
            raise ValueError(f"Schema 文件为空列表: {schema_path}")
        data = data[0]
    return PartialServiceSchema.from_sgd_dict(data)


def extract_partial_schema_from_dialogue(
    dialogue: Dict[str, Any],
    service_name: str = "",
) -> PartialServiceSchema:
    """
    从单条原始安逸花对话（chat_test_100.json 或 SGD 格式）中
    归纳出 PartialServiceSchema。

    仅保留对话中实际出现过的槽位名称和意图名称，不包含描述等元信息。
    这是"允许部分字段缺失"设计的体现：若对话中槽位值/意图无法提取，
    对应的 PartialSlot / PartialIntent 将不出现在结果中。

    支持两种输入格式：
    1. SGD 格式（含 ``turns`` 列表及 ``frames`` 标注）：从 state/service_call 提取
    2. 原始安逸花格式（含 ``对话历史`` 列表）：仅提取发言文本，无槽位标注

    参数:
        dialogue:     对话字典
        service_name: 服务名称（可选；默认为空字符串）

    返回:
        PartialServiceSchema（部分字段可能缺失 / 为空）
    """
    seen_slots: Dict[str, PartialSlot] = {}
    seen_intents: Dict[str, PartialIntent] = {}

    if "turns" in dialogue:
        # SGD 格式
        for turn in dialogue["turns"]:
            for frame in turn.get("frames", []):
                state = frame.get("state")
                if state:
                    active_intent = state.get("active_intent")
                    if active_intent and active_intent not in seen_intents:
                        seen_intents[active_intent] = PartialIntent(name=active_intent)
                    for slot_name in state.get("slot_values", {}):
                        if slot_name not in seen_slots:
                            seen_slots[slot_name] = PartialSlot(name=slot_name)

                service_call = frame.get("service_call")
                if service_call:
                    method = service_call.get("method")
                    if method and method not in seen_intents:
                        seen_intents[method] = PartialIntent(name=method)
                    for param_name in service_call.get("parameters", {}):
                        if param_name not in seen_slots:
                            seen_slots[param_name] = PartialSlot(name=param_name)

    # 原始安逸花格式无槽位/意图标注，返回仅含 service_name 的最小 Schema
    if "turns" in dialogue:
        resolved_name = service_name or (dialogue.get("services") or [""])[0]
    else:
        resolved_name = service_name
    return PartialServiceSchema(
        service_name=resolved_name,
        slots=list(seen_slots.values()),
        intents=list(seen_intents.values()),
    )
