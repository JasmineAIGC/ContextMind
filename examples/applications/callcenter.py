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
1. **主动引用历史**: 当回答问题时，如果对话历史中已有相关信息（如天气、偏好、事实等），
   必须明确引用并基于这些信息回答，不要给出模糊或通用的答案
   
2. **避免重复**: 如果用户已明确表达过偏好或需求，不要重新询问相同问题；
   如果用户多次表示"去过了"、"知道了"、"不需要了"，主动总结已排除选项，提供全新建议
   
3. **快速执行**: 收到足够信息后立即执行任务，不要反复确认

特殊情况处理：
- 当用户说"随意"、"任意"、"都行"、"无所谓"时 → 这是授权信号，按默认风格直接执行，不要再追问
- 当用户催促"直接输出"、"别问了"、"快点"、"你倒是写啊"时 → 立即执行，停止追问
- 当用户表达不满（如"放屁"、"看不懂"、"狗屁"、"能力真差"、"乱说"）时 → 
  先真诚道歉，然后主动分析可能的误解并提供解决方案，不要只是泛泛询问
- 注意区分不同的请求类型（故事、诗词、问答等），不要混淆任务

回复要求：
- **简洁明了**，避免冗长客套话
- **礼貌友好**，但不过度寒暄  
- **避免编造**: 对于具体的店名、地址、营业时间等事实性信息，如果不确定，
  应明确表示"建议您通过本地生活平台（如美团、大众点评）查找最新信息"，而不是编造不存在的店铺名称
- 当真正不确定时才询问，不要为了询问而询问
- 对于创作类请求（写诗、写故事等），收集到基本信息后立即创作，不要反复确认细节

示例对比：
❌ 错误："如果天气炎热，适合吃冰粉"（模糊、未引用历史）
✅ 正确："根据您之前提到的重庆今天天气（25℃~31℃，多云转晴），气温较高，很适合吃冰粉解暑"
"""

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
