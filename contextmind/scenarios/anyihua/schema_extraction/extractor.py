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
        prompt_description="从安逸花外呼对话中提取槽位值和意图",
        examples=lx_examples,
        model_id="gemini-2.5-flash",
    )
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
                # 用户意图
                active_intent = state.get("active_intent")
                if active_intent and active_intent != "NONE":
                    attrs: Dict[str, str] = {}
                    if schema:
                        intent_def = schema.get_intent(active_intent)
                        if intent_def and intent_def.description:
                            attrs["description"] = intent_def.description
                    extractions.append(
                        {
                            "extraction_class": "intent",
                            "extraction_text": active_intent,
                            "attributes": attrs if attrs else None,
                        }
                    )

                # 用户槽位值
                for slot_name, values in state.get("slot_values", {}).items():
                    if not values:
                        continue
                    value_text = values[0] if isinstance(values, list) else str(values)
                    key = (slot_name, value_text)
                    if key in seen_slot_values:
                        continue
                    seen_slot_values.add(key)

                    slot_attrs: Dict[str, str] = {"slot_name": slot_name}
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
            if speaker == "SYSTEM":
                service_call = frame.get("service_call")
                if service_call:
                    method = service_call.get("method")
                    if method:
                        sys_attrs: Dict[str, str] = {}
                        if utterance:
                            # 将对应坐席发言文本附加到 attributes 供 langextract 参考
                            sys_attrs["utterance"] = utterance
                        if schema:
                            intent_def = schema.get_intent(method)
                            if intent_def and intent_def.description:
                                sys_attrs["description"] = intent_def.description
                        extractions.append(
                            {
                                "extraction_class": "system_intent",
                                "extraction_text": method,
                                "attributes": sys_attrs if sys_attrs else None,
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
                    "extraction_class": "slot_value" | "intent" | "system_intent",
                    "extraction_text": "<槽位值 | 意图名称>",
                    "attributes": {"slot_name": "...", "description": "...", ...} | None
                },
                ...
            ]
        }

    部分字段可能缺失：
    - 若对话中没有有效的槽位状态，``extractions`` 中对应条目为空；
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
