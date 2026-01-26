"""
基于规则的知识提取器
"""

from typing import List, Optional
import re

from .base import BaseExtractor
from ...core.models import Message, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger
from ...core.types import Knowledge, KnowledgeType, ScoreInfo

logger = get_logger(__name__)


class RuleBasedExtractor(BaseExtractor):
    """
    基于规则的知识提取器 (已弃用 - 仅作为轻量级fallback)
    
    ⚠️ DEPRECATED: 建议使用 LLMBasedExtractor 获得更好的提取效果
    
    使用模式匹配和启发式方法从对话中提取事实、偏好和事件
    轻量级且确定性的提取方式，但只支持9种基础知识类型
    主要作为LLM提取失败时的后备方案使用
    """
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        """
        初始化基于规则的提取器
        
        Args:
            config: 提取配置, 未指定时使用默认配置
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
    
    # 属性用于与现有代码向后兼容
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
        使用基于规则的模式提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
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
                logger.debug(f"  {i}. [{k.knowledge_type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
            if len(knowledge) > 5:
                logger.debug(f"  ... 以及其他 {len(knowledge) - 5} 条知识")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """
        提取用户偏好 - 通用语言学模式
        
        设计原则:
        - 基于语言学模式，而非特定领域知识
        - 不硬编码品牌、产品等具体名词
        - 适用于任何对话场景（客服、聊天、咨询等）
        - 捕获用户的意图、需求、偏好表达
        """
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 2:
                continue
            
            # 通用偏好模式 - 基于常见的中文表达习惯
            # 这些模式适用于任何领域
            
            # 1. 意图和需求表达（通用）
            intent_patterns = [
                (r'想(买|要|购买|入手|做|学|了解|知道)(.+?)(?=[。！？,.!?；：]|$)', 'intent'),
                (r'需要(.+?)(?=[。！？,.!?；：]|$)', 'need'),
                (r'希望(.+?)(?=[。！？,.!?；：]|$)', 'hope'),
                (r'打算(.+?)(?=[。！？,.!?；：]|$)', 'plan'),
                (r'给我(推荐|介绍|找|看看)(.+?)(?=[。！？,.!?；：]|$)', 'request'),
            ]
            
            # 2. 正向偏好表达（通用）
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好|想|要|爱|倾向于)(.+?)(?=[。！？,.!?；：]|$)', 'preference'),
                (r'比较(喜欢|想要|倾向|偏向)(.+?)(?=[。！？,.!?；：]|$)', 'comparative_preference'),
                (r'更(喜欢|想要|倾向|偏向)(.+?)(?=[。！？,.!?；：]|$)', 'comparative_preference'),
            ]
            
            # 3. 负向偏好表达（通用）
            negative_patterns = [
                (r'不(喜欢|想要|需要|要)(.+?)(?=[。！？,.!?；：]|$)', 'dislike'),
                (r'讨厌(.+?)(?=[。！？,.!?；：]|$)', 'dislike'),
            ]
            
            # 4. 数值约束表达（通用 - 价格、数量、时间等）
            numeric_patterns = [
                (r'(\d+)([元块钱]?)以下', 'upper_limit'),
                (r'低于(\d+)', 'upper_limit'),
                (r'不超过(\d+)', 'upper_limit'),
                (r'(\d+)左右', 'approximate'),
                (r'(\d+)以上', 'lower_limit'),
                (r'大于(\d+)', 'lower_limit'),
            ]
            
            # 处理意图和需求
            for pattern, category in intent_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        action = match[0]
                        target = match[1].strip()
                    else:
                        action = ''
                        target = match[0].strip() if isinstance(match, str) else ''
                    
                    target = re.sub(r'[，。！？,.!?；:：]+$', '', target)
                    
                    if (2 <= len(target) <= self.config.max_phrase_length
                        and target.strip()):
                        full_content = f"用户{category}: {action}{target}" if action else f"用户{category}: {target}"
                        # 根据category映射到正确的知识类型
                        if category in ('intent', 'plan', 'hope'):
                            k_type = KnowledgeType.INTENT
                        elif category == 'need':
                            k_type = KnowledgeType.NEED
                        else:
                            k_type = KnowledgeType.PREFERENCE
                        
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=k_type,
                            scores=ScoreInfo(confidence=0.75),  # 意图表达置信度
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'action': action,
                                'target': target,
                                'context': content[:100]
                            }
                        ))
            
            # 处理正向偏好
            for pattern, category in positive_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        keyword = match[0]
                        phrase = match[1].strip() if len(match) > 1 else match[0].strip()
                    else:
                        keyword = ''
                        phrase = match.strip()
                    
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    # 过滤否定表达
                    if (2 <= len(phrase) <= self.config.max_phrase_length
                        and not phrase.startswith(('不', '没', '无'))
                        and phrase.strip()):
                        full_content = f"用户偏好: {keyword}{phrase}" if keyword else f"用户偏好: {phrase}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.PREFERENCE,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_PREFERENCE_POSITIVE),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'keyword': keyword,
                                'phrase': phrase,
                                'context': content[:100]
                            }
                        ))
            
            # 处理负向偏好
            for pattern, category in negative_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        keyword = match[0] if len(match) > 1 else ''
                        phrase = match[1].strip() if len(match) > 1 else match[0].strip()
                    else:
                        keyword = ''
                        phrase = match.strip()
                    
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    if (2 <= len(phrase) <= self.config.max_phrase_length
                        and phrase.strip()):
                        full_content = f"用户不{keyword}{phrase}" if keyword else f"用户不喜欢: {phrase}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.PREFERENCE,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_PREFERENCE_NEGATIVE),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'sentiment': 'negative',
                                'keyword': keyword,
                                'phrase': phrase,
                                'context': content[:100]
                            }
                        ))
            
            # 处理数值约束
            for pattern, category in numeric_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        value = match[0]
                        unit = match[1] if len(match) > 1 else ''
                    else:
                        value = match
                        unit = ''
                    
                    full_value = f"{value}{unit}"
                    full_content = f"用户约束: {full_value}"
                    preferences.append(Knowledge(
                        content=full_content,
                        knowledge_type=KnowledgeType.CONSTRAINT,  # 使用CONSTRAINT类型
                        scores=ScoreInfo(confidence=0.85),  # 明确的数值约束置信度高
                        extraction_method='rule',
                        source_message_ids=[getattr(msg, 'id', '')],
                        metadata={
                            'category': category,
                            'value': value,
                            'unit': unit,
                            'constraint_type': category,
                            'context': content[:100]
                        }
                    ))
            
            # 5. 观点和看法表达（新增）
            opinion_patterns = [
                (r'我(觉得|认为|感觉|think|believe)(.+?)(?=[。！？,.!?；：]|$)', 'opinion'),
                (r'在我看来(.+?)(?=[。！？,.!?；：]|$)', 'viewpoint'),
                (r'我的(看法|观点|意见)是(.+?)(?=[。！？,.!?；：]|$)', 'view'),
            ]
            
            for pattern, category in opinion_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        opinion_text = match[1].strip()
                    else:
                        opinion_text = match[0].strip() if isinstance(match, str) else ''
                    
                    opinion_text = re.sub(r'[，。！？,.!?；:：]+$', '', opinion_text)
                    
                    if 2 <= len(opinion_text) <= self.config.max_phrase_length and opinion_text.strip():
                        full_content = f"用户观点: {opinion_text}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.OPINION,
                            scores=ScoreInfo(confidence=0.70),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'opinion': opinion_text,
                                'context': content[:100]
                            }
                        ))
            
            # 6. 习惯表达（新增）
            habit_patterns = [
                (r'我(经常|常常|总是|一般|通常|平时|习惯)(.+?)(?=[。！？,.!?；：]|$)', 'habit'),
                (r'我(每天|每周|每月|每年)(.+?)(?=[。！？,.!?；：]|$)', 'routine'),
            ]
            
            for pattern, category in habit_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        frequency = match[0]
                        action = match[1].strip()
                    else:
                        frequency = ''
                        action = match[0].strip() if isinstance(match, str) else ''
                    
                    action = re.sub(r'[，。！？,.!?；:：]+$', '', action)
                    
                    if 2 <= len(action) <= self.config.max_phrase_length and action.strip():
                        full_content = f"用户习惯: {frequency}{action}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.HABIT,
                            scores=ScoreInfo(confidence=0.80),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'frequency': frequency,
                                'action': action,
                                'context': content[:100]
                            }
                        ))
            
            # 7. 兴趣表达（新增）
            interest_patterns = [
                (r'我(对|关于)(.+?)(感兴趣|有兴趣|很感兴趣|挺感兴趣)', 'interest'),
                (r'我(喜欢|爱好)(.+?)(?=[。！？,.!?；：]|$)', 'hobby'),
                (r'我(关注|在意)(.+?)(?=[。！？,.!?；：]|$)', 'concern'),
            ]
            
            for pattern, category in interest_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        topic = match[1].strip() if len(match) > 1 else match[0].strip()
                    else:
                        topic = match[0].strip() if isinstance(match, str) else ''
                    
                    topic = re.sub(r'[，。！？,.!?；:：]+$', '', topic)
                    
                    if 2 <= len(topic) <= self.config.max_phrase_length and topic.strip():
                        full_content = f"用户兴趣: {topic}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.INTEREST,
                            scores=ScoreInfo(confidence=0.75),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'topic': topic,
                                'context': content[:100]
                            }
                        ))
        
        return preferences
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """
        提取事实陈述 - 通用语言学模式
        
        设计原则:
        - 基于"主语-谓语-宾语"等语法结构
        - 不针对特定领域（如电商、客服等）
        - 捕获客观陈述和确定性信息
        - 适用于任何对话场景
        """
        facts = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 3:
                continue
            
            # 通用事实陈述模式
            
            # 1. 身份和状态陈述（通用）
            identity_patterns = [
                (r'(我|他|她|它|这|那)是(.+?)(?=[。！？,.!?；：]|$)', 'identity'),
                (r'(我|他|她|这个|那个)叫(.+?)(?=[。！？,.!?；：]|$)', 'name'),
                (r'(我|他|她)(.+?岁)(?=[。！？,.!?；：]|$)', 'age'),
                (r'(我|他|她|这|那)在(.+?)(?=[。！？,.!?；：]|$)', 'location'),
                (r'(我|他|她|这|那)有(.+?)(?=[。！？,.!?；：]|$)', 'possession'),
            ]
            
            # 2. 属性和特征描述（通用）
            attribute_patterns = [
                (r'(这|那|它)(.+?)[很挺特别非常](.+?)(?=[。！？,.!?；：]|$)', 'attribute'),
                (r'(.+?)的(.+?)是(.+?)(?=[。！？,.!?；：]|$)', 'property'),
            ]
            
            # 3. 时间和数量事实（通用）
            temporal_quantitative_patterns = [
                (r'(\d+年|\d+月|\d+日|\d+号)', 'temporal'),
                (r'(\d+[个只台件份])', 'quantity'),
                (r'(\d+)([元块钱斤米厘米公里小时分钟秒])', 'measurement'),
            ]
            
            # 处理身份和状态
            for pattern, category in identity_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        subject = match[0]
                        detail = match[1].strip() if len(match) > 1 else match[0]
                    else:
                        subject = ''
                        detail = match.strip()
                    
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    
                    if 2 <= len(detail) <= self.config.max_phrase_length:
                        facts.append(Knowledge(
                            content=f"{subject}{detail}",
                            knowledge_type=KnowledgeType.FACT,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_FACT),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'subject': subject,
                                'detail': detail,
                                'context': content[:100]
                            }
                        ))
            
            # 处理属性和特征
            for pattern, category in attribute_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        fact_text = ''.join(match).strip()
                    else:
                        fact_text = match.strip() if isinstance(match, str) else ''
                    
                    fact_text = re.sub(r'[，。！？,.!?；:：]+$', '', fact_text)
                    
                    if 3 <= len(fact_text) <= self.config.max_phrase_length:
                        facts.append(Knowledge(
                            content=f"{fact_text}",
                            knowledge_type=KnowledgeType.FACT,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_FACT * 0.9),  # 属性描述置信度略低
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'fact_text': fact_text,
                                'context': content[:100]
                            }
                        ))
            
            # 处理时间和数量事实
            for pattern, category in temporal_quantitative_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        value = match[0]
                        unit = match[1] if len(match) > 1 else ''
                        fact_text = f"{value}{unit}"
                    else:
                        fact_text = match.strip()
                    
                    if fact_text and len(fact_text) <= 20:  # 时间和数量通常较短
                        facts.append(Knowledge(
                            content=f"{fact_text}",
                            knowledge_type=KnowledgeType.FACT,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_FACT * 0.95),  # 客观数据置信度高
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'value': fact_text,
                                'context': content[:100]
                            }
                        ))
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """从消息中提取事件"""
        events = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 3:
                continue
            
            # 事件模式
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
                            knowledge_type=KnowledgeType.EVENT,
                            scores=ScoreInfo(confidence=self.CONFIDENCE_EVENT),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'keyword': keyword,
                                'category': category,
                                'context': content[:100]
                            }
                        ))
        
        return events
