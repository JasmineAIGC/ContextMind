"""
安逸花外呼 · 任务三（Schema Extraction）· Schema 持久化与格式对比工具

提供三项核心功能：

1. save_schema_as_sgd(schema, path)
   将 PartialServiceSchema 以标准 SGD JSON 数组格式写入文件，
   使输出可直接用于 SGD 数据集工具链。

2. align_schema_with_sgd(induced, reference)
   将 LLM 归纳出的 Schema 与参考 SGD Schema 做字段级对齐分析：
   - 匹配的槽位 / 意图
   - 参考中有但归纳中缺失的槽位 / 意图
   - 归纳中有但参考中没有的槽位 / 意图
   - 字段级差异（description / is_categorical / possible_values 等）

3. format_comparison_report(schema, reference_sgd_schema)
   生成三方格式对比报告，分析归纳 Schema 与以下两种格式的异同：
   - SGD 数据集格式（Google SGD：Schema-Guided Dialogue）
   - langextract 格式（google/langextract ExampleData / Extraction）

典型使用::

    from contextmind.scenarios.anyihua.schema_extraction import (
        save_schema_as_sgd,
        align_schema_with_sgd,
        format_comparison_report,
        schema_from_sgd_file,
    )

    # 保存为 SGD 格式文件
    save_schema_as_sgd(induced_schema, Path("output/induced_schema.json"))

    # 与参考 SGD Schema 做字段对齐分析
    ref = schema_from_sgd_file(Path("resources/anyihua_sgd/schema.json"))
    alignment = align_schema_with_sgd(induced_schema, ref)
    print(alignment["summary"])

    # 三方格式对比报告
    report = format_comparison_report(induced_schema, ref)
    print(report["langextract_comparison"]["key_differences"])
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schema import PartialServiceSchema


# --------------------------------------------------------------------------- #
# 1. 保存为 SGD 格式文件
# --------------------------------------------------------------------------- #


def save_schema_as_sgd(
    schema: PartialServiceSchema,
    path: Path,
    *,
    indent: int = 2,
) -> None:
    """
    将 PartialServiceSchema 保存为标准 SGD JSON 数组格式文件。

    SGD 格式规范：
    - 顶层为 JSON 数组（即使只有一个服务）
    - 每个服务条目包含 service_name / description / slots / intents
    - slots[i].optional 在 SGD 原始格式中默认 False（未出现该字段）
    - intents[i].optional_slots 在 SGD 原始格式中为 dict（slot_name→default_value）
      本实现将 List[str] 转回 dict 格式（value 为空字符串）

    参数:
        schema: PartialServiceSchema 实例
        path:   目标文件路径（含文件名，父目录不存在时自动创建）
        indent: JSON 缩进量（默认 2）
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    sgd_dict = _to_sgd_array_entry(schema)
    output = json.dumps([sgd_dict], ensure_ascii=False, indent=indent)
    path.write_text(output, encoding="utf-8")


def _to_sgd_array_entry(schema: PartialServiceSchema) -> Dict[str, Any]:
    """
    将 PartialServiceSchema 转为 SGD JSON 数组元素格式（单个服务 dict）。

    与 schema.to_sgd_dict() 的区别：
    - intents 的 optional_slots 从 List[str] 转回 dict（SGD 标准格式）
    - 补充 SGD 所需字段（如 service_name 而非 name）
    """
    entry: Dict[str, Any] = {"service_name": schema.service_name}
    if schema.description is not None:
        entry["description"] = schema.description

    # slots
    slots_list = []
    for s in schema.slots:
        slot_dict: Dict[str, Any] = {"name": s.name}
        if s.description is not None:
            slot_dict["description"] = s.description
        # SGD 要求 is_categorical 和 possible_values 必须同时出现
        slot_dict["is_categorical"] = s.is_categorical if s.is_categorical is not None else False
        slot_dict["possible_values"] = s.possible_values if s.possible_values is not None else []
        slots_list.append(slot_dict)
    entry["slots"] = slots_list

    # intents
    intents_list = []
    for i in schema.intents:
        intent_dict: Dict[str, Any] = {"name": i.name}
        if i.description is not None:
            intent_dict["description"] = i.description
        intent_dict["is_transactional"] = i.is_transactional if i.is_transactional is not None else False
        intent_dict["required_slots"] = i.required_slots if i.required_slots is not None else []
        # SGD 标准格式：optional_slots 为 dict {slot_name: ""}
        if i.optional_slots is not None:
            intent_dict["optional_slots"] = {s: "" for s in i.optional_slots}
        else:
            intent_dict["optional_slots"] = {}
        intent_dict["result_slots"] = i.result_slots if i.result_slots is not None else []
        intents_list.append(intent_dict)
    entry["intents"] = intents_list

    return entry


# --------------------------------------------------------------------------- #
# 2. 与参考 SGD Schema 做字段对齐分析
# --------------------------------------------------------------------------- #


def align_schema_with_sgd(
    induced: PartialServiceSchema,
    reference: PartialServiceSchema,
) -> Dict[str, Any]:
    """
    将 LLM 归纳出的 Schema 与参考 SGD Schema 做字段级对齐分析。

    分析维度：
    - slot 匹配 / 缺失 / 新增
    - intent 匹配 / 缺失 / 新增
    - 匹配条目的字段差异（description / is_categorical / possible_values 等）

    参数:
        induced:   LLM 归纳出的 PartialServiceSchema
        reference: 参考 SGD PartialServiceSchema（如 resources/anyihua_sgd/schema.json）

    返回:
        {
            "summary":          <str 简要文字摘要>,
            "slot_alignment":   {
                "matched":          [{"name": ..., "field_diffs": {...}}],
                "missing_in_induced": [<slot_name>, ...],
                "extra_in_induced": [<slot_name>, ...],
            },
            "intent_alignment": {
                "matched":            [{"name": ..., "field_diffs": {...}}],
                "missing_in_induced": [<intent_name>, ...],
                "extra_in_induced":   [<intent_name>, ...],
            },
            "coverage_pct": {
                "slot_coverage":   <float 0~1>,
                "intent_coverage": <float 0~1>,
            }
        }
    """
    induced_slots = {s.name: s for s in induced.slots}
    ref_slots = {s.name: s for s in reference.slots}

    induced_intents = {i.name: i for i in induced.intents}
    ref_intents = {i.name: i for i in reference.intents}

    # ---- Slot 对齐 ----
    slot_matched: List[Dict[str, Any]] = []
    slot_missing: List[str] = []  # 参考有但归纳缺失
    slot_extra: List[str] = []   # 归纳有但参考没有

    for name, ref_slot in ref_slots.items():
        if name in induced_slots:
            ind_slot = induced_slots[name]
            diffs: Dict[str, Any] = {}
            if ind_slot.description != ref_slot.description:
                diffs["description"] = {
                    "induced": ind_slot.description,
                    "reference": ref_slot.description,
                }
            if ind_slot.is_categorical != ref_slot.is_categorical:
                diffs["is_categorical"] = {
                    "induced": ind_slot.is_categorical,
                    "reference": ref_slot.is_categorical,
                }
            if ind_slot.possible_values != ref_slot.possible_values:
                diffs["possible_values"] = {
                    "induced": ind_slot.possible_values,
                    "reference": ref_slot.possible_values,
                }
            slot_matched.append({"name": name, "field_diffs": diffs})
        else:
            slot_missing.append(name)

    for name in induced_slots:
        if name not in ref_slots:
            slot_extra.append(name)

    # ---- Intent 对齐 ----
    intent_matched: List[Dict[str, Any]] = []
    intent_missing: List[str] = []
    intent_extra: List[str] = []

    for name, ref_intent in ref_intents.items():
        if name in induced_intents:
            ind_intent = induced_intents[name]
            diffs = {}
            if ind_intent.description != ref_intent.description:
                diffs["description"] = {
                    "induced": ind_intent.description,
                    "reference": ref_intent.description,
                }
            if ind_intent.is_transactional != ref_intent.is_transactional:
                diffs["is_transactional"] = {
                    "induced": ind_intent.is_transactional,
                    "reference": ref_intent.is_transactional,
                }
            # required_slots 差异（集合对比）
            ind_req = set(ind_intent.required_slots or [])
            ref_req = set(ref_intent.required_slots or [])
            if ind_req != ref_req:
                diffs["required_slots"] = {
                    "induced": sorted(ind_req),
                    "reference": sorted(ref_req),
                    "missing": sorted(ref_req - ind_req),
                    "extra": sorted(ind_req - ref_req),
                }
            # optional_slots 差异
            ind_opt = set(ind_intent.optional_slots or [])
            ref_opt = set(ref_intent.optional_slots or [])
            if ind_opt != ref_opt:
                diffs["optional_slots"] = {
                    "induced": sorted(ind_opt),
                    "reference": sorted(ref_opt),
                    "missing": sorted(ref_opt - ind_opt),
                    "extra": sorted(ind_opt - ref_opt),
                }
            intent_matched.append({"name": name, "field_diffs": diffs})
        else:
            intent_missing.append(name)

    for name in induced_intents:
        if name not in ref_intents:
            intent_extra.append(name)

    # ---- Coverage ----
    slot_coverage = len(slot_matched) / len(ref_slots) if ref_slots else 1.0
    intent_coverage = len(intent_matched) / len(ref_intents) if ref_intents else 1.0

    # ---- Summary ----
    summary_lines = [
        f"=== Schema 对齐摘要 ===",
        f"槽位: {len(slot_matched)} 匹配 / {len(slot_missing)} 缺失 / {len(slot_extra)} 新增"
        f"（参考共 {len(ref_slots)} 个，覆盖率 {slot_coverage:.0%}）",
        f"意图: {len(intent_matched)} 匹配 / {len(intent_missing)} 缺失 / {len(intent_extra)} 新增"
        f"（参考共 {len(ref_intents)} 个，覆盖率 {intent_coverage:.0%}）",
    ]
    if slot_missing:
        summary_lines.append(f"缺失槽位: {slot_missing}")
    if slot_extra:
        summary_lines.append(f"新增槽位（参考中无）: {slot_extra}")
    if intent_missing:
        summary_lines.append(f"缺失意图: {intent_missing}")
    if intent_extra:
        summary_lines.append(f"新增意图（参考中无）: {intent_extra}")
    diffed_slots = [m["name"] for m in slot_matched if m["field_diffs"]]
    if diffed_slots:
        summary_lines.append(f"有字段差异的槽位: {diffed_slots}")
    diffed_intents = [m["name"] for m in intent_matched if m["field_diffs"]]
    if diffed_intents:
        summary_lines.append(f"有字段差异的意图: {diffed_intents}")

    return {
        "summary": "\n".join(summary_lines),
        "slot_alignment": {
            "matched": slot_matched,
            "missing_in_induced": slot_missing,
            "extra_in_induced": slot_extra,
        },
        "intent_alignment": {
            "matched": intent_matched,
            "missing_in_induced": intent_missing,
            "extra_in_induced": intent_extra,
        },
        "coverage_pct": {
            "slot_coverage": round(slot_coverage, 2),
            "intent_coverage": round(intent_coverage, 2),
        },
    }


# --------------------------------------------------------------------------- #
# 3. 三方格式对比报告
# --------------------------------------------------------------------------- #


def format_comparison_report(
    induced: PartialServiceSchema,
    reference_sgd: Optional[PartialServiceSchema] = None,
) -> Dict[str, Any]:
    """
    生成三方格式对比报告：

    比较以下三种格式的字段结构、用途和异同点：

    A. **ContextMind PartialServiceSchema（本项目格式）**
       - PartialSlot / PartialIntent / PartialServiceSchema 数据类
       - 允许字段缺失（部分字段为 None）
       - 序列化后与 SGD 格式基本兼容

    B. **SGD 数据集格式**（Google Schema-Guided Dialogue）
       - 与 A 高度相似，但：
         - 必须有 service_name / slots / intents
         - optional_slots 必须为 dict（非 list）
         - possible_values 存在时为 list（哪怕为空）
         - 不允许字段缺失（None）

    C. **langextract 格式**（google/langextract ExampleData / Extraction）
       - 完全不同的用途：用于定义"few-shot 提取示例"，不是服务定义
       - ExampleData.text: 原始文本（对话/文档）
       - ExampleData.extractions: Extraction 列表
         - extraction_class: 实体类型（"slot_value" / "intent" / "system_intent"）
         - extraction_text: 必须是 text 中的 verbatim substring（精确文本子串）
         - attributes: dict of str→str（槽位名称、描述等元信息）

    参数:
        induced:       LLM 归纳出的 PartialServiceSchema（用于示例展示）
        reference_sgd: 参考 SGD Schema（可选，用于对齐分析）

    返回:
        {
            "our_schema_format":    <PartialServiceSchema 字段说明>,
            "sgd_format":           <SGD 格式字段说明>,
            "langextract_format":   <langextract 格式字段说明>,
            "our_vs_sgd":           <字段对比表（相同 / 差异 / 缺失）>,
            "our_vs_langextract":   <字段对比表>,
            "langextract_example":  <由 induced schema 生成的 langextract 样本示例>,
            "sgd_alignment":        <若传入 reference_sgd 则包含对齐结果>,
        }
    """
    # ---- A: 本项目格式描述 ----
    our_format = {
        "container": "PartialServiceSchema (Python dataclass)",
        "top_level_fields": {
            "service_name": "str（必填）",
            "description": "Optional[str]（可选）",
            "slots": "List[PartialSlot]（可为空列表）",
            "intents": "List[PartialIntent]（可为空列表）",
        },
        "slot_fields": {
            "name": "str（必填）",
            "description": "Optional[str]",
            "is_categorical": "Optional[bool]",
            "possible_values": "Optional[List[str]]",
        },
        "intent_fields": {
            "name": "str（必填）",
            "description": "Optional[str]",
            "is_transactional": "Optional[bool]",
            "required_slots": "Optional[List[str]]",
            "optional_slots": "Optional[List[str]]（内部 list，序列化时转 dict）",
            "result_slots": "Optional[List[str]]",
        },
        "serialization": "to_sgd_dict() → 跳过 None 字段；to_json() → JSON 字符串",
        "file_format": "JSON 数组（[{...}]），与 SGD schema.json 兼容",
    }

    # ---- B: SGD 格式描述 ----
    sgd_format = {
        "source": "Google Research, Schema-Guided Dialogue Dataset",
        "url": "https://github.com/google-research-datasets/dstc8-schema-guided-dialogue",
        "container": "JSON 数组，每元素为一个服务定义",
        "top_level_fields": {
            "service_name": "str（必填）",
            "description": "str（必填，不可为 None）",
            "slots": "list of slot objects（必填）",
            "intents": "list of intent objects（必填）",
        },
        "slot_fields": {
            "name": "str（必填）",
            "description": "str（必填）",
            "is_categorical": "bool（必填）",
            "possible_values": "list of str（必填，非分类槽为 []）",
        },
        "intent_fields": {
            "name": "str（必填）",
            "description": "str（必填）",
            "is_transactional": "bool（必填）",
            "required_slots": "list of str（必填）",
            "optional_slots": "dict {slot_name: default_value}（注意：dict 非 list）",
            "result_slots": "list of str（必填）",
        },
        "key_constraints": [
            "所有字段必须存在，不允许 None",
            "optional_slots 必须为 dict 格式（{slot: ''}），不能为 list",
            "possible_values 即使为空也必须是 []",
            "顶层必须是 JSON 数组，即使只有一个服务",
        ],
    }

    # ---- C: langextract 格式描述 ----
    langextract_format = {
        "source": "google/langextract Python library",
        "url": "https://github.com/google/langextract",
        "purpose": "定义 few-shot 提取示例（不是服务定义 schema）",
        "container": "ExampleData 对象列表，传给 lx.extract(examples=...)",
        "ExampleData_fields": {
            "text": "str — 原始文本（对话或文档），必须是实际文本内容",
            "extractions": "List[Extraction] — 从 text 中提取的实体列表",
        },
        "Extraction_fields": {
            "extraction_class": "str — 实体类别（如 'slot_value' / 'intent' / 'character'）",
            "extraction_text": "str — 必须是 text 中的 verbatim substring（精确子串）",
            "attributes": "Optional[Dict[str, str]] — 附加属性（key/value 均为 str）",
        },
        "key_constraints": [
            "extraction_text 必须是 text 中的精确子串（verbatim substring）",
            "extractions 按在 text 中的出现顺序排列",
            "attributes 的 value 必须是 str（不能是 int/bool/list）",
            "ExampleData 驱动 LLM 行为，不用于定义业务 schema",
            "不包含 slots/intents 层级结构，所有提取项平铺在 extractions 列表中",
        ],
    }

    # ---- 对比：本项目 vs SGD ----
    our_vs_sgd = {
        "相同点": [
            "顶层字段名完全一致：service_name / description / slots / intents",
            "Slot 字段名完全一致：name / description / is_categorical / possible_values",
            "Intent 字段名完全一致：name / description / is_transactional / required_slots / result_slots",
            "文件格式相同：JSON 数组",
        ],
        "差异点": [
            {
                "字段": "optional_slots",
                "本项目格式": "List[str]（Python 内部表示，序列化时转 dict）",
                "SGD 格式": "dict {slot_name: default_value}（如 {'phone_suffix': ''}）",
                "影响": "save_schema_as_sgd() 会自动将 list 转回 dict",
            },
            {
                "字段": "字段必填性",
                "本项目格式": "description / is_categorical / possible_values 可以为 None（允许部分缺失）",
                "SGD 格式": "所有字段必须存在且非 None",
                "影响": "save_schema_as_sgd() 会为 None 字段填写默认值（False / []）",
            },
        ],
        "兼容性结论": (
            "本项目格式是 SGD 格式的超集（允许字段缺失），"
            "通过 save_schema_as_sgd() 可完全转换为标准 SGD 格式。"
            "从 SGD 文件加载（schema_from_sgd_file）同样无损。"
        ),
    }

    # ---- 对比：本项目 vs langextract ----
    our_vs_langextract = {
        "用途差异": {
            "本项目 PartialServiceSchema": "定义业务服务的数据结构（槽位、意图、约束）— 用于推理时约束信息提取",
            "langextract ExampleData": "提供 few-shot 示例以指导 LLM 的提取行为 — 包含真实文本和标注",
        },
        "结构差异": {
            "本项目": "层次化结构（service → slots / intents → fields）",
            "langextract": "平铺结构（text + extractions 列表）",
        },
        "字段对应关系": [
            {"本项目字段": "slot.name", "langextract 字段": "Extraction.attributes['slot_name']"},
            {"本项目字段": "slot.description", "langextract 字段": "Extraction.attributes['description']"},
            {"本项目字段": "slot.is_categorical", "langextract 字段": "Extraction.attributes['is_categorical']（str）"},
            {"本项目字段": "intent.name", "langextract 字段": "Extraction.extraction_text（当 class='intent'）"},
            {"本项目字段": "slot_value（运行时）", "langextract 字段": "Extraction.extraction_text（当 class='slot_value'）"},
        ],
        "关键差异": [
            "langextract 中的 extraction_text 必须是原文中的 verbatim substring（精确子串），"
            "而本项目 schema 中的 slot/intent name 是标准化英文标识符",
            "langextract attributes 的 value 必须全为 str，"
            "而本项目 schema 中 is_categorical 是 bool、possible_values 是 List[str]",
            "langextract 没有 required_slots / optional_slots / result_slots 的概念",
            "本项目 schema 可通过 to_langextract_schema_dict() 转换为 langextract ExampleData 字典",
        ],
        "互操作方式": (
            "PartialServiceSchema.to_langextract_schema_dict() 将 schema 本身序列化为一个 "
            "langextract ExampleData 兼容字典（text=schema JSON，extractions=slot/intent列表）；"
            "extractor.py 中的 dialogue_to_langextract_example() 将标注对话转为 langextract 样本。"
        ),
    }

    # ---- langextract 示例（由 induced schema 生成）----
    langextract_example = induced.to_langextract_schema_dict()
    # 只展示前 3 个 extractions 以减少输出体积
    preview = {
        "text_length": len(langextract_example["text"]),
        "extractions_count": len(langextract_example["extractions"]),
        "extractions_preview": langextract_example["extractions"][:3],
    }

    result: Dict[str, Any] = {
        "our_schema_format": our_format,
        "sgd_format": sgd_format,
        "langextract_format": langextract_format,
        "our_vs_sgd": our_vs_sgd,
        "our_vs_langextract": our_vs_langextract,
        "langextract_example_preview": preview,
    }

    if reference_sgd is not None:
        result["sgd_alignment"] = align_schema_with_sgd(induced, reference_sgd)

    return result
