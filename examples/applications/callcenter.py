"""
CallCenterApplication - 客服应用示例

展示如何使用ContextEngine构建客服对话应用。
重点展示上下文工程能力：利用历史、记忆和知识提供连贯回复。
"""

from contextmind import ContextEngine, Client, ContextResult
from contextmind.pipeline.compressor import DEFAULT_MAX_SESSION_ITEMS
from contextmind.utils import get_logger
from .base import BaseApplication
from ..prompts import get_system_prompt

logger = get_logger(__name__)


class CallCenterApplication(BaseApplication):
    """客服应用示例"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        business_info: str = "",
        history_turns: int = 10,
        **config
    ):
        """初始化客服应用"""
        system_prompt = get_system_prompt(include_business_info=True)

        super().__init__(
            context_engine=context_engine,
            llm_client=llm_client,
            system_prompt=system_prompt,
            **config
        )
        
        self.business_info = business_info
        self.history_turns = history_turns
    
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建客服场景 Prompt"""
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Prompt] ========== 开始构建 Prompt ==========")
        logger.info("=" * 100)
        logger.info("")
        
        prompt_parts = [self.system_prompt]
        
        # 记忆库日志
        logger.info("[Prompt] 📚 检查记忆库状态:")
        if context.long_term_memory:
            for i, item in enumerate(context.long_term_memory, 1):
                logger.info(f"  [{i}] {item.content} (score={item.score:.2f})")
            logger.info(f"  总计: {len(context.long_term_memory)} 条")
        else:
            logger.warning("  记忆库为空")
        logger.info("")
        
        # 添加相关记忆到 Prompt
        RELEVANCE_THRESHOLD = 0.3
        
        if context.long_term_memory:
            relevant_memories = [
                item for item in context.long_term_memory
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
        
        # 添加对话历史到 Prompt - 只添加最近N轮
        if context.recent_history:
            relevant_history = context.recent_history[-self.history_turns:]
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}"
                for msg in relevant_history
            )
            prompt_parts.append(f"\n## 对话历史\n{history_text}")
            logger.info(f"[Prompt] ✓ 添加对话历史到 Prompt (最近 {len(relevant_history)} 轮，共 {len(context.recent_history)} 轮可用)")
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
