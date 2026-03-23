"""
MemoryBank - 长期记忆存储和检索
"""

from typing import List, Optional, Dict, Any
import uuid
import re
from datetime import datetime

from ..core.data_models import (
    ContextItem,
    MemoryNote,
    Knowledge,
)
from ..core.config import ContextSource, KnowledgeType, MemoryType
from ..core.config import DEFAULT_MEMORY_CONFIG, RetrievalConfig
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)

try:
    from .retriever import (
        BaseRetriever,
        SemanticSearchRetriever,
    )
    from .updater import (
        BaseUpdater,
        SimpleUpdater,
    )
    PLUGINS_AVAILABLE = True
except ImportError:
    PLUGINS_AVAILABLE = False
    logger.debug("[MemoryBank] Plugin 架构不可用, 使用内部实现")

# 停用词列表（可配置，支持国际化扩展）
STOPWORDS = {
    # 中文常用停用词
    '的', '了', '是', '在', '有', '和', '与', '或', '我', '你', '他', '她', '它', '们',
    '这', '那', '什么', '怎么', '为什么', '如何', '哪里', '谁', '哪', '吗', '呢', '啊',
    '就', '都', '也', '还', '能', '会', '要', '可以', '不', '没', '很', '但', '而',
    # 英文常用停用词
    'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should',
    'i', 'you', 'he', 'she', 'it', 'we', 'they', 'what', 'which', 'who',
    'this', 'that', 'these', 'those', 'and', 'or', 'but', 'if', 'then',
}


class MemoryBank:
    """
    记忆管理器 - 封装 ADK Memory Service

    提供长期记忆的存储、检索和管理功能
    """
    
    # 偏好类知识需要比事实/事件更高的置信度，因为错误的偏好会悄然影响每次后续交互，
    # 而且没有明显的纠正信号；相比之下，错误事实更容易在对话中被发现并修正。
    STORAGE_THRESHOLD_PREFERENCE = 0.75
    STORAGE_THRESHOLD_FACT = 0.70
    STORAGE_THRESHOLD_EVENT = 0.70
    STORAGE_MIN_LENGTH = 3  # 拒绝单字符或纯空白字符串
    
    def __init__(
        self,
        memory_service: Optional[Any] = None,
        session_service: Optional[Any] = None,
        app_name: str = "evolve",
        user_id: str = "default",
        retrieval_config: Optional[RetrievalConfig] = None,
        retriever: Optional[Any] = None,
        updater: Optional[Any] = None,
    ):
        """
        初始化记忆管理器

        Args:
            memory_service: 记忆服务实例（可选），如果为 None 则仅使用本地缓存
            session_service: 会话服务实例（可选）
            app_name: 应用名称
            user_id: 用户 ID
            retrieval_config: 检索配置，如果为 None 则使用默认配置
            retriever: 自定义检索器插件（可选），默认使用语义搜索检索器
            updater: 自定义更新器插件（可选），默认使用简单更新器
        """
        self.memory_service = memory_service
        self.session_service = session_service
        self.app_name = app_name
        self.user_id = user_id
        self.config = retrieval_config or DEFAULT_MEMORY_CONFIG.retrieval
        
        if PLUGINS_AVAILABLE:
            self._retriever = retriever or SemanticSearchRetriever(self.config)
            self._updater = updater or SimpleUpdater()
            logger.debug(f"[MemoryBank] 使用 Plugin - Retriever: {type(self._retriever).__name__}, Updater: {type(self._updater).__name__}")
        else:
            self._retriever = None
            self._updater = None
        
        self._memory_notes: Dict[str, MemoryNote] = {}
        self._local_cache: List[ContextItem] = []
    
    async def retrieve(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        检索相关记忆

        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量

        Returns:
            上下文条目列表，按相关性排序
        """
        logger.info(f"[MemoryBank] 开始检索记忆 - 查询: '{query[:50]}{'...' if len(query) > 50 else ''}'")
        logger.debug(f"[MemoryBank] 记忆库状态 - Memory Service: {'已配置' if self.memory_service else '未配置'}, 本地缓存大小: {len(self._local_cache)}")

        if not self.memory_service:
            logger.debug("[MemoryBank] Memory Service 未配置，使用本地缓存检索")
            return await self._retrieve_from_cache(query, limit)
        
        try:
            response = await self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            if response and response.memories:
                items = []
                for memory in response.memories[:limit]:
                    content = self._content_to_text(memory.content)
                    if not content:
                        continue
                    
                    items.append(ContextItem(
                        content=content,
                        source=ContextSource.MEMORY,
                        score=1.0,  # ADK 不提供分数，默认为 1.0
                        timestamp=memory.timestamp if hasattr(memory, 'timestamp') else None,
                        metadata={}
                    ))
                
                if items:
                    logger.info(f"✓ Retrieved {len(items)} memories from Memory Service")
                    return items
            
            logger.debug(f"No memories from Memory Service, falling back to local cache (size={len(self._local_cache)})")
            return await self._retrieve_from_cache(query, limit)
            
        except Exception as e:
            logger.warning(f"Failed to retrieve memories from Memory Service: {str(e)}, using local cache")
            return await self._retrieve_from_cache(query, limit)
    
    async def _retrieve_from_cache(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        从本地缓存检索相关记忆，优先使用可插拔检索器。

        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量

        Returns:
            匹配的上下文条目列表
        """
        logger.info(f"[MemoryBank] 从本地缓存检索 - 查询: '{query[:50]}', 缓存大小: {len(self._local_cache)}")
        
        if not self._local_cache:
            logger.warning("[MemoryBank] ✗ 本地缓存为空 - 无法检索记忆")
            return []
        
        if self._retriever:
            return await self._retriever.retrieve(query, self._local_cache, limit)

        return self._retrieve_from_cache_internal(query, limit)
    
    def _retrieve_from_cache_internal(self, query: str, limit: int = 5) -> List[ContextItem]:
        """当插件不可用时，缓存检索的内部实现（回退方案）"""
        
        query_lower = query.lower()

        scored_items = []
        for item in self._local_cache:
            content_lower = item.content.lower()

            # 直接子串包含是强相关证据；评分为 0.9 而非 1.0，
            # 以便向量检索器仍有机会获得更高分。
            if query_lower in content_lower or content_lower in query_lower:
                score = 0.9
            else:
                query_chars = set(query_lower)
                content_chars = set(content_lower)
                overlap = len(query_chars & content_chars)

                # 字符集 Jaccard 相似度是词汇相似性的快速近似计算。
                # min_overlap_chars 过滤掉仅由常用标点驱动的虚假匹配。
                if overlap >= self.config.min_overlap_chars:
                    union = len(query_chars | content_chars)
                    similarity = overlap / union if union > 0 else 0
                    # 将 Jaccard 相似度 [0, 1] 线性映射到 [base_score, 0.9]
                    score = self.config.base_score + similarity * (0.9 - self.config.base_score)
                else:
                    score = self.config.base_score

            if self.config.enable_recency_boost and item.timestamp:
                try:
                    if isinstance(item.timestamp, datetime):
                        days_ago = (datetime.now() - item.timestamp).days
                        if days_ago <= self.config.recency_days_threshold:
                            recency_boost = self.config.recency_weight * (
                                1 - days_ago / self.config.recency_days_threshold
                            )
                            score = min(1.0, score + recency_boost)
                except Exception as e:
                    logger.debug(f"Error calculating recency boost: {e}")
            
            scored_items.append((item, score))
        
        scored_items.sort(key=lambda x: x[1], reverse=True)

        if self.config.relevance_threshold > 0:
            filtered_items = [
                (item, score) for item, score in scored_items
                if score >= self.config.relevance_threshold
            ]
            
            if not filtered_items and scored_items:
                logger.debug(f"No memories above threshold {self.config.relevance_threshold}, using top items")
                filtered_items = scored_items[:limit]
        else:
            filtered_items = scored_items
        
        if self.config.enable_deduplication:
            filtered_items = self._deduplicate_memories(filtered_items)
        
        # 限制数量
        filtered_items = filtered_items[:min(limit, self.config.max_limit)]

        result = [
            ContextItem(
                content=item.content,
                source=item.source,
                score=score,
                timestamp=item.timestamp,
                metadata=item.metadata
            )
            for item, score in filtered_items
        ]
        
        if result:
            logger.info(f"[MemoryBank] ✓ 本地缓存检索成功 - 找到 {len(result)} 条相关记忆 (最高分: {filtered_items[0][1]:.2f})")
            logger.debug(f"[MemoryBank] 检索结果详情:")
            for i, (item, score) in enumerate(filtered_items[:limit]):
                logger.debug(f"  {i+1}. [score={score:.2f}] {item.content[:80]}...")
        else:
            logger.warning(f"[MemoryBank] ✗ 未找到相关记忆 - 查询: '{query}'")
        
        return result
    
    def _deduplicate_memories(self, scored_items: List[tuple]) -> List[tuple]:
        """去除高度相似的记忆"""
        if not scored_items:
            return []
        
        deduplicated = []
        seen_contents = []
        
        for item, score in scored_items:
            content = item.content.lower()
            
            # 检查是否与已有记忆高度相似
            is_duplicate = False
            for seen in seen_contents:
                similarity = self._calculate_similarity(content, seen)
                if similarity >= self.config.similarity_threshold_for_dedup:
                    is_duplicate = True
                    logger.debug(f"Skipping duplicate memory (similarity={similarity:.2f}): {item.content[:40]}...")
                    break
            
            if not is_duplicate:
                deduplicated.append((item, score))
                seen_contents.append(content)
        
        return deduplicated
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """计算两个文本的 Jaccard 相似度"""
        chars1 = set(text1)
        chars2 = set(text2)
        
        if not chars1 or not chars2:
            return 0.0
        
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        return intersection / union if union > 0 else 0.0
    
    async def store(self, knowledge: List[Knowledge]) -> None:
        """
        存储知识到长期记忆

        Args:
            knowledge: 知识列表
        """
        if not knowledge:
            logger.debug("[MemoryBank] 没有知识需要存储")
            return
        
        logger.info(f"[MemoryBank] 开始存储知识 - 收到 {len(knowledge)} 条知识项")
        logger.info("")
        
        if self._updater:
            self._local_cache = await self._updater.update(self._local_cache, knowledge)
            logger.info("")
            return

        await self._store_internal(knowledge)
    
    async def _store_internal(self, knowledge: List[Knowledge]) -> None:
        """当插件不可用时，知识存储的内部实现（回退方案）"""
        
        filtered_knowledge = []
        for k in knowledge:
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
                logger.debug(f"[MemoryBank] ✗ 过滤低质量知识: [{k.type.value}] {k.content[:50]}... (置信度={k.confidence:.2f})")
        
        if len(filtered_knowledge) < len(knowledge):
            logger.info(f"[MemoryBank] 质量过滤: {len(knowledge)} → {len(filtered_knowledge)} 条知识")
        
        new_knowledge = []
        for k in filtered_knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"

            is_duplicate = False
            for existing in self._local_cache:
                if self._is_similar(formatted_content, existing.content):
                    logger.debug(f"[MemoryBank] ✗ 跳过重复知识: {formatted_content[:50]}...")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                new_knowledge.append(k)
                item_metadata = {**k.metadata, 'type': k.type.value}
                self._local_cache.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    embeddings=k.embeddings,
                    metadata=item_metadata
                ))
                logger.debug(f"[MemoryBank] ✓ 已存储: {formatted_content[:80]}...")
        
        if not new_knowledge:
            logger.info("[MemoryBank] 所有知识项均为重复或低质量，未存储新内容")
            logger.info("")
            return
        
        logger.info("")
        logger.info(f"[MemoryBank] ✓ 存储完成 - 新增 {len(new_knowledge)} 条知识 (过滤 {len(knowledge) - len(new_knowledge)} 条)")
        logger.info(f"[MemoryBank] 当前记忆库总计: {len(self._local_cache)} 条记忆")
        logger.info("")
        
        # 注意：记忆服务存储功能已禁用（需要外部服务支持）
        # 当前所有知识仅存储在本地缓存中
        if self.memory_service:
            logger.debug("[MemoryBank] Memory Service 可用但外部存储未实现 - 仅使用本地缓存")
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """检查两个文本是否相似（支持中文）"""
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip()

        if not clean1 or not clean2:
            return False

        if clean1 in clean2 or clean2 in clean1:
            return True

        chars1 = set(clean1.lower())
        chars2 = set(clean2.lower())

        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}

        if not chars1 or not chars2:
            return False

        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)

        similarity = intersection / union if union > 0 else 0

        return similarity > 0.7
    
    async def seed(self, facts: List[str]) -> None:
        """
        植入记忆种子
        
        在初始化时植入预定义的知识，作为长期记忆的基础。
        
        Args:
            facts: 事实字符串列表
        """
        if not facts:
            logger.debug("No facts to seed")
            return
        
        valid_facts = [f.strip() for f in facts if f.strip() and len(f.strip()) > 3]
        if not valid_facts:
            logger.debug("All facts are empty or too short, skipping seed")
            return
        
        logger.info(f"Seeding {len(valid_facts)} facts into long-term memory...")

        for fact in valid_facts:
            item = ContextItem(
                content=f"[预设知识] {fact}",
                source=ContextSource.MEMORY,
                score=1.0,
                metadata={'seeded': True}
            )
            self._local_cache.append(item)
            logger.debug(f"  Added to cache: {item.content}")
        
        logger.info(f"✓ Added {len(valid_facts)} seed facts to local cache (total cache size: {len(self._local_cache)})")

        if not self.memory_service:
            logger.debug("Memory service is not configured, seeds stored in local cache only")
            logger.info(f"Successfully seeded {len(valid_facts)} facts to local cache")
            return
        
        # 注意：记忆服务存储功能已禁用（需要外部服务支持）
        logger.info(f"Successfully seeded {len(valid_facts)} facts to local cache (external storage not available)")
    
    def get_memory_cache(self) -> List[ContextItem]:
        """
        获取本地记忆缓存的完整内容
        
        用于调试模式下查看所有已存储的长期记忆。
        
        Returns:
            本地缓存中所有的上下文条目列表
        """
        return list(self._local_cache)
    
    def create_memory_note(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        keywords: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
    ) -> MemoryNote:
        """
        创建结构化记忆笔记

        自动提取关键词、生成描述、建立关联。

        Args:
            content: 记忆内容
            memory_type: 记忆类型（工作/语义/情节）
            keywords: 关键词列表（可选，不提供则自动提取）
            tags: 标签列表（可选）
            importance: 初始重要性分数

        Returns:
            创建的MemoryNote对象
        """
        note_id = str(uuid.uuid4())[:8]
        
        if keywords is None:
            keywords = self._extract_keywords(content)

        description = self._generate_description(content, memory_type)
        
        note = MemoryNote(
            content=content,
            memory_type=memory_type.value,
            metadata={
                'id': note_id,
                'keywords': keywords,
                'tags': tags or [],
                'description': description,
                'importance_score': importance,
                'linked_memories': [],
                'access_count': 0,
            }
        )
        
        self._link_related_memories(note, note_id, keywords)

        self._memory_notes[note_id] = note

        self._local_cache.append(ContextItem(
            content=content,
            source=ContextSource.MEMORY,
            score=importance,
            metadata=note.metadata
        ))
        
        logger.debug(f"Created memory note {note_id}: {content[:50]}... "
                    f"(keywords: {keywords}, links: {len(note.metadata.get('linked_memories', []))})")
        
        return note
    
    def _extract_keywords(self, content: str) -> List[str]:
        """从内容中提取关键词"""
        cleaned = re.sub(r'[^\w\s]', ' ', content)
        words = cleaned.split()

        keywords = [w for w in words if len(w) >= 2 and w not in STOPWORDS]

        seen = set()
        unique = []
        for w in keywords:
            if w not in seen:
                seen.add(w)
                unique.append(w)

        return unique[:5]
    
    def _generate_description(self, content: str, memory_type: MemoryType) -> str:
        """生成语义描述"""
        type_labels = {
            MemoryType.SEMANTIC: "知识记录",
            MemoryType.KEYWORD: "关键词记录",
            MemoryType.STRUCTURED: "结构化记录",
        }
        label = type_labels.get(memory_type, "记忆")

        short_content = content[:50] + "..." if len(content) > 50 else content
        return f"{label}: {short_content}"
    
    def _link_related_memories(self, note: MemoryNote, note_id: str, keywords: List[str]) -> None:
        """
        查找并建立与现有记忆的关联

        基于关键词重叠度判断语义相关性。
        Requires at least 2 keyword overlaps to form a link; a single shared word
        is too common to signal genuine relatedness and would create a noisy graph.
        Linked memories receive a 10% importance boost since co-activation suggests
        they form a coherent knowledge cluster.
        """
        if not self._memory_notes:
            return
        
        note_keywords = set(keywords)
        linked_memories = []
        
        for existing_id, existing in self._memory_notes.items():
            existing_keywords = set(existing.metadata.get('keywords', []))
            overlap = len(note_keywords & existing_keywords)
            
            if overlap >= 2:  # 至少 2 个共同关键词才建立关联，避免虚假链接
                linked_memories.append(existing_id)
                existing_links = existing.metadata.get('linked_memories', [])
                if note_id not in existing_links:
                    existing_links.append(note_id)
                    existing.metadata['linked_memories'] = existing_links

                current_importance = existing.metadata.get('importance_score', 0.5)
                # 与新记忆共同激活表明该记忆属于某个知识簇；
                # 提升 10% 重要性以抵抗演化过程中的遗忘。
                existing.metadata['importance_score'] = min(1.0, current_importance * 1.1)
        
        note.metadata['linked_memories'] = linked_memories
    
    def retrieve_memory_notes(
        self,
        query: str,
        memory_types: Optional[List[str]] = None,
        limit: int = 5,
    ) -> List[MemoryNote]:
        """
        检索相关的记忆笔记
        
        支持按类型过滤，返回按重要性排序的结果。
        
        Args:
            query: 查询字符串
            memory_types: 限定的记忆类型（可选）
            limit: 返回的最大数量
            
        Returns:
            相关的MemoryNote列表
        """
        if not self._memory_notes:
            return []
        
        query_words = set(query.lower().split())
        scored_notes = []
        
        for note in self._memory_notes.values():
            if memory_types and note.memory_type not in memory_types:
                continue

            content_lower = note.content.lower()

            if query.lower() in content_lower:
                score = 0.9
            else:
                note_keywords = set(k.lower() for k in note.metadata.get('keywords', []))
                overlap = len(query_words & note_keywords)
                if overlap > 0:
                    score = 0.5 + (overlap / max(len(query_words), len(note_keywords))) * 0.4
                else:
                    content_words = set(content_lower.split())
                    overlap = len(query_words & content_words)
                    if overlap > 0:
                        score = 0.3 + (overlap / max(len(query_words), len(content_words))) * 0.3
                    else:
                        score = 0

            importance = note.metadata.get('importance_score', 0.5)
            # 70% 查询相关性 + 30% 内在重要性：防止高频但查询无关的记忆
            # 挤占更相关的检索结果。
            final_score = score * 0.7 + importance * 0.3
            
            if final_score > 0:
                scored_notes.append((note, final_score))
        
        scored_notes.sort(key=lambda x: x[1], reverse=True)

        result = []
        for note, _ in scored_notes[:limit]:
            access_count = note.metadata.get('access_count', 0)
            note.metadata['access_count'] = access_count + 1
            note.metadata['last_accessed'] = datetime.now()
            result.append(note)
        
        return result
    
    def evolve_memories(self) -> int:
        """
        记忆演化：更新重要性、淘汰低价值记忆
        
        模拟人类记忆的遗忘和巩固机制。
        
        Returns:
            被淘汰的记忆数量
        """
        if not self._memory_notes:
            return 0
        
        # 每轮 2% 衰减近似艾宾浩斯遗忘曲线的周级时间尺度；
        # 被主动检索的记忆通过 _link_related_memories 和 retrieve_memory_notes
        # 中的重要性提升机制来抵抗遗忘。
        decay_factor = 0.98
        for note in self._memory_notes.values():
            current_importance = note.metadata.get('importance_score', 0.5)
            note.metadata['importance_score'] = current_importance * decay_factor
        
        removed = 0
        # 最少保留 10 条记忆，维持最小可用工作集。
        if len(self._memory_notes) > 10:
            sorted_notes = sorted(
                self._memory_notes.items(),
                key=lambda x: x[1].metadata.get('importance_score', 0.5)
            )

            # 衰减至 0.1 以下的记忆视为已遗忘
            threshold = 0.1
            to_remove = []
            
            for note_id, note in sorted_notes:
                importance = note.metadata.get('importance_score', 0.5)
                if importance < threshold and len(self._memory_notes) - len(to_remove) > 10:
                    to_remove.append(note_id)
            
            for note_id in to_remove:
                removed_note = self._memory_notes.pop(note_id)
                self._local_cache = [
                    item for item in self._local_cache
                    if item.metadata.get('id') != note_id
                ]
                removed += 1
        
        if removed > 0:
            logger.debug(f"Memory evolution: removed {removed} low-value memories")
        
        return removed
    
    def get_memory_notes(self) -> List[MemoryNote]:
        """
        获取所有结构化记忆笔记
        
        用于调试模式下查看完整记忆库。
        
        Returns:
            所有记忆笔记列表
        """
        return list(self._memory_notes.values())
    
    def get_memory_statistics(self) -> Dict[str, Any]:
        """
        获取记忆系统统计信息
        
        Returns:
            统计信息字典
        """
        notes = list(self._memory_notes.values())
        
        if not notes:
            return {
                'total_notes': 0,
                'by_type': {},
                'avg_importance': 0,
                'total_links': 0,
            }
        
        by_type = {}
        for note in notes:
            type_name = note.memory_type
            by_type[type_name] = by_type.get(type_name, 0) + 1

        avg_importance = sum(n.metadata.get('importance_score', 0.5) for n in notes) / len(notes)

        total_links = sum(len(n.metadata.get('linked_memories', [])) for n in notes)
        
        return {
            'total_notes': len(notes),
            'by_type': by_type,
            'avg_importance': round(avg_importance, 3),
            'total_links': total_links,
        }
    
    @staticmethod
    def _content_to_text(content: Any) -> str:
        """将内容转换为文本"""
        if isinstance(content, str):
            return content
        elif hasattr(content, 'text'):
            return content.text
        elif hasattr(content, 'content'):
            return str(content.content)
        else:
            return str(content)
    
    @staticmethod
    def _new_invocation_id() -> str:
        """生成新的调用 ID"""
        return str(uuid.uuid4())
