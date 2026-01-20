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
from ..core import ProcessedContext, ContextItem, ContextSource
from ..utils import get_logger
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
        logger.info(f"[Retriever] 开始检索上下文 - 查询: '{query[:30]}{'...' if len(query) > 30 else ''}'")
        logger.debug(f"[Retriever] 检索配置 - 会话历史: {include_session}, 长期记忆: {include_memory}, 外部知识: {include_knowledge}")
        
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
                logger.info(f"[Retriever] ✓ 会话历史检索完成 - 获取 {len(history)} 条对话")
                if history:
                    logger.debug(f"[Retriever] 会话历史详情:")
                    for i, msg in enumerate(history[:3], 1):  # Show first 3 for brevity
                        logger.debug(f"  {i}. [{msg.role.value}] {msg.content[:60]}...")
                    if len(history) > 3:
                        logger.debug(f"  ... 以及其他 {len(history) - 3} 条对话")
            except Exception as e:
                logger.warning(f"[Retriever] ✗ 会话历史检索失败: {e}")
        
        # 检索长期记忆
        if include_memory and self.memory_bank:
            try:
                # Log memory bank state before retrieval
                cache_size = len(self.memory_bank.get_memory_cache())
                logger.info(f"[Retriever] 准备从记忆库检索 - 当前记忆库大小: {cache_size}")
                
                memories = await self.memory_bank.retrieve(query)
                for item in memories:
                    context.add_item(ContextItem(
                        content=item.content,
                        source=ContextSource.MEMORY,
                        metadata={"score": item.score}
                    ))
                
                if memories:
                    logger.info(f"[Retriever] ✓ 长期记忆检索完成 - 获取 {len(memories)} 条记忆")
                    logger.debug(f"[Retriever] 检索到的记忆详情:")
                    for i, mem in enumerate(memories, 1):
                        logger.debug(f"  {i}. [score={mem.score:.2f}] {mem.content[:80]}...")
                else:
                    logger.warning(f"[Retriever] ✗ 未检索到相关记忆 (记忆库大小: {cache_size})")
            except Exception as e:
                logger.warning(f"[Retriever] ✗ 长期记忆检索失败: {e}")
        elif include_memory and not self.memory_bank:
            logger.warning(f"[Retriever] ✗ 长期记忆未启用 - 记忆库未初始化")
        
        # 检索外部知识（预留）
        if include_knowledge:
            logger.debug("[Retriever] 外部知识检索未实现")
        
        total_items = len(context.items)
        logger.info(f"[Retriever] 检索完成 - 总共获取 {total_items} 条上下文项")
        
        return context
