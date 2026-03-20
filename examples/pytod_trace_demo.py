"""
PyTOD 对话追踪脚本

展示 PyTOD（Program-of-Thought for Task-Oriented Dialogue）算法在
安逸花外呼场景中的运行过程：通过 ADK 原生 Function Calling 实现
API 工具调用，并将全链路 I/O 写入 Markdown 报告。

用法::

    python examples/pytod_trace_demo.py
    python examples/pytod_trace_demo.py --seed 42
    python examples/pytod_trace_demo.py --index 5
    python examples/pytod_trace_demo.py --output /tmp/trace.md --verbose
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import sys
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from contextmind.infra.llm_client import LLMConfig, AdkLLMClient
from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
from contextmind.modes.pytod.registry import SCENARIO_API_REGISTRY

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

_SCENARIO_CONTEXT = (
    "这是一个外呼小额借款推介场景（安逸花外呼促活）。"
    "坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。"
    "标准流程：① 核实用户身份 → ② 告知可用额度和利率 → "
    "③ 解答疑问 → ④ 引导用户在 APP 完成借款操作 → ⑤ 礼貌告别。"
)


def _load_session(index: Optional[int], seed: Optional[int]) -> Dict[str, Any]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    sessions = data if isinstance(data, list) else data.get("sessions", [])
    if index is not None:
        return sessions[index % len(sessions)]
    if seed is not None:
        random.seed(seed)
    return random.choice(sessions)


async def run_trace(session: Dict[str, Any], verbose: bool = False) -> Dict[str, Any]:
    """运行单条会话的 PyTOD 追踪，返回结构化结果。"""
    engine = ExecutionEngine()
    # 注册安逸花外呼场景 API
    register_fn = SCENARIO_API_REGISTRY.get("anyihua")
    if register_fn:
        register_fn(engine)

    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    history = session.get("对话历史", [])
    user_turns = [utt[len(_USER_PREFIX):] for utt in history if utt.startswith(_USER_PREFIX)]
    if not user_turns:
        return {"error": "no user turns found", "session_id": session.get("session_id", "")}

    turns_results: List[Dict[str, Any]] = []

    # 将会话中的用户信息注入 scenario_context，让 AP 了解用户的账户详情，
    # 避免重复询问已知信息（如身份、额度等）
    user_info = session.get("用户信息", "")
    scenario_context = _SCENARIO_CONTEXT
    if user_info:
        scenario_context = f"{_SCENARIO_CONTEXT}\n\n## 本次通话用户信息\n{user_info}"

    if llm_available:
        llm_client = AdkLLMClient(config=config)
        agent = AdkPyTODTracker(llm_client=llm_client, engine=engine, scenario_context=scenario_context)
        for i, utt in enumerate(user_turns):
            try:
                result = await agent.process_turn(utt)
            except Exception as exc:
                result = {"response": f"(error: {exc})", "program_text": "", "state": {}}
            execution = result.get("execution")
            turns_results.append({
                "turn": i + 1,
                "user": utt[:120],
                "program": result.get("program_text", ""),
                "response": result.get("response", ""),
                "state": result.get("state", {}),
                "execution_success": getattr(execution, "success", None),
                "execution_errors": getattr(execution, "errors", []),
                "say_output": getattr(execution, "say_output", ""),
                "step_timings": dict(agent.step_timings),
            })
            if verbose:
                print(f"[Turn {i+1}] {utt[:80]}")
                print(f"  → program: {result.get('program_text', '')}")
                print(f"  → response: {result.get('response', '')[:80]}")
    else:
        for i, utt in enumerate(user_turns):
            turns_results.append({
                "turn": i + 1,
                "user": utt[:120],
                "program": "⚠️ LLM 未配置",
                "response": "⚠️ LLM 未配置",
                "state": {},
                "execution_success": None,
                "execution_errors": [],
                "say_output": "",
                "step_timings": {},
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "PyTOD (ADK native function calling)",
            "llm_available": llm_available,
        },
        "session_id": session.get("session_id", ""),
        "用户信息": session.get("用户信息", ""),
        "actual_response": session.get("坐席回复", ""),
        "registered_apis": engine.list_functions(),
        "turns": turns_results,
    }


def _render_markdown(trace: Dict[str, Any]) -> str:
    lines = [
        "# PyTOD 追踪报告",
        "",
        f"**时间**: {trace['metadata']['timestamp']}",
        f"**算法**: {trace['metadata']['algorithm']}",
        f"**会话 ID**: {trace.get('session_id', 'N/A')}",
        f"**用户信息**: {trace.get('用户信息', 'N/A')}",
        "",
        "## 注册 API",
        "",
        f"{', '.join(trace.get('registered_apis', []))}",
        "",
        "## 对话追踪",
        "",
    ]
    for t in trace.get("turns", []):
        lines.append(f"### Turn {t['turn']}")
        lines.append(f"**用户**: {t['user']}")
        lines.append("")

        # AP 输出程序
        lines.append("**[Step 1 AP] 程序**:")
        lines.append("```")
        lines.append(t["program"] or "(空)")
        lines.append("```")
        lines.append("")

        # EE 执行结果
        exec_ok = t.get("execution_success")
        if exec_ok is None:
            ee_status = "N/A"
        elif exec_ok:
            ee_status = "✅ 成功"
        else:
            ee_status = "❌ 失败"
        lines.append(f"**[Step 2 EE] 执行**: {ee_status}")
        exec_errors = t.get("execution_errors") or []
        if exec_errors:
            lines.append(f"  - 错误: {'; '.join(str(e) for e in exec_errors)}")
        say_out = t.get("say_output", "")
        if say_out:
            lines.append(f"  - say 输出: {say_out}")
        lines.append("")

        # DM 回复
        lines.append(f"**[Step 3 DM] 回复**: {t['response']}")
        lines.append("")

        # 耗时
        timings = t.get("step_timings") or {}
        if timings:
            timing_parts = [f"{k}: {v}s" for k, v in timings.items()]
            lines.append(f"**耗时**: {' | '.join(timing_parts)}")
            lines.append("")

        # 累积状态
        lines.append("**累积状态**:")
        lines.append("```json")
        lines.append(json.dumps(t["state"], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    lines += [
        "## 实际坐席回复（参考）",
        "",
        trace.get("actual_response", "（无）"),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTOD 全链路追踪脚本")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")

    trace = asyncio.run(run_trace(session, verbose=args.verbose))

    md = _render_markdown(trace)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"✓ 报告已写入: {args.output}")
    else:
        output_path = _PROJECT_ROOT / "examples" / "pytod_trace_output.md"
        output_path.write_text(md, encoding="utf-8")
        print(f"✓ 报告已写入: {output_path}")

    if not trace["metadata"]["llm_available"]:
        print("⚠️  LLM 未配置，工具调用未执行。请在 .env 中配置 LLM_API_KEY 后重新运行。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ 执行失败: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
