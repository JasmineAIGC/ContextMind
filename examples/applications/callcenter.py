"""
CallCenterApplication - 客服应用示例

展示如何使用ContextEngine构建客服对话应用。

注意：这是一个简化的示例，重点展示上下文工程能力：
- 如何利用对话历史维持上下文连贯性
- 如何利用长期记忆记住重要信息
- 如何精简历史对话只保留相关部分

ContextMind专注于上下文工程，不负责定义agent的基础prompt。
基础prompt应由使用ContextMind的应用层自行定义。
"""

from contextmind import ContextEngine, Client, ContextResult
from contextmind.pipeline.context_optimizer import DEFAULT_MAX_SESSION_ITEMS
from contextmind.logger import get_logger
from .base import BaseApplication

logger = get_logger(__name__)


class CallCenterApplication(BaseApplication):
    """
    客服应用示例
    
    展示如何利用上下文引擎构建一个智能客服应用：
    - 利用对话历史提供连贯的回复
    - 利用长期记忆记住用户的重要信息
    - 使用业务知识提供准确的服务
    """
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        business_info: str = "",
        history_turns: int = 10,
        **config
    ):
        """
        初始化客服应用
        
        Args:
            context_engine: 上下文引擎实例
            llm_client: LLM客户端实例
            business_info: 业务信息（产品介绍、服务流程等）
            history_turns: Prompt中包含的历史对话轮数（默认10）
            **config: 其他配置
        """
        # 极简系统提示词 - ContextMind专注上下文，不定义agent行为
        system_prompt = "你是一个智能对话助手。请基于提供的上下文信息进行回复。"

        super().__init__(
            context_engine=context_engine,
            llm_client=llm_client,
            system_prompt=system_prompt,
            **config
        )
        
        self.business_info = business_info
        self.history_turns = history_turns
    
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """
        构建客服场景的Prompt
        
        上下文工程的核心：将多源上下文整合为高质量的prompt。
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的Prompt
        """
        prompt_parts = [self.system_prompt]
        
        # === 1. 首先打印记忆库所有内容（调试信息）===
        logger.info("=" * 80)
        logger.info("📚 记忆库全部内容:")
        if context.long_term_memory:
            for i, item in enumerate(context.long_term_memory, 1):
                logger.info(f"  [{i}] {item.content} (score={item.score:.2f})")
            logger.info(f"  总计: {len(context.long_term_memory)} 条记忆")
        else:
            logger.warning("  记忆库为空")
        logger.info("=" * 80)
        
        # === 2. 添加长期记忆到Prompt（只取前5条）===
        if context.long_term_memory:
            used_memories = context.long_term_memory[:5]
            memory_text = "\n".join(
                f"- {item.content}"
                for item in used_memories
            )
            prompt_parts.append(f"\n## 长期记忆\n{memory_text}")
            logger.info(f"✓ 本次使用的记忆 ({len(used_memories)} 条):")
            for i, item in enumerate(used_memories, 1):
                logger.info(f"  ✓ [{i}] {item.content} (score={item.score:.2f})")
        else:
            logger.warning("⚠ No long-term memory included in prompt")
        
        # === 3. 添加对话历史（使用配置的轮数）===
        if context.recent_history:
            # 使用配置的history_turns参数
            relevant_history = context.recent_history[-self.history_turns:]
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}"
                for msg in relevant_history
            )
            prompt_parts.append(f"\n## 相关对话历史\n{history_text}")
            logger.info(f"✓ Prompt includes {len(relevant_history)} turns of history (max={self.history_turns})")
        
        # === 4. 添加业务信息（可选）===
        if self.business_info:
            prompt_parts.append(f"\n## 参考信息\n{self.business_info}")
        
        # === 5. 添加当前用户输入===
        prompt_parts.append(f"\n## 当前问题\n{user_input}")
        
        return "\n".join(prompt_parts)
