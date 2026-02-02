#!/usr/bin/env python3
"""
Gradio UI组件和样式定义

将UI设计代码从gradio_demo.py中分离出来，便于维护和复用
"""

import gradio as gr

# 自定义CSS样式
CUSTOM_CSS = """
/* 全局样式优化 */
.gradio-container {
    font-family: 'Microsoft YaHei', 'PingFang SC', 'Helvetica Neue', Arial, sans-serif !important;
    max-width: 1400px !important;
    margin: 0 auto !important;
    padding: 20px !important;
}

/* 美化标题 */
.main-title {
    text-align: center !important;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    -webkit-background-clip: text !important;
    -webkit-text-fill-color: transparent !important;
    background-clip: text !important;
    font-size: 2.2em !important;
    font-weight: 700 !important;
    margin-bottom: 0.3em !important;
}

.subtitle {
    text-align: center !important;
    color: #666 !important;
    font-size: 1.1em !important;
    margin-bottom: 1.5em !important;
}

/* 强制主内容区左右布局，防止换行 */
.main-content-row {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
}

/* 左右布局样式 */
.left-panel {
    padding-right: 20px !important;
}

.right-panel {
    padding-left: 20px !important;
    border-left: 2px solid #e1e8ed !important;
    min-width: 350px !important;
}

/* 配置区域样式 */
.config-section {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%) !important;
    padding: 15px !important;
    border-radius: 10px !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08) !important;
    margin-bottom: 15px !important;
}

.config-status {
    background: #ffffff !important;
    padding: 10px 15px !important;
    border-radius: 8px !important;
    border-left: 4px solid #667eea !important;
    margin-top: 10px !important;
    font-size: 0.95em !important;
    color: #2c3e50 !important;
}

/* 美化输入框 */
textarea {
    border-radius: 10px !important;
    border: 2px solid #e1e8ed !important;
    padding: 12px !important;
    font-size: 1em !important;
    transition: all 0.3s ease !important;
}

textarea:focus {
    border-color: #667eea !important;
    box-shadow: 0 0 0 4px rgba(102, 126, 234, 0.15) !important;
    transform: translateY(-1px) !important;
}

/* 美化按钮 */
.primary-button button {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border: none !important;
    border-radius: 10px !important;
    padding: 12px 24px !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 15px rgba(102, 126, 234, 0.35) !important;
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.primary-button button:hover {
    transform: translateY(-3px) !important;
    box-shadow: 0 8px 20px rgba(102, 126, 234, 0.45) !important;
}

.secondary-button button {
    background: white !important;
    color: #667eea !important;
    border: 2px solid #667eea !important;
    border-radius: 10px !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    transition: all 0.3s ease !important;
}

.secondary-button button:hover {
    background: #667eea !important;
    color: white !important;
    transform: translateY(-2px) !important;
}

/* 美化对话框 */
.chatbot {
    border-radius: 15px !important;
    border: 2px solid #e1e8ed !important;
    box-shadow: 0 8px 25px rgba(0,0,0,0.1) !important;
    background: white !important;
}

.chatbot .message {
    border-radius: 12px !important;
    padding: 12px 16px !important;
    margin: 8px 0 !important;
}

.chatbot .message.user {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
}

.chatbot .message.bot {
    background: #f7f9fc !important;
    color: #2c3e50 !important;
}

/* Radio按钮美化 */
.radio-group label {
    background: white !important;
    border: 2px solid #e1e8ed !important;
    border-radius: 10px !important;
    padding: 12px 20px !important;
    margin: 5px !important;
    transition: all 0.3s ease !important;
    cursor: pointer !important;
}

.radio-group label:hover {
    border-color: #667eea !important;
    background: #f7f9fc !important;
}

.radio-group input:checked + label {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    color: white !important;
    border-color: transparent !important;
}

/* JSON显示区美化 */
.json-display {
    background: #2d3748 !important;
    color: #e2e8f0 !important;
    border-radius: 10px !important;
    padding: 15px !important;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace !important;
    font-size: 0.9em !important;
    line-height: 1.6 !important;
}

/* 滚动条美化 */
::-webkit-scrollbar {
    width: 10px !important;
    height: 10px !important;
}

::-webkit-scrollbar-track {
    background: #f1f1f1 !important;
    border-radius: 10px !important;
}

::-webkit-scrollbar-thumb {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    border-radius: 10px !important;
}

::-webkit-scrollbar-thumb:hover {
    background: linear-gradient(135deg, #764ba2 0%, #667eea 100%) !important;
}

/* 响应式设计 */
@media (max-width: 1200px) {
    .gradio-container {
        max-width: 95% !important;
        padding: 15px !important;
    }
}

@media (max-width: 768px) {
    .main-title {
        font-size: 1.6em !important;
    }
    
    .gradio-container {
        max-width: 100% !important;
        padding: 10px !important;
    }
    
    .left-panel, .right-panel {
        padding: 10px !important;
    }
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
    with gr.Blocks(title="ContextMind 统一Demo v0.4.0") as app:
        # 标题
        gr.Markdown("# 🤖 ContextMind 统一对话系统", elem_classes=["main-title"])
        gr.Markdown("智能对话 · 场景灵活 · 模式可选", elem_classes=["subtitle"])
        
        # 主内容区 - 左右分栏
        with gr.Row(equal_height=True, elem_classes=["main-content-row"]):
            # 左侧列 - 对话区域
            with gr.Column(scale=8, elem_classes=["left-panel"]):
                # 对话框
                chatbot = gr.Chatbot(
                    height=650,
                    label="💬 对话窗口",
                    avatar_images=(None, "🤖"),
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
                    send_btn = gr.Button("📤 发送", scale=1, elem_classes=["primary-button"])
            
            # 右侧列 - 配置面板
            with gr.Column(scale=4, elem_classes=["right-panel"]):
                # 场景与模式配置
                with gr.Group(elem_classes=["config-section"]):
                    gr.Markdown("### ⚙️ 场景配置")
                    scenario_selector = gr.Dropdown(
                        choices=[
                            ("💬 闲聊对话", "chat"),
                            ("📞 智能客服", "callcenter"),
                            ("🏥 保险咨询", "insurance")
                        ],
                        value="chat",
                        label="选择场景",
                        scale=1
                    )
                    
                    mode_selector = gr.Radio(
                        choices=["contextmind", "dst"],
                        value="contextmind",
                        label="选择模式",
                        elem_classes=["radio-group"]
                    )
                    
                    apply_btn = gr.Button("✨ 应用配置", elem_classes=["primary-button"])
                    config_status = gr.Markdown("📌 当前: 闲聊对话 / contextmind", elem_classes=["config-status"])
                
                # 高级设置
                with gr.Accordion("⚙️ 高级设置", open=False):
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
                        info="长对话时自动摘要"
                    )
                    
                    use_llm_summary_check = gr.Checkbox(
                        value=False,
                        label="LLM生成摘要",
                        info="更智能但慢"
                    )
                    
                    apply_settings_btn = gr.Button("💾 应用设置", elem_classes=["primary-button"])
                    settings_status = gr.Markdown("⚙️ 轮数=10, 摘要=启用", elem_classes=["config-status"])
                
                # 对话状态
                with gr.Accordion("📊 对话状态", open=False):
                    state_display = gr.JSON(label="当前状态", elem_classes=["json-display"])
                
                # 操作按钮
                gr.Markdown("### 🎮 操作")
                with gr.Row():
                    view_state_btn = gr.Button("🔍 状态", scale=1, elem_classes=["secondary-button"])
                    reset_btn = gr.Button("🔄 重置", scale=1, elem_classes=["secondary-button"])
                
                clear_btn = gr.Button("🗑️ 清空历史", elem_classes=["secondary-button"])
        
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
            
            - **contextmind**: 完整的五层架构，支持记忆和进化学习
            - **dst**: 基础对话状态追踪，轻量级实现
            
            ### 使用技巧
            
            1. 选择合适的场景和模式
            2. 点击"应用配置"生效
            3. 在输入框中输入消息
            4. 查看状态了解对话状态
            5. 可随时重置或清空对话
            
            ### 注意事项
            
            - 确保已配置.env文件中的API密钥
            - 切换配置会重置当前对话
            - 状态信息仅在DST模式下可用
            """)
        
        # Footer
        gr.Markdown(
            "ContextMind v0.4.0 | 💡 Powered by LLM",
            elem_classes=["footer"]
        )
        
        # 返回应用和组件
        components = {
            "scenario_selector": scenario_selector,
            "mode_selector": mode_selector,
            "apply_btn": apply_btn,
            "config_status": config_status,
            "max_history_slider": max_history_slider,
            "enable_summary_check": enable_summary_check,
            "use_llm_summary_check": use_llm_summary_check,
            "apply_settings_btn": apply_settings_btn,
            "settings_status": settings_status,
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
            # 发送消息
            send_btn.click(
                fn=demo_instance.chat,
                inputs=[msg, chatbot],
                outputs=[chatbot]
            ).then(
                fn=lambda: "",
                outputs=[msg]
            )
            
            msg.submit(
                fn=demo_instance.chat,
                inputs=[msg, chatbot],
                outputs=[chatbot]
            ).then(
                fn=lambda: "",
                outputs=[msg]
            )
            
            # 查看状态
            view_state_btn.click(
                fn=demo_instance.get_state,
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
            
            # 应用配置
            apply_btn.click(
                fn=demo_instance.change_scenario_or_mode,
                inputs=[scenario_selector, mode_selector],
                outputs=[chatbot, config_status]
            )
            
            # 应用设置
            apply_settings_btn.click(
                fn=demo_instance.update_settings,
                inputs=[
                    max_history_slider,
                    enable_summary_check,
                    use_llm_summary_check
                ],
                outputs=[settings_status]
            )
        
    return app, components
