"""
step1_build_kb.py — 通用知识库构建（第一步）

从任意对话数据 → SGD schema.json，供第二/三步使用。
支持多种输入格式（chat_test、SGD turns、文本列表等），自动归一化。

用法:
    python examples/step1_build_kb.py --data resources/data/chat_test_100.json --num 5 --scene "安逸花外呼"
    python examples/step1_build_kb.py --data file1.json file2.json --num 20 --scene "银行贷款外呼"
    python examples/step1_build_kb.py --demo
    python examples/step1_build_kb.py --data ... --workers 4 --verbose

输出目录（默认 output/kb_output/）:
    schema.json             服务 schema（槽位 + 意图）
    dialogues_001.json      SGD 格式标注对话
    discovery_raw.json      逐轮原始提取结果
    conversion_summary.json 转换摘要
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, List

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.knowledge import KnowledgeBaseBuilder
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# 内嵌演示对话（无需外部文件，--demo 模式使用）
# ------------------------------------------------------------------

_DEMO_DIALOGUES: List[Any] = [
    # 格式 1：平铺文本
    (
        "机器人：你好，请问是李先生吗？\n"
        "用户：是的，我是李明。\n"
        "机器人：李先生您好，我是某某银行客服，请问您手机尾号是 6789 吗？\n"
        "用户：是的，没错。\n"
        "机器人：好的，已核实您的身份。您目前有 50000 元的可用额度，年化利率 12%。\n"
        "用户：哦，那月供多少？\n"
        "机器人：如果借 5 万元分 12 期，每月还款约 4431 元。\n"
        "用户：感觉利率有点高。\n"
        "机器人：理解您的顾虑，这是市场参考价，具体还可以根据您的资质调整。\n"
        "用户：好吧，我再想想。"
    ),
    # 格式 2：列表格式（agent:/user: 前缀）
    [
        "agent: 您好，请问是王女士吗？",
        "user: 是的，我是王丽。",
        "agent: 王女士，请问您手机尾号是 1234 吗？",
        "user: 对的。",
        "agent: 好的，您的信用额度是 30000 元，可以申请 1 万到 3 万之间的贷款。",
        "user: 那利息怎么算的？",
        "agent: 日利率 0.03%，年化约 10.95%，12 期月供约 885 元每万元。",
        "user: 感觉还可以，我考虑一下。",
    ],
    # 格式 3：dict（chat_test 格式，含 "对话历史"）
    {
        "session_id": "demo_003",
        "对话历史": [
            {"机器人": "您好，我是某某银行贷款客服，请问是张先生吗？", "用户": "是我，有什么事？"},
            {"机器人": "张先生，您账户有 20000 元额度到期未使用，特来提醒。", "用户": "我最近不需要借款。"},
            {"机器人": "理解，那我们记录一下您的意见，再次打扰请见谅。", "用户": "好的，再见。"},
        ],
    },
    # 格式 4：dict（SGD turns 格式）
    {
        "dialogue_id": "demo_004",
        "services": ["BankLoan"],
        "turns": [
            {"speaker": "SYSTEM", "utterance": "您好，请问是赵女士吗？"},
            {"speaker": "USER", "utterance": "是的。"},
            {"speaker": "SYSTEM", "utterance": "赵女士，您有 8000 元可用额度，是否需要了解贷款详情？"},
            {"speaker": "USER", "utterance": "这个额度有点低，能提高吗？"},
            {"speaker": "SYSTEM", "utterance": "您目前的额度是根据信用评分确定的，暂时无法调整，后续会持续优化。"},
            {"speaker": "USER", "utterance": "好吧，那就算了，谢谢。"},
        ],
    },
]


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="通用知识库构建演示 — 任意对话数据 → 完整 SGD 数据集",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--data",
        type=str,
        nargs="+",
        default=None,
        metavar="PATH",
        help=(
            "输入对话 JSON 文件路径，可同时指定多个（空格分隔）；"
            "支持 chat_test_100/500 格式、SGD turns 格式等，格式自动识别"
        ),
    )
    parser.add_argument("--num", type=int, default=10, help="使用对话条数（0 = 全部，默认 10）")
    parser.add_argument("--scene", type=str, default="对话场景", help="业务场景名称")
    parser.add_argument("--scene-desc", type=str, default="", help="场景描述（可选）")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="output/kb_output",
        dest="output_dir",
        help="SGD 数据集输出目录（默认 output/kb_output）；目录不存在时自动创建",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别（默认 INFO）",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用内嵌演示对话（无需 --data）",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        default=3,
        metavar="N",
        help="langextract 逐轮提取时的历史轮次窗口大小（默认 3，0 = 不传历史上下文）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        metavar="N",
        help="发现阶段并行线程数（默认 1；建议 2–8）",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="开启详细输出，将底层阶段日志实时打印到终端",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  ContextMind 知识库构建演示")
    print("  第一步：建立知识库 → 完整 SGD 数据集")
    print("=" * 70)

    # ── 日志设置 ──
    from contextmind.infra.logger import setup_logging, LogLevel
    log_level = LogLevel.DEBUG if args.verbose or args.log_level == "DEBUG" else (
        LogLevel[args.log_level] if hasattr(LogLevel, args.log_level) else LogLevel.INFO
    )
    setup_logging(level=log_level, save_to_file=True, log_dir="log", log_name="step1_build_kb")
    if args.verbose or args.log_level == "DEBUG":
        print("🔍 详细输出模式已开启 — 底层阶段日志（含 LLM 响应等 DEBUG 信息）将实时打印到终端")
        print("   同时将逐步打印每条对话的提取→合并→融合中间结果")
        print()

    # ── 加载对话 ──
    if args.demo or args.data is None:
        if not args.demo and args.data is None:
            print("\n[提示] 未指定 --data，使用内嵌演示对话（--demo 模式）")
        dialogues = _DEMO_DIALOGUES
        scene = args.scene if args.scene != "对话场景" else "银行贷款外呼"
        scene_desc = args.scene_desc or "银行客服主动致电老客户推介个人贷款产品"
        print(f"\n内嵌演示对话：{len(dialogues)} 条（格式多样，涵盖 5 种输入格式）")
    else:
        # 逐个加载文件并合并；normalizer 统一处理所有格式（含 chat_test_500 嵌套格式）
        all_raw: List[Any] = []
        for path_str in args.data:
            data_path = Path(path_str)
            if not data_path.exists():
                print(f"[错误] 文件不存在: {data_path}", file=sys.stderr)
                sys.exit(1)
            file_raw = json.loads(data_path.read_text(encoding="utf-8"))
            if isinstance(file_raw, list):
                all_raw.extend(file_raw)
                n = len(file_raw)
            elif isinstance(file_raw, dict):
                all_raw.append(file_raw)
                n = 1
            else:
                print(
                    f"[错误] 无法识别的 JSON 格式: {data_path.name} ({type(file_raw).__name__})",
                    file=sys.stderr,
                )
                sys.exit(1)
            print(f"\n加载对话文件: {data_path.name} ({n} 条)")

        dialogues = all_raw[: args.num] if args.num > 0 else all_raw
        scene = args.scene
        scene_desc = args.scene_desc
        src_names = ", ".join(Path(p).name for p in args.data)
        print(
            f"\n合并后共 {len(all_raw)} 条，本次使用前 {len(dialogues)} 条"
            f"  [来源: {src_names}]"
        )

    print(f"场景名称: {scene}")
    print(f"场景描述: {scene_desc or '（未提供）'}")
    print(f"输出目录: {args.output_dir}")
    print(f"历史窗口: {args.context_window} 轮")
    print(f"并行线程: {args.workers}")

    # ── 构建知识库 ──
    print("\n" + "─" * 70)
    print("▶ 初始化 KnowledgeBaseBuilder …")
    builder = KnowledgeBaseBuilder(
        scene_name=scene,
        scene_description=scene_desc,
        context_window=args.context_window,
        workers=args.workers,
        verbose=args.verbose,
    )

    print("▶ 执行知识库构建（生成完整 SGD 数据集）…")
    print("  流程：提取 → 合并 → 融合（增量方式）")
    print("  Phase 1 — 提取阶段：LLM + langextract 逐轮提取槽位和意图（含溯源）")
    print("  Phase 2 — 合并阶段：LLM 将发现结果合成为规范 SGD Schema（自动输出数量信息）")
    print("  Phase 3 — 融合阶段：精炼去重，消除跨对话产生的相似/重复条目（自动输出精炼前后数量）")
    print("  Phase 4 — 转换阶段：将对话转换为 SGD 格式对话文件")
    if args.verbose:
        print("  （--verbose 模式：将逐步打印每条对话的槽位/意图名称明细）")
    print()

    try:
        dataset = builder.build_dataset(dialogues)
    except Exception as exc:
        print(f"[错误] 知识库构建失败: {exc}", file=sys.stderr)
        raise

    schema_dict = dataset["schema"]
    sgd_dialogues = dataset["dialogues"]

    # ── 保存数据集 ──
    output_dir = Path(args.output_dir)
    builder.save_dataset(dataset, output_dir)

    # ── 展示结果 ──
    print("\n" + "─" * 70)
    print("✓ 知识库构建完成！")
    print(f"\n服务名称: {schema_dict.get('service_name', '(未知)')}")
    print(f"服务描述: {schema_dict.get('description', '(未知)')}")
    print()

    slots = schema_dict.get("slots", [])
    intents = schema_dict.get("intents", [])
    print(f"槽位（slots）共 {len(slots)} 个：")
    for s in slots:
        categorical = "（枚举型）" if s.get("is_categorical") else ""
        possible = ""
        if s.get("is_categorical") and s.get("possible_values"):
            possible = f" 可选值: {s['possible_values']}"
        print(f"  - {s.get('name', '<unnamed>')}: {s.get('description', '')}{categorical}{possible}")

    print(f"\n意图（intents）共 {len(intents)} 个：")
    for it in intents:
        trans = "（事务型）" if it.get("is_transactional") else ""
        print(f"  - {it.get('name', '<unnamed>')}: {it.get('description', '')}{trans}")
        if it.get("required_slots"):
            print(f"    必填槽位: {it['required_slots']}")
        if it.get("optional_slots"):
            print(f"    可选槽位: {it['optional_slots']}")

    print(f"\n发现统计（发现阶段 raw 数据）：")
    slot_all = builder.last_slot_counter.most_common()
    intent_all = builder.last_intent_counter.most_common()
    print(f"  槽位（共 {len(slot_all)} 个，按出现次数降序）：")
    for _name, _cnt in slot_all:
        print(f"    · {_name}: {_cnt} 次")
    if not slot_all:
        print("    （无）")
    print(f"  意图（共 {len(intent_all)} 个，按出现次数降序）：")
    for _name, _cnt in intent_all:
        print(f"    · {_name}: {_cnt} 次")
    if not intent_all:
        print("    （无）")

    total_turns = sum(len(d.get("turns", [])) for d in sgd_dialogues)
    print(f"\nSGD 对话文件统计：")
    print(f"  对话数: {len(sgd_dialogues)}")
    print(f"  总轮次: {total_turns}")

    print(f"\n✓ SGD 数据集已保存至: {output_dir.resolve()}")
    print(f"  ├── schema.json           (服务 schema)")
    print(f"  ├── dialogues_001.json    (SGD 格式对话，{len(sgd_dialogues)} 条)")
    print(f"  ├── discovery_raw.json    (逐轮原始提取结果，含 langextract 字符级溯源)")
    print(f"  └── conversion_summary.json")
    print("─" * 70)
    print()


if __name__ == "__main__":
    main()
