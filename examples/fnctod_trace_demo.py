"""
FnCTOD 对话追踪脚本

展示 FnCTOD（Function Calling for Task-Oriented Dialogue）算法在
客服场景中的运行过程：通过 ADK 原生 Function Calling 实现
结构化对话状态提取，并将全链路 I/O 写入 Markdown 报告。

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
from contextmind.modes.fnctod.schemas import get_callcenter_function_schema
from contextmind.modes.pytod.schemas import load_schema_from_dict

_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"
_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："

_SCENARIO_CONTEXT = (
    "这是一个客服对话场景。"
    "坐席代表客服中心接听用户来电，目标是解答用户问题、处理投诉并提供帮助。"
)


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
    """运行单条会话的 FnCTOD 追踪，返回结构化结果。

    Args:
        session:     对话会话字典。
        verbose:     是否打印详细日志。
        domain_spec: 外部传入的 DomainSpec（来自 ``--schema``）；
                     若为 None 则使用预定义的客服场景 Schema。
    """
    schema = domain_spec if domain_spec is not None else get_callcenter_function_schema()
    fm = FunctionManager()
    fm.add_domain(schema)

    try:
        config = LLMConfig.from_env()
        llm_available = True
    except Exception:
        llm_available = False

    # 提取对话轮次
    history = session.get("对话历史", [])
    user_turns = [utt[len(_USER_PREFIX):] for utt in history if utt.startswith(_USER_PREFIX)]
    if not user_turns:
        return {"error": "no user turns found", "session_id": session.get("session_id", "")}

    turns_results: List[Dict[str, Any]] = []

    if llm_available:
        agent = FnCTODTracker(function_manager=fm, config=config)
        for i, utt in enumerate(user_turns):
            try:
                updates = await agent.process_turn(utt)
            except Exception as exc:
                updates = {"error": str(exc)}
            turns_results.append({
                "turn": i + 1,
                "user": utt[:120],
                "state_updates": updates,
                "cumulative_state": dict(agent.get_current_state()),
            })
            if verbose:
                print(f"[Turn {i+1}] {utt[:80]}")
                print(f"  → updates: {updates}")
    else:
        for i, utt in enumerate(user_turns):
            turns_results.append({
                "turn": i + 1,
                "user": utt[:120],
                "state_updates": "⚠️ LLM 未配置",
                "cumulative_state": {},
            })

    return {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "algorithm": "FnCTOD (ADK native function calling)",
            "llm_available": llm_available,
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


def _render_markdown(trace: Dict[str, Any]) -> str:
    lines = [
        "# FnCTOD 追踪报告",
        "",
        f"**时间**: {trace['metadata']['timestamp']}",
        f"**算法**: {trace['metadata']['algorithm']}",
        f"**会话 ID**: {trace.get('session_id', 'N/A')}",
        f"**用户信息**: {trace.get('用户信息', 'N/A')}",
        "",
        "## Schema 配置",
        "",
        f"**注册域**: {trace.get('schema_domains', [])}",
        "",
    ]
    for d in trace.get("schema_parameters", []):
        lines.append(f"**{d['domain']}** 参数: {', '.join(d['params'])}")
    lines += ["", "## 对话追踪", ""]
    for t in trace.get("turns", []):
        lines += [
            f"### Turn {t['turn']}",
            f"**用户**: {t['user']}",
            "",
            "**状态更新**:",
            "```json",
            json.dumps(t["state_updates"], ensure_ascii=False, indent=2),
            "```",
            "",
            "**累积状态**:",
            "```json",
            json.dumps(t["cumulative_state"], ensure_ascii=False, indent=2),
            "```",
            "",
        ]
    lines += [
        "## 实际坐席回复（参考）",
        "",
        trace.get("actual_response", "（无）"),
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="FnCTOD 全链路追踪脚本")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--index", type=int, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--schema", type=str, default=None,
        help="schema.json 路径（SGD 或 FnCTOD 格式）；若提供则替换预定义场景 Schema",
    )
    args = parser.parse_args()

    if not _DATA_PATH.exists():
        print(f"❌ 数据文件不存在: {_DATA_PATH}", file=sys.stderr)
        sys.exit(1)

    domain_spec: Optional[DomainSpec] = None
    if args.schema:
        schema_path = Path(args.schema)
        if not schema_path.exists():
            print(f"❌ Schema 文件不存在: {schema_path}", file=sys.stderr)
            sys.exit(1)
        domain_spec = _load_domain_spec_from_schema_file(schema_path)
        print(f"✓ 已加载外部 Schema: {schema_path} (domain={domain_spec.name})")

    session = _load_session(args.index, args.seed)
    print(f"✓ 已加载会话: {session.get('session_id', 'N/A')}")

    trace = asyncio.run(run_trace(session, verbose=args.verbose, domain_spec=domain_spec))

    md = _render_markdown(trace)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"✓ 报告已写入: {args.output}")
    else:
        output_path = _PROJECT_ROOT / "examples" / "fnctod_trace_output.md"
        output_path.write_text(md, encoding="utf-8")
        print(f"✓ 报告已写入: {output_path}")

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
