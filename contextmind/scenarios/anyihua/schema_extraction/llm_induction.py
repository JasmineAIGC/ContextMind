"""
安逸花外呼 · 任务三（Schema Extraction）· LLM 驱动的 Schema 归纳与信息提取

提供两个基于 LLM 的核心能力：

1. Schema 归纳（induce_schema_with_llm）：
   从原始（未标注）安逸花外呼对话中，通过 LLM 自动归纳出
   完善、丰富、准确的 PartialServiceSchema（包含槽位描述、分类标志、
   可选值、意图描述、所需/可选槽位等元信息）。

2. Schema 引导的信息提取（extract_dialogue_info）：
   给定一个预定义的 PartialServiceSchema 和一段新的对话文本，
   通过 LLM 按照 Schema 定义提取精准、细粒度的结构化 JSON。

设计原则：
   · Schema 归纳基于多条对话样本，归纳槽位和意图的完整元信息
   · 信息提取严格遵循预定义 Schema，输出格式化 JSON
   · 两个函数均支持 SimpleLLMClient，对外暴露简洁接口
   · 错误处理健壮：LLM 输出解析失败时返回部分结果而不是抛出异常

典型使用::

    from contextmind.scenarios.anyihua.schema_extraction import (
        induce_schema_with_llm,
        extract_dialogue_info,
    )
    from contextmind.infra.llm_client import SimpleLLMClient

    # 初始化 LLM 客户端
    llm = SimpleLLMClient()

    # 1. 从原始对话归纳 Schema
    raw_dialogues = [...]  # chat_test_100.json 中的对话条目列表
    schema = induce_schema_with_llm(raw_dialogues, llm, service_name="AnYiHua_1")
    print(schema.to_json())

    # 2. 基于 Schema 提取结构化信息
    dialogue_text = "坐席：请问您是高先生吗？\\n用户：是的。"
    result = extract_dialogue_info(dialogue_text, schema, llm)
    # result = {"active_intents": [...], "slot_values": {"customer_name": "高先生", ...}}
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .schema import PartialIntent, PartialServiceSchema, PartialSlot

# --------------------------------------------------------------------------- #
# 类型别名
# --------------------------------------------------------------------------- #

_LLMClient = Any  # SimpleLLMClient（避免循环导入）

# --------------------------------------------------------------------------- #
# 内部辅助
# --------------------------------------------------------------------------- #

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


def _dialogue_to_text(dialogue: Dict[str, Any]) -> str:
    """
    将对话条目转换为纯文本字符串。

    支持两种输入格式：
    - chat_test 格式：含 ``对话历史`` 列表（字符串形式，已含角色前缀）
    - SGD 格式：含 ``turns`` 列表

    返回：按发言顺序拼接的文本，角色前缀保留。
    """
    # chat_test 格式
    if "对话历史" in dialogue:
        lines = dialogue["对话历史"]
        if isinstance(lines, list):
            return "\n".join(str(line) for line in lines)
        return str(lines)

    # SGD 格式
    if "turns" in dialogue:
        _SPEAKER_PREFIX = {"SYSTEM": _AGENT_PREFIX, "USER": _USER_PREFIX}
        lines: List[str] = []
        for turn in dialogue["turns"]:
            speaker = turn.get("speaker", "")
            prefix = _SPEAKER_PREFIX.get(speaker, f"{speaker}：")
            lines.append(f"{prefix}{turn.get('utterance', '')}")
        return "\n".join(lines)

    return ""


def _extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    从 LLM 输出文本中提取 JSON 对象。

    依次尝试：
    1. 直接解析整个文本
    2. 提取 ```json … ``` 代码块
    3. 正则查找最外层的 { … }
    4. 返回 None（解析失败）
    """
    text = text.strip()

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. 代码块
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 3. 最外层大括号
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def _build_schema_induction_prompt(dialogue_texts: List[str], service_name: str) -> str:
    """
    构建 Schema 归纳 Prompt。

    给 LLM 若干条对话样本，要求 LLM 从中归纳出完整的 Schema JSON。
    """
    samples_text = ""
    for idx, text in enumerate(dialogue_texts, 1):
        # 截断过长对话，避免 prompt 超出上下文
        truncated = text[:1200] if len(text) > 1200 else text
        samples_text += f"\n\n【对话样本 {idx}】\n{truncated}"

    prompt = f"""你是一名专业的对话数据 Schema 分析专家。

以下是若干条安逸花外呼业务对话的样本（坐席代表金融公司主动联系客户，
目的是激活用户闲置的借款额度）：
{samples_text}

请仔细阅读以上对话，归纳出一个完整、丰富、准确的服务 Schema，描述对话中涉及的：
- **槽位（slots）**：对话中收集或提及的信息字段（如客户姓名、可提现额度、手机尾号等）
- **意图（intents）**：坐席执行的对话动作（如核实身份、告知额度、计算还款等）

**要求：**
1. 槽位（slots）必须包含：
   - name: 英文下划线命名（如 customer_name）
   - description: 简洁的中文描述（15字以内）
   - is_categorical: 是否为固定枚举值（true/false）
   - possible_values: 仅当 is_categorical=true 时列出枚举值，否则为 []

2. 意图（intents）必须包含：
   - name: 英文下划线命名（如 verify_identity）
   - description: 简洁的中文描述意图目的（20字以内）
   - is_transactional: 是否需要外部操作/API调用（true/false）
   - required_slots: 此意图必须填写的槽位名称列表
   - optional_slots: 此意图可选填写的槽位名称列表
   - result_slots: 此意图执行后可能新增/更新的槽位名称列表

3. 尽量覆盖所有在对话中出现的信息字段和动作，不遗漏
4. 槽位和意图命名保持英文，描述用中文

**严格按照以下 JSON 格式输出（不要输出任何解释文字）：**

{{
  "service_name": "{service_name}",
  "description": "<服务的一句话描述>",
  "slots": [
    {{
      "name": "<英文名>",
      "description": "<中文描述>",
      "is_categorical": false,
      "possible_values": []
    }}
  ],
  "intents": [
    {{
      "name": "<英文名>",
      "description": "<中文描述>",
      "is_transactional": false,
      "required_slots": [],
      "optional_slots": [],
      "result_slots": []
    }}
  ]
}}"""
    return prompt


def _build_merge_schema_prompt(
    partial_schemas: List[Dict[str, Any]],
    service_name: str,
) -> str:
    """
    构建 Schema 合并 Prompt。

    将多批次归纳出的部分 Schema 合并为最终完整 Schema。
    """
    schemas_text = json.dumps(partial_schemas, ensure_ascii=False, indent=2)
    # 截断超长内容
    if len(schemas_text) > 6000:
        schemas_text = schemas_text[:6000] + "\n... (已截断)"

    prompt = f"""你是一名专业的对话数据 Schema 整合专家。

以下是从多批次安逸花外呼对话中分别归纳出的若干个部分 Schema：

{schemas_text}

请将这些部分 Schema 合并为一个完整、去重、完善的最终 Schema，要求：
1. 合并同名槽位（相同 name），保留最详细的描述和元信息
2. 合并同名意图（相同 name），取所有批次中 required_slots / optional_slots / result_slots 的并集
3. 补充任何明显缺失但在安逸花外呼业务中应当存在的槽位或意图
4. 确保每个槽位的 description、is_categorical、possible_values 都完整准确
5. 确保每个意图的 description、is_transactional、required_slots 都完整准确
6. 删除重复或语义相同的条目
7. 按重要性排序：核心槽位/意图放在前面

**严格按照以下 JSON 格式输出（不要输出任何解释文字）：**

{{
  "service_name": "{service_name}",
  "description": "<服务的一句话描述>",
  "slots": [
    {{
      "name": "<英文名>",
      "description": "<中文描述>",
      "is_categorical": false,
      "possible_values": []
    }}
  ],
  "intents": [
    {{
      "name": "<英文名>",
      "description": "<中文描述>",
      "is_transactional": false,
      "required_slots": [],
      "optional_slots": [],
      "result_slots": []
    }}
  ]
}}"""
    return prompt


def _build_extraction_prompt(
    dialogue_text: str,
    schema: PartialServiceSchema,
) -> str:
    """
    构建 Schema 引导的信息提取 Prompt。

    给 LLM 提供 Schema 定义和对话文本，要求按 Schema 提取结构化 JSON。
    """
    schema_json = schema.to_json()
    # 截断过长的 Schema（通常不会超限，保险起见）
    if len(schema_json) > 3000:
        schema_json = schema_json[:3000] + "\n... (已截断)"

    # 截断过长的对话
    truncated_dialogue = dialogue_text[:4000] if len(dialogue_text) > 4000 else dialogue_text

    # 收集槽位名称和意图名称，便于 LLM 参考
    slot_names = [s.name for s in schema.slots]
    intent_names = [i.name for i in schema.intents]

    prompt = f"""你是一名精准的对话信息提取专家，专门处理安逸花外呼业务对话。

**预定义 Schema（提取的依据）：**
```json
{schema_json}
```

**可提取的槽位名称：** {json.dumps(slot_names, ensure_ascii=False)}
**可识别的意图名称：** {json.dumps(intent_names, ensure_ascii=False)}

**待提取的对话：**
```
{truncated_dialogue}
```

**任务：** 根据上方 Schema 定义，从对话中提取所有出现的信息。

**提取规则：**
1. slot_values：只提取对话中明确出现的槽位值，未出现的槽位不包含在结果中
   - 值必须直接来自对话内容，不可推断或捏造
   - 数值类槽位直接填写阿拉伯数字或中文原文均可
   - 分类型槽位（is_categorical=true）的值必须来自 possible_values 列表
2. active_intents：列出对话中坐席实际执行的所有意图，按出现顺序排列
   - 只包含在对话中有明确体现的意图，不可猜测
3. 提取要求精准、细粒度，尽可能完整地捕获对话中的所有关键信息

**严格按照以下 JSON 格式输出（不要输出任何解释文字）：**

{{
  "active_intents": ["<意图名1>", "<意图名2>"],
  "slot_values": {{
    "<槽位名>": "<槽位值>",
    "<槽位名>": "<槽位值>"
  }}
}}"""
    return prompt


def _parse_schema_from_llm_response(
    response_text: str,
    service_name: str,
) -> Optional[PartialServiceSchema]:
    """
    从 LLM 输出中解析 PartialServiceSchema。

    解析失败时返回 None（由调用方处理降级逻辑）。
    """
    data = _extract_json_from_text(response_text)
    if not data or not isinstance(data, dict):
        return None

    # 兼容 LLM 可能返回的键名变体
    resolved_name = (
        data.get("service_name")
        or data.get("name")
        or service_name
    )

    try:
        slots: List[PartialSlot] = []
        for s in data.get("slots", []):
            if not isinstance(s, dict) or not s.get("name"):
                continue
            raw_vals = s.get("possible_values")
            # Accept both [] and non-empty lists; only reject non-list types
            possible_values: Optional[List[str]] = (
                raw_vals if isinstance(raw_vals, list) else None
            )
            slots.append(
                PartialSlot(
                    name=s["name"],
                    description=s.get("description") or None,
                    is_categorical=s.get("is_categorical") or None,
                    possible_values=possible_values,
                )
            )

        intents: List[PartialIntent] = []
        for i in data.get("intents", []):
            if not isinstance(i, dict) or not i.get("name"):
                continue
            # optional_slots 在 SGD 中可能是 dict 或 list；空 list 也是合法值
            raw_opt = i.get("optional_slots")
            if isinstance(raw_opt, dict):
                optional_slots: Optional[List[str]] = list(raw_opt.keys())
            elif isinstance(raw_opt, list):
                optional_slots = raw_opt
            else:
                optional_slots = None

            req = i.get("required_slots")
            res = i.get("result_slots")
            intents.append(
                PartialIntent(
                    name=i["name"],
                    description=i.get("description") or None,
                    is_transactional=i.get("is_transactional") or None,
                    required_slots=req if isinstance(req, list) else None,
                    optional_slots=optional_slots,
                    result_slots=res if isinstance(res, list) else None,
                )
            )

        return PartialServiceSchema(
            service_name=resolved_name,
            description=data.get("description") or None,
            slots=slots,
            intents=intents,
        )
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# 公开 API
# --------------------------------------------------------------------------- #


def induce_schema_with_llm(
    dialogues: List[Dict[str, Any]],
    llm_client: _LLMClient,
    service_name: str = "AnYiHua_1",
    batch_size: int = 5,
) -> PartialServiceSchema:
    """
    使用 LLM 从原始（未标注）安逸花外呼对话中归纳完整的 Schema。

    算法：
    1. 将对话分批（每批 batch_size 条），逐批提示 LLM 归纳部分 Schema
    2. 收集各批次归纳的部分 Schema（JSON）
    3. 若批次 > 1，再次调用 LLM 合并所有部分 Schema 为最终完整 Schema
    4. 返回 PartialServiceSchema 实例

    支持输入格式：
    - chat_test 格式（含 ``对话历史`` 列表）
    - SGD 格式（含 ``turns`` 列表）

    参数:
        dialogues:    对话条目列表（每条为字典）
        llm_client:   已初始化的 SimpleLLMClient 实例
        service_name: 服务名称（默认 "AnYiHua_1"）
        batch_size:   每批处理的对话数量（默认 5）

    返回:
        PartialServiceSchema 实例（包含完整 slots / intents 元信息）

    抛出:
        ValueError: LLM 返回结果无法解析为有效 Schema 时
    """
    if not dialogues:
        return PartialServiceSchema(service_name=service_name)

    # ------------------------------------------------------------------ #
    # Step 1: 分批归纳
    # ------------------------------------------------------------------ #
    partial_schema_dicts: List[Dict[str, Any]] = []

    for batch_start in range(0, len(dialogues), batch_size):
        batch = dialogues[batch_start : batch_start + batch_size]
        texts = [_dialogue_to_text(d) for d in batch]
        texts = [t for t in texts if t.strip()]  # 过滤空文本
        if not texts:
            continue

        prompt = _build_schema_induction_prompt(texts, service_name)
        _, response = llm_client.generate(prompt)

        schema_data = _extract_json_from_text(response)
        if schema_data and isinstance(schema_data, dict):
            partial_schema_dicts.append(schema_data)

    if not partial_schema_dicts:
        raise ValueError(
            "LLM 未能从提供的对话中归纳出任何有效 Schema。"
            "请检查对话内容和 LLM 连接。"
        )

    # ------------------------------------------------------------------ #
    # Step 2: 若只有一个批次，直接解析返回
    # ------------------------------------------------------------------ #
    if len(partial_schema_dicts) == 1:
        schema = _parse_schema_from_llm_response(
            json.dumps(partial_schema_dicts[0], ensure_ascii=False),
            service_name,
        )
        if schema is not None:
            return schema
        raise ValueError(
            f"LLM 归纳的 Schema 格式无效，无法解析。原始输出: "
            f"{json.dumps(partial_schema_dicts[0], ensure_ascii=False)[:500]}"
        )

    # ------------------------------------------------------------------ #
    # Step 3: 多批次合并
    # ------------------------------------------------------------------ #
    merge_prompt = _build_merge_schema_prompt(partial_schema_dicts, service_name)
    _, merge_response = llm_client.generate(merge_prompt)

    schema = _parse_schema_from_llm_response(merge_response, service_name)
    if schema is not None:
        return schema

    # 合并失败，降级：直接用第一个批次的结果
    schema = _parse_schema_from_llm_response(
        json.dumps(partial_schema_dicts[0], ensure_ascii=False),
        service_name,
    )
    if schema is not None:
        return schema

    raise ValueError(
        "LLM 归纳和合并 Schema 均失败，无法生成有效 Schema。"
        "请检查 LLM 连接和对话质量。"
    )


def extract_dialogue_info(
    dialogue_text_or_dict: Any,
    schema: PartialServiceSchema,
    llm_client: _LLMClient,
) -> Dict[str, Any]:
    """
    基于预定义 Schema，使用 LLM 从对话中提取精准的结构化信息。

    该函数是"schema 引导的细粒度信息提取"的核心实现：
    提供 Schema 作为约束，LLM 只能从 Schema 定义的槽位和意图中提取，
    确保输出结构化、精准、可直接用于下游任务。

    支持输入格式：
    - 字符串（已拼接的对话文本）
    - chat_test 格式字典（含 ``对话历史``）
    - SGD 格式字典（含 ``turns``）

    参数:
        dialogue_text_or_dict: 对话文本（字符串）或对话条目字典
        schema:                预定义的 PartialServiceSchema
        llm_client:            已初始化的 SimpleLLMClient 实例

    返回:
        结构化提取结果字典::

            {
                "active_intents": ["verify_identity", "explain_credit_limit"],
                "slot_values": {
                    "customer_name": "高先生",
                    "phone_suffix": "六七八",
                    "available_credit": "七千零四十一"
                }
            }

        若 LLM 输出无法解析，返回::

            {
                "active_intents": [],
                "slot_values": {},
                "parse_error": "<错误信息>"
            }
    """
    # 统一转为文本
    if isinstance(dialogue_text_or_dict, str):
        dialogue_text = dialogue_text_or_dict
    elif isinstance(dialogue_text_or_dict, dict):
        dialogue_text = _dialogue_to_text(dialogue_text_or_dict)
    else:
        dialogue_text = str(dialogue_text_or_dict)

    if not dialogue_text.strip():
        return {"active_intents": [], "slot_values": {}}

    prompt = _build_extraction_prompt(dialogue_text, schema)
    _, response = llm_client.generate(prompt)

    data = _extract_json_from_text(response)
    if not data or not isinstance(data, dict):
        return {
            "active_intents": [],
            "slot_values": {},
            "parse_error": f"LLM 输出无法解析为 JSON（前 200 字符）: {response[:200]}",
        }

    # 规范化输出结构
    active_intents = data.get("active_intents", [])
    if not isinstance(active_intents, list):
        active_intents = []

    slot_values = data.get("slot_values", {})
    if not isinstance(slot_values, dict):
        slot_values = {}

    # 过滤掉不在 Schema 中的意图（防止 LLM 幻觉）
    valid_intent_names = {i.name for i in schema.intents}
    active_intents = [
        intent for intent in active_intents if intent in valid_intent_names
    ]

    # 过滤掉不在 Schema 中的槽位（防止 LLM 幻觉）
    valid_slot_names = {s.name for s in schema.slots}
    slot_values = {
        k: v for k, v in slot_values.items() if k in valid_slot_names
    }

    return {
        "active_intents": active_intents,
        "slot_values": slot_values,
    }
