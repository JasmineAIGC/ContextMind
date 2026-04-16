"""
FnCTOD 对话状态追踪脚本

展示 FnCTOD（基于函数调用的零样本对话状态追踪，ACL 2024）算法在
客服场景中的运行过程：通过 ADK 原生 Function Calling 实现
结构化槽位提取，并将全链路 I/O 写入 Markdown 报告和 JSON 文件。

追踪格式与 pytod_trace_demo.py 对齐，每轮记录：
  - 原始对话（坐席先说，用户后说）
  - Function Call DST 结果（本轮槽位更新）
  - DM 生成回复
  - 回复对比（原始 vs DM）
  - 本轮新增状态（delta）
  - 累积状态（可折叠）
  - LLM 输入上下文（可折叠）

用法::

    python examples/fnctod_trace_demo.py
    python examples/fnctod_trace_demo.py --seed 42
    python examples/fnctod_trace_demo.py --index 5
    python examples/fnctod_trace_demo.py --output /tmp/trace.md --verbose
    python examples/fnctod_trace_demo.py --schema schema/anyihua_fnctod_domain.json
    python examples/fnctod_trace_demo.py --schema schema/anyihua_schema.json
    python examples/fnctod_trace_demo.py --json-mode  # vLLM 等未启用原生函数调用时使用
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
from contextmind.modes.fnctod import FnCTODTracker, FunctionManager
from contextmind.modes.fnctod.function_manager import DomainSpec
from contextmind.modes.pytod.schemas import load_schema_from_dict

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
# 默认 schema：安逸花外呼业务 companion 文件（schema/anyihua_fnctod_domain.json）
# 若 companion 文件不存在，自动回退到 anyihua_schema.json
_DEFAULT_SCHEMA_PATH = _PROJECT_ROOT / "schema" / "anyihua_fnctod_domain.json"
_DEFAULT_SCHEMA_PATH_FALLBACK = _PROJECT_ROOT / "schema" / "anyihua_schema.json"
_AGENT_KEY = "机器人"
_USER_KEY = "用户"

_SCENARIO_CONTEXT = (
    "这是安逸花外呼促活场景。"
    "机器人代表安逸花主动致电用户，目标是促进用户借款使用额度。"
    "标准流程：① 核实身份 → ② 告知额度/临时提额 → "
    "③ 解答疑问（利率/还款/逾期等）→ ④ 引导借款 → ⑤ 礼貌结束。"
)

_AGENT_ICON = "🤖"
_USER_ICON = "👤"


def _load_domain_spec_from_schema_file(path: Path) -> DomainSpec:
    """从 schema 文件加载 DomainSpec，供 FnCTOD 追踪器使用。

    支持以下输入格式（按优先级排序）：

    1. ``*_fnctod_domain.json`` — 预生成的 companion 文件（推荐），由
       ``python examples/build_schema_data.py`` 生成。
    2. ``*_schema.json`` — 原始 SGD/KB-builder 格式；若同目录存在对应的
       ``*_fnctod_domain.json`` companion 文件则自动优先使用它。

    Args:
        path: schema 文件路径（``*_fnctod_domain.json`` 或 ``*_schema.json``）。

    Returns:
        对应的 DomainSpec，可直接传给 ``FunctionManager.add_domain()``。
    """
    from contextmind.modes.fnctod.schemas import load_domain_spec_from_file

    # 若传入 *_schema.json，自动检查同目录是否存在预生成的 companion 文件
    load_path = path
    if path.stem.endswith("_schema"):
        base = path.stem[: -len("_schema")]
        companion = path.parent / f"{base}_fnctod_domain.json"
        if companion.exists():
            load_path = companion

    return load_domain_spec_from_file(load_path)


def _load_session(index: Optional[int], seed: Optional[int]) -> Dict[str, Any]:
    with open(_DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    sessions = data if isinstance(data, list) else data.get("sessions", [])
    if index is not None:
        return sessions[index % len(sessions)]
    if seed is not None:
        random.seed(seed)
    return random.choice(sessions)


async def run_trace(session: Dict[str, Any], verbose: bool = False,
                    domain_spec: Optional[DomainSpec] = None,
                    use_native_tools: bool = True) -> Dict[str, Any]:
    """运行单条会话的 FnCTOD 追踪，返回结构化结果（含每步完整 I/O）。

    追踪格式与 pytod_trace_demo.py 对齐：每轮包含原始对话（坐席先说，用户后说）、
    Function Call DST 结果、DM 生成回复、state_delta、累积状态和 LLM 输入上下文。

    Args:
        session:     对话会话字典。
        verbose:     是否打印详细日志。
        domain_spec: 外部传入的 DomainSpec（来自 ``--schema``）；
                     若为 None 则使用空 FunctionManager（无 schema 模式）。
    """
    fm = FunctionManager()
    if domain_spec is not None:
        fm.add_domain(domain_spec)

    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    history = session.get("对话历史", [])
    # 每条 entry 格式：{"机器人": "坐席说的话", "用户": "用户回复"}
    # preceding_agent = entry[i]['机器人']：坐席在用户发言「之前」说的话（用于过程上下文）
    # following_agent = entry[i+1]['机器人']（或 坐席回复）：坐席对用户的「实际回应」（用于效果对比）
    history_entries = [e for e in history if isinstance(e, dict) and e.get(_USER_KEY)]
    final_agent_response = session.get("坐席回复", "")
    paired_turns: List[tuple] = []  # (user_text, preceding_agent, following_agent)
    for i, entry in enumerate(history_entries):
        user_text = entry[_USER_KEY]
        preceding_agent = entry.get(_AGENT_KEY, "")
        following_agent = (
            history_entries[i + 1].get(_AGENT_KEY, "")
            if i + 1 < len(history_entries)
            else final_agent_response
        )
        paired_turns.append((user_text, preceding_agent, following_agent))
    if not paired_turns:
        return {"error": "no user turns found", "session_id": session.get("session_id", "")}

    turns_results: List[Dict[str, Any]] = []

    # 将会话中的用户信息注入 scenario_context，让 LLM 了解用户的账户详情，
    # 避免重复询问已知信息（如身份、额度等）。与 pytod_trace_demo.py 保持一致。
    user_info = session.get("用户信息", "")
    scenario_context = _SCENARIO_CONTEXT
    if user_info:
        scenario_context = f"{_SCENARIO_CONTEXT}\n\n## 本次通话用户信息\n{user_info}"

    if llm_available:
        agent = FnCTODTracker(function_manager=fm, config=config,
                              scenario_context=scenario_context,
                              use_native_tools=use_native_tools)
        prev_state: Dict[str, Any] = {}
        n_turns = len(paired_turns)
        for idx, (utt, preceding_agent, following_agent) in enumerate(paired_turns):
            print(f"  → 处理第 {idx + 1}/{n_turns} 轮...", flush=True)
            # 捕获本轮历史（process_turn 之前）用于 llm_input_messages
            # effective_user_content 反映实际发送给 LLM 的完整对话对（坐席+用户）
            hist_before = list(getattr(agent, "_dialogue_history", []))
            effective_user_content = (
                f"坐席: {preceding_agent}\n用户: {utt}" if preceding_agent else utt
            )
            try:
                result = await asyncio.wait_for(
                    agent.process_turn(utt, agent_utterance=preceding_agent),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                result = {
                    "response": "(超时: LLM 调用超时，请检查 API 连接是否正常)",
                    "state": dict(getattr(agent, "_current_state", {})),
                    "updates": {},
                }
                print(f"  ⚠️  第 {idx + 1} 轮 LLM 调用超时", flush=True)
            except Exception as exc:
                result = {
                    "response": f"(error: {exc})",
                    "state": dict(getattr(agent, "_current_state", {})),
                    "updates": {},
                }
                print(f"  ⚠️  第 {idx + 1} 轮 LLM 调用失败: {exc}", flush=True)

            # 使用 process_turn 执行后的实际系统提示词（原生模式 or JSON 备用模式），
            # 确保 llm_input_messages 与实际 LLM 调用一致（特别是 turn 1 fallback 时）。
            llm_input_messages = (
                [{"role": "system", "content": agent.current_system_prompt}]
                + hist_before
                + [{"role": "user", "content": effective_user_content}]
            )

            response_text = result.get("response", "")
            new_state: Dict[str, Any] = result.get("state", {})
            state_delta = result.get("updates", {})
            # 仅保留非空 delta（过滤 None/""/[]）
            state_delta = {k: v for k, v in state_delta.items() if v not in (None, "", [])}

            turn_record = {
                "turn": idx + 1,
                "user": utt,
                "preceding_agent": preceding_agent,  # 坐席在本轮用户发言前说的话（过程上下文）
                "original_agent": following_agent,   # 坐席对本轮用户的实际回应（对比基准）
                "function_call": {
                    "domains": fm.get_domain_names(),
                    "args": state_delta,
                },
                "response": response_text,
                "state_delta": state_delta,
                "cumulative_state": new_state,
                "llm_input_messages": llm_input_messages,
            }
            turns_results.append(turn_record)
            prev_state = dict(new_state)

            if verbose:
                print(f"[Turn {idx+1}] user: {utt[:80]}")
                print(f"  [FC] updates: {state_delta}")
                print(f"  [DM] response: {response_text[:100]}")
    else:
        for idx, (utt, preceding_agent, following_agent) in enumerate(paired_turns):
            turns_results.append({
                "turn": idx + 1,
                "user": utt,
                "preceding_agent": preceding_agent,
                "original_agent": following_agent,
                "function_call": {"domains": fm.get_domain_names(), "args": {}},
                "response": "⚠️ LLM 未配置",
                "state_delta": {},
                "cumulative_state": {},
                "llm_input_messages": [],
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "FnCTOD (零样本DST via Function Calling, ACL 2024)",
            "llm_available": llm_available,
            "scenario": "安逸花外呼",
        },
        "session_id": session.get("session_id", ""),
        "用户信息": session.get("用户信息", ""),
        "actual_response": session.get("坐席回复", ""),
        "turns": turns_results,
        "schema_domains": fm.get_domain_names(),
        "schema_parameters": [
            {"domain": d.name, "params": [p.name for p in d.parameters]}
            for d in fm.get_all_domains()
        ],
    }


def _format_messages_collapsible(messages: List[Dict[str, str]], label: str) -> List[str]:
    """将 LLM 消息列表渲染为可折叠的 <details> HTML 块（与 pytod_trace_demo 一致）。"""
    if not messages:
        return []
    lines = [
        "<details>",
        f"<summary>📋 {label}（点击展开）</summary>",
        "",
    ]
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        role_label = {"system": "**System**", "user": "**User**", "assistant": "**Assistant**"}.get(
            role, f"**{role}**"
        )
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
    """将 trace 字典渲染为 Markdown 报告（格式与 pytod_trace_demo 对齐）。

    每轮展示：
    - 原始对话（坐席先说，用户后说）
    - Function Call DST 结果（本轮槽位更新）
    - DM 生成回复
    - 回复对比（原始 vs DM）
    - 本轮新增状态（delta）
    - 累积状态（可折叠）
    - LLM 输入上下文（可折叠）
    """
    meta = trace["metadata"]
    llm_ok = meta["llm_available"]
    lines = [
        "# FnCTOD 追踪报告",
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

    # Schema domains (compact bullet list)
    for d in trace.get("schema_parameters", []):
        lines.append(f"**{d['domain']}** 槽位: {', '.join(f'`{p}`' for p in d['params'])}")
    lines += ["", "---", ""]

    for t in trace.get("turns", []):
        lines += [
            f"### Turn {t['turn']}",
            "",
        ]

        # 原始对话（机器人先说，用户后说）
        # preceding_agent：本轮用户发言之前坐席说的话（提供对话上下文）
        preceding_agent = t.get("preceding_agent", t.get("original_agent", ""))
        # original_agent：本轮用户发言之后坐席的实际回复（作为对比基准）
        orig_agent = t.get("original_agent", "")
        lines += ["**原始对话**:", ""]
        if preceding_agent:
            lines.append(f"{_AGENT_ICON} **机器人**: {preceding_agent}")
            lines.append("")
        lines.append(f"{_USER_ICON} **用户**: {t['user']}")
        lines.append("")

        # Function Call DST 结果（等同于 PyTOD 的 EE 步骤）
        state_delta = t.get("state_delta", {})
        fc_info = t.get("function_call", {})
        domains_str = ", ".join(f"`{d}`" for d in fc_info.get("domains", []))
        lines.append(f"**① Function Call DST**（域: {domains_str}）:")
        if state_delta:
            lines += [
                "```json",
                json.dumps(state_delta, ensure_ascii=False, indent=2),
                "```",
            ]
        else:
            lines.append("*(本轮无槽位更新)*")
        lines.append("")

        # DM 生成回复
        new_response = t.get("response") or "(空)"
        lines += [
            "**② DM 生成回复**:",
            f"> {new_response}",
            "",
        ]

        # 回复对比（仅当存在原始机器人发言时）
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

        # 本轮新增状态（delta，不重复历史变量）
        if state_delta:
            lines += [
                "**本轮新增状态**:",
                "```json",
                json.dumps(state_delta, ensure_ascii=False, indent=2),
                "```",
                "",
            ]

        # 累积状态（全量，可折叠）
        cumstate = t.get("cumulative_state", {})
        active_cum = (
            {k: v for k, v in cumstate.items() if v not in (None, "", [])}
            if isinstance(cumstate, dict) else cumstate
        )
        if active_cum:
            lines += [
                "<details>",
                "<summary>📊 累积状态（点击展开）</summary>",
                "",
                "```json",
                json.dumps(active_cum, ensure_ascii=False, indent=2),
                "```",
                "",
                "</details>",
                "",
            ]

        # LLM 输入上下文（可折叠）
        llm_msgs = t.get("llm_input_messages") or []
        lines += _format_messages_collapsible(llm_msgs, "LLM 输入上下文（点击展开）")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="FnCTOD 全链路追踪脚本")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--output", type=str, default=None,
                        help="Markdown 输出路径（默认 output/fnctod_trace_output.md）")
    parser.add_argument(
        "--json-mode", action="store_true",
        help="跳过原生函数调用，直接使用 JSON 提示词备用模式（适用于 vLLM 未启用 "
             "--enable-auto-tool-choice 的场景，避免第 1 轮 tool_choice 报错）",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--schema", type=str, default=None,
        help="schema 文件路径：推荐使用预生成的 *_fnctod_domain.json（由 build_schema_data.py 生成）；"
             "也接受 *_schema.json（自动寻找同目录 companion 文件）；"
             "若不提供则默认使用 schema/anyihua_schema.json",
    )
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    # 加载 schema（必须指定 --schema 或存在默认 companion / schema 文件）
    domain_spec: Optional[DomainSpec] = None
    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"❌ Schema 文件不存在: {schema_path}", file=sys.stderr)
            sys.exit(1)
    else:
        # 优先使用预生成的 companion 文件，不存在则回退到原始 schema
        schema_path = (
            _DEFAULT_SCHEMA_PATH if _DEFAULT_SCHEMA_PATH.exists()
            else _DEFAULT_SCHEMA_PATH_FALLBACK
        )
    if schema_path.exists():
        domain_spec = _load_domain_spec_from_schema_file(schema_path)
        print(f"✓ 已加载 Schema: {schema_path} (domain={domain_spec.name})")
    else:
        print(
            f"⚠️  默认 Schema 文件不存在: {schema_path}\n"
            "   请先运行: python examples/build_schema_data.py\n"
            "   或通过 --schema 指定 schema 文件路径",
            file=sys.stderr,
        )
        print("   继续运行（无 schema 模式，FnCTOD 将无法提取槽位）", file=sys.stderr)

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")
    print("正在执行 FnCTOD 追踪（每轮 LLM 调用超时 120s）...", flush=True)

    trace = asyncio.run(run_trace(session, verbose=args.verbose, domain_spec=domain_spec,
                                  use_native_tools=not args.json_mode))
    print("✓ 追踪完成", flush=True)

    # 输出路径
    if args.output:
        md_path = Path(args.output)
    else:
        md_path = _PROJECT_ROOT / "output" / "fnctod_trace_output.md"
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
        print("⚠️  LLM 未配置，State 追踪未执行。请在 .env 中配置 LLM_API_KEY 后重新运行。")


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
