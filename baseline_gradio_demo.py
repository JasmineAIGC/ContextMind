"""
Baseline Template Gradio Demo - 槽位模板基线版本 Gradio UI

这是一个基于 Gradio 的交互式 UI，展示槽位模板基线方法的使用。

特点:
- 不使用记忆库
- 基于规则的意图提取
- 模板填充生成提示词
- 简单、快速、直观
"""

import asyncio
import gradio as gr
from datetime import datetime
from typing import List, Tuple

from baseline_template import TemplateEngine, Message, SimpleTemplateEngine
from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT


class BaselineGradioApp:
    """Gradio 应用程序"""
    
    def __init__(self):
        """初始化应用"""
        self.engine = None
        self.conversation_history: List[Message] = []
        self.system_prompt = BASELINE_TEMPLATE_SYSTEM_PROMPT
        
        # 初始化引擎
        self._initialize_engine()
    
    def _initialize_engine(self):
        """初始化模板引擎"""
        self.engine = SimpleTemplateEngine(system_prompt=self.system_prompt)
    
    def clear_history(self) -> Tuple[List, str]:
        """清空对话历史"""
        self.conversation_history = []
        return [], "对话历史已清空"
    
    def change_system_prompt(self, prompt_choice: str) -> str:
        """更改系统提示词"""
        if prompt_choice == "基线模板提示词":
            self.system_prompt = BASELINE_TEMPLATE_SYSTEM_PROMPT
        elif prompt_choice == "闲聊提示词":
            self.system_prompt = CHAT_SYSTEM_PROMPT
        else:
            self.system_prompt = BASELINE_TEMPLATE_SYSTEM_PROMPT
        
        # 重新初始化引擎
        self._initialize_engine()
        
        return f"✓ 已切换到: {prompt_choice}"
    
    def chat(
        self,
        user_input: str,
        chatbot_history: List,
    ) -> Tuple[List, str, str]:
        """
        处理用户输入
        
        Args:
            user_input: 用户输入
            chatbot_history: Gradio chatbot 历史
            
        Returns:
            (更新的chatbot历史, 清空的输入框, 生成的提示词)
        """
        if not user_input.strip():
            return chatbot_history, "", ""
        
        # 添加用户消息到历史
        self.conversation_history.append(
            Message(role="user", content=user_input.strip())
        )
        
        # 生成提示词
        try:
            prompt = asyncio.run(
                self.engine.generate_prompt(self.conversation_history)
            )
            
            # 模拟助手回复（在实际应用中，这里会调用 LLM）
            assistant_response = "（这里是模拟的助手回复。实际使用时，应该将生成的提示词发送给 LLM 并获取回复）"
            
            # 添加助手回复到历史
            self.conversation_history.append(
                Message(role="assistant", content=assistant_response)
            )
            
            # 更新 Gradio chatbot 历史
            chatbot_history.append([user_input, assistant_response])
            
            return chatbot_history, "", prompt
            
        except Exception as e:
            error_msg = f"错误: {str(e)}"
            chatbot_history.append([user_input, error_msg])
            return chatbot_history, "", f"生成提示词时出错: {e}"
    
    def get_conversation_info(self) -> str:
        """获取对话统计信息"""
        if not self.conversation_history:
            return "暂无对话"
        
        user_msgs = sum(1 for m in self.conversation_history if m.role == "user")
        assistant_msgs = sum(1 for m in self.conversation_history if m.role == "assistant")
        
        return f"""对话统计:
- 总轮数: {len(self.conversation_history) // 2}
- 用户消息: {user_msgs}
- 助手回复: {assistant_msgs}
- 最后更新: {datetime.now().strftime('%H:%M:%S')}"""


def create_demo() -> gr.Blocks:
    """创建 Gradio 演示界面"""
    
    app = BaselineGradioApp()
    
    with gr.Blocks(
        title="槽位模板基线版本 - Baseline Template Demo",
        theme=gr.themes.Soft()
    ) as demo:
        gr.Markdown("""
        # 🎯 槽位模板基线版本 - Gradio UI
        
        这是一个简单的槽位模板系统演示，**不使用记忆库**，仅基于对话历史进行意图提取和模板填充。
        
        ## 特点
        - ✅ 完全独立，不依赖 ContextMind 框架
        - ✅ 基于规则的意图提取（< 5ms）
        - ✅ 模板填充生成提示词（< 1ms）
        - ✅ 适合简单对话场景和快速原型
        
        ## 工作流程
        ```
        用户输入 → 规则意图提取 → 模板填充 → 生成提示词
        ```
        """)
        
        with gr.Row():
            with gr.Column(scale=2):
                # 聊天区域
                chatbot = gr.Chatbot(
                    label="对话区",
                    height=400,
                    show_copy_button=True,
                )
                
                with gr.Row():
                    user_input = gr.Textbox(
                        label="输入消息",
                        placeholder="输入你的消息...",
                        scale=4,
                    )
                    send_btn = gr.Button("发送", variant="primary", scale=1)
                
                with gr.Row():
                    clear_btn = gr.Button("清空对话", variant="secondary")
                    info_display = gr.Textbox(
                        label="对话信息",
                        value=app.get_conversation_info(),
                        interactive=False,
                        scale=2,
                    )
            
            with gr.Column(scale=1):
                # 配置区域
                gr.Markdown("### ⚙️ 配置")
                
                prompt_choice = gr.Radio(
                    choices=["基线模板提示词", "闲聊提示词"],
                    value="基线模板提示词",
                    label="系统提示词",
                    info="选择使用的系统提示词模板"
                )
                
                prompt_status = gr.Textbox(
                    label="提示词状态",
                    value="✓ 当前: 基线模板提示词",
                    interactive=False,
                )
                
                gr.Markdown("### 📝 生成的提示词")
                generated_prompt = gr.Textbox(
                    label="最新提示词",
                    placeholder="生成的提示词将显示在这里...",
                    lines=10,
                    max_lines=20,
                    interactive=False,
                )
                
                gr.Markdown("""
                ### 💡 使用提示
                
                1. 在左侧输入框输入消息
                2. 点击"发送"按钮
                3. 查看右侧生成的提示词
                4. 提示词会根据对话历史动态更新
                
                ### 🔍 槽位说明
                
                - **intent**: 用户意图（自动识别）
                - **topic**: 对话主题（自动提取）
                - **context**: 上下文摘要（最近对话）
                """)
        
        # 事件处理
        def on_send(user_msg, chat_history):
            """发送消息"""
            new_history, cleared_input, prompt = app.chat(user_msg, chat_history)
            info = app.get_conversation_info()
            return new_history, cleared_input, prompt, info
        
        def on_clear():
            """清空对话"""
            history, msg = app.clear_history()
            info = app.get_conversation_info()
            return history, msg, "", info
        
        def on_prompt_change(choice):
            """更改提示词"""
            status = app.change_system_prompt(choice)
            return status
        
        # 绑定事件
        send_btn.click(
            fn=on_send,
            inputs=[user_input, chatbot],
            outputs=[chatbot, user_input, generated_prompt, info_display],
        )
        
        user_input.submit(
            fn=on_send,
            inputs=[user_input, chatbot],
            outputs=[chatbot, user_input, generated_prompt, info_display],
        )
        
        clear_btn.click(
            fn=on_clear,
            outputs=[chatbot, prompt_status, generated_prompt, info_display],
        )
        
        prompt_choice.change(
            fn=on_prompt_change,
            inputs=[prompt_choice],
            outputs=[prompt_status],
        )
        
        gr.Markdown("""
        ---
        
        ### 📚 相关文档
        
        - 查看 `baseline_template/README.md` 了解模块详情
        - 查看 `docs/COMPARISON_GUIDE.md` 了解与 ContextMind 的对比
        - 运行 `python baseline_demo.py` 查看命令行版本
        - 运行 `python comparison_experiment.py` 进行对比实验
        
        ### 🎯 适用场景
        
        | 场景 | 是否适用 | 说明 |
        |-----|---------|------|
        | 简单问答 | ✅ 推荐 | 速度快，足够使用 |
        | 快速原型 | ✅ 推荐 | 开发简单 |
        | 客服系统 | ❌ 不推荐 | 需要记忆客户信息，建议用 ContextMind |
        | 长期对话 | ❌ 不推荐 | 无法记住早期信息，建议用 ContextMind |
        
        ---
        **版本**: Baseline Template v1.0 | **更新**: 2026-01-29
        """)
    
    return demo


if __name__ == "__main__":
    # 创建并启动演示
    demo = create_demo()
    
    print("\n" + "=" * 80)
    print("🚀 启动槽位模板基线版本 Gradio UI")
    print("=" * 80)
    print("\n特点:")
    print("  ✅ 不使用记忆库")
    print("  ✅ 规则意图提取")
    print("  ✅ 模板填充")
    print("  ✅ 快速响应 (< 10ms)")
    print("\n访问地址: http://localhost:7860")
    print("=" * 80 + "\n")
    
    # 启动服务
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
    )
