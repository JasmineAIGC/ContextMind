"""
通用知识库构建演示（build_kb_demo.py）

演示 ContextMind 框架的第一步：**建立知识库**。

核心思路
--------
1. 提供任意对话数据（可以是安逸花外呼、银行贷款、电商客服等任意场景）
2. KnowledgeBaseBuilder 自动完成：
   - 对话格式归一化（支持 chat_test / SGD / 文本列表等多种格式）
   - 发现阶段：LLM 开放式提取槽位和意图
   - 合成阶段：LLM 将发现结果整理为规范 SGD ServiceSchema
3. 输出 schema.json，可直接供 PyTOD 等执行算法使用

两步走
------
    第一步（本 Demo）：建立知识库 → schema.json
    第二步（pytod_trace_demo.py）：执行 → 使用 schema.json 驱动对话

支持的输入格式
--------------
    - chat_test 格式（JSON，含 "对话历史" 字段）
    - SGD 格式（JSON，含 "turns" 字段）
    - 简单文本列表（["agent: ...", "user: ..."]）
    - 平铺文本（"坐席：...\\n用户：..."）

运行示例
--------
    # 使用安逸花外呼数据（快速测试，仅用前 5 条对话）
    python examples/build_kb_demo.py \\
        --data resources/data/chat_test_100.json \\
        --num 5 \\
        --scene "安逸花外呼" \\
        --scene-desc "安逸花/马上消费金融外呼促活服务，核实身份→告知额度→解答疑问→引导借款"

    # 使用任意 JSON 文件（SGD turns 格式）
    python examples/build_kb_demo.py \\
        --data my_dialogues.json \\
        --num 10 \\
        --scene "银行贷款外呼" \\
        --scene-desc "银行客服主动致电老客户推介个人贷款产品" \\
        --output data/bank_loan_kb/schema.json

    # 直接传入内嵌演示对话（无需外部文件）
    python examples/build_kb_demo.py --demo

参数说明
--------
    --data          输入对话 JSON 文件路径
    --num           使用对话条数（发现阶段，默认 10）
    --scene         业务场景名称（默认 "对话场景"）
    --scene-desc    场景描述（可选）
    --output        schema.json 输出路径（默认 data/kb_output/schema.json）
    --demo          使用内嵌演示对话（无需 --data）
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

from contextmind.kb import KnowledgeBaseBuilder
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# 内嵌演示对话（无需外部文件，--demo 模式使用）
# ------------------------------------------------------------------

_DEMO_DIALOGUES: List[Any] = [
    # 格式 1：平铺文本（换行分隔）
    (
        "坐席：你好，请问是李先生吗？\n"
        "用户：是的，我是李明。\n"
        "坐席：李先生您好，我是某某银行客服小王，请问您手机尾号是 6789 吗？\n"
        "用户：是的，没错。\n"
        "坐席：好的，已核实您的身份。您目前有 50000 元的可用额度，年化利率 12%。\n"
        "用户：哦，那月供多少？\n"
        "坐席：如果借 5 万元分 12 期，每月还款约 4431 元。\n"
        "用户：感觉利率有点高。\n"
        "坐席：理解您的顾虑，这是市场参考价，具体还可以根据您的资质调整。\n"
        "用户：好吧，我再想想。\n"
        "坐席：好的，祝您生活愉快，再见。"
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
        "agent: 好的，随时欢迎联系，再见。",
    ],
    # 格式 3：dict（chat_test 格式，含 "对话历史"）
    {
        "session_id": "demo_003",
        "对话历史": [
            "坐席：您好，我是某某银行贷款客服，请问是张先生吗？",
            "用户：是我，有什么事？",
            "坐席：张先生，您账户有 20000 元额度到期未使用，特来提醒。",
            "用户：我最近不需要借款。",
            "坐席：理解，那我们记录一下您的意见，再次打扰请见谅。",
            "用户：好的，再见。",
            "坐席：再见，祝您生活愉快。",
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
            {"speaker": "SYSTEM", "utterance": "不客气，再见。"},
        ],
    },
]


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="通用知识库构建演示 — 任意对话数据 → SGD schema.json",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--data", type=str, default=None, help="输入对话 JSON 文件路径")
    parser.add_argument("--num", type=int, default=10, help="使用对话条数（默认 10）")
    parser.add_argument("--scene", type=str, default="对话场景", help="业务场景名称")
    parser.add_argument("--scene-desc", type=str, default="", help="场景描述（可选）")
    parser.add_argument(
        "--output",
        type=str,
        default="data/kb_output/schema.json",
        help="schema.json 输出路径",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="使用内嵌演示对话（无需 --data）",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  ContextMind 知识库构建演示")
    print("  第一步：建立知识库 → SGD schema.json")
    print("=" * 70)

    # ── 加载对话 ──
    if args.demo or args.data is None:
        if not args.demo and args.data is None:
            print("\n[提示] 未指定 --data，使用内嵌演示对话（--demo 模式）")
        dialogues = _DEMO_DIALOGUES
        scene = args.scene if args.scene != "对话场景" else "银行贷款外呼"
        scene_desc = args.scene_desc or "银行客服主动致电老客户推介个人贷款产品"
        print(f"\n内嵌演示对话：{len(dialogues)} 条（格式多样，涵盖 4 种输入格式）")
    else:
        data_path = Path(args.data)
        if not data_path.exists():
            print(f"[错误] 文件不存在: {data_path}", file=sys.stderr)
            sys.exit(1)
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        # JSON 文件可能是列表或字典
        if isinstance(raw, list):
            dialogues = raw[: args.num] if args.num > 0 else raw
        elif isinstance(raw, dict):
            dialogues = [raw]
        else:
            print(f"[错误] 无法识别的 JSON 格式: {type(raw)}", file=sys.stderr)
            sys.exit(1)
        scene = args.scene
        scene_desc = args.scene_desc
        print(f"\n加载对话文件: {data_path.name}，使用前 {len(dialogues)} 条")

    print(f"场景名称: {scene}")
    print(f"场景描述: {scene_desc or '（未提供）'}")
    print(f"输出路径: {args.output}")

    # ── 构建知识库 ──
    print("\n" + "─" * 70)
    print("▶ 初始化 KnowledgeBaseBuilder …")
    builder = KnowledgeBaseBuilder(
        scene_name=scene,
        scene_description=scene_desc,
        discovery_sample=args.num,
    )

    print("▶ 执行两阶段知识库构建 …")
    print("  Phase 1 — 发现阶段：LLM 开放式提取槽位和意图")
    print("  Phase 2 — 合成阶段：LLM 将发现结果合成为规范 SGD Schema")
    print()

    try:
        schema_dict = builder.build(dialogues)
    except Exception as exc:
        print(f"[错误] 知识库构建失败: {exc}", file=sys.stderr)
        raise

    # ── 保存 schema.json ──
    output_path = Path(args.output)
    builder.save(schema_dict, output_path)

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
        print(f"  - {s['name']}: {s.get('description', '')}{categorical}{possible}")

    print(f"\n意图（intents）共 {len(intents)} 个：")
    for it in intents:
        trans = "（事务型）" if it.get("is_transactional") else ""
        print(f"  - {it['name']}: {it.get('description', '')}{trans}")
        if it.get("required_slots"):
            print(f"    必填槽位: {it['required_slots']}")
        if it.get("optional_slots"):
            print(f"    可选槽位: {it['optional_slots']}")

    print(f"\n发现统计（发现阶段 raw 数据）：")
    print(f"  Top-10 槽位: {builder.last_slot_counter.most_common(10)}")
    print(f"  Top-10 意图: {builder.last_intent_counter.most_common(10)}")

    print(f"\n✓ schema.json 已保存至: {output_path.resolve()}")
    print("─" * 70)
    print()
    print("下一步：使用此 schema.json 运行 PyTOD 对话：")
    print("  from contextmind.modes.pytod import AdkPyTODTracker, ServiceSchema")
    print(f"  schema = ServiceSchema.from_json(open('{output_path}').read())[0]")
    print("  tracker = AdkPyTODTracker(engine=engine, schema=schema)")
    print()


if __name__ == "__main__":
    main()
