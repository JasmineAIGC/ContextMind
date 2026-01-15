"""
全新设计的 Gradio UI - 简洁现代的界面
"""

try:
    import gradio as gr
except ImportError:
    print("❌ 错误: 未安装 gradio")
    print("💡 解决方案: pip install gradio>=4.0.0")
    import sys
    sys.exit(1)

import asyncio
from pathlib import Path
from contextmind import Client, ContextEngine
from contextmind.logger import setup_logging, get_logger, INFO, DEBUG
from examples.applications.callcenter import CallCenterApplication

setup_logging(level=INFO, log_to_console=True, auto_create_file=False)
logger = get_logger(__name__)

# 加载环境变量
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    pass


class ContextMindUI:
    """ContextMind 现代化UI"""
    
    def __init__(self):
        self.app = None
        self.engine = None
        self.conversation_history = []
        
    def init_engine(self, use_memory: bool = False, debug: bool = False):
        """初始化引擎"""
        # 设置日志级别
        setup_logging(level=DEBUG if debug else INFO, log_to_console=False, auto_create_file=False)
        
        client = Client()
        
        # 创建引擎
        self.engine = ContextEngine(
            app_name="contextmind-demo",
            user_id="demo-user",
            llm_client=client,
            max_recent_events=9999,  # 不限制历史
            memory_service=None  # 暂不使用记忆
        )
        
        # 创建应用
        self.app = CallCenterApplication(
            context_engine=self.engine,
            llm_client=client,
            business_info="""智能对话助手 Demo
- 基于 ContextMind 框架构建
- 支持多轮对话和上下文理解
- 智能提取关键信息""",
            debug=debug
        )
        
        return "✅ 引擎初始化成功！"
    
    async def chat(self, user_input: str, history):
        """处理聊天"""
        if not self.app:
            return history + [("系统", "❌ 请先点击'初始化引擎'按钮")]
        
        # 获取回复
        response = await self.app.get_response(user_input)
        
        # 更新历史
        history.append((user_input, response))
        
        return history
    
    def create_ui(self):
        """创建UI"""
        with gr.Blocks(title="ContextMind Demo", theme=gr.themes.Soft()) as demo:
            gr.Markdown("""
            # 🤖 ContextMind 智能对话演示
            
            **通用上下文工程框架** - 支持任何话题的多轮对话
            """)
            
            with gr.Row():
                # 左侧：对话区域
                with gr.Column(scale=2):
                    chatbot = gr.Chatbot(
                        label="对话窗口",
                        height=500,
                        bubble_full_width=False,
                        show_label=True,
                    )
                    
                    with gr.Row():
                        user_input = gr.Textbox(
                            placeholder="输入消息...",
                            show_label=False,
                            scale=4,
                        )
                        send_btn = gr.Button("发送", variant="primary", scale=1)
                    
                    gr.Examples(
                        examples=[
                            "你好，你是谁？",
                            "帮我写一首诗",
                            "我想去重庆旅游",
                            "推荐一些美食",
                        ],
                        inputs=user_input,
                    )
                
                # 右侧：控制面板
                with gr.Column(scale=1):
                    gr.Markdown("### ⚙️ 引擎设置")
                    
                    with gr.Group():
                        use_memory_cb = gr.Checkbox(
                            label="启用长期记忆",
                            value=False,
                            info="记住重要信息"
                        )
                        
                        debug_mode_cb = gr.Checkbox(
                            label="调试模式",
                            value=False,
                            info="显示详细日志"
                        )
                        
                        init_btn = gr.Button("🚀 初始化引擎", variant="primary")
                        init_status = gr.Textbox(
                            label="状态",
                            value="未初始化",
                            interactive=False
                        )
                    
                    gr.Markdown("### 📊 对话统计")
                    stats = gr.Textbox(
                        label="",
                        value="对话轮数: 0\n上下文项: 0",
                        interactive=False,
                        lines=3
                    )
                    
                    clear_btn = gr.Button("🗑️ 清空对话")
            
            # 事件绑定
            def init_engine_wrapper(use_memory, debug):
                return self.init_engine(use_memory, debug)
            
            def chat_wrapper(user_input, history):
                # 同步包装异步函数
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.chat(user_input, history))
                    return future.result()
            
            def update_stats(history):
                return f"对话轮数: {len(history)}\n上下文项: {len(history) * 2}"
            
            # 初始化引擎
            init_btn.click(
                fn=init_engine_wrapper,
                inputs=[use_memory_cb, debug_mode_cb],
                outputs=init_status
            )
            
            # 发送消息
            send_btn.click(
                fn=chat_wrapper,
                inputs=[user_input, chatbot],
                outputs=chatbot
            ).then(
                fn=update_stats,
                inputs=chatbot,
                outputs=stats
            ).then(
                fn=lambda: "",
                outputs=user_input
            )
            
            # 回车发送
            user_input.submit(
                fn=chat_wrapper,
                inputs=[user_input, chatbot],
                outputs=chatbot
            ).then(
                fn=update_stats,
                inputs=chatbot,
                outputs=stats
            ).then(
                fn=lambda: "",
                outputs=user_input
            )
            
            # 清空对话
            clear_btn.click(
                fn=lambda: ([], "对话轮数: 0\n上下文项: 0"),
                outputs=[chatbot, stats]
            )
        
        return demo


if __name__ == "__main__":
    ui = ContextMindUI()
    demo = ui.create_ui()
    demo.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False
    )
