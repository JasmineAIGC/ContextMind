"""
ContextPipeline 演示脚本（context_pipeline_demo.py）

展示 ContextMind 统一上下文工程流水线（ContextPipeline）的完整用法（三步框架）：

    第一步（Phase 1）：建立知识库 — 任意对话数据 → SGD schema.json
                       统一使用 examples/build_kb.py
    第二步（Phase 2）：Schema 数据生成 — schema.json → 算法专用数据（PyTOD 可选）
    第三步（Phase 3）：算法执行 — 基于 SGD 知识库，使用 5 种算法提取有效上下文

三步框架
--------
Phase 1（build_kb.py）输出：
    schema.json         服务 schema（槽位 + 意图）
    dialogues_001.json  SGD 格式标注对话
    discovery_raw.json  逐轮原始提取结果

Phase 2（build_schema_data.py，可选）：
    xxx_pytod_apis.py   PyTOD API 代码文件（仅 PyTOD 需要）

Phase 3（本脚本）支持五种算法：

    算法      schema.json              适用场景
    ------    -----------------------  ----------------------------------------
    pytod     必须                     任务型对话（AP→EE→DM 三步流程）[默认]
    fnctod    必须                     ADK 原生函数调用对话状态追踪
    dst       可选                     通用槽位提取（无 schema 也可运行）
    evolve    不需要                   演化式上下文优化（会话记忆 + 长期记忆）
    genie     schema 或 worksheet      Genie Worksheets 声明式策略执行

本脚本提供三种运行模式：

    1. --demo-kb    仅演示 Phase 1（知识库构建）
    2. --demo-exec  仅演示 Phase 3（从已保存 schema 加载，运行对话）
    3. 默认         端到端演示（Phase 1 + Phase 3，跳过可选的 Phase 2）

运行示例
--------

    # 端到端演示（Phase 1 + Phase 3，默认 pytod 模式）：
    python examples/context_pipeline_demo.py

    # 仅测试知识库构建：
    python examples/context_pipeline_demo.py --demo-kb

    # 从已有 schema.json 加载并演示对话（pytod 模式）：
    python examples/context_pipeline_demo.py --demo-exec --schema data/kb_output/schema.json

    # 使用 fnctod 模式（需要 schema）：
    python examples/context_pipeline_demo.py --demo-exec --schema data/kb_output/schema.json --mode fnctod

    # 使用 dst 模式（schema 可选，不指定 schema 也可直接运行）：
    python examples/context_pipeline_demo.py --demo-exec --mode dst

    # 使用 evolve 模式（不需要 schema）：
    python examples/context_pipeline_demo.py --demo-exec --mode evolve

    # 使用 genie 模式（通过 Worksheet CSV 驱动，不需要 schema.json）：
    python examples/context_pipeline_demo.py --demo-exec --mode genie \\
        --worksheet-path schema/my_service_worksheet.csv

    # 使用 genie 模式（通过已有 schema.json 驱动，自动转换为 GenieSchema）：
    python examples/context_pipeline_demo.py --demo-exec --mode genie \\
        --schema data/kb_output/schema.json

    # 使用 genie 模式并指定目标意图名称：
    python examples/context_pipeline_demo.py --demo-exec --mode genie \\
        --worksheet-path schema/my_service_worksheet.csv \\
        --genie-intent search_restaurant

    # 指定场景和数据文件：
    python examples/context_pipeline_demo.py \\
        --data resources/data/chat_test_100.json \\
        --num 5 \\
        --scene "安逸花外呼" \\
        --mode pytod

架构说明
--------

ContextPipeline 整合了三步框架：
    Phase 1 — contextmind.knowledge.KnowledgeBaseBuilder（知识发现 + 合成）
    Phase 2 — contextmind.schema_builder.SchemaDataBuilder（Schema → 算法专用数据，可选）
    Phase 3 — 五种算法（均通过 ContextPipeline 统一调度）：
               pytod   : contextmind.modes.pytod.AdkPyTODTracker
               fnctod  : contextmind.modes.fnctod.FnCTODTracker
               dst     : contextmind.modes.dst.DialogueStateTracker
               evolve  : contextmind.modes.evolve.EvolveEngine
               genie   : contextmind.modes.genie.GenieTracker

用户只需与 ContextPipeline 交互，无需了解底层算法细节。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from contextmind.pipeline import ContextPipeline
from contextmind.infra.llm_client import AdkLLMClient, LLMConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

# ------------------------------------------------------------------
# 内嵌演示对话（无需外部文件）
# ------------------------------------------------------------------

_DEMO_DIALOGUES: List[Any] = [
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
        "用户：好吧，我再想想。\n"
        "机器人：好的，祝您生活愉快，再见。"
    ),
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
    {
        "session_id": "demo_003",
        "对话历史": [
            {"机器人": "您好，我是某某银行贷款客服，请问是张先生吗？", "用户": "是我，有什么事？"},
            {"机器人": "张先生，您账户有 20000 元额度到期未使用，特来提醒。", "用户": "我最近不需要借款。"},
            {"机器人": "理解，那我们记录一下您的意见，再次打扰请见谅。", "用户": "好的，再见。"},
            {"机器人": "再见，祝您生活愉快。"},
        ],
    },
]

# 演示对话轮次（Phase 2 演示时使用）
# 每条为 (系统发起语, 用户回复语) 二元组，体现客服场景的正确对话结构：
#   系统发起 → 用户回答 → 意图预测 + 语言回复
_DEMO_TURNS = [
    (
        "您好，我是某某银行贷款客服，请问是李明先生吗？",
        "是的，我是李明，想了解一下贷款情况",
    ),
    (
        "李明先生您好！请问您手机尾号是 6789 吗？",
        "是的，尾号是 6789",
    ),
    (
        "好的，身份已核实。请问您想了解哪方面的贷款信息？",
        "我想知道我的可用额度是多少",
    ),
    (
        "您目前可用额度为 5 万元。请问您打算借多久？",
        "如果分 12 期，月供大概是多少？",
    ),
    (
        "如果借 5 万元分 12 期，每月还款约 4431 元，年化利率 12%。请问您有意向申请吗？",
        "好的，我考虑一下，谢谢",
    ),
]


# ------------------------------------------------------------------
# Phase 1 演示
# ------------------------------------------------------------------


def demo_phase1(
    pipeline: ContextPipeline,
    dialogues: List[Any],
    save_path: str,
) -> Dict[str, Any]:
    """演示 Phase 1：知识库构建。"""
    print("\n" + "─" * 65)
    print("▶ Phase 1：知识库构建（任意对话 → SGD schema.json）")
    print("  流程：归一化 → LLM 发现槽位/意图 → LLM 合成 SGD Schema")
    print("─" * 65)

    schema_dict = pipeline.build_kb(
        dialogues=dialogues,
        save_path=save_path,
    )

    print(f"\n✓ 知识库构建完成！")
    print(f"\n服务名称: {schema_dict.get('service_name', '(未知)')}")
    print(f"服务描述: {schema_dict.get('description', '(未知)')}")

    slots = schema_dict.get("slots", [])
    intents = schema_dict.get("intents", [])
    print(f"\n槽位（slots）共 {len(slots)} 个：")
    for s in slots:
        categorical = "（枚举型）" if s.get("is_categorical") else ""
        print(f"  - {s['name']}: {s.get('description', '')}{categorical}")

    print(f"\n意图（intents）共 {len(intents)} 个：")
    for it in intents:
        trans = "（事务型）" if it.get("is_transactional") else ""
        print(f"  - {it['name']}: {it.get('description', '')}{trans}")

    # 显示发现统计
    summary = pipeline.last_build_summary
    if summary.get("top_slots"):
        print(f"\n发现统计（Top-5 槽位）: {[s for s, _ in summary['top_slots']]}")
    if summary.get("top_intents"):
        print(f"发现统计（Top-5 意图）: {[i for i, _ in summary['top_intents']]}")

    if save_path:
        print(f"\n✓ schema.json 已保存至: {Path(save_path).resolve()}")

    return schema_dict


# ------------------------------------------------------------------
# Phase 2 演示
# ------------------------------------------------------------------


async def demo_phase2(pipeline: ContextPipeline, turns: List[Any]) -> None:
    """演示 Phase 2：对话上下文提取。"""
    print("\n" + "─" * 65)
    print("▶ Phase 2：对话上下文提取（基于 SGD 知识库，逐轮提取有效上下文）")
    print(f"  模式: {pipeline.mode.upper()}")
    _mode_desc = {
        "pytod":  "PyTOD AP→EE→DM 三步流程（需要 schema）",
        "fnctod": "ADK 原生函数调用（需要 schema）",
        "dst":    "对话状态追踪，纯槽位提取（schema 可选）",
        "evolve": "演化式上下文优化，会话记忆 + 长期记忆（不需要 schema）",
        "genie":  "Genie Worksheets 声明式策略执行（需要 schema 或 worksheet_path）",
    }
    print(f"  说明: {_mode_desc.get(pipeline.mode, pipeline.mode)}")
    print("─" * 65)

    # 显示 schema 摘要
    if pipeline.schema:
        print(f"\n已加载 Schema: {pipeline.schema.service_name}")
        print(f"  槽位: {pipeline.schema.get_slot_names()}")
        print(f"  意图: {pipeline.schema.get_intent_names()}")

    print(f"\n开始对话（{len(turns)} 轮）：\n")

    for i, turn in enumerate(turns, 1):
        # 支持 (系统发起语, 用户回复) 二元组和纯字符串两种格式
        if isinstance(turn, (list, tuple)) and len(turn) == 2:
            system_utterance, user_input = turn
        else:
            system_utterance, user_input = "", str(turn)

        if system_utterance:
            print(f"[Turn {i}] 系统发起: {system_utterance}")
        print(f"[Turn {i}] 用户回复: {user_input}")

        try:
            result = await pipeline.process_turn(
                user_input, system_utterance=system_utterance
            )

            # 显示系统回复
            response = result.get("response", "(无回复)")
            print(f"         系统回复: {response}")

            # 显示提取的上下文
            context = result.get("context", {})
            if context:
                print(f"         上下文: {context}")

            # PyTOD 模式显示程序文本
            program = result.get("program_text", "")
            if program:
                print(f"         程序: {program}")

            # Genie 模式显示 Worksheet 填写状态
            if pipeline.mode == "genie":
                ws_state = result.get("worksheet_state", {})
                if ws_state:
                    print(f"         Worksheet: {ws_state}")
                next_field = result.get("next_field")
                if next_field:
                    print(f"         下一待填字段: {next_field}")
                print(f"         已完成: {result.get('is_complete', False)}")

        except Exception as e:
            print(f"         [错误] {e}")

        print()

    # 显示累积上下文
    final_ctx = pipeline.get_context()
    if final_ctx:
        print("─" * 65)
        print("✓ 对话结束，累积上下文（提取的全量信息）：")
        for k, v in final_ctx.items():
            print(f"  {k}: {v}")

    print("\n" + pipeline.summary())


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ContextPipeline 演示 — 通用上下文工程流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--data", type=str, default=None, help="输入对话 JSON 文件路径")
    parser.add_argument("--num", type=int, default=10, help="使用对话条数（默认 10）")
    parser.add_argument("--scene", type=str, default="银行贷款外呼", help="业务场景名称")
    parser.add_argument("--scene-desc", type=str, default="", help="场景描述（可选）")
    parser.add_argument("--mode", type=str, default="pytod",
                        choices=["pytod", "fnctod", "dst", "evolve", "genie"],
                        help=(
                            "Phase 2 执行模式（默认 pytod）：\n"
                            "  pytod   — PyTOD 三步流程，需要 schema\n"
                            "  fnctod  — ADK 原生函数调用，需要 schema\n"
                            "  dst     — 对话状态追踪，schema 可选\n"
                            "  evolve  — 演化式上下文优化，不需要 schema\n"
                            "  genie   — Genie Worksheets 声明式策略，需要 schema 或 --worksheet-path"
                        ))
    parser.add_argument("--schema", type=str, default=None,
                        help="已有 schema.json 路径（跳过 Phase 1，直接运行 Phase 2）")
    parser.add_argument("--worksheet-path", type=str, default=None,
                        help="Genie 模式专用：Worksheet 文件路径（.csv 或 .json），"
                             "与 --mode genie 配合使用")
    parser.add_argument("--genie-intent", type=str, default=None,
                        help="Genie 模式专用：指定目标意图名称（默认使用第一个含 policy_fields 的意图）")
    parser.add_argument("--output", type=str, default="data/kb_output/schema.json",
                        help="schema.json 输出路径（默认 data/kb_output/schema.json）")
    parser.add_argument("--demo-kb", action="store_true", help="仅演示 Phase 1（知识库构建）")
    parser.add_argument("--demo-exec", action="store_true", help="仅演示 Phase 2（对话执行）")
    args = parser.parse_args()

    print("=" * 65)
    print("  ContextMind — 上下文工程流水线演示")
    print("  ContextPipeline: Phase 1（建立知识库）+ Phase 2（执行）")
    print("=" * 65)

    # ── 加载对话（Phase 1 需要）──
    if args.data:
        data_path = Path(args.data)
        if not data_path.exists():
            print(f"[错误] 文件不存在: {data_path}", file=sys.stderr)
            sys.exit(1)
        raw = json.loads(data_path.read_text(encoding="utf-8"))
        if isinstance(raw, list):
            dialogues = raw[: args.num] if args.num > 0 else raw
        elif isinstance(raw, dict):
            dialogues = [raw]
        else:
            print(f"[错误] 无法识别的 JSON 格式: {type(raw)}", file=sys.stderr)
            sys.exit(1)
        print(f"\n加载对话文件: {data_path.name}，使用前 {len(dialogues)} 条")
    else:
        dialogues = _DEMO_DIALOGUES
        print(f"\n使用内嵌演示对话（{len(dialogues)} 条，涵盖 3 种输入格式）")

    # ── 初始化 ContextPipeline ──
    print(f"\n初始化 ContextPipeline（模式={args.mode}，场景={args.scene}）...")

    try:
        llm_client = AdkLLMClient(config=LLMConfig.from_env())
        llm_available = True
        print("✓ LLM 客户端初始化成功")
    except Exception:
        llm_client = None
        llm_available = False
        print("⚠️  LLM 未配置，Phase 2 执行将跳过实际 LLM 调用")

    pipeline = ContextPipeline(
        llm_client=llm_client,
        mode=args.mode,
        scene_name=args.scene,
        scene_description=args.scene_desc or "",
        discovery_sample=args.num,
        worksheet_path=args.worksheet_path,
        genie_intent=args.genie_intent,
    )

    # ── Phase 1 ──
    if not args.demo_exec:
        if args.schema:
            # 从已有 schema.json 加载
            print(f"\n跳过 Phase 1，从已有 schema 加载: {args.schema}")
            pipeline.load_kb(args.schema)
        else:
            if not llm_available:
                print(
                    "\n⚠️  LLM 未配置，跳过 Phase 1（知识库构建需要 LLM）。"
                    "\n   若需运行 Phase 1，请在 .env 中配置 LLM_API_KEY。"
                )
            else:
                demo_phase1(pipeline, dialogues, args.output)

    # ── Phase 2 ──
    if not args.demo_kb:
        if pipeline.schema is None and args.schema:
            pipeline.load_kb(args.schema)

        # DST 和 Evolve 不需要 schema，可直接运行；PyTOD 和 FnCTOD 需要 schema；
        # Genie 可通过 worksheet_path 替代 schema
        _schema_optional = args.mode in ("dst", "evolve")
        _genie_ok = args.mode == "genie" and args.worksheet_path is not None
        if pipeline.schema is None and not _schema_optional and not _genie_ok:
            print("\n[提示] Phase 2 需要先完成 Phase 1 或通过 --schema 加载已有 schema。")
            print("       若 LLM 未配置，可使用 --schema data/kb_output/schema.json 运行演示。")
            if args.mode == "genie":
                print("       Genie 模式也可通过 --worksheet-path 直接提供 Worksheet 文件。")
            print(f"       提示：使用 --mode dst 或 --mode evolve 可无需 schema 直接运行。")
        else:
            asyncio.run(demo_phase2(pipeline, _DEMO_TURNS))

    print("\n" + "=" * 65)
    print("  演示结束")
    print("=" * 65)


if __name__ == "__main__":
    main()
