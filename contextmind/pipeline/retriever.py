"""
ContextRetriever - 统一检索模块

职责：
- RAG检索相关历史
- 检索外部知识
- 检索长期记忆

可插拔策略：
- BM25检索
- Dense Retrieval（语义检索）
- Hybrid混合检索
- ReRank重排序
"""

from typing import List, Optional
from ..core import ProcessedContext, ContextItem, ContextSource, get_logger
from .session import SessionManager
from .memory import MemoryBank

logger = get_logger(__name__)


class ContextRetriever:
    """
    上下文检索器
    
    统一的检索接口，支持多源检索：
    - 会话历史（短期）
    - 长期记忆
    - 外部知识（预留）
    """
    
    def __init__(
        self,
        session_manager: SessionManager,
        memory_bank: Optional[MemoryBank] = None,
    ):
        """
        初始化检索器
        
        Args:
            session_manager: 会话管理器
            memory_bank: 记忆库
        """
        self.session_manager = session_manager
        self.memory_bank = memory_bank
    
    async def retrieve(
        self,
        query: str,
        include_session: bool = True,
        include_memory: bool = True,
        include_knowledge: bool = False,
    ) -> ProcessedContext:
        """
        统一检索接口
        
        Args:
            query: 查询文本（用户输入）
            include_session: 是否检索会话历史
            include_memory: 是否检索长期记忆
            include_knowledge: 是否检索外部知识
            
        Returns:
            检索到的上下文
        """
        context = ProcessedContext()
        
        # 检索会话历史
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
                logger.debug(f"Retrieved {len(history)} session messages")
            except Exception as e:
                logger.warning(f"Session retrieval failed: {e}")
        
        # 检索长期记忆
        if include_memory and self.memory_bank:
            try:
                memories = await self.memory_bank.retrieve(query)
                for item in memories:
                    context.add_item(ContextItem(
                        content=item.content,
                        source=ContextSource.MEMORY,
                        metadata={"score": item.score}
                    ))
                logger.debug(f"Retrieved {len(memories)} memories")
            except Exception as e:
                logger.warning(f"Memory retrieval failed: {e}")
        
        # 检索外部知识（预留）
        if include_knowledge:
            logger.debug("External knowledge retrieval not implemented")
        
        return context
