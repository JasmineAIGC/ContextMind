"""
ContextMind v0.4.0 客服对话 Gradio Demo

模块化架构 + 基于嵌入向量的智能记忆系统
适用于客服对话场景，支持上下文理解和业务知识管理。

v0.4.0 新特性：
- Utils模块移至根目录，完全独立
- 增强的DST实现，完整ACL 2023合规
- 新增知识提取能力
- 基于嵌入向量的语义检索和去重
- 流水线优化：移除KVCache，新增ResponseHandler
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
import random
from typing import List
from dataclasses import dataclass
import os
from pathlib import Path
import traceback

from contextmind import ContextEngine, setup_logging, get_logger, LogLevel, ContextMindLogger, MessageRole
from apps.callcenter_app import CallCenterApplication
from prompts import CALLCENTER_SYSTEM_PROMPT
from dst import DialogueStateTracker, PromptManager

# 设置日志级别为 INFO
setup_logging(level=LogLevel.INFO)
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


# 开场白列表 - 客服机器人会从中随机选择一条作为开场
OPENING_SCRIPTS = [
    "您好，请问是胡女士本人吗？耽误您一分钟，有项业务想跟您同步。",
    "您好，我是马上消费的客服，有个好消息要通知您。",
    "您好，打扰您一下，有个重要业务需要跟您确认一下。",
    "您好，我是优逸花客服，有个专属福利要通知您。",
    "您好，耽误您两分钟时间，有个限时优惠要介绍给您。",
    "您好，我是马上消费工作人员，有个额度提升的好消息。",
    "您好，打扰您了，有个重要提醒需要通知您。",
    "您好，我是优逸花客服，有个预留额度业务要介绍。",
    "您好，有个限时福利要通知您，耽误您一分钟好吗？",
    "您好，我是马上消费客服，有个资金周转的好方案要介绍。",
]


@dataclass
class ChatResult:
    """客服对话结果数据类"""
    response: str
    history_count: int = 0
    memory_count: int = 0
    processing_time: float = 0.0
    dialogue_state: dict = None


class CustomerServiceGradioDemo:
    
    def __init__(self):
        """初始化客服对话 Gradio 演示"""
        self.engine = None
        self.app = None  # CallCenterApplication 实例
        self.turn_counter = 0
        # 上下文控制参数
        self.use_session = True
        self.use_memory = True  # 客服场景启用长期记忆以满足需求2-5
        self.max_recent_events = 10  # 客服场景通常对话较短
        # 模式控制
        self.mode = "contextmind"  # "contextmind" 或 "basic_dst"
        self.dst_tracker = None  # DialogueStateTracker 实例（基础模式）
        self.llm_client = None  # LLM 客户端
        self.last_assistant_response = ""  # 记录上一次助手回复（用于 DST）
        
    async def initialize_engine(self, mode="contextmind", use_session=True, use_memory=True, max_recent_events=10):
        """初始化引擎"""
        try:
            logger.info("=" * 80)
            logger.info(f"🚀 [客服Demo] 开始初始化引擎...")
            logger.info(f"   - 模式: {mode}")
            logger.info(f"   - 会话历史: {'✅' if use_session else '❌'}")
            logger.info(f"   - 长期记忆: {'✅' if use_memory else '❌'}")
            logger.info(f"   - 最大历史: {max_recent_events}轮")
            logger.info("=" * 80)
            
            # 保存配置
            self.mode = mode
            self.use_session = use_session
            self.use_memory = use_memory
            self.max_recent_events = max_recent_events
            
            # 创建LLM客户端
            from utils.llm_client import SimpleLLMClient, LLMConfig
            self.llm_client = SimpleLLMClient(LLMConfig.from_env())
            
            if mode == "basic_dst":
                # 基础 DST 模式
                logger.info("📋 初始化基础 DST 模式...")
                
                # 创建 PromptManager，定义客服领域的槽位
                prompt_manager = PromptManager(domain="callcenter")
                
                # 添加客服领域特定槽位
                prompt_manager.add_slot("issue_type", "问题类型", None)
                prompt_manager.add_slot("customer_name", "客户姓名", None)
                prompt_manager.add_slot("product", "产品名称", None)
                prompt_manager.add_slot("resolution_status", "解决状态", None)
                
                # 创建 DialogueStateTracker
                self.dst_tracker = DialogueStateTracker(
                    llm_client=self.llm_client,
                    prompt_manager=prompt_manager,
                    domain="callcenter"
                )
                
                # 重置对话
                self.dst_tracker.reset_dialogue()
                
                # 机器人主动发起对话
                opening_message = random.choice(OPENING_SCRIPTS)
                self.last_assistant_response = opening_message
                
                logger.info("✅ 基础 DST 模式初始化成功")
                self.engine = None
                self.app = None
                
                logger.info("✅ 引擎初始化完成")
                return f"✅ 基础 DST 模式初始化成功！\n\n📞 客服: {opening_message}"
                
            else:
                # ContextMind 完整模式
                logger.info("🧠 初始化 ContextMind 完整模式...")
                
                from contextmind.core.configs import ExtractionConfig
                
                # 配置知识提取 - 确保全面捕获(需求3)
                extraction_config = ExtractionConfig(
                    extraction_method="llm",  # 使用LLM提取，更全面
                    min_confidence=0.5,  # 适当降低置信度阈值，捕获更多潜在有价值的知识
                    extract_preferences=True,
                    extract_facts=True,
                    extract_events=True,
                    extract_entities=True,
                    extract_relationships=True,
                )
                
                # 创建引擎 (v0.4.0: 使用 LLM 提取知识，基于嵌入向量的语义理解)
                self.engine = ContextEngine(
                    app_name="customer-service-demo",
                    user_id="customer-user",
                    max_recent_events=max_recent_events,
                    llm_client=self.llm_client,  # 用于知识提取的 LLM 客户端
                    extraction_method="llm",  # 使用 LLM 提取（语义理解，40 种类型）
                    extraction_config=extraction_config,  # 应用提取配置
                )
                
                # 配置记忆库检索 - 设置上限(需求4)和综合性(需求3)
                # 需要在引擎初始化后配置MemoryBank
                from contextmind.core.configs import RetrievalConfig
                
                retrieval_config = RetrievalConfig(
                    top_k=3,  # 限制检索出的记忆数量上限为3条(需求4)
                    min_score=0.3,  # 降低阈值，确保不遗漏重要信息(需求3)
                    use_semantic=True,
                    enable_recency_boost=True,  # 启用新近性加权
                )
                # 更新内存银行的配置
                self.engine.memory_bank.config = retrieval_config
                
                logger.info("✅ [客服Demo] 引擎初始化成功 (v0.4.0 - Pure Context Engineering)")
                logger.info(f"   - 记忆检索限制: top_k={retrieval_config.top_k}")
                logger.info(f"   - 知识提取阈值: min_confidence={extraction_config.min_confidence}")
                
                # 初始化 CallCenterApplication
                try:
                    business_info = """
产品介绍：
- 安逸花/马上消费智能金融服务
- 支持额度提升、资金周转、优惠福利

服务承诺：
- 7x24小时在线
- 响应快速、专业友好
"""
                    self.app = CallCenterApplication(
                        context_engine=self.engine,
                        business_info=business_info.strip(),
                        system_prompt=CALLCENTER_SYSTEM_PROMPT,
                        history_turns=10,  # Prompt 中显示的历史轮数
                        use_real_llm=True,  # 使用真实 LLM
                    )
                    logger.info("✅ CallCenterApplication 初始化成功")
                except Exception as app_err:
                    logger.error(f"❌ CallCenterApplication 初始化失败: {str(app_err)}")
                    raise
                
                # 机器人主动发起对话 - 随机选择一条开场白
                opening_message = random.choice(OPENING_SCRIPTS)
                logger.info(f"客服开场: {opening_message}")
                
                # 将开场白添加到会话历史
                await self.engine.session_manager.add_message(
                    role=MessageRole.ASSISTANT,
                    content=opening_message
                )
                
                # 保存开场白以便在UI中显示
                self.opening_message = opening_message
                
                self.dst_tracker = None
                
                # 重置计数器
                self.turn_counter = 0
                
                logger.info("✅ 引擎初始化完成")
                return f"✅ 引擎初始化成功！\n\n📞 客服: {opening_message}"
            
        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = f"❌ 引擎初始化失败: {str(e)}"
            logger.error(error_msg)
            logger.error(f"错误详情:\n{error_details}")
            return error_msg
    
    async def chat(self, user_message: str) -> ChatResult:
        """处理客服对话消息 - 支持 ContextMind 和基础 DST 模式"""
        if self.mode == "basic_dst":
            return await self._chat_basic_dst(user_message)
        else:
            return await self._chat_contextmind(user_message)
    
    async def _chat_basic_dst(self, user_message: str) -> ChatResult:
        """基础 DST 模式的聊天处理"""
        if not self.dst_tracker:
            raise ValueError("DST追踪器未初始化，请先点击'初始化引擎'按钮")
        
        start_time = time.time()
        self.turn_counter += 1
        
        logger.info(f"\n{'='*80}")
        logger.info(f"💬 [轮次 {self.turn_counter}] 用户输入: {user_message}")
        logger.info(f"{'='*80}")
        
        try:
            # 1. 更新对话状态
            dialogue_state = await self.dst_tracker.process_turn(
                system_utterance=self.last_assistant_response,
                user_utterance=user_message
            )
            
            # 2. 构建简单的 prompt（基于状态）
            state_str = "\n".join([f"- {k}: {v}" for k, v in dialogue_state.items()])
            
            prompt = f"""你是一个专业的客服助手。

当前对话状态:
{state_str if state_str else "- 暂无状态信息"}

用户说: {user_message}

请专业、友好地回复用户。"""
            
            # 3. 调用 LLM 生成回复
            messages = [
                {"role": "system", "content": "你是一个专业的客服助手。"},
                {"role": "user", "content": prompt}
            ]
            
            response = await self.llm_client.chat_async(messages=messages)
            
            # 4. 保存助手回复以供下一轮使用
            self.last_assistant_response = response
            
            processing_time = time.time() - start_time
            
            logger.info(f"🤖 助手回复: {response}")
            logger.info(f"⏱️  处理耗时: {processing_time:.2f}秒")
            logger.info(f"📊 对话状态: {dialogue_state}")
            
            return ChatResult(
                response=response,
                history_count=len(self.dst_tracker.turns),
                memory_count=len(dialogue_state),
                processing_time=processing_time,
                dialogue_state=dialogue_state
            )
            
        except Exception as e:
            error_details = traceback.format_exc()
            error_msg = f"处理失败: {str(e)}"
            logger.error(f"❌ {error_msg}")
            logger.error(f"错误详情:\n{error_details}")
            raise
    
    async def _chat_contextmind(self, user_message: str) -> ChatResult:
        """ContextMind 模式的聊天处理 - 使用 CallCenterApplication.process_turn()"""
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
            # 使用 CallCenterApplication 的 process_turn 方法处理对话
            # 这会自动处理：optimize → build_prompt → generate → update → extract_knowledge
            # 与 interactive_demo 使用相同的处理流程
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
        if self.mode == "basic_dst" and self.dst_tracker:
            self.dst_tracker.reset_dialogue()
            opening_message = random.choice(OPENING_SCRIPTS)
            self.last_assistant_response = opening_message
            logger.info("🔄 基础 DST 对话已重置")
            return f"✅ 对话已重置！\n\n📞 客服: {opening_message}"
        elif self.engine:
            await self.engine.clear_session()
            # 重新生成开场白
            opening_message = random.choice(OPENING_SCRIPTS)
            await self.engine.session_manager.add_message(
                role=MessageRole.ASSISTANT,
                content=opening_message
            )
            self.opening_message = opening_message
            logger.info("🔄 ContextMind 对话已重置")
            return f"✅ 对话已重置！\n\n📞 客服: {opening_message}"
        return "✅ 对话已重置，可以开始新的聊天了！"
    
    def get_dialogue_state(self):
        """获取当前对话状态（仅基础 DST 模式）"""
        if self.mode == "basic_dst" and self.dst_tracker:
            state = self.dst_tracker.get_current_state()
            if state:
                import json
                return f"📋 当前对话状态:\n{json.dumps(state, ensure_ascii=False, indent=2)}"
            else:
                return "📋 对话状态: 空"
        else:
            return "⚠️ 此功能仅在基础 DST 模式下可用"
    
    def reset_conversation(self):
        """重置对话（同步包装）"""
        # 为 Gradio 提供同步接口
        return asyncio.run(self.reset_conversation_async())


def create_gradio_interface():
    """创建 Gradio 界面"""
    demo_instance = CustomerServiceGradioDemo()
    
    async def init_engine_async(mode, use_session, use_memory, max_events):
        return await demo_instance.initialize_engine(mode, use_session, use_memory, max_events)
    
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
            
            # 构建状态信息 - 根据模式不同显示不同内容
            if demo_instance.mode == "basic_dst":
                status = f"⏱️ {result.processing_time:.2f}s | 📝 状态槽位: {result.memory_count}个 | 轮次: {result.history_count}"
            else:
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
            # 如果结果包含开场白，添加到聊天历史
            if "📞 客服:" in result:
                opening = result.split("📞 客服:")[-1].strip()
                return result, [{"role": "assistant", "content": opening}], ""
            return result, [], ""
        except Exception as e:
            logger.error(f"[Gradio] 重置失败: {str(e)}")
            return f"❌ 重置失败: {str(e)}", [], ""
    
    def update_mode_visibility(mode):
        """根据模式更新组件可见性"""
        is_contextmind = (mode == "ContextMind 完整模式")
        # 返回: session_visible, memory_visible, state_btn_visible
        return (
            gr.update(visible=is_contextmind),  # use_session_check
            gr.update(visible=is_contextmind),  # use_memory_check
            gr.update(visible=not is_contextmind),  # state_btn
        )
    
    # 创建界面
    with gr.Blocks(title="ContextMind 客服对话Demo v0.4.0") as app:
        gr.Markdown("# 📞 ContextMind v0.4.0 客服对话演示")
        gr.Markdown("智能客服 · 上下文工程 · 专业对话")
        
        with gr.Row():
            with gr.Column(scale=4):
                # 聊天界面 - 主要区域
                chatbot = gr.Chatbot(
                    label="对话窗口",
                    height=450,
                    show_label=False,
                )
                
                with gr.Row():
                    msg_input = gr.Textbox(
                        label="",
                        placeholder="输入您的问题... (按 Enter 发送，Shift+Enter 换行)",
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
                
                # 模式选择器
                mode_radio = gr.Radio(
                    choices=["ContextMind 完整模式", "基础 DST 模式"],
                    value="ContextMind 完整模式",
                    label="运行模式",
                    info="选择对话处理模式"
                )
                
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
                    info="记住对话上下文",
                    visible=True
                )
                
                use_memory_check = gr.Checkbox(
                    label="长期记忆",
                    value=True,
                    info="智能管理客户知识库",
                    visible=True
                )
                
                max_events_slider = gr.Slider(
                    minimum=1,
                    maximum=50,
                    value=10,
                    step=1,
                    label="历史轮数",
                    info="保留的对话轮数"
                )
                
                # 对话状态按钮（仅在基础 DST 模式显示）
                state_btn = gr.Button("📋 查看对话状态", visible=False, size="sm")
                state_output = gr.Textbox(
                    label="对话状态",
                    interactive=False,
                    lines=6,
                    visible=False
                )
                
                gr.Markdown("---")
        
        # 模式切换事件
        mode_radio.change(
            fn=update_mode_visibility,
            inputs=[mode_radio],
            outputs=[use_session_check, use_memory_check, state_btn]
        )
        
        # 事件绑定
        def init_wrapper(mode, use_session, use_memory, max_events):
            # 将模式转换为内部格式
            mode_internal = "basic_dst" if mode == "基础 DST 模式" else "contextmind"
            return asyncio.run(init_engine_async(mode_internal, use_session, use_memory, int(max_events)))
        
        init_btn.click(
            fn=init_wrapper,
            inputs=[mode_radio, use_session_check, use_memory_check, max_events_slider],
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
        
        # 查看对话状态按钮
        state_btn.click(
            fn=lambda: (demo_instance.get_dialogue_state(), gr.update(visible=True)),
            outputs=[state_output, state_output]
        )
        
        # 使用提示（放在底部，横向排列）
        gr.Markdown("---")
        gr.Markdown("### 💡 使用提示")
        with gr.Row():
            with gr.Column():
                gr.Markdown("""
                **ContextMind 完整模式：** 完整上下文工程 · 智能记忆库 · 语义检索
                """)
            with gr.Column():
                gr.Markdown("""
                **基础 DST 模式：** 对话状态追踪 · 槽位填充 · 轻量级处理
                """)
            with gr.Column():
                gr.Markdown("""
                **使用步骤：** 1. 选择模式 → 2. 初始化引擎 → 3. 开始对话
                """)
            with gr.Column():
                gr.Markdown("""
                **常见咨询：** 业务办理 · 额度查询 · 优惠活动
                """)
    
    return app


if __name__ == "__main__":
    print("=" * 60)
    print("📞 ContextMind v0.4.0 客服对话 Gradio Demo")
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
