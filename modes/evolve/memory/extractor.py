"""
记忆提取器 - 统一知识提取

合并自：
- extractors/base.py (BaseExtractor)
- extractors/rule.py (RuleBasedExtractor)
- extractors/llm.py (LLMBasedExtractor)
- extractors/importance.py (ImportancePredictorExtractor)

本模块提供多种策略, 用于从对话中提取有价值的信息并存储到长期记忆
"""

from typing import List, Optional
import re
import json

from ..core.data_models import Message, Knowledge, ScoreInfo
from ..core.types import KnowledgeType
from ..core.configs import ExtractionConfig, DEFAULT_MEMORY_CONFIG
from utils.logger import get_logger
from ..core.strategies import ExtractionStrategy as BaseExtractor  # Use core base class
from utils.embedding import get_embedding_client

logger = get_logger(__name__)

# ============================================================================
# RuleBasedExtractor - 基于规则的提取
# ============================================================================

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
    
    # 属性用于访问
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
        """
        使用基于规则的模式提取知识
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识列表
        """
        logger.info(f"[Extractor] 开始基于规则的知识提取 - 处理 {len(messages)} 条消息")
        
        knowledge = []
        
        # 提取偏好
        preferences = self._extract_preferences(messages)
        knowledge.extend(preferences)
        logger.debug(f"[Extractor] 提取偏好: {len(preferences)} 条")
        
        # 提取事实
        facts = self._extract_facts(messages)
        knowledge.extend(facts)
        logger.debug(f"[Extractor] 提取事实: {len(facts)} 条")
        
        # 提取事件
        events = self._extract_events(messages)
        knowledge.extend(events)
        logger.debug(f"[Extractor] 提取事件: {len(events)} 条")
        
        # 过滤低置信度知识
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
            
            # 意图模式
            intent_patterns = [
                (r'想(买|要|购买|入手|做|学|了解|知道)(.+?)(?=[。！？,.!?；：]|$)', 'intent'),
                (r'需要(.+?)(?=[。！？,.!?；：]|$)', 'need'),
                (r'希望(.+?)(?=[。！？,.!?；：]|$)', 'hope'),
            ]
            
            # 正向偏好模式
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好|想|要|爱|倾向于)(.+?)(?=[。！？,.!?；：]|$)', 'preference'),
                (r'比较(喜欢|想要|倾向|偏向)(.+?)(?=[。！？,.!?；：]|$)', 'comparative_preference'),
            ]
            
            # 处理意图模式
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
            
            # 身份模式
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


# ============================================================================
# LLMBasedExtractor - 基于 LLM 的提取
# ============================================================================

class LLMBasedExtractor(BaseExtractor):
    """
    基于LLM的知识提取器（推荐使用）
    
    ✨ 使用LLM的语义理解能力从对话中提取结构化知识
    📊 支持全部40种知识类型的智能提取
    
    相比规则提取，LLM提取器能够：
    1. ✅ 理解语义和上下文
    2. ✅ 识别隐含知识和意图
    3. ✅ 处理同义词和不同表达方式
    4. ✅ 自动分类到40种知识类型
    5. ✅ 更高的准确率和召回率
    """
    
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
        # 如果没有 LLM 客户端，回退到基于规则的提取
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
        """使用LLM提取知识"""
        system_prompt = """你是一个专业的知识提取助手。从对话中提取结构化知识信息。

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
只提取高价值信息，置信度需要>=0.70。"""
        
        user_prompt = f"""请从以下对话中提取结构化知识：

{conversation_text}

请返回JSON格式的提取结果。"""
        
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        
        try:
            if hasattr(self.llm_client, 'generate_async'):
                _, response = await self.llm_client.generate_async(full_prompt)
            elif hasattr(self.llm_client, 'generate'):
                _, response = self.llm_client.generate(full_prompt)
            else:
                raise ValueError("LLM客户端缺少generate或generate_async方法")
            
            return response
            
        except Exception as e:
            logger.error(f"[LLMBasedExtractor] LLM调用失败: {e}")
            raise
    
    def _parse_llm_response(self, llm_response: str, messages: List[Message]) -> List[Knowledge]:
        """解析LLM返回的JSON格式知识"""
        knowledge_list = []
        
        try:
            # 如果存在，从 markdown 代码块中提取 JSON
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
                        
                        # 验证检查
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
                        
                        # 生成嵌入向量
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


# ============================================================================
# ImportancePredictorExtractor - 重要性感知提取
# ============================================================================

class ImportancePredictorExtractor(BaseExtractor):
    """
    重要性感知提取器（未来实现的占位符）
    
    使用训练好的模型预测提取信息的长期重要性
    在存储前过滤低价值记忆
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
        """
        logger.debug("[ImportancePredictorExtractor] 使用回退到 RuleBasedExtractor（尚未实现）")
        
        fallback = RuleBasedExtractor(self.config)
        knowledge = await fallback.extract(messages)
        
        # 未来: 在此添加重要性预测评分
        
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
