"""
安逸花外呼对话数据清洗模块（任务一：1.1 数据链路清洗）

对原始 chat_test 格式的对话数据进行系统清洗，输出干净的标准格式，
供增量提取管线（pipeline.py）和基准评测（benchmark/runners/）使用。

清洗项目：
  · 去除截断对话（对话轮数过少，无实质性内容）
  · 去除超长长尾对话（轮数过多，LLM 上下文窗口处理困难）
  · 格式规范化：确保每行对话均含"坐席："/"用户："前缀
  · 必填字段校验：session_id、对话历史
  · 空白发言过滤：去除每轮中发言内容为空的行

典型使用::

    from contextmind.scenarios.anyihua.schema_extraction.data_cleaner import (
        clean_dialogues, CleanConfig, CleanReport,
    )

    raw = json.loads(Path("resources/data/chat_test_100.json").read_text())
    config = CleanConfig(min_turns=2, max_turns=40)
    clean_data, report = clean_dialogues(raw, config)
    print(report)

产出:
  · clean_data: 清洗后的对话列表（格式与原始 chat_test 完全兼容）
  · report:     CleanReport，含各清洗阶段过滤数量和对齐统计
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

# 对话前缀正则（兼容全角/半角冒号）
_LINE_PREFIX_RE = re.compile(r"^(坐席[：:])|(用户[：:])")


# ---------------------------------------------------------------------------
# 配置与报告数据类
# ---------------------------------------------------------------------------


@dataclass
class CleanConfig:
    """
    数据清洗策略配置。

    所有阈值均提供合理默认值，可根据数据集规模和任务特性调整。
    """

    #: 最少对话轮数（含）——低于此值视为截断对话
    min_turns: int = 2
    #: 最多对话轮数（含）——高于此值视为长尾异常对话
    max_turns: int = 60
    #: 是否自动修正无前缀的对话行（True=尝试补全；False=丢弃该行）
    fix_missing_prefix: bool = True
    #: 最短发言字符数（不含前缀）——低于此值视为空白/噪声发言
    min_utterance_chars: int = 1
    #: 是否要求 session_id 字段存在且非空
    require_session_id: bool = True


@dataclass
class CleanReport:
    """
    数据清洗报告。

    记录各阶段过滤数量，用于数据质量审计与基准评测文档生成。
    """

    total_input: int = 0
    filtered_no_session_id: int = 0
    filtered_too_short: int = 0
    filtered_too_long: int = 0
    filtered_no_valid_turns: int = 0
    total_output: int = 0

    #: 因缺少前缀而被修正的对话行数（仅当 fix_missing_prefix=True）
    lines_prefix_fixed: int = 0
    #: 因缺少前缀且不可修正而被丢弃的对话行数
    lines_dropped: int = 0
    #: 因内容过短被过滤的发言行数
    lines_too_short: int = 0

    def __str__(self) -> str:
        kept_pct = (
            round(self.total_output / self.total_input * 100, 1)
            if self.total_input
            else 0.0
        )
        return (
            f"CleanReport("
            f"input={self.total_input}, "
            f"output={self.total_output} ({kept_pct}% kept), "
            f"filtered=["
            f"no_session_id={self.filtered_no_session_id}, "
            f"too_short={self.filtered_too_short}, "
            f"too_long={self.filtered_too_long}, "
            f"no_valid_turns={self.filtered_no_valid_turns}"
            f"], "
            f"line_fixes={self.lines_prefix_fixed}, "
            f"line_drops={self.lines_dropped}"
            f")"
        )


# ---------------------------------------------------------------------------
# 核心清洗函数
# ---------------------------------------------------------------------------


def _normalize_prefix(line: str, config: CleanConfig, report: CleanReport) -> Optional[str]:
    """
    规范化单条对话行的角色前缀。

    - 如果已有合法前缀（坐席：/用户：），直接返回原行。
    - 如果缺少前缀且 fix_missing_prefix=True，尝试根据行首关键字推断角色。
    - 否则返回 None（该行将被丢弃）。

    参数:
        line:    原始对话行字符串
        config:  清洗配置
        report:  清洗报告（in-place 更新）

    返回:
        规范化后的对话行，或 None（应丢弃）
    """
    line = line.strip()
    if not line:
        return None

    # 已有合法前缀
    if line.startswith(_AGENT_PREFIX) or line.startswith(_USER_PREFIX):
        return line

    # 兼容全角/半角冒号变体
    if re.match(r"^坐席[：:]", line):
        normalized = _AGENT_PREFIX + line.split("：", 1)[-1].split(":", 1)[-1]
        report.lines_prefix_fixed += 1
        return normalized
    if re.match(r"^用户[：:]", line):
        normalized = _USER_PREFIX + line.split("：", 1)[-1].split(":", 1)[-1]
        report.lines_prefix_fixed += 1
        return normalized

    if not config.fix_missing_prefix:
        report.lines_dropped += 1
        return None

    # 尝试关键字推断（启发式）
    lower = line.lower()
    if any(kw in lower for kw in ("客服", "坐席", "agent", "客服：", "坐席：")):
        normalized = _AGENT_PREFIX + line
        report.lines_prefix_fixed += 1
        return normalized

    # 无法修复，丢弃
    report.lines_dropped += 1
    return None


def _clean_single_dialogue(
    raw: Dict[str, Any],
    config: CleanConfig,
    report: CleanReport,
) -> Optional[Dict[str, Any]]:
    """
    清洗单条对话，返回清洗后的对话字典或 None（应过滤掉）。

    参数:
        raw:    原始对话字典（chat_test 格式）
        config: 清洗配置
        report: 清洗报告（in-place 更新）

    返回:
        清洗后的字典（字段与原始格式兼容）或 None
    """
    # 1. 必填字段校验
    if config.require_session_id and not (raw.get("session_id") or "").strip():
        report.filtered_no_session_id += 1
        logger.debug(f"[Cleaner] 过滤：缺少 session_id")
        return None

    raw_lines: List[str] = [str(line) for line in raw.get("对话历史", [])]

    # 2. 规范化每一行前缀 + 过滤空白发言
    clean_lines: List[str] = []
    for raw_line in raw_lines:
        norm = _normalize_prefix(raw_line, config, report)
        if norm is None:
            continue
        # 提取发言内容（去掉前缀）
        if norm.startswith(_AGENT_PREFIX):
            utterance = norm[len(_AGENT_PREFIX):]
        elif norm.startswith(_USER_PREFIX):
            utterance = norm[len(_USER_PREFIX):]
        else:
            utterance = norm

        if len(utterance.strip()) < config.min_utterance_chars:
            report.lines_too_short += 1
            continue

        clean_lines.append(norm)

    # 3. 轮数校验（截断 / 长尾）
    n_turns = len(clean_lines)
    session_id = raw.get("session_id", "?")

    if n_turns < config.min_turns:
        report.filtered_too_short += 1
        logger.debug(f"[Cleaner] 过滤：对话过短 ({n_turns} 轮), session_id={session_id}")
        return None

    if n_turns > config.max_turns:
        report.filtered_too_long += 1
        logger.debug(f"[Cleaner] 过滤：对话过长 ({n_turns} 轮), session_id={session_id}")
        return None

    if not clean_lines:
        report.filtered_no_valid_turns += 1
        logger.debug(f"[Cleaner] 过滤：无有效对话行, session_id={session_id}")
        return None

    # 构建清洗后的字典（保持与原始格式完全兼容）
    clean = dict(raw)
    clean["对话历史"] = clean_lines
    return clean


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


def clean_dialogues(
    raw_dialogues: List[Dict[str, Any]],
    config: Optional[CleanConfig] = None,
) -> Tuple[List[Dict[str, Any]], CleanReport]:
    """
    批量清洗安逸花外呼对话数据。

    参数:
        raw_dialogues: 原始对话列表（chat_test 格式）
        config:        清洗配置（None 时使用默认配置）

    返回:
        (clean_dialogues, report) 元组：
        - clean_dialogues: 清洗后的对话列表
        - report:          CleanReport 报告对象
    """
    if config is None:
        config = CleanConfig()

    report = CleanReport(total_input=len(raw_dialogues))
    clean: List[Dict[str, Any]] = []

    for raw in raw_dialogues:
        result = _clean_single_dialogue(raw, config, report)
        if result is not None:
            clean.append(result)

    report.total_output = len(clean)

    logger.info(
        f"[Cleaner] 清洗完成: {report.total_input} → {report.total_output} 条 "
        f"(过滤 {report.total_input - report.total_output} 条)"
    )
    return clean, report
