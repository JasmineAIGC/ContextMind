"""
安逸花外呼促活服务 · PyTOD 坐席回复质量提升 Web Demo

通过 Gradio 界面从 chat_test_100.json 中选择一条会话，
使用 PyTODTracker 三步流程（动作解析器 → 执行引擎 → 对话管理器）
生成更优质的坐席回复，并与实际坐席回复进行对比展示。

流程说明:
    1. 从下拉列表中选择一条会话
    2. 点击「生成回复」按钮
    3. PyTOD 三步流程：解析 CRM → 执行程序 → 生成回复
    4. 对比 PyTOD 生成回复 vs 实际坐席回复

环境要求:
    QWEN3_API_KEY=your_key_here
    LLM_BASE_URL=https://your-endpoint/v1

用法:
    cd /path/to/ContextMind
    python examples/anyihua_generation_demo.py
    python examples/anyihua_generation_demo.py --port 7861
    python examples/anyihua_generation_demo.py --share
    python examples/anyihua_generation_demo.py --verbose  # 控制台打印详细 PyTOD 步骤日志
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

# 添加项目根目录到 Python 路径，使得可以直接运行而无需安装
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import gradio as gr

from contextmind.infra.llm_client import SimpleLLMClient as LLMClient, LLMConfig
from contextmind.modes.pytod import PyTODPromptBuilder, PyTODTracker
from contextmind.modes.pytod.prompts import ConversationTurn
from contextmind.scenarios.anyihua.generation import ANYIHUA_SCHEMA, build_generation_engine

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_PATH = _PROJECT_ROOT / "resources" / "data" / "chat_test_100.json"

_AGENT_PREFIX = "坐席："
_USER_PREFIX = "用户："


# --------------------------------------------------------------------------- #
# 核心函数：单条会话在线生成
# --------------------------------------------------------------------------- #


async def run_online_generation(
    session: Dict[str, Any],
    llm_client: LLMClient,
    max_history_turns: int = 10,
    verbose: bool = False,
) -> Dict[str, Any]:
    """
    使用 PyTODTracker 对单条会话进行在线回复生成。

    参数:
        session:           单条 chat_test_100.json 记录
        llm_client:        LLMClient 实例
        max_history_turns: 保留的最大历史轮数（默认 10）
        verbose:           是否将详细步骤日志打印到控制台

    返回:
        包含以下键的字典:
            - response:     PyTOD 生成的回复文本
            - program_text: 动作解析器生成的 PyTOD 程序
            - state:        执行引擎累积的变量状态
            - execution:    ProgramExecutionResult | None
            - actual_reply: 实际坐席回复（来自数据集）
            - label:        人工校验标签
    """
    engine = build_generation_engine(session)

    builder = PyTODPromptBuilder(
        schema=ANYIHUA_SCHEMA,
        max_history_turns=max_history_turns,
        response_language="中文",
    )

    tracker = PyTODTracker(
        llm_client=llm_client,
        execution_engine=engine,
        prompt_builder=builder,
        scenario_name="安逸花外呼",
        max_history_turns=max_history_turns,
        scenario_context=(
            "这是一个外呼小额借款推介场景（安逸花外呼促活）。"
            "坐席代表安逸花/马上消费金融主动致电老用户，目标是激活用户闲置的借款额度。"
            "标准流程：① 核实用户身份（姓名/手机尾号）→ ② 告知可用额度和利率 → "
            "③ 解答疑问（还款方式、账单争议等）→ ④ 引导用户在 APP 完成借款操作 → "
            "⑤ 确认无未解决诉求后礼貌告别。"
            "注意：核实身份前不得告知账户详细信息；若用户有未解决诉求则不得直接告别。"
        ),
    )

    # Replay 对话历史（不调用 LLM，直接注入 ConversationTurn）
    # 目标：将历史中除最后一条用户发言之外的所有轮次注入 tracker.history，
    # 最后一条用户发言作为 process_turn() 的新鲜输入，不在此处注入。
    # 这样 LLM 在 [HISTORY] 中看到的是"已发生的"历史，
    # 在 [CURRENT] 中看到的是"当前用户正在说"的内容，语义不会重复。
    history = session["对话历史"]
    i = 0
    while i < len(history) - 2:  # 停在倒数第二轮之前，不含最后一对（坐席+用户）
        if (
            history[i].startswith(_AGENT_PREFIX)
            and history[i + 1].startswith(_USER_PREFIX)
        ):
            system_utt = history[i].removeprefix(_AGENT_PREFIX)
            user_utt = history[i + 1].removeprefix(_USER_PREFIX)
            tracker.history.append(ConversationTurn(role="assistant", content=system_utt))
            tracker.history.append(ConversationTurn(role="user", content=user_utt))
            i += 2
        else:
            i += 1
    # 将倒数第二轮坐席发言（history[-2]）也注入，使 LLM 知道坐席上一步说了什么，
    # 但不注入最后一条用户发言——它将作为 process_turn() 的新鲜输入
    if len(history) >= 2 and history[-2].startswith(_AGENT_PREFIX):
        tracker.history.append(
            ConversationTurn(
                role="assistant",
                content=history[-2].removeprefix(_AGENT_PREFIX),
            )
        )

    # 处理最后一轮用户发言
    last_user = history[-1].removeprefix(_USER_PREFIX)
    if verbose:
        print(f"\n[Generation Verbose] 会话: {session['session_id']}")
        print(f"[Generation Verbose] 用户输入: {last_user}")
    result = await tracker.process_turn(user_utterance=last_user)

    if verbose:
        print(f"[Generation Verbose] PyTOD 程序:\n{result.get('program_text', '(无)')}")
        if result.get("state"):
            import json as _json
            print(f"[Generation Verbose] 执行状态: {_json.dumps(result['state'], ensure_ascii=False)}")
        print(f"[Generation Verbose] 生成回复: {result['response']}")
        print(f"[Generation Verbose] 实际回复: {session['坐席回复']}")

    return {
        "response": result["response"],
        "program_text": result["program_text"],
        "state": result["state"],
        "execution": result["execution"],
        "actual_reply": session["坐席回复"],
        "label": session.get("人工校验", ""),
    }


# --------------------------------------------------------------------------- #
# Gradio Web Demo
# --------------------------------------------------------------------------- #


def load_data(data_path: Path) -> List[Dict[str, Any]]:
    with open(data_path, encoding="utf-8") as f:
        return json.load(f)


def build_session_choices(data: List[Dict[str, Any]]) -> List[str]:
    """生成下拉列表选项：'序号 | 标签 | 会话ID后8位'"""
    choices = []
    for i, d in enumerate(data):
        label = d.get("人工校验", "无标签命中")
        sid = d["session_id"][-8:]
        choices.append(f"{i:03d} | {label} | …{sid}")
    return choices


def format_history(session: Dict[str, Any]) -> str:
    """将对话历史格式化为可读文本。"""
    lines = []
    for turn in session["对话历史"]:
        lines.append(turn)
    return "\n".join(lines)


def on_session_select(
    choice: str,
    data: List[Dict[str, Any]],
) -> tuple:
    """用户从下拉列表中选择会话后，更新信息面板。"""
    if not choice:
        return "", "", "", ""
    idx = int(choice.split("|")[0].strip())
    session = data[idx]
    label = session.get("人工校验", "无标签命中")
    user_info = session.get("用户信息", "")
    history_text = format_history(session)
    actual_reply = session.get("坐席回复", "")
    return label, user_info, history_text, actual_reply


def on_generate(
    choice: str,
    data: List[Dict[str, Any]],
    llm_client_holder: List,  # mutable container [LLMClient | None]
    verbose: bool = False,
) -> tuple:
    """点击「生成回复」时运行 PyTOD，返回结果文本。"""
    if not choice:
        return "请先从下拉列表中选择一条会话。", "", ""

    idx = int(choice.split("|")[0].strip())
    session = data[idx]

    llm = llm_client_holder[0]
    if llm is None:
        return (
            "⚠️ LLM 客户端未初始化。\n请检查 .env 文件中的 QWEN3_API_KEY / LLM_BASE_URL 配置。",
            "",
            "",
        )

    try:
        result = asyncio.run(run_online_generation(session, llm, verbose=verbose))
    except Exception as exc:
        return f"❌ 生成失败: {exc}", "", ""

    program_text = result["program_text"] or "（无程序）"
    state_text = (
        json.dumps(result["state"], ensure_ascii=False, indent=2)
        if result["state"]
        else "（无执行状态）"
    )
    return result["response"], program_text, state_text


def create_ui(
    data: List[Dict[str, Any]],
    llm_client_holder: List,
    verbose: bool = False,
) -> gr.Blocks:
    """构建 Gradio Blocks 界面。"""
    choices = build_session_choices(data)

    with gr.Blocks(title="安逸花 PyTOD 坐席回复质量提升") as app:
        gr.Markdown(
            "# 🤖 安逸花外呼 · PyTOD 坐席回复质量提升\n"
            "从下拉列表中选择一条会话，点击「生成回复」，对比 PyTOD 生成回复与实际坐席回复。"
        )

        # 会话选择
        with gr.Row():
            session_dropdown = gr.Dropdown(
                choices=choices,
                label="选择会话（序号 | 人工校验标签 | 会话ID）",
                interactive=True,
                scale=4,
            )
            label_box = gr.Textbox(label="人工校验标签", interactive=False, scale=1)

        # 会话信息
        with gr.Row():
            user_info_box = gr.Textbox(
                label="用户信息",
                lines=3,
                interactive=False,
                scale=1,
            )

        # 对话历史 + 实际坐席回复
        with gr.Row():
            history_box = gr.Textbox(
                label="对话历史",
                lines=12,
                interactive=False,
                scale=3,
            )
            actual_reply_box = gr.Textbox(
                label="实际坐席回复",
                lines=12,
                interactive=False,
                scale=2,
            )

        # 生成按钮
        generate_btn = gr.Button("🚀 生成回复（PyTOD）", variant="primary")

        # PyTOD 结果
        with gr.Row():
            pytod_reply_box = gr.Textbox(
                label="🤖 PyTOD 生成回复",
                lines=6,
                interactive=False,
                scale=3,
            )
        with gr.Row():
            program_box = gr.Textbox(
                label="📝 PyTOD 程序",
                lines=3,
                interactive=False,
                scale=2,
            )
            state_box = gr.Textbox(
                label="📊 执行引擎状态",
                lines=3,
                interactive=False,
                scale=2,
            )

        # 事件绑定
        session_dropdown.change(
            fn=lambda choice: on_session_select(choice, data),
            inputs=[session_dropdown],
            outputs=[label_box, user_info_box, history_box, actual_reply_box],
        )

        generate_btn.click(
            fn=lambda choice: on_generate(choice, data, llm_client_holder, verbose),
            inputs=[session_dropdown],
            outputs=[pytod_reply_box, program_box, state_box],
        )

    return app


# --------------------------------------------------------------------------- #
# 命令行入口
# --------------------------------------------------------------------------- #


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="安逸花外呼 PyTOD 坐席回复质量提升 Web Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
用法示例:
  python examples/anyihua_generation_demo.py
  python examples/anyihua_generation_demo.py --port 7861
  python examples/anyihua_generation_demo.py --share
        """,
    )
    parser.add_argument(
        "--data",
        default=str(_DEFAULT_DATA_PATH),
        help=f"数据文件路径（默认: {_DEFAULT_DATA_PATH}）",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=7860,
        help="Web 服务器端口（默认: 7860）",
    )
    parser.add_argument(
        "--share",
        action="store_true",
        help="创建公共分享链接（Gradio share）",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="将 PyTOD 每步详细日志打印到控制台（程序文本、API 执行结果、生成回复）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 加载数据
    data_path = Path(args.data)
    if not data_path.exists():
        raise FileNotFoundError(f"数据文件不存在: {data_path}")
    data = load_data(data_path)
    print(f"✅ 加载数据: {data_path}（共 {len(data)} 条会话）")

    # 初始化 LLM 客户端（允许失败——界面仍可打开，生成时报错）
    llm_client_holder: List = [None]
    try:
        config = LLMConfig.from_env()
        llm_client_holder[0] = LLMClient(config)
        print(f"✅ LLM 客户端初始化成功 (model: {config.model})")
    except Exception as exc:
        print(f"⚠️  LLM 客户端初始化失败: {exc}")
        print("   请检查 .env 文件中的 QWEN3_API_KEY 和 LLM_BASE_URL 配置")
        print("   界面仍可打开，但点击「生成回复」时将报错。")

    # 启动 Gradio
    app = create_ui(data, llm_client_holder, verbose=args.verbose)
    if args.verbose:
        print("✅ Verbose 模式已启用：每次生成回复将在此控制台打印详细日志")
    app.launch(
        server_name="0.0.0.0",
        server_port=args.port,
        share=args.share,
    )


if __name__ == "__main__":
    main()
