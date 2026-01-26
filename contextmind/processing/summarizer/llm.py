"""
LLMBasedSummarizer - 基于LLM的智能摘要器

使用LLM的语义理解能力生成高质量摘要
"""

from typing import List, Optional, Any

from ...core.models import Message, MessageRole, get_logger
from .base import SummarizerStrategy, SummarizationConfig

logger = get_logger(__name__)


class LLMBasedSummarizer(SummarizerStrategy):
    """
    基于LLM的摘要器（推荐使用）
    
    ✨ 使用LLM的语义理解能力生成高质量摘要
    📊 能够智能提取关键信息和主题
    
    相比规则摘要（RuleBasedSummarizer），LLM摘要器能够：
    1. ✅ 理解对话的语义和上下文
    2. ✅ 识别隐含的主题和意图
    3. ✅ 生成流畅自然的摘要文本
    4. ✅ 自动提取关键点和要点
    5. ✅ 更高的准确性和可读性
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[Any] = None
    ):
        """
        初始化LLM摘要器
        
        Args:
            llm_client: LLM客户端（需要有generate方法）
            config: 配置，可以是 SummarizationConfig 或字典
        """
        self.llm_client = llm_client
        
        # 支持 SummarizationConfig 或 dict
        if isinstance(config, SummarizationConfig):
            self.max_summary_length = config.max_summary_length
            self.llm_max_tokens = config.llm_max_tokens
            self.llm_temperature = config.llm_temperature
        else:
            self.config = config or {}
            self.max_summary_length = self.config.get('max_summary_length', 200)
            self.llm_max_tokens = self.config.get('llm_max_tokens', 150)
            self.llm_temperature = self.config.get('llm_temperature', 0.3)
        
        if llm_client:
            logger.info("[LLMBasedSummarizer] 初始化完成 - 使用LLM智能摘要")
        else:
            logger.warning("[LLMBasedSummarizer] 未提供LLM客户端 - 将回退到规则摘要")
    
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """
        使用LLM生成摘要
        
        Args:
            messages: 消息列表
            existing_summary: 已有摘要 (用于增量更新)
            
        Returns:
            摘要文本
        """
        from .rule import RuleBasedSummarizer
        
        # 如果没有LLM客户端，回退到规则摘要
        if not self.llm_client:
            logger.debug("[LLMBasedSummarizer] 回退到规则摘要 (无LLM客户端)")
            fallback = RuleBasedSummarizer(self.config)
            return await fallback.summarize(messages, existing_summary)
        
        if not messages:
            return "暂无对话历史"
        
        logger.info(f"[LLMBasedSummarizer] 开始LLM摘要生成 - 处理 {len(messages)} 条消息")
        
        # 构建对话文本
        conversation_text = self._build_conversation_text(messages)
        
        # 构建prompt
        system_prompt = """你是一个专业的对话摘要助手。请从对话中提取关键信息并生成简洁的摘要。

**摘要要求**:
1. 提取对话的核心主题和关键信息
2. 使用简洁清晰的语言
3. 保留重要细节（如时间、地点、人物、计划等）
4. 按时间顺序组织信息
5. 每个要点单独成行，使用数字编号

**摘要格式**:
```
对话轮次: X 轮
1. 第一个关键点
2. 第二个关键点
...
```

**注意事项**:
- **只提取用户相关的重要信息（用户的偏好、需求、计划、个人信息等）**
- **不要提取助手/机器人的信息（如助手的自我介绍、助手的能力等）**
- 忽略简单的问候和确认
- 合并重复或相似的信息
- 保持客观，不添加主观评价
- 摘要应该以用户为中心，记录用户说了什么、想要什么"""
        
        # 如果有已存在的摘要，说明这是增量更新
        if existing_summary:
            user_prompt = f"""请基于以下已有摘要和新对话，生成更新后的完整摘要：

已有摘要：
{existing_summary}

新对话：
{conversation_text}

请生成合并后的完整摘要，保持简洁清晰。"""
        else:
            user_prompt = f"""请对以下对话生成摘要：

{conversation_text}

请生成简洁清晰的摘要。"""
        
        # 合并为完整prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # 调用LLM
        try:
            if hasattr(self.llm_client, 'generate_async'):
                # 异步调用
                _, summary = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                # 同步调用（返回 reasoning, content 元组）
                _, summary = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")
            
            # 清理摘要文本
            summary = summary.strip()
            
            # 截断过长的摘要
            if len(summary) > self.max_summary_length * 2:  # 给LLM摘要更多空间
                summary = summary[:self.max_summary_length * 2] + "..."
            
            logger.info(f"[LLMBasedSummarizer] LLM摘要生成完成 - 长度: {len(summary)}")
            return summary
            
        except Exception as e:
            logger.error(f"[LLMBasedSummarizer] LLM调用失败: {e}")
            # 回退到规则摘要
            logger.info("[LLMBasedSummarizer] 回退到规则摘要")
            fallback = RuleBasedSummarizer(self.config)
            return await fallback.summarize(messages, existing_summary)
    
    def _build_conversation_text(self, messages: List[Message]) -> str:
        """构建对话文本用于LLM摘要"""
        lines = []
        for msg in messages:
            role_name = "用户" if msg.role == MessageRole.USER else "助手"
            lines.append(f"{role_name}: {msg.content}")
        return "\n".join(lines)
