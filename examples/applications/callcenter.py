"""
CallCenterApplication - 客服应用示例

展示如何使用ContextEngine构建客服对话应用。
"""

from contextmind import ContextEngine, Client, ContextResult
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
        system_prompt = """你是一个专业的客服助手。

职责：
1. 礼貌、耐心地回答用户问题
2. 提供准确的业务信息
3. 记住用户的重要信息和偏好
4. 根据对话历史提供连贯的服务

回复要求：
- 简洁明了，不超过50字
- 礼貌友好，使用恰当的称呼
- 针对性强，直接回答用户问题
- 如果不确定，主动询问或澄清"""

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
        
        结合系统角色、业务信息、对话历史和用户输入。
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的Prompt
        """
        prompt_parts = [self.system_prompt]
        
        # 添加业务信息
        if self.business_info:
            prompt_parts.append(f"\n## 业务信息\n{self.business_info}")
        
        # 添加长期记忆（用户的重要信息）
        if context.long_term_memory:
            memory_text = "\n".join(
                f"- {item.content}"
                for item in context.long_term_memory[:3]  # 只取前3条
            )
            prompt_parts.append(f"\n## 用户历史信息\n{memory_text}")
        
        # 添加对话历史
        if context.recent_history:
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}"
                for msg in context.recent_history[-3:]  # 只取最近3轮
            )
            prompt_parts.append(f"\n## 近期对话\n{history_text}")
        
        # 添加当前用户输入
        prompt_parts.append(f"\n## 当前用户输入\nuser: {user_input}")
        
        # 添加回复指令
        prompt_parts.append("\n请根据以上信息，给出合适的回复：")
        
        return "\n".join(prompt_parts)
