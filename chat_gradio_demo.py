"""
ContextMind v7.1 闲聊 Gradio Demo

五层架构 (core/pipeline/strategies/adapters/utils) + 智能记忆系统
适用于日常闲聊场景，支持上下文理解和长期记忆。

v7.1 新特性：
- 增强的日志系统：模块前缀、状态指示器、详细的记忆追踪
- 完整的记忆生命周期：提取 → 存储 → 检索
- 改进的可观测性：记忆库内容可见、检索结果带分数
"""

try:
    import gradio as gr
except ImportError:
    print("=" * 60)
    print("❌ 错误: 未安装 gradio")
    print("=" * 60)
    print("💡 解决方案:")
    print("   pip install gradio>=4.0.0")
    print("   或者: pip install -r requirements.txt")
    print("=" * 60)
    import sys
    sys.exit(1)

import asyncio
import time
from typing import List
from dataclasses import dataclass
import os
from pathlib import Path

from contextmind import ContextEngine, setup_logging, get_logger, LogLevel
from demos.chat_app import ChatApplication, CHAT_SYSTEM_PROMPT

# 设置日志级别为 INFO (使用 BASIC)
setup_logging(level=LogLevel.BASIC)
logger = get_logger(__name__)

# 自动加载 .env 文件
try:
    from dotenv import load_dotenv
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        load_dotenv(env_file)
        logger.debug(f"✓ 已加载环境变量文件: {env_file}")
    else:
        logger.warning(f"⚠️  环境变量文件不存在: {env_file}")
except ImportError:
    logger.warning("⚠️  python-dotenv 未安装，尝试手动设置环境变量")


@dataclass
class ChatResult:
    """聊天结果数据类"""
    response: str
    history_count: int = 0
    memory_count: int = 0
    processing_time: float = 0.0


class ChatGradioDemo:
    
    def __init__(self):
        """初始化闲聊 Gradio 演示"""
        self.engine = None
        self.app = None  # ChatApplication instance
        self.turn_counter = 0
        # 上下文控制参数
        self.use_session = True
        self.use_memory = True  # 闲聊场景默认启用长期记忆
        self.max_recent_events = 20  # 闲聊可能需要更长的上下文
        
    async def initialize_engine(self, use_session=True, use_memory=True, max_recent_events=20):
        """初始化引擎"""
        try:
            logger.info("=" * 80)
            logger.info("🚀 [闲聊Demo] 开始初始化引擎...")
            logger.info(f"   - 会话历史: {'✅' if use_session else '❌'}")
            logger.info(f"   - 长期记忆: {'✅' if use_memory else '❌'}")
            logger.info(f"   - 最大历史: {max_recent_events}轮")
            logger.info("=" * 80)
            
            # 保存配置
            self.use_session = use_session
            self.use_memory = use_memory
            self.max_recent_events = max_recent_events
            
            # 创建引擎 (v7.1: LLM invocation is external, no client needed)
            self.engine = ContextEngine(
                app_name="chat-demo",
                user_id="chat-user",
                max_recent_events=max_recent_events,
            )
            
            logger.info("✅ [闲聊Demo] 引擎初始化成功 (v7.1 - Pure Context Engineering)")
            
            # 初始化 ChatApplication - 使用与 chat_interactive_demo 相同的模式
            self.app = ChatApplication(
                context_engine=self.engine,
                system_prompt=CHAT_SYSTEM_PROMPT,
                history_turns=10,  # Prompt中显示的历史轮数
                use_real_llm=True,  # 使用真实LLM
            )
            
            # 重置计数器
            self.turn_counter = 0
            
            logger.info("✅ 引擎初始化完成")
            return "✅ 引擎初始化成功！可以开始聊天了。"
            
        except Exception as e:
            error_msg = f"❌ 引擎初始化失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    async def chat(self, user_message: str) -> ChatResult:
        """处理聊天消息 - 使用 ChatApplication.process_turn()"""
        if not self.app:
            raise ValueError("应用未初始化，请先点击'初始化引擎'按钮")
        
        start_time = time.time()
        self.turn_counter += 1
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💬 [轮次 {self.turn_counter}] 用户输入: {user_message}")
        logger.info(f"{'='*80}")
        
        try:
            # 使用 ChatApplication 的 process_turn 方法处理对话
            # 这会自动处理: optimize → build_prompt → generate → update → extract_knowledge
            # 与 chat_interactive_demo 使用相同的处理流程
            response = await self.app.process_turn(user_input=user_message)
            
            processing_time = time.time() - start_time
            
            # 获取记忆库和会话历史状态
            memory_cache = self.engine.memory_bank.get_memory_cache()
            memory_count = len(memory_cache)
            
            # 获取历史消息数量
            history = await self.engine.session_manager.get_recent_history()
            history_count = len(history)
            
            logger.info(f"🤖 助手回复: {response}")
            logger.info(f"⏱️  处理耗时: {processing_time:.2f}秒")
            logger.info(f"📊 历史: {history_count}轮 | 记忆: {memory_count}条")
            
            return ChatResult(
                response=response,
                history_count=history_count,
                memory_count=memory_count,
                processing_time=processing_time
            )
            
        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise
    
    async def reset_conversation_async(self):
        """重置对话（异步版本）"""
        self.turn_counter = 0
        if self.engine:
            await self.engine.clear_session()
        logger.info("🔄 对话已重置")
        return "✅ 对话已重置，可以开始新的聊天了！"
    
    def reset_conversation(self):
        """重置对话（同步包装）"""
        # 为 Gradio 提供同步接口
        return asyncio.run(self.reset_conversation_async())


def create_gradio_interface():
    """创建 Gradio 界面"""
    demo_instance = ChatGradioDemo()
    
    async def init_engine_async(use_session, use_memory, max_events):
        return await demo_instance.initialize_engine(use_session, use_memory, max_events)
    
    async def chat_async(message, history):
        try:
            result = await demo_instance.chat(message)
            # Gradio 6.x chatbot format: each message is a dict with 'role' and 'content'
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": result.response})
            
            # 构建状态信息
            status = f"⏱️ {result.processing_time:.2f}s | 📝 上下文: {result.history_count}项"
            
            return history, status
        except Exception as e:
            error_response = f"❌ 错误: {str(e)}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_response})
            return history, "❌ 处理失败"
    
    def reset_async():
        return demo_instance.reset_conversation(), [], ""
    
    # 创建界面
    with gr.Blocks(title="ContextMind 闲聊Demo v7.1") as app:
        gr.Markdown("# 🎭 ContextMind v7.1 闲聊演示")
        gr.Markdown("基于五层架构的智能对话系统，支持上下文理解和长期记忆")
        
        with gr.Row():
            with gr.Column(scale=4):
                # 聊天界面 - 主要区域
                chatbot = gr.Chatbot(
                    label="对话窗口",
                    height=600,
                    show_label=False,
                )
                
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="",
                        placeholder="输入你想说的话... (按 Enter 发送，Shift+Enter 换行)",
                        lines=1,
                        scale=9,
                        show_label=False,
                    )
                    submit_btn = gr.Button("📤 发送", variant="primary", scale=1, size="lg")
                
                with gr.Row():
                    status_text = gr.Textbox(
                        label="",
                        interactive=False,
                        lines=1,
                        show_label=False,
                        container=False,
                    )
                    clear_btn = gr.Button("🗑️ 清空", variant="secondary", size="sm")
            
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 配置")
                
                init_btn = gr.Button("🚀 初始化引擎", variant="primary", size="lg")
                init_status = gr.Textbox(
                    label="",
                    interactive=False,
                    lines=2,
                    show_label=False,
                )
                
                gr.Markdown("---")
                
                use_session_check = gr.Checkbox(
                    label="会话历史",
                    value=True,
                    info="记住对话上下文"
                )
                
                use_memory_check = gr.Checkbox(
                    label="长期记忆",
                    value=True,
                    info="记住用户偏好"
                )
                
                max_events_slider = gr.Slider(
                    minimum=5,
                    maximum=50,
                    value=20,
                    step=5,
                    label="历史轮数",
                    info="保留的对话轮数"
                )
                
                gr.Markdown("---")
                gr.Markdown("### 💡 使用提示")
                gr.Markdown("""
                1. 点击 **初始化引擎**
                2. 输入消息，按 **Enter** 发送
                3. 系统会记住对话内容
                
                **话题建议：**
                - 自我介绍
                - 兴趣爱好
                - 讲个笑话
                - 推荐电影
                - 生活窍门
                """)
        
        # 事件绑定
        init_btn.click(
            fn=lambda s, m, e: asyncio.run(init_engine_async(s, m, int(e))),
            inputs=[use_session_check, use_memory_check, max_events_slider],
            outputs=[init_status]
        )
        
        submit_btn.click(
            fn=lambda msg, hist: asyncio.run(chat_async(msg, hist)),
            inputs=[msg_input, chatbot],
            outputs=[chatbot, status_text]
        ).then(
            lambda: "",  # 清空输入框
            None,
            msg_input
        )
        
        msg_input.submit(
            fn=lambda msg, hist: asyncio.run(chat_async(msg, hist)),
            inputs=[msg_input, chatbot],
            outputs=[chatbot, status_text]
        ).then(
            lambda: "",
            None,
            msg_input
        )
        
        clear_btn.click(
            fn=reset_async,
            outputs=[init_status, chatbot, status_text]
        )
    
    return app


if __name__ == "__main__":
    print("=" * 60)
    print("🎭 ContextMind v7.1 闲聊 Gradio Demo")
    print("=" * 60)
    print()
    
    app = create_gradio_interface()
    
    # 启动应用
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        show_error=True,
        theme=gr.themes.Soft()
    )
