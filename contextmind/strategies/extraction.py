"""
Extraction Strategies - 提取策略实现

提供多种知识提取策略，用于从对话中提取结构化知识。

v3.3更新：
- 支持可配置化设计
- 使用ExtractionConfig减少硬编码
"""

from typing import List, Optional
import re
import json

from ..core import Message, Knowledge, KnowledgeType
from .base import ExtractionStrategy
from ..utils import get_logger
from ..core import DEFAULT_MEMORY_CONFIG, ExtractionConfig

logger = get_logger(__name__)


class RuleBasedExtractionStrategy(ExtractionStrategy):
    """
    基于规则的提取策略
    
    使用预定义的规则和模式从对话中提取知识。
    """
    
    def __init__(self, config: Optional[ExtractionConfig] = None):
        """
        初始化基于规则的提取策略
        
        Args:
            config: 提取配置，如果为None则使用默认配置
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用规则提取知识
        
        Args:
            messages: 消息列表
            
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
        
        # 过滤低置信度的知识 - 降低阈值以提取更多
        before_filter = len(knowledge)
        knowledge = [k for k in knowledge if k.confidence >= self.CONFIDENCE_FILTER_MIN]
        filtered_count = before_filter - len(knowledge)
        
        if filtered_count > 0:
            logger.debug(f"[Extractor] 过滤低置信度知识: {filtered_count} 条 (阈值: {self.CONFIDENCE_FILTER_MIN})")
        
        logger.info(f"[Extractor] ✓ 知识提取完成 - 总计 {len(knowledge)} 条有效知识")
        
        if knowledge:
            logger.debug(f"[Extractor] 提取的知识详情:")
            for i, k in enumerate(knowledge[:5], 1):  # Show first 5
                logger.debug(f"  {i}. [{k.type.value}] {k.content[:60]}... (置信度: {k.confidence:.2f})")
            if len(knowledge) > 5:
                logger.debug(f"  ... 以及其他 {len(knowledge) - 5} 条知识")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好和关键策略，保留完整上下文
        
        优化：存储完整用户消息，提供更丰富的上下文信息。
        """
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content.strip()
            
            # 跳过过短的消息
            if len(content) < 2:
                continue
            
            # 正面偏好 - 提取明确的"我喜欢/我想要"等，保留完整句子
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好|想|要|爱)(.+?)(?=[。！？,.!?；：]|$)', 'positive'),
                (r'(想|要|愿意)(.+?)(?=[。！？,.!?；：]|$)', 'interest'),  # 更广泛的兴趣表达
            ]
            
            for pattern, sentiment in positive_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    phrase = match[1].strip()
                    
                    # 清理尾随标点
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    # 质量检查：长度合理（放宽要求），不以否定词开头
                    if (2 <= len(phrase) <= 100  # Minimum 2 chars instead of 1
                        and not phrase.startswith(('不', '没', '无'))
                        and phrase.strip()):
                        # 保留完整上下文
                        full_content = f"用户表示{keyword}{phrase}"
                        preferences.append(Knowledge(
                            content=full_content,
                            type=KnowledgeType.PREFERENCE,
                            confidence=self.CONFIDENCE_PREFERENCE_POSITIVE,
                            metadata={'sentiment': sentiment, 'keyword': keyword, 'category': '偏好'}
                        ))
            
            # 负面偏好/拒绝 - 提取完整的否定对象
            negative_patterns = [
                # 匹配：我不需要/不想/拒绝 + 名词短语
                (r'我?(不喜欢|不想|不要|拒绝|不需要|讨厌|反感)([^，。！？,!?；:：的了吗呢啊]{1,15})', 'negative'),
                (r'太(麻烦|贵|复杂|难)了?', 'negative'),  # 抱怨
            ]
            
            for pattern, sentiment in negative_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        keyword = match[0] if len(match) > 0 else ""
                        phrase = match[1].strip() if len(match) > 1 else match[0]
                    else:
                        keyword = ""
                        phrase = match
                    
                    # 清理尾随标点和连接词
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    phrase = re.sub(r'^[的了吗呢啊]+', '', phrase)
                    phrase = phrase.strip()
                    
                    # 质量检查 - 放宽要求
                    if (2 <= len(phrase) <= self.config.max_phrase_length  # Minimum 2 chars
                        and phrase.strip()):
                        content_str = f"{keyword}{phrase}" if keyword else phrase
                        preferences.append(Knowledge(
                            content=content_str,
                            type=KnowledgeType.PREFERENCE,
                            confidence=self.CONFIDENCE_PREFERENCE_NEGATIVE,
                            metadata={'sentiment': sentiment, 'keyword': keyword, 'category': '拒绝'}
                        ))
        
        return preferences
    
    def _extract_key_phrase(self, content: str, keyword: str) -> str:
        """从句子中提取包含关键词的关键短语"""
        # 分句
        sentences = re.split(r'[，。！？,.!?；;]', content)
        
        # 找到包含关键词的句子
        for sentence in sentences:
            if keyword in sentence:
                # 清理和简化
                cleaned = sentence.strip()
                # 移除冗余词汇
                for filler in ["我", "觉得", "感觉", "认为", "就是"]:
                    cleaned = cleaned.replace(filler, "")
                cleaned = cleaned.strip()
                if cleaned:
                    return cleaned
        
        return content[:30]  # 回退：返回前30个字符
    
    def _extract_facts(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户相关事实信息（用户属性），使用结构化格式存储
        
        只提取用户自身的属性信息，不提取业务流程或客服建议。
        """
        facts = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content
            
            # 用户属性提取 - 更广泛的模式
            fact_patterns = [
                (r'我(是|在|做)(.{2,20})(工作|职业|行业)', '职业'),
                (r'我(今年|已经)(.{1,3})(岁|周岁)', '年龄'),
                (r'我(住在|在|来自|是)(.{2,10})(人|地方|城市)', '位置'),
                (r'我是(.{2,10})人', '位置'),
                (r'我(喜欢|爱好|爱)(吃|玩|看|听|做)(.{2,15})', '爱好'),
                (r'我喜欢(.{2,15})', '爱好'),
                (r'我叫(.{2,8})', '姓名'),
                (r'我(有|没有)(.{2,15})(工作|收入|存款|房|车)', '经济状况'),
                (r'我(开|买了|有)(.{2,10})(车|房)', '资产'),
                # 新增：更多用户信息模式
                (r'我(.{1,5})(岁|年|周岁)', '年龄'),
                (r'(我的|我)(.{1,8})(号码|电话|手机|身份证)', '联系方式'),
                (r'我(学|毕业于|在)(.{2,15})(学校|大学|专业)', '教育'),
            ]
            
            for pattern, category in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # 提取关键部分
                    if isinstance(match, tuple):
                        # 根据不同模式提取相应部分
                        if category == '位置' and len(match) >= 2:
                            fact = match[1].strip()
                        elif category == '爱好' and len(match) >= 3:
                            fact = (match[1] + match[2]).strip() if len(match) > 2 else match[1].strip()
                        elif category == '年龄' and len(match) >= 1:
                            fact = match[0].strip() if len(match) == 1 else match[1].strip()
                        elif len(match) >= 2:
                            fact = match[1].strip()
                        else:
                            fact = match[0].strip() if match else ""
                    else:
                        fact = match.strip() if isinstance(match, str) else str(match)
                    
                    # 清理尾随标点
                    fact = re.sub(r'[，。！？,.!?；:：]+$', '', fact)
                    
                    # 质量检查 - 放宽要求
                    if (2 <= len(fact) <= self.config.max_phrase_length  # Minimum 2 chars
                        and fact.strip()):
                        facts.append(Knowledge(
                            content=f"{category}: {fact}",
                            type=KnowledgeType.FACT,
                            confidence=self.CONFIDENCE_FACT,
                            metadata={'category': category}
                        ))
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """提取关键事件和决策，使用结构化格式存储
        
        只提取用户的明确决策和意向，不提取客服的建议。
        """
        events = []
        
        for msg in messages:
            # 只提取用户消息中的决策
            if msg.role.value != "user":
                continue
                
            content = msg.content
            
            # 用户意向和决策 - 更宽泛的模式
            decision_patterns = [
                (r'(我要|我想|我需要|我打算|我决定|想|要|需要)([^，。！？,!?；:：吗呢啊]{2,20})', '意向'),
                (r'(同意|接受|确认|可以|好的|行|没问题)(申请|开通|办理|提升|使用|查询)?(.{0,10})', '确认'),
                (r'(查|办|申请|提升|开通)(.{0,15})', '操作意向'),  # 简单的动作意向
            ]
            
            for pattern, category in decision_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if isinstance(match, tuple):
                        keyword = match[0] if len(match) > 0 else ""
                        # 合并所有捕获组作为detail
                        if len(match) > 2:
                            detail = (match[1] + match[2]).strip()
                        else:
                            detail = match[1].strip() if len(match) > 1 else match[0]
                    else:
                        keyword = ""
                        detail = match
                    
                    # 如果detail为空或太短，使用原始匹配
                    if not detail or len(detail) < 1:
                        detail = keyword
                        keyword = ""
                    
                    # 清理尾随标点和连接词
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    detail = re.sub(r'^[的了吗呢啊]+', '', detail)
                    detail = detail.strip()
                    
                    # 质量检查 - 放宽要求
                    if (2 <= len(detail) <= self.config.max_phrase_length  # Minimum 2 chars
                        and detail.strip()):
                        content_str = f"{keyword}{detail}" if keyword else detail
                        events.append(Knowledge(
                            content=content_str,
                            type=KnowledgeType.EVENT,
                            confidence=self.CONFIDENCE_EVENT,
                            metadata={'keyword': keyword, 'category': category}
                        ))
        
        return events


class LLMExtractionStrategy(ExtractionStrategy):
    """
    基于LLM的提取策略
    
    使用大语言模型从对话中提取知识（预留接口）。
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        config: Optional[ExtractionConfig] = None,
    ):
        """
        初始化基于LLM的提取策略
        
        Args:
            llm_client: LLM客户端实例
            config: 提取配置，如果为None则使用默认配置
        """
        self.llm_client = llm_client
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
    
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
            fallback = RuleBasedExtractionStrategy(self.config)
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
                    
                    if confidence >= self.config.min_confidence:
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
            fallback = RuleBasedExtractionStrategy(self.config)
            return await fallback.extract(messages)
