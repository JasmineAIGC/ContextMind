"""
ContextFormatter - 上下文格式化工具

提供标准化的上下文信息格式化和打印功能。
将 Debug 日志格式化逻辑从业务代码中解耦，确保输出格式的一致性。

设计原则：
- 单一职责：只负责格式化和打印上下文信息
- 格式统一：所有输出使用统一的格式规范
- 易于扩展：新增格式化需求只需添加新方法
"""

from typing import List, Optional, TYPE_CHECKING
from ..logger import get_logger

if TYPE_CHECKING:
    from ..data_models import ContextResult, ContextItem, Message

logger = get_logger(__name__)

# ============================================================================
# 格式化常量 - 可配置的显示文本
# ============================================================================

# 布局常量
BOX_WIDTH = 100
BORDER_CHAR = "="
SECTION_CHAR = "-"
MIN_BOX_WIDTH = 40

# 日志前缀常量
LOG_PREFIX_PROCESS = "[处理对话]"
LOG_PREFIX_COMPLETE = "[处理完成]"
LOG_PREFIX_OPTIMIZE = "[上下文优化]"
LOG_PREFIX_MEMORY = "[长期记忆]"
LOG_PREFIX_PROMPT = "[Prompt构建]"

# 标题文本常量
TITLE_CONTEXT_RESULT = "【上下文优化结果】Context Optimization Result"
TITLE_MEMORY_DB = "【长期记忆数据库】"
TITLE_PROMPT_ANALYSIS = "【Prompt构成分析】Prompt Composition Analysis"
TITLE_COMPLETE_PROMPT = "【完整Prompt】Complete Prompt Sent to LLM"

# 说明文本常量
DESC_CONTEXT_RESULT = "说明：ContextMind 从多源收集并优化后的上下文信息"
DESC_PROMPT_ANALYSIS = "说明：发送给LLM的Prompt统计分析"
DESC_COMPLETE_PROMPT = "说明：发送给大语言模型的完整提示词"


class ContextFormatter:
    """
    上下文格式化器
    
    提供统一的上下文信息格式化方法，确保Debug输出的标准化和规范化。
    
    使用示例：
        ```python
        formatter = ContextFormatter()
        formatter.format_context_result(context_result)
        formatter.format_memory_cache(memory_cache)
        ```
    """
    
    def __init__(self, box_width: int = BOX_WIDTH):
        """
        初始化格式化器
        
        Args:
            box_width: 输出框的宽度（字符数），最小为 MIN_BOX_WIDTH
        """
        if box_width < MIN_BOX_WIDTH:
            box_width = MIN_BOX_WIDTH
        self.box_width = box_width
    
    def _format_box_header(self, title: str, subtitle: str = "") -> List[str]:
        """
        格式化标题框
        
        Args:
            title: 主标题
            subtitle: 副标题（说明文字）
            
        Returns:
            格式化的行列表
        """
        lines = [
            "",
            "╔" + BORDER_CHAR * (self.box_width - 2) + "╗",
            "║" + title.center(self.box_width - 2) + "║",
        ]
        if subtitle:
            lines.append("║" + subtitle.center(self.box_width - 2) + "║")
        lines.append("╚" + BORDER_CHAR * (self.box_width - 2) + "╝")
        return lines
    
    def _format_section(self, title: str) -> str:
        """格式化节标题"""
        return f"\n【{title}】"
    
    def _format_stat_line(self, label: str, value: str) -> str:
        """格式化统计行"""
        return f"  - {label}: {value}"
    
    def _format_item_line(self, index: int, content: str, extra: str = "") -> str:
        """格式化条目行"""
        if extra:
            return f"  {index}. {content} ({extra})"
        return f"  {index}. {content}"
    
    def format_context_result(self, context_result: "ContextResult") -> str:
        """
        格式化上下文优化结果
        
        Args:
            context_result: 上下文结果对象
            
        Returns:
            格式化的字符串
        """
        lines = []
        
        # 标题 - 使用常量
        lines.extend(self._format_box_header(
            TITLE_CONTEXT_RESULT,
            DESC_CONTEXT_RESULT
        ))
        
        # 统计信息
        lines.append(self._format_section("统计信息"))
        lines.append(self._format_stat_line("近期对话", f"{len(context_result.recent_history)} 条消息"))
        lines.append(self._format_stat_line("长期记忆", f"{len(context_result.long_term_memory)} 项"))
        lines.append(self._format_stat_line("外部知识", f"{len(context_result.external_knowledge)} 项"))
        
        # 对话历史
        lines.append(self._format_section("对话历史"))
        if context_result.recent_history:
            lines.append(f"  共 {len(context_result.recent_history)} 条消息")
            for i, msg in enumerate(context_result.recent_history, 1):
                lines.append(self._format_item_line(i, f"{msg.role.value}: {msg.content}"))
        else:
            lines.append("  (无历史对话)")
        
        # 长期记忆
        lines.append(self._format_section("长期记忆"))
        if context_result.long_term_memory:
            lines.append(f"  共 {len(context_result.long_term_memory)} 项记忆")
            for i, item in enumerate(context_result.long_term_memory, 1):
                lines.append(self._format_item_line(i, item.content, f"相关性: {item.score:.2f}"))
        else:
            lines.append("  (无相关记忆)")
        
        # 外部知识
        lines.append(self._format_section("外部知识"))
        if context_result.external_knowledge:
            lines.append(f"  共 {len(context_result.external_knowledge)} 项知识")
            for i, item in enumerate(context_result.external_knowledge, 1):
                lines.append(self._format_item_line(i, item.content))
        else:
            lines.append("  (无外部知识)")
        
        lines.append("")
        return "\n".join(lines)
    
    def format_memory_cache(self, memory_cache: List["ContextItem"]) -> str:
        """
        格式化长期记忆数据库内容
        
        Args:
            memory_cache: 记忆缓存列表
            
        Returns:
            格式化的字符串
        """
        lines = []
        
        lines.append(self._format_section("长期记忆数据库"))
        lines.append(f"  共 {len(memory_cache)} 条记忆")
        lines.append("  说明: 从对话历史中提取的知识、经验、策略等信息")
        
        if memory_cache:
            lines.append("")
            lines.append("  记忆库内容：")
            for i, item in enumerate(memory_cache, 1):
                source_name = item.source.value if item.source else 'unknown'
                lines.append(f"  {i}. [{source_name}] {item.content}")
        else:
            lines.append("  记忆库为空")
            lines.append("  提示: 启用 auto_extract_knowledge=True 自动提取知识")
        
        lines.append("")
        return "\n".join(lines)
    
    def format_prompt_analysis(self, prompt: str, context_result: "ContextResult") -> str:
        """
        格式化Prompt构成分析
        
        Args:
            prompt: 完整的Prompt
            context_result: 上下文结果
            
        Returns:
            格式化的字符串
        """
        lines = []
        
        # Prompt分析标题 - 使用常量
        lines.extend(self._format_box_header(
            TITLE_PROMPT_ANALYSIS,
            DESC_PROMPT_ANALYSIS
        ))
        
        # 统计信息
        lines.append(self._format_stat_line("总字符数", str(len(prompt))))
        has_history = "是" if context_result.recent_history else "否"
        if context_result.recent_history:
            has_history += f" ({len(context_result.recent_history)} 轮)"
        lines.append(self._format_stat_line("包含对话历史", has_history))
        
        has_memory = "是" if context_result.long_term_memory else "否"
        if context_result.long_term_memory:
            has_memory += f" ({len(context_result.long_term_memory)} 项)"
        lines.append(self._format_stat_line("包含长期记忆", has_memory))
        
        lines.append("")
        return "\n".join(lines)
    
    def format_complete_prompt(self, prompt: str) -> str:
        """
        格式化完整Prompt
        
        Args:
            prompt: 完整的Prompt
            
        Returns:
            格式化的字符串
        """
        lines = []
        
        # 标题 - 使用常量
        lines.extend(self._format_box_header(
            TITLE_COMPLETE_PROMPT,
            DESC_COMPLETE_PROMPT
        ))
        lines.append("")
        lines.append(prompt)
        lines.append("")
        
        return "\n".join(lines)


# 全局格式化器实例
_formatter = ContextFormatter()


def format_context_result(context_result: "ContextResult") -> str:
    """格式化上下文结果的便捷函数"""
    return _formatter.format_context_result(context_result)


def format_memory_cache(memory_cache: List["ContextItem"]) -> str:
    """格式化记忆缓存的便捷函数"""
    return _formatter.format_memory_cache(memory_cache)


def format_prompt_analysis(prompt: str, context_result: "ContextResult") -> str:
    """格式化Prompt分析的便捷函数"""
    return _formatter.format_prompt_analysis(prompt, context_result)


def format_complete_prompt(prompt: str) -> str:
    """格式化完整Prompt的便捷函数"""
    return _formatter.format_complete_prompt(prompt)


# === Visualization (merged from visualizer.py) ===


from typing import List, Optional
from ..data_models import ContextResult, Message, ContextItem


class ContextVisualizer:
    