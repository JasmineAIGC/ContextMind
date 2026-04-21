"""
Genie Worksheets 对话状态追踪脚本

展示 Genie Worksheets 算法（stanford-oval/genie-worksheets，ACL 2024）在
业务场景中的完整六步流水线运行过程，并将全链路 I/O 写入 Markdown 报告和 JSON 文件。

六步流水线（每轮）
------------------
  Step 1: 确认流检查       — 检测 PENDING_CONFIRM 字段，处理 yes/no 用户意图
  Step 2: 语义解析（LLM-1）— 从用户话语中提取字段赋值（SemanticParser）
  Step 3: Worksheet 状态更新 — PolicyExecutor.fill_batch() 推进字段状态
  Step 4: on_success dispatch — 触发字段关联的 API 回调（ReportAgentAct）
  Step 5: AgentActs 计算   — 确定性：Ask / AskForConfirmation / Report
  Step 6: 回复生成（LLM-2）— ResponseGenerator 根据 AgentActs 生成自然语言回复

追踪格式与 pytod_trace_demo.py / fnctod_trace_demo.py 对齐，每轮记录：
  - 原始对话（坐席先说，用户后说）
  - ① 语义解析结果（LLM-1 提取的字段赋值）
  - ② PolicyExecutor 状态更新（字段状态变化）
  - ③ AgentActs（Ask/Confirm/Report 动作列表）
  - ④ DM 生成回复（LLM-2）
  - 回复对比（原始 vs DM）
  - 本轮新增 Worksheet 字段（delta）
  - 累积 Worksheet 状态（可折叠）

用法::

    python examples/genie_trace_demo.py
    python examples/genie_trace_demo.py --seed 42
    python examples/genie_trace_demo.py --index 5
    python examples/genie_trace_demo.py --output /tmp/trace.md --verbose
    python examples/genie_trace_demo.py --worksheet schema/anyihua_genie_worksheet.json
    python examples/genie_trace_demo.py --worksheet schema/restaurant_booking_genie_worksheet.json

Worksheet 文件说明::

    Genie 使用预生成的 *_genie_worksheet.json 文件（或 CSV 格式）。
    默认使用 schema/anyihua_genie_worksheet.json（由 build_schema_data.py 生成）。
    若文件不存在，请先运行::

        python examples/build_schema_data.py --genie-only
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
from contextmind.modes.genie import GenieTracker
from contextmind.scenarios import get_anyihua_scenario

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
# 默认 Worksheet：安逸花外呼业务（由 build_schema_data.py --genie-only 生成）
_DEFAULT_WORKSHEET_PATH = _PROJECT_ROOT / "schema" / "anyihua_genie_worksheet.json"
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


def _load_session(index: Optional[int], seed: Optional[int],
                  data_path: Path = _DATA_PATH) -> Dict[str, Any]:
    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)
    sessions = data if isinstance(data, list) else data.get("sessions", [])
    if index is not None:
        return sessions[index % len(sessions)]
    if seed is not None:
        random.seed(seed)
    return random.choice(sessions)


async def run_trace(
    session: Dict[str, Any],
    verbose: bool = False,
    worksheet_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """运行单条会话的 Genie Worksheets 追踪，返回结构化结果（含每步完整 I/O）。

    追踪格式与 pytod_trace_demo.py / fnctod_trace_demo.py 对齐：每轮包含
    原始对话（坐席先说，用户后说）、六步流水线各阶段结果、
    worksheet state delta、累积状态。

    Args:
        session:        对话会话字典。
        verbose:        是否打印详细日志。
        worksheet_path: Worksheet 文件路径（.json 或 .csv）；
                        若为 None 则使用默认 anyihua_genie_worksheet.json。
    """
    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    history = session.get("对话历史", [])
    # 每条 entry 格式：{"机器人": "坐席说的话", "用户": "用户回复"}
    # preceding_agent = entry[i]['机器人']：坐席在用户发言「之前」说的话（过程上下文）
    # following_agent = entry[i+1]['机器人']（或坐席回复）：坐席对用户的「实际回应」（对比基准）
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

    # 将会话中的用户信息注入场景描述，让 LLM 了解用户的账户详情，
    # 避免重复询问已知信息（如身份、额度等）。与其他 trace_demo 保持一致。
    user_info = session.get("用户信息", "")
    scene_description = _SCENARIO_CONTEXT
    if user_info:
        scene_description = f"{_SCENARIO_CONTEXT}\n\n## 本次通话用户信息\n{user_info}"

    # Worksheet 字段信息（供 metadata 展示）
    worksheet_fields: List[str] = []
    intent_name: str = ""

    if llm_available:
        llm_client = AdkLLMClient(config=config)
        scenario_config = get_anyihua_scenario()
        # 覆盖场景描述，注入本次通话用户信息
        scenario_config.description = scene_description

        ws_path = worksheet_path or _DEFAULT_WORKSHEET_PATH
        tracker = GenieTracker.from_scenario(
            llm_client=llm_client,
            scenario_config=scenario_config,
            worksheet_path=ws_path,
        )

        # 收集 Worksheet 字段信息用于 metadata
        if tracker._executor.intent:
            intent_name = tracker._executor.intent.name
            worksheet_fields = [pf.name for pf in tracker._executor._policy_fields]

        prev_worksheet_state: Dict[str, Any] = {}
        n_turns = len(paired_turns)
        for idx, (utt, preceding_agent, following_agent) in enumerate(paired_turns):
            print(f"  → 处理第 {idx + 1}/{n_turns} 轮...", flush=True)
            try:
                result = await asyncio.wait_for(
                    tracker.process_turn(utt),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                result = {
                    "response": "(超时: LLM 调用超时，请检查 API 连接是否正常)",
                    "worksheet_state": dict(tracker.get_current_state()),
                    "extracted_fields": {},
                    "is_complete": tracker.is_complete,
                    "next_field": None,
                    "missing_required": [],
                    "errors": ["LLM 调用超时"],
                    "agent_acts": [],
                    "confirmed_fields": [],
                    "rejected_fields": [],
                    "dispatched_apis": [],
                }
                print(f"  ⚠️  第 {idx + 1} 轮 LLM 调用超时", flush=True)
            except Exception as exc:
                result = {
                    "response": f"(error: {exc})",
                    "worksheet_state": dict(tracker.get_current_state()),
                    "extracted_fields": {},
                    "is_complete": tracker.is_complete,
                    "next_field": None,
                    "missing_required": [],
                    "errors": [str(exc)],
                    "agent_acts": [],
                    "confirmed_fields": [],
                    "rejected_fields": [],
                    "dispatched_apis": [],
                }
                print(f"  ⚠️  第 {idx + 1} 轮 LLM 调用失败: {exc}", flush=True)

            response_text = result.get("response", "")
            worksheet_state: Dict[str, Any] = result.get("worksheet_state", {})
            extracted_fields: Dict[str, Any] = result.get("extracted_fields", {})
            agent_acts: List[str] = result.get("agent_acts", [])
            confirmed_fields: List[str] = result.get("confirmed_fields", [])
            rejected_fields: List[str] = result.get("rejected_fields", [])
            dispatched_apis: List[str] = result.get("dispatched_apis", [])
            is_complete: bool = result.get("is_complete", False)
            next_field: Optional[str] = result.get("next_field")
            missing_required: List[str] = result.get("missing_required", [])
            errors: List[str] = result.get("errors", [])

            # state_delta：本轮新填入的字段（与上轮累积状态对比）
            state_delta = {
                k: v
                for k, v in worksheet_state.items()
                if k not in prev_worksheet_state or prev_worksheet_state[k] != v
            }

            # 获取本轮各字段的状态（EMPTY/FILLED/PENDING_CONFIRM/CONFIRMED）
            field_statuses = dict(tracker._executor.state.field_statuses)

            turn_record = {
                "turn": idx + 1,
                "user": utt,
                "preceding_agent": preceding_agent,   # 坐席在本轮用户发言前说的话
                "original_agent": following_agent,    # 坐席对本轮用户的实际回应（对比基准）
                # Step 1: 确认流
                "confirmed_fields": confirmed_fields,
                "rejected_fields": rejected_fields,
                # Step 2: 语义解析（LLM-1）
                "extracted_fields": extracted_fields,
                # Step 3: Worksheet 状态
                "field_statuses": field_statuses,
                "parse_errors": errors,
                # Step 4: on_success dispatch
                "dispatched_apis": dispatched_apis,
                # Step 5: AgentActs
                "agent_acts": agent_acts,
                # Step 6: 回复生成（LLM-2）
                "response": response_text,
                # 整体状态
                "is_complete": is_complete,
                "next_field": next_field,
                "missing_required": missing_required,
                "state_delta": state_delta,
                "cumulative_state": dict(worksheet_state),
            }
            turns_results.append(turn_record)
            prev_worksheet_state = dict(worksheet_state)

            if verbose:
                print(f"[Turn {idx+1}] user: {utt[:80]}")
                print(f"  [Step1-Confirm] confirmed={confirmed_fields} rejected={rejected_fields}")
                print(f"  [Step2-Parse ] extracted={extracted_fields}")
                print(f"  [Step4-API   ] dispatched={dispatched_apis}")
                print(f"  [Step5-Acts  ] {agent_acts}")
                print(f"  [Step6-DM    ] response: {response_text[:100]}")
                print(f"  [State] complete={is_complete}, next={next_field}")
    else:
        for idx, (utt, preceding_agent, following_agent) in enumerate(paired_turns):
            turns_results.append({
                "turn": idx + 1,
                "user": utt,
                "preceding_agent": preceding_agent,
                "original_agent": following_agent,
                "confirmed_fields": [],
                "rejected_fields": [],
                "extracted_fields": {},
                "field_statuses": {},
                "parse_errors": [],
                "dispatched_apis": [],
                "agent_acts": [],
                "response": "⚠️ LLM 未配置",
                "is_complete": False,
                "next_field": None,
                "missing_required": [],
                "state_delta": {},
                "cumulative_state": {},
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "Genie Worksheets（声明式策略 + 六步流水线）",
            "llm_available": llm_available,
            "scenario": "安逸花外呼",
            "intent_name": intent_name,
            "worksheet_fields": worksheet_fields,
            "worksheet_path": str(worksheet_path or _DEFAULT_WORKSHEET_PATH),
        },
        "session_id": session.get("session_id", ""),
        "用户信息": session.get("用户信息", ""),
        "actual_response": session.get("坐席回复", ""),
        "turns": turns_results,
    }


def _format_messages_collapsible(messages: List[Dict[str, str]], label: str) -> List[str]:
    """将 LLM 消息列表渲染为可折叠的 <details> HTML 块（与其他 trace_demo 一致）。"""
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
        role_label = {
            "system": "**System**",
            "user": "**User**",
            "assistant": "**Assistant**",
        }.get(role, f"**{role}**")
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
    """将 trace 字典渲染为 Markdown 报告（格式与 pytod_trace_demo / fnctod_trace_demo 对齐）。

    每轮展示：
    - 原始对话（坐席先说，用户后说）
    - ① 语义解析（LLM-1）— 提取字段赋值
    - ② PolicyExecutor 状态更新 — 字段状态
    - ③ AgentActs — 确定性动作列表（Ask/Confirm/Report）
    - ④ DM 生成回复（LLM-2）
    - 回复对比（原始 vs DM）
    - 本轮新增 Worksheet 字段（delta）
    - 累积 Worksheet 状态（可折叠）
    """
    meta = trace["metadata"]
    llm_ok = meta["llm_available"]
    ws_fields = meta.get("worksheet_fields", [])
    intent_name = meta.get("intent_name", "")

    lines = [
        "# Genie Worksheets 追踪报告",
        "",
        "| 字段 | 值 |",
        "|---|---|",
        f"| 时间 | {meta['timestamp']} |",
        f"| 算法 | {meta['algorithm']} |",
        f"| 场景 | {meta.get('scenario', 'N/A')} |",
        f"| 会话 ID | `{trace.get('session_id', 'N/A')}` |",
        f"| LLM | {'✅ 可用' if llm_ok else '❌ 未配置'} |",
        f"| Worksheet | `{Path(meta.get('worksheet_path', '')).name}` |",
        "",
    ]

    user_info = trace.get("用户信息")
    if user_info:
        lines += [f"**用户信息**: {user_info}", ""]

    if intent_name:
        lines.append(f"**意图**: `{intent_name}`")
    if ws_fields:
        lines.append(
            f"**Worksheet 字段**: {', '.join(f'`{f}`' for f in ws_fields)}"
        )
    lines += ["", "---", ""]

    # Genie 六步流水线说明
    lines += [
        "## Genie 六步流水线",
        "",
        "| 步骤 | 组件 | 说明 |",
        "|---|---|---|",
        "| Step 1 | 确认流检查 | 检测 PENDING_CONFIRM 字段，处理 yes/no |",
        "| Step 2 | SemanticParser（LLM-1）| 从用户话语提取字段赋值 |",
        "| Step 3 | PolicyExecutor | fill_batch() 推进字段状态 |",
        "| Step 4 | on_success dispatch | 触发字段关联 API 回调 |",
        "| Step 5 | AgentActs 计算 | 确定性：Ask / AskForConfirmation / Report |",
        "| Step 6 | ResponseGenerator（LLM-2）| 根据 AgentActs 生成自然语言回复 |",
        "",
        "---",
        "",
    ]

    for t in trace.get("turns", []):
        lines += [
            f"### Turn {t['turn']}",
            "",
        ]

        # 原始对话（机器人先说，用户后说）
        preceding_agent = t.get("preceding_agent", "")
        orig_agent = t.get("original_agent", "")
        lines += ["**原始对话**:", ""]
        if preceding_agent:
            lines.append(f"{_AGENT_ICON} **机器人**: {preceding_agent}")
            lines.append("")
        lines.append(f"{_USER_ICON} **用户**: {t['user']}")
        lines.append("")

        # Step 1: 确认流
        confirmed = t.get("confirmed_fields", [])
        rejected = t.get("rejected_fields", [])
        if confirmed or rejected:
            confirm_parts = []
            if confirmed:
                confirm_parts.append(f"✅ 已确认: {', '.join(f'`{f}`' for f in confirmed)}")
            if rejected:
                confirm_parts.append(f"❌ 已拒绝: {', '.join(f'`{f}`' for f in rejected)}")
            lines += [
                f"**Step 1 — 确认流**: {' | '.join(confirm_parts)}",
                "",
            ]
        else:
            lines += ["**Step 1 — 确认流**: （无待确认字段）", ""]

        # Step 2: 语义解析（LLM-1）
        extracted = t.get("extracted_fields", {})
        parse_errors = t.get("parse_errors", [])
        if extracted:
            lines += [
                "**Step 2 — 语义解析（LLM-1）**:",
                "```json",
                json.dumps(extracted, ensure_ascii=False, indent=2),
                "```",
                "",
            ]
        else:
            lines += ["**Step 2 — 语义解析（LLM-1）**: （未提取到字段值）", ""]
        if parse_errors:
            lines += [f"⚠️ 校验错误: {'; '.join(parse_errors)}", ""]

        # Step 3: PolicyExecutor 字段状态
        field_statuses = t.get("field_statuses", {})
        if field_statuses:
            _STATUS_LABELS = {
                "empty": "空",
                "filled": "已填",
                "pending_confirm": "待确认",
                "confirmed": "已确认",
            }
            status_parts = [
                f"`{k}`: {_STATUS_LABELS.get(v, v)}"
                for k, v in field_statuses.items()
            ]
            lines += [
                f"**Step 3 — Worksheet 状态**: {' | '.join(status_parts)}",
                "",
            ]
        else:
            lines += ["**Step 3 — Worksheet 状态**: （无状态变化）", ""]

        # Step 4: on_success dispatch
        dispatched = t.get("dispatched_apis", [])
        if dispatched:
            lines += [
                f"**Step 4 — on_success dispatch**: {', '.join(f'`{a}`' for a in dispatched)}",
                "",
            ]
        else:
            lines += ["**Step 4 — on_success dispatch**: （无 API 触发）", ""]

        # Step 5: AgentActs
        agent_acts = t.get("agent_acts", [])
        if agent_acts:
            acts_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(agent_acts))
            lines += [
                "**Step 5 — AgentActs**:",
                "```",
                acts_text,
                "```",
                "",
            ]
        else:
            is_complete = t.get("is_complete", False)
            lines += [
                f"**Step 5 — AgentActs**: "
                f"{'（Worksheet 已完成）' if is_complete else '（无动作）'}",
                "",
            ]

        # Step 6: DM 生成回复（LLM-2）
        new_response = t.get("response") or "(空)"
        lines += [
            "**Step 6 — DM 生成回复（LLM-2）**:",
            f"> {new_response}",
            "",
        ]

        # 回复对比（仅当存在原始机器人回复时）
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

        # 本轮新增 Worksheet 字段（delta）
        state_delta = t.get("state_delta", {})
        if state_delta:
            lines += [
                "**本轮新增 Worksheet 字段**:",
                "```json",
                json.dumps(state_delta, ensure_ascii=False, indent=2),
                "```",
                "",
            ]

        # Worksheet 完成状态
        is_complete = t.get("is_complete", False)
        next_field = t.get("next_field")
        missing = t.get("missing_required", [])
        status_icon = "✅ 已完成" if is_complete else "⏳ 进行中"
        status_parts = [status_icon]
        if next_field:
            status_parts.append(f"下一个待填字段: `{next_field}`")
        if missing:
            status_parts.append(f"未填必填字段: {', '.join(f'`{f}`' for f in missing)}")
        lines += [f"**Worksheet 状态**: {' | '.join(status_parts)}", ""]

        # 累积 Worksheet 状态（全量，可折叠）
        cumstate = t.get("cumulative_state", {})
        active_cum = {k: v for k, v in cumstate.items() if v not in (None, "", [])}
        if active_cum:
            lines += [
                "<details>",
                "<summary>📊 累积 Worksheet 状态（点击展开）</summary>",
                "",
                "```json",
                json.dumps(active_cum, ensure_ascii=False, indent=2),
                "```",
                "",
                "</details>",
                "",
            ]

        lines += ["---", ""]

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genie Worksheets 全链路追踪脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python examples/genie_trace_demo.py
  python examples/genie_trace_demo.py --seed 42 --verbose
  python examples/genie_trace_demo.py --index 0
  python examples/genie_trace_demo.py --worksheet schema/anyihua_genie_worksheet.json
  python examples/genie_trace_demo.py --output /tmp/genie_trace.md --verbose
  python examples/genie_trace_demo.py --data resources/data/chat_test_500.json --index 5

Worksheet 文件生成:
  python examples/build_schema_data.py --genie-only
        """,
    )
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument(
        "--data", dest="data", type=str, default=None,
        help=(
            "对话数据文件路径（JSON，默认 resources/data/chat_test_100.json）。"
            "支持 chat_test_100.json / chat_test_500.json 或任意同格式文件。"
        ),
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Markdown 输出路径（默认 output/genie_trace_output.md）；父目录不存在时自动创建",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="日志级别（默认 INFO；--verbose 同时影响追踪详情输出）",
    )
    parser.add_argument(
        "--worksheet", dest="worksheet", type=str, default=None,
        help=(
            "Worksheet 文件路径（.json 或 .csv）。"
            "推荐使用预生成的 *_genie_worksheet.json（由 build_schema_data.py --genie-only 生成）。"
            "若不提供则默认使用 schema/anyihua_genie_worksheet.json。"
        ),
    )
    args = parser.parse_args()

    # ── 日志设置 ──
    from contextmind.infra.logger import setup_logging, LogLevel
    log_level = LogLevel.DEBUG if args.verbose or args.log_level == "DEBUG" else (
        LogLevel[args.log_level] if hasattr(LogLevel, args.log_level) else LogLevel.INFO
    )
    setup_logging(level=log_level, save_to_file=True, log_dir="log", log_name="genie_trace_demo")

    data_path = Path(args.data) if args.data else _DATA_PATH
    if not data_path.exists():
        print(f"❌ 数据文件不存在: {data_path}", file=sys.stderr)
        sys.exit(1)
    print(f"✓ 使用数据文件: {data_path}")

    # 确定 Worksheet 路径
    if args.worksheet:
        worksheet_path = Path(args.worksheet)
        if not worksheet_path.exists():
            print(f"❌ Worksheet 文件不存在: {worksheet_path}", file=sys.stderr)
            sys.exit(1)
        print(f"✓ 已指定 Worksheet: {worksheet_path}")
    else:
        worksheet_path = _DEFAULT_WORKSHEET_PATH
        if worksheet_path.exists():
            print(f"✓ 使用默认 Worksheet: {worksheet_path}")
        else:
            print(
                f"⚠️  默认 Worksheet 文件不存在: {worksheet_path}\n"
                "   请先运行: python examples/build_schema_data.py --genie-only\n"
                "   或通过 --worksheet 指定 Worksheet 文件路径",
                file=sys.stderr,
            )
            sys.exit(1)

    session = _load_session(args.index, args.seed, data_path)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")
    print("正在执行 Genie Worksheets 追踪（每轮 LLM 调用超时 120s）...", flush=True)

    trace = asyncio.run(
        run_trace(session, verbose=args.verbose, worksheet_path=worksheet_path)
    )
    print("✓ 追踪完成", flush=True)

    # 输出路径（无论是否自定义，都确保父目录存在）
    if args.output:
        md_path = Path(args.output)
    else:
        md_path = _PROJECT_ROOT / "output" / "genie_trace_output.md"
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
        print("⚠️  LLM 未配置，Genie 追踪未执行。请在 .env 中配置 LLM_API_KEY 后重新运行。")


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
