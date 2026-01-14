"""
KnowledgeExtractor - 知识提取器

从对话中提取结构化知识，用于持久化到长期记忆。
"""

from typing import List, Optional
import re

from ..data_models import Message, Knowledge, KnowledgeType
from ..logger import get_logger

logger = get_logger(__name__)


class KnowledgeExtractor:
    """
    知识提取器
    
    从对话消息中提取结构化知识：
    - 用户偏好
    - 重要事实
    - 关键事件
    - 实体信息
    - 业务规则
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """
        初始化知识提取器
        
        Args:
            min_confidence: 最小置信度阈值，低于此值的知识将被过滤
        """
        self.min_confidence = min_confidence
    
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
        
        knowledge = []
        
        # 提取用户偏好
        knowledge.extend(self._extract_preferences(messages))
        
        # 提取重要事实
        knowledge.extend(self._extract_facts(messages))
        
        # 提取关键事件
        knowledge.extend(self._extract_events(messages))
        
        # 过滤低置信度的知识
        knowledge = [k for k in knowledge if k.confidence >= self.min_confidence]
        
        logger.debug(f"Extracted {len(knowledge)} knowledge items from {len(messages)} messages")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好"""
        preferences = []
        
        # 偏好关键词模式
        like_patterns = [
            r'(喜欢|想要|希望|需要|期待)(.{1,50})',
            r'(.{1,50})(很好|不错|满意|可以)',
        ]
        
        dislike_patterns = [
            r'(不喜欢|不想|不要|拒绝|反对)(.{1,50})',
            r'(.{1,50})(不好|不行|不满意|太贵)',
        ]
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content
            
            # 检查喜欢的内容
            for pattern in like_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    pref_content = ''.join(match).strip()
                    if len(pref_content) > 5:
                        preferences.append(Knowledge(
                            content=f"用户偏好: {pref_content}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.7,
                            metadata={'sentiment': 'positive'}
                        ))
            
            # 检查不喜欢的内容
            for pattern in dislike_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    pref_content = ''.join(match).strip()
                    if len(pref_content) > 5:
                        preferences.append(Knowledge(
                            content=f"用户不喜欢: {pref_content}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.7,
                            metadata={'sentiment': 'negative'}
                        ))
        
        return preferences
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """提取重要事实"""
        facts = []
        
        # 事实关键词
        fact_keywords = [
            '我是', '我的', '我叫', '我在', '我住',
            '已经', '确认', '收到', '知道了',
            '可以', '同意', '接受',
        ]
        
        for msg in messages:
            content = msg.content
            
            # 检查是否包含事实关键词
            for keyword in fact_keywords:
                if keyword in content:
                    # 提取包含关键词的句子
                    sentences = re.split(r'[。！？\n]', content)
                    for sentence in sentences:
                        if keyword in sentence and len(sentence.strip()) > 5:
                            facts.append(Knowledge(
                                content=sentence.strip(),
                                type=KnowledgeType.FACT,
                                confidence=0.6,
                                metadata={'author': msg.role.value}
                            ))
                    break
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """提取关键事件"""
        events = []
        
        # 事件关键词
        event_keywords = [
            '投诉', '申请', '办理', '开通', '取消',
            '报警', '拒绝', '同意', '确认',
            '支付', '还款', '逾期',
        ]
        
        for msg in messages:
            content = msg.content
            
            # 检查是否包含事件关键词
            for keyword in event_keywords:
                if keyword in content:
                    # 高优先级事件
                    events.append(Knowledge(
                        content=f"[关键事件] {content[:100]}",
                        type=KnowledgeType.EVENT,
                        confidence=0.8,
                        metadata={
                            'author': msg.role.value,
                            'timestamp': msg.timestamp.isoformat() if msg.timestamp else None,
                            'keyword': keyword
                        }
                    ))
                    break
        
        return events
