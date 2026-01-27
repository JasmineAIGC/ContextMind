"""
ContextMind v7.3 闲聊 Gradio Demo

模块化架构 + 基于嵌入向量的智能记忆系统
适用于日常闲聊场景，支持上下文理解和长期记忆。

v7.3 新特性：
- 基于嵌入向量的语义检索和去重
- 流水线优化：移除KVCache，新增ResponseHandler
- 全面使用大语言模型处理，移除规则方法
- 完整的记忆生命周期：提取 → 存储 → 检索
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
import traceback

from contextmind import ContextEngine, setup_logging, get_logger, LogLevel, ContextMindLogger
from examples.chat_app import ChatApplication, CHAT_SYSTEM_PROMPT

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
        self.app = None  # ChatApplication 实例
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
            
            # 创建LLM客户端用于知识提取
            from examples.llm_client import SimpleLLMClient, LLMConfig
            llm_client_for_extraction = SimpleLLMClient(LLMConfig.from_env())
            
            # 创建引擎 (v7.3: 使用 LLM 提取知识，基于嵌入向量的语义理解)
            self.engine = ContextEngine(
                app_name="chat-demo",
                user_id="chat-user",
                max_recent_events=max_recent_events,
                llm_client=llm_client_for_extraction,  # 用于知识提取的 LLM 客户端
                extraction_method="llm",  # 使用 LLM 提取（语义理解，40 种类型）
            )
            
            logger.info("✅ [闲聊Demo] 引擎初始化成功 (v7.3 - Pure Context Engineering)")
            
            # 初始化 ChatApplication - 使用与 chat_interactive_demo 相同的模式
            try:
                self.app = ChatApplication(
                    context_engine=self.engine,
                    system_prompt=CHAT_SYSTEM_PROMPT,
                    history_turns=10,  # Prompt 中显示的历史轮数
                    use_real_llm=True,  # 使用真实 LLM
                )
                logger.info("✅ ChatApplication 初始化成功")
            except Exception as app_err:
                logger.error(f"❌ ChatApplication 初始化失败: {str(app_err)}")
                raise
            
            # 重置计数器
            self.turn_counter = 0
            
            logger.info("✅ 引擎初始化完成")
            return "✅ 引擎初始化成功！可以开始聊天了。"
            
        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = f"❌ 引擎初始化失败: {str(e)}"
            logger.error(error_msg)
            logger.error(f"错误详情:\n{error_details}")
            return error_msg
    
    async def chat(self, user_message: str) -> ChatResult:
        """处理聊天消息 - 使用 ChatApplication.process_turn()"""
        if not self.app:
            raise ValueError("应用未初始化，请先点击'初始化引擎'按钮")
        
        start_time = time.time()
        self.turn_counter += 1
        
        # 检测是否为 DEBUG 模式
        is_debug = ContextMindLogger.get_current_level() == LogLevel.DEBUG
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💬 [轮次 {self.turn_counter}] 用户输入: {user_message}")
        logger.info(f"{'='*80}")
        
        try:
            # 使用 ChatApplication 的 process_turn 方法处理对话
            # 这会自动处理：optimize → build_prompt → generate → update → extract_knowledge
            # 与 chat_interactive_demo 使用相同的处理流程
            if is_debug:
                response, debug_info = await self.app.process_turn(user_input=user_message, debug=True)
            else:
                response = await self.app.process_turn(user_input=user_message)
            
            processing_time = time.time() - start_time
            
            # 获取记忆库和会话历史状态
            memory_cache = self.engine.memory_bank.get_memory_cache()
            memory_count = len(memory_cache)
            
            # 获取历史消息数量
            history = await self.engine.session_manager.get_recent_history()
            history_count = len(history)
            
            # Debug 模式下显示详细信息（先打印 DEBUG，再打印回复和统计）
            if is_debug:
                print("\n" + "=" * 100)
                print("📊 DEBUG 信息")
                print("=" * 100)
                
                # 1. 记忆库内容 - 使用简化的清晰格式
                if debug_info.get('memory_before'):
                    print(f"\n1️⃣  记忆库内容（{len(debug_info['memory_before'])}条）:")
                    for i, mem in enumerate(debug_info['memory_before'], 1):
                        # 简化格式：只显示核心信息
                        print(f"   [{i}] {mem['content']}")
                        print(f"       类型:{mem['type']} | 置信度:{mem['confidence']:.2f}")
                else:
                    print("\n1️⃣  记忆库内容: 空")
                
                # 2. 召回结果 - 明确区分记忆库和历史对话
                if debug_info.get('context_result'):
                    ctx = debug_info['context_result']
                    print(f"\n2️⃣  召回结果（共{ctx['total_items']}项，压缩: {ctx['compressed']}）:")
                    
                    # 分类显示：记忆库 vs 历史对话
                    memory_items = [item for item in ctx['items'] if item['source'] == 'ContextSource.MEMORY']
                    history_items = [item for item in ctx['items'] if item['source'] != 'ContextSource.MEMORY']
                    
                    if memory_items:
                        print(f"\n   📚 从记忆库召回 ({len(memory_items)}项):")
                        for i, item in enumerate(memory_items, 1):
                            print(f"      [{i}] {item['content']} (分数: {item['score']:.2f})")
                    else:
                        print(f"\n   📚 从记忆库召回: 无")
                    
                    if history_items:
                        print(f"\n   💬 从历史对话召回 ({len(history_items)}项):")
                        for i, item in enumerate(history_items, 1):
                            content = item['content'][:100] + "..." if len(item['content']) > 100 else item['content']
                            print(f"      [{i}] {content} (分数: {item['score']:.2f})")
                    else:
                        print(f"\n   💬 从历史对话召回: 无")
                else:
                    print("\n2️⃣  召回结果: 无")
                
                # 3. 上下文优化后的结果（包括摘要信息）
                print(f"\n3️⃣  上下文优化: 已完成")
                # 总是显示摘要信息（即使没有摘要）
                summary_info = debug_info.get('summary_info', {'has_summary': False, 'recent_turns': 0})
                print(f"   对话摘要: {'是' if summary_info.get('has_summary', False) else '否'}")
                if summary_info.get('has_summary'):
                    print(f"   - 摘要轮数: {summary_info.get('summarized_turns', 0)}轮")
                    print(f"   - 保留轮数: {summary_info.get('recent_turns', 0)}轮")
                    incremental_count = summary_info.get('incremental_count', 0)
                    if incremental_count > 0:
                        print(f"   - 增量摘要: {incremental_count}个")
                    summary_text = summary_info.get('summary_text', 'N/A')
                    preview = summary_text[:150] + "..." if len(summary_text) > 150 else summary_text
                    print(f"   - 摘要内容: {preview}")
                else:
                    recent_turns = summary_info.get('recent_turns', 0)
                    print(f"   - 对话历史: {recent_turns}轮 (未达到摘要阈值5轮)")
                
                # 4. 完整的 Prompt - 显示所有部分
                if debug_info.get('prompt'):
                    prompt_text = debug_info['prompt']
                    print(f"\n4️⃣  完整Prompt ({len(prompt_text)}字符):")
                    print("   " + "-" * 96)
                    
                    # 按部分显示Prompt，确保所有部分都可见
                    lines = prompt_text.split("\n")
                    for line in lines:
                        print("   " + line)
                    
                    print("   " + "-" * 96)
                    
                    # 检查并提示Prompt中是否包含各个部分
                    has_memory = "## 已知信息" in prompt_text
                    has_summary = "## 早期对话摘要" in prompt_text
                    has_recent = "## 最近对话" in prompt_text or "## 对话历史" in prompt_text
                    has_current = "## 当前问题" in prompt_text
                    
                    print(f"\n   Prompt结构检查:")
                    print(f"      已知信息: {'✓' if has_memory else '✗'}")
                    print(f"      对话摘要: {'✓' if has_summary else '✗'}")
                    print(f"      对话历史: {'✓' if has_recent else '✗'}")
                    print(f"      当前问题: {'✓' if has_current else '✗'}")
                
                # 5. 提取的知识 - 使用简化格式
                if debug_info.get('extracted_knowledge'):
                    print(f"\n5️⃣  提取的知识（{len(debug_info['extracted_knowledge'])}条）:")
                    for i, k in enumerate(debug_info['extracted_knowledge'], 1):
                        # 简化格式：每条知识一行
                        print(f"   [{i}] {k['content']}")
                        print(f"       类型:{k['type']} | 置信度:{k['confidence']:.2f}")
                else:
                    print("\n5️⃣  提取的知识: 无")
                
                print("\n" + "=" * 100)
            
            # 在 DEBUG 信息之后打印助手回复和统计信息
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
            error_details = traceback.format_exc()
            error_msg = f"处理失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"错误详情:\n{error_details}")
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
            # 添加输入验证
            if not message or not message.strip():
                return history, "⚠️ 请输入消息"
            
            logger.info(f"[Gradio] 开始处理消息，当前历史长度: {len(history)}")
            
            result = await demo_instance.chat(message)
            
            # Gradio 6.x 聊天机器人格式：每条消息是带有 'role' 和 'content' 的字典
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": result.response})
            
            # 构建状态信息
            status = f"⏱️ {result.processing_time:.2f}s | 📝 上下文: {result.history_count}项"
            
            logger.info(f"[Gradio] 消息处理完成，新历史长度: {len(history)}")
            
            return history, status
        except Exception as e:
            error_details = traceback.format_exc()
            logger.error(f"[Gradio] 处理失败: {str(e)}")
            logger.error(f"[Gradio] 错误详情:\n{error_details}")
            
            error_response = f"❌ 错误: {str(e)}"
            history.append({"role": "user", "content": message})
            history.append({"role": "assistant", "content": error_response})
            return history, f"❌ 处理失败: {str(e)}"
    
    async def reset_async():
        try:
            # 使用异步版本避免 asyncio.run 嵌套问题
            result = await demo_instance.reset_conversation_async()
            return result, [], ""
        except Exception as e:
            logger.error(f"[Gradio] 重置失败: {str(e)}")
            return f"❌ 重置失败: {str(e)}", [], ""
    
    # 创建界面
    with gr.Blocks(title="ContextMind 闲聊Demo v7.3") as app:
        gr.Markdown("# 🎭 ContextMind v7.3 闲聊演示")
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
    print("🎭 ContextMind v7.3 闲聊 Gradio Demo")
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
