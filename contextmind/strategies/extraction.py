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
        """提取用户偏好和关键策略"""
        preferences = []
        
        for msg in messages:
            if msg.role.value != "user":
                continue
            
            content = msg.content
            
            # 喜欢的内容 - 提取更具体的偏好
            for word in ["喜欢", "想要", "希望", "需要", "偏好"]:
                if word in content:
                    # 提取关键信息而非整句
                    key_info = self._extract_key_phrase(content, word)
                    if key_info and len(key_info) > 3:  # 至少4个字符
                        preferences.append(Knowledge(
                            content=f"用户偏好: {key_info}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.8,
                            metadata={'sentiment': 'positive', 'keyword': word}
                        ))
                    break
            
            # 不喜欢的内容 - 提取拒绝策略
            for word in ["不喜欢", "不想", "不要", "拒绝", "不感兴趣"]:
                if word in content:
                    key_info = self._extract_key_phrase(content, word)
                    if key_info and len(key_info) > 3:
                        preferences.append(Knowledge(
                            content=f"用户拒绝策略: {key_info}",
                            type=KnowledgeType.PREFERENCE,
                            confidence=0.8,
                            metadata={'sentiment': 'negative', 'keyword': word}
                        ))
                    break
        
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
        """提取关键事实和用户信息"""
        facts = []
        
        fact_patterns = [
            (r'我是(.{2,15}[^，。！？,.!?]{0,5})', '身份'),
            (r'我叫(.{2,10})', '姓名'),
            (r'我的(.{2,20}[是：:].*?[，。！？,.!?])', '属性'),
            (r'我在(.{2,20}[市县区镇])', '位置'),
            (r'我(今年)?(\d+岁)', '年龄'),
        ]
        
        for msg in messages:
            if msg.role.value != "user":
                continue
                
            content = msg.content
            
            for pattern, category in fact_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    # 处理可能的tuple（从带多个捕获组的pattern）
                    if isinstance(match, tuple):
                        match = ''.join(match)
                    
                    # 清理匹配结果
                    cleaned = match.strip()
                    # 移除尾随的标点
                    cleaned = re.sub(r'[，。！？,.!?；:：]+$', '', cleaned)
                    
                    # 至少2个字符且不超过30个字符
                    if 2 <= len(cleaned) <= 30:
                        facts.append(Knowledge(
                            content=f"{category}: {cleaned}",
                            type=KnowledgeType.FACT,
                            confidence=0.75,
                            metadata={'category': category}
                        ))
        
        return facts
    
    def _extract_events(self, messages: List[Message]) -> List[Knowledge]:
        """提取关键事件和重要决策"""
        events = []
        
        # 重要事件关键词
        event_keywords = {
            "投诉": 0.9,
            "申请": 0.8,
            "办理": 0.75,
            "开通": 0.75,
            "取消": 0.8,
            "同意": 0.85,
            "确认": 0.75,
            "拒绝": 0.85,
            "接受": 0.8,
        }
        
        for msg in messages:
            content = msg.content
            
            # 检查是否包含关键事件词
            for keyword, confidence in event_keywords.items():
                if keyword in content:
                    # 提取包含关键词的短语而非整句
                    key_phrase = self._extract_key_phrase(content, keyword)
                    if key_phrase and len(key_phrase) > 3:
                        events.append(Knowledge(
                            content=f"关键决策: {key_phrase}",
                            type=KnowledgeType.EVENT,
                            confidence=confidence,
                            metadata={'keyword': keyword, 'source_role': msg.role.value}
                        ))
                    break  # 每条消息只提取一个事件
        
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
