"""
Intent Extractor - 意图提取器（基线版本）

从对话历史中提取用户意图，不依赖外部框架。
"""

from __future__ import annotations

from typing import List, Dict
from dataclasses import dataclass, field
import re


@dataclass
class Message:
    """简化的消息数据结构"""
    role: str  # "user" or "assistant"
    content: str
    
    
@dataclass
class ExtractedIntent:
    """
    提取的意图信息
    
    Attributes:
        intent_type: 意图类型
        description: 意图描述
        confidence: 置信度 (0-1)
        metadata: 其他元数据
    """
    intent_type: str
    description: str
    confidence: float = 1.0
    metadata: Dict = field(default_factory=dict)


class IntentExtractor:
    """
    意图提取器（基于规则）
    
    从对话历史中提取用户意图，支持：
    - 问答意图识别
    - 任务请求识别
    - 情感表达识别
    - 主题识别
    """
    
    def __init__(self):
        """初始化意图提取器"""
        # 意图识别关键词
        self.question_keywords = ['什么', '怎么', '如何', '为什么', '哪里', '谁', '吗', '？', '?']
        self.task_keywords = ['帮我', '请', '能否', '可以', '想要', '需要', '希望']
        self.greeting_keywords = ['你好', '您好', 'hello', 'hi', '早上好', '晚上好']
        self.emotion_keywords = {
            'positive': ['开心', '高兴', '喜欢', '太好了', '棒', '赞'],
            'negative': ['难过', '失望', '不喜欢', '糟糕', '烦', '郁闷'],
            'neutral': ['好的', '知道了', '明白', '了解']
        }
    
    async def extract_intent(
        self,
        messages: List[Message],
        focus_recent: int = 5
    ) -> ExtractedIntent:
        """
        从消息历史中提取意图
        
        Args:
            messages: 对话消息列表
            focus_recent: 重点关注最近N条消息
            
        Returns:
            提取的意图信息
        """
        if not messages:
            return ExtractedIntent(
                intent_type="general_chat",
                description="一般对话",
                confidence=0.5
            )
        
        # 重点分析最近的消息
        recent_messages = messages[-focus_recent:] if len(messages) > focus_recent else messages
        
        # 只分析用户消息
        user_messages = [msg for msg in recent_messages if msg.role == "user"]
        
        if not user_messages:
            return ExtractedIntent(
                intent_type="general_chat",
                description="一般对话",
                confidence=0.5
            )
        
        # 获取最新的用户消息
        latest_user_msg = user_messages[-1].content
        
        # 意图识别
        intent_type, description, confidence = self._classify_intent(latest_user_msg)
        
        return ExtractedIntent(
            intent_type=intent_type,
            description=description,
            confidence=confidence,
            metadata={
                'analyzed_messages': len(user_messages),
                'latest_message': latest_user_msg[:50]
            }
        )
    
    def _classify_intent(self, text: str) -> tuple[str, str, float]:
        """
        分类意图
        
        Returns:
            (intent_type, description, confidence)
        """
        # 1. 问候
        if any(keyword in text for keyword in self.greeting_keywords):
            return "greeting", "用户打招呼", 0.9
        
        # 2. 问题/查询
        if any(keyword in text for keyword in self.question_keywords):
            return "question", "用户提出问题或查询信息", 0.85
        
        # 3. 任务请求
        if any(keyword in text for keyword in self.task_keywords):
            return "task_request", "用户请求帮助完成任务", 0.85
        
        # 4. 情感表达
        for emotion, keywords in self.emotion_keywords.items():
            if any(keyword in text for keyword in keywords):
                return f"emotion_{emotion}", f"用户表达{emotion}情感", 0.8
        
        # 5. 默认：一般对话
        return "general_chat", "一般对话交流", 0.6
    
    async def extract_topic(self, messages: List[Message], focus_recent: int = 10) -> str:
        """
        提取对话主题
        
        Args:
            messages: 对话消息列表
            focus_recent: 重点关注最近N条消息
            
        Returns:
            主题描述
        """
        if not messages:
            return "未识别"
        
        # 重点分析最近的消息
        recent_messages = messages[-focus_recent:] if len(messages) > focus_recent else messages
        
        # 提取用户消息
        user_messages = [msg for msg in recent_messages if msg.role == "user"]
        
        if not user_messages:
            return "未识别"
        
        # 简单实现：提取最新消息的关键词
        latest_msg = user_messages[-1].content
        
        # 移除标点符号，提取关键词
        words = re.findall(r'[\u4e00-\u9fa5a-zA-Z0-9]+', latest_msg)
        
        if len(words) > 3:
            # 取前3-5个词作为主题
            topic = ' '.join(words[:min(5, len(words))])
            return topic
        elif words:
            return ' '.join(words)
        
        return "一般对话"
    
    async def extract_context_summary(
        self,
        messages: List[Message],
        max_length: int = 200
    ) -> str:
        """
        提取上下文摘要
        
        Args:
            messages: 对话消息列表
            max_length: 最大摘要长度
            
        Returns:
            上下文摘要
        """
        if not messages:
            return "暂无上下文"
        
        # 简单实现：总结最近几轮对话
        recent_messages = messages[-4:] if len(messages) > 4 else messages
        
        summary_parts = []
        for msg in recent_messages:
            role_name = "用户" if msg.role == "user" else "助手"
            content_preview = msg.content[:30] + "..." if len(msg.content) > 30 else msg.content
            summary_parts.append(f"{role_name}: {content_preview}")
        
        summary = "; ".join(summary_parts)
        
        # 限制长度
        if len(summary) > max_length:
            summary = summary[:max_length] + "..."
        
        return summary


__all__ = [
    'Message',
    'ExtractedIntent',
    'IntentExtractor',
]
