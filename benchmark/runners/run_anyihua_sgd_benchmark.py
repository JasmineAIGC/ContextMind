#!/usr/bin/env python3
"""
安逸花外呼 SGD 知识库提取质量基准评测

对 3 步 SGD 管道产出的每条对话进行知识质量评测，聚合报告：
  · 溯源完整率（Provenance Completeness）：提取项有 char_interval 的占比
  · 精确对齐率（Exact Alignment Rate）：对齐状态为 match_exact 的占比
  · 槽位提取率（Slot Extraction Rate）：每条对话平均提取到的槽位值数
  · 意图检测率（Intent Detection Rate）：用户轮次中识别到具体意图的占比
  · Schema 覆盖率（Schema Coverage）：已发现的槽位/意图 / 预定义 Schema 的比例

评测使用 **规则模式**（无需 LLM 调用）：
  · 由 ChatTestToSGDConverter._convert_record（规则标注）生成 SGD 对话结构
  · 通过 langextract WordAligner 对每条对话批量对齐槽位/意图至原文字符区间

----------------------------------------------------------------------
使用方法
----------------------------------------------------------------------

  # 全量评测（100 条对话）
  python benchmark/runners/run_anyihua_sgd_benchmark.py

  # 限制条数（快速调试）
  python benchmark/runners/run_anyihua_sgd_benchmark.py --limit 10

  # 指定数据 / Schema 路径
  python benchmark/runners/run_anyihua_sgd_benchmark.py \\
      --input resources/data/chat_test_100.json \\
      --schema resources/anyihua_sgd/schema.json

  # 保存详细结果到 JSON 文件
  python benchmark/runners/run_anyihua_sgd_benchmark.py \\
      --output-json data/anyihua_sgd_benchmark_result.json

----------------------------------------------------------------------
输出示例
----------------------------------------------------------------------

  ============================================================
    安逸花 SGD 知识库提取质量评测
  ============================================================
  数据: resources/data/chat_test_100.json (100 条对话)
  Schema: resources/anyihua_sgd/schema.json

  [数据清洗]
    输入: 100 条  →  输出: 100 条 (无过滤)

  [溯源质量（langextract WordAligner）]
    溯源完整率 (Provenance Completeness):  89.23%
    精确对齐率 (Exact Alignment Rate):     62.47%

  [提取丰富度]
    槽位提取率 (Slot/dialogue):            3.21
    意图检测率 (Intent Detection Rate):    74.50%

  [Schema 覆盖率]
    槽位覆盖 (Slot Coverage):   8 / 10  (80.0%)
    意图覆盖 (Intent Coverage): 7 / 9   (77.8%)

  [统计]
    总对话数:    100
    总提取项数:  432
    用户轮次数:  310
  ============================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# 将项目根目录加入 Python 路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from langextract.data import Extraction, ExampleData, CharInterval, AlignmentStatus

from benchmark.algorithms.anyihua_sgd import AnYiHuaSGDEvaluator, AnYiHuaSGDMetrics
from benchmark.datasets.anyihua.adapter import ChatTestToSGDConverter
from contextmind.infra.logger import get_logger, setup_logging, LogLevel
from contextmind.scenarios.anyihua.schema_extraction import schema_from_sgd_file
from contextmind.scenarios.anyihua.schema_extraction.data_cleaner import (
    CleanConfig,
    CleanReport,
    clean_dialogues,
)

logger = get_logger(__name__)

# 默认路径
_DEFAULT_INPUT = str(_PROJECT_ROOT / "resources" / "data" / "chat_test_100.json")
_DEFAULT_SCHEMA = str(_PROJECT_ROOT / "resources" / "anyihua_sgd" / "schema.json")

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# ---------------------------------------------------------------------------
# 溯源后处理：对规则转换结果添加 langextract 对齐信息
# ---------------------------------------------------------------------------


def _align_with_substring_search(
    extractions: List[Extraction],
    source_text: str,
) -> List[Extraction]:
    """
    使用简单字符串搜索对每个 Extraction 进行原文定位。

    直接在 source_text 中查找 extraction_text，并设置 CharInterval
    和 AlignmentStatus（match_exact 或 None）。这比 WordAligner 的
    difflib SequenceMatcher 方法快几个数量级，适合长对话的批量评测。

    参数:
        extractions: 待对齐的 Extraction 列表
        source_text: 完整对话原文

    返回:
        对齐后的 Extraction 列表（char_interval / alignment_status 已填充）
    """
    aligned = []
    for ext in extractions:
        text = ext.extraction_text
        pos = source_text.find(text)
        if pos >= 0:
            aligned.append(Extraction(
                extraction_class=ext.extraction_class,
                extraction_text=text,
                char_interval=CharInterval(start_pos=pos, end_pos=pos + len(text)),
                alignment_status=AlignmentStatus.MATCH_EXACT,
                attributes=ext.attributes,
            ))
        else:
            aligned.append(Extraction(
                extraction_class=ext.extraction_class,
                extraction_text=text,
                char_interval=None,
                alignment_status=None,
                attributes=ext.attributes,
            ))
    return aligned


def _add_provenance(sgd_dialogue: Dict[str, Any]) -> Dict[str, Any]:
    """
    对 ChatTestToSGDConverter 产出的 SGD 对话，补充 langextract 溯源信息。

    从 turns 中提取意图和槽位值，拼接对话原文，通过直接字符串搜索
    （O(n) 复杂度）回溯对齐到字符区间，并将结果（langextract CharInterval /
    AlignmentStatus）写入 metadata.langextract_example。

    注意：这里使用 str.find() 而非 langextract WordAligner（基于 difflib
    SequenceMatcher），因为 SequenceMatcher 对长中文对话（数百字符）
    的运行时间不可接受。两种方法产出相同的 langextract 数据结构。

    参数:
        sgd_dialogue: ChatTestToSGDConverter.convert_record() 的输出
    
    返回:
        添加了 metadata.langextract_example 的 SGD 对话字典
    """
    turns: List[Dict[str, Any]] = sgd_dialogue.get("turns", [])

    # 重建对话原文（坐席：.../用户：... 格式）
    source_lines = []
    for turn in turns:
        prefix = _AGENT_PREFIX if turn.get("speaker") == "SYSTEM" else _USER_PREFIX
        source_lines.append(f"{prefix}{turn.get('utterance', '')}")
    source_text = "\n".join(source_lines)

    # 从 frames 提取意图和槽位信息，构造 Extraction 对象
    raw_extractions: List[Extraction] = []

    for turn in turns:
        speaker = turn.get("speaker", "")
        utterance = turn.get("utterance", "")
        frames = turn.get("frames", [])
        if not frames or not utterance:
            continue
        frame = frames[0]

        if speaker == "USER":
            # 用户意图：extraction_text = 用户发言原话
            state = frame.get("state", {})
            intent_name = state.get("active_intent", "general_inquiry")
            if intent_name and intent_name not in ("general_inquiry", "NONE"):
                raw_extractions.append(Extraction(
                    extraction_class="intent",
                    extraction_text=utterance,
                    attributes={"intent_name": intent_name},
                    # char_interval & alignment_status 由 _align_extractions() 批量填充
                ))
            # 槽位值：extraction_text = 槽位的原始值文本
            for slot_name, values in state.get("slot_values", {}).items():
                if values:
                    raw_extractions.append(Extraction(
                        extraction_class="slot_value",
                        extraction_text=values[0],
                        attributes={"slot_name": slot_name},
                        # char_interval & alignment_status 由 _align_extractions() 批量填充
                    ))
        else:  # SYSTEM
            # 系统意图：extraction_text = 坐席发言原话
            svc_call = frame.get("service_call")
            if svc_call:
                method = svc_call.get("method", "")
                if method:
                    raw_extractions.append(Extraction(
                        extraction_class="system_intent",
                        extraction_text=utterance,
                        attributes={"method_name": method},
                        # char_interval & alignment_status 由 _align_extractions() 批量填充
                    ))

    # 批量对齐：使用高效字符串搜索（langextract CharInterval + AlignmentStatus）
    aligned_extractions = _align_with_substring_search(raw_extractions, source_text)

    # 对齐统计
    aligned_count = sum(
        1 for e in aligned_extractions if e.alignment_status is not None
    )
    total = len(aligned_extractions)

    # 序列化并写入 metadata（使用 langextract ExampleData 结构）
    example_data = ExampleData(text=source_text, extractions=aligned_extractions)

    def _ext_to_dict(e: Extraction) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "extraction_class": e.extraction_class,
            "extraction_text": e.extraction_text,
            "alignment_status": e.alignment_status.value if e.alignment_status else None,
            "attributes": e.attributes or {},
        }
        if e.char_interval is not None:
            d["char_interval"] = {
                "start_pos": e.char_interval.start_pos,
                "end_pos": e.char_interval.end_pos,
            }
        else:
            d["char_interval"] = None
        return d

    result = dict(sgd_dialogue)
    metadata = dict(sgd_dialogue.get("metadata", {}))
    metadata["langextract_example"] = {
        "text": example_data.text,
        "extractions": [_ext_to_dict(e) for e in example_data.extractions],
    }
    metadata["langextract_stats"] = {
        "total_extractions": total,
        "aligned_count": aligned_count,
        "alignment_rate": round(aligned_count / total, 3) if total else 0.0,
    }
    result["metadata"] = metadata
    return result


# ---------------------------------------------------------------------------
# 规则模式 SGD 转换 + 溯源
# ---------------------------------------------------------------------------


def _convert_with_provenance(
    clean_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    使用规则模式将清洗后的对话转换为 SGD 格式，并添加 langextract 溯源信息。

    参数:
        clean_data: 清洗后的 chat_test 格式对话列表

    返回:
        SGD 格式对话列表（含 metadata.langextract_example）
    """
    converter = ChatTestToSGDConverter()
    sgd_dialogues = []
    for idx, raw in enumerate(clean_data):
        try:
            sgd = converter.convert_record(raw, idx)    # public API
            sgd_with_prov = _add_provenance(sgd)
            sgd_dialogues.append(sgd_with_prov)
        except Exception as exc:
            session_id = raw.get("session_id", f"idx_{idx}")
            logger.warning(f"[Runner] 转换失败 session_id={session_id}: {exc}")
    return sgd_dialogues


# ---------------------------------------------------------------------------
# 主评测流程
# ---------------------------------------------------------------------------


def run_benchmark(
    input_path: str = _DEFAULT_INPUT,
    schema_path: str = _DEFAULT_SCHEMA,
    limit: Optional[int] = None,
    output_json: Optional[str] = None,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    执行安逸花 SGD 知识库提取质量基准评测。

    参数:
        input_path:  chat_test JSON 文件路径
        schema_path: SGD schema.json 路径
        limit:       仅评测前 N 条对话（None = 全量）
        output_json: 将结果写入此 JSON 文件（None = 不写入）
        verbose:     是否开启 DEBUG 日志

    返回:
        评测结果字典（含 metrics、clean_report、meta 等字段）
    """
    setup_logging(LogLevel.DEBUG if verbose else LogLevel.INFO)
    logger.info("=" * 60)
    logger.info("安逸花 SGD 知识库提取质量评测")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 加载原始数据
    # ------------------------------------------------------------------
    raw_data: List[Dict[str, Any]] = json.loads(
        Path(input_path).read_text(encoding="utf-8")
    )
    if limit:
        raw_data = raw_data[:limit]
    logger.info(f"[Runner] 加载数据: {input_path} ({len(raw_data)} 条)")

    # ------------------------------------------------------------------
    # 数据清洗（1.1 数据链路清洗）
    # ------------------------------------------------------------------
    clean_data, clean_report = clean_dialogues(raw_data, CleanConfig())
    logger.info(f"[Runner] 清洗完成: {clean_report}")

    # ------------------------------------------------------------------
    # 规则模式 SGD 转换（含 langextract 溯源对齐）
    # ------------------------------------------------------------------
    logger.info("[Runner] 开始规则模式 SGD 转换（含 langextract 溯源对齐）...")
    sgd_dialogues = _convert_with_provenance(clean_data)
    logger.info(f"[Runner] 转换完成: {len(sgd_dialogues)} 条 SGD 对话")

    # ------------------------------------------------------------------
    # 加载 Schema，初始化评测器
    # ------------------------------------------------------------------
    schema = schema_from_sgd_file(Path(schema_path))
    slot_names = [s.name for s in schema.slots]
    intent_names = [i.name for i in schema.intents]

    evaluator = AnYiHuaSGDEvaluator(
        schema_slot_names=slot_names,
        schema_intent_names=intent_names,
    )
    for dlg in sgd_dialogues:
        evaluator.add_dialogue(dlg)

    # ------------------------------------------------------------------
    # 计算并打印指标
    # ------------------------------------------------------------------
    metrics = evaluator.calculate_metrics()

    _print_report(
        metrics=metrics,
        clean_report=clean_report,
        input_path=input_path,
        schema_path=schema_path,
        total_raw=len(raw_data),
    )

    # ------------------------------------------------------------------
    # 构建结果字典
    # ------------------------------------------------------------------
    result: Dict[str, Any] = {
        "meta": {
            "input_path": input_path,
            "schema_path": schema_path,
            "total_raw": len(raw_data),
            "total_clean": len(clean_data),
            "total_converted": len(sgd_dialogues),
        },
        "clean_report": {
            "total_input": clean_report.total_input,
            "total_output": clean_report.total_output,
            "filtered_no_session_id": clean_report.filtered_no_session_id,
            "filtered_too_short": clean_report.filtered_too_short,
            "filtered_too_long": clean_report.filtered_too_long,
            "lines_prefix_fixed": clean_report.lines_prefix_fixed,
            "lines_dropped": clean_report.lines_dropped,
        },
        "metrics": metrics.to_dict(),
    }

    if output_json:
        Path(output_json).parent.mkdir(parents=True, exist_ok=True)
        Path(output_json).write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"[Runner] 结果已写入: {output_json}")

    return result


def _print_report(
    metrics: AnYiHuaSGDMetrics,
    clean_report: CleanReport,
    input_path: str,
    schema_path: str,
    total_raw: int,
) -> None:
    """格式化打印评测报告到标准输出。"""
    print()
    print("=" * 60)
    print("  安逸花 SGD 知识库提取质量评测")
    print("=" * 60)
    print(f"  数据: {input_path} ({total_raw} 条对话)")
    print(f"  Schema: {schema_path}")
    print()

    filtered = clean_report.total_input - clean_report.total_output
    print("  [数据清洗]")
    print(
        f"    输入: {clean_report.total_input} 条  →  "
        f"输出: {clean_report.total_output} 条 "
        f"({'%d 条被过滤' % filtered if filtered else '无过滤'})"
    )
    print()

    print("  [溯源质量（langextract CharInterval 字符串搜索）]")
    print(
        f"    溯源完整率 (Provenance Completeness):  "
        f"{metrics.provenance_completeness * 100:.2f}%"
    )
    print(
        f"    精确对齐率 (Exact Alignment Rate):     "
        f"{metrics.exact_alignment_rate * 100:.2f}%"
    )
    print()

    print("  [提取丰富度]")
    print(f"    槽位提取率 (Slot/dialogue):            {metrics.slot_extraction_rate:.2f}")
    print(
        f"    意图检测率 (Intent Detection Rate):    "
        f"{metrics.intent_detection_rate * 100:.2f}%"
    )
    print()

    print("  [Schema 覆盖率]")
    n_seen_slots = len(metrics.seen_slot_names)
    n_total_slots = len(metrics.schema_slot_names)
    n_seen_intents = len(metrics.seen_intent_names)
    n_total_intents = len(metrics.schema_intent_names)
    print(
        f"    槽位覆盖 (Slot Coverage):   "
        f"{n_seen_slots} / {n_total_slots}  "
        f"({metrics.schema_slot_coverage * 100:.1f}%)"
    )
    print(
        f"    意图覆盖 (Intent Coverage): "
        f"{n_seen_intents} / {n_total_intents}  "
        f"({metrics.schema_intent_coverage * 100:.1f}%)"
    )
    print()

    print("  [统计]")
    print(f"    总对话数:    {metrics.total_dialogues}")
    print(f"    总提取项数:  {metrics.total_extractions}")
    print(f"    用户轮次数:  {metrics.total_user_turns}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="安逸花外呼 SGD 知识库提取质量基准评测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--input",
        default=_DEFAULT_INPUT,
        help="chat_test JSON 文件路径（默认: resources/data/chat_test_100.json）",
    )
    p.add_argument(
        "--schema",
        default=_DEFAULT_SCHEMA,
        help="SGD schema.json 路径（默认: resources/anyihua_sgd/schema.json）",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="仅评测前 N 条对话（默认: 全量）",
    )
    p.add_argument(
        "--output-json",
        default=None,
        dest="output_json",
        help="将结果写入此 JSON 文件",
    )
    p.add_argument("--verbose", action="store_true", help="开启 DEBUG 日志")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_benchmark(
        input_path=args.input,
        schema_path=args.schema,
        limit=args.limit,
        output_json=args.output_json,
        verbose=args.verbose,
    )

