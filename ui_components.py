#!/usr/bin/env python3
"""
Gradio UI组件和样式定义

将UI设计代码从gradio_demo.py中分离出来，便于维护和复用
"""

import json
import gradio as gr


def format_state_as_json(state_dict):
    """
    将状态字典格式化为 JSON 字符串
    
    Args:
        state_dict: 状态字典
        
    Returns:
        格式化的 JSON 字符串
    """
    if isinstance(state_dict, dict):
        return json.dumps(state_dict, ensure_ascii=False, indent=2)
    return str(state_dict)


# 自定义CSS样式 - 简化版本，配合 Soft 主题使用
CUSTOM_CSS = """
/* 全局样式优化 */
.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
}

/* 聊天区域优化 */
.chatbot {
    border-radius: 12px !important;
}

/* 配置区域样式 */
.config-section {
    background: #f8f9fa !important;
    padding: 15px !important;
    border-radius: 10px !important;
    border: 1px solid #e5e7eb !important;
    margin-bottom: 15px !important;
}

/* JSON显示区美化 */
.json-display {
    border-radius: 10px !important;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
    font-size: 0.9em !important;
    line-height: 1.6 !important;
}

/* Footer样式 */
.footer {
    text-align: center !important;
    color: #666 !important;
    font-size: 0.9em !important;
    margin-top: 30px !important;
    padding: 20px !important;
    border-top: 1px solid #e1e8ed !important;
}
"""


def create_gradio_ui(demo_instance=None):
    """
    创建Gradio UI界面
    
    Args:
        demo_instance: UnifiedGradioDemo实例，用于绑定事件
    
    Returns:
        tuple: (app, components_dict) - Gradio应用和组件字典
    """
    with gr.Blocks(
        title="ContextMind Demo v0.4.1",
        theme=gr.themes.Soft(),  # 使用 Soft 主题，更美观
        css=CUSTOM_CSS  # 附加自定义CSS
    ) as app:
        # 标题
        gr.Markdown("# 🧠 ContextMind 对话系统")
        gr.Markdown("上下文工程框架 · 智能对话 · 场景灵活 · 模式可选")
        
        # 主内容区 - 左右分栏
        with gr.Row():
            # 左侧列 - 对话区域
            with gr.Column(scale=3):
                gr.Markdown("### 💬 对话窗口")
                
                # 对话框
                chatbot = gr.Chatbot(
                    height=550,
                    avatar_images=("👤", "🤖"),
                    elem_classes=["chatbot"]
                )
                
                # 输入区域
                with gr.Row():
                    msg = gr.Textbox(
                        placeholder="💭 在这里输入您的消息...",
                        show_label=False,
                        scale=5,
                        container=False
                    )
                    send_btn = gr.Button("📤 发送", scale=1, variant="primary")
            
            # 右侧列 - 配置面板
            with gr.Column(scale=2):
                # 场景与模式配置
                gr.Markdown("### ⚙️ 场景配置")
                
                scenario_selector = gr.Dropdown(
                    choices=[
                        ("💬 闲聊对话", "chat"),
                        ("📞 智能客服", "callcenter"),
                        ("🏥 保险咨询", "insurance")
                    ],
                    value="chat",
                    label="选择场景"
                )
                
                mode_selector = gr.Radio(
                    choices=[
                        ("Evolve 模式 (记忆进化)", "evolve"),
                        ("DST 模式 (槽位提取)", "dst")
                    ],
                    value="evolve",
                    label="选择模式"
                )
                
                apply_btn = gr.Button("✨ 应用配置", variant="primary")
                
                # 操作按钮
                gr.Markdown("### 🎮 操作")
                with gr.Row():
                    view_state_btn = gr.Button("🔍 查看状态", scale=1)
                    reset_btn = gr.Button("🔄 重置对话", scale=1)
                
                clear_btn = gr.Button("🗑️ 清空历史")
                
                # 对话状态
                with gr.Accordion("📊 对话状态", open=True):
                    state_display = gr.Code(
                        label="当前状态",
                        language="json",
                        lines=12,
                        elem_classes=["json-display"]
                    )
                
                # 高级设置
                with gr.Accordion("⚙️ 高级设置", open=False):
                    # DST模式设置
                    with gr.Group(visible=False) as dst_settings:
                        gr.Markdown("**DST模式设置**")
                        max_history_slider = gr.Slider(
                            minimum=5,
                            maximum=50,
                            value=10,
                            step=1,
                            label="历史轮数",
                            info="DST模式保存的对话轮数"
                        )
                        
                        enable_summary_check = gr.Checkbox(
                            value=True,
                            label="启用历史摘要",
                            info="自动摘要历史对话（减少token消耗）"
                        )
                        
                        use_llm_summary_check = gr.Checkbox(
                            value=False,
                            label="使用LLM生成摘要",
                            info="用LLM生成摘要(更智能但慢)"
                        )
                    
                    # Evolve模式设置
                    with gr.Group(visible=False) as contextmind_settings:
                        gr.Markdown("**Evolve模式设置**")
                        enable_memory_check = gr.Checkbox(
                            value=True,
                            label="启用记忆功能",
                            info="启用长期记忆存储"
                        )
                        
                        enable_evolution_check = gr.Checkbox(
                            value=True,
                            label="启用进化学习",
                            info="从对话中学习和优化"
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

### 使用步骤

1. **选择场景**: 根据对话任务选择合适场景
2. **选择模式**: 需要记忆和学习 → Evolve 模式；需要结构化信息提取 → DST 模式
3. **应用配置**: 点击"✨ 应用配置"按钮生效
4. **开始对话**: 在输入框输入消息，系统自动处理
5. **查看状态**: 点击"🔍 查看状态"查看提取的信息或记忆库
            """)
        
        # Footer
        gr.Markdown(
            "ContextMind v0.4.1 | 💡 Powered by LLM",
            elem_classes=["footer"]
        )
        
        # 返回应用和组件
        components = {
            "scenario_selector": scenario_selector,
            "mode_selector": mode_selector,
            "apply_btn": apply_btn,
            "dst_settings": dst_settings,
            "contextmind_settings": contextmind_settings,
            "max_history_slider": max_history_slider,
            "enable_summary_check": enable_summary_check,
            "use_llm_summary_check": use_llm_summary_check,
            "enable_memory_check": enable_memory_check,
            "enable_evolution_check": enable_evolution_check,
            "chatbot": chatbot,
            "msg": msg,
            "send_btn": send_btn,
            "state_display": state_display,
            "view_state_btn": view_state_btn,
            "reset_btn": reset_btn,
            "clear_btn": clear_btn
        }
        
        # 如果提供了demo_instance，则绑定事件
        if demo_instance:
            def get_state_json():
                """获取状态并格式化为JSON"""
                state = demo_instance.get_state()
                return format_state_as_json(state)
            
            # 发送消息 - 并自动更新状态显示
            send_btn.click(
                fn=demo_instance.chat,
                inputs=[msg, chatbot],
                outputs=[chatbot]
            ).then(
                fn=get_state_json,
                outputs=[state_display]
            ).then(
                fn=lambda: "",
                outputs=[msg]
            )
            
            msg.submit(
                fn=demo_instance.chat,
                inputs=[msg, chatbot],
                outputs=[chatbot]
            ).then(
                fn=get_state_json,
                outputs=[state_display]
            ).then(
                fn=lambda: "",
                outputs=[msg]
            )
            
            # 查看状态
            view_state_btn.click(
                fn=get_state_json,
                outputs=[state_display]
            )
            
            # 重置对话
            reset_btn.click(
                fn=demo_instance.reset_conversation,
                outputs=[chatbot]
            )
            
            # 清空历史
            clear_btn.click(
                fn=lambda: [],
                outputs=[chatbot]
            )
            
            # 应用配置 - 同时更新设置显示
            def apply_config_and_update_ui(scenario, mode):
                history, status = demo_instance.change_scenario_or_mode(scenario, mode)
                
                # 根据模式显示/隐藏对应的设置组
                if mode == "dst":
                    return history, gr.update(visible=True), gr.update(visible=False)
                else:  # evolve
                    return history, gr.update(visible=False), gr.update(visible=True)
            
            apply_btn.click(
                fn=apply_config_and_update_ui,
                inputs=[scenario_selector, mode_selector],
                outputs=[chatbot, dst_settings, contextmind_settings]
            )
            
            # 页面加载时自动应用默认配置，显示欢迎消息
            app.load(
                fn=apply_config_and_update_ui,
                inputs=[scenario_selector, mode_selector],
                outputs=[chatbot, dst_settings, contextmind_settings]
            )
        
    return app, components
