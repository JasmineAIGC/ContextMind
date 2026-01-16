"""
Extraction Strategies - 提取策略实现

提供多种知识提取策略，用于从对话中提取结构化知识。
"""

from typing import List, Optional
import re
import json

from ..data_models import Message, Knowledge, KnowledgeType
from .base import ExtractionStrategy
from ..logger import get_logger

logger = get_logger(__name__)


class RuleBasedExtractionStrategy(ExtractionStrategy):
    """
    基于规则的提取策略
    
    使用预定义的规则和模式从对话中提取知识。
    """
    
    def __init__(self, min_confidence: float = 0.5):
        """
        初始化基于规则的提取策略
        
        Args:
            min_confidence: 最小置信度阈值
        """
        self.min_confidence = min_confidence
    
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
        knowledge = [k for k in knowledge if k.confidence >= self.min_confidence]
        
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
                    if 2 <= len(phrase) <= 20 and not phrase.startswith(('不', '没', '无')):
                        preferences.append(Knowledge(
                            content=f"[偏好] {keyword}: {phrase}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.85,
                            metadata={'sentiment': sentiment, 'keyword': keyword}
                        ))
            
            # 负面偏好/拒绝
            negative_patterns = [
                (r'我?(不喜欢|不想|不要|拒绝|不需要)(.{2,20})', 'negative'),
            ]
            
            for pattern, sentiment in negative_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    phrase = match[1].strip()
                    
                    # 清理尾随标点
                    phrase = re.sub(r'[，。！？,.!?；:：]+$', '', phrase)
                    
                    # 质量检查
                    if 2 <= len(phrase) <= 20:
                        preferences.append(Knowledge(
                            content=f"[拒绝] {keyword}: {phrase}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.85,
                            metadata={'sentiment': sentiment, 'keyword': keyword}
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
                (r'我(住在|在|来自)(.{2,10})', '位置'),
                (r'我是(.{2,15})', '身份'),
                (r'我叫(.{2,8})', '姓名'),
                (r'我(有|没有)(.{2,15})(工作|收入|存款)', '经济状况'),
            ]
            
            for pattern, category in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # 提取关键部分
                    if isinstance(match, tuple) and len(match) >= 2:
                        fact = match[1].strip() if len(match) > 1 else str(match[0]).strip()
                    else:
                        fact = match.strip() if isinstance(match, str) else str(match)
                    
                    # 清理尾随标点
                    fact = re.sub(r'[，。！？,.!?；:：]+$', '', fact)
                    
                    # 质量检查：长度合理，不是空白
                    if 2 <= len(fact) <= 20 and fact.strip():
                        facts.append(Knowledge(
                            content=f"[事实] {category}: {fact}",
                            type=KnowledgeType.FACT,
                            confidence=0.75,
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
                (r'(我要|我想|我需要|我打算|我决定)(.{2,20})', '意向'),
                (r'(同意|接受|确认|好的|可以)(.{0,15})', '确认'),
                (r'(拒绝|不要|不想|不需要)(.{2,15})', '拒绝'),
            ]
            
            for pattern, category in decision_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    keyword = match[0]
                    detail = match[1].strip() if len(match) > 1 else ""
                    
                    # 如果detail为空或太短，跳过
                    if not detail or len(detail) < 2:
                        continue
                    
                    # 清理尾随标点
                    detail = re.sub(r'[，。！？,.!?；:：]+$', '', detail)
                    
                    # 质量检查
                    if 2 <= len(detail) <= 20:
                        events.append(Knowledge(
                            content=f"[决策] {keyword}: {detail}",
                            type=KnowledgeType.EVENT,
                            confidence=0.70,
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
        min_confidence: float = 0.5,
    ):
        """
        初始化基于LLM的提取策略
        
        Args:
            llm_client: LLM客户端实例
            min_confidence: 最小置信度阈值
        """
        self.llm_client = llm_client
        self.min_confidence = min_confidence
    
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
            fallback = RuleBasedExtractionStrategy(self.min_confidence)
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
                    
                    if confidence >= self.min_confidence:
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
            fallback = RuleBasedExtractionStrategy(self.min_confidence)
            return await fallback.extract(messages)
