"""
Memory Extractors - 知识提取的 Plugin 实现

本模块提供多种策略, 用于从对话中提取有价值的信息并存储到长期记忆
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re

from ..models import Message, Knowledge, KnowledgeType, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger

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
                            knowledge_type=KnowledgeType.PREFERENCE,
                            confidence=self.CONFIDENCE_PREFERENCE_POSITIVE,
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'sentiment': sentiment,
                                'keyword': keyword,
                                'category': '偏好',
                                'context': content[:100]  # 保留上下文前100字符
                            }
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
                            knowledge_type=KnowledgeType.FACT,
                            confidence=self.CONFIDENCE_FACT,
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={
                                'category': category,
                                'subject': subject,
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
                            confidence=self.CONFIDENCE_EVENT,
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
                            confidence=float(item.get('confidence', 0.8)),
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
