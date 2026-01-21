"""
ChatApplication - 通用闲聊应用示例

展示如何使用ContextEngine构建通用对话应用。
适用于日常闲聊、知识问答、娱乐互动等场景。
"""

from typing import Optional

from contextmind import ContextEngine
from contextmind.models import Message, MessageRole, ContextResult, ContextSource, get_logger

from .llm_client import SimpleLLMClient, LLMConfig

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


class ChatApplication:
    """通用闲聊应用示例"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        system_prompt: str = CHAT_SYSTEM_PROMPT,
        history_turns: int = 10,
        llm_config: Optional[LLMConfig] = None,
        use_real_llm: bool = True,
        **config
    ):
        """初始化闲聊应用
        
        Args:
            context_engine: 上下文引擎
            system_prompt: 系统提示词（可自定义）
            history_turns: Prompt中包含的历史轮数
            llm_config: LLM 配置（可选，从环境变量加载）
            use_real_llm: 是否使用真实 LLM（True=调用API，False=模拟回复）
            **config: 其他配置参数
        """
        self.context_engine = context_engine
        self.system_prompt = system_prompt
        self.history_turns = history_turns
        self.config = config
        self.use_real_llm = use_real_llm
        
        # 初始化 LLM 客户端（如果使用真实 LLM）
        if use_real_llm:
            try:
                self.llm_client = SimpleLLMClient(llm_config)
                logger.info("[ChatApplication] ✓ 初始化完成 (使用真实 LLM)")
            except Exception as e:
                logger.warning(f"[ChatApplication] ⚠ LLM 客户端初始化失败: {e}")
                logger.warning("[ChatApplication] 将使用模拟回复")
                self.use_real_llm = False
                self.llm_client = None
        else:
            self.llm_client = None
            logger.info("[ChatApplication] ✓ 初始化完成 (使用模拟回复)")
    
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建闲聊场景 Prompt
        
        包含系统提示词、相关记忆、对话历史和当前输入。
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[Prompt] ========== 开始构建 Prompt ==========")
        logger.info("=" * 100)
        logger.info("")
        
        prompt_parts = [self.system_prompt]
        
        # 添加相关记忆（如果有）
        RELEVANCE_THRESHOLD = 0.3
        
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
                logger.debug(f"[Prompt] 无相关记忆 (阈值: {RELEVANCE_THRESHOLD})")
        else:
            logger.debug("[Prompt] 无长期记忆")
        logger.info("")
        
        # 添加对话历史 - 从items中提取
        history_items = [item for item in context.items if item.source == ContextSource.HISTORY]
        if history_items:
            relevant_history = history_items[-self.history_turns:]
            history_text = "\n".join(
                item.content for item in relevant_history
            )
            prompt_parts.append(f"\n## 对话历史\n{history_text}")
            logger.info(f"[Prompt] ✓ 添加对话历史到 Prompt (最近 {len(relevant_history)} 轮，共 {len(history_items)} 轮可用)")
        else:
            logger.debug("[Prompt] 无对话历史")
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
        try:
            await self.context_engine.extract_knowledge(auto_store=True)
        except Exception as e:
            logger.warning(f"知识提取失败: {e}")
        
        return response
