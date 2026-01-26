"""
Memory Updaters - Memory 更新的插件实现

该模块提供各种策略用于更新和维护 Memory Bank（增加、更新、删除操作）。
"""

from abc import ABC, abstractmethod
from typing import List, Optional
import re
from datetime import datetime

from ..models import ContextItem, ContextSource, Knowledge, KnowledgeType, get_logger
from ..utils.embedding import calculate_embedding_similarity

logger = get_logger(__name__)


class BaseUpdater(ABC):
    """
    Memory Updater 的基类接口
    
    Updater 处理 Add、Update 和 Delete 操作
    来维护 Memory Bank。
    """
    
    @abstractmethod
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        使用新知识更新 Memory Cache
        
        处理：
        - Add: 插入新记忆
        - Update: 合并或替换现有记忆
        - Delete: 移除过时或低价值的记忆
        
        Args:
            memory_cache: 当前 Memory Cache
            new_knowledge: 待集成的新知识
            
        Returns:
            更新后的 Memory Cache
        """
        pass


class SimpleUpdater(BaseUpdater):
    """
    简单 Memory Updater（现有实现）
    
    基本的增加/更新/去重逻辑，具有可配置的阈值。
    按置信度过滤、去重并限制 Cache 大小。
    
    v3.5: 新增记忆合并功能
    - 检测相似记忆并合并/更新
    - 保留高置信度版本
    - 更新时间戳
    """
    
    # 存储阈值（提高质量要求）
    STORAGE_THRESHOLD_PREFERENCE = 0.80  # 0.75 → 0.80
    STORAGE_THRESHOLD_FACT = 0.75  # 0.70 → 0.75
    STORAGE_THRESHOLD_EVENT = 0.75  # 0.70 → 0.75
    STORAGE_MIN_LENGTH = 5  # 3 → 5 最小字符数
    
    # 相似度阈值（用于检测需要合并的记忆）
    SIMILARITY_THRESHOLD_FOR_MERGE = 0.65  # 降低到65%以捕获更多相似记忆
    EXACT_DUPLICATE_THRESHOLD = 0.85  # 从0.90降至0.85，捕获更多重复项
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        简单更新策略（含记忆合并）
        
        1. 过滤低质量知识
        2. 检测并合并相似记忆
        3. 对现有 Cache 去重
        4. 向 Cache 添加新条目
        
        Args:
            memory_cache: 当前 Cache
            new_knowledge: 新知识
            
        Returns:
            更新后的 Cache
        """
        if not new_knowledge:
            logger.debug("[SimpleUpdater] 没有知识需要存储")
            return memory_cache
        
        logger.info(f"[SimpleUpdater] 开始存储知识 - 收到 {len(new_knowledge)} 条知识项")
        
        # 按置信度和内容质量过滤
        filtered_knowledge = []
        for k in new_knowledge:
            min_confidence = {
                KnowledgeType.PREFERENCE: self.STORAGE_THRESHOLD_PREFERENCE,
                KnowledgeType.FACT: self.STORAGE_THRESHOLD_FACT,
                KnowledgeType.EVENT: self.STORAGE_THRESHOLD_EVENT,
            }.get(k.type, self.STORAGE_THRESHOLD_FACT)
            
            if (k.confidence >= min_confidence 
                and len(k.content.strip()) >= self.STORAGE_MIN_LENGTH
                and not k.content.isdigit()):
                filtered_knowledge.append(k)
            else:
                # 提供具体的过滤原因以辅助调试
                if k.confidence < min_confidence:
                    reason = f"置信度不足 ({k.confidence:.2f} < {min_confidence:.2f})"
                elif len(k.content.strip()) < self.STORAGE_MIN_LENGTH:
                    reason = f"内容过短 ({len(k.content.strip())} < {self.STORAGE_MIN_LENGTH})"
                else:  # k.content.isdigit()
                    reason = "纯数字内容"
                logger.debug(f"[SimpleUpdater] 过滤低质量知识 ({reason}): [{k.type.value}] {k.content[:50]}...")
        
        if len(filtered_knowledge) < len(new_knowledge):
            logger.info(f"[SimpleUpdater] 质量过滤: {len(new_knowledge)} → {len(filtered_knowledge)} 条知识")
        
        # **新增**: 记忆合并逻辑
        # 复制当前cache用于更新
        updated_cache = list(memory_cache)
        new_items = []
        merged_count = 0
        
        for k in filtered_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            # 检查是否有相似的现有记忆需要合并/更新
            merge_target_idx = None
            max_similarity = 0.0
            
            for idx, existing in enumerate(updated_cache):
                # 优先使用 embedding 相似度，如果不可用则回退到字符级
                similarity = self._calculate_similarity_with_embedding(k, existing)
                
                # 如果相似度极高（完全重复），跳过
                if similarity >= self.EXACT_DUPLICATE_THRESHOLD:
                    logger.debug(f"[SimpleUpdater] 跳过完全重复知识 (相似度={similarity:.2f}): {formatted_content[:50]}...")
                    merge_target_idx = -1  # 标记为完全重复，不处理
                    break
                
                # 如果相似度中等（需要合并），记录最相似的条目
                if similarity >= self.SIMILARITY_THRESHOLD_FOR_MERGE and similarity > max_similarity:
                    max_similarity = similarity
                    merge_target_idx = idx
            
            if merge_target_idx == -1:
                # 完全重复，跳过
                continue
            elif merge_target_idx is not None:
                # 找到相似记忆，需要合并/更新
                existing_item = updated_cache[merge_target_idx]
                
                # 如果新知识置信度更高，替换旧记忆
                if k.confidence > existing_item.score:
                    logger.info(f"[SimpleUpdater] 🔄 合并记忆 (相似度={max_similarity:.2f}, 新置信度={k.confidence:.2f} > 旧={existing_item.score:.2f})")
                    logger.debug(f"  旧: {existing_item.content[:60]}...")
                    logger.debug(f"  新: {formatted_content[:60]}...")
                    
                    # 更新为新版本
                    updated_cache[merge_target_idx] = ContextItem(
                        content=formatted_content,
                        source=ContextSource.MEMORY,
                        score=k.confidence,
                        timestamp=datetime.now(),  # 更新时间戳
                        embeddings=k.embeddings,  # 保留 embeddings
                        metadata={**k.metadata, 'updated': True, 'previous_score': existing_item.score}
                    )
                    merged_count += 1
                else:
                    # 旧记忆置信度更高，保留旧的
                    logger.debug(f"[SimpleUpdater] 保留旧记忆 (相似度={max_similarity:.2f}, 旧置信度={existing_item.score:.2f} >= 新={k.confidence:.2f}): {existing_item.content[:50]}...")
            else:
                # 没有相似记忆，添加为新项
                new_items.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    timestamp=datetime.now(),
                    embeddings=k.embeddings,  # 添加 embeddings
                    metadata=k.metadata
                ))
                logger.debug(f"[SimpleUpdater] 已存储: {formatted_content[:80]}...")
        
        if not new_items and merged_count == 0:
            logger.info("[SimpleUpdater] 所有知识项均为重复或低质量，未存储新内容")
            return updated_cache
        
        # 添加新项到cache
        if new_items:
            updated_cache.extend(new_items)
        
        logger.info(f"[SimpleUpdater] ✓ 存储完成 - 新增 {len(new_items)} 条知识, 合并/更新 {merged_count} 条")
        logger.info(f"[SimpleUpdater] 当前记忆库总计: {len(updated_cache)} 条记忆")
        
        return updated_cache
    
    def _calculate_similarity_with_embedding(self, knowledge: Knowledge, existing: ContextItem) -> float:
        """
        计算知识与现有记忆的相似度，优先使用 embedding
        
        Args:
            knowledge: 新知识对象
            existing: 现有记忆项
            
        Returns:
            相似度分数（0-1）
        """
        # 尝试使用 embedding 相似度
        if knowledge.embeddings and existing.embeddings:
            knowledge_emb = knowledge.embeddings.get('default')
            existing_emb = existing.embeddings.get('default')
            
            if knowledge_emb and existing_emb:
                similarity, success = calculate_embedding_similarity(knowledge_emb, existing_emb)
                if success:
                    logger.debug(f"[SimpleUpdater] 使用 embedding 相似度: {similarity:.3f}")
                    return similarity
        
        # 回退到字符级相似度
        formatted_content = f"[{knowledge.type.value.upper()}] {knowledge.content}"
        return self._calculate_similarity(formatted_content, existing.content)
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        计算两个文本的Jaccard相似度
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            相似度分数（0-1）
        """
        # 移除类型标签用于比较
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip().lower()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip().lower()
        
        if not clean1 or not clean2:
            return 0.0
        
        # 对于中文，使用字符集合
        chars1 = set(clean1)
        chars2 = set(clean2)
        
        # 移除空格和标点
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return 0.0
        
        # 计算Jaccard相似度
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """检查两个文本是否相似（支持中文）"""
        # 移除类型标签用于比较
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip()
        
        if not clean1 or not clean2:
            return False
        
        # 子字符串匹配
        if clean1 in clean2 or clean2 in clean1:
            return True
        
        # 中文的字符级 Jaccard Similarity
        chars1 = set(clean1.lower())
        chars2 = set(clean2.lower())
        
        # 移除空格和标点符号
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return False
        
        # Jaccard Similarity（Jaccard 相似度）
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        similarity = intersection / union if union > 0 else 0
        
        # 70% 相似度阈值
        return similarity > 0.7


class ConflictResolverUpdater(BaseUpdater):
    """
    冲突感知 Updater（未来实现的占位符）
    
    检测并解决新信息与现有记忆相冲突的情况。
    支持版本控制和合并策略。
    
    未来增强功能：
    - 基于 LLM 的冲突检测
    - 自动矛盾解决
    - 版本历史跟踪
    - 用户冲突处理偏好设置
    """
    
    def __init__(
        self,
        llm_client: Optional[any] = None,
        enable_versioning: bool = True
    ):
        """
        初始化冲突解决器
        
        Args:
            llm_client: 用于冲突推理的 LLM（可选）
            enable_versioning: 追踪版本历史
        """
        self.llm_client = llm_client
        self.enable_versioning = enable_versioning
        logger.info(f"[ConflictResolverUpdater] 已初始化（占位符）- versioning={enable_versioning}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        带冲突检测的更新
        
        当前实现是一个占位符，会回退到简单更新。
        
        未来待做事项：
        - 检测相互矛盾的记忆
        - 解决冲突（合并、替换、版本控制）
        - 追踪更新历史
        
        Args:
            memory_cache: 当前 Cache
            new_knowledge: 新知识
            
        Returns:
            更新后的 Cache（目前使用回退方案）
        """
        logger.debug("[ConflictResolverUpdater] 使用 SimpleUpdater 的回退方案（尚未实现）")
        
        # 目前回退到简单更新
        fallback = SimpleUpdater()
        return await fallback.update(memory_cache, new_knowledge)


class AdaptiveEvictionUpdater(BaseUpdater):
    """
    自适应驱逐 Updater（未来实现的占位符）
    
    基于重要性、访问模式和容量限制智能移除低价值记忆。
    防止 Cache 膨胀。
    
    未来增强功能：
    - 基于重要性的驱逐（LRU + 分数）
    - 自适应容量限制
    - 预测性驱逐
    - 访问模式分析
    """
    
    def __init__(
        self,
        max_cache_size: int = 100,
        min_importance_threshold: float = 0.1
    ):
        """
        初始化自适应驱逐 Updater
        
        Args:
            max_cache_size: 缓存的最大记忆数
            min_importance_threshold: 保持的最小重要性
        """
        self.max_cache_size = max_cache_size
        self.min_importance_threshold = min_importance_threshold
        logger.info(f"[AdaptiveEvictionUpdater] 已初始化（占位符）- max_size={max_cache_size}, min_importance={min_importance_threshold}")
    
    async def update(
        self,
        memory_cache: List[ContextItem],
        new_knowledge: List[Knowledge]
    ) -> List[ContextItem]:
        """
        带自适应驱逐的更新
        
        当前实现是一个占位符，会回退到简单更新。
        
        未来待做事项：
        - 实现重要性评分
        - 当 Cache 满时驱逐低价值记忆
        - 考虑访问频率和新近性
        
        Args:
            memory_cache: 当前 Cache
            new_knowledge: 新知识
            
        Returns:
            更新后的 Cache（目前使用回退方案）
        """
        logger.debug("[AdaptiveEvictionUpdater] 使用 SimpleUpdater 的回退方案（尚未实现）")
        
        # 目前回退到简单更新
        fallback = SimpleUpdater()
        updated_cache = await fallback.update(memory_cache, new_knowledge)
        
        # 未来：当 Cache 超过 max_cache_size 时添加驱逐逻辑
        # 这涉及：
        # 1. 为所有缓存项计算重要性分数
        # 2. 按重要性排序（结合新近性、访问频率和分数）
        # 3. 驱逐最低重要性的项目以达到目标大小
        # 示例实现（当重要性评分准备好时）：
        #   if len(updated_cache) > self.max_cache_size:
        #       updated_cache = self._evict_low_value_memories(updated_cache)
        
        return updated_cache
    
    def _evict_low_value_memories(self, cache: List[ContextItem]) -> List[ContextItem]:
        """
        驱逐低价值记忆以维持 Cache 大小（占位符）
        
        该方法会智能地移除重要性分数低的记忆，
        同时保留高价值和最近的项目。
        
        Args:
            cache: 当前 Memory Cache
            
        Returns:
            驱逐后的 Cache
        """
        # TODO: 当重要性评分可用时实现
        # 当前实现只是截断为 max_cache_size
        if len(cache) > self.max_cache_size:
            # 保留最近的项目（简单策略）
            return cache[-self.max_cache_size:]
        return cache
