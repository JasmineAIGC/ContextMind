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
from .base import BaseApplication


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
        **config
    ):
        """
        初始化客服应用
        
        Args:
            context_engine: 上下文引擎实例
            llm_client: LLM客户端实例
            business_info: 业务信息（产品介绍、服务流程等）
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
        
        # 添加长期记忆（用户的重要信息）- 上下文工程核心能力
        if context.long_term_memory:
            memory_text = "\n".join(
                f"- {item.content}"
                for item in context.long_term_memory[:5]  # 取最相关的5条
            )
            prompt_parts.append(f"\n## 长期记忆\n{memory_text}")
            logger.info(f"✓ Prompt includes {len(context.long_term_memory[:5])} long-term memories")
        else:
            logger.warning("⚠ No long-term memory included in prompt")
        
        # 添加对话历史 - 只取最相关的部分（由引擎优化）
        if context.recent_history:
            # 限制历史对话数量，只保留最相关的
            relevant_history = context.recent_history[-DEFAULT_MAX_SESSION_ITEMS:]
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}"
                for msg in relevant_history
            )
            prompt_parts.append(f"\n## 相关对话历史\n{history_text}")
        
        # 添加业务信息（可选）
        if self.business_info:
            prompt_parts.append(f"\n## 参考信息\n{self.business_info}")
        
        # 添加当前用户输入
        prompt_parts.append(f"\n## 当前问题\n{user_input}")
        
        return "\n".join(prompt_parts)
