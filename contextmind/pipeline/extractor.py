"""
KnowledgeExtractor - 知识提取模块

职责：
- 从对话中提取关键信息
- 生成结构化知识
- 更新长期记忆

策略：
- 基于规则的提取
- LLM辅助提取（预留）
- 实体识别
- 关系抽取
"""

from typing import List, Optional
from ..core import Message, Knowledge
from ..strategies.extraction import RuleBasedExtractionStrategy
from ..core import get_logger

logger = get_logger(__name__)


class KnowledgeExtractor:
    """
    知识提取器
    
    从对话中提取关键信息并结构化：
    - 用户偏好
    - 用户事实
    - 关键决策
    """
    
    def __init__(
        self,
        strategy: Optional[RuleBasedExtractionStrategy] = None,
    ):
        """
        初始化提取器
        
        Args:
            strategy: 提取策略（可插拔）
        """
        self.strategy = strategy or RuleBasedExtractionStrategy()
    
    async def extract(
        self,
        messages: List[Message],
    ) -> List[Knowledge]:
        """
        提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
        """
        # 委托给提取策略
        knowledge_list = await self.strategy.extract(messages)
        
        logger.debug(f"Extracted {len(knowledge_list)} knowledge items")
        
        return knowledge_list
