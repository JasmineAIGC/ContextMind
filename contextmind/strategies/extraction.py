"""
Extraction Strategies - 提取策略实现

提供多种知识提取策略，用于从对话中提取结构化知识。
"""

from typing import List, Optional
import re
import json

from ..data_models import Message, Knowledge, KnowledgeType
from .base import ExtractionStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class RuleBasedExtractionStrategy(ExtractionStrategy):
    """
    基于规则的提取策略
    
    使用预定义的规则和模式从对话中提取知识。
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """
        初始化基于规则的提取策略
        
        Args:
            min_confidence: 最小置信度阈值
        """
        self.min_confidence = min_confidence
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用规则提取知识
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的知识列表
        """
        knowledge = []
        
        # 提取偏好
        knowledge.extend(self._extract_preferences(messages))
        
        # 提取事实
        knowledge.extend(self._extract_facts(messages))
        
        # 提取事件
        knowledge.extend(self._extract_events(messages))
        
        # 过滤低置信度的知识
        knowledge = [k for k in knowledge if k.confidence >= self.min_confidence]
        
        logger.debug(f"RuleBasedExtraction: extracted {len(knowledge)} knowledge items")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好"""
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content
            
            # 喜欢的内容
            if any(word in content for word in ["喜欢", "想要", "希望", "需要"]):
                preferences.append(Knowledge(
                    content=f"用户偏好: {content}",
                    type=KnowledgeType.PREFERENCE,
                    confidence=0.7,
                    metadata={'sentiment': 'positive'}
                ))
            
            # 不喜欢的内容
            if any(word in content for word in ["不喜欢", "不想", "不要", "拒绝"]):
                preferences.append(Knowledge(
                    content=f"用户不喜欢: {content}",
                    type=KnowledgeType.PREFERENCE,
                    confidence=0.7,
                    metadata={'sentiment': 'negative'}
                ))
        
        return preferences
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """提取事实"""
        facts = []
        
        fact_patterns = [
            r'我是(.{1,20})',
            r'我叫(.{1,20})',
            r'我的(.{1,30})',
            r'我在(.{1,30})',
        ]
        
        for msg in messages:
            content = msg.content
            
            for pattern in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    facts.append(Knowledge(
                        content=f"事实: {match}",
                        type=KnowledgeType.FACT,
                        confidence=0.6
                    ))
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """提取关键事件"""
        events = []
        
        event_keywords = [
            "投诉", "申请", "办理", "开通", "取消",
            "报警", "拒绝", "同意", "确认",
        ]
        
        for msg in messages:
            content = msg.content
            
            for keyword in event_keywords:
                if keyword in content:
                    events.append(Knowledge(
                        content=f"关键事件: {content}",
                        type=KnowledgeType.EVENT,
                        confidence=0.8,
                        metadata={'keyword': keyword}
                    ))
                    break
        
        return events


class LLMExtractionStrategy(ExtractionStrategy):
    """
    基于LLM的提取策略
    
    使用大语言模型从对话中提取知识（预留接口）。
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        min_confidence: float = 0.5,
    ):
        """
        初始化基于LLM的提取策略
        
        Args:
            llm_client: LLM客户端实例
            min_confidence: 最小置信度阈值
        """
        self.llm_client = llm_client
        self.min_confidence = min_confidence
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用LLM提取知识
        
        Args:
            messages: 消息列表
            
        Returns:
            提取的知识列表
        """
        if not self.llm_client:
            logger.warning("LLMExtractionStrategy: llm_client not configured, falling back to rule-based")
            # 回退到基于规则的提取
            fallback = RuleBasedExtractionStrategy(self.min_confidence)
            return await fallback.extract(messages)
        
        if not messages:
            return []
        
        # 构建对话文本
        conversation = "\n".join(
            f"{msg.role.value}: {msg.content}"
            for msg in messages
        )
        
        # 构建提取prompt
        extraction_prompt = f"""请从以下对话中提取关键信息，以JSON格式输出。

对话:
{conversation}

请提取以下类型的知识:
1. 用户偏好 (preference)
2. 重要事实 (fact)
3. 关键事件 (event)
4. 实体信息 (entity)
5. 业务规则 (rule)

输出格式(JSON数组):
[
  {{"type": "preference", "content": "...", "confidence": 0.8}},
  {{"type": "fact", "content": "...", "confidence": 0.9}}
]

只输出JSON数组，不要其他内容:"""
        
        try:
            # 调用LLM
            _, response = self.llm_client.generate(extraction_prompt)
            
            # 解析JSON
            # 清理可能的markdown代码块
            response = response.strip()
            if response.startswith('```json'):
                response = response[7:]
            if response.startswith('```'):
                response = response[3:]
            if response.endswith('```'):
                response = response[:-3]
            response = response.strip()
            
            # 解析JSON
            extracted = json.loads(response)
            
            # 转换为Knowledge对象
            knowledge = []
            for item in extracted:
                try:
                    k_type = KnowledgeType(item['type'])
                    confidence = float(item.get('confidence', 0.5))
                    
                    if confidence >= self.min_confidence:
                        knowledge.append(Knowledge(
                            content=item['content'],
                            type=k_type,
                            confidence=confidence
                        ))
                except (ValueError, KeyError) as e:
                    logger.warning(f"Failed to parse knowledge item: {e}")
                    continue
            
            logger.debug(f"LLMExtraction: extracted {len(knowledge)} knowledge items")
            return knowledge
            
        except Exception as e:
            logger.warning(f"LLMExtraction failed: {e}, falling back to rule-based")
            # 回退到基于规则的提取
            fallback = RuleBasedExtractionStrategy(self.min_confidence)
            return await fallback.extract(messages)
