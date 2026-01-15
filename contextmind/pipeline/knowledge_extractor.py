"""
KnowledgeExtractor - 知识提取器

从对话中提取结构化知识，用于持久化到长期记忆。

上下文工程核心能力：
- 从对话历史中自动提炼有价值的知识
- 识别用户偏好、重要事实、关键事件
- 生成可用于指导后续对话的记忆条目
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
    - 用户偏好（喜欢/不喜欢什么）
    - 重要事实（用户信息、已确认的事项）
    - 关键事件（投诉、申请等重要操作）
    - 对话主题和实体
    - 交互策略（什么样的回复效果好）
    
    这些提取的知识将作为长期记忆存储，在后续对话中
    通过语义相似度检索，为LLM提供更精准的上下文信息。
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
        
        # 提取对话主题
        knowledge.extend(self._extract_topics(messages))
        
        # 提取交互策略（从对话模式中学习）
        knowledge.extend(self._extract_strategies(messages))
        
        # 过滤低置信度的知识
        knowledge = [k for k in knowledge if k.confidence >= self.min_confidence]
        
        # 去重
        knowledge = self._deduplicate(knowledge)
        
        logger.debug(f"Extracted {len(knowledge)} knowledge items from {len(messages)} messages")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好"""
        preferences = []
        
        # 偏好关键词模式
        like_patterns = [
            r'(喜欢|想要|希望|需要|期待)(.{2,30})',
            r'(.{2,30})(很好|不错|满意|可以)',
        ]
        
        dislike_patterns = [
            r'(不喜欢|不想|不要|拒绝|反对)(.{2,30})',
            r'(.{2,30})(不好|不行|不满意|太贵)',
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
                    if len(pref_content) > 3:
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
                    if len(pref_content) > 3:
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
                        if keyword in sentence and 3 < len(sentence.strip()) < 100:
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
                        content=f"[事件] {content[:80]}",
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
    
    def _extract_topics(self, messages: List[Message]) -> List[Knowledge]:
        """提取对话主题和关键实体"""
        topics = []
        
        # 从对话中识别主要话题
        all_content = " ".join([msg.content for msg in messages])
        
        # 简单的主题词提取（可以替换为更复杂的NLP方法）
        topic_patterns = [
            (r'关于(.{2,15})', '话题'),
            (r'问题是(.{2,20})', '问题'),
            (r'想了解(.{2,15})', '兴趣'),
            (r'需要(.{2,15})', '需求'),
        ]
        
        for pattern, topic_type in topic_patterns:
            matches = re.findall(pattern, all_content)
            for match in matches:
                if len(match.strip()) > 2:
                    topics.append(Knowledge(
                        content=f"对话{topic_type}: {match.strip()}",
                        type=KnowledgeType.FACT,
                        confidence=0.6,
                        metadata={'topic_type': topic_type}
                    ))
        
        return topics
    
    def _extract_strategies(self, messages: List[Message]) -> List[Knowledge]:
        """从对话模式中提取交互策略"""
        strategies = []
        
        # 分析用户对回复的反馈
        for i, msg in enumerate(messages):
            if msg.role.value != "user":
                continue
            
            content = msg.content.lower()
            
            # 检测正面反馈
            if any(w in content for w in ['好的', '谢谢', '不错', '满意', '很好']):
                if i > 0:  # 有之前的回复
                    strategies.append(Knowledge(
                        content=f"有效策略: 用户对回复表示满意",
                        type=KnowledgeType.RULE,
                        confidence=0.65,
                        metadata={'feedback': 'positive'}
                    ))
            
            # 检测负面反馈
            if any(w in content for w in ['不对', '不是', '错了', '不满意', '不好']):
                if i > 0:
                    strategies.append(Knowledge(
                        content=f"需改进: 用户对之前的回复不满意",
                        type=KnowledgeType.RULE,
                        confidence=0.7,
                        metadata={'feedback': 'negative'}
                    ))
        
        return strategies
    
    def _deduplicate(self, knowledge: List[Knowledge]) -> List[Knowledge]:
        """去除重复的知识条目"""
        seen = set()
        unique = []
        for k in knowledge:
            # 简化内容用于比较
            simplified = k.content.strip().lower()
            if simplified not in seen:
                seen.add(simplified)
                unique.append(k)
        return unique
