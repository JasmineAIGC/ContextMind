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
        self.conversation_history = []
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
            
            # 重置对话历史
            self.conversation_history = []
            self.turn_counter = 0
            
            logger.info("✅ 引擎初始化完成")
            return "✅ 引擎初始化成功！可以开始聊天了。"
            
        except Exception as e:
            error_msg = f"❌ 引擎初始化失败: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    async def chat(self, user_message: str) -> ChatResult:
        """处理聊天消息"""
        if not self.engine:
            raise ValueError("引擎未初始化，请先点击'初始化引擎'按钮")
        
        start_time = time.time()
        self.turn_counter += 1
        is_debug = ContextMindLogger.get_current_level() == LogLevel.DEBUG
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💬 [轮次 {self.turn_counter}] 用户输入: {user_message}")
        logger.info(f"{'='*80}")
        
        try:
            # Debug: 保存优化前的记忆库状态
            if is_debug:
                memory_cache = self.engine.memory_bank.get_memory_cache()
                logger.info("\n1️⃣  记忆库内容:")
                if memory_cache:
                    for i, mem in enumerate(memory_cache[:5], 1):
                        # ContextItem.content 格式为 "[TYPE] content"，提取类型
                        mem_type = mem.metadata.get('type', 'UNKNOWN') if hasattr(mem, 'metadata') and mem.metadata else 'UNKNOWN'
                        logger.info(f"   [{i}] [{mem_type}] {mem.content[:60]}... (置信度: {mem.score:.2f})")
                    if len(memory_cache) > 5:
                        logger.info(f"   ... (还有{len(memory_cache) - 5}条)")
                else:
                    logger.info("   空")
            
            # 构建系统提示词 - 简洁的闲聊角色设定
            system_prompt = """你是一个友好、有趣的聊天助手。

特点：
- 亲切自然，像朋友一样交流
- 适当使用表情和轻松的语气
- 记住用户提到的信息，让对话更连贯
- 话题广泛，可以聊天、讲笑话、分享知识

注意：
- 回复简洁有趣，不要过于正式
- 适当提问，保持对话互动
- 如果用户分享了个人信息（如名字、爱好、城市等），记住并在后续对话中自然提及"""
            
            # 1. 优化上下文
            context_result = await self.engine.optimize(
                user_input=user_message,
                include_session=self.use_session,
                include_memory=self.use_memory,
            )
            
            # Debug: 显示召回结果
            if is_debug:
                logger.info(f"\n2️⃣  召回结果（共{len(context_result.items)}项，压缩: {context_result.compressed}）:")
                for i, item in enumerate(context_result.items[:5], 1):
                    logger.info(f"   [{i}] [{item.source}] {item.content[:50]}... (分数: {item.score:.2f})")
                if len(context_result.items) > 5:
                    logger.info(f"   ... (还有{len(context_result.items) - 5}项)")
                logger.info(f"\n3️⃣  上下文优化: 已完成 (压缩: {context_result.compressed})")
            
            # 2. 构建prompt
            prompt = f"{system_prompt}\n\n用户: {user_message}\n助手:"
            
            # Debug: 显示Prompt
            if is_debug:
                logger.info(f"\n4️⃣  完整Prompt ({len(prompt)}字符):")
                prompt_lines = prompt[:300].split('\n')
                for line in prompt_lines[:4]:
                    if line:
                        logger.info(f"   {line[:70]}")
                if len(prompt) > 300:
                    logger.info(f"   ... (共{len(prompt)}字符)")
            
            # 3. 调用 LLM 生成回复
            _, assistant_response = self.llm_client.generate(prompt)
            
            # 4. 更新对话历史
            await self.engine.update(
                user_input=user_message,
                assistant_response=assistant_response
            )
            
            # 5. 提取知识到长期记忆
            extracted_knowledge = []
            if self.use_memory:
                knowledge_list = await self.engine.extract_knowledge(auto_store=True)
                if is_debug and knowledge_list:
                    extracted_knowledge = knowledge_list
            
            # Debug: 显示提取的知识
            if is_debug:
                logger.info("\n5️⃣  提取的知识:")
                if extracted_knowledge:
                    for i, k in enumerate(extracted_knowledge[:5], 1):
                        logger.info(f"   [{i}] [{k.knowledge_type}] {k.content[:55]}... (置信度: {k.confidence:.2f})")
                    if len(extracted_knowledge) > 5:
                        logger.info(f"   ... (还有{len(extracted_knowledge) - 5}条)")
                else:
                    logger.info("   无")
                logger.info("")
            
            # 记录对话
            self.conversation_history.append({
                "user": user_message,
                "assistant": assistant_response,
                "turn": self.turn_counter
            })
            
            processing_time = time.time() - start_time
            
            # 获取上下文信息
            history_count = len(context_result.context_items) if hasattr(context_result, 'context_items') else 0
            memory_count = 0
            
            logger.info(f"🤖 助手回复: {assistant_response}")
            logger.info(f"⏱️  处理耗时: {processing_time:.2f}秒")
            logger.info(f"📊 上下文项: {history_count}")
            
            return ChatResult(
                response=assistant_response,
                history_count=history_count,
                memory_count=memory_count,
                processing_time=processing_time
            )
            
        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            raise
    
    def reset_conversation(self):
        """重置对话"""
        self.conversation_history = []
        self.turn_counter = 0
        logger.info("🔄 对话已重置")
        return "✅ 对话已重置，可以开始新的聊天了！"


def create_gradio_interface():
    """创建 Gradio 界面"""
    demo_instance = ChatGradioDemo()
    
    async def init_engine_async(use_session, use_memory, max_events):
        return await demo_instance.initialize_engine(use_session, use_memory, max_events)
    
    async def chat_async(message, history):
        try:
            result = await demo_instance.chat(message)
            # Gradio chatbot 格式：[(用户消息, 机器人消息), ...]
            history.append((message, result.response))
            
            # 构建状态信息
            status = f"⏱️ {result.processing_time:.2f}s | 📝 上下文: {result.history_count}项"
            
            return history, status
        except Exception as e:
            error_response = f"❌ 错误: {str(e)}"
            history.append((message, error_response))
            return history, "❌ 处理失败"
    
    def reset_async():
        return demo_instance.reset_conversation(), [], ""
    
    # 创建界面
    with gr.Blocks(title="ContextMind 闲聊Demo v7.1") as app:
        gr.Markdown("# 🎭 ContextMind v7.1 闲聊演示")
        gr.Markdown("基于五层架构的智能对话系统，支持上下文理解和长期记忆")
        
        with gr.Row():
            with gr.Column(scale=3):
                # 聊天界面
                chatbot = gr.Chatbot(
                    label="对话窗口",
                    height=500,
                    show_copy_button=True,
                )
                
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="输入消息",
                        placeholder="输入你想说的话...",
                        lines=2,
                        scale=4
                    )
                    submit_btn = gr.Button("发送", variant="primary", scale=1)
                
                status_text = gr.Textbox(
                    label="状态",
                    interactive=False,
                    lines=1
                )
                
                with gr.Row():
                    clear_btn = gr.Button("清空对话", variant="secondary")
            
            with gr.Column(scale=1):
                gr.Markdown("### ⚙️ 引擎配置")
                
                use_session_check = gr.Checkbox(
                    label="启用会话历史",
                    value=True,
                    info="记住对话上下文"
                )
                
                use_memory_check = gr.Checkbox(
                    label="启用长期记忆",
                    value=True,
                    info="记住用户偏好和重要信息"
                )
                
                max_events_slider = gr.Slider(
                    minimum=5,
                    maximum=50,
                    value=20,
                    step=5,
                    label="最大历史轮数",
                    info="保留的对话轮数"
                )
                
                init_btn = gr.Button("初始化引擎", variant="primary")
                init_status = gr.Textbox(
                    label="初始化状态",
                    interactive=False,
                    lines=2
                )
                
                gr.Markdown("### 💡 使用提示")
                gr.Markdown("""
                1. 点击"初始化引擎"开始
                2. 输入消息后点击"发送"
                3. 系统会记住你的偏好
                4. 随时可以"清空对话"重新开始
                
                **试试这些话题：**
                - 自我介绍
                - 聊聊兴趣爱好
                - 讲个笑话
                - 推荐电影/书籍
                - 生活小窍门
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
