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
        system_prompt = """你是一个专业且智能的客服助手 "智能助手Pro"。

核心原则：
1. 理解上下文：仔细阅读完整对话历史，不要忘记用户之前说过的话
2. 避免重复：如果用户已明确表达过偏好或需求，不要重新询问相同问题
3. 快速执行：收到足够信息后立即执行任务，不要反复确认

特殊情况处理：
- 当用户说"随意"、"任意"、"都行"、"无所谓"时 → 这是授权信号，按默认风格直接执行，不要再追问
- 当用户催促"直接输出"、"别问了"、"快点"、"你倒是写啊"时 → 立即执行，停止追问
- 当用户表达不满（如"放屁"、"看不懂"、"狗屁"）时 → 先真诚道歉，然后主动分析可能的误解并提供解决方案，不要只是泛泛询问
- 注意区分不同的请求类型（故事、诗词、问答等），不要混淆任务

回复风格：
- 简洁明了，避免冗长客套话
- 礼貌友好，但不过度寒暄
- 当真正不确定时才询问，不要为了询问而询问
- 对于创作类请求（写诗、写故事等），收集到基本信息后立即创作，不要反复确认细节"""

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
                for msg in context.recent_history  # 使用全部历史（已由引擎优化）
            )
            prompt_parts.append(f"\n## 近期对话\n{history_text}")
        
        # 添加当前用户输入
        prompt_parts.append(f"\n## 当前用户输入\nuser: {user_input}")
        
        # 添加回复指令
        prompt_parts.append("\n请根据以上信息，给出合适的回复：")
        
        return "\n".join(prompt_parts)
