"""
ChatApplication - 通用闲聊应用示例

展示如何使用ContextEngine构建通用对话应用。
适用于日常闲聊、知识问答、娱乐互动等场景。
"""

from contextmind import ContextEngine, Client, ContextResult
from contextmind.utils import get_logger
from .base import BaseApplication

logger = get_logger(__name__)


# 通用闲聊系统提示词
CHAT_SYSTEM_PROMPT = """你是一个友好、有趣的聊天助手。

## 角色定位：
- 像朋友一样自然交流，亲切轻松
- 适当使用表情，让对话更生动
- 记住用户分享的信息，保持对话连贯性
- 话题广泛：聊天、笑话、知识、推荐等

## 对话原则：
1. **简洁有趣**：回复精炼，不要过于冗长
2. **保持互动**：适当提问，让对话继续
3. **善用记忆**：如果用户分享了个人信息（名字、爱好、城市等），在后续对话中自然提及
4. **尊重边界**：如果用户表示不想继续某话题，及时转换

## 风格特点：
- 语气亲切自然，不过于正式
- 适当使用网络用语和表情
- 回答准确但不学究气
- 幽默风趣但不失礼貌

请与用户进行愉快的对话交流！"""


class ChatApplication(BaseApplication):
    """通用闲聊应用示例"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        system_prompt: str = CHAT_SYSTEM_PROMPT,
        history_turns: int = 10,
        **config
    ):
        """初始化闲聊应用
        
        Args:
            context_engine: 上下文引擎
            llm_client: LLM客户端
            system_prompt: 系统提示词（可自定义）
            history_turns: Prompt中包含的历史轮数
            **config: 其他配置参数
        """
        super().__init__(
            context_engine=context_engine,
            llm_client=llm_client,
            system_prompt=system_prompt,
            **config
        )
        
        self.history_turns = history_turns
    
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建闲聊场景 Prompt
        
        包含系统提示词、相关记忆、对话历史和当前输入。
        """
        prompt_parts = [self.system_prompt]
        
        # 添加相关记忆（如果有）
        RELEVANCE_THRESHOLD = 0.3
        
        if context.long_term_memory:
            relevant_memories = [
                item for item in context.long_term_memory
                if item.score >= RELEVANCE_THRESHOLD
            ]
            
            if relevant_memories:
                used_memories = relevant_memories[:5]  # 最多使用5条记忆
                memory_text = "\n".join(
                    f"- {item.content}"
                    for item in used_memories
                )
                prompt_parts.append(f"\n## 已知信息\n{memory_text}")
                logger.debug(f"使用 {len(used_memories)} 条相关记忆")
        
        # 添加对话历史
        if context.recent_history:
            relevant_history = context.recent_history[-self.history_turns:]
            history_text = "\n".join(
                f"{msg.role.value}: {msg.content}"
                for msg in relevant_history
            )
            prompt_parts.append(f"\n## 对话历史\n{history_text}")
            logger.debug(f"包含 {len(relevant_history)} 轮历史")
        
        # 添加当前输入
        prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
        
        return "\n".join(prompt_parts)
