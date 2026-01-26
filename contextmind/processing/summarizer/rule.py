"""
RuleBasedSummarizer - 基于规则的摘要器

使用统计信息和关键词提取生成摘要
轻量级, 适合快速摘要
"""

from typing import List, Optional, Any

from ...core.models import Message, MessageRole, get_logger
from .base import SummarizerStrategy, SummarizationConfig

logger = get_logger(__name__)


class RuleBasedSummarizer(SummarizerStrategy):
    """
    基于规则的摘要器
    
    使用统计信息和关键词提取生成摘要
    轻量级, 适合快速摘要
    
    ⚠️ 已弃用：推荐使用 LLMBasedSummarizer 以获得更好的摘要质量
    """
    
    def __init__(self, config: Optional[Any] = None):
        """
        初始化规则摘要器
        
        Args:
            config: 配置，可以是 SummarizationConfig 或字典，可包含:
                - max_topics: 最多提取的话题数
                - topic_length: 每个话题的最大长度
                - include_stats: 是否包含统计信息
        """
        # 支持 SummarizationConfig 或 dict
        if isinstance(config, SummarizationConfig):
            self.max_topics = config.max_topics
            self.topic_length = config.topic_length
            self.include_stats = config.include_stats
            self.max_summary_length = config.max_summary_length
            self.extract_key_points = config.extract_key_points
        else:
            self.config = config or {}
            self.max_topics = self.config.get('max_topics', 5)
            self.topic_length = self.config.get('topic_length', 50)
            self.include_stats = self.config.get('include_stats', True)
            self.max_summary_length = self.config.get('max_summary_length', 200)
            self.extract_key_points = self.config.get('extract_key_points', True)
    
    async def summarize(
        self,
        messages: List[Message],
        existing_summary: Optional[str] = None
    ) -> str:
        """生成基于规则的摘要"""
        if not messages:
            return "暂无对话历史"
        
        summary_parts = []
        
        # 统计信息
        if self.include_stats:
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            assistant_msgs = [m for m in messages if m.role == MessageRole.ASSISTANT]
            
            summary_parts.append(f"对话轮次: {len(messages) // 2} 轮")
        
        # 提取关键点（如果启用）
        if self.extract_key_points:
            key_points = []
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            
            for msg in user_msgs:
                content = msg.content
                
                # 跳过太短的对话
                if len(content) < 10:
                    continue
                
                # 自我介绍相关
                if any(keyword in content for keyword in ["我是", "我叫", "我的", "我在"]):
                    key_points.append(content.strip())
                
                # 偏好相关
                elif any(keyword in content for keyword in ["喜欢", "不喜欢", "偏好", "想要", "需要", "希望"]):
                    key_points.append(content.strip())
                
                # 事实陈述
                elif any(keyword in content for keyword in ["是", "有", "没有", "已经", "正在"]):
                    key_points.append(content.strip())
            
            # 去重并限制数量
            seen = set()
            unique_points = []
            for point in key_points:
                # 简单的去重：检查前30个字符
                key = point[:30]
                if key not in seen:
                    seen.add(key)
                    unique_points.append(point)
            
            # 添加关键点
            if unique_points:
                for i, point in enumerate(unique_points[:8], 1):  # 最多8个要点
                    if len(point) > 50:
                        point = point[:50] + "..."
                    summary_parts.append(f"{i}. {point}")
        
        # 提取最近话题（原有逻辑）
        if not self.extract_key_points:
            user_msgs = [m for m in messages if m.role == MessageRole.USER]
            if user_msgs:
                recent_topics = []
                for msg in user_msgs[-self.max_topics:]:
                    if len(msg.content) > 0:
                        topic = msg.content[:self.topic_length]
                        if len(msg.content) > self.topic_length:
                            topic += "..."
                        recent_topics.append(topic)
                
                if recent_topics:
                    summary_parts.append(f"\n主要话题:")
                    for i, topic in enumerate(recent_topics, 1):
                        summary_parts.append(f"  {i}. {topic}")
        
        # 合并已有摘要 (如果是增量更新)
        if existing_summary:
            summary_parts.append(f"\n[历史摘要]: {existing_summary}")
        
        summary = "\n".join(summary_parts) if summary_parts else "暂无对话历史"
        
        # 截断过长的摘要
        if len(summary) > self.max_summary_length:
            summary = summary[:self.max_summary_length] + "..."
        
        return summary
