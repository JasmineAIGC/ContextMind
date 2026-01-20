"""
Optimization Strategies - 优化策略实现

提供多种优化策略，用于压缩和重排上下文以适应模型输入限制。

v3.3更新：
- 支持可配置化设计
- 使用CompressionConfig减少硬编码
"""

from typing import Optional, List
from datetime import datetime

from ..core import ProcessedContext, ContextItem, ContextResult, ContextSource
from .base import OptimizationStrategy
from ..utils import get_logger
from ..core import DEFAULT_MEMORY_CONFIG, CompressionConfig

logger = get_logger(__name__)


class CompressionStrategy(OptimizationStrategy):
    """
    压缩策略
    
    通过截断和摘要来压缩上下文，使其适应token限制。
    """
    
    def __init__(
        self,
        max_tokens: int = None,
        max_items: Optional[int] = None,
        config: Optional[CompressionConfig] = None,
    ):
        """
        初始化压缩策略
        
        Args:
            max_tokens: 最大token数（这里用字符数近似，None则使用配置）
            max_items: 最大上下文项数量（None则使用配置）
            config: 压缩配置，如果为None则使用默认配置
        """
        self.config = config or DEFAULT_MEMORY_CONFIG.compression
        self.max_tokens = max_tokens or self.config.default_max_tokens
        self.max_items = max_items or self.config.default_max_items
    
    async def optimize(self, context: ProcessedContext) -> ContextResult:
        """
        优化上下文
        
        通过截断来压缩上下文，然后转换为 ContextResult。
        压缩时会保留不同来源的条目，避免只保留单一来源。
        
        Args:
            context: 待优化的上下文（ProcessedContext）
            
        Returns:
            优化后的上下文结果（ContextResult）
        """
        items = context.items
        
        # 限制项数量 - 智能保留不同来源的条目
        if self.max_items and len(items) > self.max_items:
            # 按来源分组
            from ..core import ContextSource
            session_items = [item for item in items if item.source == ContextSource.SESSION]
            memory_items = [item for item in items if item.source == ContextSource.MEMORY]
            knowledge_items = [item for item in items if item.source in (ContextSource.KNOWLEDGE, ContextSource.EXTERNAL)]
            
            # 智能分配配额：优先保留记忆和知识，剩余给会话
            # 为记忆和知识各保留至少N个位置（如果有的话）
            reserved_for_memory = min(
                len(memory_items), 
                max(self.config.min_memory_items, int(self.max_items * self.config.memory_quota_percentage))
            )
            reserved_for_knowledge = min(
                len(knowledge_items),
                max(self.config.min_knowledge_items, int(self.max_items * self.config.knowledge_quota_percentage))
            )
            remaining_for_session = self.max_items - reserved_for_memory - reserved_for_knowledge
            
            # 确保不超出实际数量
            kept_memory = memory_items[:reserved_for_memory]
            kept_knowledge = knowledge_items[:reserved_for_knowledge]
            kept_session = session_items[:remaining_for_session]
            
            # 重新组合，保持原始顺序的相对位置
            items = []
            for item in context.items:
                if item in kept_session or item in kept_memory or item in kept_knowledge:
                    items.append(item)
                if len(items) >= self.max_items:
                    break
            
            context.metadata['truncated_by_count'] = True
            context.metadata['kept_session'] = len(kept_session)
            context.metadata['kept_memory'] = len(kept_memory)
            context.metadata['kept_knowledge'] = len(kept_knowledge)
        
        # 限制总token数（用字符数近似）
        total_chars = sum(len(item.content) for item in items)
        if total_chars > self.max_tokens:
            compressed_items = []
            current_chars = 0
            
            for item in items:
                if current_chars + len(item.content) <= self.max_tokens:
                    compressed_items.append(item)
                    current_chars += len(item.content)
                else:
                    # 尝试截断当前项
                    remaining = self.max_tokens - current_chars
                    if remaining > 50:
                        truncated_content = item.content[:remaining] + "..."
                        truncated_item = ContextItem(
                            content=truncated_content,
                            source=item.source,
                            score=item.score,
                            timestamp=item.timestamp,
                            metadata={**item.metadata, 'truncated': True}
                        )
                        compressed_items.append(truncated_item)
                    break
            
            items = compressed_items
            context.metadata['truncated_by_length'] = True
        
        # 更新处理后的条目
        context.items = items
        context.metadata['optimization_strategy'] = 'compression'
        
        logger.debug(f"CompressionStrategy: {len(items)} items after optimization")
        
        # 转换为 ContextResult
        result = context.to_context_result()
        
        logger.debug(
            f"CompressionStrategy converted to ContextResult: "
            f"{len(result.recent_history)} history, "
            f"{len(result.long_term_memory)} memory, "
            f"{len(result.external_knowledge)} knowledge"
        )
        
        return result


class RerankingStrategy(OptimizationStrategy):
    """
    重排策略
    
    使用 Lost-in-the-Middle 优化技术，将重要信息放在开头和结尾。
    """
    
    def __init__(self, keep_recent_at_end: bool = True):
        """
        初始化重排策略
        
        Args:
            keep_recent_at_end: 是否将最近的信息保留在末尾
        """
        self.keep_recent_at_end = keep_recent_at_end
    
    async def optimize(self, context: ProcessedContext) -> ProcessedContext:
        """
        优化上下文
        
        应用 Lost-in-the-Middle 优化：
        - 高分项放在开头
        - 最近的项放在结尾
        - 中等重要的项放在中间
        
        Args:
            context: 待优化的上下文（ProcessedContext）
            
        Returns:
            重排序后的上下文（ProcessedContext）
            
        Note:
            这是一个中间优化步骤，返回 ProcessedContext 而非 ContextResult。
            只有最终的压缩步骤才会转换为 ContextResult。
        """
        items = context.items
        
        if len(items) <= 3:
            # 太少不需要重排
            return context
        
        # 按分数排序
        sorted_by_score = sorted(items, key=lambda x: x.score, reverse=True)
        
        # 分成三组
        n = len(sorted_by_score)
        high_priority = sorted_by_score[:n//3]  # 前1/3
        medium_priority = sorted_by_score[n//3:2*n//3]  # 中间1/3
        low_priority = sorted_by_score[2*n//3:]  # 后1/3
        
        # 重排：高优先级在前，低优先级在后，中优先级在中间
        # 这样可以避免重要信息被"淹没"在中间
        reranked = high_priority + medium_priority + low_priority
        
        # 如果需要，将最近的项移到最后
        if self.keep_recent_at_end and items:
            # 找出最近的几个项（基于时间戳）
            # 只包含有效的datetime类型的timestamp
            from datetime import datetime
            items_with_time = [
                item for item in reranked 
                if item.timestamp and isinstance(item.timestamp, datetime)
            ]
            if items_with_time:
                items_with_time.sort(key=lambda x: x.timestamp, reverse=True)
                recent_items = items_with_time[:2]  # 最近的2个
                
                # 从reranked中移除这些项
                for item in recent_items:
                    if item in reranked:
                        reranked.remove(item)
                
                # 添加到末尾
                reranked.extend(recent_items)
        
        context.items = reranked
        context.metadata['optimization_strategy'] = 'reranking'
        context.metadata['reranking_applied'] = True
        
        logger.debug(f"RerankingStrategy: reranked {len(items)} items")
        
        return context
