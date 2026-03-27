"""
PyTOD 对话追踪脚本

展示 PyTOD（Program-of-Thought for Task-Oriented Dialogue）算法在
安逸花外呼场景中的运行过程，完整记录三步流水线（AP→EE→DM）每个阶段的
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
from contextmind.modes.pytod.schemas import ServiceSchema, load_schema_from_dict
from contextmind.modes.pytod.tracker import _is_stub_only_result, load_pytod_api_module
from contextmind.scenarios import get_anyihua_scenario

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
# 默认 schema：安逸花外呼业务（data/anyihua_schema.json）
_DEFAULT_SCHEMA_PATH = _PROJECT_ROOT / "data" / "anyihua_schema.json"
_AGENT_KEY = "机器人"
_USER_KEY = "用户"

_AGENT_ICON = "🤖"
_USER_ICON = "👤"

_SCENARIO_CONTEXT = (
    "这是安逸花外呼促活场景。"
    "机器人代表安逸花主动致电用户，目标是促进用户借款使用额度。"
    "标准流程：① 核实身份 → ② 告知额度/临时提额 → "
    "③ 解答疑问（利率/还款/逾期等）→ ④ 引导借款 → ⑤ 礼貌结束。"
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


def _is_noop_program(program_text: str) -> bool:
    """Return True when every non-comment line of *program_text* is a no-op sentinel.

    A "no-op" statement is either ``NONE()`` or ``conversation_pause()``,
    with or without a leading variable binding (e.g. ``x9 conversation_pause()``).
    These are intentional pause/skip markers that produce no EE output, so the
    EE result display should read "– 跳过" rather than "✅ 成功".
    """
    import re as _re
    if not program_text:
        return False
    lines = [
        ln.strip() for ln in program_text.strip().splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    if not lines:
        return False
    _noop_re = _re.compile(
        r"^(?:x\d+\s+)?(?:NONE|CONVERSATION_PAUSE)\s*\(", _re.IGNORECASE
    )
    return all(_noop_re.match(line) for line in lines)


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
                    external_schema: Optional[ServiceSchema] = None,
                    schema_path: Optional[Path] = None,
                    compact_schema: bool = False) -> Dict[str, Any]:
    """运行单条会话的 PyTOD 追踪，返回结构化结果（含每步完整 I/O）。

    Args:
        session:         对话会话字典。
        verbose:         是否打印详细日志。
        external_schema: 外部传入的 ServiceSchema（来自 ``--schema`` 或默认 anyihua_schema.json）；
                         若为 None 则使用空引擎运行（无 API 注册模式）。
        schema_path:     schema.json 文件路径，用于加载 companion ``*_pytod_apis.py`` 函数。
        compact_schema:  为 True 时，AP prompt 中省略详细业务意图说明（减少 token 用量）。
    """
    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    history = session.get("对话历史", [])
    # 统一格式：每条 entry 为 {"机器人": "xxx", "用户": "yyy"} 配对 dict。
    # 兼容旧式平铺字符串格式（向后兼容）。
    paired_turns: List[tuple] = []  # (user_text, preceding_agent_text)
    for entry in history:
        if isinstance(entry, dict):
            # 新格式：配对 dict
            user_text = entry.get(_USER_KEY, "")
            orig_agent = entry.get(_AGENT_KEY, "")
            if user_text:
                paired_turns.append((user_text, orig_agent))
        elif isinstance(entry, str):
            # 旧格式：平铺字符串（向后兼容）
            import re as _re
            if entry.startswith("机器人：") or entry.startswith("坐席："):
                preceding_agent_text = _re.sub(r"^(机器人|坐席)[：:]\s*", "", entry)
                # 暂存，等待下一条用户发言
                _pending_agent = preceding_agent_text
            elif entry.startswith("用户："):
                user_text = entry[len("用户："):]
                orig_agent = locals().get("_pending_agent", "")
                if user_text:
                    paired_turns.append((user_text, orig_agent))
                _pending_agent = ""
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
        scenario_config = get_anyihua_scenario()
        from_kwargs: Dict[str, Any] = {
            "scenario_context": scenario_context,
            "compact_schema": compact_schema,
        }
        if external_schema is not None:
            from_kwargs["schema"] = external_schema
            from_kwargs["schema_path"] = schema_path
        agent = AdkPyTODTracker.from_scenario(
            llm_client=llm_client,
            scenario_config=scenario_config,
            **from_kwargs,
        )
        engine = agent.engine  # 从追踪器获取已注册 API 的执行引擎
        # 使用实际运行引擎的 API 列表（包含 schema 自动注册的函数）
        registered_apis_list = sorted(engine.list_functions())
        for i, (utt, orig_agent) in enumerate(paired_turns):
            try:
                result = await agent.process_turn(utt)
            except Exception as exc:
                # 保留 tracker 已累积的状态和最近一轮执行结果，避免异常清空状态
                result = {
                    "response": f"(error: {exc})",
                    "program_text": getattr(agent, "last_program_text", ""),
                    "state": dict(agent.current_state),
                    "execution": getattr(agent, "last_execution_result", None),
                }

            ee_data = _serialize_execution(result.get("execution"))

            # state_delta：本轮 EE 新计算的变量，排除 say() 输出变量。
            # say() 变量已从 tracker.current_state 中过滤，这里同步保持一致，
            # 避免 state_delta 与 cumulative_state 出现差异（say 变量在 delta
            # 中出现但不在 cumulative 中）。
            _execution_obj = result.get("execution")
            _say_var_names: set = set()
            if hasattr(_execution_obj, "say_variable_names"):
                _say_var_names = _execution_obj.say_variable_names or set()
            state_delta: Dict[str, Any] = {
                k: v for k, v in ee_data.get("variables", {}).items()
                if k not in _say_var_names and not _is_stub_only_result(v)
            }
            # cumulative_state：tracker 跨轮累积的 API 结果（不含 say 输出、不含存根占位值）
            new_state: Dict[str, Any] = {
                k: v for k, v in result.get("state", {}).items()
                if not _is_stub_only_result(v)
            }

            # Fix 5: capture AP and DM prompt messages for this turn
            ap_messages = list(getattr(agent, "last_ap_messages", []))
            dm_messages = list(getattr(agent, "last_dm_messages", []))

            # Fix 3: annotate whether the AP result is valid
            program = result.get("program_text", "")
            ap_valid = bool(program and program.strip() and
                            not program.startswith("⚠️") and
                            not ee_data.get("errors"))

            turn_record = {
                "turn": i + 1,
                "user": utt,
                "original_agent": orig_agent,
                "program": program,
                "ap_valid": ap_valid,
                "ee": ee_data,
                "response": result.get("response", ""),
                "state_delta": state_delta,    # 本轮新增变量（来自 EE 执行结果）
                "cumulative_state": new_state, # 跨轮累积状态（tracker current_state）
                "timings": dict(agent.step_timings),
                "ap_messages": ap_messages,    # Fix 5: AP prompt
                "dm_messages": dm_messages,    # Fix 5: DM prompt
            }
            turns_results.append(turn_record)

            if verbose:
                print(f"[Turn {i+1}] user: {utt[:80]}")
                print(f"  [AP] {'✅' if ap_valid else '⚠️ invalid'} program: {program[:120]}")
                ee_ok = "✅" if ee_data.get("success") else ("❌" if ee_data.get("success") is False else "N/A")
                print(f"  [EE] {ee_ok} say={ee_data.get('say','')[:60]!r}")
                print(f"  [DM] response: {result.get('response', '')[:100]}")
    else:
        registered_apis_list = sorted(_probe_engine.list_functions())
        for i, (utt, orig_agent) in enumerate(paired_turns):
            turns_results.append({
                "turn": i + 1,
                "user": utt,
                "original_agent": orig_agent,
                "program": "⚠️ LLM 未配置",
                "ap_valid": False,
                "ee": {"success": None, "errors": [], "variables": {}, "say": "", "hints": []},
                "response": "⚠️ LLM 未配置",
                "state_delta": {},
                "cumulative_state": {},
                "timings": {},
                "ap_messages": [],
                "dm_messages": [],
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "PyTOD AP→EE→DM (官方三步流水线)",
            "llm_available": llm_available,
            "scenario": "安逸花外呼",
            "registered_apis": registered_apis_list,
        },
        "session_id": session.get("session_id", ""),
        "用户信息": session.get("用户信息", ""),
        "actual_response": session.get("坐席回复", ""),
        "turns": turns_results,
    }


def _format_messages_collapsible(messages: List[Dict[str, str]], label: str) -> List[str]:
    """将 LLM 消息列表渲染为可折叠的 <details> HTML 块。

    Fix 5: 使用 HTML <details>/<summary> 实现可折叠 LLM prompt 展示。
    """
    if not messages:
        return []
    lines = [
        f"<details>",
        f"<summary>📋 {label}（点击展开）</summary>",
        "",
    ]
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        role_label = {"system": "**System**", "user": "**User**", "assistant": "**Assistant**"}.get(role, f"**{role}**")
        lines += [
            f"{role_label}:",
            "",
            "```",
            content,
            "```",
            "",
        ]
    lines += ["</details>", ""]
    return lines


def _render_markdown(trace: Dict[str, Any]) -> str:
    """将 trace 字典渲染为 Markdown 报告。

    每轮展示：
    - 原始对话（坐席先说，用户后说）  Fix 2
    - ① AP 程序（标注是否有效）       Fix 3
    - ② EE 执行结果
    - ③ DM 生成回复
    - 回复对比（原始 vs DM）
    - 本轮新增状态（delta，不重复显示）Fix 4
    - AP / DM prompt（可折叠）        Fix 5
    """
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

        # Fix 2: 原始对话 — 机器人先说，用户后说
        orig_agent = t.get("original_agent", "")
        lines += ["**原始对话**:", ""]
        if orig_agent:
            lines.append(f"{_AGENT_ICON} **机器人**: {orig_agent}")
            lines.append("")
        lines.append(f"{_USER_ICON} **用户**: {t['user']}")
        lines.append("")

        # Fix 3: ① AP 程序（标注有效性）
        program = t.get("program") or ""
        ap_valid = t.get("ap_valid", True)
        ap_label = "**① AP 程序**" if ap_valid else "**① AP 程序** ⚠️ *（无效 / NONE）*"
        lines += [
            ap_label + ":",
            "```",
            program or "(空)",
            "```",
            "",
        ]

        # ② EE
        ee = t.get("ee", {})
        ee_ok = ee.get("success")
        # 检测 NONE / conversation_pause — 这两种语句是无操作占位符，
        # EE 正确地不产生任何变量；显示为"跳过"而非"成功"，避免产生歧义。
        is_noop = _is_noop_program(program)
        if is_noop:
            ee_status = "– 跳过 (NONE/pause)"
        else:
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
                f"| {_AGENT_ICON} 原始机器人 | {orig_agent} |",
                f"| {_AGENT_ICON} DM 生成 | {new_response} |",
                "",
            ]

        # 本轮新增状态（来自 EE 执行结果，含 API 返回值与 say 输出）
        state_delta = t.get("state_delta", {})
        if state_delta:
            lines += [
                "**本轮新增状态**:",
                "```json",
                json.dumps(state_delta, ensure_ascii=False, indent=2),
                "```",
                "",
            ]

        # 累积状态（tracker 跨轮积累的 API 结果，全量，可折叠）
        cumstate = t.get("cumulative_state", {})
        if cumstate:
            lines += [
                "<details>",
                "<summary>📊 累积状态（点击展开）</summary>",
                "",
                "```json",
                json.dumps(cumstate, ensure_ascii=False, indent=2),
                "```",
                "",
                "</details>",
                "",
            ]

        # Fix 5: AP / DM prompt（可折叠）
        ap_messages = t.get("ap_messages") or []
        dm_messages = t.get("dm_messages") or []
        lines += _format_messages_collapsible(ap_messages, "AP Prompt（动作解析器输入）")
        lines += _format_messages_collapsible(dm_messages, "DM Prompt（对话管理器输入）")

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
        "--compact-schema", dest="compact_schema", action="store_true",
        help="省略 AP prompt 中的详细业务意图说明（减少 token 用量；适合 token 敏感部署）",
    )
    parser.add_argument(
        "--schema", type=str, default=None,
        help="schema.json 路径（SGD 格式）；若不提供则默认使用 data/anyihua_schema.json",
    )
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    # 加载 schema（必须指定 --schema 或存在默认 anyihua_schema.json）
    external_schema: Optional[ServiceSchema] = None
    schema_path = Path(args.schema) if args.schema else _DEFAULT_SCHEMA_PATH
    if schema_path.exists():
        external_schema = _load_service_schema_from_file(schema_path)
        print(f"✓ 已加载 Schema: {schema_path} (service={external_schema.service_name})")
    elif args.schema:
        print(f"❌ Schema 文件不存在: {schema_path}", file=sys.stderr)
        sys.exit(1)
    else:
        print(
            f"⚠️  默认 Schema 文件不存在: {schema_path}\n"
            "   请先运行: python examples/build_schema_data.py\n"
            "   或通过 --schema 指定 schema 文件路径",
            file=sys.stderr,
        )
        print("   继续运行（无 schema 模式，AP 将无法调用业务 API）", file=sys.stderr)

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")

    trace = asyncio.run(run_trace(session, verbose=args.verbose,
                                   external_schema=external_schema,
                                   schema_path=schema_path if external_schema is not None else None,
                                   compact_schema=args.compact_schema))

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

