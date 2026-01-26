"""
Memory Extractors - 知识提取的 Plugin 实现

本模块提供多种策略, 用于从对话中提取有价值的信息并存储到长期记忆
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ..models import Message, Knowledge, KnowledgeType, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger, ScoreInfo
from ..utils.embedding import get_embedding_client

logger = get_logger(__name__)


class BaseExtractor(ABC):
    """
    Memory Extractor 基类接口
    
    Extractor 分析对话并识别值得存储到长期记忆的信息
    (事实、偏好、事件等)
    """
    
    @abstractmethod
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        从消息中提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识项列表
        """
        pass


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


class LLMBasedExtractor(BaseExtractor):
    """
    基于LLM的知识提取器（推荐使用）
    
    ✨ 使用LLM的语义理解能力从对话中提取结构化知识
    📊 支持全部40种知识类型的智能提取
    
    相比规则提取（RuleBasedExtractor），LLM提取器能够：
    1. ✅ 理解语义和上下文（不依赖关键词匹配）
    2. ✅ 识别隐含知识和意图
    3. ✅ 处理同义词和不同表达方式
    4. ✅ 自动分类到40种知识类型
    5. ✅ 提取复杂的关系和模式
    6. ✅ 更高的准确率和召回率
    
    支持的40种知识类型分10大类：
    - 用户画像（4种）：user_info, personality, values, lifestyle
    - 认知（4种）：opinion, belief, attitude, value_judgment
    - 行为（6种）：event, habit, experience, skill, achievement
    - 意图（6种）：intent, need, goal, plan, expectation
    - 关系（3种）：relationship, emotional_connection, influence
    - 知识（4种）：fact, procedural, domain_knowledge, common_sense
    - 情感（3种）：preference, emotion, sentiment
    - 策略（4种）：solution, strategy, best_practice, lesson_learned
    - 上下文（4种）：constraint, interest, topic, scenario
    - 多轮（4种）：conversation_pattern, topic_evolution, problem_solution_sequence, causality
    """
    
    # 静态类型映射表（优化查找性能）
    _TYPE_MAPPING = {
        kt.value.lower(): kt for kt in KnowledgeType
    }
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        初始化LLM知识提取器
        
        Args:
            llm_client: LLM客户端（需要有generate方法）
            config: 提取配置
        """
        self.llm_client = llm_client
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        
        if llm_client:
            logger.info("[LLMBasedExtractor] 初始化完成 - 使用LLM自动提取")
        else:
            logger.warning("[LLMBasedExtractor] 未提供LLM客户端 - 将回退到规则提取")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用LLM提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
        """
        # 如果没有LLM客户端，回退到规则提取
        if not self.llm_client:
            logger.debug("[LLMBasedExtractor] 回退到规则提取 (无LLM客户端)")
            fallback = RuleBasedExtractor(self.config)
            return await fallback.extract(messages)
        
        logger.info(f"[LLMBasedExtractor] 开始LLM知识提取 - 处理 {len(messages)} 条消息")
        
        # 构建对话文本
        conversation_text = self._build_conversation_text(messages)
        
        if not conversation_text:
            logger.warning("[LLMBasedExtractor] 对话文本为空，跳过提取")
            return []
        
        # 使用LLM提取知识
        try:
            extracted_data = await self._extract_with_llm(conversation_text)
            knowledge_list = self._parse_llm_response(extracted_data, messages)
            
            # 过滤低置信度知识
            before_filter = len(knowledge_list)
            knowledge_list = [k for k in knowledge_list if k.confidence >= self.config.min_confidence]
            filtered_count = before_filter - len(knowledge_list)
            
            if filtered_count > 0:
                logger.debug(f"[LLMBasedExtractor] 过滤低置信度知识: {filtered_count} 条")
            
            logger.info(f"[LLMBasedExtractor] ✓ 知识提取完成 - 总计 {len(knowledge_list)} 条有效知识")
            
            if knowledge_list:
                logger.debug(f"[LLMBasedExtractor] 提取的知识详情:")
                for i, k in enumerate(knowledge_list[:5], 1):
                    logger.debug(f"  {i}. [{k.knowledge_type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
                if len(knowledge_list) > 5:
                    logger.debug(f"  ... 以及其他 {len(knowledge_list) - 5} 条知识")
            
            return knowledge_list
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM提取失败: {e}, 回退到规则提取")
            fallback = RuleBasedExtractor(self.config)
            return await fallback.extract(messages)
    
    def _build_conversation_text(self, messages: List[Message]) -> str:
        """构建对话文本"""
        lines = []
        for msg in messages:
            role = "用户" if msg.role.value == "user" else "助手"
            lines.append(f"{role}: {msg.content}")
        return "\n".join(lines)
    
    async def _extract_with_llm(self, conversation_text: str) -> str:
        """
        使用LLM提取知识
        
        Args:
            conversation_text: 对话文本
            
        Returns:
            LLM返回的结构化知识（JSON格式字符串）
        """
        # 构建提取提示词 - 支持40种知识类型
        system_prompt = """你是一个专业的知识提取助手。你的任务是从对话中提取结构化的知识信息。

**关键要求**:
1. **总结提炼**：不要直接复制对话原文，而是总结归纳成简洁的知识点
2. **准确分类**：必须使用下面40种类型之一，不要使用UNKNOWN或其他类型
3. **合理置信度**：根据信息的明确程度合理评分（0.7-1.0之间，严格筛选）
4. **精选重要信息**：只提取真正有价值的核心知识
5. **完整整合**：将分散在多轮对话中的相关信息整合成完整的知识点
6. **避免重复**：不要提取已经在之前对话中提到过的相同或相似信息

**支持的40种知识类型**:

**1. 用户画像类(4种)**:
- user_info: 用户基本信息（年龄、职业、姓名、居住地）
- personality: 性格特征（外向/内向、乐观/悲观）
- values: 价值观和人生观
- lifestyle: 生活方式和日常习惯

**2. 认知类(4种)**:
- opinion: 观点和看法
- belief: 信念和信仰
- attitude: 态度和立场
- value_judgment: 价值判断

**3. 行为类(6种)**:
- event: 发生的事件和活动
- habit: 习惯和常规行为
- experience: 过往经历
- skill: 技能和能力
- achievement: 成就和里程碑

**4. 意图类(6种)**:
- intent: 意图和打算
- need: 需求和要求
- goal: 目标和追求
- plan: 具体计划和安排（含时间/地点）
- expectation: 期望和预期

**5. 关系类(3种)**:
- relationship: 社交关系
- emotional_connection: 情感连接
- influence: 影响因素

**6. 知识类(4种)**:
- fact: 客观事实
- procedural: 程序性知识（如何做某事）
- domain_knowledge: 领域专业知识
- common_sense: 常识

**7. 情感类(3种)**:
- preference: 偏好和喜好
- emotion: 情绪状态
- sentiment: 情感倾向

**8. 策略类(4种)**:
- solution: 解决方案
- strategy: 策略方法
- best_practice: 最佳实践
- lesson_learned: 经验教训

**9. 上下文类(4种)**:
- constraint: 约束条件
- interest: 兴趣爱好（长期的）
- topic: 讨论话题
- scenario: 场景和情境

**10. 多轮对话分析(4种)**:
- conversation_pattern: 对话模式
- topic_evolution: 话题演变
- problem_solution_sequence: 问题解决序列
- causality: 因果关系

**输出格式**:
```json
{
  "knowledge": [
    {
      "content": "用户是软件工程师，25岁",
      "type": "user_info",
      "confidence": 0.95
    }
  ]
}
```

**置信度评分标准（严格筛选）**:
- 0.90-1.00: 用户明确陈述的核心事实信息
- 0.75-0.89: 从对话中可以合理推断的重要信息
- 0.70-0.74: 需要一定推理但仍重要的信息
- <0.70: 不要提取，质量不够高

**提取原则**:
- 只提取真正有价值的核心知识点
- 优先提取用户的核心信息（user_info, plan, preference, goal等）
- 不要提取次要的、模糊的、重复的信息

**提取示例**:

❌ **错误示例**（直接复制对话、类型错误）:
对话:
用户: 想去丽江
助手: 什么时候去呢？
用户: 过两个月

错误提取:
- {"content": "想去丽江", "type": "UNKNOWN", "confidence": 0.5}  ← 类型错误、置信度过低
- {"content": "过两个月", "type": "event", "confidence": 0.3}  ← 分类错误、信息不完整

✅ **正确示例**（总结归纳、准确分类）:
- {"content": "用户想去丽江旅行", "type": "intent", "confidence": 0.85}
- {"content": "用户计划两个月后去丽江", "type": "plan", "confidence": 0.85}

**不要提取的内容**:
- 助手的回复（只提取用户信息）
- 简单的确认回复（"好的"、"嗯"、"没有"）
- 问候语（"你好"、"再见"）
- 无实际信息内容的对话

请严格按照要求提取知识，返回有效的JSON格式。"""
        
        user_prompt = f"""请从以下对话中提取结构化知识：

{conversation_text}

请返回JSON格式的提取结果。"""
        
        # 合并system_prompt和user_prompt为完整的prompt
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        # 调用LLM（SimpleLLMClient只接受单个prompt参数）
        try:
            if hasattr(self.llm_client, 'generate_async'):
                # 异步调用
                _, response = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                # 同步调用（返回 reasoning, content 元组）
                _, response = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")
            
            return response
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM调用失败: {e}")
            raise
    
    def _parse_llm_response(self, llm_response: str, messages: List[Message]) -> List[Knowledge]:
        """
        解析LLM返回的JSON格式知识
        
        Args:
            llm_response: LLM返回的文本
            messages: 原始消息列表（用于获取消息ID）
            
        Returns:
            Knowledge对象列表
        """
        import json
        import re
        
        knowledge_list = []
        
        try:
            # 尝试提取JSON部分（LLM可能返回带有markdown代码块的文本）
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                # 尝试直接解析整个响应
                json_str = llm_response.strip()
            
            # 解析JSON
            data = json.loads(json_str)
            
            # 提取knowledge列表
            if 'knowledge' in data:
                for item in data['knowledge']:
                    try:
                        # 获取内容和类型
                        content = item.get('content', '').strip()
                        type_str = item.get('type', '').lower()
                        confidence = float(item.get('confidence', 0.8))
                        
                        # **验证1**: 跳过无效类型（UNKNOWN等）
                        if not type_str or type_str in ['unknown', 'none', '']:
                            logger.debug(f"[LLMBasedExtractor] 跳过无效类型的知识: type={type_str}, content={content[:50]}")
                            continue
                        
                        # **验证2**: 内容不能为空或过短（至少5个字符）
                        if not content or len(content) < 5:
                            logger.debug(f"[LLMBasedExtractor] 跳过内容过短的知识: {content}")
                            continue
                        
                        # **验证3**: 跳过无意义的简短回复和过于简单的描述
                        meaningless_phrases = {'好的', '嗯', '哦', '没有', '是的', '不是', '可以', '不可以', '你好', '再见', '谢谢', '不客气'}
                        if content in meaningless_phrases or content.strip() in meaningless_phrases:
                            logger.debug(f"[LLMBasedExtractor] 跳过无意义短语: {content}")
                            continue
                        
                        # **验证3.5**: 跳过过于简短且信息量低的内容（少于8个汉字且不含实体信息）
                        if len(content) < 8 and not any(char.isdigit() or char in '年月日时' for char in content):
                            logger.debug(f"[LLMBasedExtractor] 跳过信息量过低的短内容: {content}")
                            continue
                        
                        # **验证4**: 置信度必须合理（0.72-1.0）- 再次提高阈值
                        if confidence < 0.72:
                            logger.debug(f"[LLMBasedExtractor] 跳过低置信度知识: confidence={confidence}, content={content[:50]}")
                            continue
                        if confidence > 1.0:
                            logger.warning(f"[LLMBasedExtractor] 置信度>1.0，调整为1.0: {confidence}")
                            confidence = 1.0
                        
                        # 使用静态映射表进行O(1)查找
                        knowledge_type = self._TYPE_MAPPING.get(type_str)
                        
                        # 如果没找到匹配，跳过（不再使用默认值）
                        if knowledge_type is None:
                            logger.warning(f"[LLMBasedExtractor] 未知知识类型 '{type_str}'，跳过该知识: {content[:50]}")
                            continue
                        
                        # 创建Knowledge对象
                        knowledge = Knowledge(
                            content=content,
                            knowledge_type=knowledge_type,
                            scores=ScoreInfo(confidence=confidence),
                            extraction_method='llm',
                            source_message_ids=[getattr(msg, 'id', '') for msg in messages],
                            metadata={
                                'category': item.get('category', ''),
                                'entities': item.get('entities', []),
                                'keywords': item.get('keywords', []),
                                'llm_extracted': True
                            }
                        )
                        
                        # 生成 embedding（异步）
                        embedding_client = get_embedding_client()
                        if embedding_client:
                            embedding_info = embedding_client.generate_embedding(content)
                            if embedding_info:
                                knowledge.embeddings['default'] = embedding_info
                                logger.debug(f"[LLMBasedExtractor] 已生成 embedding - dim: {embedding_info.dimension}")
                        
                        knowledge_list.append(knowledge)
                        
                    except Exception as e:
                        logger.warning(f"[LLMBasedExtractor] 解析知识项失败: {e}, 项: {item}")
                        continue
            
            logger.debug(f"[LLMBasedExtractor] 成功解析 {len(knowledge_list)} 条知识")
            
        except json.JSONDecodeError as e:
            logger.error(f"[LLMBasedExtractor] JSON解析失败: {e}")
            logger.debug(f"[LLMBasedExtractor] LLM响应: {llm_response[:200]}...")
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] 解析LLM响应失败: {e}")
        
        return knowledge_list


class ImportancePredictorExtractor(BaseExtractor):
    """
    重要性感知提取器（未来实现的占位符）
    
    使用训练好的模型预测提取信息的长期重要性
    在存储前过滤低价值记忆
    
    未来增强功能：
    - 用于重要性预测的微调 BERT 模型
    - 多因素评分（新近性、频率、用户参与度）
    - 基于记忆容量的自适应阈值
    """
    
    def __init__(
        self,
        model: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        初始化重要性预测提取器
        
        Args:
            model: 训练好的重要性预测模型
            config: 提取配置
        """
        self.model = model
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        logger.info("[ImportancePredictorExtractor] 已初始化（占位符实现）")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用重要性预测提取知识
        
        当前实现是占位符，会回退到基于规则的提取
        
        未来待做事项：
        - 训练/加载重要性预测模型
        - 为每个提取项评分长期价值
        - 基于预测的重要性阈值进行过滤
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识（当前使用回退方案）
        """
        logger.debug("[ImportancePredictorExtractor] 使用回退到 RuleBasedExtractor（尚未实现）")
        
        # 目前回退到基于规则的提取
        fallback = RuleBasedExtractor(self.config)
        knowledge = await fallback.extract(messages)
        
        # 未来：在此处添加重要性预测评分
        # 这将涉及：
        # 1. 加载/初始化重要性预测模型
        # 2. 根据预测的长期价值为每个知识项评分
        # 3. 过滤低于重要性阈值的项
        # 示例实现（当模型可用时）：
        #   for item in knowledge:
        #       importance_score = self._predict_importance(item)
        #       item.confidence *= importance_score
        
        return knowledge
    
    def _predict_importance(self, knowledge: Knowledge) -> float:
        """
        预测知识项的重要性分数（占位符）
        
        此方法将使用训练好的模型来预测此知识对未来对话的重要性
        
        Args:
            knowledge: 要评分的知识项
            
        Returns:
            重要性分数（0-1）
        """
        # TODO: 当模型可用时实现
        # 实现步骤：
        # 1. 提取知识的特征（类型、内容长度、置信度等）
        # 2. 使用训练好的模型预测长期价值
        # 3. 返回 0-1 之间的重要性分数
        # 当前返回默认值（占位符实现）
        logger.warning("[ImportancePredictorExtractor] 使用占位符实现，返回默认重要性分数 1.0")
        return 1.0
