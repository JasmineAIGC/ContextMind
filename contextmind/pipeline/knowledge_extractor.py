"""
KnowledgeExtractor - 知识提取器

从对话中提取结构化知识，用于持久化到长期记忆。
此组件委托给 ExtractionStrategy 来执行实际提取逻辑。

v3.2 Agent Memory System 更新：
- 支持提取为MemoryNote（结构化记忆笔记）
- 自动生成关键词、标签
- 区分语义记忆和情节记忆

上下文工程核心能力：
- 从对话历史中自动提炼有价值的知识
- 识别用户偏好、重要事实、关键事件
- 生成可用于指导后续对话的记忆条目
"""

from typing import List, Optional
import re
import hashlib

from ..data_models import Message, Knowledge, KnowledgeType, MemoryNote, MemoryType
from ..strategies import ExtractionStrategy, RuleBasedExtractionStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class KnowledgeExtractor:
    """
    知识提取器
    
    从对话消息中提取结构化知识，委托给可插拔的提取策略。
    默认使用 RuleBasedExtractionStrategy。
    
    这些提取的知识将作为长期记忆存储，在后续对话中
    通过语义相似度检索，为LLM提供更精准的上下文信息。
    """
    
    def __init__(
        self, 
        min_confidence: float = 0.5,
        strategy: Optional[ExtractionStrategy] = None
    ):
        """
        初始化知识提取器
        
        Args:
            min_confidence: 最小置信度阈值，低于此值的知识将被过滤
            strategy: 自定义提取策略，默认使用 RuleBasedExtractionStrategy
        """
        self.min_confidence = min_confidence
        self.strategy = strategy or RuleBasedExtractionStrategy(min_confidence=min_confidence)
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        从消息列表中提取知识
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的知识列表
        """
        if not messages:
            return []
        
        # 委托给策略执行提取
        knowledge = await self.strategy.extract(messages)
        
        logger.debug(f"Extracted {len(knowledge)} knowledge items from {len(messages)} messages")
        
        return knowledge
    
    def convert_to_memory_notes(self, knowledge: List[Knowledge]) -> List[MemoryNote]:
        """
        将知识转换为 MemoryNote（Agent Memory System）
        
        Args:
            knowledge: 知识列表
            
        Returns:
            MemoryNote 列表
        """
        notes = []
        
        for k in knowledge:
            # 生成唯一ID（使用内容哈希）
            note_id = hashlib.md5(k.content.encode()).hexdigest()[:12]
            
            # 确定记忆类型
            if k.type == KnowledgeType.EVENT:
                memory_type = MemoryType.EPISODIC  # 事件属于情节记忆
            else:
                memory_type = MemoryType.SEMANTIC  # 其他属于语义记忆
            
            # 提取关键词（简单分词）
            keywords = self._extract_keywords(k.content)
            
            # 生成标签
            tags = [k.type.value]
            if k.metadata.get('sentiment'):
                tags.append(k.metadata['sentiment'])
            
            note = MemoryNote(
                id=note_id,
                content=k.content,
                memory_type=memory_type,
                keywords=keywords,
                tags=tags,
                importance_score=k.confidence,
            )
            
            notes.append(note)
        
        return notes
    
    def _extract_keywords(self, text: str) -> List[str]:
        """简单关键词提取"""
        # 移除标点符号
        clean_text = re.sub(r'[^\w\s]', ' ', text)
        # 分词（简单按空格分割）
        words = clean_text.split()
        # 过滤长度
        keywords = [w for w in words if 2 <= len(w) <= 10]
        # 去重并限制数量
        return list(dict.fromkeys(keywords))[:5]
