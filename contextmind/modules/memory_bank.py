"""
MemoryBank - 记忆库模块

职责：
- 长期记忆存储
- 记忆检索与召回
- 持久化用户事实/偏好

可插拔策略：
- VectorDB存储
- Locator机制
- User Memory持久化

上下文工程核心能力：
- 长期记忆存储和检索
- 跨会话的知识持久化
- 基于语义相似度的记忆检索
- 本地缓存提供备用检索
- 记忆热度评估和动态淘汰
"""

from typing import List, Optional, Dict, Any
import uuid
import re

from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.events.event import Event
from google.adk.sessions.base_session_service import BaseSessionService
from google.genai.types import Content, Part

from ..data_models import ContextItem, ContextSource, Knowledge, MemoryNote, MemoryType
from ..logger import get_logger

logger = get_logger(__name__)

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
    
    提供长期记忆的存储、检索和管理功能，是上下文优化框架的核心组件之一。
    
    v3.2 Agent Memory System 架构：
    基于A-MEM（Agentic Memory）设计，实现智能记忆管理。
    
    三层记忆模型：
    1. 工作记忆（Working Memory）：当前任务的即时上下文，由Session管理
    2. 语义记忆（Semantic Memory）：结构化知识网络，包含关键词、标签、链接
    3. 情节记忆（Episodic Memory）：时间序列的事件历史，支持因果链追溯
    
    核心功能：
    - 检索相关记忆（支持语义搜索和关键词备用）
    - 存储结构化记忆笔记（MemoryNote）
    - 记忆演化：热度评估、动态淘汰、链接更新
    - 知识网络构建：自动建立记忆间的语义关联
    
    Attributes:
        memory_service: ADK Memory Service 实例（可选）
        app_name: 应用名称
        user_id: 用户ID
        session_service: Session Service 实例（用于创建临时会话）
        _memory_notes: 结构化记忆笔记存储（MemoryNote）
        _local_cache: 本地记忆缓存，用于备用检索（兼容）
    """
    
    def __init__(
        self,
        memory_service: Optional[BaseMemoryService],
        session_service: Optional[BaseSessionService],
        app_name: str,
        user_id: str,
    ):
        """
        初始化记忆管理器
        
        Args:
            memory_service: ADK Memory Service 实例，如果为None则不使用长期记忆
            session_service: Session Service 实例，用于创建临时会话
            app_name: 应用名称
            user_id: 用户ID
        """
        self.memory_service = memory_service
        self.session_service = session_service
        self.app_name = app_name
        self.user_id = user_id
        
        # v3.2 Agent Memory System: 结构化记忆笔记存储
        self._memory_notes: Dict[str, MemoryNote] = {}
        
        # 本地缓存：存储所有已存储的知识，用于备用检索（兼容旧接口）
        self._local_cache: List[ContextItem] = []
    
    async def retrieve(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        检索相关记忆
        
        根据查询字符串从长期记忆中检索相关的上下文信息。
        支持两种检索方式：
        1. 优先使用 Memory Service 的语义搜索
        2. 如果语义搜索无结果，使用本地缓存的关键词匹配
        
        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量
            
        Returns:
            上下文条目列表，按相关性排序
        """
        logger.debug(f"retrieve() called with query='{query}', limit={limit}")
        logger.debug(f"Memory service configured: {self.memory_service is not None}, Cache size: {len(self._local_cache)}")
        
        if not self.memory_service:
            logger.debug("Memory service is not configured, using local cache")
            return self._retrieve_from_cache(query, limit)
        
        try:
            # 调用 Memory Service 搜索
            response = await self.memory_service.search_memory(
                app_name=self.app_name,
                user_id=self.user_id,
                query=query
            )
            
            if response and response.memories:
                # 转换为 ContextItem
                items = []
                for memory in response.memories[:limit]:
                    content = self._content_to_text(memory.content)
                    if not content:
                        continue
                    
                    items.append(ContextItem(
                        content=content,
                        source=ContextSource.MEMORY,
                        score=1.0,  # ADK不提供分数，默认为1.0
                        timestamp=memory.timestamp if hasattr(memory, 'timestamp') else None,
                        metadata={}
                    ))
                
                if items:
                    logger.info(f"✓ Retrieved {len(items)} memories from Memory Service")
                    return items
            
            # Memory Service 未返回结果，使用本地缓存备用
            logger.debug(f"No memories from Memory Service, falling back to local cache (size={len(self._local_cache)})")
            return self._retrieve_from_cache(query, limit)
            
        except Exception as e:
            logger.warning(f"Failed to retrieve memories from Memory Service: {str(e)}, using local cache")
            return self._retrieve_from_cache(query, limit)
    
    def _retrieve_from_cache(self, query: str, limit: int = 5) -> List[ContextItem]:
        """
        从本地缓存检索相关记忆
        
        使用简单的关键词匹配进行检索，支持中文。
        优先返回相关记忆，如果没有相关的则返回所有记忆。
        
        Args:
            query: 查询字符串
            limit: 返回的最大记忆数量
            
        Returns:
            匹配的上下文条目列表
        """
        logger.debug(f"_retrieve_from_cache called with query='{query}', cache size={len(self._local_cache)}")
        
        if not self._local_cache:
            logger.warning("Local cache is empty! No memories to retrieve.")
            return []
        
        query_lower = query.lower()
        
        # 计算每个缓存项的相关性分数
        scored_items = []
        for item in self._local_cache:
            content_lower = item.content.lower()
            
            # 方法1: 完整匹配
            if query_lower in content_lower or content_lower in query_lower:
                score = 0.9
            # 方法2: 字符重叠（对中文更有效）
            else:
                # 对于中文，按字符而非词语计算重叠
                query_chars = set(query_lower)
                content_chars = set(content_lower)
                overlap = len(query_chars & content_chars)
                
                # 至少有一个字符重叠才考虑
                if overlap > 0:
                    # 计算Jaccard相似度
                    union = len(query_chars | content_chars)
                    similarity = overlap / union if union > 0 else 0
                    score = 0.2 + similarity * 0.7  # 基础分0.2，最高0.9
                else:
                    score = 0.1  # 即使没有重叠，也给一个基础分
            
            scored_items.append((item, score))
        
        # 按分数排序
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # 返回前limit个（总是返回一些记忆，即使分数低）
        result = [
            ContextItem(
                content=item.content,
                source=item.source,
                score=score,
                timestamp=item.timestamp,
                metadata=item.metadata
            )
            for item, score in scored_items[:limit]
        ]
        
        if result:
            logger.info(f"✓ Retrieved {len(result)} memories from local cache (top score: {scored_items[0][1]:.2f})")
            for i, (item, score) in enumerate(scored_items[:limit]):
                logger.debug(f"  Memory {i+1} (score={score:.2f}): {item.content[:60]}...")
        else:
            logger.error(f"ERROR: scored_items is empty even though cache has {len(self._local_cache)} items!")
        
        return result
    
    async def store(self, knowledge: List[Knowledge]) -> None:
        """
        存储知识到长期记忆
        
        将提取的知识存储到长期记忆中，供后续检索使用。
        自动去重，避免存储重复的知识。
        同时存储到本地缓存，确保备用检索可用。
        
        Args:
            knowledge: 知识列表
        """
        if not knowledge:
            logger.debug("No knowledge to store")
            return
        
        # 去重：检查是否已存在相似的知识
        new_knowledge = []
        for k in knowledge:
            formatted_content = f"[{k.type.value.upper()}] {k.content}"
            
            # 检查是否已存在相似内容
            is_duplicate = False
            for existing in self._local_cache:
                # 简单的相似度检查：如果内容高度相似，认为是重复
                if self._is_similar(formatted_content, existing.content):
                    logger.debug(f"Skipping duplicate knowledge: {formatted_content[:50]}...")
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                new_knowledge.append(k)
                self._local_cache.append(ContextItem(
                    content=formatted_content,
                    source=ContextSource.MEMORY,
                    score=k.confidence,
                    metadata=k.metadata
                ))
        
        if not new_knowledge:
            logger.debug("All knowledge items are duplicates, nothing new to store")
            return
        
        logger.debug(f"Added {len(new_knowledge)} new items to local cache (filtered {len(knowledge) - len(new_knowledge)} duplicates), total: {len(self._local_cache)}")
        
        # 然后尝试存储到 Memory Service
        if not self.memory_service:
            logger.debug("Memory service is not configured, knowledge stored in local cache only")
            return
        
        try:
            # 创建临时会话来存储知识
            session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            
            # 将新知识作为事件添加到会话
            for k in new_knowledge:
                # 格式化知识内容，包含类型标签
                formatted_content = f"[{k.type.value.upper()}] {k.content}"
                
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=formatted_content)]),
                )
                await self.session_service.append_event(session=session, event=event)
            
            # 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(session)
            
            logger.debug(f"Stored {len(new_knowledge)} new knowledge items to Memory Service")
            
        except Exception as e:
            logger.warning(f"Failed to store knowledge to Memory Service: {str(e)}, kept in local cache")
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """
        检查两个文本是否相似（支持中文）
        
        使用字符级别的包含和Jaccard相似度检查。
        
        Args:
            text1: 文本1
            text2: 文本2
            
        Returns:
            是否相似
        """
        # 去除类型标签进行比较
        clean1 = re.sub(r'\[.*?\]\s*', '', text1).strip()
        clean2 = re.sub(r'\[.*?\]\s*', '', text2).strip()
        
        if not clean1 or not clean2:
            return False
        
        # 如果其中一个包含另一个，认为相似
        if clean1 in clean2 or clean2 in clean1:
            return True
        
        # 对于中文，使用字符集合而非词汇
        chars1 = set(clean1.lower())
        chars2 = set(clean2.lower())
        
        # 移除空格和标点
        chars1 = {c for c in chars1 if c.strip() and c not in '，。！？,.!?；:：'}
        chars2 = {c for c in chars2 if c.strip() and c not in '，。！？,.!?；:：'}
        
        if not chars1 or not chars2:
            return False
        
        # 计算Jaccard相似度
        intersection = len(chars1 & chars2)
        union = len(chars1 | chars2)
        
        similarity = intersection / union if union > 0 else 0
        
        # 如果相似度超过70%，认为是重复（提高阈值，减少误判）
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
        
        # 过滤空字符串和过短的事实
        valid_facts = [f.strip() for f in facts if f.strip() and len(f.strip()) > 3]
        if not valid_facts:
            logger.debug("All facts are empty or too short, skipping seed")
            return
        
        logger.info(f"Seeding {len(valid_facts)} facts into long-term memory...")
        
        # 首先添加到本地缓存
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
        
        # 然后尝试添加到 Memory Service
        if not self.memory_service:
            logger.debug("Memory service is not configured, seeds stored in local cache only")
            logger.info(f"Successfully seeded {len(valid_facts)} facts to local cache")
            return
        
        try:
            # 创建临时会话来存储种子知识
            session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )
            
            # 将种子数据作为系统事件添加到会话
            for fact in valid_facts:
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=f"[预设知识] {fact}")]),
                )
                await self.session_service.append_event(session=session, event=event)
            
            # 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(session)
            
            logger.info(f"Successfully seeded {len(valid_facts)} facts to memory")
            
        except Exception as e:
            logger.error(f"Failed to seed memory: {str(e)}, kept in local cache")
    
    @staticmethod
    def _content_to_text(content: Optional[Content]) -> str:
        """将 Content 对象转换为纯文本"""
        if not content or not content.parts:
            return ""
        
        fragments: List[str] = []
        for part in content.parts:
            if part.text:
                fragments.append(part.text)
            elif part.function_call:
                fragments.append(f"[FunctionCall] {part.function_call.name}")
            elif part.function_response:
                fragments.append(f"[FunctionResponse] {part.function_response.name}")
            elif part.code_execution_result:
                fragments.append(part.code_execution_result.output_text or "")
        
        return "\n".join(fragment for fragment in fragments if fragment)
    
    def get_memory_cache(self) -> List[ContextItem]:
        """
        获取本地记忆缓存的完整内容
        
        用于debug模式下查看所有已存储的长期记忆。
        
        Returns:
            本地缓存中所有的上下文条目列表
        """
        return list(self._local_cache)
    
    # =========================================================================
    # v3.2 Agent Memory System - 结构化记忆管理
    # =========================================================================
    
    def create_memory_note(
        self,
        content: str,
        memory_type: MemoryType = MemoryType.SEMANTIC,
        keywords: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        importance: float = 0.5,
    ) -> MemoryNote:
        """
        创建结构化记忆笔记（A-MEM风格）
        
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
        
        # 自动提取关键词（如果未提供）
        if keywords is None:
            keywords = self._extract_keywords(content)
        
        # 生成语义描述
        description = self._generate_description(content, memory_type)
        
        note = MemoryNote(
            id=note_id,
            content=content,
            memory_type=memory_type,
            keywords=keywords,
            tags=tags or [],
            description=description,
            importance_score=importance,
        )
        
        # 查找并建立关联
        self._link_related_memories(note)
        
        # 存储到记忆库
        self._memory_notes[note_id] = note
        
        # 同时添加到本地缓存（兼容）
        self._local_cache.append(note.to_context_item())
        
        logger.debug(f"Created memory note {note_id}: {content[:50]}... "
                    f"(keywords: {keywords}, links: {len(note.linked_memories)})")
        
        return note
    
    def _extract_keywords(self, content: str) -> List[str]:
        """
        从内容中提取关键词
        
        使用简单的规则提取（可扩展为NLP方法）
        """
        # 移除标点
        cleaned = re.sub(r'[^\w\s]', ' ', content)
        words = cleaned.split()
        
        # 过滤停用词和短词（可配置）
        keywords = [w for w in words if len(w) >= 2 and w not in STOPWORDS]
        
        # 去重并取前5个
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
            MemoryType.WORKING: "当前任务上下文",
            MemoryType.SEMANTIC: "知识记录",
            MemoryType.EPISODIC: "事件记录",
        }
        label = type_labels.get(memory_type, "记忆")
        
        # 简单截断作为描述
        short_content = content[:50] + "..." if len(content) > 50 else content
        return f"{label}: {short_content}"
    
    def _link_related_memories(self, note: MemoryNote) -> None:
        """
        查找并建立与现有记忆的关联
        
        基于关键词重叠度判断语义相关性。
        需要至少2个关键词重叠才建立关联（避免过度链接）。
        """
        if not self._memory_notes:
            return
        
        note_keywords = set(note.keywords)
        
        for existing_id, existing in self._memory_notes.items():
            existing_keywords = set(existing.keywords)
            overlap = len(note_keywords & existing_keywords)
            
            # 需要至少2个关键词重叠才建立关联（避免过度链接）
            if overlap >= 2:
                note.add_link(existing_id)
                existing.add_link(note.id)
                
                # 新记忆触发旧记忆的重要性更新
                existing.update_importance()
    
    def retrieve_memory_notes(
        self,
        query: str,
        memory_types: Optional[List[MemoryType]] = None,
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
            # 类型过滤
            if memory_types and note.memory_type not in memory_types:
                continue
            
            # 计算相关性分数
            content_lower = note.content.lower()
            
            # 完整匹配
            if query.lower() in content_lower:
                score = 0.9
            else:
                # 关键词匹配
                note_keywords = set(k.lower() for k in note.keywords)
                overlap = len(query_words & note_keywords)
                if overlap > 0:
                    score = 0.5 + (overlap / max(len(query_words), len(note_keywords))) * 0.4
                else:
                    # 内容词匹配
                    content_words = set(content_lower.split())
                    overlap = len(query_words & content_words)
                    if overlap > 0:
                        score = 0.3 + (overlap / max(len(query_words), len(content_words))) * 0.3
                    else:
                        score = 0
            
            # 结合重要性分数
            final_score = score * 0.7 + note.importance_score * 0.3
            
            if final_score > 0:
                scored_notes.append((note, final_score))
        
        # 按分数排序
        scored_notes.sort(key=lambda x: x[1], reverse=True)
        
        # 标记访问
        result = []
        for note, _ in scored_notes[:limit]:
            note.access()
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
        
        # 更新所有记忆的重要性（时间衰减）
        for note in self._memory_notes.values():
            note.update_importance(decay_factor=0.98)
        
        # 淘汰低价值记忆（保留最少10条）
        removed = 0
        if len(self._memory_notes) > 10:
            # 找出重要性最低的记忆
            sorted_notes = sorted(
                self._memory_notes.items(),
                key=lambda x: x[1].importance_score
            )
            
            # 淘汰阈值
            threshold = 0.1
            to_remove = []
            
            for note_id, note in sorted_notes:
                if note.importance_score < threshold and len(self._memory_notes) - len(to_remove) > 10:
                    to_remove.append(note_id)
            
            # 执行淘汰（同时从_local_cache中移除）
            for note_id in to_remove:
                removed_note = self._memory_notes.pop(note_id)
                # 同步移除_local_cache中的对应条目
                self._local_cache = [
                    item for item in self._local_cache
                    if item.metadata.get('memory_id') != note_id
                ]
                removed += 1
        
        if removed > 0:
            logger.debug(f"Memory evolution: removed {removed} low-value memories")
        
        return removed
    
    def get_memory_notes(self) -> List[MemoryNote]:
        """
        获取所有结构化记忆笔记
        
        用于debug模式下查看完整记忆库。
        
        Returns:
            所有MemoryNote列表
        """
        return list(self._memory_notes.values())
    
    def get_memory_statistics(self) -> Dict[str, any]:
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
        
        # 按类型统计
        by_type = {}
        for note in notes:
            type_name = note.memory_type.value
            by_type[type_name] = by_type.get(type_name, 0) + 1
        
        # 平均重要性
        avg_importance = sum(n.importance_score for n in notes) / len(notes)
        
        # 总链接数
        total_links = sum(len(n.linked_memories) for n in notes)
        
        return {
            'total_notes': len(notes),
            'by_type': by_type,
            'avg_importance': round(avg_importance, 3),
            'total_links': total_links,
        }
    
    @staticmethod
    def _new_invocation_id() -> str:
        """生成新的调用ID"""
        return str(uuid.uuid4())
