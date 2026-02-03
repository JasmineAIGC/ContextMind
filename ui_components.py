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
    min-width: 1000px !important;
    width: 1400px !important;
    margin: 0 auto !important;
    padding: 20px !important;
}

/* 美化标题 */
.main-title {
    text-align: center !important;
    color: #667eea !important;
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
    background: #f8f9fa !important;
    padding: 15px !important;
    border-radius: 8px !important;
    border: 1px solid #e1e8ed !important;
    margin-bottom: 15px !important;
}

/* Removed redundant .config-status styling */

/* 美化输入框 */
textarea {
    border-radius: 8px !important;
    border: 1px solid #d1d5db !important;
    padding: 12px !important;
    font-size: 1em !important;
    transition: border-color 0.2s ease !important;
}

textarea:focus {
    border-color: #667eea !important;
    outline: none !important;
}

/* 美化按钮 */
.primary-button button {
    background: #667eea !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    transition: background-color 0.2s ease !important;
}

.primary-button button:hover {
    background: #5568d3 !important;
}

.secondary-button button {
    background: white !important;
    color: #667eea !important;
    border: 1px solid #667eea !important;
    border-radius: 8px !important;
    padding: 10px 20px !important;
    font-weight: 600 !important;
    transition: all 0.2s ease !important;
}

.secondary-button button:hover {
    background: #f0f4ff !important;
}

/* 美化对话框 - 简化样式，移除消息背景 */
.chatbot {
    border-radius: 8px !important;
    border: 1px solid #e5e7eb !important;
    background: white !important;
}

.chatbot .message {
    border-radius: 8px !important;
    padding: 10px 14px !important;
    margin: 6px 0 !important;
    /* 移除背景颜色，让文本内容更简洁 */
}

/* Radio按钮美化 */
.radio-group label {
    background: white !important;
    border: 1px solid #d1d5db !important;
    border-radius: 8px !important;
    padding: 10px 16px !important;
    margin: 5px !important;
    transition: all 0.2s ease !important;
    cursor: pointer !important;
}

.radio-group label:hover {
    border-color: #667eea !important;
    background: #f9fafb !important;
}

.radio-group input:checked + label {
    background: #667eea !important;
    color: white !important;
    border-color: #667eea !important;
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
    width: 8px !important;
    height: 8px !important;
}

::-webkit-scrollbar-track {
    background: #f1f1f1 !important;
    border-radius: 4px !important;
}

::-webkit-scrollbar-thumb {
    background: #888 !important;
    border-radius: 4px !important;
}

::-webkit-scrollbar-thumb:hover {
    background: #555 !important;
}

/* 响应式设计 */
@media (max-width: 1200px) {
    .gradio-container {
        max-width: 95% !important;
        min-width: 768px !important;
        padding: 15px !important;
    }
}

@media (max-width: 768px) {
    .main-title {
        font-size: 1.6em !important;
    }
    
    .gradio-container {
        max-width: 100% !important;
        min-width: auto !important;
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
    with gr.Blocks(title="Evolve 统一Demo v0.4.1") as app:
        # 标题
        gr.Markdown("# 🤖 Evolve 统一对话系统", elem_classes=["main-title"])
        gr.Markdown("智能对话 · 场景灵活 · 模式可选", elem_classes=["subtitle"])
        
        # 主内容区 - 左右分栏
        with gr.Row(equal_height=True, elem_classes=["main-content-row"]):
            # 左侧列 - 对话区域
            with gr.Column(scale=8, elem_classes=["left-panel"]):
                # 对话框
                chatbot = gr.Chatbot(
                    height=650,
                    label="💬 对话窗口",
                    avatar_images=("👤", "🤖"),  # 设置用户和机器人的默认头像
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
                    # 移除config_status，避免重复的配置状态显示框
                
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
                            info="用LLM生成摘要(更智能但慢)，否则使用模板摘要(快速)"
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
            2. **选择模式**: 
               - 需要记忆和学习 → Evolve 模式
               - 需要结构化信息提取 → DST 模式
            3. **应用配置**: 点击"✨ 应用配置"按钮生效
            4. **开始对话**: 在输入框输入消息，系统自动处理
            5. **查看状态**: 点击"🔍 状态"查看提取的信息或记忆库
            
            ### 高级设置
            
            - **DST模式**: 可调整历史轮数、启用/禁用摘要功能
            - **Evolve模式**: 可控制记忆功能和进化学习开关
            5. 可随时重置或清空对话
            
            ### 注意事项
            
            - 确保已配置.env文件中的API密钥
            - 切换配置会重置当前对话
            - 状态信息仅在DST模式下可用
            """)
        
        # Footer
        gr.Markdown(
            "Evolve v0.4.1 | 💡 Powered by LLM",
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
            # 发送消息 - 并自动更新状态显示
            send_btn.click(
                fn=demo_instance.chat,
                inputs=[msg, chatbot],
                outputs=[chatbot]
            ).then(
                fn=demo_instance.get_state,
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
                fn=demo_instance.get_state,
                outputs=[state_display]
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
            
            # 应用配置 - 同时更新设置显示
            def apply_config_and_update_ui(scenario, mode):
                history, status = demo_instance.change_scenario_or_mode(scenario, mode)
                
                # 根据模式显示/隐藏对应的设置组
                if mode == "dst":
                    return history, gr.update(visible=True), gr.update(visible=False)
                else:  # contextmind
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
