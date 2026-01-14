"""
ContextEngine - 上下文引擎核心模块

专注于上下文优化的独立模块，提供会话管理和记忆管理能力。
职责：
- 短期记忆（Session）：管理近期对话历史
- 长期记忆（Memory）：持久化和检索重要知识
- 上下文优化：为应用层提供优化后的上下文数据

不包含：
- Prompt 构建（由应用层负责）
- LLM 调用（由应用层负责）
- 业务逻辑（由应用层负责）
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import json
import re
import string
from typing import List, Optional, Sequence, Tuple
import uuid

from google.adk.events.event import Event
from google.adk.memory import InMemoryMemoryService
from google.adk.memory.base_memory_service import BaseMemoryService
from google.adk.sessions import InMemorySessionService, Session
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
)
from google.genai.types import Content, Part

from .data_models import Message, Memory, ContextResult
from .logger import get_logger

logger = get_logger(__name__)


# 内部数据类用于状态跟踪
class _UserState:
    """内部用户状态跟踪类"""
    def __init__(self):
        self.interaction_count = 0
        self.summary_interval = 5  # 每隔多少轮对话进行一次总结


# =============================================================================
# 工具函数
# =============================================================================

def _content_to_text(content: Optional[Content]) -> str:
    """将 Content 对象转换为纯文本。"""
    if not content or not content.parts:
        return ""

    fragments: List[str] = []
    for part in content.parts:
        if part.text:
            fragments.append(part.text)
        elif part.function_call:
            fragments.append(f"[FunctionCall] {part.function_call.name}")
        elif part.function_response:
            fragments.append(
                f"[FunctionResponse] {part.function_response.name}"
            )
        elif part.code_execution_result:
            fragments.append(part.code_execution_result.output_text or "")
    return "\n".join(fragment for fragment in fragments if fragment)


def _render_events(events: Sequence[Event]) -> str:
    """将事件列表渲染为多行文本。"""
    lines = []
    for event in events:
        text = _content_to_text(event.content).strip()
        if not text:
            continue
        speaker = "User" if event.author == "user" else event.author
        lines.append(f"{speaker}: {text}")
    return "\n".join(lines)


def _render_memory_entries(memories) -> Tuple[str, List[str]]:
    """将记忆检索结果渲染为文本。"""
    if not memories:
        return "", []

    lines = []
    raw_entries: List[str] = []
    for entry in memories:
        text = _content_to_text(entry.content).strip()
        if not text:
            continue
        formatted = f"[{entry.timestamp}] {entry.author}: {text}"
        lines.append(formatted)
        raw_entries.append(formatted)
    return "\n".join(lines), raw_entries


# =============================================================================
# 核心引擎类
# =============================================================================

class ContextEngine:
    """
    上下文引擎核心类 - 专注于上下文优化
    
    该引擎提供独立的上下文优化能力，不包含业务逻辑和 LLM 调用。
    核心功能：
    - 短期记忆（Session）：管理近期对话历史
    - 长期记忆（Memory）：持久化和检索重要知识
    - 上下文优化：返回结构化的上下文数据供应用层使用
    
    使用示例：
        ```python
        from contextmind import ContextEngine, Message, Memory, ContextResult
        from google.adk.memory import InMemoryMemoryService
        
        # 创建引擎
        engine = ContextEngine(
            app_name="my-app",
            user_id="user-123",
            max_recent_events=6,
            memory_service=InMemoryMemoryService(),
        )
        
        # 优化上下文
        context_result = await engine.optimize("用户输入")
        
        # 应用层使用上下文信息构建 Prompt 并调用 LLM
        # ...
        
        # 更新上下文状态
        await engine.update("用户输入", "助手回复")
        ```
    """
    
    # 常量定义
    MIN_FACT_LENGTH = 5  # 有效记忆事实的最小长度

    def __init__(
        self,
        *,
        app_name: str,
        user_id: str,
        session_service: Optional[BaseSessionService] = None,
        memory_service: Optional[BaseMemoryService] = None,
        session_id: Optional[str] = None,
        max_recent_events: int = 6,
        agent_timeout: float = 10.0,
    ):
        """
        初始化上下文引擎
        
        Args:
            app_name: 应用名称，用于区分不同应用的数据
            user_id: 用户ID，用于区分不同用户的数据
            session_service: Session服务实例，默认使用InMemorySessionService
            memory_service: Memory服务实例，默认None（不使用长期记忆）
            session_id: 可选的session ID，不提供则自动创建
            max_recent_events: 保留的最近事件数量，0表示不保留历史
            agent_timeout: 超时控制参数（预留，暂未使用）
        """
        self.app_name = app_name
        self.user_id = user_id
        self._session_id = session_id
        self._max_recent_events = max_recent_events
        self._agent_timeout = agent_timeout

        self._user_state = _UserState()

        self.session_service = session_service or InMemorySessionService()
        self.memory_service = memory_service

    # =============================================================================
    # 核心 API 方法
    # =============================================================================

    async def optimize(self, user_input: str, **kwargs) -> ContextResult:
        """
        优化上下文 - 主要入口方法
        
        根据用户输入，检索相关的对话历史和长期记忆，返回优化后的上下文信息。
        
        Args:
            user_input: 用户输入
            **kwargs: 额外参数（预留扩展）
        
        Returns:
            ContextResult: 包含优化后的上下文信息
        """
        import time
        start_time = time.time()
        
        # 1. 收集对话历史
        recent_history = await self._collect_recent_history_as_messages()
        
        # 2. 检索长期记忆
        long_term_memory = await self._retrieve_memory_as_memories(query=user_input)
        
        # 3. 收集元数据
        metadata = {
            'optimization_time': time.time() - start_time,
            'history_count': len(recent_history),
            'memory_count': len(long_term_memory),
        }
        
        return ContextResult(
            recent_history=recent_history,
            long_term_memory=long_term_memory,
            metadata=metadata
        )

    async def update(
        self,
        user_input: str,
        assistant_response: str,
        metadata: Optional[dict] = None
    ) -> None:
        """
        更新上下文状态
        
        将对话添加到会话历史，提取知识并持久化到长期记忆。
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
            metadata: 额外元数据（预留）
        """
        # 1. 将对话添加到会话
        if self._max_recent_events > 0:
            await self._append_to_session(user_input, assistant_response)
        
        # 2. 提取知识并持久化
        if self.memory_service:
            await self._extract_and_persist_knowledge(user_input, assistant_response)
        
        # 3. 清理旧事件
        if self._max_recent_events > 0:
            await self._cleanup_old_events()
        
        # 4. 定期总结
        if self.memory_service:
            await self._periodic_summary()
        

    # =============================================================================
    # 辅助方法 - 收集上下文信息
    # =============================================================================

    async def _collect_recent_history_as_messages(self) -> List[Message]:
        """收集最近对话历史，返回 Message 列表"""
        try:
            session = await self._fetch_session(num_recent_events=self._max_recent_events)
            
            if not session.events:
                return []
            
            messages = []
            for event in session.events:
                text = _content_to_text(event.content).strip()
                if not text:
                    continue
                
                # 将 event.author 映射到标准角色
                role = "user" if event.author == "user" else "assistant"
                
                messages.append(Message(
                    role=role,
                    content=text,
                    timestamp=event.timestamp if hasattr(event, 'timestamp') else datetime.now(),
                    metadata={'author': event.author}
                ))
            
            return messages
        except Exception as e:
            logger.debug(f"Failed to collect recent history: {str(e)}")
            return []

    async def _retrieve_memory_as_memories(self, *, query: str) -> List[Memory]:
        """检索长期记忆，返回 Memory 列表"""
        if not self.memory_service:
            return []

        try:
            # 构建搜索查询列表
            search_queries = self._build_search_queries(query)
            
            # 并发执行多轮搜索
            all_memories = []
            seen_contents = set()
            
            async def search_single_query(search_query: str):
                """单个查询的搜索函数"""
                try:
                    response = await self.memory_service.search_memory(
                        app_name=self.app_name, user_id=self.user_id, query=search_query
                    )
                    return response.memories if response.memories else []
                except Exception as e:
                    logger.debug(f"Failed to search memory with query '{search_query}': {str(e)}")
                    return []
            
            # 并发执行所有搜索查询（最多5个）
            search_tasks = [search_single_query(q) for q in search_queries[:5]]
            search_results = await asyncio.gather(*search_tasks)
            
            # 收集并去重结果
            for memories in search_results:
                for entry in memories:
                    entry_text = _content_to_text(entry.content).strip()
                    if not entry_text or entry_text in seen_contents:
                        continue
                    
                    seen_contents.add(entry_text)
                    
                    # 计算相关性分数
                    relevance_score = self._calculate_relevance_score(
                        entry_text, query, entry.timestamp
                    )
                    
                    all_memories.append({
                        'entry': entry,
                        'text': entry_text,
                        'score': relevance_score,
                        'timestamp': entry.timestamp
                    })
            
            if not all_memories:
                logger.debug("🔍 长期记忆检索：未找到相关记忆")
                return []

            # 按相关性分数排序
            all_memories.sort(key=lambda x: x['score'], reverse=True)
            
            # 选择最相关的记忆（最多5条）
            top_memories = all_memories[:5]
            
            # 转换为 Memory 对象
            result = []
            for mem in top_memories:
                result.append(Memory(
                    content=mem['text'],
                    source='extracted',  # 从记忆中检索到的
                    timestamp=mem['timestamp'],
                    score=mem['score'],
                    metadata={'author': mem['entry'].author}
                ))
            
            logger.info(f"🧠 检索到 {len(result)} 条长期记忆")
            for i, mem in enumerate(result, 1):
                content_preview = mem.content[:100] + "..." if len(mem.content) > 100 else mem.content
                logger.info(f"  [{i}] {content_preview}")
            
            return result
            
        except Exception as e:
            logger.debug(f"Failed to retrieve memory: {str(e)}")
            return []

    async def _append_to_session(self, user_input: str, assistant_response: str) -> None:
        """将对话添加到会话"""
        try:
            await self._ensure_session()
            session = await self._fetch_session()
            
            # 添加用户输入
            user_event = Event(
                invocation_id=self._new_invocation_id(),
                author="user",
                content=Content(role="user", parts=[Part(text=user_input)]),
            )
            await self.session_service.append_event(session=session, event=user_event)
            
            # 添加助手回复
            assistant_event = Event(
                invocation_id=self._new_invocation_id(),
                author="assistant",
                content=Content(role="assistant", parts=[Part(text=assistant_response)]),
            )
            await self.session_service.append_event(session=session, event=assistant_event)
            
        except Exception as e:
            logger.debug(f"Failed to append to session: {str(e)}")

    async def _extract_and_persist_knowledge(self, user_input: str, assistant_response: str) -> None:
        """从对话中提取知识并持久化到长期记忆"""
        try:
            session = await self._fetch_session()
            
            # 简化的知识提取：直接将对话作为记忆事实
            # 应用层可以通过更高级的方式提取知识
            facts_to_store = []
            
            # 将对话总结作为一条记忆
            summary = f"用户说: {user_input[:50]}... 回复: {assistant_response[:50]}..."
            facts_to_store.append(f"[对话记录] {summary}")
            
            # 将提取的知识作为独立事件存储到记忆中
            if facts_to_store:
                knowledge_session = await self.session_service.create_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                )
                
                for fact in facts_to_store:
                    event = Event(
                        invocation_id=self._new_invocation_id(),
                        author="system",
                        content=Content(role="system", parts=[Part(text=fact)]),
                    )
                    await self.session_service.append_event(session=knowledge_session, event=event)
                
                # 将知识 session 持久化到 Memory Service
                await self.memory_service.add_session_to_memory(knowledge_session)
                
                logger.debug(f"💾 Persisted {len(facts_to_store)} knowledge facts to memory.")
                
        except Exception as e:
            logger.warning(f"Failed to persist knowledge to memory: {str(e)}")

    # =============================================================================
    # 公共接口方法 - 种子数据和辅助功能
    # =============================================================================

    async def seed_memory(self, facts: List[str]):
        """
        为长期记忆添加种子数据
        
        将预定义的知识事实添加到长期记忆中，供后续检索使用。
        
        Args:
            facts: 需要作为记忆存储的事实列表
            
        Raises:
            ValueError: 如果 facts 为空或包含无效数据
        """
        if not self.memory_service:
            logger.warning("Memory service is not configured, cannot seed memory.")
            return
        
        if not facts:
            logger.warning("No facts provided to seed memory.")
            return
        
        # 过滤掉空字符串（使用 walrus operator 避免重复调用 strip）
        valid_facts = [stripped for f in facts if (stripped := f.strip()) and len(stripped) > self.MIN_FACT_LENGTH]
        if not valid_facts:
            logger.warning("All provided facts are empty or too short, skipping seed.")
            return

        logger.info(f"🧠 Seeding {len(valid_facts)} facts into long-term memory...")

        try:
            # 创建一个专门的 session 来存储种子知识
            seed_session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )

            # 将种子数据作为系统事件添加到 session
            for fact in valid_facts:
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=f"[预设知识] {fact}")]),
                )
                await self.session_service.append_event(session=seed_session, event=event)
            
            # 关键修复：将 session 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(seed_session)
            
            logger.info(f"✅ {len(valid_facts)} facts seeded and persisted to memory successfully.")

        except Exception as e:
            logger.error(f"❌ Failed to seed memory: {e}")

    # =============================================================================
    # 内部辅助方法 - 记忆检索相关
    # =============================================================================

    def _build_search_queries(self, query: str) -> List[str]:
        """构建多个搜索查询以提高检索召回率"""
        search_queries = [query]
        
        # 关键词列表：重要的业务相关词汇
        MEMORY_SEARCH_KEYWORDS = [
            "骚扰", "报警", "拒绝", "烦", "不要", "停止", "备注",
            "投诉", "满意", "同意", "申请", "额度", "还款", "逾期",
            "利息", "费用", "客服", "服务", "问题", "解决"
        ]
        
        # 如果查询较长，提取包含的关键词
        if len(query) > 10:
            matched_keywords = [kw for kw in MEMORY_SEARCH_KEYWORDS if kw in query]
            search_queries.extend(matched_keywords[:2])
        
        # 如果查询很短，添加通用查询
        if len(query) < 5:
            search_queries.extend(["用户", "对话", "历史"])
        
        # 添加语义相关的查询
        semantic_variants = self._get_semantic_variants(query)
        search_queries.extend(semantic_variants[:2])
        
        return search_queries

    def _get_semantic_variants(self, query: str) -> List[str]:
        """生成语义相关的查询变体"""
        variants = []
        
        # 情绪相关变体
        emotion_keywords = {
            "生气": ["愤怒", "不满", "烦躁"],
            "不满": ["抱怨", "投诉", "意见"],
            "同意": ["接受", "可以", "好的"],
            "拒绝": ["不要", "不行", "不需要"],
            "担心": ["顾虑", "疑问", "不确定"]
        }
        
        for emotion, synonyms in emotion_keywords.items():
            if emotion in query:
                variants.extend(synonyms[:2])
                break
        
        # 业务相关变体
        business_keywords = {
            "额度": ["借款", "贷款", "资金"],
            "还款": ["还钱", "付钱", "偿还"],
            "费用": ["利息", "成本", "花费"],
            "申请": ["办理", "开通", "使用"]
        }
        
        for keyword, synonyms in business_keywords.items():
            if keyword in query:
                variants.extend(synonyms[:2])
                break
        
        return variants

    def _calculate_relevance_score(self, memory_text: str, query: str, timestamp) -> float:
        """计算记忆与查询的相关性分数"""
        score = 0.0
        
        # 1. 关键词匹配分数（权重：0.4）
        query_lower = query.lower()
        memory_lower = memory_text.lower()
        
        # 完全匹配
        if query_lower in memory_lower:
            score += 0.4
        else:
            # 部分匹配
            query_words = set(query_lower.split())
            memory_words = set(memory_lower.split())
            overlap = len(query_words & memory_words)
            if query_words:
                score += 0.4 * (overlap / len(query_words))
        
        # 2. 重要性标签分数（权重：0.3）
        importance_tags = {
            "[重要事实]": 0.3,
            "[关键事件]": 0.3,
            "[对话总结]": 0.25,
            "[情绪状态]": 0.2,
            "[用户偏好]": 0.2
        }
        
        for tag, tag_score in importance_tags.items():
            if tag in memory_text:
                score += tag_score
                break
        
        # 3. 时间衰减分数（权重：0.3）
        try:
            now = datetime.now()
            memory_time = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
            time_diff = (now - memory_time).total_seconds()
            
            # 时间衰减：越近的记忆分数越高
            # 1天内：1.0，7天内：0.8，30天内：0.6，更久：0.4
            if time_diff < 86400:  # 1天
                time_score = 1.0
            elif time_diff < 604800:  # 7天
                time_score = 0.8
            elif time_diff < 2592000:  # 30天
                time_score = 0.6
            else:
                time_score = 0.4
            
            score += 0.3 * time_score
        except Exception:
            # 如果时间解析失败，给予中等分数
            score += 0.15
        
        return score

    # =============================================================================
    # 内部辅助方法 - 总结和清理
    # =============================================================================
        
        for tag, tag_score in importance_tags.items():
            if tag in memory_text:
                score += tag_score
                break
        
        # 3. 时间衰减分数（权重：0.3）
        try:
            from datetime import datetime
            now = datetime.now()
            memory_time = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
            time_diff = (now - memory_time).total_seconds()
            
            # 时间衰减：越近的记忆分数越高
            # 1天内：1.0，7天内：0.8，30天内：0.6，更久：0.4
            if time_diff < 86400:  # 1天
                time_score = 1.0
            elif time_diff < 604800:  # 7天
                time_score = 0.8
            elif time_diff < 2592000:  # 30天
                time_score = 0.6
            else:
                time_score = 0.4
            
            score += 0.3 * time_score
        except Exception:
            # 如果时间解析失败，给予中等分数
            score += 0.15
        
        return score

    async def _periodic_summary(self) -> None:
        """定期总结 - 简化版本，不依赖 LLM
        
        在新架构中，总结由应用层负责。这里只是一个占位方法。
        """
        if not self.memory_service:
            return

        interval = self._user_state.summary_interval
        if interval <= 0:
            return

        if self._user_state.interaction_count % interval != 0:
            return

        # 总结功能由应用层实现
        logger.debug(f"Periodic summary interval reached (every {interval} turns)")

    async def _cleanup_old_events(self) -> None:
        """
        清理旧的事件，只保留最近的 _max_recent_events 个事件
        
        注意：InMemorySessionService 不支持直接修改 session.events，
        因此需要创建新 session 并复制最近的 events。
        这会导致 session_id 变化，但这是当前 ADK API 的限制。
        """
        if self._max_recent_events <= 0:
            return
        
        try:
            # 获取完整的session
            session = await self._fetch_session()
            
            # 如果事件数量超过限制，需要清理
            if session.events and len(session.events) > self._max_recent_events:
                # 创建一个新的session，只保留最近的事件
                old_events = session.events
                recent_events = old_events[-self._max_recent_events:]
                
                # 创建新session
                new_session = await self.session_service.create_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                )
                
                # 将最近的事件添加到新session
                for event in recent_events:
                    await self.session_service.append_event(session=new_session, event=event)
                
                # 更新session_id
                self._session_id = new_session.id
                logger.debug(f"🗑️  清理完成，保留最近 {len(recent_events)} 个事件")
        except Exception as e:
            logger.warning(f"Failed to cleanup old events: {str(e)}")

    async def _ensure_session(self) -> None:
        """确保 Session 已存在，若无则创建。"""
        if self._session_id:
            try:
                session = await self.session_service.get_session(
                    app_name=self.app_name,
                    user_id=self.user_id,
                    session_id=self._session_id,
                )
                if session:
                    return
            except Exception as e:
                logger.debug(f"Failed to get existing session: {str(e)}")
                pass
        
        session = await self.session_service.create_session(
            app_name=self.app_name,
            user_id=self.user_id,
        )
        self._session_id = session.id

    async def _fetch_session(
        self,
        num_recent_events: Optional[int] = None,
    ) -> Session:
        """根据需要获取完整会话或最近事件视图。"""
        if not self._session_id:
            raise RuntimeError("Session has not been initialized.")

        config = None
        if num_recent_events is not None:
            config = GetSessionConfig(num_recent_events=num_recent_events)

        session = await self.session_service.get_session(
            app_name=self.app_name,
            user_id=self.user_id,
            session_id=self._session_id,
            config=config,
        )
        if not session:
            raise RuntimeError("Unable to load session from SessionService.")
        return session


    @staticmethod
    def _new_invocation_id() -> str:
        """生成新的调用 ID"""
        return str(uuid.uuid4())

    # =============================================================================
    # 公共接口方法
    # =============================================================================

    async def get_current_session(self) -> Session:
        """获取当前会话（公共方法）"""
        return await self._fetch_session()

    def get_interaction_count(self) -> int:
        """获取当前交互次数"""
        return self._user_state.interaction_count

    def reset_user_state(self) -> None:
        """重置用户状态计数器"""
        self._user_state = _UserState()

