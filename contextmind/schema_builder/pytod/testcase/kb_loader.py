"""
KB（知识库）上下文数据加载器。

本模块从 KnowledgeBaseBuilder 生成的 4 个 JSON 文件中读取业务背景数据，
供测试用例生成器（:class:`~contextmind.schema_builder.pytod.testcase.generator.TestCaseGenerator`）
和代码生成器注入 LLM prompt：

- :func:`load_dialogue_samples`            — 从 chat_test 格式对话文件加载对话样本。
- :func:`load_sgd_dialogue_samples`        — 从 dialogues_001.json（SGD 格式）加载对话样本。
- :func:`load_discovery_samples`           — 从 discovery_raw.json 提取槽位/意图示例摘要。
- :func:`load_conversion_summary_context`  — 从 conversion_summary.json 提取发现统计摘要。
- :func:`load_kb_context`                  — 扫描 KB 目录，返回各文件路径字典。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


def load_dialogue_samples(
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
            logger.warning(f"[kb_loader] 对话数据文件不存在: {path}")
            return []

        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)

        if not isinstance(data, list) or not data:
            return []

        samples: List[str] = []
        for item in data:
            if len(samples) >= max_samples:
                break

            # 判断对话数据格式并提取字段
            if "query" in item:
                # chat_test_500 格式：{label, query:{用户信息, 对话历史}}
                q = item["query"]
                user_info = q.get("用户信息", "")
                history = q.get("对话历史", [])
            else:
                # chat_test_100 格式：{session_id, 用户信息, 对话历史}
                user_info = item.get("用户信息", "")
                history = item.get("对话历史", [])

            if not history:
                continue

            lines: List[str] = []
            # 截取用户信息前 3 个字段摘要
            if user_info:
                brief = "、".join(user_info.split("#")[1:4])
                lines.append(f"[用户信息] {brief}")

            # 格式化对话轮次
            for turn in history[:8]:  # 最多取前 8 轮
                if isinstance(turn, dict):
                    for speaker, text in turn.items():
                        lines.append(f"{speaker}：{text[:80]}")
                elif isinstance(turn, str):
                    lines.append(turn[:100])

            if lines:
                samples.append("\n".join(lines))

        return samples

    except Exception as exc:
        logger.warning(f"[kb_loader] 加载对话数据失败: {exc}")
        return []


def load_sgd_dialogue_samples(
    data_path: Union[str, Path],
    max_samples: int = 5,
) -> List[str]:
    """从 SGD 格式的 dialogues_001.json 加载并格式化对话样本。

    SGD 格式：``[{"dialogue_id":..., "services":[...], "turns":[{"speaker":..., "utterance":...,
    "frames":[{"service":..., "slots":[...], "state":{"slot_values":{...}}}]}]}]``

    除对话文本外，还会提取 ``frames.state.slot_values`` 中的实际槽位值，
    帮助 LLM 了解多轮对话中槽位的积累过程。

    Returns:
        格式化后的对话文本列表（每条包含对话内容和槽位状态快照）。
    """
    try:
        path = Path(data_path)
        if not path.exists():
            logger.warning(f"[kb_loader] SGD 对话文件不存在: {path}")
            return []
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list) or not data:
            return []
        samples: List[str] = []
        for item in data:
            if len(samples) >= max_samples:
                break
            turns = item.get("turns", [])
            if not turns:
                continue
            lines: List[str] = []
            # 记录最后一次出现的 slot_values 快照（反映多轮积累结果）
            slot_snapshots: List[str] = []
            for turn in turns[:12]:
                speaker = turn.get("speaker", "")
                utterance = turn.get("utterance", "")
                # SGD 中机器人说话者标签为 SYSTEM，用户为 USER
                label = "机器人" if speaker.upper() in ("SYSTEM", "机器人") else "用户"
                lines.append(f"{label}：{utterance[:80]}")
                # 提取该轮的槽位值快照（USER 轮次 frames 中的 state.slot_values）
                if speaker.upper() in ("USER", "用户"):
                    for frame in turn.get("frames", []):
                        state = frame.get("state", {})
                        sv = state.get("slot_values", {})
                        if sv:
                            sv_str = "、".join(
                                f"{k}={v[0] if isinstance(v, list) else v}"
                                for k, v in list(sv.items())[:6]
                            )
                            slot_snapshots.append(f"  [已收集槽位: {sv_str}]")
            # 在对话末尾附加槽位快照（展示多轮积累的槽位状态）
            if slot_snapshots:
                lines.append(slot_snapshots[-1])  # 只展示最终状态，避免过长
            if lines:
                samples.append("\n".join(lines))
        return samples
    except Exception as exc:
        logger.warning(f"[kb_loader] 加载 SGD 对话数据失败: {exc}")
        return []


def load_discovery_samples(
    data_path: Union[str, Path],
    max_items: int = 25,
) -> str:
    """从 discovery_raw.json 提取真实槽位示例，格式化为 LLM 可读的摘要。

    discovery_raw.json 格式：
    ``[{"dialogue_id":..., "turns":[{"turn_idx":..., "speaker":..., "utterance":...,
        "extractions":[{"extraction_class":..., "label":..., "value":...}]}]}]``

    提取所有 extraction_class 类型（intent、slot、slot_value、fact）中的标签和值，
    为 LLM 提供更丰富的真实业务数据示例。

    Returns:
        格式化后的槽位示例摘要字符串（空时返回空字符串）。
    """
    try:
        path = Path(data_path)
        if not path.exists():
            return ""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return ""
        # 收集所有有 extractions 的轮次中的意图/槽位/事实示例
        examples: Dict[str, List[str]] = {}
        count = 0
        for item in data:
            for turn in item.get("turns", []):
                for ext in turn.get("extractions", []):
                    label = ext.get("label", "")
                    value = ext.get("value", "")
                    cls = ext.get("extraction_class", "")
                    # 覆盖所有有意义的提取类型
                    if label and value and cls in ("intent", "slot", "slot_value", "fact"):
                        examples.setdefault(label, [])
                        if value not in examples[label]:
                            examples[label].append(value)
                            count += 1
                if count >= max_items * 3:
                    break
            if count >= max_items * 3:
                break
        if not examples:
            return ""
        lines = ["## 真实对话中提取到的槽位/意图示例（参考生成真实业务值）"]
        for label, values in list(examples.items())[:max_items]:
            sample_vals = "、".join(str(v)[:60] for v in values[:3])
            lines.append(f"- {label}：{sample_vals}")
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"[kb_loader] 加载 discovery_raw 失败: {exc}")
        return ""


def load_conversion_summary_context(
    data_path: Union[str, Path],
) -> str:
    """从 conversion_summary.json 提取发现的意图/槽位统计，格式化为 LLM 可读摘要。

    conversion_summary.json 格式（由 KnowledgeBaseBuilder.save_dataset() 生成）：
    ``{"output_dir":..., "dialogues":N, "turns":N, "schema_coverage":
       {"extracted_slots":[...], "extracted_intents":[...]}, ...}``

    Returns:
        格式化后的统计摘要字符串（空时返回空字符串）。
    """
    try:
        path = Path(data_path)
        if not path.exists():
            return ""
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return ""
        lines: List[str] = ["## 知识库构建统计（来自 conversion_summary）"]
        n_dlg = data.get("dialogues", "?")
        n_turns = data.get("turns", "?")
        lines.append(f"- 对话数: {n_dlg}，总轮次: {n_turns}")
        coverage = data.get("schema_coverage", {})
        extracted_intents: List[str] = coverage.get("extracted_intents", [])
        extracted_slots: List[str] = coverage.get("extracted_slots", [])
        if extracted_intents:
            shown = "、".join(extracted_intents[:20])
            lines.append(
                f"- 从真实对话中发现的意图（共 {len(extracted_intents)} 个）: {shown}"
            )
        if extracted_slots:
            shown = "、".join(extracted_slots[:20])
            lines.append(
                f"- 从真实对话中发现的槽位（共 {len(extracted_slots)} 个）: {shown}"
            )
        return "\n".join(lines)
    except Exception as exc:
        logger.warning(f"[kb_loader] 加载 conversion_summary 失败: {exc}")
        return ""


def load_kb_context(
    kb_dir: Union[str, Path],
) -> Dict[str, Any]:
    """从 KB 输出目录加载 4 个数据文件的上下文信息。

    KB 输出目录（由 :func:`contextmind.knowledge.KnowledgeBaseBuilder.save_dataset` 生成）
    中包含以下文件（全部可选，缺失时跳过）：

    - ``schema.json``         — 服务 schema（意图/槽位定义）
    - ``dialogues_001.json``  — SGD 格式的处理后对话
    - ``discovery_raw.json``  — 逐轮槽位提取原始数据
    - ``conversion_summary.json`` — 转换摘要统计

    Returns:
        包含以下键的字典：
        ``dialogues_path``  (Path|None)、``discovery_path``  (Path|None)、
        ``summary_path``    (Path|None)、``schema_path``     (Path|None)。
    """
    kb_dir = Path(kb_dir)

    def _find(name: str) -> Optional[Path]:
        p = kb_dir / name
        return p if p.exists() else None

    return {
        "dialogues_path": _find("dialogues_001.json"),
        "discovery_path": _find("discovery_raw.json"),
        "summary_path": _find("conversion_summary.json"),
        "schema_path": _find("schema.json"),
    }
