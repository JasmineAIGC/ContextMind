"""
对话格式归一化器

将任意输入格式统一转换为内部标准格式（dict，含 ``对话历史`` 字段），
使 KnowledgeBaseBuilder 能够将任何来源的对话送入知识提取流程。

支持的输入格式
--------------
1. **chat_test 格式**：含 ``对话历史`` 字段的 dict（如 ``chat_test_100.json``）。
2. **SGD 格式**：含 ``turns`` 字段的 dict（SYSTEM/USER speaker）。
3. **简单列表格式**：``List[str]``，每项形如 ``"agent: ..."`` / ``"user: ..."``
   或 ``"机器人：..."`` / ``"用户：..."``（兼容旧式 ``"坐席：..."``）。
4. **平铺文本格式**：单条 ``str``，多轮以换行分隔，每行含说话人前缀。
5. **嵌套 query 格式**：含 ``query`` 字段的 dict，``query`` 本身含 ``对话历史``
   （如 ``chat_test_500.json``，结构为
   ``{"label": "...", "query": {"用户信息": "...", "对话历史": [...], ...}}``）。

归一化输出格式
--------------
内部格式为 ``dict``，包含以下字段：

    {
        "session_id": "<dialogue_id 或自动生成>",
        "对话历史": [{"机器人": "...", "用户": "..."}, ...]
    }

每条 ``对话历史`` 元素为配对轮次 dict，键为 ``"机器人"``（机器人/助手发言）
和 ``"用户"``（用户发言）；若某一方在本轮中无发言则省略该键。

原始记录中的其他业务字段（如 ``用户信息``、``坐席回复``、``人工校验``、``label``）
会原样保留在输出 dict 中，供下游代码按需使用。
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Dict, List, Union

# ------------------------------------------------------------------
# 说话人标记规范化常量
# ------------------------------------------------------------------

# 中文前缀（统一标准：机器人 / 用户）
_AGENT_ZH = "机器人："
_USER_ZH = "用户："

# 英文前缀（常见 agent/user）
_AGENT_EN_RE = re.compile(
    r"^(agent|system|assistant|机器人|坐席|客服|ai)\s*[：:]\s*",
    re.IGNORECASE,
)
_USER_EN_RE = re.compile(
    r"^(user|human|customer|用户|客户|顾客)\s*[：:]\s*",
    re.IGNORECASE,
)

# SGD speaker 映射
_SGD_SPEAKER_MAP: Dict[str, str] = {
    "SYSTEM": "机器人",
    "USER": "用户",
}


def _normalize_line(line: str) -> str:
    """
    将单行文本规范化为 ``机器人：...`` / ``用户：...`` 格式。

    若无法识别说话人前缀，默认视为机器人话语。
    """
    line = line.strip()
    if not line:
        return ""
    if _AGENT_EN_RE.match(line):
        utt = _AGENT_EN_RE.sub("", line).strip()
        return f"{_AGENT_ZH}{utt}"
    if _USER_EN_RE.match(line):
        utt = _USER_EN_RE.sub("", line).strip()
        return f"{_USER_ZH}{utt}"
    # 已是规范格式（机器人：/用户：）
    if line.startswith(_AGENT_ZH) or line.startswith(_USER_ZH):
        return line
    # 无法识别：默认作为机器人话语（外呼场景通常以机器人开场）
    return f"{_AGENT_ZH}{line}"


def _pair_flat_history(flat: List[str]) -> List[Dict[str, str]]:
    """将平铺的归一化字符串列表转换为配对轮次 dict 列表。

    每条 agent 发言与紧跟其后的 user 发言合并为一个
    ``{"机器人": "...", "用户": "..."}`` dict；若 agent 发言无后续
    user 发言（如最终告别语），则产生 ``{"机器人": "..."}``；
    若 user 发言无前置 agent 发言，则产生 ``{"用户": "..."}``。
    """
    turns: List[Dict[str, str]] = []
    current: Dict[str, str] = {}
    for line in flat:
        if line.startswith(_AGENT_ZH):
            if current:
                turns.append(current)
            current = {"机器人": line[len(_AGENT_ZH):]}
        elif line.startswith(_USER_ZH):
            text = line[len(_USER_ZH):]
            if "机器人" in current:
                current["用户"] = text
                turns.append(current)
                current = {}
            else:
                # user-only (no preceding agent utterance)
                if current:
                    turns.append(current)
                turns.append({"用户": text})
                current = {}
    if current:
        turns.append(current)
    return turns


def _is_new_format(history: List[Any]) -> bool:
    """判断 ``对话历史`` 列表是否已经是新配对 dict 格式。"""
    if not history:
        return True
    return isinstance(history[0], dict) and (
        "机器人" in history[0] or "用户" in history[0]
    )


def normalize_dialogue(
    raw: Union[str, List[Any], Dict[str, Any]],
    dialogue_id: str = "",
) -> Dict[str, Any]:
    """
    将单条原始对话归一化为内部 chat_test 格式。

    参数
    ----
    raw:
        支持以下类型：

        - ``str``：平铺文本，以 ``\\n`` 分隔各轮，每行含说话人前缀。
        - ``List``：每项为一轮话语（含说话人前缀的 str）或 SGD turn dict，
          也可为已转换的 ``{"机器人": "...", "用户": "..."}`` dict。
        - ``Dict``：含 ``对话历史`` 的 chat_test 格式 *或*
          含 ``turns`` 的 SGD 格式。已经是规范格式的 dict 直接透传。
    dialogue_id:
        可选的对话 ID；若 raw 已含 ID 字段则以 raw 为准。

    返回
    ----
    dict，格式为
    ``{"session_id": "...", "对话历史": [{"机器人": "...", "用户": "..."}, ...]}``.
    """
    if isinstance(raw, str):
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        flat = [_normalize_line(ln) for ln in lines if _normalize_line(ln)]
        return {
            "session_id": dialogue_id or "dlg_0",
            "对话历史": _pair_flat_history(flat),
        }

    if isinstance(raw, list):
        # 已是新格式 dict 列表（含 "机器人"/"用户" 键）→ 直接使用
        if _is_new_format(raw):
            return {
                "session_id": dialogue_id or "dlg_0",
                "对话历史": list(raw),
            }
        # 列表：每项要么是 str（一轮），要么是 dict（SGD turn）
        flat: List[str] = []
        for item in raw:
            if isinstance(item, str):
                norm = _normalize_line(item)
                if norm:
                    flat.append(norm)
            elif isinstance(item, dict):
                # SGD turn dict
                speaker_code = item.get("speaker", "SYSTEM")
                speaker_zh = _SGD_SPEAKER_MAP.get(speaker_code, "机器人")
                utt = item.get("utterance", "").strip()
                if utt:
                    flat.append(f"{speaker_zh}：{utt}")
        return {
            "session_id": dialogue_id or "dlg_0",
            "对话历史": _pair_flat_history(flat),
        }

    if isinstance(raw, dict):
        # 已含 对话历史：直接返回（保留原有字段）
        if "对话历史" in raw:
            result = dict(raw)
            if not result.get("session_id"):
                result["session_id"] = dialogue_id or "dlg_0"
            # 若 对话历史 仍是旧格式字符串列表，在线转换
            hist = result["对话历史"]
            if hist and isinstance(hist[0], str):
                flat_h = [_normalize_line(ln) for ln in hist if isinstance(ln, str) and ln.strip()]
                result["对话历史"] = _pair_flat_history(flat_h)
            return result

        # SGD turns 格式
        if "turns" in raw:
            flat = []
            for turn in raw["turns"]:
                speaker_code = turn.get("speaker", "SYSTEM")
                speaker_zh = _SGD_SPEAKER_MAP.get(speaker_code, "机器人")
                utt = turn.get("utterance", "").strip()
                if utt:
                    flat.append(f"{speaker_zh}：{utt}")
            sid = (
                raw.get("session_id")
                or raw.get("dialogue_id")
                or dialogue_id
                or "dlg_0"
            )
            return {"session_id": sid, "对话历史": _pair_flat_history(flat)}

        # 嵌套 query 格式（如 chat_test_500.json：{label, query:{用户信息, 对话历史, ...}}）
        if "query" in raw and isinstance(raw.get("query"), dict):
            query: Dict[str, Any] = dict(raw["query"])
            # 将顶层 label 字段映射到 人工校验（如已有则不覆盖）
            if "label" in raw:
                query.setdefault("人工校验", raw["label"])
            # 生成 session_id（嵌套格式通常没有此字段）
            if not query.get("session_id"):
                raw_bytes = json.dumps(raw, ensure_ascii=False, sort_keys=True).encode()
                h = hashlib.sha256(raw_bytes).hexdigest()[:12]
                query["session_id"] = dialogue_id or f"dlg_{h}"
            # 递归：query 内部含 对话历史，走格式 1 分支
            return normalize_dialogue(query, dialogue_id=dialogue_id)

        # 未知 dict 格式：尝试从常见字段提取
        for key in ("dialogue", "conversation", "text", "content"):
            if key in raw:
                return normalize_dialogue(raw[key], dialogue_id=dialogue_id)

        raise ValueError(
            f"无法识别的对话格式：dict 中既无 '对话历史' 也无 'turns' 字段。"
            f"已知 key: {list(raw.keys())[:10]}"
        )

    raise TypeError(
        f"不支持的对话类型 {type(raw).__name__}，"
        "期望 str、List 或 Dict。"
    )


def normalize_dialogues(
    raws: List[Any],
) -> List[Dict[str, Any]]:
    """
    批量归一化对话列表。

    参数
    ----
    raws:
        每项可为 :func:`normalize_dialogue` 支持的任意格式。

    返回
    ----
    归一化后的 dict 列表。
    """
    result = []
    for i, raw in enumerate(raws):
        try:
            result.append(normalize_dialogue(raw, dialogue_id=f"dlg_{i}"))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"第 {i} 条对话归一化失败: {exc}") from exc
    return result
