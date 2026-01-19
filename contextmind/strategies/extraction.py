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
from ..core import get_logger
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
        knowledge = []
        
        # 提取偏好
        knowledge.extend(self._extract_preferences(messages))
        
        # 提取事实
        knowledge.extend(self._extract_facts(messages))
        
        # 提取事件
        knowledge.extend(self._extract_events(messages))
        
        # 过滤低置信度的知识
        knowledge = [k for k in knowledge if k.confidence >= self.config.min_confidence]
        
        logger.debug(f"RuleBasedExtraction: extracted {len(knowledge)} knowledge items")
        
        return knowledge
    
    def _extract_preferences(self, messages: List[Message]) -> List[Knowledge]:
        """提取用户偏好和关键策略，使用结构化格式存储
        
        只提取明确的用户偏好，严格过滤质量。
        """
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content
            
            # 正面偏好 - 只提取明确的"我喜欢/我想要"等
            positive_patterns = [
                (r'我(喜欢|想要|希望|需要|偏好)(.{2,20})', 'positive'),
            ]
            
            for pattern, sentiment in positive_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    phrase = match[1].strip()
                    
                    # 清理尾随标点
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    # 质量检查：长度合理，不以否定词开头
                    if (self.config.min_phrase_length <= len(phrase) <= self.config.max_phrase_length 
                        and not phrase.startswith(('不', '没', '无'))):
                        preferences.append(Knowledge(
                            content=f"{keyword}{phrase}",  # 简化格式，移除冗余标签
                            type=KnowledgeType.PREFERENCE,
                            confidence=self.config.preference_confidence,
                            metadata={'sentiment': sentiment, 'keyword': keyword, 'category': '偏好'}
                        ))
            
            # 负面偏好/拒绝 - 提取完整的否定对象
            negative_patterns = [
                # 匹配：我不需要/不想/拒绝 + 名词短语（不含问号）
                (r'我?(不喜欢|不想|不要|拒绝|不需要)([^，。！？,!?；:：的了吗呢啊]{2,15})', 'negative'),
            ]
            
            for pattern, sentiment in negative_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    phrase = match[1].strip()
                    
                    # 清理尾随标点和连接词
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    phrase = re.sub(r'^[的了吗呢啊]+', '', phrase)
                    phrase = phrase.strip()
                    
                    # 质量检查：
                    # 1. 长度合理
                    # 2. 不包含问号（避免"不需要小额贷款，可以有大额的吗"这样的提取）
                    # 3. 不是纯数字或符号
                    if (self.config.min_phrase_length <= len(phrase) <= self.config.max_phrase_length
                        and '吗' not in phrase and '?' not in phrase and not phrase.isdigit()):
                        preferences.append(Knowledge(
                            content=f"{keyword}{phrase}",  # 简化格式，移除冗余标签
                            type=KnowledgeType.PREFERENCE,
                            confidence=self.config.preference_confidence,
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
            
            # 用户属性提取 - 聚焦个人信息
            fact_patterns = [
                (r'我(是|在|做)(.{2,20})(工作|职业|行业)', '职业'),
                (r'我(今年|已经)(.{1,3})(岁|周岁)', '年龄'),
                (r'我(住在|在|来自|是)(.{2,10})(人|地方|城市)', '位置'),
                (r'我是(.{2,10})人', '位置'),  # "我是重庆人"
                (r'我(喜欢|爱好|爱)(吃|玩|看|听|做)(.{2,15})', '爱好'),
                (r'我喜欢(.{2,15})', '爱好'),  # 通用爱好提取
                (r'我叫(.{2,8})', '姓名'),
                (r'我(有|没有)(.{2,15})(工作|收入|存款|房|车)', '经济状况'),
                (r'我(开|买了|有)(.{2,10})(车|房)', '资产'),
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
                            # 合并动词和宾语
                            fact = (match[1] + match[2]).strip() if len(match) > 2 else match[1].strip()
                        elif len(match) >= 2:
                            fact = match[1].strip()
                        else:
                            fact = match[0].strip() if match else ""
                    else:
                        fact = match.strip() if isinstance(match, str) else str(match)
                    
                    # 清理尾随标点
                    fact = re.sub(r'[，。！？,.!?；:：]+$', '', fact)
                    
                    # 质量检查：长度合理，不是空白
                    if (self.config.min_phrase_length <= len(fact) <= self.config.max_phrase_length 
                        and fact.strip()):
                        facts.append(Knowledge(
                            content=f"{category}: {fact}",  # 简化格式
                            type=KnowledgeType.FACT,
                            confidence=self.config.fact_confidence,
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
            
            # 用户意向和决策
            decision_patterns = [
                (r'(我要|我想|我需要|我打算|我决定)([^，。！？,!?；:：吗呢啊]{3,20})', '意向'),
                # 注意：不提取单独的"同意"、"可以"、"好的"等短语，因为它们依赖上下文
                # 只在有明确对象时才提取
                (r'(同意|接受|确认)(申请|开通|办理|提升|使用)(.{0,10})', '确认'),
            ]
            
            for pattern, category in decision_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    # 合并所有捕获组作为detail
                    if len(match) > 2:
                        detail = (match[1] + match[2]).strip()
                    else:
                        detail = match[1].strip() if len(match) > 1 else ""
                    
                    # 如果detail为空、太短，或是疑问句，跳过
                    if not detail or len(detail) < 3:
                        continue
                    
                    # 清理尾随标点和连接词
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    detail = re.sub(r'^[的了吗呢啊]+', '', detail)
                    detail = detail.strip()
                    
                    # 质量检查：不包含问号（避免提取疑问句片段）
                    if (3 <= len(detail) <= self.config.max_phrase_length 
                        and '吗' not in detail and '?' not in detail):
                        events.append(Knowledge(
                            content=f"{keyword}{detail}",  # 简化格式
                            type=KnowledgeType.EVENT,
                            confidence=self.config.event_confidence,
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
