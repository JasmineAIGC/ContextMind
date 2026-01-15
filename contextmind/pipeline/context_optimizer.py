"""
ContextOptimizer - 上下文优化器

优化上下文以适应模型的输入限制，包括压缩、截断和重排。

上下文工程核心能力：
- 智能限制历史对话数量（默认保留最近6条，约3轮对话）
- Token限制和截断
- 重要信息前置
- 从对话历史中提炼关键信息
"""

from typing import Optional, List, Dict, Any
import re

from ..data_models import ProcessedContext, ContextItem, ContextSource
from ..logger import get_logger

logger = get_logger(__name__)

# 默认配置常量
DEFAULT_MAX_SESSION_ITEMS = 6  # 默认最多保留6条会话消息（约3轮对话）
DEFAULT_MAX_MEMORY_ITEMS = 5   # 默认最多保留5条长期记忆


class ContextOptimizer:
    """
    上下文优化器
    
    对整合后的上下文进行优化：
    - 限制会话历史数量（默认保留最近3轮对话）
    - Token限制和截断
    - 重要信息前置
    - 智能提炼关键信息
    
    上下文工程原则：
    - 不是所有历史都需要，只保留相关的部分
    - 长期记忆补充短期历史
    - 避免信息过载影响LLM表现
    """
    
    def __init__(
        self,
        max_length: Optional[int] = None,
        max_items: Optional[int] = None,
        max_session_items: int = DEFAULT_MAX_SESSION_ITEMS,
        max_memory_items: int = DEFAULT_MAX_MEMORY_ITEMS,
        enable_summarization: bool = True,
    ):
        """
        初始化上下文优化器
        
        Args:
            max_length: 最大文本长度限制（字符数）
            max_items: 最大上下文项数量限制（总数）
            max_session_items: 会话历史最大条数（默认6条，约3轮对话）
            max_memory_items: 长期记忆最大条数（默认5条）
            enable_summarization: 是否启用智能总结和提炼
        """
        self.max_length = max_length
        self.max_items = max_items
        self.max_session_items = max_session_items
        self.max_memory_items = max_memory_items
        self.enable_summarization = enable_summarization
    
    def _extract_key_info(self, items: List[ContextItem]) -> Dict[str, Any]:
        """
        从对话历史中提炼关键信息
        
        Args:
            items: 上下文项列表
            
        Returns:
            提炼出的关键信息字典
        """
        key_info = {
            'topics': set(),  # 讨论的主题
            'entities': set(),  # 提到的实体（人、地点、物品等）
            'user_preferences': [],  # 用户偏好
            'user_states': [],  # 用户状态
            'action_items': [],  # 待办事项
        }
        
        # 简单的关键词提取（可以扩展为更复杂的NLP）
        topic_keywords = ['关于', '讨论', '谈', '说', '想', '要', '需要']
        entity_patterns = [
            r'(?:去|在|到)([^，。！？\s]{2,6})',  # 地点
            r'(?:叫|是)([^，。！？\s]{2,6})',  # 名称
        ]
        preference_keywords = ['喜欢', '不喜欢', '偏好', '想要', '不想']
        state_keywords = ['累', '忙', '闲', '开心', '难过', '不想']
        action_keywords = ['帮', '做', '写', '处理', '完成']
        
        for item in items:
            content = item.content
            
            # 提取实体
            for pattern in entity_patterns:
                matches = re.findall(pattern, content)
                key_info['entities'].update(matches)
            
            # 提取偏好
            for keyword in preference_keywords:
                if keyword in content:
                    # 获取keyword周围的文本作为偏好描述
                    idx = content.find(keyword)
                    context_slice = content[max(0, idx-10):min(len(content), idx+20)]
                    key_info['user_preferences'].append(context_slice.strip())
            
            # 提取状态
            for keyword in state_keywords:
                if keyword in content:
                    idx = content.find(keyword)
                    context_slice = content[max(0, idx-5):min(len(content), idx+15)]
                    key_info['user_states'].append(context_slice.strip())
            
            # 提取行动项
            for keyword in action_keywords:
                if keyword in content:
                    idx = content.find(keyword)
                    context_slice = content[max(0, idx-5):min(len(content), idx+20)]
                    key_info['action_items'].append(context_slice.strip())
        
        # 去重并限制数量
        key_info['entities'] = list(key_info['entities'])[:10]
        key_info['user_preferences'] = list(set(key_info['user_preferences']))[:5]
        key_info['user_states'] = list(set(key_info['user_states']))[:5]
        key_info['action_items'] = list(set(key_info['action_items']))[:5]
        
        return key_info
    
    async def optimize(
        self,
        context: ProcessedContext,
        max_length: Optional[int] = None,
        max_items: Optional[int] = None,
    ) -> ProcessedContext:
        """
        优化上下文
        
        上下文工程核心：不是把所有信息都放入prompt，而是选择最相关的部分。
        
        优化策略：
        1. 按来源分类限制数量（会话历史、长期记忆分别限制）
        2. 优先保留最近的会话历史
        3. 优先保留高分数的长期记忆
        4. 提炼关键信息作为补充
        
        Args:
            context: 待优化的上下文对象
            max_length: 最大文本长度（覆盖初始化参数）
            max_items: 最大项数量（覆盖初始化参数）
            
        Returns:
            优化后的上下文对象
        """
        # 使用传入参数或初始化参数
        max_len = max_length if max_length is not None else self.max_length
        max_it = max_items if max_items is not None else self.max_items
        
        items = context.items
        original_count = len(items)
        
        # 智能提炼关键信息（如果启用）
        if self.enable_summarization and items:
            key_info = self._extract_key_info(items)
            context.metadata['extracted_info'] = key_info
            logger.debug(f"Extracted key info: {len(key_info['entities'])} entities, "
                        f"{len(key_info['user_preferences'])} preferences, "
                        f"{len(key_info['action_items'])} actions")
        
        # ===== 按来源分类限制数量 =====
        # 分离不同来源的上下文项
        session_items = [item for item in items if item.source == ContextSource.SESSION]
        memory_items = [item for item in items if item.source == ContextSource.MEMORY]
        other_items = [item for item in items if item.source not in (ContextSource.SESSION, ContextSource.MEMORY)]
        
        # 限制会话历史数量（只保留最近的）
        if len(session_items) > self.max_session_items:
            session_items = session_items[-self.max_session_items:]  # 保留最近的
            context.metadata['session_truncated'] = True
            logger.debug(f"Session items limited to last {self.max_session_items}")
        
        # 限制长期记忆数量（保留分数最高的）
        if len(memory_items) > self.max_memory_items:
            memory_items = sorted(memory_items, key=lambda x: x.score, reverse=True)[:self.max_memory_items]
            context.metadata['memory_truncated'] = True
            logger.debug(f"Memory items limited to top {self.max_memory_items}")
        
        # 重新组合：长期记忆在前，会话历史在后，其他项最后
        items = memory_items + session_items + other_items
        
        # 全局项数量限制（如果设置了max_it）
        if max_it and len(items) > max_it:
            items = items[:max_it]
            context.metadata['truncated_by_count'] = True
            logger.debug(f"Truncated items from {original_count} to {max_it}")
        
        # 限制文本长度
        if max_len:
            total_length = sum(len(item.content) for item in items)
            if total_length > max_len:
                # 简单截断策略：按比例保留每个项
                kept_items = []
                current_length = 0
                
                for item in items:
                    if current_length + len(item.content) <= max_len:
                        kept_items.append(item)
                        current_length += len(item.content)
                    else:
                        # 尝试截断当前项以填满剩余空间
                        remaining = max_len - current_length
                        if remaining > 100:  # 至少保留100字符
                            truncated_content = item.content[:remaining] + "..."
                            truncated_item = ContextItem(
                                content=truncated_content,
                                source=item.source,
                                score=item.score,
                                timestamp=item.timestamp,
                                metadata={**item.metadata, 'truncated': True}
                            )
                            kept_items.append(truncated_item)
                        break
                
                items = kept_items
                context.metadata['truncated_by_length'] = True
                logger.debug(f"Truncated by length from {total_length} to {max_len} chars")
        
        # 更新上下文
        context.items = items
        context.metadata['optimized'] = True
        context.metadata['final_items'] = len(items)
        
        logger.debug(f"Optimized to {len(items)} context items")
        
        return context
