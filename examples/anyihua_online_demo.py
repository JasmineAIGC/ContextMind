"""
安逸花外呼促活服务 · PyTOD 在线生成演示

使用 PyTODTracker 对单条安逸花外呼会话进行在线回复生成，
演示 PyTOD 三步流程（动作解析器 → 执行引擎 → 对话管理器）
如何基于真实 CRM 数据生成回复，从根本上避免数据错误。

流程说明:
    1. 解析 用户信息 → 构建 mock CRM (ExecutionEngine)
    2. 加载 ANYIHUA_SCHEMA → 创建 PyTODPromptBuilder（Schema 驱动模式）
    3. 创建 PyTODTracker
    4. 将 对话历史 逐轮注入 tracker（不调用 LLM，仅更新 history）
    5. 对最后一轮用户发言调用 tracker.process_turn() → 生成回复
    6. 对比 PyTOD 生成回复 vs 实际坐席回复

环境要求:
    QWEN3_API_KEY=your_key_here
    LLM_BASE_URL=https://your-endpoint/v1

用法:
    cd /path/to/ContextMind
    python examples/anyihua_online_demo.py

    # 按标签筛选演示会话：
    python examples/anyihua_online_demo.py --label 数据错误

    # 演示多条（默认各类型各 1 条）：
    python examples/anyihua_online_demo.py --label 不当告别 --label 重复询问

    # 指定会话索引（0-based）：
    python examples/anyihua_online_demo.py --index 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from contextmind.infra.llm_client import SimpleLLMClient as LLMClient, LLMConfig
from contextmind.modes.pytod import PyTODPromptBuilder, PyTODTracker
from contextmind.modes.pytod.prompt_builder import ConversationTurn
from contextmind.scenarios.anyihua import ANYIHUA_SCHEMA, build_anyihua_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"


# --------------------------------------------------------------------------- #
# 核心函数：单条会话在线生成
# --------------------------------------------------------------------------- #


_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


async def run_online_generation(
    session: Dict[str, Any],
    llm_client: LLMClient,
    max_history_turns: int = 10,
) -> Dict[str, Any]:
    """
    使用 PyTODTracker 对单条会话进行在线回复生成。

    参数:
        session:           单条 chat_test_100.json 记录
        llm_client:        LLMClient 实例
        max_history_turns: 保留的最大历史轮数（默认 10）

    返回:
        包含以下键的字典:
            - response:     PyTOD 生成的回复文本
            - program_text: 动作解析器生成的 PyTOD 程序
            - state:        执行引擎累积的变量状态
            - execution:    ProgramExecutionResult | None
            - actual_reply: 实际坐席回复（来自数据集）
            - label:        人工校验标签
    """
    # ---- 构建 mock CRM（ExecutionEngine）----
    engine = build_anyihua_engine(session)

    # ---- 创建 Prompt Builder（Schema 驱动模式）----
    builder = PyTODPromptBuilder(
        schema=ANYIHUA_SCHEMA,
        max_history_turns=max_history_turns,
        response_language="中文",
    )

    # ---- 创建追踪器 ----
    tracker = PyTODTracker(
        llm_client=llm_client,
        execution_engine=engine,
        prompt_builder=builder,
        scenario_name="安逸花外呼",
        max_history_turns=max_history_turns,
    )

    # ---- Replay 对话历史（不调用 LLM，直接注入 ConversationTurn）----
    # 数据格式：交替出现"坐席：…"和"用户：…"，最后一项为用户最新发言
    history = session["对话历史"]
    i = 0
    while i < len(history) - 1:
        if (
            history[i].startswith(_AGENT_PREFIX)
            and i + 1 < len(history)
            and history[i + 1].startswith(_USER_PREFIX)
        ):
            system_utt = history[i].removeprefix(_AGENT_PREFIX)
            user_utt = history[i + 1].removeprefix(_USER_PREFIX)
            tracker.history.append(ConversationTurn(role="assistant", content=system_utt))
            tracker.history.append(ConversationTurn(role="user", content=user_utt))
            i += 2
        else:
            i += 1

    # ---- 处理最后一轮用户发言 ----
    last_user = history[-1].removeprefix(_USER_PREFIX)  # 去除 "用户：" 前缀
    result = await tracker.process_turn(user_utterance=last_user)

    return {
        "response": result["response"],
        "program_text": result["program_text"],
        "state": result["state"],
        "execution": result["execution"],
        "actual_reply": session["坐席回复"],
        "label": session.get("人工校验", ""),
    }


# --------------------------------------------------------------------------- #
# 打印辅助
# --------------------------------------------------------------------------- #


def print_session_demo(
    session: Dict[str, Any],
    result: Dict[str, Any],
    session_idx: int,
) -> None:
    """格式化打印单条会话的演示结果。"""
    sid = session["session_id"][-8:]
    label = session.get("人工校验", "")
    last_user = session["对话历史"][-1].removeprefix(_USER_PREFIX)

    print("\n" + "=" * 60)
    print(f"会话 {session_idx + 1} | ID: {sid} | 标签: {label}")
    print("=" * 60)

    # 展示最近几轮历史（最多 4 轮）
    recent_history = session["对话历史"][-8:-1]
    if recent_history:
        print("\n📋 最近对话历史（最后 4 轮）:")
        for line in recent_history[-8:]:
            print(f"  {line}")

    print(f"\n👤 用户最后发言: {last_user}")
    print(f"\n❌ 实际坐席回复:\n   {result['actual_reply'][:120]}")

    print(f"\n🤖 PyTOD 生成回复:\n   {result['response'][:120]}")

    if result["program_text"] and result["program_text"] != "NONE()":
        print(f"\n📝 PyTOD 程序:\n   {result['program_text']}")

    if result["state"]:
        print(f"\n📊 执行引擎状态: {result['state']}")


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼对话 PyTOD 在线生成演示",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data",
        default=str(_DEFAULT_DATA_PATH),
        help=f"数据文件路径（默认: {_DEFAULT_DATA_PATH}）",
    )
    parser.add_argument(
        "--label",
        action="append",
        dest="labels",
        default=[],
        choices=["数据错误", "重复询问", "不当告别", "答非所问", "无标签命中"],
        help="按人工校验标签筛选演示会话（可多次指定）",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=None,
        help="按 0-based 索引指定特定会话",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=1,
        help="最多演示多少条会话（默认 1）",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()

    # ---- 加载数据 ----
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_path}")

    with open(data_path, encoding="utf-8") as f:
        data = json.load(f)

    # ---- 选取演示会话 ----
    if args.index is not None:
        if args.index < 0 or args.index >= len(data):
            raise ValueError(f"索引 {args.index} 超出范围 [0, {len(data) - 1}]")
        sessions_to_demo = [(args.index, data[args.index])]
    elif args.labels:
        sessions_to_demo = [
            (i, d) for i, d in enumerate(data)
            if d.get("人工校验", "") in args.labels
        ][: args.max_sessions]
        if not sessions_to_demo:
            print(f"⚠️  未找到标签 {args.labels} 的会话")
            return
    else:
        # 默认：各类标签各取一条
        label_order = ["数据错误", "不当告别", "重复询问", "答非所问"]
        sessions_to_demo = []
        seen_labels: set = set()
        for i, d in enumerate(data):
            lbl = d.get("人工校验", "")
            if lbl in label_order and lbl not in seen_labels:
                sessions_to_demo.append((i, d))
                seen_labels.add(lbl)
            if len(sessions_to_demo) >= args.max_sessions:
                break

    # ---- 初始化 LLM 客户端 ----
    try:
        config = LLMConfig.from_env()
        llm = LLMClient(config)
        print(f"✅ LLM 客户端初始化成功 (model: {config.model})")
    except Exception as exc:
        print(f"⚠️  LLM 客户端初始化失败: {exc}")
        print("   请检查 .env 文件中的 QWEN3_API_KEY 和 LLM_BASE_URL 配置")
        return

    # ---- 逐条演示 ----
    print(f"\n📊 将演示 {len(sessions_to_demo)} 条会话\n")
    for session_idx, session in sessions_to_demo:
        try:
            result = await run_online_generation(session, llm)
            print_session_demo(session, result, session_idx)
        except Exception as exc:
            print(f"❌ 会话 {session_idx} 处理失败: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
