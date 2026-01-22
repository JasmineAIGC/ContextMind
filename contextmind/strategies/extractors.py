"""
Memory Extractors - 知识提取的 Plugin 实现

本模块提供多种策略, 用于从对话中提取有价值的信息并存储到长期记忆
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ..models import Message, Knowledge, KnowledgeType, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger, ScoreInfo

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
    基于规则的知识提取器 (现有实现)
    
    使用模式匹配和启发式方法从对话中提取事实、偏好和事件
    轻量级且确定性的提取方式
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
    基于LLM的知识提取器
    
    使用LLM的语义理解能力从对话中提取结构化知识
    相比规则提取，能够：
    1. 识别更复杂的语义模式
    2. 提取实体和关系
    3. 自动分类和总结知识
    4. 处理上下文相关的信息
    """
    
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
        # 构建提取提示词
        system_prompt = """你是一个专业的知识提取助手。你的任务是从对话中提取结构化的知识信息。

请从对话中提取以下类型的知识：
1. **偏好 (preference)**: 用户的喜好、需求、意愿
2. **事实 (fact)**: 关于用户或主题的客观事实（姓名、年龄、身份等）
3. **事件 (event)**: 发生的事件、行为或活动

对每个提取的知识，提供：
- content: 知识内容的完整描述
- type: 知识类型 (preference/fact/event)
- confidence: 置信度 (0-1之间的数值)
- category: 具体分类（如"食物偏好"、"个人信息"等）
- entities: 涉及的实体列表（人名、地名等）
- keywords: 关键词列表

请以JSON格式返回提取结果，格式如下：
```json
{
  "knowledge": [
    {
      "content": "用户喜欢吃辣的食物",
      "type": "preference",
      "confidence": 0.9,
      "category": "食物偏好",
      "entities": [],
      "keywords": ["喜欢", "辣", "食物"]
    }
  ]
}
```

注意：
- 只提取明确、有价值的信息
- 不要编造或推断不存在的信息
- 置信度要基于信息的明确程度
- 如果没有值得提取的知识，返回空列表
"""
        
        user_prompt = f"""请从以下对话中提取结构化知识：

{conversation_text}

请返回JSON格式的提取结果。"""
        
        # 调用LLM
        try:
            if hasattr(self.llm_client, 'generate'):
                # 异步调用
                response = await self.llm_client.generate(
                    user_prompt,
                    system_prompt=system_prompt,
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens
                )
            elif hasattr(self.llm_client, 'generate_sync'):
                # 同步调用
                response = self.llm_client.generate_sync(
                    user_prompt,
                    system_prompt=system_prompt,
                    temperature=self.config.llm_temperature,
                    max_tokens=self.config.llm_max_tokens
                )
            else:
                raise ValueError("LLM客户端缺少generate或generate_sync方法")
            
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
                        # 映射类型字符串到KnowledgeType枚举
                        type_str = item.get('type', 'fact').lower()
                        if type_str == 'preference':
                            knowledge_type = KnowledgeType.PREFERENCE
                        elif type_str == 'event':
                            knowledge_type = KnowledgeType.EVENT
                        else:
                            knowledge_type = KnowledgeType.FACT
                        
                        # 创建Knowledge对象
                        knowledge = Knowledge(
                            content=item.get('content', ''),
                            knowledge_type=knowledge_type,
                            scores=ScoreInfo(confidence=float(item.get('confidence', 0.8))),
                            extraction_method='llm',
                            source_message_ids=[getattr(msg, 'id', '') for msg in messages],
                            metadata={
                                'category': item.get('category', ''),
                                'entities': item.get('entities', []),
                                'keywords': item.get('keywords', []),
                                'llm_extracted': True
                            }
                        )
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
        
        # Future: Add importance prediction scoring here
        # This would involve:
        # 1. Loading/initializing the importance prediction model
        # 2. Scoring each knowledge item based on predicted long-term value
        # 3. Filtering items below importance threshold
        # Example implementation (when model is available):
        #   for item in knowledge:
        #       importance_score = self._predict_importance(item)
        #       item.confidence *= importance_score
        
        return knowledge
    
    def _predict_importance(self, knowledge: Knowledge) -> float:
        """
        Predict importance score for a knowledge item (placeholder)
        
        This method would use a trained model to predict how important
        this knowledge will be for future conversations.
        
        Args:
            knowledge: Knowledge item to score
            
        Returns:
            Importance score (0-1)
        """
        # TODO: Implement when model is available
        # Current implementation returns neutral score
        return 1.0


class EnhancedExtractor(BaseExtractor):
    """
    增强知识提取器 - 支持30种知识类型
    
    在RuleBasedExtractor基础上扩展，提取更全面的知识类型：
    - 单轮对话提取：21种基础知识类型
    - 多轮对话提取：4种对话级知识类型
    - 跨对话提取：5种模式识别类型
    
    提取策略：
    1. 基于规则的模式匹配（快速、确定性）
    2. 多轮上下文分析（识别对话模式）
    3. 语义关联提取（知识间的关系）
    """
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        """
        初始化增强提取器
        
        Args:
            config: 提取配置, 未指定时使用默认配置
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        # 复用基础提取器的逻辑
        self.base_extractor = RuleBasedExtractor(config)
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用增强规则提取30种知识类型
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
        """
        logger.info(f"[EnhancedExtractor] 开始增强知识提取 - 处理 {len(messages)} 条消息，支持30种知识类型")
        
        knowledge = []
        
        # 1. 使用基础提取器提取原有9种类型
        base_knowledge = await self.base_extractor.extract(messages)
        knowledge.extend(base_knowledge)
        logger.debug(f"[EnhancedExtractor] 基础提取: {len(base_knowledge)} 条")
        
        # 2. 提取新增的21种知识类型
        
        # 用户画像类 (4种)
        user_profile = self._extract_user_profile(messages)
        knowledge.extend(user_profile)
        logger.debug(f"[EnhancedExtractor] 用户画像: {len(user_profile)} 条")
        
        # 认知类 (3种新增)
        cognitive = self._extract_cognitive(messages)
        knowledge.extend(cognitive)
        logger.debug(f"[EnhancedExtractor] 认知类: {len(cognitive)} 条")
        
        # 行为类 (3种新增)
        behavioral = self._extract_behavioral(messages)
        knowledge.extend(behavioral)
        logger.debug(f"[EnhancedExtractor] 行为类: {len(behavioral)} 条")
        
        # 意图类 (3种新增)
        intentional = self._extract_intentional(messages)
        knowledge.extend(intentional)
        logger.debug(f"[EnhancedExtractor] 意图类: {len(intentional)} 条")
        
        # 关系类 (3种)
        relational = self._extract_relational(messages)
        knowledge.extend(relational)
        logger.debug(f"[EnhancedExtractor] 关系类: {len(relational)} 条")
        
        # 知识类 (3种新增)
        epistemic = self._extract_epistemic(messages)
        knowledge.extend(epistemic)
        logger.debug(f"[EnhancedExtractor] 知识类: {len(epistemic)} 条")
        
        # 情感类 (2种新增)
        emotional = self._extract_emotional(messages)
        knowledge.extend(emotional)
        logger.debug(f"[EnhancedExtractor] 情感类: {len(emotional)} 条")
        
        # 策略类 (4种)
        strategic = self._extract_strategic(messages)
        knowledge.extend(strategic)
        logger.debug(f"[EnhancedExtractor] 策略类: {len(strategic)} 条")
        
        # 上下文类 (2种新增)
        contextual = self._extract_contextual(messages)
        knowledge.extend(contextual)
        logger.debug(f"[EnhancedExtractor] 上下文类: {len(contextual)} 条")
        
        # 3. 多轮对话分析 (4种)
        if len(messages) >= 3:  # 至少3条消息才能分析多轮模式
            multi_turn = self._extract_multi_turn(messages)
            knowledge.extend(multi_turn)
            logger.debug(f"[EnhancedExtractor] 多轮对话: {len(multi_turn)} 条")
        
        # 过滤低置信度知识
        before_filter = len(knowledge)
        knowledge = [k for k in knowledge if k.confidence >= self.config.min_confidence]
        filtered_count = before_filter - len(knowledge)
        
        if filtered_count > 0:
            logger.debug(f"[EnhancedExtractor] 过滤低置信度知识: {filtered_count} 条")
        
        logger.info(f"[EnhancedExtractor] ✓ 增强知识提取完成 - 总计 {len(knowledge)} 条有效知识（30种类型）")
        
        if knowledge:
            # 按类型统计
            type_counts = {}
            for k in knowledge:
                type_name = k.knowledge_type.value
                type_counts[type_name] = type_counts.get(type_name, 0) + 1
            
            logger.debug(f"[EnhancedExtractor] 知识类型分布:")
            for ktype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                logger.debug(f"  - {ktype}: {count} 条")
            if len(type_counts) > 10:
                logger.debug(f"  ... 以及其他 {len(type_counts) - 10} 种类型")
        
        return knowledge
    
    def _extract_user_profile(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户画像类知识 (4种)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # USER_INFO: 基本信息
            info_patterns = [
                (r'我(今年|是)(\d+)(岁|周岁)', 'age'),
                (r'我(是|在|做)(.{2,10})(工作|职业|行业)', 'occupation'),
                (r'我(在|住在|来自)(.{2,15})(市|省|区|县)', 'location'),
                (r'我(叫|是|名字叫)(.{2,6})(?=[，。！？]|$)', 'name'),
            ]
            
            for pattern, category in info_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        info_value = match[1].strip() if len(match) > 1 else match[0].strip()
                        if 2 <= len(info_value) <= 20:
                            knowledge.append(Knowledge(
                                content=f"用户{category}: {info_value}",
                                knowledge_type=KnowledgeType.USER_INFO,
                                scores=ScoreInfo(confidence=0.8),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'category': category, 'value': info_value}
                            ))
            
            # PERSONALITY: 性格特征
            personality_patterns = [
                (r'我(是个|比较|很)(.{2,8})(的人|性格)', 'trait'),
                (r'我(性格|为人)(.{2,8})', 'trait'),
            ]
            
            for pattern, category in personality_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        trait = match[1].strip()
                        if 2 <= len(trait) <= 15:
                            knowledge.append(Knowledge(
                                content=f"用户性格: {trait}",
                                knowledge_type=KnowledgeType.PERSONALITY,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'trait': trait}
                            ))
            
            # VALUES: 价值观
            value_patterns = [
                (r'我(认为|觉得|相信)(.{5,30})(很重要|重要|最重要)', 'importance'),
                (r'对我来说(.{3,20})(最重要|很重要)', 'importance'),
            ]
            
            for pattern, category in value_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        value = match[0].strip() if len(match) == 1 else match[1].strip()
                        if 3 <= len(value) <= 30:
                            knowledge.append(Knowledge(
                                content=f"用户价值观: {value}",
                                knowledge_type=KnowledgeType.VALUES,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'value': value}
                            ))
            
            # LIFESTYLE: 生活方式
            lifestyle_patterns = [
                (r'我(经常|总是|习惯|平时)(.{3,20})', 'routine'),
                (r'我(每天|每周|每月)(.{3,20})', 'frequency'),
            ]
            
            for pattern, category in lifestyle_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        activity = match[1].strip()
                        if 3 <= len(activity) <= 25:
                            knowledge.append(Knowledge(
                                content=f"用户生活方式: {activity}",
                                knowledge_type=KnowledgeType.LIFESTYLE,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'activity': activity}
                            ))
        
        return knowledge
    
    def _extract_cognitive(self, messages: List[Message]) -> List[Knowledge]:
        """提取认知类知识 (3种新增)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # BELIEF: 信念
            belief_patterns = [
                (r'我(相信|坚信|深信)(.{3,30})', 'belief'),
                (r'我(一直|始终)(相信|认为)(.{3,30})', 'belief'),
            ]
            
            for pattern, category in belief_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        belief_text = match[-1].strip()
                        if 3 <= len(belief_text) <= 40:
                            knowledge.append(Knowledge(
                                content=f"用户信念: {belief_text}",
                                knowledge_type=KnowledgeType.BELIEF,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'belief': belief_text}
                            ))
            
            # ATTITUDE: 态度
            attitude_patterns = [
                (r'我(对|对于)(.{2,15})(的态度|持|保持)(.{2,20})', 'attitude'),
                (r'我(支持|反对|赞成)(.{3,25})', 'stance'),
            ]
            
            for pattern, category in attitude_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        target = match[1].strip()
                        attitude_text = match[-1].strip() if len(match) > 2 else target
                        if 2 <= len(attitude_text) <= 30:
                            knowledge.append(Knowledge(
                                content=f"用户态度: {attitude_text}",
                                knowledge_type=KnowledgeType.ATTITUDE,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'target': target, 'attitude': attitude_text}
                            ))
            
            # VALUE_JUDGMENT: 价值判断
            judgment_patterns = [
                (r'(.{2,15})(是|很|非常)(好|不好|糟糕|优秀|差)', 'judgment'),
                (r'我(认为|觉得)(.{3,20})(不错|很好|不行|不好)', 'opinion_judgment'),
            ]
            
            for pattern, category in judgment_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        subject = match[0].strip() if category == 'judgment' else match[1].strip()
                        judgment = match[-1].strip()
                        if 2 <= len(subject) <= 25:
                            knowledge.append(Knowledge(
                                content=f"用户判断: {subject} - {judgment}",
                                knowledge_type=KnowledgeType.VALUE_JUDGMENT,
                                scores=ScoreInfo(confidence=0.65),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'subject': subject, 'judgment': judgment}
                            ))
        
        return knowledge
    
    def _extract_behavioral(self, messages: List[Message]) -> List[Knowledge]:
        """提取行为类知识 (3种新增)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # EXPERIENCE: 经验
            experience_patterns = [
                (r'我(曾经|以前|之前)(.{3,30})(过|了)', 'past_experience'),
                (r'我(有|具有)(.{3,25})(经验|经历)', 'has_experience'),
                (r'我(试过|尝试过|做过)(.{3,30})', 'tried'),
            ]
            
            for pattern, category in experience_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        exp_text = match[1].strip()
                        if 3 <= len(exp_text) <= 35:
                            knowledge.append(Knowledge(
                                content=f"用户经验: {exp_text}",
                                knowledge_type=KnowledgeType.EXPERIENCE,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'experience': exp_text, 'category': category}
                            ))
            
            # SKILL: 技能
            skill_patterns = [
                (r'我(会|能|擅长|精通)(.{2,20})', 'can_do'),
                (r'我(掌握|学会|学过)(.{2,20})', 'learned'),
            ]
            
            for pattern, category in skill_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        skill = match[1].strip()
                        if 2 <= len(skill) <= 25:
                            knowledge.append(Knowledge(
                                content=f"用户技能: {skill}",
                                knowledge_type=KnowledgeType.SKILL,
                                scores=ScoreInfo(confidence=0.8),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'skill': skill}
                            ))
            
            # ACHIEVEMENT: 成就
            achievement_patterns = [
                (r'我(获得|拿到|取得|赢得)(.{3,30})(奖|证书|成就|认证)', 'award'),
                (r'我(完成|实现|达成)(.{3,30})', 'accomplishment'),
            ]
            
            for pattern, category in achievement_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        achievement = match[1].strip()
                        if 3 <= len(achievement) <= 35:
                            knowledge.append(Knowledge(
                                content=f"用户成就: {achievement}",
                                knowledge_type=KnowledgeType.ACHIEVEMENT,
                                scores=ScoreInfo(confidence=0.8),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'achievement': achievement}
                            ))
        
        return knowledge
    
    def _extract_intentional(self, messages: List[Message]) -> List[Knowledge]:
        """提取意图类知识 (3种新增)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # GOAL: 目标
            goal_patterns = [
                (r'我(的目标|希望|目标)是(.{3,30})', 'explicit_goal'),
                (r'我(想要|要)(实现|达到|达成)(.{3,30})', 'achieve_goal'),
            ]
            
            for pattern, category in goal_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        goal = match[-1].strip()
                        if 3 <= len(goal) <= 35:
                            knowledge.append(Knowledge(
                                content=f"用户目标: {goal}",
                                knowledge_type=KnowledgeType.GOAL,
                                scores=ScoreInfo(confidence=0.8),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'goal': goal}
                            ))
            
            # PLAN: 计划
            plan_patterns = [
                (r'我(打算|计划|准备)(.{3,30})', 'plan'),
                (r'我(会|将要|要去)(.{3,30})', 'future_action'),
            ]
            
            for pattern, category in plan_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        plan = match[1].strip()
                        if 3 <= len(plan) <= 35:
                            knowledge.append(Knowledge(
                                content=f"用户计划: {plan}",
                                knowledge_type=KnowledgeType.PLAN,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'plan': plan}
                            ))
            
            # EXPECTATION: 期望
            expectation_patterns = [
                (r'我(期望|期待|希望)(.{3,30})', 'expectation'),
                (r'最好(.{3,25})', 'preference_expectation'),
            ]
            
            for pattern, category in expectation_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        expectation = match[0].strip() if len(match) == 1 else match[1].strip()
                        if 3 <= len(expectation) <= 35:
                            knowledge.append(Knowledge(
                                content=f"用户期望: {expectation}",
                                knowledge_type=KnowledgeType.EXPECTATION,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'expectation': expectation}
                            ))
        
        return knowledge
    
    def _extract_relational(self, messages: List[Message]) -> List[Knowledge]:
        """提取关系类知识 (3种)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # RELATIONSHIP: 社交关系
            relationship_patterns = [
                (r'我(的|有个?)(.{2,8})(叫|是|名字)(.{2,10})', 'person'),
                (r'我(和|跟)(.{2,10})(是|认识|熟悉)', 'connection'),
            ]
            
            for pattern, category in relationship_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        relation = match[1].strip()
                        person = match[-1].strip() if len(match) > 2 else relation
                        if 2 <= len(relation) <= 15:
                            knowledge.append(Knowledge(
                                content=f"用户关系: {relation} - {person}",
                                knowledge_type=KnowledgeType.RELATIONSHIP,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'relation': relation, 'person': person}
                            ))
            
            # EMOTIONAL_CONNECTION: 情感连接
            emotion_connection_patterns = [
                (r'我(很|非常)(喜欢|爱|在乎|关心)(.{2,15})', 'care'),
                (r'(.{2,15})(对我|对于我)(很重要|重要)', 'important_to_me'),
            ]
            
            for pattern, category in emotion_connection_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        target = match[-1].strip() if category == 'care' else match[0].strip()
                        if 2 <= len(target) <= 20:
                            knowledge.append(Knowledge(
                                content=f"用户情感连接: {target}",
                                knowledge_type=KnowledgeType.EMOTIONAL_CONNECTION,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'target': target}
                            ))
            
            # INFLUENCE: 影响因素
            influence_patterns = [
                (r'(.{2,15})(影响|影响了|会影响)(.{2,20})', 'influence'),
                (r'因为(.{3,20})(所以|导致|使得)(.{3,25})', 'causation'),
            ]
            
            for pattern, category in influence_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 2:
                        factor = match[0].strip()
                        effect = match[-1].strip()
                        if 2 <= len(factor) <= 25:
                            knowledge.append(Knowledge(
                                content=f"影响因素: {factor} → {effect}",
                                knowledge_type=KnowledgeType.INFLUENCE,
                                scores=ScoreInfo(confidence=0.65),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'factor': factor, 'effect': effect}
                            ))
        
        return knowledge
    
    def _extract_epistemic(self, messages: List[Message]) -> List[Knowledge]:
        """提取知识类 (3种新增)"""
        knowledge = []
        
        for msg in messages:
            content = msg.content.strip()
            
            # PROCEDURAL: 程序性知识（如何做）
            procedural_patterns = [
                (r'(要|需要|应该)(先|首先)(.{3,20})(然后|再|接着)(.{3,20})', 'steps'),
                (r'(可以|能够)(通过|用|使用)(.{3,25})(来|去)(.{3,20})', 'method'),
            ]
            
            for pattern, category in procedural_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 3:
                        step1 = match[2].strip()
                        step2 = match[-1].strip()
                        if 3 <= len(step1) <= 30:
                            knowledge.append(Knowledge(
                                content=f"程序性知识: {step1} → {step2}",
                                knowledge_type=KnowledgeType.PROCEDURAL,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'steps': [step1, step2]}
                            ))
            
            # DOMAIN_KNOWLEDGE: 领域知识
            domain_patterns = [
                (r'在(.{2,10})(领域|行业|方面)(.{3,30})', 'domain_fact'),
                (r'(.{3,15})(是|指|意思是)(.{3,35})', 'definition'),
            ]
            
            for pattern, category in domain_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        domain = match[0].strip() if category == 'domain_fact' else match[0].strip()
                        knowledge_text = match[-1].strip()
                        if 3 <= len(knowledge_text) <= 40:
                            knowledge.append(Knowledge(
                                content=f"领域知识: {domain} - {knowledge_text}",
                                knowledge_type=KnowledgeType.DOMAIN_KNOWLEDGE,
                                scores=ScoreInfo(confidence=0.65),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'domain': domain, 'knowledge': knowledge_text}
                            ))
            
            # COMMON_SENSE: 常识
            common_sense_patterns = [
                (r'(一般|通常|普遍)(.{3,25})', 'general'),
                (r'(大家|人们|大部分人)(都|通常)(.{3,25})', 'common'),
            ]
            
            for pattern, category in common_sense_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        sense = match[-1].strip()
                        if 3 <= len(sense) <= 30:
                            knowledge.append(Knowledge(
                                content=f"常识: {sense}",
                                knowledge_type=KnowledgeType.COMMON_SENSE,
                                scores=ScoreInfo(confidence=0.6),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'sense': sense}
                            ))
        
        return knowledge
    
    def _extract_emotional(self, messages: List[Message]) -> List[Knowledge]:
        """提取情感类知识 (2种新增)"""
        knowledge = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # EMOTION: 情绪状态
            emotion_patterns = [
                (r'我(感到|觉得|很|非常)(开心|高兴|难过|伤心|生气|愤怒|焦虑|紧张|兴奋|激动|失望|沮丧|害怕|担心)', 'emotion_state'),
                (r'我(心情|情绪)(好|不好|低落|高涨)', 'mood'),
            ]
            
            for pattern, category in emotion_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        emotion = match[-1].strip()
                        knowledge.append(Knowledge(
                            content=f"用户情绪: {emotion}",
                            knowledge_type=KnowledgeType.EMOTION,
                            scores=ScoreInfo(confidence=0.75),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={'emotion': emotion}
                        ))
            
            # SENTIMENT: 情感倾向
            sentiment_patterns = [
                (r'我(对|对于)(.{2,15})(持|保持)(积极|消极|乐观|悲观|正面|负面)', 'sentiment_toward'),
                (r'(.{2,15})(让我|使我)(感到|觉得)(高兴|难过|生气|失望)', 'triggered_sentiment'),
            ]
            
            for pattern, category in sentiment_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        target = match[1].strip() if category == 'sentiment_toward' else match[0].strip()
                        sentiment = match[-1].strip()
                        if 2 <= len(target) <= 20:
                            knowledge.append(Knowledge(
                                content=f"用户情感倾向: {target} - {sentiment}",
                                knowledge_type=KnowledgeType.SENTIMENT,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'target': target, 'sentiment': sentiment}
                            ))
        
        return knowledge
    
    def _extract_strategic(self, messages: List[Message]) -> List[Knowledge]:
        """提取策略类知识 (4种)"""
        knowledge = []
        
        for msg in messages:
            content = msg.content.strip()
            
            # SOLUTION: 解决方案
            solution_patterns = [
                (r'(可以|能够)(用|通过|采用)(.{3,30})(来解决|解决|处理)', 'solution_method'),
                (r'(解决方案|办法|方法)是(.{3,30})', 'explicit_solution'),
            ]
            
            for pattern, category in solution_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        solution = match[-2].strip() if category == 'solution_method' else match[-1].strip()
                        if 3 <= len(solution) <= 35:
                            knowledge.append(Knowledge(
                                content=f"解决方案: {solution}",
                                knowledge_type=KnowledgeType.SOLUTION,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'solution': solution}
                            ))
            
            # STRATEGY: 策略
            strategy_patterns = [
                (r'(策略|战略|方针)是(.{3,30})', 'strategy'),
                (r'(应该|需要|要)(采取|使用|运用)(.{3,25})(策略|方法)', 'recommended_strategy'),
            ]
            
            for pattern, category in strategy_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        strategy = match[-2].strip() if category == 'recommended_strategy' else match[-1].strip()
                        if 3 <= len(strategy) <= 35:
                            knowledge.append(Knowledge(
                                content=f"策略: {strategy}",
                                knowledge_type=KnowledgeType.STRATEGY,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'strategy': strategy}
                            ))
            
            # BEST_PRACTICE: 最佳实践
            best_practice_patterns = [
                (r'(最好|建议|推荐)(.{3,30})', 'recommendation'),
                (r'(最佳|理想)(做法|方法|实践)是(.{3,30})', 'best_practice'),
            ]
            
            for pattern, category in best_practice_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        practice = match[-1].strip()
                        if 3 <= len(practice) <= 35:
                            knowledge.append(Knowledge(
                                content=f"最佳实践: {practice}",
                                knowledge_type=KnowledgeType.BEST_PRACTICE,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'practice': practice}
                            ))
            
            # LESSON_LEARNED: 经验教训
            lesson_patterns = [
                (r'(我学到|学会|明白|懂得)(.{3,30})', 'learned'),
                (r'(教训|经验)是(.{3,30})', 'lesson'),
                (r'(不应该|不要|避免)(.{3,25})', 'what_not_to_do'),
            ]
            
            for pattern, category in lesson_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        lesson = match[-1].strip()
                        if 3 <= len(lesson) <= 35:
                            knowledge.append(Knowledge(
                                content=f"经验教训: {lesson}",
                                knowledge_type=KnowledgeType.LESSON_LEARNED,
                                scores=ScoreInfo(confidence=0.7),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'lesson': lesson, 'category': category}
                            ))
        
        return knowledge
    
    def _extract_contextual(self, messages: List[Message]) -> List[Knowledge]:
        """提取上下文类知识 (2种新增)"""
        knowledge = []
        
        # TOPIC: 话题识别
        if messages:
            # 简单的话题提取：从用户消息中提取高频词汇
            user_messages = [m for m in messages if m.role.value == "user"]
            if user_messages:
                # 提取最后几条消息的主题词
                recent_content = " ".join([m.content for m in user_messages[-3:]])
                # 简单的关键词提取（这里使用简化版本）
                words = re.findall(r'[\u4e00-\u9fff]{2,6}', recent_content)
                word_counts = {}
                for word in words:
                    if word not in ['我们', '你们', '他们', '什么', '怎么', '这个', '那个', '可以', '需要']:
                        word_counts[word] = word_counts.get(word, 0) + 1
                
                # 提取高频主题词
                top_topics = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                for topic, count in top_topics:
                    if count >= 2:  # 至少出现2次
                        knowledge.append(Knowledge(
                            content=f"对话话题: {topic}",
                            knowledge_type=KnowledgeType.TOPIC,
                            scores=ScoreInfo(confidence=0.6),
                            extraction_method='frequency',
                            source_message_ids=[getattr(m, 'id', '') for m in user_messages[-3:]],
                            metadata={'topic': topic, 'frequency': count}
                        ))
        
        # SCENARIO: 场景识别
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            scenario_patterns = [
                (r'在(.{2,10})(的时候|时|中)(.{3,20})', 'when_doing'),
                (r'(工作|生活|学习|旅行|购物)(中|时)(.{3,25})', 'context'),
            ]
            
            for pattern, category in scenario_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        scenario = match[0].strip() if category == 'when_doing' else match[0].strip()
                        context = match[-1].strip()
                        if 2 <= len(scenario) <= 15:
                            knowledge.append(Knowledge(
                                content=f"场景: {scenario} - {context}",
                                knowledge_type=KnowledgeType.SCENARIO,
                                scores=ScoreInfo(confidence=0.65),
                                extraction_method='rule',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'scenario': scenario, 'context': context}
                            ))
        
        return knowledge
    
    def _extract_multi_turn(self, messages: List[Message]) -> List[Knowledge]:
        """提取多轮对话知识 (4种)"""
        knowledge = []
        
        if len(messages) < 3:
            return knowledge
        
        # CONVERSATION_PATTERN: 对话模式
        # 分析问答模式
        qa_sequences = []
        for i in range(len(messages) - 1):
            if messages[i].role.value == "user" and messages[i+1].role.value == "assistant":
                user_content = messages[i].content[:50]
                qa_sequences.append(user_content)
        
        if len(qa_sequences) >= 2:
            knowledge.append(Knowledge(
                content=f"对话模式: 问答序列 ({len(qa_sequences)}轮)",
                knowledge_type=KnowledgeType.CONVERSATION_PATTERN,
                scores=ScoreInfo(confidence=0.65),
                extraction_method='multi_turn_analysis',
                source_message_ids=[getattr(m, 'id', '') for m in messages],
                metadata={'pattern_type': 'qa_sequence', 'turns': len(qa_sequences)}
            ))
        
        # TOPIC_EVOLUTION: 主题演变
        # 简单检测主题变化
        user_messages = [m for m in messages if m.role.value == "user"]
        if len(user_messages) >= 3:
            first_topics = set(re.findall(r'[\u4e00-\u9fff]{2,6}', user_messages[0].content))
            last_topics = set(re.findall(r'[\u4e00-\u9fff]{2,6}', user_messages[-1].content))
            
            common = first_topics & last_topics
            new_topics = last_topics - first_topics
            
            if new_topics:
                knowledge.append(Knowledge(
                    content=f"主题演变: 从 {len(first_topics)} 个初始话题扩展到 {len(last_topics)} 个话题",
                    knowledge_type=KnowledgeType.TOPIC_EVOLUTION,
                    scores=ScoreInfo(confidence=0.6),
                    extraction_method='multi_turn_analysis',
                    source_message_ids=[getattr(m, 'id', '') for m in user_messages],
                    metadata={'initial_topics': len(first_topics), 'final_topics': len(last_topics), 'new_topics': len(new_topics)}
                ))
        
        # PROBLEM_SOLUTION_SEQ: 问题-解决序列
        # 检测问题和解决方案的序列
        problem_keywords = ['问题', '困难', '麻烦', '怎么办', '如何', '怎样']
        solution_keywords = ['解决', '办法', '方法', '可以', '建议', '推荐']
        
        has_problem = any(any(kw in m.content for kw in problem_keywords) for m in messages if m.role.value == "user")
        has_solution = any(any(kw in m.content for kw in solution_keywords) for m in messages if m.role.value == "assistant")
        
        if has_problem and has_solution:
            knowledge.append(Knowledge(
                content="问题-解决序列: 用户提出问题 → 系统提供解决方案",
                knowledge_type=KnowledgeType.PROBLEM_SOLUTION_SEQ,
                scores=ScoreInfo(confidence=0.7),
                extraction_method='multi_turn_analysis',
                source_message_ids=[getattr(m, 'id', '') for m in messages],
                metadata={'has_problem': has_problem, 'has_solution': has_solution}
            ))
        
        # CAUSALITY: 因果关系
        # 检测因果关系表达
        causality_patterns = [
            r'因为(.{3,20})(所以|导致|使得)(.{3,20})',
            r'由于(.{3,20})(造成|引起)(.{3,20})',
        ]
        
        for msg in messages:
            content = msg.content
            for pattern in causality_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple) and len(match) >= 3:
                        cause = match[0].strip()
                        effect = match[2].strip()
                        if 3 <= len(cause) <= 25 and 3 <= len(effect) <= 25:
                            knowledge.append(Knowledge(
                                content=f"因果关系: {cause} → {effect}",
                                knowledge_type=KnowledgeType.CAUSALITY,
                                scores=ScoreInfo(confidence=0.75),
                                extraction_method='multi_turn_analysis',
                                source_message_ids=[getattr(msg, 'id', '')],
                                metadata={'cause': cause, 'effect': effect}
                            ))
        
        return knowledge
