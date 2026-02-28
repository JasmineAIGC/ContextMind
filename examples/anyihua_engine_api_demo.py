"""
安逸花外呼场景 · PyTOD Engine API 完整演示

本脚本回答以下三个问题（对应问题描述）：
  1. API 是如何定义的？       → 第一部分：@engine.register + 闭包机制
  2. API 是如何运行的？       → 第二部分：两种调用路径（直接调用 / execute_program）
  3. API 是如何起到作用的？   → 第三部分：在标签预测中的实际贡献

【API 设计说明】
  engine.py 中注册的 5 个 API 对应安逸花外呼质检的 5 个标签类别：
  - predict_data_error()        → 检测数据错误
  - predict_repetition()        → 检测重复询问
  - predict_improper_farewell() → 检测不当告别
  - predict_off_topic()         → 检测答非所问
  - predict_no_issue()          → 无标签命中（默认）

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

from contextmind.scenarios.anyihua.engine import build_anyihua_engine
from contextmind.scenarios.anyihua.detectors import predict_label_pytod

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


def _hr(title: str = "") -> None:
    """Print a horizontal rule with an optional centered title."""
    width = 72
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─' * pad} {title} {'─' * pad}")
    else:
        print("\n" + "─" * width)


def _pp(label: str, data: Any) -> None:
    """Pretty-print a labeled value or dict."""
    print(f"  ✦ {label}:")
    if isinstance(data, dict):
        for k, v in data.items():
            v_str = str(v)
            if len(v_str) > 80:
                v_str = v_str[:80] + "…"
            print(f"      {k}: {v_str}")
    else:
        print(f"      {data}")


# ---------------------------------------------------------------------------
# 加载真实会话数据
# ---------------------------------------------------------------------------

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_data: list = json.loads(_DATA_PATH.read_text(encoding="utf-8"))
_SESSION: Dict[str, Any] = _data[10]


# ===========================================================================
# 第一部分：API 是如何定义的？
# ===========================================================================


def part1_api_definition() -> None:
    _hr("第一部分：API 是如何定义的？")
    print("""
engine.py 注册的 5 个 API 直接对应 5 个质量标签类别。
每个 API 是一个「闭包」，捕获当前会话的 info（用户信息）和 history（对话历史）。

注册机制（三步）：
  步骤 ①  创建空引擎   ExecutionEngine()
  步骤 ②  解析会话数据 parse_user_info(session["用户信息"]) → info
  步骤 ③  用 @engine.register 装饰器注册 5 个检测 API（闭包捕获 info/history）

核心伪代码：
""")

    print("""\
    engine  = ExecutionEngine()
    info    = parse_user_info(session["用户信息"])
    history = session["对话历史"]
    reply   = session["坐席回复"]

    @engine.register                       # 标签 1：数据错误
    def predict_data_error(customer_name=None):
        # 比较 reply 中的金额 与 info["available_credit"] 的偏差
        ...

    @engine.register                       # 标签 2：重复询问
    def predict_repetition(utterance=None):
        # 将 reply 与 history 中的历史坐席发言做精确/模糊匹配
        ...

    @engine.register                       # 标签 3：不当告别
    def predict_improper_farewell(customer_name=None):
        # 检查 reply 是否含告别词 AND history 是否有用户未解决诉求
        ...

    @engine.register                       # 标签 4：答非所问
    def predict_off_topic(customer_name=None):
        # 检查最后一条用户发言与 reply 的话题是否匹配
        ...

    @engine.register                       # 标签 5：默认标签
    def predict_no_issue(customer_name=None):
        return {"label": "无标签命中", "detected": True, ...}

    return engine
""")

    engine = build_anyihua_engine(_SESSION)
    print(f"  engine.list_functions() → {engine.list_functions()}")
    print()
    print("  engine.to_prompt_text()（供 LLM 动作解析器使用的函数签名列表）：")
    for line in engine.to_prompt_text().splitlines():
        print(f"    {line}")

    print("""
关键点：
  • 5 个 API 直接对应 5 个质量标签 → 引擎目的与任务目标对齐
  • 闭包捕获 info/history：各会话独立，互不干扰
  • 每个 API 返回标准结构：{"label", "detected", "confidence", "evidence", ...}
""")


# ===========================================================================
# 第二部分：API 是如何运行的？
# ===========================================================================


def part2_api_execution() -> None:
    _hr("第二部分：API 是如何运行的？")
    print("""
5 个 API 有两条调用路径：

  路径 A（直接调用）：engine.registry["api_name"](**kwargs)
    → 用于 predict_label_pytod() 纯规则预测

  路径 B（程序调用）：engine.execute_program(program_text)
    → 模拟 PyTOD 论文的「动作解析器 → 执行引擎」完整流程
""")

    engine = build_anyihua_engine(_SESSION)
    from contextmind.scenarios.anyihua.utils import parse_user_info
    info = parse_user_info(_SESSION["用户信息"])
    print(f"  会话 ID: {_SESSION['session_id'][-12:]}  客户: {info['customer_name']}\n")

    # ── 路径 A：直接调用 ──────────────────────────────────────────────────
    print("【路径 A：直接调用 registry 函数】\n")

    for api_name in engine.list_functions():
        r = engine.registry[api_name]()
        status = "✅ 检出" if r["detected"] and r["label"] else "  未检出"
        label = r["label"] or "(无)"
        conf = f"{r['confidence']:.0%}" if r["confidence"] > 0 else "—"
        print(f"  {status}  {api_name:35s} label={label}  confidence={conf}")

    # ── 路径 B：execute_program ───────────────────────────────────────────
    _hr("路径 B：execute_program（PyTOD 完整程序流程）")
    print("""
动作解析器（LLM）生成如下 PyTOD 程序文本，执行引擎逐行解析并调用：
""")

    program = """\
x1 predict_data_error()
x2 predict_repetition()
x3 predict_improper_farewell()
x4 predict_off_topic()
x5 say(x1)
"""
    print("  程序文本:")
    for line in program.strip().splitlines():
        print(f"    {line}")
    print()

    result = engine.execute_program(program)
    print(f"  result.success = {result.success}")
    print()

    for var in ["x1", "x2", "x3", "x4"]:
        val = result.variable_values.get(var, {})
        detected = val.get("detected", False)
        label = val.get("label") or "(未检出)"
        evidence = (val.get("evidence") or "")[:60]
        status = "✅" if detected and val.get("label") else "  "
        print(f"  {status} {var}: label={label}  evidence={evidence}")

    print()
    print("  result.to_context_text()（注入对话管理器 prompt 的格式化文本）：")
    ctx = result.to_context_text()
    for line in ctx.splitlines()[:8]:
        print(f"    {line}")
    if ctx.count("\n") >= 8:
        print("    ...")

    print("""
execute_program 内部流程：
  ① parse_program(text)  → 正则 + ast 逐行解析（不 eval，安全）
  ② 逐条执行：
       ProgramStatement → engine.registry[name](**kwargs)
       SayStatement     → 拼接变量输出
  ③ 打包为 ProgramExecutionResult 返回
""")


# ===========================================================================
# 第三部分：API 是如何起到作用的？
# ===========================================================================


def part3_api_contribution() -> None:
    _hr("第三部分：API 是如何起到作用的？")
    print("""
5 个标签 API 在两个不同场景起作用：

  场景 1  predict_label_pytod()：纯规则预测，零 LLM
    ┌──────────────────────────────────────────────────────────────┐
    │  API                      规则精度    角色                    │
    │  ─────────────────────────────────────────────────────────── │
    │  predict_data_error()     P=87% R=87% 规则直接预测（无 LLM） │
    │  predict_repetition()     P=87% R=87% 规则直接预测（无 LLM） │
    │  predict_improper_farewell()  FP↑    仅提供 LLM hint         │
    │  predict_off_topic()      召回≈60%   仅提供 LLM hint         │
    │  predict_no_issue()       兜底        —                      │
    └──────────────────────────────────────────────────────────────┘

  场景 2  detect_session_llm()：API 结果作为结构化 hint 注入 LLM prompt
    → data_error_hints / repetition_hint / farewell_hint
    → 提升 LLM 在数值偏差和重复模式上的感知精度

下面演示各 API 在真实标签预测中的贡献：
""")

    # —— 3A. predict_data_error ——————————————————————————
    de_session = next((s for s in _data if s.get("人工校验") == "数据错误"), None)
    if de_session:
        _hr("3A. predict_data_error → 数据错误检测")
        e = build_anyihua_engine(de_session)
        r = e.registry["predict_data_error"]()
        print(f"  会话: {de_session['session_id'][-12:]}  人工标签: {de_session['人工校验']}")
        print(f"  detected    = {r['detected']}")
        print(f"  evidence    = {r['evidence']}")
        print(f"  system_credit = {r['system_credit']:,} 元")
        if r["data_error_hints"]:
            print(f"  LLM hint    = {r['data_error_hints'][0][:70]}…")

    # —— 3B. predict_repetition ——————————————————————————
    rep_session = next((s for s in _data if s.get("人工校验") == "重复询问"), None)
    if rep_session:
        _hr("3B. predict_repetition → 重复询问检测")
        e = build_anyihua_engine(rep_session)
        r = e.registry["predict_repetition"]()
        print(f"  会话: {rep_session['session_id'][-12:]}  人工标签: {rep_session['人工校验']}")
        print(f"  detected       = {r['detected']}")
        print(f"  is_exact_repeat= {r['is_exact_repeat']}")
        print(f"  repeat_count   = {r['repeat_count']}")
        print(f"  evidence       = {r['evidence']}")
        if r["detected"]:
            print("  → 规则直接输出「重复询问」标签，无需 LLM ✓")

    # —— 3C. predict_improper_farewell ——————————————————
    fw_session = next((s for s in _data if s.get("人工校验") == "不当告别"), None)
    if fw_session:
        _hr("3C. predict_improper_farewell → 不当告别检测")
        e = build_anyihua_engine(fw_session)
        r = e.registry["predict_improper_farewell"]()
        print(f"  会话: {fw_session['session_id'][-12:]}  人工标签: {fw_session['人工校验']}")
        print(f"  detected        = {r['detected']}")
        print(f"  can_farewell    = {r['can_farewell']}")
        if r["unresolved_issues"]:
            print(f"  unresolved[0]   = {r['unresolved_issues'][-1][:60]}…")
        print(f"  farewell_hint   = {r['farewell_hint'][:70] if r['farewell_hint'] else '(无)'}…")
        print("  → farewell_hint 注入 LLM prompt，辅助语义判断")

    # —— 整体效果 ——————————————————————————————————————
    _hr("整体效果：predict_label_pytod() 在 100 条数据集上的表现")
    total = len(_data)
    pred_count = 0
    pred_correct = 0
    by_label: Dict[str, Dict[str, int]] = {}
    for s in _data:
        label, conf, _ = predict_label_pytod(s)
        gold = s.get("人工校验", "")
        if label is not None:
            pred_count += 1
            if label == gold:
                pred_correct += 1
                by_label.setdefault(label, {"correct": 0, "total": 0})["correct"] += 1
            by_label.setdefault(label, {"correct": 0, "total": 0})["total"] += 1

    print(f"\n  规则预测覆盖: {pred_count}/{total} ({pred_count/total:.0%})")
    print(f"  规则预测精度: {pred_correct}/{pred_count} ({pred_correct/pred_count:.0%})" if pred_count else "")
    print(f"  节省 LLM 调用: 约 {pred_count/total:.0%}")
    print()
    for lbl, stats in by_label.items():
        prec = stats["correct"] / stats["total"]
        print(f"  {lbl}: {stats['correct']}/{stats['total']} 正确 (精度 {prec:.0%})")

    print("""
  API 贡献对比：
  ┌──────────────────────────────────────────────────────────────────┐
  │  无标签 API（旧 CRM 设计）       有标签 API（新设计）             │
  │  ─────────────────────────────────────────────────────────────── │
  │  predict_label_pytod 手动组合    直接调用 predict_data_error()    │
  │  check_repetition → 字段提取    predict_repetition() 自包含      │
  │  query_account → 手动比较       predict_data_error() 自包含      │
  │  引擎 API 目的 ≠ 任务目标       引擎 API = 标签 = 任务目标 ✓    │
  └──────────────────────────────────────────────────────────────────┘
""")


# ===========================================================================
# 主入口
# ===========================================================================


def main() -> None:
    print("=" * 72)
    print("  安逸花外呼场景 · PyTOD engine.py 标签 API 完整演示")
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
  • contextmind/scenarios/anyihua/engine.py    — 5 个标签 API 的完整实现
  • contextmind/modes/pytod/execution_engine.py — ExecutionEngine 源码
  • docs/analysis/pytod-engine-api-explained.md — 配套分析文档
  • examples/anyihua_online_demo.py            — 含 LLM 的完整在线生成流程
""")


if __name__ == "__main__":
    main()
