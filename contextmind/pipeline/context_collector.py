"""
ContextCollector - 上下文收集器

从不同来源收集相关的上下文信息，包括会话历史、长期记忆和外部知识。
"""

from typing import Optional

from ..data_models import ProcessedContext, ContextItem, ContextSource, Message
from ..managers import SessionManager, MemoryManager
from ..logger import get_logger

logger = get_logger(__name__)


class ContextCollector:
    """
    上下文收集器
    
    负责从多个来源收集上下文信息：
    - 会话历史（短期记忆）
    - 长期记忆
    - 外部知识（预留接口）
    """
    
    def __init__(
        self,
        session_manager: SessionManager,
        memory_manager: Optional[MemoryManager] = None,
    ):
        """
        初始化上下文收集器
        
        Args:
            session_manager: 会话管理器实例
            memory_manager: 记忆管理器实例（可选）
        """
        self.session_manager = session_manager
        self.memory_manager = memory_manager
    
    async def collect(
        self,
        user_input: str,
        include_session: bool = True,
        include_memory: bool = True,
        include_knowledge: bool = False,
    ) -> ProcessedContext:
        """
        收集所有相关上下文
        
        Args:
            user_input: 用户输入（用于检索相关记忆）
            include_session: 是否包含会话历史
            include_memory: 是否包含长期记忆
            include_knowledge: 是否包含外部知识（当前未实现）
            
        Returns:
            处理后的上下文对象
        """
        context = ProcessedContext()
        
        # 收集会话历史
        if include_session:
            try:
                history = await self.session_manager.get_recent_history()
                for msg in history:
                    context.add_item(ContextItem(
                        content=f"{msg.role.value}: {msg.content}",
                        source=ContextSource.SESSION,
                        timestamp=msg.timestamp,
                        metadata=msg.metadata
                    ))
                logger.debug(f"Collected {len(history)} messages from session history")
            except Exception as e:
                logger.warning(f"Failed to collect session history: {str(e)}")
        
        # 收集长期记忆
        if include_memory and self.memory_manager:
            try:
                memories = await self.memory_manager.retrieve(user_input)
                context.items.extend(memories)
                logger.debug(f"Collected {len(memories)} items from long-term memory")
            except Exception as e:
                logger.warning(f"Failed to collect long-term memory: {str(e)}")
        
        # 外部知识（预留接口）
        if include_knowledge:
            logger.debug("External knowledge retrieval not yet implemented")
        
        # 记录元数据
        context.metadata['include_session'] = include_session
        context.metadata['include_memory'] = include_memory
        context.metadata['include_knowledge'] = include_knowledge
        context.metadata['total_items'] = len(context.items)
        
        logger.info(f"Collected {len(context.items)} context items")
        
        return context
