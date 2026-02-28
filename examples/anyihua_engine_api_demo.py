"""
安逸花外呼场景 · PyTOD Engine API 完整演示

本脚本回答以下三个问题（对应问题描述）：
  1. API 是如何定义的？       → 第一部分：手工拆解 @engine.register 机制
  2. API 是如何运行的？       → 第二部分：逐步调用 execute_program()
  3. API 是如何起到作用的？   → 第三部分：在质量标签预测中的实际贡献

【无需 LLM 或任何 API Key】本脚本完全离线运行，所有演示均基于本地数据。

用法:
    cd /path/to/ContextMind
    python examples/anyihua_engine_api_demo.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------------
# 路径设置（使脚本可直接运行，无需 pip install）
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.modes.pytod import ExecutionEngine
from contextmind.scenarios.anyihua.engine import build_anyihua_engine
from contextmind.scenarios.anyihua.utils import parse_user_info

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _hr(title: str = "") -> None:
    """打印分隔线"""
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("\n" + "─" * width)


def _pp(label: str, data: Any) -> None:
    """美化打印一个结果字典"""
    print(f"  ✦ {label}:")
    if isinstance(data, dict):
        for k, v in data.items():
            print(f"      {k}: {v}")
    else:
        print(f"      {data}")


# ---------------------------------------------------------------------------
# 加载一条真实会话数据
# ---------------------------------------------------------------------------

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_data: list = json.loads(_DATA_PATH.read_text(encoding="utf-8"))

# 选择一条含有丰富对话历史的样本（第11条，潘女士，24轮对话）
_SESSION: Dict[str, Any] = _data[10]


# ===========================================================================
# 第一部分：API 是如何定义的？
# ===========================================================================


def part1_api_definition() -> None:
    _hr("第一部分：API 是如何定义的？")
    print("""
PyTOD ExecutionEngine 的 API 注册机制分三步：

  步骤 ①  创建空引擎（空函数注册表 self.registry = {}）
  步骤 ②  用 @engine.register 装饰器把 Python 函数注册进去
  步骤 ③  被注册的函数是「闭包」，它们通过变量捕获持有当前会话数据

以 build_anyihua_engine(session) 为例，其核心伪代码如下：
""")

    print("""\
    engine = ExecutionEngine()          # ① 空引擎
    info   = parse_user_info(session)   # 解析 "用户信息" 字段
    history = session['对话历史']        # 获取对话历史

    @engine.register                    # ② 装饰器注册
    def query_account(customer_name=None):
        # ③ 闭包：捕获 info（来自当前会话的真实 CRM 数据）
        return {'available_credit': info['available_credit'], ...}

    # ... 同样方式注册其余 5 个 API 函数
    return engine
""")

    print("\n实际演示 — 构建引擎并列出已注册的 API：\n")
    engine = build_anyihua_engine(_SESSION)
    print(f"  engine.list_functions() → {engine.list_functions()}")
    print()

    print("  engine.to_prompt_text()（注入 LLM prompt 的函数签名列表）：")
    for line in engine.to_prompt_text().splitlines():
        print(f"    {line}")

    print(f"""
关键点：
  • 每个会话调用一次 build_anyihua_engine()，生成一个独立引擎实例
  • 引擎只包含该会话的 CRM 数据，不同会话互不干扰
  • @engine.register 原理：func.__name__ → engine.registry[name] = func
  • 闭包捕获 info / history，无需传入数据库连接或全局状态
""")


# ===========================================================================
# 第二部分：API 是如何运行的？
# ===========================================================================


def part2_api_execution() -> None:
    _hr("第二部分：API 是如何运行的？")
    print("""
已注册的 API 函数可以通过两种方式调用：

  方式 A（直接调用）：engine.registry['func_name'](**kwargs)
  方式 B（程序调用）：engine.execute_program(program_text)

方式 A 用于纯规则预测（predict_label_pytod）；
方式 B 模拟 PyTOD 论文中的完整"动作解析器 → 执行引擎"流程。
""")

    engine = build_anyihua_engine(_SESSION)
    sid = _SESSION["session_id"][-12:]
    print(f"  会话: {sid}  客户: {parse_user_info(_SESSION['用户信息'])['customer_name']}\n")

    # ── 方式 A：直接调用 ──────────────────────────────────────────────────
    print("【方式 A：直接调用 registry 函数】\n")

    _pp("query_account()", engine.registry["query_account"]())
    print()
    _pp(
        "query_loan_records(target_date='七月二十三')",
        engine.registry["query_loan_records"](target_date="七月二十三"),
    )
    print()
    _pp(
        "calculate_monthly_payment(amount=10000, term_months=12)",
        engine.registry["calculate_monthly_payment"](amount=10000, term_months=12),
    )
    print()
    _pp("check_farewell_preconditions()", engine.registry["check_farewell_preconditions"]())
    print()
    _pp(
        "check_repetition(utterance=<坐席回复前30字>)",
        engine.registry["check_repetition"](
            utterance=_SESSION["坐席回复"].strip()[:30]
        ),
    )
    print()
    _pp(
        "escalate_to_human(issue='客户投诉', priority='高')",
        engine.registry["escalate_to_human"](issue="客户投诉", priority="高"),
    )

    # ── 方式 B：execute_program ───────────────────────────────────────────
    _hr("方式 B：execute_program（PyTOD 论文标准流程）")
    print("""
动作解析器（LLM）生成如下程序文本：

    x1 query_account(customer_name='潘女士')
    x2 check_repetition(utterance='您好，我是安逸花客服')
    x3 say(x1)

执行引擎解析 → 逐行执行 → 收集结果 → 格式化为对话管理器的输入。
""")
    program = """\
x1 query_account(customer_name='潘女士')
x2 check_repetition(utterance='您好，我是安逸花客服')
x3 say(x1)
"""
    print("  程序文本:")
    for line in program.strip().splitlines():
        print(f"    {line}")
    print()

    result = engine.execute_program(program)
    print(f"  result.success          = {result.success}")
    print(f"  result.variable_values  = {{")
    for k, v in result.variable_values.items():
        if k != "x3":  # x3 is say output, shown below
            v_str = str(v)
            v_short = v_str[:80] + ("…" if len(v_str) > 80 else "")
            print(f"      '{k}': {v_short}")
    print("  }")
    say_str = str(result.say_output)
    print(f"  result.say_output[:60]  = {say_str[:60]}…")
    print()
    print("  result.to_context_text()（注入对话管理器 prompt 的格式化文本）：")
    for line in result.to_context_text().splitlines():
        print(f"    {line}")

    print("""
execute_program 执行流程（源码 execution_engine.py）：

  ① parse_program(text)      # 正则 + ast 逐行解析，不 eval 任何代码
  ② 对每条语句分类处理：
       ProgramStatement  → 调用 registry 中对应函数
       SlotAssignment    → 更新已有变量的槽位值
       HintStatement     → 收集需要向用户询问的信息
       SayStatement      → 拼接 x1/x2 等变量输出
  ③ 将所有结果打包到 ProgramExecutionResult 返回
""")


# ===========================================================================
# 第三部分：API 是如何起到作用的？
# ===========================================================================


def part3_api_contribution() -> None:
    _hr("第三部分：API 是如何起到作用的？")
    print("""
6 个 API 各自解决一个具体的质量问题，或提供关键的输入信号：

┌──────────────────────────────────────────────────────────────────────┐
│  API                       作用                    质量标签          │
├──────────────────────────────────────────────────────────────────────┤
│  query_account()           系统真实额度/利率         数据错误 ✓      │
│  query_loan_records()      借款记录核实              数据错误 辅助   │
│  calculate_monthly_payment 月还款计算（防幻觉）      数据错误 辅助   │
│  check_farewell_precond.() 是否满足告别前提          不当告别 ✓      │
│  check_repetition()        历史精确/模糊匹配         重复询问 ✓      │
│  escalate_to_human()       转人工工单（可选动作）     —              │
└──────────────────────────────────────────────────────────────────────┘

下面演示每个 API 在实际质检中的贡献：
""")

    # 选取有"数据错误"标签的会话来演示 query_account
    data_error_session = next(
        (s for s in _data if s.get("人工校验") == "数据错误"), None
    )
    if data_error_session:
        _hr("3A. query_account → 检测数据错误")
        print(f"  会话: {data_error_session['session_id'][-12:]}")
        print(f"  人工标签: {data_error_session['人工校验']}")
        print(f"  坐席回复片段: {data_error_session['坐席回复'][:80]}…\n")
        e = build_anyihua_engine(data_error_session)
        acct = e.registry["query_account"]()
        print(f"  系统真实额度 (available_credit): {acct['available_credit']:,} 元")

        from contextmind.scenarios.anyihua.utils import extract_amounts
        amounts = extract_amounts(data_error_session["坐席回复"])
        if amounts:
            for text, val in amounts:
                diff = abs(val - acct["available_credit"])
                match = diff <= 300
                status = "✅ 一致" if match else "❌ 偏差 > 300 元 → 数据错误"
                print(f"  回复金额「{text}」({val:,}元) vs 系统额度 → {status}")
        else:
            print("  （该回复无可提取金额，数据错误由历史轮次体现）")

    # 选取有"重复询问"标签的会话演示 check_repetition
    rep_session = next(
        (s for s in _data if s.get("人工校验") == "重复询问"), None
    )
    if rep_session:
        _hr("3B. check_repetition → 检测重复询问")
        print(f"  会话: {rep_session['session_id'][-12:]}")
        print(f"  人工标签: {rep_session['人工校验']}")
        e = build_anyihua_engine(rep_session)
        rep = e.registry["check_repetition"](utterance=rep_session["坐席回复"].strip())
        print(f"  坐席回复前40字: {rep_session['坐席回复'].strip()[:40]}…")
        print(f"  is_exact_repeat : {rep['is_exact_repeat']}")
        print(f"  repeat_count    : {rep['repeat_count']}")
        print(f"  max_similarity  : {rep['max_similarity']}")
        print(f"  recommendation  : {rep['recommendation']}")
        if rep["is_exact_repeat"]:
            print("  → 规则直接判断「重复询问」，无需 LLM ✓")

    # 选取有"不当告别"标签的会话演示 check_farewell
    farewell_session = next(
        (s for s in _data if s.get("人工校验") == "不当告别"), None
    )
    if farewell_session:
        _hr("3C. check_farewell_preconditions → 检测不当告别")
        print(f"  会话: {farewell_session['session_id'][-12:]}")
        print(f"  人工标签: {farewell_session['人工校验']}")
        e = build_anyihua_engine(farewell_session)
        fare = e.registry["check_farewell_preconditions"]()
        print(f"  can_farewell      : {fare['can_farewell']}")
        if fare["unresolved_issues"]:
            print(f"  unresolved_issues : {fare['unresolved_issues'][:2]}")
        print(f"  recommendation    : {fare['recommendation']}")
        print("  → 此信号作为 hint 注入 LLM prompt，提升不当告别检测精度")

    _hr("小结：API 贡献对比")
    print("""
  无 PyTOD engine                            有 PyTOD engine
  ─────────────────────────────────────────────────────────
  LLM 只能"猜"额度（幻觉风险高）     query_account() 提供系统真实值
  LLM 依赖对话文本判断是否重复        check_repetition() 字符串精确匹配
  LLM 主观判断是否可告别              check_farewell_preconditions() 结构化诉求扫描
  100% LLM 调用成本                  32% 会话可由规则直接预测（节省 token）
""")


# ===========================================================================
# 主入口
# ===========================================================================


def main() -> None:
    print("=" * 72)
    print("  安逸花外呼场景 · PyTOD engine.py API 完整演示")
    print("  （零 LLM 调用 · 纯本地运行）")
    print("=" * 72)
    print(f"\n  数据文件: {_DATA_PATH.name}  ({len(_data)} 条会话)")

    part1_api_definition()
    part2_api_execution()
    part3_api_contribution()

    _hr()
    print("""
演示完毕。

更多阅读：
  • contextmind/scenarios/anyihua/engine.py    — 6 个 API 的完整实现
  • contextmind/modes/pytod/execution_engine.py — ExecutionEngine 源码
  • docs/analysis/pytod-engine-api-explained.md — 本演示对应的文档说明
  • examples/anyihua_online_demo.py            — 含 LLM 的完整在线生成流程
""")


if __name__ == "__main__":
    main()
