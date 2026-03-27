#!/usr/bin/env python3
"""
Gradio UI 组件定义

提供三个函数：
- ``create_layout()``   — 纯布局构建，不含任何事件绑定
- ``bind_events()``     — 将事件处理器绑定到已创建的组件
- ``create_gradio_ui()``— 组合以上两步，创建完整 UI
"""

import json
import gradio as gr

from .styles import CUSTOM_CSS, APP_VERSION


def format_state_as_json(state_dict):
    """将状态字典格式化为 JSON 字符串。

    Args:
        state_dict: 状态字典

    Returns:
        格式化的 JSON 字符串
    """
    if isinstance(state_dict, dict):
        return json.dumps(state_dict, ensure_ascii=False, indent=2)
    return str(state_dict)


def create_layout() -> tuple:
    """构建 Gradio 界面布局，不绑定任何事件。

    Returns:
        ``(app, components)`` — Gradio Blocks 应用实例和组件字典。
    """
    with gr.Blocks(
        title=f"ContextMind Demo v{APP_VERSION}",
        theme=gr.themes.Soft(),
        css=CUSTOM_CSS,
    ) as app:
        # 标题
        gr.Markdown("# 🧠 ContextMind 对话系统")
        gr.Markdown("上下文工程框架 · 智能对话 · 场景灵活 · 模式可选")

        # 主内容区 - 左右分栏
        with gr.Row():
            # 左侧列 - 对话区域
            with gr.Column(scale=3):
                gr.Markdown("### 💬 对话窗口")
                chatbot = gr.Chatbot(
                    height=500,
                    avatar_images=("👤", "🤖"),
                    elem_classes=["chatbot"],
                )
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="在这里输入您的消息...",
                        show_label=False,
                        scale=5,
                        container=False,
                        submit_btn=False,  # 禁用内置提交按钮，避免 Enter 同时触发 msg.submit 和 send_btn.click 双重提交
                    )
                    send_btn = gr.Button("发送", scale=1, variant="primary")

            # 右侧列 - 配置面板
            with gr.Column(scale=2):
                gr.Markdown("### ⚙️ 场景配置")
                scenario_selector = gr.Dropdown(
                    choices=[
                        ("闲聊对话", "chat"),
                        ("智能客服", "callcenter"),
                        ("保险咨询", "insurance"),
                        ("安逸花外呼", "anyihua"),
                    ],
                    value="chat",
                    label="选择场景",
                )
                mode_selector = gr.Radio(
                    choices=[
                        ("DST 模式 (槽位提取)", "dst"),
                        ("FnCTOD 模式 (函数调用)", "fnctod"),
                        ("PyTOD 模式 (程序执行)", "pytod"),
                        ("Evolve 模式 (记忆进化)", "evolve"),
                    ],
                    value="evolve",
                    label="选择模式",
                )
                apply_btn = gr.Button("应用配置", variant="primary")

                gr.Markdown("### 🎮 操作")
                with gr.Row():
                    view_state_btn = gr.Button("查看状态", scale=1)
                    reset_btn = gr.Button("重置对话", scale=1)
                clear_btn = gr.Button("清空历史")

                with gr.Accordion("📊 对话状态", open=True):
                    state_display = gr.Code(
                        label="当前状态",
                        language="json",
                        lines=10,
                        elem_classes=["json-display"],
                    )

                with gr.Accordion("⚙️ 高级设置", open=False):
                    # DST模式设置
                    with gr.Group(visible=False) as dst_settings:
                        gr.Markdown("**DST模式设置**")
                        max_history_slider = gr.Slider(
                            minimum=5, maximum=50, value=10, step=1,
                            label="历史轮数", info="DST模式保存的对话轮数",
                        )
                        enable_summary_check = gr.Checkbox(
                            value=True, label="启用历史摘要",
                            info="自动摘要历史对话（减少token消耗）",
                        )
                        use_llm_summary_check = gr.Checkbox(
                            value=False, label="使用LLM生成摘要",
                            info="用LLM生成摘要(更智能但慢)",
                        )
                        dst_temperature_slider = gr.Slider(
                            minimum=0.0, maximum=1.0, value=0.0, step=0.1,
                            label="温度参数", info="控制槽位提取的确定性（0=严格，1=灵活）",
                        )
                        enable_dynamic_slots_check = gr.Checkbox(
                            value=True, label="启用动态槽位",
                            info="允许提取未预定义的槽位（通用模式）",
                        )

                    # FnCTOD模式设置
                    with gr.Group(visible=False) as fnctod_settings:
                        gr.Markdown("**FnCTOD模式设置**")
                        fnctod_max_history_slider = gr.Slider(
                            minimum=5, maximum=50, value=10, step=1,
                            label="历史轮数", info="FnCTOD模式保存的对话轮数",
                        )
                        use_two_stage_check = gr.Checkbox(
                            value=True, label="启用两阶段处理",
                            info="先选择domain再填充参数（推荐）",
                        )
                        fnctod_temperature_slider = gr.Slider(
                            minimum=0.0, maximum=1.0, value=0.0, step=0.1,
                            label="温度参数", info="控制函数调用的确定性（0=严格，1=灵活）",
                        )

                    # Evolve模式设置
                    with gr.Group(visible=False) as evolve_settings:
                        gr.Markdown("**Evolve模式设置**")
                        enable_memory_check = gr.Checkbox(
                            value=True, label="启用记忆功能",
                            info="启用长期记忆存储和语义检索",
                        )
                        enable_evolution_check = gr.Checkbox(
                            value=True, label="启用进化学习",
                            info="从对话中学习和优化响应策略",
                        )
                        evolve_temperature_slider = gr.Slider(
                            minimum=0.0, maximum=2.0, value=0.7, step=0.1,
                            label="创造性温度", info="控制回复的随机性和创造性（0=保守，2=创新）",
                        )

        # 使用指南
        with gr.Accordion("💡 使用指南", open=False):
            gr.Markdown("""
### 场景说明

| 场景 | 说明 | 适用场景 |
|------|------|----------|
| 💬 闲聊对话 | 日常对话，轻松交流 | 聊天、问候、闲聊 |
| 📞 智能客服 | 专业客服服务 | 咨询、投诉、售后 |
| 🏥 保险咨询 | 共荣保险客服 | 保险产品咨询 |

### 模式对比

**Evolve 模式（基于记忆进化）**
- 📚 **语义记忆**: 自动记住对话内容，支持语义检索
- 🧬 **进化学习**: 从每次对话中学习，持续优化响应
- 🎯 **个性化**: 根据用户偏好调整对话策略
- 💡 **适用**: 开放域对话、长期交互、个性化服务

**DST 模式（对话状态追踪）**
- 🎯 **意图识别**: 准确识别用户意图（三级意图体系）
- 📋 **槽位提取**: 自动提取关键信息到预定义槽位
- 📊 **状态追踪**: 跟踪对话状态变化，累积信息
- 💡 **适用**: 任务型对话、信息收集、结构化交互

**FnCTOD 模式（函数调用型对话）**
- 🔧 **函数调用**: 通过函数调用方式提取结构化信息
- 🎯 **两阶段处理**: 先选择domain，再填充参数
- 📦 **结构化输出**: 输出标准function call格式
- 💡 **适用**: API集成、结构化任务、多domain场景

### 使用步骤

1. **选择场景**: 根据对话任务选择合适场景
2. **选择模式**: 需要记忆和学习 → Evolve 模式；需要结构化信息提取 → DST/FnCTOD 模式
3. **应用配置**: 点击"✨ 应用配置"按钮生效
4. **开始对话**: 在输入框输入消息，系统自动处理
5. **查看状态**: 点击"🔍 查看状态"查看提取的信息或记忆库
            """)

        # 页脚
        gr.Markdown(
            f"ContextMind v{APP_VERSION} | 💡 Powered by LLM",
            elem_classes=["footer"],
        )

    components = {
        "scenario_selector": scenario_selector,
        "mode_selector": mode_selector,
        "apply_btn": apply_btn,
        "dst_settings": dst_settings,
        "fnctod_settings": fnctod_settings,
        "evolve_settings": evolve_settings,
        "max_history_slider": max_history_slider,
        "enable_summary_check": enable_summary_check,
        "use_llm_summary_check": use_llm_summary_check,
        "dst_temperature_slider": dst_temperature_slider,
        "enable_dynamic_slots_check": enable_dynamic_slots_check,
        "fnctod_max_history_slider": fnctod_max_history_slider,
        "use_two_stage_check": use_two_stage_check,
        "fnctod_temperature_slider": fnctod_temperature_slider,
        "enable_memory_check": enable_memory_check,
        "enable_evolution_check": enable_evolution_check,
        "evolve_temperature_slider": evolve_temperature_slider,
        "chatbot": chatbot,
        "msg": msg,
        "send_btn": send_btn,
        "state_display": state_display,
        "view_state_btn": view_state_btn,
        "reset_btn": reset_btn,
        "clear_btn": clear_btn,
    }
    return app, components


def bind_events(app: gr.Blocks, components: dict, demo_instance) -> None:
    """将事件处理器绑定到已创建的 Gradio 组件。

    Args:
        app:           ``create_layout()`` 返回的 Gradio Blocks 应用。
        components:    ``create_layout()`` 返回的组件字典。
        demo_instance: 提供 ``chat``、``reset_conversation``、``get_state``、
                       ``change_scenario_or_mode`` 等方法的 Demo 实例。
    """
    chatbot = components["chatbot"]
    msg = components["msg"]
    send_btn = components["send_btn"]
    state_display = components["state_display"]
    view_state_btn = components["view_state_btn"]
    reset_btn = components["reset_btn"]
    clear_btn = components["clear_btn"]
    apply_btn = components["apply_btn"]
    scenario_selector = components["scenario_selector"]
    mode_selector = components["mode_selector"]
    dst_settings = components["dst_settings"]
    fnctod_settings = components["fnctod_settings"]
    evolve_settings = components["evolve_settings"]

    def get_state_json():
        """获取状态并格式化为 JSON。"""
        state = demo_instance.get_state()
        return format_state_as_json(state)

    def apply_config_and_update_ui(scenario, mode):
        """应用场景/模式配置，并按模式切换显示对应高级设置。"""
        history, _status = demo_instance.change_scenario_or_mode(scenario, mode)
        dst_vis = mode == "dst"
        fnctod_vis = mode == "fnctod"
        evolve_vis = mode not in ("dst", "fnctod")
        return (
            history,
            gr.update(visible=dst_vis),
            gr.update(visible=fnctod_vis),
            gr.update(visible=evolve_vis),
        )

    def _send_message(message, history):
        """防止双重提交：send_btn.click 和 msg.submit 共享此入口。"""
        return demo_instance.chat.__func__(demo_instance, message, history) if hasattr(demo_instance.chat, '__func__') else demo_instance.chat(message, history)

    with app:
        # 发送消息（send_btn.click 和 msg.submit 共享同一调用链，避免双重触发 LLM）
        # submit_btn=False 已在 create_layout 中设置，保证 Enter 仅触发 msg.submit
        chat_chain = send_btn.click(
            fn=demo_instance.chat,
            inputs=[msg, chatbot],
            outputs=[chatbot],
        ).then(
            fn=get_state_json,
            outputs=[state_display],
        ).then(
            fn=lambda: "",
            outputs=[msg],
        )

        msg.submit(
            fn=demo_instance.chat,
            inputs=[msg, chatbot],
            outputs=[chatbot],
        ).then(
            fn=get_state_json,
            outputs=[state_display],
        ).then(
            fn=lambda: "",
            outputs=[msg],
        )

        # 查看状态
        view_state_btn.click(fn=get_state_json, outputs=[state_display])

        # 重置对话
        reset_btn.click(fn=demo_instance.reset_conversation, outputs=[chatbot])

        # 清空历史
        clear_btn.click(fn=lambda: [], outputs=[chatbot])

        # 应用配置
        apply_btn.click(
            fn=apply_config_and_update_ui,
            inputs=[scenario_selector, mode_selector],
            outputs=[chatbot, dst_settings, fnctod_settings, evolve_settings],
        )

        # 页面加载时应用默认配置
        app.load(
            fn=apply_config_and_update_ui,
            inputs=[scenario_selector, mode_selector],
            outputs=[chatbot, dst_settings, fnctod_settings, evolve_settings],
        )


def create_gradio_ui(demo_instance=None) -> tuple:
    """创建 Gradio UI 界面（``create_layout()`` + ``bind_events()`` 的组合）。

    Args:
        demo_instance: 提供对话相关方法的 Demo 实例；传 None 则仅返回布局。

    Returns:
        ``(app, components)`` — Gradio Blocks 应用和组件字典。
    """
    app, components = create_layout()
    if demo_instance:
        bind_events(app, components, demo_instance)
    return app, components

