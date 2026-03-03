"""记忆提取器 - 统一知识提取"""

from typing import List, Optional
import re
import json

from ..core.data_models import Message, Knowledge, ScoreInfo
from ..core.types import KnowledgeType
from ..core.configs import ExtractionConfig, DEFAULT_MEMORY_CONFIG
from contextmind.infra.logger import get_logger
from ..core.strategies import ExtractionStrategy as BaseExtractor  # Use core base class
from contextmind.infra.embedding import get_embedding_client

logger = get_logger(__name__)


class RuleBasedExtractor(BaseExtractor):
    """基于规则的知识提取器，作为 LLMBasedExtractor 失败时的轻量级后备方案。"""
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
    
    @property
    def confidence_filter_min(self) -> float:
        return self.config.min_confidence
    
    @property
    def confidence_preference_positive(self) -> float:
        return self.config.preference_confidence
    
    @property
    def confidence_preference_negative(self) -> float:
        return self.config.preference_confidence * 0.9
    
    @property
    def confidence_fact(self) -> float:
        return self.config.fact_confidence
    
    @property
    def confidence_event(self) -> float:
        return self.config.event_confidence
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """使用基于规则的模式提取知识"""
        logger.info(f"[Extractor] 开始基于规则的知识提取 - 处理 {len(messages)} 条消息")
        
        knowledge = []
        
        preferences = self._extract_preferences(messages)
        knowledge.extend(preferences)
        logger.debug(f"[Extractor] 提取偏好: {len(preferences)} 条")
        
        facts = self._extract_facts(messages)
        knowledge.extend(facts)
        logger.debug(f"[Extractor] 提取事实: {len(facts)} 条")
        
        events = self._extract_events(messages)
        knowledge.extend(events)
        logger.debug(f"[Extractor] 提取事件: {len(events)} 条")
        
        before_filter = len(knowledge)
        knowledge = [k for k in knowledge if k.confidence >= self.confidence_filter_min]
        filtered_count = before_filter - len(knowledge)
        
        if filtered_count > 0:
            logger.debug(f"[Extractor] 过滤低置信度知识: {filtered_count} 条 (阈值: {self.confidence_filter_min})")
        
        logger.info(f"[Extractor] ✓ 知识提取完成 - 总计 {len(knowledge)} 条有效知识")
        
        if knowledge:
            logger.debug(f"[Extractor] 提取的知识详情:")
            for i, k in enumerate(knowledge[:5], 1):
                logger.debug(f"  {i}. [{k.knowledge_type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
            if len(knowledge) > 5:
                logger.debug(f"  ... 以及其他 {len(knowledge) - 5} 条知识")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好 - 通用语言学模式"""
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 2:
                continue
            
            intent_patterns = [
                (r'想(买|要|购买|入手|做|学|了解|知道)(.+?)(?=[。！？,.!?；：]|$)', 'intent'),
                (r'需要(.+?)(?=[。！？,.!?；：]|$)', 'need'),
                (r'希望(.+?)(?=[。！？,.!?；：]|$)', 'hope'),
            ]
            
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好|想|要|爱|倾向于)(.+?)(?=[。！？,.!?；：]|$)', 'preference'),
                (r'比较(喜欢|想要|倾向|偏向)(.+?)(?=[。！？,.!?；：]|$)', 'comparative_preference'),
            ]
            
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
                    
                    if (2 <= len(target) <= self.config.max_phrase_length and target.strip()):
                        full_content = f"用户{category}: {action}{target}" if action else f"用户{category}: {target}"
                        k_type = KnowledgeType.INTENT if category in ('intent', 'plan', 'hope') else KnowledgeType.NEED if category == 'need' else KnowledgeType.PREFERENCE
                        
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=k_type,
                            scores=ScoreInfo(confidence=0.75),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={'category': category, 'action': action, 'target': target, 'context': content[:100]}
                        ))
            
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
                    
                    if (2 <= len(phrase) <= self.config.max_phrase_length
                        and not phrase.startswith(('不', '没', '无'))
                        and phrase.strip()):
                        full_content = f"用户偏好: {keyword}{phrase}" if keyword else f"用户偏好: {phrase}"
                        preferences.append(Knowledge(
                            content=full_content,
                            knowledge_type=KnowledgeType.PREFERENCE,
                            scores=ScoreInfo(confidence=self.confidence_preference_positive),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={'category': category, 'keyword': keyword, 'phrase': phrase, 'context': content[:100]}
                        ))
        
        return preferences
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """提取事实陈述 - 通用语言学模式"""
        facts = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            if len(content) < 3:
                continue
            
            identity_patterns = [
                (r'(我|他|她)是(.+?)(?=[。！？,.!?；：]|$)', 'identity'),
                (r'(我|他|她)叫(.+?)(?=[。！？,.!?；：]|$)', 'name'),
                (r'(我|他|她)在(.+?)(?=[。！？,.!?；：]|$)', 'location'),
            ]
            
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
                            scores=ScoreInfo(confidence=self.confidence_fact),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={'category': category, 'subject': subject, 'detail': detail, 'context': content[:100]}
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
                            scores=ScoreInfo(confidence=self.confidence_event),
                            extraction_method='rule',
                            source_message_ids=[getattr(msg, 'id', '')],
                            metadata={'keyword': keyword, 'category': category, 'context': content[:100]}
                        ))
        
        return events


class LLMBasedExtractor(BaseExtractor):
    """基于LLM的知识提取器（推荐），支持40种知识类型的语义提取。"""
    
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
        """使用LLM提取知识"""
        if not self.llm_client:
            logger.debug("[LLMBasedExtractor] 回退到规则提取 (无LLM客户端)")
            fallback = RuleBasedExtractor(self.config)
            return await fallback.extract(messages)
        
        logger.info(f"[LLMBasedExtractor] 开始LLM知识提取 - 处理 {len(messages)} 条消息")
        
        conversation_text = self._build_conversation_text(messages)
        if not conversation_text:
            logger.warning("[LLMBasedExtractor] 对话文本为空，跳过提取")
            return []
        
        try:
            extracted_data = await self._extract_with_llm(conversation_text)
            knowledge_list = self._parse_llm_response(extracted_data, messages)
            
            before_validation = len(knowledge_list)
            knowledge_list = self._validate_knowledge_against_conversation(knowledge_list, conversation_text)
            hallucination_count = before_validation - len(knowledge_list)
            
            if hallucination_count > 0:
                logger.warning(f"[LLMBasedExtractor] ⚠️ 过滤疑似幻觉知识: {hallucination_count} 条")
            
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
        """使用LLM提取知识"""
        system_prompt = """你是一个专业的知识提取助手。从对话中提取结构化知识信息。

⚠️ 重要原则：
1. **只能提取对话中明确出现的信息** - 必须能在原文中找到直接依据
2. **严禁推理、联想、补充信息** - 不要根据常识或背景知识添加内容
3. **严禁捏造或猜测** - 如果对话中没有说，就不要提取
4. **如实提取** - 保持原意，不要过度解读或扩展

返回JSON格式:
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

支持的知识类型包括: user_info, preference, fact, event, intent, need, opinion, habit, constraint, interest等40种。
只提取高价值信息，置信度需要>=0.70。
记住：提取的每条知识都必须有对话中的直接依据，不可凭空创造。"""
        
        user_prompt = f"""请从以下对话中提取结构化知识：

{conversation_text}

请返回JSON格式的提取结果。
提醒：只提取对话中明确出现的信息，不要添加任何推理、联想或补充的内容。"""
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            if hasattr(self.llm_client, 'chat_async'):
                response = await self.llm_client.chat_async(messages=messages)
            elif hasattr(self.llm_client, 'chat'):
                response = self.llm_client.chat(messages=messages)
            elif hasattr(self.llm_client, 'generate_async'):
                _, response = await self.llm_client.generate_async(system_prompt + "\n\n" + user_prompt)
            elif hasattr(self.llm_client, 'generate'):
                _, response = self.llm_client.generate(system_prompt + "\n\n" + user_prompt)
            else:
                raise ValueError("LLM客户端缺少chat_async、chat、generate_async或generate方法")

            return response
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM调用失败: {e}")
            raise
    
    def _parse_llm_response(self, llm_response: str, messages: List[Message]) -> List[Knowledge]:
        """解析LLM返回的JSON格式知识"""
        knowledge_list = []
        
        try:
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', llm_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = llm_response.strip()
            
            data = json.loads(json_str)
            
            if 'knowledge' in data:
                for item in data['knowledge']:
                    try:
                        content = item.get('content', '').strip()
                        type_str = item.get('type', '').lower()
                        confidence = float(item.get('confidence', 0.8))
                        
                        if not type_str or type_str in ['unknown', 'none', '']:
                            logger.debug(f"[LLMBasedExtractor] 跳过无效类型: type={type_str}")
                            continue
                        
                        if not content or len(content) < 5:
                            logger.debug(f"[LLMBasedExtractor] 跳过内容过短: {content}")
                            continue
                        
                        if confidence < 0.72 or confidence > 1.0:
                            logger.debug(f"[LLMBasedExtractor] 跳过不合理置信度: {confidence}")
                            continue
                        
                        knowledge_type = self._TYPE_MAPPING.get(type_str)
                        if knowledge_type is None:
                            logger.warning(f"[LLMBasedExtractor] 未知类型 '{type_str}'，跳过")
                            continue
                        
                        knowledge = Knowledge(
                            content=content,
                            knowledge_type=knowledge_type,
                            scores=ScoreInfo(confidence=confidence),
                            extraction_method='llm',
                            source_message_ids=[getattr(msg, 'id', '') for msg in messages],
                            metadata={
                                'category': item.get('category', ''),
                                'llm_extracted': True
                            }
                        )
                        
                        embedding_client = get_embedding_client()
                        if embedding_client:
                            embedding_info = embedding_client.generate_embedding(content)
                            if embedding_info:
                                knowledge.embeddings['default'] = embedding_info
                        
                        knowledge_list.append(knowledge)
                        
                    except Exception as e:
                        logger.warning(f"[LLMBasedExtractor] 解析知识项失败: {e}")
                        continue
            
            logger.debug(f"[LLMBasedExtractor] 成功解析 {len(knowledge_list)} 条知识")
            
        except json.JSONDecodeError as e:
            logger.error(f"[LLMBasedExtractor] JSON解析失败: {e}")
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] 解析LLM响应失败: {e}")
        
        return knowledge_list


    def _validate_knowledge_against_conversation(self, knowledge_list: List[Knowledge], conversation_text: str) -> List[Knowledge]:
        """
        验证提取的知识是否真实存在于对话中，过滤幻觉内容
        
        Args:
            knowledge_list: 待验证的知识列表
            conversation_text: 原始对话文本
            
        Returns:
            验证通过的知识列表
        """
        validated = []
        conversation_lower = conversation_text.lower()
        
        for knowledge in knowledge_list:
            content = knowledge.content.strip()
            
            content_clean = re.sub(r'^(用户|助手|客户)?(偏好|意图|需求|事实|事件|观点|习惯|约束|兴趣|信息|计划|目标|问题|反馈|评价|建议|要求|条件|状态|行为|特征|属性|关系|经历|技能|知识|态度|情感|价值观|理念|原则|规则|标准|期望|愿望|梦想|担忧|顾虑|限制|障碍|挑战|机会|资源|能力|优势|劣势|风险|威胁)[:：]\s*', '', content)
            
            key_phrases = re.findall(r'[\u4e00-\u9fa5]{3,}', content_clean)
            
            if not key_phrases:
                key_phrases = [content_clean]
            
            found = False
            for phrase in key_phrases:
                if len(phrase) >= 2 and phrase.lower() in conversation_lower:
                    found = True
                    break
            
            if found:
                validated.append(knowledge)
            else:
                logger.debug(f"[LLMBasedExtractor] 过滤疑似幻觉: [{knowledge.knowledge_type.value}] {content[:50]}...")
        
        return validated


class ImportancePredictorExtractor(BaseExtractor):
    """重要性感知提取器，使用训练好的模型预测提取信息的长期重要性，在存储前过滤低价值记忆。"""
    
    def __init__(
        self,
        model: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        self.model = model
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        logger.info("[ImportancePredictorExtractor] 已初始化（占位符实现）")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """使用重要性预测提取知识，当前回退到基于规则的提取。"""
        logger.debug("[ImportancePredictorExtractor] 使用回退到 RuleBasedExtractor（尚未实现）")
        
        fallback = RuleBasedExtractor(self.config)
        knowledge = await fallback.extract(messages)
        
        return knowledge
    
    def _predict_importance(self, knowledge: Knowledge) -> float:
        """预测知识项的重要性分数（占位符）"""
        logger.warning("[ImportancePredictorExtractor] 使用占位符实现，返回默认重要性分数 1.0")
        return 1.0


__all__ = [
    "BaseExtractor",
    "RuleBasedExtractor",
    "LLMBasedExtractor",
    "ImportancePredictorExtractor",
]
