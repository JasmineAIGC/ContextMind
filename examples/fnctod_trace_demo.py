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
    python examples/fnctod_trace_demo.py --schema /path/to/schema.json
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
# 默认 schema：安逸花外呼业务（data/anyihua_schema.json）
_DEFAULT_SCHEMA_PATH = _PROJECT_ROOT / "data" / "anyihua_schema.json"
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
    """从 schema.json 文件加载 DomainSpec，替换预定义的场景 Schema。

    支持两种 JSON 格式：

    1. **SGD / KB-builder 格式**（推荐，由 ``save_dataset()`` 生成）::

           [{"service_name": "...", "description": "...",
             "slots": [...], "intents": [...]}]

    2. **FnCTOD 原生参数格式**（直接含 ``parameters`` 列表）::

           {"name": "...", "description": "...",
            "parameters": [{"name": "...", "description": "...", ...}]}

    Args:
        path: schema.json 文件路径。

    Returns:
        对应的 DomainSpec，可直接传给 ``FunctionManager.add_domain()``。
    """
    from contextmind.modes.fnctod.function_manager import FunctionParameter, ParameterType

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    entry = data[0] if isinstance(data, list) else data

    # FnCTOD 原生格式：顶层包含 "parameters" 列表且元素为参数定义字典
    params_raw = entry.get("parameters", [])
    if (
        isinstance(params_raw, list)
        and params_raw
        and isinstance(params_raw[0], dict)
        and "name" in params_raw[0]
    ):
        domain = DomainSpec(
            name=entry.get("name", entry.get("service_name", "custom")),
            description=entry.get("description", ""),
        )
        for p in params_raw:
            domain.add_parameter(FunctionParameter(
                name=p["name"],
                description=p.get("description", ""),
                param_type=ParameterType.STRING,
                required=p.get("required", False),
                enum_values=p.get("enum") or p.get("enum_values") or None,
            ))
        return domain

    # SGD / ServiceSchema 格式
    svc = load_schema_from_dict(data)
    fm = FunctionManager()
    fm.add_domain_from_slots(
        domain_name=svc.service_name,
        domain_description=svc.description,
        slots={slot.name: slot.description for slot in svc.slots},
        categorical_slots={
            slot.name: slot.possible_values
            for slot in svc.slots
            if slot.possible_values
        } or None,
        required_slots=[slot.name for slot in svc.slots if slot.is_required] or None,
    )
    return fm.get_all_domains()[0]


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
                    domain_spec: Optional[DomainSpec] = None) -> Dict[str, Any]:
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
    paired_turns: List[tuple] = []  # (user_text, preceding_agent_text)
    for entry in history:
        if isinstance(entry, dict):
            user_text = entry.get(_USER_KEY, "")
            orig_agent = entry.get(_AGENT_KEY, "")
            if user_text:
                paired_turns.append((user_text, orig_agent))
    if not paired_turns:
        return {"error": "no user turns found", "session_id": session.get("session_id", "")}

    turns_results: List[Dict[str, Any]] = []

    if llm_available:
        agent = FnCTODTracker(function_manager=fm, config=config)
        prev_state: Dict[str, Any] = {}
        for idx, (utt, orig_agent) in enumerate(paired_turns):
            # 捕获本轮 LLM 输入上下文（system + 历史对话 + 当前用户发言）
            hist_before = list(getattr(agent, "_dialogue_history", []))
            llm_input_messages = (
                [{"role": "system", "content": agent.system_instruction}]
                + hist_before
                + [{"role": "user", "content": utt}]
            )
            try:
                result = await agent.process_turn(utt)
            except Exception as exc:
                result = {"response": f"(error: {exc})", "state": {}, "updates": {}}

            response_text = result.get("response", "")
            new_state: Dict[str, Any] = result.get("state", {})
            state_delta = result.get("updates", {})
            # 仅保留非空 delta（过滤 None/""/[]）
            state_delta = {k: v for k, v in state_delta.items() if v not in (None, "", [])}

            turn_record = {
                "turn": idx + 1,
                "user": utt,
                "original_agent": orig_agent,
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
        for idx, (utt, orig_agent) in enumerate(paired_turns):
            turns_results.append({
                "turn": idx + 1,
                "user": utt,
                "original_agent": orig_agent,
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
        orig_agent = t.get("original_agent", "")
        lines += ["**原始对话**:", ""]
        if orig_agent:
            lines.append(f"{_AGENT_ICON} **机器人**: {orig_agent}")
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
    parser = argparse.ArgumentParser(description="FnCTOD 全链路追踪脚本")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--output", type=str, default=None,
                        help="Markdown 输出路径（默认 output/fnctod_trace_output.md）")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--schema", type=str, default=None,
        help="schema.json 路径（SGD 或 FnCTOD 格式）；若不提供则默认使用 data/anyihua_schema.json",
    )
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    # 加载 schema（必须指定 --schema 或存在默认 anyihua_schema.json）
    domain_spec: Optional[DomainSpec] = None
    schema_path = Path(args.schema) if args.schema else _DEFAULT_SCHEMA_PATH
    if schema_path.exists():
        domain_spec = _load_domain_spec_from_schema_file(schema_path)
        print(f"✓ 已加载 Schema: {schema_path} (domain={domain_spec.name})")
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
        print("   继续运行（无 schema 模式，FnCTOD 将无法提取槽位）", file=sys.stderr)

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")

    trace = asyncio.run(run_trace(session, verbose=args.verbose, domain_spec=domain_spec))

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
