"""
PyTOD 对话追踪脚本

展示 PyTOD（Program-of-Thought for Task-Oriented Dialogue）算法在
客服场景中的运行过程，完整记录三步流水线（AP→EE→DM）每个阶段的
输入/输出/执行方式，并将全链路 I/O 写入 Markdown 报告和 JSON 文件。

用法::

    python examples/pytod_trace_demo.py
    python examples/pytod_trace_demo.py --seed 42
    python examples/pytod_trace_demo.py --index 5
    python examples/pytod_trace_demo.py --output /tmp/trace.md --verbose
    python examples/pytod_trace_demo.py --schema /path/to/schema.json
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
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict
from contextmind.scenarios import get_callcenter_scenario

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

_SCENARIO_CONTEXT = (
    "这是一个客服对话场景。"
    "坐席代表客服中心接听用户来电，目标是解答用户问题、处理订单和提供帮助。"
    "标准流程：① 问候确认身份 → ② 了解用户诉求 → "
    "③ 解答疑问或处理问题 → ④ 确认用户满意 → ⑤ 礼貌告别。"
)


def _load_service_schema_from_file(path: Path) -> ServiceSchema:
    """从 schema.json 文件加载 ServiceSchema，替换预定义的场景 Schema。

    支持 SGD / KB-builder 输出格式::

        [{"service_name": "...", "description": "...",
          "slots": [...], "intents": [...]}]

    或单对象格式::

        {"service_name": "...", "description": "...",
         "slots": [...], "intents": [...]}

    Args:
        path: schema.json 文件路径。

    Returns:
        解析后的 ServiceSchema，可直接传给 ``AdkPyTODTracker.from_scenario()``。
    """
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return load_schema_from_dict(data)


def _load_session(index: Optional[int], seed: Optional[int]) -> Dict[str, Any]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    sessions = data if isinstance(data, list) else data.get("sessions", [])
    if index is not None:
        return sessions[index % len(sessions)]
    if seed is not None:
        random.seed(seed)
    return random.choice(sessions)


def _serialize_execution(execution_result: Any) -> Dict[str, Any]:
    """将 ProgramExecutionResult 序列化为可 JSON 化的字典。"""
    if execution_result is None:
        return {"success": None, "errors": [], "variables": {}, "say": "", "hints": []}
    try:
        var_values = dict(getattr(execution_result, "variable_values", {}))
        for k, v in var_values.items():
            try:
                json.dumps(v)
            except (TypeError, ValueError):
                var_values[k] = str(v)
        return {
            "success": getattr(execution_result, "success", None),
            "errors": [str(e) for e in getattr(execution_result, "errors", [])],
            "variables": var_values,
            "say": getattr(execution_result, "say_output", ""),
            "hints": list(getattr(execution_result, "hint_messages", [])),
        }
    except Exception as exc:
        return {"success": None, "errors": [str(exc)], "variables": {}, "say": "", "hints": []}


async def run_trace(session: Dict[str, Any], verbose: bool = False,
                    external_schema: Optional[ServiceSchema] = None) -> Dict[str, Any]:
    """运行单条会话的 PyTOD 追踪，返回结构化结果（含每步完整 I/O）。

    Args:
        session:         对话会话字典。
        verbose:         是否打印详细日志。
        external_schema: 外部传入的 ServiceSchema（来自 ``--schema``）；
                         若为 None 则使用预定义的场景 Schema。
    """
    # 用于获取已注册 API 列表（无论 LLM 是否可用）
    _probe_engine = ExecutionEngine()
    register_fn = SCENARIO_API_REGISTRY.get("callcenter")
    if register_fn:
        register_fn(_probe_engine)

    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    history = session.get("对话历史", [])
    # Extract paired turns: (user_utterance, original_agent_response)
    paired_turns: List[tuple] = []
    i = 0
    while i < len(history):
        utt = history[i]
        if utt.startswith(_USER_PREFIX):
            user_text = utt[len(_USER_PREFIX):]
            orig_agent = ""
            if i + 1 < len(history) and history[i + 1].startswith(_AGENT_PREFIX):
                orig_agent = history[i + 1][len(_AGENT_PREFIX):]
                i += 2
            else:
                i += 1
            paired_turns.append((user_text, orig_agent))
        else:
            i += 1
    if not paired_turns:
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
        # 使用 from_scenario() 自动加载客服场景 API 和预置 Schema，
        # 确保 AP 提示词包含完整的业务意图和槽位描述，无需手动创建知识库。
        scenario_config = get_callcenter_scenario()
        agent = AdkPyTODTracker.from_scenario(
            llm_client=llm_client,
            scenario_config=scenario_config,
            scenario_context=scenario_context,
            **({"schema": external_schema} if external_schema is not None else {}),
        )
        engine = agent.engine  # 从追踪器获取已注册 API 的执行引擎
        for i, (utt, orig_agent) in enumerate(paired_turns):
            try:
                result = await agent.process_turn(utt)
            except Exception as exc:
                result = {"response": f"(error: {exc})", "program_text": "", "state": {}, "execution": None}

            ee_data = _serialize_execution(result.get("execution"))

            turn_record = {
                "turn": i + 1,
                "user": utt,
                "original_agent": orig_agent,
                "program": result.get("program_text", ""),
                "ee": ee_data,
                "response": result.get("response", ""),
                "cumulative_state": result.get("state", {}),
                "timings": dict(agent.step_timings),
            }
            turns_results.append(turn_record)

            if verbose:
                print(f"[Turn {i+1}] user: {utt[:80]}")
                print(f"  [AP] program: {result.get('program_text', '')[:120]}")
                ee_ok = "✅" if ee_data.get("success") else ("❌" if ee_data.get("success") is False else "N/A")
                print(f"  [EE] {ee_ok} say={ee_data.get('say','')[:60]!r}")
                print(f"  [DM] response: {result.get('response', '')[:100]}")
    else:
        for i, (utt, orig_agent) in enumerate(paired_turns):
            turns_results.append({
                "turn": i + 1,
                "user": utt,
                "original_agent": orig_agent,
                "program": "⚠️ LLM 未配置",
                "ee": {"success": None, "errors": [], "variables": {}, "say": "", "hints": []},
                "response": "⚠️ LLM 未配置",
                "cumulative_state": {},
                "timings": {},
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "PyTOD AP→EE→DM (官方三步流水线)",
            "llm_available": llm_available,
            "scenario": "客服对话",
            "registered_apis": _probe_engine.list_functions(),
        },
        "session_id": session.get("session_id", ""),
        "用户信息": session.get("用户信息", ""),
        "actual_response": session.get("坐席回复", ""),
        "turns": turns_results,
    }


def _render_markdown(trace: Dict[str, Any]) -> str:
    """将 trace 字典渲染为 Markdown 报告，每轮显示原始对话 + 算法步骤 + 回复对比。"""
    meta = trace["metadata"]
    llm_ok = meta["llm_available"]
    lines = [
        "# PyTOD 追踪报告",
        "",
        f"| 字段 | 值 |",
        f"|---|---|",
        f"| 时间 | {meta['timestamp']} |",
        f"| 算法 | {meta['algorithm']} |",
        f"| 场景 | {meta.get('scenario', 'N/A')} |",
        f"| 会话 ID | `{trace.get('session_id', 'N/A')}` |",
        f"| LLM | {'✅ 可用' if llm_ok else '❌ 未配置'} |",
        "",
    ]

    user_info = trace.get("用户信息")
    if user_info:
        lines += [f"**用户信息**: {user_info}", ""]

    apis = meta.get("registered_apis", [])
    if apis:
        lines += [f"**注册 API**: {', '.join(f'`{fn}`' for fn in apis)}", ""]

    lines += ["---", ""]

    for t in trace.get("turns", []):
        timings = t.get("timings") or {}
        timing_str = ""
        if timings:
            timing_str = "  *(" + " / ".join(f"{k}: {v}s" for k, v in timings.items()) + ")*"

        lines += [
            f"### Turn {t['turn']}{timing_str}",
            "",
        ]

        # 原始对话（用户 + 原始坐席回复）
        orig_agent = t.get("original_agent", "")
        lines += [
            "**原始对话**:",
            "",
            f"| 角色 | 话语 |",
            f"|---|---|",
            f"| 👤 用户 | {t['user']} |",
        ]
        if orig_agent:
            lines.append(f"| 🤖 原始坐席 | {orig_agent} |")
        lines.append("")

        # ① AP
        program = t.get("program") or ""
        lines += [
            "**① AP 程序**:",
            "```",
            program or "(空)",
            "```",
            "",
        ]

        # ② EE
        ee = t.get("ee", {})
        ee_ok = ee.get("success")
        ee_status = "✅ 成功" if ee_ok else ("❌ 失败" if ee_ok is False else "–")
        ee_parts = [f"**② EE**: {ee_status}"]
        if ee.get("errors"):
            ee_parts.append(f"· 错误: {'; '.join(ee['errors'])}")
        if ee.get("say"):
            ee_parts.append(f"· say: `{ee['say']}`")
        lines.append("  ".join(ee_parts))
        if ee.get("variables"):
            lines += [
                "```json",
                json.dumps(ee["variables"], ensure_ascii=False, indent=2),
                "```",
            ]
        if ee.get("hints"):
            lines.append(f"hints: {', '.join(ee['hints'])}")
        lines.append("")

        # ③ DM 生成回复
        new_response = t.get("response") or "(空)"
        lines += [
            "**③ DM 生成回复**:",
            f"> {new_response}",
            "",
        ]

        # 回复对比
        if orig_agent:
            lines += [
                "**回复对比**:",
                "",
                "| | 回复 |",
                "|---|---|",
                f"| 🤖 原始坐席 | {orig_agent} |",
                f"| 🤖 DM 生成 | {new_response} |",
                "",
            ]

        # 累积状态
        cumstate = t.get("cumulative_state", {})
        if cumstate:
            lines += [
                "**累积状态**:",
                "```json",
                json.dumps(cumstate, ensure_ascii=False, indent=2),
                "```",
                "",
            ]

    actual = trace.get("actual_response")
    if actual:
        lines += [
            "---",
            "",
            "**参考坐席回复**:",
            f"> {actual}",
            "",
        ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="PyTOD 全链路追踪脚本")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--output", type=str, default=None,
                        help="Markdown 输出路径（默认 output/pytod_trace_output.md）")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--schema", type=str, default=None,
        help="schema.json 路径（SGD 格式）；若提供则替换预定义场景 ServiceSchema",
    )
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    external_schema: Optional[ServiceSchema] = None
    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"❌ Schema 文件不存在: {schema_path}", file=sys.stderr)
            sys.exit(1)
        external_schema = _load_service_schema_from_file(schema_path)
        print(f"✓ 已加载外部 Schema: {schema_path} (service={external_schema.service_name})")

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")

    trace = asyncio.run(run_trace(session, verbose=args.verbose, external_schema=external_schema))

    # 输出路径
    if args.output:
        md_path = Path(args.output)
    else:
        md_path = _PROJECT_ROOT / "output" / "pytod_trace_output.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)

    # 写 Markdown
    md = _render_markdown(trace)
    md_path.write_text(md, encoding="utf-8")
    print(f"✓ Markdown 报告已写入: {md_path}")

    # 同时写 JSON（结构化数据，便于后续分析）
    json_path = md_path.with_suffix(".json")
    json_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ JSON 数据已写入:     {json_path}")

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

