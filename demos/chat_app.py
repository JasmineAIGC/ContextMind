"""
ChatApplication - 通用闲聊应用示例

展示如何使用ContextEngine构建通用对话应用。
适用于日常闲聊、知识问答、娱乐互动等场景。
"""

import logging
from typing import Optional, Dict

from contextmind import ContextEngine
from contextmind.models import Message, MessageRole, ContextResult, ContextSource, get_logger
from contextmind.pipeline.summarizer import ConversationSummarizer, SummarizationConfig

from .llm_client import SimpleLLMClient, LLMConfig

# 禁用HTTP/网络层的debug日志，减少噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.INFO)

logger = get_logger(__name__)


# 通用闲聊系统提示词
CHAT_SYSTEM_PROMPT = """你是友好、有趣的聊天助手。

角色：像朋友一样自然交流，亲切轻松

对话原则：
1. 简洁有趣 - 回复精炼（通常1-3句），不要过于冗长
2. 保持互动 - 适当提问，让对话继续
3. 善用记忆 - 如果用户分享了个人信息（名字、爱好等），在后续对话中自然提及
4. 尊重边界 - 如果用户表示不想继续某话题，及时转换

风格：亲切自然，适当使用表情和网络用语，幽默风趣但不失礼貌

**重要：回复要简短，通常1-3句话，除非用户明确要求详细解释。**"""


class ChatApplication:
    """通用闲聊应用示例"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        system_prompt: str = CHAT_SYSTEM_PROMPT,
        history_turns: int = 10,
        llm_config: Optional[LLMConfig] = None,
        use_real_llm: bool = True,
        extraction_method: str = None,  # 知识提取方式 ('rule' 或 'llm')
        **config
    ):
        """初始化闲聊应用
        
        Args:
            context_engine: 上下文引擎
            system_prompt: 系统提示词（可自定义）
            history_turns: Prompt中包含的历史轮数
            llm_config: LLM 配置（可选，从环境变量加载）
            use_real_llm: 是否使用真实 LLM（True=调用API，False=模拟回复）
            extraction_method: 知识提取方式 ('rule' 规则提取, 'llm' LLM自动提取)
                如未指定，使用引擎的extraction_method
            **config: 其他配置参数
        """
        self.context_engine = context_engine
        self.system_prompt = system_prompt
        self.history_turns = history_turns
        self.config = config
        self.use_real_llm = use_real_llm
        
        # 记录提取方式
        if extraction_method:
            self.extraction_method = extraction_method
        else:
            self.extraction_method = getattr(context_engine, 'extraction_method', 'rule')
        
        # 初始化 LLM 客户端（如果使用真实 LLM）
        if use_real_llm:
            try:
                self.llm_client = SimpleLLMClient(llm_config)
                logger.info(
                    f"[ChatApplication] ✓ 初始化完成 "
                    f"(真实LLM: {use_real_llm}, 知识提取: {self.extraction_method})"
                )
            except Exception as e:
                logger.warning(f"[ChatApplication] ⚠ LLM 客户端初始化失败: {e}")
                logger.warning("[ChatApplication] 将使用模拟回复")
                self.use_real_llm = False
                self.llm_client = None
        else:
            self.llm_client = None
            logger.info(
                f"[ChatApplication] ✓ 初始化完成 "
                f"(模拟回复, 知识提取: {self.extraction_method})"
            )
        
        # 初始化对话摘要器
        summarization_config = SummarizationConfig(
            summarize_threshold=5,  # 超过5轮触发摘要（降低阈值以更早生成摘要）
            keep_recent_turns=3,  # 保留最近3轮（摘要后显示更少原始对话）
            method="llm"  # 使用LLM摘要（更高质量）
        )
        self.summarizer = ConversationSummarizer(
            config=summarization_config,
            llm_client=self.llm_client if use_real_llm else None
        )
        logger.debug(f"[ChatApplication] ✓ 对话摘要器已初始化 (方式: {summarization_config.method}, 触发阈值: {summarization_config.summarize_threshold}轮)")

    
    async def build_prompt(self, user_input: str, context: ContextResult, debug_info: Optional[Dict] = None) -> str:
        """构建闲聊场景的 Prompt。
        
        包含系统提示词、相关记忆、对话历史和当前输入。
        确保所有部分都在 Prompt 中体现（即使为空）。
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Prompt] ========== 开始构建 Prompt ==========")
        logger.info("=" * 100)
        logger.info("")
        
        prompt_parts = [self.system_prompt]
        
        # 总是添加"已知信息"部分（即使为空）
        RELEVANCE_THRESHOLD = 0.3
        NO_MEMORY_TEXT = "(暂无相关记忆)"
        
        # 从items中提取长期记忆
        long_term_items = [item for item in context.items if item.source == ContextSource.MEMORY]
        if long_term_items:
            logger.info(f"[Prompt] 检查长期记忆: {len(long_term_items)} 条")
            relevant_memories = [
                item for item in long_term_items
                if item.score >= RELEVANCE_THRESHOLD
            ]
            
            if relevant_memories:
                used_memories = relevant_memories[:5]  # 最多使用5条记忆
                memory_text = "\n".join(
                    f"- {item.content}"
                    for item in used_memories
                )
                prompt_parts.append(f"\n## 已知信息\n{memory_text}")
                logger.info(f"[Prompt] ✓ 添加长期记忆到 Prompt: {len(used_memories)} 条")
                for i, item in enumerate(used_memories, 1):
                    logger.debug(f"  {i}. {item.content} (score={item.score:.2f})")
            else:
                # 即使无相关记忆，也添加该部分（标记为空）
                prompt_parts.append(f"\n## 已知信息\n{NO_MEMORY_TEXT}")
                logger.debug(f"[Prompt] 已添加空的'已知信息'部分 (阈值: {RELEVANCE_THRESHOLD})")
        else:
            # 记忆库为空时，也添加该部分
            prompt_parts.append(f"\n## 已知信息\n{NO_MEMORY_TEXT}")
            logger.debug("[Prompt] 已添加空的'已知信息'部分 (记忆库为空)")
        logger.info("")
        
        # 添加对话历史 - 从items中提取
        # 使用对话摘要器智能处理历史（增量摘要模式）
        history_items = [item for item in context.items if item.source == ContextSource.HISTORY]
        summary_info = None  # 摘要信息用于debug
        
        if history_items:
            total_turns = len(history_items)
            
            # 获取完整session历史以确定真实轮数（用于增量判断）
            # 从engine的session获取实际轮数
            import asyncio
            try:
                # 尝试获取session的完整历史长度
                session = self.context_engine.session_manager.get_session()
                if session:
                    # 使用同步方式获取历史（如果在事件循环中）
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # 创建任务以获取历史
                            full_history = asyncio.create_task(session.get_recent_history(limit=1000))
                            actual_turns = len(full_history.result()) if hasattr(full_history, 'result') else total_turns
                        else:
                            full_history = loop.run_until_complete(session.get_recent_history(limit=1000))
                            actual_turns = len(full_history)
                    except:
                        actual_turns = total_turns
                else:
                    actual_turns = total_turns
            except:
                actual_turns = total_turns
            
            # 使用摘要器判断是否需要摘要（传入实际轮数用于增量判断）
            # 注意：get_summary_and_recent 是 async 方法
            # build_prompt 从 async process_turn 调用，因此可以使用 await
            summary, recent_history = await self.summarizer.get_summary_and_recent(history_items, actual_turns)
            
            if summary:
                # 有摘要：添加摘要 + 最近对话
                prompt_parts.append(f"\n## 早期对话摘要\n{summary}")
                logger.info(f"[Prompt] ✓ 添加对话摘要 (总共{total_turns}轮，前{total_turns - len(recent_history)}轮已摘要)")
                
                # 保存摘要信息用于debug
                summary_info = {
                    'has_summary': True,
                    'summary_text': summary,
                    'summarized_turns': self.summarizer.last_summarized_turn,
                    'recent_turns': len(recent_history),
                    'incremental_count': len(self.summarizer.incremental_summaries)
                }
                
                # 添加最近对话
                if recent_history:
                    history_text = "\n".join(item.content for item in recent_history)
                    prompt_parts.append(f"\n## 最近对话\n{history_text}")
                    logger.info(f"[Prompt] ✓ 添加最近对话 ({len(recent_history)} 轮)")
            else:
                # 无摘要：使用传统方式（最多10轮）
                MAX_HISTORY_TURNS = min(self.history_turns, 10)  # 最多10轮
                relevant_history = history_items[-MAX_HISTORY_TURNS:]
                history_text = "\n".join(item.content for item in relevant_history)
                prompt_parts.append(f"\n## 对话历史\n{history_text}")
                logger.info(f"[Prompt] ✓ 添加对话历史 (最近{len(relevant_history)}轮，共{len(history_items)}轮可用)")
                if len(history_items) > MAX_HISTORY_TURNS:
                    logger.debug(f"[Prompt] 提示: 共{len(history_items)}轮对话，仅使用最近{MAX_HISTORY_TURNS}轮（其余{len(history_items)-MAX_HISTORY_TURNS}轮已省略）")
                
                summary_info = {
                    'has_summary': False,
                    'recent_turns': len(relevant_history)
                }
        else:
            logger.debug("[Prompt] 无对话历史")
            summary_info = {'has_summary': False, 'recent_turns': 0}
        
        # 如果提供了debug_info，保存摘要信息
        if summary_info and debug_info is not None:
            debug_info['summary_info'] = summary_info
        
        logger.info("")
        
        # 添加当前输入
        prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
        logger.info(f"[Prompt] ✓ 添加当前用户输入")
        logger.info("")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[Prompt] ✓ Prompt 构建完成 (总长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    async def process_turn(self, user_input: str, debug: bool = False):
        """处理一轮对话
        
        完整的对话处理流程：
        1. 优化上下文（获取相关历史和记忆）
        2. 构建 Prompt
        3. 调用 LLM 生成回复（模拟）
        4. 更新上下文
        5. 提取知识
        
        Args:
            user_input: 用户输入
            debug: 是否返回调试信息
            
        Returns:
            助手回复，或 (助手回复, 调试信息字典) 当debug=True时
        """
        debug_info = {} if debug else None
        
        # 1. 优化上下文
        if debug:
            # 保存优化前的记忆库状态
            memory_cache = self.context_engine.memory_bank.get_memory_cache()
            debug_info['memory_before'] = [
                {
                    "content": m.content,
                    "type": m.metadata.get('type', 'UNKNOWN') if hasattr(m, 'metadata') else 'UNKNOWN',
                    "confidence": m.score  # ContextItem 使用 score 而不是 confidence
                }
                for m in memory_cache
            ]
        
        context_result = await self.context_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        
        if debug:
            # 保存召回结果
            debug_info['context_result'] = {
                'items': [
                    {
                        'content': item.content,
                        'source': str(item.source),
                        'score': item.score,
                        'metadata': item.metadata
                    }
                    for item in context_result.items
                ],
                'total_items': len(context_result.items),
                'compressed': context_result.compressed
            }
        
        # 2. 构建 Prompt (传递debug_info以保存摘要信息)
        prompt = await self.build_prompt(user_input, context_result, debug_info if debug else None)
        
        if debug:
            debug_info['prompt'] = prompt
        
        # 3. 调用 LLM（v7.1: LLM 调用是外部的）
        if self.use_real_llm and self.llm_client:
            try:
                # 调用真实 LLM
                reasoning, response = await self.llm_client.generate_async(prompt)
                if reasoning:
                    logger.debug(f"[LLM Reasoning] {reasoning[:200]}...")
                logger.info(f"[LLM Response] 生成回复 ({len(response)} 字符)")
            except Exception as e:
                logger.error(f"❌ LLM调用失败: {e}")
                response = f"抱歉，我现在有点问题，等会儿再聊好吗？😅"
        else:
            # 模拟回复（仅用于测试）
            response = f"[模拟回复] 收到您的消息：{user_input}。这是一个示例回复，需要配置LLM才能获得真实回复。"
            logger.warning("[Simulated] 使用模拟回复（未配置LLM）")
        
        # 4. 更新上下文
        await self.context_engine.update(
            user_input=user_input,
            assistant_response=response
        )
        
        # 5. 提取知识（如果需要）
        extracted_knowledge = []
        try:
            knowledge_list = await self.context_engine.extract_knowledge(auto_store=True)
            if debug and knowledge_list:
                extracted_knowledge = [
                    {
                        'content': k.content,
                        'type': str(k.knowledge_type),
                        'confidence': k.confidence
                    }
                    for k in knowledge_list
                ]
        except Exception as e:
            logger.warning(f"知识提取失败: {e}")
        
        if debug:
            debug_info['extracted_knowledge'] = extracted_knowledge
            return response, debug_info
        
        return response
