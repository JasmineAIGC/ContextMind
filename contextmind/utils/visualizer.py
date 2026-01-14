"""
ContextVisualizer - 上下文可视化工具

提供上下文的可视化展示功能。
"""

from typing import List, Optional
from ..data_models import ContextResult, Message, ContextItem


class ContextVisualizer:
    """
    上下文可视化器
    
    提供多种格式的上下文可视化输出。
    """
    
    @staticmethod
    def render_text(context_result: ContextResult, max_width: int = 80) -> str:
        """
        渲染文本格式的上下文
        
        Args:
            context_result: 上下文结果
            max_width: 最大宽度
            
        Returns:
            格式化的文本字符串
        """
        lines = []
        separator = "=" * max_width
        
        lines.append(separator)
        lines.append("CONTEXT VISUALIZATION".center(max_width))
        lines.append(separator)
        
        # 历史消息
        if context_result.recent_history:
            lines.append("\n📜 Recent History:")
            lines.append("-" * max_width)
            for i, msg in enumerate(context_result.recent_history, 1):
                role_prefix = f"{msg.role.value.upper()}:"
                lines.append(f"  {i}. {role_prefix:12} {msg.content}")
        
        # 长期记忆
        if context_result.long_term_memory:
            lines.append("\n🧠 Long-term Memory:")
            lines.append("-" * max_width)
            for i, item in enumerate(context_result.long_term_memory, 1):
                score = f"(score: {item.score:.2f})"
                lines.append(f"  {i}. {item.content} {score}")
        
        # 外部知识
        if context_result.external_knowledge:
            lines.append("\n📚 External Knowledge:")
            lines.append("-" * max_width)
            for i, item in enumerate(context_result.external_knowledge, 1):
                lines.append(f"  {i}. {item.content}")
        
        # 元数据
        if context_result.metadata:
            lines.append("\n🏷️  Metadata:")
            lines.append("-" * max_width)
            for key, value in context_result.metadata.items():
                lines.append(f"  {key}: {value}")
        
        lines.append(separator)
        
        return "\n".join(lines)
    
    @staticmethod
    def render_json(context_result: ContextResult) -> dict:
        """
        渲染JSON格式的上下文
        
        Args:
            context_result: 上下文结果
            
        Returns:
            JSON格式的字典
        """
        return context_result.to_dict()
    
    @staticmethod
    def render_markdown(context_result: ContextResult) -> str:
        """
        渲染Markdown格式的上下文
        
        Args:
            context_result: 上下文结果
            
        Returns:
            Markdown格式的字符串
        """
        lines = []
        
        lines.append("# Context Visualization\n")
        
        # 历史消息
        if context_result.recent_history:
            lines.append("## 📜 Recent History\n")
            for i, msg in enumerate(context_result.recent_history, 1):
                lines.append(f"{i}. **{msg.role.value.upper()}**: {msg.content}")
            lines.append("")
        
        # 长期记忆
        if context_result.long_term_memory:
            lines.append("## 🧠 Long-term Memory\n")
            for i, item in enumerate(context_result.long_term_memory, 1):
                lines.append(f"{i}. {item.content} _(score: {item.score:.2f})_")
            lines.append("")
        
        # 外部知识
        if context_result.external_knowledge:
            lines.append("## 📚 External Knowledge\n")
            for i, item in enumerate(context_result.external_knowledge, 1):
                lines.append(f"{i}. {item.content}")
            lines.append("")
        
        # 元数据
        if context_result.metadata:
            lines.append("## 🏷️ Metadata\n")
            lines.append("```json")
            import json
            lines.append(json.dumps(context_result.metadata, indent=2, ensure_ascii=False))
            lines.append("```\n")
        
        return "\n".join(lines)
    
    @staticmethod
    def render_summary(context_result: ContextResult) -> str:
        """
        渲染摘要信息
        
        Args:
            context_result: 上下文结果
            
        Returns:
            摘要字符串
        """
        summary_parts = []
        
        history_count = len(context_result.recent_history)
        memory_count = len(context_result.long_term_memory)
        knowledge_count = len(context_result.external_knowledge)
        
        summary_parts.append(f"📊 Context Summary:")
        summary_parts.append(f"  - History: {history_count} messages")
        summary_parts.append(f"  - Memory: {memory_count} items")
        summary_parts.append(f"  - Knowledge: {knowledge_count} items")
        
        # 计算总字符数
        total_chars = sum(len(msg.content) for msg in context_result.recent_history)
        total_chars += sum(len(item.content) for item in context_result.long_term_memory)
        total_chars += sum(len(item.content) for item in context_result.external_knowledge)
        
        summary_parts.append(f"  - Total characters: {total_chars}")
        
        return "\n".join(summary_parts)
