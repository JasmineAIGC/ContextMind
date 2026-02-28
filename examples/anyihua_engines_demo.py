"""
安逸花外呼场景 · PyTOD 两个任务的执行引擎演示

本脚本演示两个任务各自的执行引擎设计：

  任务一 (QC)：build_qc_engine()
    注册 5 个质量标签检测 API，直接对应 5 个质量标签类别。
    用于离线标签预测（predict_label_pytod）和 LLM hint 注入（classify_session_llm）。

  任务二 (Generation)：build_generation_engine()
    注册 5 个 CRM 数据查询 API（query_account、get_agent_history 等）。
    动作解析器（LLM）可基于 ANYIHUA_SCHEMA 生成 PyTOD 程序调用这些 API，
    对话管理器再基于真实数据生成坐席回复。

两个引擎完全独立，目的不同、数据不同，不可混用。

用法（无需 LLM，完全离线）:
    cd /path/to/ContextMind
    python examples/anyihua_engines_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.scenarios.anyihua.qc import build_qc_engine, predict_label_pytod
from contextmind.scenarios.anyihua.generation import build_generation_engine

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_data = json.loads(_DATA_PATH.read_text(encoding="utf-8"))


def _hr(title: str = "") -> None:
    """Print a horizontal rule with an optional centered title."""
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("\n" + "─" * width)


def demo_qc_engine() -> None:
    """演示 QC 任务引擎：5 个标签检测 API。"""
    _hr("任务一（QC）：build_qc_engine() 演示")
    session = _data[10]
    engine = build_qc_engine(session)

    print(f"注册的 API：{engine.list_functions()}\n")

    for api_name in engine.list_functions():
        r = engine.registry[api_name]()
        status = "✅ 检出" if r["detected"] and r["label"] else "  未检出"
        label = r["label"] or "(无)"
        conf = f"{r['confidence']:.0%}" if r["confidence"] > 0 else "—"
        print(f"  {status}  {api_name:35s}  label={label}  confidence={conf}")

    _hr("execute_program 演示")
    result = engine.execute_program("""
x1 predict_data_error()
x2 predict_repetition()
x3 predict_improper_farewell()
x4 predict_off_topic()
x5 say(x3)
""")
    print(f"success: {result.success}")
    print(f"x3 (不当告别): detected={result.variable_values.get('x3', {}).get('detected')}")

    _hr("predict_label_pytod() 在 100 条数据集上的表现")
    total, predicted, correct = len(_data), 0, 0
    for s in _data:
        label, conf, _ = predict_label_pytod(s)
        if label is not None:
            predicted += 1
            correct += (label == s.get("人工校验", ""))
    print(f"  规则预测覆盖: {predicted}/{total} ({predicted/total:.0%})")
    if predicted > 0:
        print(f"  规则预测精度: {correct}/{predicted} ({correct/predicted:.0%})")
    # 总体准确率：规则未覆盖的会话以"无标签命中"兜底
    overall_correct = correct
    for s in _data:
        label, _, _ = predict_label_pytod(s)
        if label is None and s.get("人工校验", "") == "无标签命中":
            overall_correct += 1
    print(f"  规则总体准确率（含兜底）: {overall_correct}/{total} ({overall_correct/total:.0%})")


def demo_generation_engine() -> None:
    """演示 Generation 任务引擎：5 个 CRM 数据查询 API。"""
    _hr("任务二（Generation）：build_generation_engine() 演示")
    session = _data[10]
    engine = build_generation_engine(session)

    print(f"注册的 API：{engine.list_functions()}\n")

    # query_account
    acct = engine.registry["query_account"]()
    print(f"  query_account():")
    print(f"    客户: {acct['customer_name']}")
    print(f"    可提现额度: {acct['available_credit']:,}元")
    print(f"    年化利率: {acct['annual_rate_pct']}%")

    # calculate_repayment
    rep = engine.registry["calculate_repayment"](amount=20000, months=12)
    print(f"\n  calculate_repayment(amount=20000, months=12):")
    print(f"    月还款额: {rep['monthly_payment']:,}元")
    print(f"    总手续费: {rep['total_interest']:,}元")

    # get_agent_history
    hist = engine.registry["get_agent_history"]()
    print(f"\n  get_agent_history():")
    print(f"    历史坐席话术条数: {hist['turn_count']}")
    if hist["agent_turns"]:
        print(f"    最后一条: {hist['agent_turns'][-1][:40]}…")

    # query_unresolved_issues
    issues = engine.registry["query_unresolved_issues"]()
    print(f"\n  query_unresolved_issues():")
    print(f"    未解决诉求数: {issues['issue_count']}")

    _hr("execute_program 演示（模拟动作解析器生成的 PyTOD 程序）")
    result = engine.execute_program("""
x1 query_account()
x2 calculate_repayment()
x3 query_unresolved_issues()
x4 say(x1)
""")
    print(f"success: {result.success}")
    print(f"x1 (账户信息): available_credit={result.variable_values.get('x1', {}).get('available_credit')}")


def main() -> None:
    """Print a banner and run both engine demos."""
    print("=" * 72)
    print("  安逸花外呼场景 · PyTOD 双引擎演示（零 LLM 调用）")
    print(f"  数据: {_DATA_PATH.name}（{len(_data)} 条会话）")
    print("=" * 72)

    demo_qc_engine()
    demo_generation_engine()

    _hr()
    print("\n更多阅读:")
    print("  任务一 QC 引擎:        contextmind/scenarios/anyihua/qc/")
    print("  任务二 Generation 引擎: contextmind/scenarios/anyihua/generation/")
    print("  任务一入口:            examples/anyihua_qc_demo.py")
    print("  任务二入口:            examples/anyihua_generation_demo.py")


if __name__ == "__main__":
    main()
