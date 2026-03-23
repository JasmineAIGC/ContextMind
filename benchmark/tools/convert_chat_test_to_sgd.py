#!/usr/bin/env python3
"""
chat_test_100.json → SGD 格式转换脚本

将安逸花外呼场景的真实通话数据（resources/data/chat_test_100.json）
转换为 Google SGD（Schema-Guided Dialogue）格式，以适配 PyTOD 算法。

----------------------------------------------------------------------
SGD 格式简介
----------------------------------------------------------------------

SGD 由两种文件组成：

  schema.json
    定义服务的意图（intents）和槽位（slots），对应安逸花的业务流程。

  dialogues_*.json
    对话数据，每条对话包含：
      - dialogue_id: 会话唯一 ID
      - services: 涉及的服务列表
      - turns: [{"speaker": "USER"|"SYSTEM", "utterance": "...", "frames": [...]}]

----------------------------------------------------------------------
chat_test_100.json 与 SGD 的字段映射
----------------------------------------------------------------------

可直接映射：
  session_id          → dialogue_id
  "坐席："前缀话语    → speaker="SYSTEM" + utterance
  "用户："前缀话语    → speaker="USER" + utterance

规则推断（默认模式）：
  active_intent        → 关键词匹配安逸花意图体系
  slot_values          → 从 用户信息 字段（parse_user_info）提取 CRM 数据
  requested_slots      → 用户疑问句检测
  service_call         → active_intent → CRM API 名称映射
  service_results      → parse_user_info 解析后的 CRM 数据

LLM 增强模式（--use-llm 启用）：
  active_intent        → 大模型结合上下文语义识别，覆盖规则层近似结果
  requested_slots      → 大模型从用户疑问句中提取正在询问的槽位
  actions (USER)       → 大模型识别用户主动告知的信息槽及值
  service_call params  → 大模型从坐席话语中提取 API 调用参数

扩展元数据（非标准 SGD 字段，存入 metadata）：
  用户信息             → metadata.user_info_raw + metadata.user_info_parsed
  坐席回复             → metadata.reference_response（参考回复，供评估）
  人工校验             → metadata.qc_label（质量标签）

----------------------------------------------------------------------
使用方法
----------------------------------------------------------------------

  # 基本用法（规则模式，转换全部 100 条）
  python benchmark/tools/convert_chat_test_to_sgd.py

  # LLM 增强模式（需要配置 API key 环境变量）
  python benchmark/tools/convert_chat_test_to_sgd.py --use-llm

  # 指定输入/输出路径
  python benchmark/tools/convert_chat_test_to_sgd.py \\
      --input resources/data/chat_test_100.json \\
      --output data/anyihua_sgd

  # 只转换前 10 条（调试用）
  python benchmark/tools/convert_chat_test_to_sgd.py \\
      --limit 10 \\
      --output /tmp/anyihua_sgd_debug

  # LLM 模式 + 调试：只转换前 5 条
  python benchmark/tools/convert_chat_test_to_sgd.py \\
      --use-llm --limit 5 --inspect

  # 打印第一条转换结果到控制台
  python benchmark/tools/convert_chat_test_to_sgd.py \\
      --limit 1 --inspect

输出目录结构（与 SGD 相同）：
  <output>/
      schema.json              # 安逸花外呼场景服务 Schema
      dialogues_001.json       # 转换后的对话数据
      conversion_summary.json  # 转换统计信息
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 将项目根目录加入 Python 路径
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

from benchmark.datasets.anyihua import ChatTestToSGDConverter

# 默认路径
_DEFAULT_INPUT = str(_PROJECT_ROOT / "resources" / "data" / "chat_test_100.json")
_DEFAULT_OUTPUT = str(_PROJECT_ROOT / "data" / "anyihua_sgd")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 chat_test_100.json 转换为 SGD 格式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--input",
        default=_DEFAULT_INPUT,
        help=f"输入文件路径（默认: {_DEFAULT_INPUT}）",
    )
    parser.add_argument(
        "--output",
        default=_DEFAULT_OUTPUT,
        help=f"输出目录路径（默认: {_DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多转换的记录数（默认: 全部）",
    )
    parser.add_argument(
        "--dialogues-per-file",
        type=int,
        default=1000,
        help="每个 dialogues_*.json 最多包含的对话数（默认: 1000）",
    )
    parser.add_argument(
        "--use-llm",
        action="store_true",
        help=(
            "启用 LLM 语义补全模式（需配置相应的 API key 环境变量，"
            "参见 contextmind/infra/llm_client.py LLMConfig.from_env() 文档）。"
            "使用大模型对以下字段进行语义补全："
            "active_intent、requested_slots、USER actions、service_call params。"
        ),
    )
    parser.add_argument(
        "--inspect",
        action="store_true",
        help="打印第一条转换结果到控制台，不写入文件",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="日志级别（默认: INFO）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="[%(asctime)s] %(levelname)s %(name)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    print(f"\n{'='*60}")
    print("chat_test_100.json → SGD 格式转换器")
    print(f"{'='*60}")
    print(f"输入文件 : {args.input}")
    print(f"输出目录 : {args.output}")
    if args.limit:
        print(f"记录限制 : 前 {args.limit} 条")
    else:
        print("记录限制 : 全部")
    print(f"LLM 模式 : {'✅ 启用' if args.use_llm else '❌ 未启用（规则模式）'}")
    print(f"{'='*60}\n")

    # 可选：初始化 LLM 补全器
    llm_enricher = None
    if args.use_llm:
        try:
            from benchmark.datasets.anyihua.llm_enricher import LLMEnricher
            llm_enricher = LLMEnricher.from_env()
            print("✅ LLM 客户端初始化成功\n")
        except Exception as exc:
            print(f"⚠️  LLM 客户端初始化失败，退回规则模式: {exc}\n")
            llm_enricher = None

    converter = ChatTestToSGDConverter(llm_enricher=llm_enricher)
    schema = converter.build_schema()

    print("▶ 正在转换对话数据...")
    dialogues = converter.convert(
        input_path=args.input,
        limit=args.limit,
    )
    print(f"  ✅ 转换完成：{len(dialogues)} 条对话")

    if args.inspect:
        print("\n🔍 检查模式：打印第一条转换结果")
        if dialogues:
            first = dialogues[0]
            print(f"\ndialogue_id: {first['dialogue_id']}")
            print(f"services: {first['services']}")
            print(f"turns ({len(first['turns'])} 个):")
            for i, turn in enumerate(first["turns"][:6]):
                frame = turn["frames"][0] if turn["frames"] else {}
                state = frame.get("state", {})
                print(
                    f"  [{i:2d}] {turn['speaker']:6s}: "
                    f"{turn['utterance'][:60]}"
                )
                if turn["speaker"] == "USER":
                    print(
                        f"         intent={state.get('active_intent', '?'):30s} "
                        f"requested={state.get('requested_slots', [])} "
                        f"slots={list(state.get('slot_values', {}).keys())}"
                    )
                else:
                    actions = frame.get("actions", [])
                    sc = frame.get("service_call", {})
                    print(
                        f"         actions={[a['act'] for a in actions]} "
                        f"service_call={sc.get('method', '-')}"
                    )
            if "metadata" in first:
                meta = first["metadata"]
                print(f"\nmetadata.qc_label: {meta.get('qc_label')}")
                print(f"metadata.reference_response: {meta.get('reference_response', '')[:80]}")
        else:
            print("  ❌ 无转换结果")
        return

    print(f"\n▶ 正在写入 SGD 文件到 {args.output} ...")
    summary = converter.save(
        dialogues=dialogues,
        schema=schema,
        output_dir=args.output,
        dialogues_per_file=args.dialogues_per_file,
    )

    print(f"\n{'='*60}")
    print("转换完成汇总")
    print(f"{'='*60}")
    print(f"  对话数量   : {summary['dialogues']}")
    print(f"  总轮次数   : {summary['turns']}")
    print(f"  服务数量   : {summary['services']}")
    print(f"  对话文件数 : {summary['dialogue_files']}")
    print(f"\n  输出目录   : {summary['output_dir']}")
    print(f"    ├── schema.json")
    for i in range(1, summary["dialogue_files"] + 1):
        print(f"    ├── dialogues_{i:03d}.json")
    print(f"    └── conversion_summary.json")
    print(f"\n📄 汇总报告已写入: {summary['output_dir']}/conversion_summary.json")


if __name__ == "__main__":
    main()
