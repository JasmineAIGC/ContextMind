"""
CallCenterApplication - 客服应用示例

展示如何使用ContextEngine构建客服对话应用。
重点展示上下文工程能力：利用历史、记忆和知识提供连贯回复。
"""

from typing import Optional

from contextmind import ContextEngine
from contextmind.models import Message, MessageRole, ContextResult, ContextSource, get_logger

from .llm_client import SimpleLLMClient, LLMConfig

logger = get_logger(__name__)

# 客服系统提示词
CALLCENTER_SYSTEM_PROMPT = """你是专业客服助手。

角色：热情、耐心、专业的客服人员

服务原则：
1. 简洁明了 - 直接回答问题，避免冗长
2. 准确回答 - 基于已知信息给出正确答复  
3. 记住客户 - 利用历史信息提供连贯服务
4. 专业礼貌 - 保持礼貌，使用专业术语

**重要：回复要简洁，通常1-3句话即可，除非问题复杂需要详细说明。**"""


class CallCenterApplication:
    """客服应用示例"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        business_info: str = "",
        history_turns: int = 10,
        system_prompt: str = CALLCENTER_SYSTEM_PROMPT,
        llm_config: Optional[LLMConfig] = None,
        use_real_llm: bool = True,
        **config
    ):
        """初始化客服应用
        
        Args:
            context_engine: ContextMind 引擎实例
            business_info: 业务信息
            history_turns: 历史轮数
            system_prompt: 系统提示
            llm_config: LLM 配置（可选，从环境变量加载）
            use_real_llm: 是否使用真实 LLM（True=调用API，False=模拟回复）
        """
        self.context_engine = context_engine
        self.business_info = business_info
        self.history_turns = history_turns
        self.system_prompt = system_prompt
        self.config = config
        self.use_real_llm = use_real_llm
        
        # 初始化 LLM 客户端（如果使用真实 LLM）
        if use_real_llm:
            try:
                self.llm_client = SimpleLLMClient(llm_config)
                logger.info("[CallCenterApplication] ✓ 初始化完成 (使用真实 LLM)")
            except Exception as e:
                logger.warning(f"[CallCenterApplication] ⚠ LLM 客户端初始化失败: {e}")
                logger.warning("[CallCenterApplication] 将使用模拟回复")
                self.use_real_llm = False
                self.llm_client = None
        else:
            self.llm_client = None
            logger.info("[CallCenterApplication] ✓ 初始化完成 (使用模拟回复)")
    
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建客服场景 Prompt"""
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Prompt] ========== 开始构建 Prompt ==========")
        logger.info("=" * 100)
        logger.info("")
        
        prompt_parts = [self.system_prompt]
        
        # 记忆库日志 - 从items中提取长期记忆
        logger.info("[Prompt] 📚 检查记忆库状态:")
        long_term_items = [item for item in context.items if item.source == ContextSource.MEMORY]
        if long_term_items:
            for i, item in enumerate(long_term_items, 1):
                logger.info(f"  [{i}] {item.content} (score={item.score:.2f})")
            logger.info(f"  总计: {len(long_term_items)} 条")
        else:
            logger.warning("  记忆库为空")
        logger.info("")
        
        # 添加相关记忆到 Prompt
        RELEVANCE_THRESHOLD = 0.3
        
        if long_term_items:
            relevant_memories = [
                item for item in long_term_items
                if item.score >= RELEVANCE_THRESHOLD
            ]
            
            if relevant_memories:
                used_memories = relevant_memories[:5]
                memory_text = "\n".join(
                    f"- {item.content}"
                    for item in used_memories
                )
                prompt_parts.append(f"\n## 长期记忆\n{memory_text}")
                logger.info(f"[Prompt] ✓ 添加长期记忆到 Prompt ({len(used_memories)} 条):")
                for i, item in enumerate(used_memories, 1):
                    logger.info(f"  ✓ [{i}] {item.content} (score={item.score:.2f})")
            else:
                logger.info(f"[Prompt] ⚠ 无相关记忆 (score < {RELEVANCE_THRESHOLD:.2f})")
        else:
            logger.warning("[Prompt] ⚠ 无长期记忆")
        logger.info("")
        
        # 添加对话历史到 Prompt - 从items中提取
        history_items = [item for item in context.items if item.source == ContextSource.HISTORY]
        if history_items:
            relevant_history = history_items[-self.history_turns:]
            history_text = "\n".join(
                item.content for item in relevant_history
            )
            prompt_parts.append(f"\n## 对话历史\n{history_text}")
            logger.info(f"[Prompt] ✓ 添加对话历史到 Prompt (最近 {len(relevant_history)} 轮，共 {len(history_items)} 轮可用)")
        else:
            logger.info("[Prompt] ⚠ 无对话历史")
        logger.info("")
        
        # 添加当前输入
        prompt_parts.append(f"\n## 当前问题\n{user_input}")
        logger.info(f"[Prompt] ✓ 添加当前用户输入")
        logger.info("")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[Prompt] ✓ Prompt 构建完成 (总长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    async def process_turn(self, user_input: str) -> str:
        """处理一轮对话
        
        完整的对话处理流程：
        1. 优化上下文（获取相关历史和记忆）
        2. 构建 Prompt
        3. 调用 LLM 生成回复（模拟）
        4. 更新上下文
        5. 提取知识
        
        Args:
            user_input: 用户输入
            
        Returns:
            助手回复
        """
        # 1. 优化上下文
        context_result = await self.context_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        
        # 2. 构建 Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # 3. 调用 LLM（v7.1: LLM invocation is external）
        if self.use_real_llm and self.llm_client:
            try:
                # 调用真实 LLM
                reasoning, response = await self.llm_client.generate_async(prompt)
                if reasoning:
                    logger.debug(f"[LLM Reasoning] {reasoning[:200]}...")
            except Exception as e:
                logger.error(f"[LLM Error] {e}")
                response = f"[LLM调用失败] {str(e)}"
        else:
            # 模拟回复（仅用于测试）
            response = f"[模拟回复] 收到您的问题：{user_input}。这是一个示例回复，实际应用中需要调用真实的LLM。"
        
        # 4. 更新上下文
        await self.context_engine.update(
            user_input=user_input,
            assistant_response=response
        )
        
        # 5. 提取知识（如果需要）
        try:
            await self.context_engine.extract_knowledge(auto_store=True)
        except Exception as e:
            logger.warning(f"知识提取失败: {e}")
        
        return response
