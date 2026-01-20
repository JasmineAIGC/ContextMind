"""
Memory Extractors - Plugin implementations for knowledge extraction

This module provides various strategies for extracting valuable information
from conversations that should be stored in long-term memory.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ...core import Message, Knowledge, KnowledgeType
from ...core.config import ExtractionConfig, DEFAULT_MEMORY_CONFIG
from ...utils import get_logger

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """
    Base interface for memory extractors
    
    Extractors analyze conversations and identify information worth storing
    in long-term memory (facts, preferences, events, etc.)
    """
    
    @abstractmethod
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        Extract knowledge from messages
        
        Args:
            messages: List of conversation messages
            
        Returns:
            List of extracted knowledge items
        """
        pass


class RuleBasedExtractor(BaseExtractor):
    """
    Rule-based knowledge extractor (existing implementation)
    
    Uses pattern matching and heuristics to extract facts, preferences,
    and events from conversations. Lightweight and deterministic.
    """
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        """
        Initialize rule-based extractor
        
        Args:
            config: Extraction configuration, uses default if None
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
    
    # Properties for backward compatibility with existing code
    @property
    def CONFIDENCE_FILTER_MIN(self) -> float:
        return self.config.min_confidence
    
    @property
    def CONFIDENCE_PREFERENCE_POSITIVE(self) -> float:
        return self.config.preference_confidence
    
    @property
    def CONFIDENCE_PREFERENCE_NEGATIVE(self) -> float:
        return self.config.preference_confidence * 0.9
    
    @property
    def CONFIDENCE_FACT(self) -> float:
        return self.config.fact_confidence
    
    @property
    def CONFIDENCE_EVENT(self) -> float:
        return self.config.event_confidence
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        Extract knowledge using rule-based patterns
        
        Args:
            messages: Conversation messages
            
        Returns:
            List of extracted knowledge
        """
        logger.info(f"[Extractor] 开始基于规则的知识提取 - 处理 {len(messages)} 条消息")
        
        knowledge = []
        
        # Extract preferences
        preferences = self._extract_preferences(messages)
        knowledge.extend(preferences)
        logger.debug(f"[Extractor] 提取偏好: {len(preferences)} 条")
        
        # Extract facts
        facts = self._extract_facts(messages)
        knowledge.extend(facts)
        logger.debug(f"[Extractor] 提取事实: {len(facts)} 条")
        
        # Extract events
        events = self._extract_events(messages)
        knowledge.extend(events)
        logger.debug(f"[Extractor] 提取事件: {len(events)} 条")
        
        # Filter low-confidence knowledge
        before_filter = len(knowledge)
        knowledge = [k for k in knowledge if k.confidence >= self.CONFIDENCE_FILTER_MIN]
        filtered_count = before_filter - len(knowledge)
        
        if filtered_count > 0:
            logger.debug(f"[Extractor] 过滤低置信度知识: {filtered_count} 条 (阈值: {self.CONFIDENCE_FILTER_MIN})")
        
        logger.info(f"[Extractor] ✓ 知识提取完成 - 总计 {len(knowledge)} 条有效知识")
        
        if knowledge:
            logger.debug(f"[Extractor] 提取的知识详情:")
            for i, k in enumerate(knowledge[:5], 1):
                logger.debug(f"  {i}. [{k.type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
            if len(knowledge) > 5:
                logger.debug(f"  ... 以及其他 {len(knowledge) - 5} 条知识")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """Extract user preferences from messages"""
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 2:
                continue
            
            # Positive preferences
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好|想|要|爱)(.+?)(?=[。！？,.!?；：]|$)', 'positive'),
                (r'(想|要|愿意)(.+?)(?=[。！？,.!?；：]|$)', 'interest'),
            ]
            
            for pattern, sentiment in positive_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    phrase = match[1].strip()
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    if (2 <= len(phrase) <= 100
                        and not phrase.startswith(('不', '没', '无'))
                        and phrase.strip()):
                        full_content = f"用户表示{keyword}{phrase}"
                        preferences.append(Knowledge(
                            content=full_content,
                            type=KnowledgeType.PREFERENCE,
                            confidence=self.CONFIDENCE_PREFERENCE_POSITIVE,
                            metadata={'sentiment': sentiment, 'keyword': keyword, 'category': '偏好'}
                        ))
        
        return preferences
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """Extract factual statements from messages"""
        facts = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 3:
                continue
            
            # Fact patterns
            fact_patterns = [
                (r'(我|他|她|它)是(.+?)(?=[。！？,.!?；：]|$)', 'identity'),
                (r'(我|他|她)叫(.+?)(?=[。！？,.!?；：]|$)', 'name'),
                (r'(我|他|她)(.+?岁)(?=[。！？,.!?；：]|$)', 'age'),
            ]
            
            for pattern, category in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    subject = match[0]
                    detail = match[1].strip() if len(match) > 1 else match[0]
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    
                    if 2 <= len(detail) <= self.config.max_phrase_length:
                        facts.append(Knowledge(
                            content=f"{subject}{detail}",
                            type=KnowledgeType.FACT,
                            confidence=self.CONFIDENCE_FACT,
                            metadata={'category': category}
                        ))
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """Extract events from messages"""
        events = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 3:
                continue
            
            # Event patterns
            event_patterns = [
                (r'(昨天|今天|明天)(.+?)(?=[。！？,.!?；：]|$)', 'temporal'),
                (r'(刚才|之前|后来)(.+?)(?=[。！？,.!?；：]|$)', 'temporal'),
            ]
            
            for pattern, category in event_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    detail = match[1].strip() if len(match) > 1 else match[0]
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    
                    if 2 <= len(detail) <= self.config.max_phrase_length:
                        events.append(Knowledge(
                            content=f"{keyword}{detail}",
                            type=KnowledgeType.EVENT,
                            confidence=self.CONFIDENCE_EVENT,
                            metadata={'keyword': keyword, 'category': category}
                        ))
        
        return events


class LLMEntityExtractor(BaseExtractor):
    """
    LLM-powered entity extractor (placeholder for future implementation)
    
    Uses LLM to perform advanced NER (Named Entity Recognition) and
    extract structured information from conversations.
    
    Future enhancements:
    - Fine-tuned entity extraction models
    - Multi-entity relationship detection
    - Confidence scoring based on LLM output
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        Initialize LLM entity extractor
        
        Args:
            llm_client: LLM client for entity extraction
            config: Extraction configuration
        """
        self.llm_client = llm_client
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        logger.info("[LLMEntityExtractor] Initialized (placeholder implementation)")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        Extract entities using LLM
        
        Current implementation is a placeholder that falls back to rule-based extraction.
        
        Future TODO:
        - Implement LLM-based NER with prompt engineering
        - Add entity relationship extraction
        - Support custom entity types
        
        Args:
            messages: Conversation messages
            
        Returns:
            Extracted knowledge (currently uses fallback)
        """
        logger.debug("[LLMEntityExtractor] Using fallback to RuleBasedExtractor (not yet implemented)")
        
        # Fallback to rule-based for now
        fallback = RuleBasedExtractor(self.config)
        return await fallback.extract(messages)


class ImportancePredictorExtractor(BaseExtractor):
    """
    Importance-aware extractor (placeholder for future implementation)
    
    Uses a trained model to predict the long-term importance of extracted
    information. Filters out low-value memories before storage.
    
    Future enhancements:
    - Fine-tuned BERT model for importance prediction
    - Multi-factor scoring (recency, frequency, user engagement)
    - Adaptive thresholds based on memory capacity
    """
    
    def __init__(
        self,
        model: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        Initialize importance predictor extractor
        
        Args:
            model: Trained importance prediction model
            config: Extraction configuration
        """
        self.model = model
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        logger.info("[ImportancePredictorExtractor] Initialized (placeholder implementation)")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        Extract knowledge with importance prediction
        
        Current implementation is a placeholder that falls back to rule-based extraction.
        
        Future TODO:
        - Train/load importance prediction model
        - Score each extracted item for long-term value
        - Filter based on predicted importance threshold
        
        Args:
            messages: Conversation messages
            
        Returns:
            Extracted knowledge (currently uses fallback)
        """
        logger.debug("[ImportancePredictorExtractor] Using fallback to RuleBasedExtractor (not yet implemented)")
        
        # Fallback to rule-based for now
        fallback = RuleBasedExtractor(self.config)
        knowledge = await fallback.extract(messages)
        
        # TODO: Add importance prediction scoring here
        # for item in knowledge:
        #     item.confidence *= self._predict_importance(item)
        
        return knowledge
