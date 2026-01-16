"""
ContextTextBuilder - 统一的上下文文本构建工具

提供统一的接口来构建各种上下文文本，消除适配器间的重复代码。
所有适配器和格式化器都应使用此工具类来构建文本。

设计原则：
- 单一职责：专注于文本构建，不包含业务逻辑
- 格式统一：提供标准化的文本格式
- 易于扩展：支持自定义格式化策略
"""

from typing import List, Optional
from ..data_models import ContextResult, ContextItem, Message


class ContextTextBuilder:
    """
    上下文文本构建器
    
    提供统一的方法将上下文数据结构转换为格式化文本。
    用于适配器、格式化器等需要将上下文转换为文本的场景。
    """
    
    @staticmethod
    def build_memory_text(
        memory_items: List[ContextItem],
        include_score: bool = True,
        score_threshold: float = 1.0
    ) -> str:
        """
        构建长期记忆的文本表示
        
        Args:
            memory_items: 记忆条目列表
            include_score: 是否包含相关性分数
            score_threshold: 分数阈值，低于此值显示分数
            
        Returns:
            格式化的长期记忆文本
        """
        if not memory_items:
            return ""
        
        lines = []
        for item in memory_items:
            # 根据分数决定是否显示
            if include_score and item.score < score_threshold:
                lines.append(f"- {item.content} (相关性: {item.score:.1%})")
            else:
                lines.append(f"- {item.content}")
        
        return "\n".join(lines)
    
    @staticmethod
    def build_knowledge_text(knowledge_items: List[ContextItem]) -> str:
        """
        构建外部知识的文本表示
        
        Args:
            knowledge_items: 知识条目列表
            
        Returns:
            格式化的外部知识文本
        """
        if not knowledge_items:
            return ""
        
        lines = []
        for item in knowledge_items:
            lines.append(f"- {item.content}")
        
        return "\n".join(lines)
    
    @staticmethod
    def build_messages_text(
        messages: List[Message],
        format_style: str = "simple"
    ) -> str:
        """
        构建消息列表的文本表示
        
        Args:
            messages: 消息列表
            format_style: 格式风格 ("simple", "detailed", "langchain")
            
        Returns:
            格式化的消息文本
        """
        if not messages:
            return ""
        
        lines = []
        
        if format_style == "simple":
            for msg in messages:
                lines.append(f"{msg.role.value}: {msg.content}")
        
        elif format_style == "detailed":
            for msg in messages:
                timestamp = msg.timestamp.strftime("%H:%M:%S") if msg.timestamp else "N/A"
                lines.append(f"[{timestamp}] {msg.role.value}: {msg.content}")
        
        elif format_style == "langchain":
            for msg in messages:
                lines.append(f"{msg.role.value.capitalize()}: {msg.content}")
        
        else:
            # 默认使用简单格式
            for msg in messages:
                lines.append(f"{msg.role.value}: {msg.content}")
        
        return "\n".join(lines)
    
    @staticmethod
    def build_context_summary(context_result: ContextResult) -> str:
        """
        构建上下文结果的摘要文本
        
        Args:
            context_result: 上下文优化结果
            
        Returns:
            摘要文本
        """
        parts = []
        
        # 统计信息
        parts.append(f"最近对话: {len(context_result.recent_history)} 条")
        parts.append(f"长期记忆: {len(context_result.long_term_memory)} 条")
        parts.append(f"外部知识: {len(context_result.external_knowledge)} 条")
        
        return " | ".join(parts)
    
    @staticmethod
    def build_enhanced_system_prompt(
        base_prompt: str,
        memory_text: str = "",
        knowledge_text: str = ""
    ) -> str:
        """
        构建增强的系统提示
        
        将基础提示与长期记忆、外部知识整合。
        
        Args:
            base_prompt: 基础系统提示
            memory_text: 长期记忆文本
            knowledge_text: 外部知识文本
            
        Returns:
            增强后的系统提示
        """
        parts = []
        
        # 基础系统提示
        if base_prompt:
            parts.append(base_prompt)
        
        # 长期记忆
        if memory_text:
            parts.append(f"\n## 用户相关信息（长期记忆）\n{memory_text}")
        
        # 外部知识
        if knowledge_text:
            parts.append(f"\n## 相关知识\n{knowledge_text}")
        
        return "\n".join(parts)
    
    @staticmethod
    def build_context_items_text(
        items: List[ContextItem],
        group_by_source: bool = False
    ) -> str:
        """
        构建上下文条目列表的文本表示
        
        Args:
            items: 上下文条目列表
            group_by_source: 是否按来源分组显示
            
        Returns:
            格式化的上下文条目文本
        """
        if not items:
            return ""
        
        if not group_by_source:
            # 简单列表
            lines = []
            for item in items:
                lines.append(f"- [{item.source.value}] {item.content}")
            return "\n".join(lines)
        else:
            # 按来源分组
            from collections import defaultdict
            grouped = defaultdict(list)
            for item in items:
                grouped[item.source].append(item)
            
            lines = []
            for source, source_items in grouped.items():
                lines.append(f"\n{source.value.upper()}:")
                for item in source_items:
                    lines.append(f"  - {item.content}")
            
            return "\n".join(lines)
