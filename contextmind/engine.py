"""
ContextEngine - 上下文引擎核心模块

基于 Google ADK 的上下文工程核心实现，实现多轮对话的短期记忆（Session）和长期记忆（Memory）管理。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import json
import re
import string
import textwrap
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

from .client import Client
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class UserState:
    """用户状态跟踪类。"""
    interaction_count: int = 0
    last_response_quality: int = 3
    summary_interval: int = 5  # 每隔多少轮对话进行一次总结


@dataclass
class ContextTurnResult:
    """单轮对话执行后的结构化结果。"""
    prompt: str
    reasoning: str
    response: str
    memory_hits: List[str] = field(default_factory=list)
    # 新增字段用于日志展示
    history_count: int = 0
    profile_summary: str = ""
    rules_count: int = 0
    memory_count: int = 0
    turn_number: int = 0
    processing_time: float = 0.0


@dataclass
class IntegratedKnowledge:
    """整合后的上下文知识结构。"""
    user_input: str
    history_text: str
    memory_text: str
    preset_info: str
    extended_context: str
    base_system_prompt: str
    user_profile: dict
    business_rules: dict
    temporal_context: dict


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
    """上下文引擎核心类，负责串联 ADK Session/Memory 与大模型客户端。"""

    def __init__(
        self,
        *,
        app_name: str,
        user_id: str,
        llm_client: "Client",
        session_service: Optional[BaseSessionService] = None,
        memory_service: Optional[BaseMemoryService] = None,
        session_id: Optional[str] = None,
        max_recent_events: int = 6,
        base_system_prompt: str = "",
        user_profile: Optional[dict] = None,
        business_rules: Optional[dict] = None,
        temporal_context: Optional[dict] = None,
        use_preset_info: bool = True,
    ):
        """初始化上下文引擎。"""
        self.app_name = app_name
        self.user_id = user_id
        self._session_id = session_id
        self._llm_client = llm_client
        self._max_recent_events = max_recent_events
        self.base_system_prompt = base_system_prompt
        self.use_preset_info = use_preset_info

        # 扩展上下文信息
        self.user_profile = user_profile or {}
        self.business_rules = business_rules or {}
        self.temporal_context = temporal_context

        self.user_state = UserState()

        self.session_service = session_service or InMemorySessionService()
        self.memory_service = memory_service or InMemoryMemoryService()

    def _get_current_temporal_context(self) -> dict:
        """获取当前时间上下文信息。"""
        now = datetime.now()
        return {
            "当前时间": now.strftime("%Y-%m-%d %H:%M:%S"),
            "时区": "北京时间",
            "工作日/周末": "工作日" if now.weekday() < 5 else "周末",
        }

    def get_temporal_context(self) -> dict:
        """获取时间上下文，优先使用预设值，否则使用当前时间。"""
        return self.temporal_context or self._get_current_temporal_context()

    # =============================================================================
    # 主要处理流程
    # =============================================================================

    async def process_turn(self, user_input: str) -> ContextTurnResult:
        """处理单轮对话的核心流程。"""
        import time
        start_time = time.time()
        
        # 1. 验证输入
        user_input = user_input.strip()
        if not user_input:
            raise ValueError("User input must be non-empty.")

        # 2. 确保 Session 存在
        try:
            await self._ensure_session()
        except Exception as e:
            raise RuntimeError(f"Failed to ensure session: {str(e)}") from e

        # 3. 更新交互次数
        self.user_state.interaction_count += 1

        # 4. 将用户输入写入 Session（仅当需要保留历史时）
        if self._max_recent_events > 0:
            try:
                session = await self._fetch_session()
                user_event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="user",
                    content=Content(role="user", parts=[Part(text=user_input)]),
                )
                await self.session_service.append_event(session=session, event=user_event)
            except Exception as e:
                raise RuntimeError(f"Failed to append user event to session: {str(e)}") from e

        # 5. 收集上下文信息
        try:
            history_text = await self._collect_recent_history()
            memory_text, memory_hits = await self._retrieve_memory(query=user_input)
        except Exception as e:
            history_text = ""
            memory_text = ""
            memory_hits = []

        # 6. 整合上下文为知识
        knowledge = await self.integrate_context_to_knowledge(
            user_input=user_input,
            history_text=history_text,
            memory_text=memory_text
        )

        # 7. 生成 prompt
        prompt = await self.generate_prompt_from_knowledge(knowledge)

        # 8. 调用 LLM 生成回复（带重试机制）
        response = await self._generate_response_with_retry(prompt)

        # 9. 将回复写入 Session（仅当需要保留历史时）
        if self._max_recent_events > 0:
            try:
                assistant_event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="assistant",
                    content=Content(role="assistant", parts=[Part(text=response)]),
                )
                session = await self._fetch_session()
                await self.session_service.append_event(
                    session=session, event=assistant_event
                )
                
                # 清理旧的事件，只保留最近的 _max_recent_events 个事件
                await self._cleanup_old_events()
            except Exception as e:
                logger.debug(f"Failed to append assistant event to session: {str(e)}")

        # 10. 持久化 Session 到 Memory
        try:
            await self._persist_session_to_memory()
        except Exception as e:
            logger.debug(f"Failed to persist session to memory: {str(e)}")

        # 11. 定期总结（如果需要）
        try:
            await self._periodic_summary()
        except Exception as e:
            logger.debug(f"Failed to perform periodic summary: {str(e)}")

        # 12. 收集元数据用于日志展示
        processing_time = time.time() - start_time
        
        # 计算历史数量
        history_count = 0
        try:
            session = await self._fetch_session()
            history_count = len(session.events) if session.events else 0
        except Exception:
            pass
        
        # 提取用户画像摘要
        profile_summary = ""
        if self.user_profile and self.user_profile.get("姓名"):
            profile_summary = self.user_profile.get("姓名", "")
        
        # 计算规则数量
        rules_count = len(self.business_rules) if self.business_rules else 0
        
        # 计算记忆数量
        memory_count = len(memory_hits)

        # 13. 返回结果
        return ContextTurnResult(
            prompt=prompt,
            reasoning="",  # 可以从LLM获取推理过程
            response=response,
            memory_hits=memory_hits,
            history_count=history_count,
            profile_summary=profile_summary,
            rules_count=rules_count,
            memory_count=memory_count,
            turn_number=self.user_state.interaction_count,
            processing_time=processing_time,
        )

    # =============================================================================
    # 上下文整合和Prompt生成方法
    # =============================================================================

    async def integrate_context_to_knowledge(
        self, *, user_input: str, history_text: str, memory_text: str
    ) -> IntegratedKnowledge:
        """将所有上下文信息整合为结构化知识。"""
        # 收集所有上下文信息
        preset_info = self._extract_preset_info() if self.use_preset_info else ""
        extended_context = self._collect_extended_context()
        
        # 构建结构化知识
        return IntegratedKnowledge(
            user_input=user_input,
            history_text=history_text,
            memory_text=memory_text,
            preset_info=preset_info,
            extended_context=extended_context,
            base_system_prompt=self.base_system_prompt,
            user_profile=self.user_profile,
            business_rules=self.business_rules,
            temporal_context=self.get_temporal_context(),
        )

    async def generate_prompt_from_knowledge(self, knowledge: IntegratedKnowledge) -> str:
        """
        基于整合的知识生成最终prompt。
        
        优先使用 agent（LLM）智能生成 prompt，失败时回退到模板拼接方式。
        """
        try:
            # 首先尝试使用 agent 生成 prompt
            agent_prompt = await self._generate_prompt_with_agent(knowledge)
            if agent_prompt and len(agent_prompt.strip()) > 50:
                logger.debug("✅ 使用 agent 生成 prompt")
                return agent_prompt
            else:
                logger.warning("⚠️  agent 生成的 prompt 无效，使用模板拼接兜底")
                return self._build_prompt(knowledge)
        except Exception as e:
            # agent 失败时使用模板拼接兜底
            logger.warning(f"⚠️  agent 生成 prompt 失败: {e}，使用模板拼接兜底")
            return self._build_prompt(knowledge)
    
    async def _generate_prompt_with_agent(self, knowledge: IntegratedKnowledge) -> str:
        """使用 agent（LLM）智能生成 prompt。"""
        # 构建 meta-prompt：让 LLM 帮助我们组织上下文信息
        meta_prompt = f"""你是一个专业的 prompt 工程师。请根据以下信息，为客服对话系统生成一个结构化的 system prompt。

## 基础角色
{knowledge.base_system_prompt}

## 当前用户输入
{knowledge.user_input}

## 可用上下文信息

### 近期对话历史
{knowledge.history_text if knowledge.history_text else "（无）"}

### 长期记忆
{knowledge.memory_text if knowledge.memory_text else "（无）"}

### 预置业务信息
{knowledge.preset_info if knowledge.preset_info else "（无）"}

### 扩展上下文
{knowledge.extended_context if knowledge.extended_context else "（无）"}

## 要求
1. 根据用户输入的重要性，智能选择和组织相关上下文
2. 如果长期记忆中有关键信息（如用户投诉、特殊要求），务必突出展示
3. 如果用户输入涉及业务问题，突出相关的业务信息
4. 生成的 prompt 要清晰、结构化，便于客服 AI 理解
5. 直接输出最终的 system prompt，不要有其他解释或标记

请生成最终的 system prompt："""

        try:
            # 调用 LLM 生成 prompt
            _, generated_prompt = self._llm_client.generate(meta_prompt)
            
            # 提取实际的 prompt 内容
            generated_prompt = self._extract_actual_response(generated_prompt)
            
            return generated_prompt.strip()
        except Exception as e:
            logger.debug(f"agent 生成 prompt 异常: {e}")
            raise

    # =============================================================================
    # 内部辅助方法
    # =============================================================================

    async def seed_memory(self, facts: List[str]):
        """
        为长期记忆添加种子数据。

        Args:
            facts: 需要作为记忆存储的事实列表。
        """
        if not self.memory_service:
            logger.warning("Memory service is not configured, cannot seed memory.")
            return

        logger.info(f"🧠 Seeding {len(facts)} facts into long-term memory...")

        try:
            # 创建一个专门的 session 来存储种子知识
            seed_session = await self.session_service.create_session(
                app_name=self.app_name,
                user_id=self.user_id,
            )

            # 将种子数据作为系统事件添加到 session
            for fact in facts:
                event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=f"[预设知识] {fact}")]),
                )
                await self.session_service.append_event(session=seed_session, event=event)
            
            # 关键修复：将 session 持久化到 Memory Service
            await self.memory_service.add_session_to_memory(seed_session)
            
            logger.info(f"✅ {len(facts)} facts seeded and persisted to memory successfully.")

        except Exception as e:
            logger.error(f"❌ Failed to seed memory: {e}")

    async def _generate_response_with_retry(self, prompt: str) -> str:
        """生成回复，带重试机制。"""
        max_retries = 3
        last_error = None
        
        for attempt in range(max_retries):
            try:
                reasoning, response = self._llm_client.generate(prompt)
                response = self._extract_actual_response(response)
                
                # 验证回复质量
                response = response.strip()
                
                if not response or len(response) < 5:
                    continue
                
                # 检查是否包含分析性内容
                analysis_keywords = [
                    '首先', '然后', '分析', '检查', '根据', '因此', '所以', 
                    '用户提到', '历史行为', '情绪', '风险等级', '需要',
                    '我应该', '可以', '建议', '考虑', '注意', '确保',
                    '系统角色', '指令', '提示词', '示例', '正确回复', '错误回复'
                ]
                
                if any(keyword in response for keyword in analysis_keywords):
                    continue
                
                if ("你是优逸花客服" in response and "系统角色和指令" in response) or \
                   "重要任务" in response or \
                   "请生成一个完整的对话prompt" in response:
                    continue
                
                # 检查是否过长（可能是分析过程）
                if len(response) > 80:
                    continue
                
                break
                    
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    logger.debug(f"LLM generation attempt {attempt + 1} failed: {str(e)}, retrying...")
                    continue
                else:
                    raise RuntimeError(
                        f"Failed to generate response from LLM after {max_retries} attempts: {str(last_error)}. "
                        "User input has been saved to session."
                    ) from last_error
        
        # 最终检查
        if not response or len(response.strip()) < 5 or \
           (("你是优逸花客服" in response and "系统角色和指令" in response) or \
            "重要任务" in response or \
            "请生成一个完整的对话prompt" in response):
            raise RuntimeError(
                f"Failed to generate valid response after {max_retries} attempts. "
                "Last response was invalid or too short. "
                "User input has been saved to session."
            )
        
        return response

    async def _collect_recent_history(self) -> str:
        """获取最近 N 条事件，用于构造短期上下文。"""
        session = await self._fetch_session(num_recent_events=self._max_recent_events)
        
        if not session.events:
            return ""
        
        return _render_events(session.events)

    async def _retrieve_memory(self, *, query: str) -> Tuple[str, List[str]]:
        """智能检索长期记忆，结合关键词匹配和语义相关性。"""
        if not self.memory_service:
            return "", []

        # 1. 构建搜索查询列表
        search_queries = self._build_search_queries(query)
        
        # 2. 并发执行多轮搜索
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
        
        # 3. 收集并去重结果
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
            return "", []

        # 3. 按相关性分数排序
        all_memories.sort(key=lambda x: x['score'], reverse=True)
        
        # 4. 选择最相关的记忆（最多5条）
        top_memories = all_memories[:5]
        
        # 5. 格式化输出
        raw_entries = []
        for mem in top_memories:
            formatted = f"[{mem['timestamp']}] {mem['entry'].author}: {mem['text']}"
            raw_entries.append(formatted)
        
        memory_text = "\n".join(raw_entries)
        
        # 增强日志：显示检索到的记忆内容
        logger.info(f"🧠 检索到 {len(top_memories)} 条长期记忆:")
        for i, mem in enumerate(top_memories, 1):
            logger.info(f"  [{i}] {mem['text'][:100]}..." if len(mem['text']) > 100 else f"  [{i}] {mem['text']}")
        
        return memory_text, raw_entries

    def _build_search_queries(self, query: str) -> List[str]:
        """构建多个搜索查询以提高检索召回率。"""
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
        """生成语义相关的查询变体。"""
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
        """计算记忆与查询的相关性分数。"""
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

    async def _extract_knowledge_from_session(self, session: Session) -> dict:
        """从 session 中提取结构化知识，用于长期记忆存储。"""
        knowledge = {
            "user_profile_updates": {},  # 用户画像更新
            "key_events": [],    # 关键事件
            "user_preferences": {},  # 用户偏好
            "important_facts": [],    # 重要事实
            "emotional_state": None    # 情绪状态
        }
        
        if not session.events or len(session.events) < 2:
            return knowledge
        
        history_text = _render_events(session.events)
        
        extraction_prompt = f"""请从以下对话中提取关键信息，严格按照JSON格式输出：

对话历史：
{history_text}

请提取以下信息，严格按照以下JSON格式输出（只输出JSON对象，不要任何解释文字）：
{{
  "user_profile_updates": {{
    "年龄": null,
    "性别": null,
    "职业": null,
    "其他特征": null
  }},
  "key_events": [],
  "user_preferences": {{
    "喜欢": null,
    "不喜欢": null,
    "敏感点": null
  }},
  "important_facts": [],
  "emotional_state": null
}}

注意：
1. 只输出JSON对象，不要```json```标记
2. 如果信息不存在，保持null
3. 数组为空就保持[]
4. 确保JSON格式完整，括号匹配
5. 事实描述不超过20字
"""

        try:
            reasoning, result = self._llm_client.generate(extraction_prompt)
            result = self._extract_actual_response(result)
            
            if result and len(result) > 20:
                try:
                    # 尝试修复常见的JSON格式问题
                    cleaned_result = result.strip()
                    
                    # 移除可能的markdown代码块标记
                    if cleaned_result.startswith('```json'):
                        cleaned_result = cleaned_result[7:]
                    if cleaned_result.startswith('```'):
                        cleaned_result = cleaned_result[3:]
                    if cleaned_result.endswith('```'):
                        cleaned_result = cleaned_result[:-3]
                    cleaned_result = cleaned_result.strip()
                    
                    # 尝试补全截断的JSON
                    if not cleaned_result.endswith('}'):
                        cleaned_result = self._repair_truncated_json(cleaned_result)
                    
                    # 移除非法字符
                    cleaned_result = self._remove_invalid_json_chars(cleaned_result)
                    
                    # 尝试解析JSON
                    parsed = json.loads(cleaned_result)
                    knowledge.update(parsed)
                    
                    logger.debug(f"✅ 知识提取成功")
                except json.JSONDecodeError as e:
                    logger.warning(f"知识提取结果JSON解析失败: {e}")
                    logger.warning(f"原始结果: {result[:200]}")
                    
                    # 使用正则表达式回退方案
                    knowledge = self._extract_knowledge_with_regex(result, knowledge)
        except Exception as e:
            logger.warning(f"知识提取失败: {str(e)}")
        
        return knowledge
    
    def _repair_truncated_json(self, json_str: str) -> str:
        """尝试修复截断的JSON字符串"""
        # 计算缺少的闭合括号
        open_braces = json_str.count('{')
        close_braces = json_str.count('}')
        open_brackets = json_str.count('[')
        close_brackets = json_str.count(']')
        
        # 添加缺少的闭合符号
        if open_braces > close_braces:
            json_str += '}' * (open_braces - close_braces)
        if open_brackets > close_brackets:
            json_str += ']' * (open_brackets - close_brackets)
        
        return json_str
    
    def _remove_invalid_json_chars(self, json_str: str) -> str:
        """移除JSON中的非法字符"""
        # 保留可打印字符和Unicode字符
        cleaned = ''.join(char for char in json_str if char in string.printable or ord(char) > 127)
        return cleaned
    
    def _extract_knowledge_with_regex(self, text: str, knowledge: dict) -> dict:
        """使用正则表达式从文本中提取知识（回退方案）"""
        # 提取情绪关键词
        emotion_keywords = ["生气", "愤怒", "不满", "烦躁", "高兴", "满意", "失望", "焦虑"]
        for keyword in emotion_keywords:
            if keyword in text:
                knowledge["emotional_state"] = keyword
                break
        
        # 提取带有"用户"的句子作为事实
        user_facts = re.findall(r'[^。！？]*用户[^。！？]*[。！？]', text)
        if user_facts:
            knowledge["important_facts"].extend(user_facts[:3])
        
        # 特殊处理：姓氏识别
        if "姓胡" in text or "胡女士" in text:
            knowledge["user_profile_updates"]["其他特征"] = "姓胡女士"
            knowledge["important_facts"].append("用户姓胡，是女性")
        else:
            # 通用回退：提取有用信息
            knowledge["important_facts"].append(f"对话总结: {text[:200]}")
        
        logger.debug(f"使用正则提取到 {len(knowledge['important_facts'])} 条事实")
        return knowledge

    async def _persist_session_to_memory(self) -> None:
        """在每轮结束后，将提取的知识存储到长期记忆，而不是原始对话。"""
        if not self.memory_service:
            return

        try:
            session = await self._fetch_session()
            
            # 提取知识，而不是存储原始对话
            knowledge = await self._extract_knowledge_from_session(session)
            
            # 只存储提取的重要事实和关键事件
            facts_to_store = []
            
            # 添加重要事实
            for fact in knowledge.get("important_facts", []):
                if fact and len(fact.strip()) > 5:
                    facts_to_store.append(f"[重要事实] {fact.strip()}")
            
            # 添加关键事件
            for event in knowledge.get("key_events", []):
                if event and len(event.strip()) > 5:
                    facts_to_store.append(f"[关键事件] {event.strip()}")
            
            # 添加情绪状态
            emotional_state = knowledge.get("emotional_state")
            if emotional_state and len(emotional_state.strip()) > 2:
                facts_to_store.append(f"[情绪状态] {emotional_state.strip()}")
            
            # 添加用户偏好
            preferences = knowledge.get("user_preferences", {})
            if preferences:
                pref_text = []
                if preferences.get("喜欢"):
                    pref_text.append(f"喜欢: {preferences['喜欢']}")
                if preferences.get("不喜欢"):
                    pref_text.append(f"不喜欢: {preferences['不喜欢']}")
                if preferences.get("敏感点"):
                    pref_text.append(f"敏感点: {preferences['敏感点']}")
                if pref_text:
                    facts_to_store.append(f"[用户偏好] {', '.join(pref_text)}")
            
            # 将提取的知识作为独立事件存储到记忆中
            # 创建一个专门的 session 来存储提取的知识
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
                
                # 关键修复：将知识 session 持久化到 Memory Service
                await self.memory_service.add_session_to_memory(knowledge_session)
                
                logger.debug(f"💾 Persisted {len(facts_to_store)} knowledge facts to memory.")
                
        except Exception as e:
            logger.warning(f"Failed to persist knowledge to memory: {str(e)}")

    async def _periodic_summary(self) -> None:
        """定期总结对话历史，生成高层次的知识摘要并存储到长期记忆。"""
        if not self.memory_service:
            return

        interval = self.user_state.summary_interval
        if interval <= 0:
            return

        if self.user_state.interaction_count % interval != 0:
            return

        try:
            session = await self._fetch_session()
            if not session.events or len(session.events) < 2:
                return

            history_text = _render_events(session.events)
            
            summary_prompt = f"""请总结以下对话历史，生成高层次的知识摘要：

对话历史：
{history_text}

请生成一个简洁的知识摘要，包括：
1. 用户的核心特征和画像更新
2. 对话的主要进展和结果
3. 用户态度和情绪的变化趋势
4. 需要长期记住的关键信息

总结要求：
- 简洁明了，不超过150字
- 只输出总结内容，不要有其他说明
- 侧重于需要长期记住的信息，而非具体对话细节
"""

            reasoning, summary = self._llm_client.generate(summary_prompt)
            summary = self._extract_actual_response(summary)

            if summary and len(summary) > 10:
                # 将总结作为独立的记忆存储，而不是添加到session
                summary_event = Event(
                    invocation_id=self._new_invocation_id(),
                    author="system",
                    content=Content(role="system", parts=[Part(text=f"[对话总结] {summary}")]),
                )
                
                # 直接存储到当前session
                await self.session_service.append_event(session=session, event=summary_event)
                
                # 总结已生成并存储，不需要打印详细日志
        except Exception as e:
            logger.warning(f"Failed to perform periodic summary: {str(e)}")

    async def _cleanup_old_events(self) -> None:
        """
        清理旧的事件，只保留最近的 _max_recent_events 个事件。
        
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

    # =============================================================================
    # Prompt生成相关方法
    # =============================================================================

    def _extract_preset_info(self) -> str:
        """返回固定的预置信息，包括客服电话目的。"""
        preset_info = """
- 电话目的：提醒用户申请优逸花预留额度
- 额度特点：
  * 限时预留额度
  * 无需下载APP
  * 微信小程序人脸识别完成
  * 无需填资料
  * 额度不用不产生任何费用
  * 后续资金周转时更方便
- 服务名称：优逸花
- 公司名称：马上消费
"""
        return preset_info.strip()

    @staticmethod
    def _format_dict_to_lines(data: dict) -> List[str]:
        """将字典格式化为列表行，支持列表值。"""
        lines = []
        for key, value in data.items():
            if isinstance(value, list):
                lines.append(f"- {key}: {', '.join(value)}")
            else:
                lines.append(f"- {key}: {value}")
        return lines

    def _collect_extended_context(self) -> str:
        """收集扩展的上下文信息。"""
        extended_parts = []
        
        if self.user_profile:
            profile_lines = self._format_dict_to_lines(self.user_profile)
            extended_parts.append("### 用户画像\n" + "\n".join(profile_lines))
        
        temporal_context = self.get_temporal_context()
        if temporal_context:
            temporal_lines = self._format_dict_to_lines(temporal_context)
            extended_parts.append("### 时间与环境\n" + "\n".join(temporal_lines))
        
        if self.business_rules:
            rules_lines = self._format_dict_to_lines(self.business_rules)
            extended_parts.append("### 业务规则与合规\n" + "\n".join(rules_lines))
        
        return "\n\n".join(extended_parts) if extended_parts else ""

    def _build_prompt(self, knowledge: IntegratedKnowledge) -> str:
        """使用模板拼接生成prompt，并应用权重优化。"""
        system_prompt = knowledge.base_system_prompt
        prompt_parts = [system_prompt]

        # 计算上下文权重
        context_weights = self._calculate_context_weights(knowledge)
        
        # 根据权重排序上下文项
        context_items = [
            ('memory', knowledge.memory_text, '长期记忆'),
            ('history', knowledge.history_text, '近期对话历史'),
            ('preset', knowledge.preset_info, '预置信息'),
            ('extended', knowledge.extended_context, '扩展上下文')
        ]
        
        # 按权重降序排序
        sorted_items = sorted(context_items, key=lambda x: context_weights[x[0]], reverse=True)
        
        # 添加当前用户输入（最高优先级）
        prompt_parts.append(f"\n【当前用户输入】\n{knowledge.user_input}")
        
        # 按权重顺序添加上下文信息
        for key, content, label in sorted_items:
            if not content:
                continue
            
            weight = context_weights[key]
            # 只添加权重>0.1的内容，避免prompt过长
            if weight < 0.1:
                continue

            if weight > 0.6:
                # 高权重：标记为重要
                prompt_parts.append(f"\n【重要参考：{label}】\n{content}")
            else:
                # 中等权重：标记为一般参考
                prompt_parts.append(f"\n【一般参考：{label}】\n{content}")

        return "\n".join(prompt_parts)

    def _calculate_context_weights(self, knowledge: IntegratedKnowledge) -> dict:
        """计算各上下文信息的权重（简化版）。"""
        weights = {
            'history': 0.5,
            'memory': 0.3,
            'preset': 0.1,
            'extended': 0.1
        }
        
        # 如果有长期记忆，其重要性提升
        if knowledge.memory_text:
            weights['memory'] = 0.8
            weights['history'] = 0.6 # 相应调整近期历史的权重

        # 如果用户输入明确涉及业务问题，提升预置信息权重
        business_keywords = ["额度", "费用", "利息", "申请", "还款", "逾期", "优逸花"]
        if any(kw in knowledge.user_input for kw in business_keywords):
            weights['preset'] = 0.7
        
        # 如果用户输入涉及情绪或负面反馈，提升长期记忆权重
        emotion_keywords = ["骚扰", "报警", "拒绝", "烦", "不要", "停止", "投诉"]
        if any(kw in knowledge.user_input for kw in emotion_keywords):
            weights['memory'] = 0.9

        return weights

    def _organize_context_by_weight(self, knowledge: IntegratedKnowledge, weights: dict) -> dict:
        """根据权重重新组织上下文信息。"""
        organized = {}
        
        # 按权重排序
        sorted_weights = sorted(weights.items(), key=lambda x: x[1], reverse=True)
        
        for key, weight in sorted_weights:
            if key == 'history':
                organized['history'] = {
                    'content': knowledge.history_text,
                    'weight': weight,
                    'priority': 1 if weight > 0.5 else 2
                }
            elif key == 'memory':
                organized['memory'] = {
                    'content': knowledge.memory_text,
                    'weight': weight,
                    'priority': 1 if weight > 0.5 else 2
                }
            elif key == 'preset':
                organized['preset'] = {
                    'content': knowledge.preset_info,
                    'weight': weight,
                    'priority': 2 if weight > 0.4 else 3
                }
            elif key == 'extended':
                organized['extended'] = {
                    'content': knowledge.extended_context,
                    'weight': weight,
                    'priority': 2 if weight > 0.3 else 3
                }
        
        return organized

    def _build_fallback_prompt(self, knowledge: IntegratedKnowledge) -> str:
        """回退方法：使用模板拼接生成prompt，并应用权重优化。"""
        system_prompt = knowledge.base_system_prompt
        prompt_parts = [system_prompt]

        # 计算上下文权重
        context_weights = self._calculate_context_weights(knowledge)
        
        # 根据权重排序上下文项
        context_items = [
            ('history', knowledge.history_text, '近期对话历史'),
            ('memory', knowledge.memory_text, '长期记忆'),
            ('preset', knowledge.preset_info, '预置信息'),
            ('extended', knowledge.extended_context, '扩展上下文')
        ]
        
        # 按权重降序排序
        sorted_items = sorted(context_items, key=lambda x: context_weights[x[0]], reverse=True)
        
        # 添加当前用户输入（最高优先级）
        prompt_parts.append(f"\n【当前用户输入】\n{knowledge.user_input}")
        
        # 按权重顺序添加上下文信息
        for key, content, label in sorted_items:
            if not content:
                continue
            
            weight = context_weights[key]
            if weight > 0.6:
                # 高权重：标记为重要
                prompt_parts.append(f"\n【重要：{label}（权重：{weight:.2f}）】\n{content}")
            elif weight > 0.3:
                # 中等权重：标记为参考
                prompt_parts.append(f"\n【参考：{label}（权重：{weight:.2f}）】\n{content}")
            else:
                # 低权重：标记为补充
                prompt_parts.append(f"\n【补充：{label}（权重：{weight:.2f}）】\n{content}")

        return "\n".join(prompt_parts)

    @staticmethod
    def _extract_actual_response(response: str) -> str:
        """从模型输出中提取实际回复内容。"""
        response = response.strip()
        
        # 如果回复看起来正常（包含标点符号，长度合理），直接返回
        if len(response) > 5 and any(char in response for char in '。！？，；：.!?,:;'):
            return response
        
        # 处理JSON格式输出
        if response.startswith('{') and response.endswith('}'):
            try:
                import json
                data = json.loads(response)
                if isinstance(data, dict) and 'content' in data:
                    return str(data['content']).strip()
            except:
                pass
        
        # 移除外层引号
        if (response.startswith('"') and response.endswith('"')) or \
           (response.startswith('"') and response.endswith('"')):
            response = response[1:-1].strip()
        
        # 处理结构化格式
        if '**' in response and '：' in response:
            lines = response.split('\n')
            for line in lines:
                if '：' in line and not line.startswith('**'):
                    content = line.split('：', 1)[1].strip()
                    if content and len(content) > 5:
                        return content
                elif line.startswith('**') and '：' in line:
                    content = line.split('：', 1)[1].strip()
                    if content and len(content) > 5:
                        return content
        
        # 移除markdown格式标记
        response = re.sub(r'\*\*(.*?)\*\*', r'\1', response)
        response = re.sub(r'`(.*?)`', r'\1', response)
        response = re.sub(r'^-\s*', '', response, flags=re.MULTILINE)
        
        # 短回复直接返回
        if len(response) < 100:
            return response
        
        # 尝试提取引号中的内容
        quoted_matches = re.findall(r'["""]([^"""]+)["""]', response)
        if quoted_matches:
            return quoted_matches[-1].strip()
        
        quoted_matches = re.findall(r'"([^"]+)"', response)
        if quoted_matches:
            return quoted_matches[-1].strip()
        
        # 提取关键词后的内容
        patterns = [
            r'回复应为[：:]\s*["""]?([^"""\n]+)["""]?',
            r'回复[：:]\s*["""]?([^"""\n]+)["""]?',
            r'因此[，,]?\s*回复应为[：:]\s*["""]?([^"""\n]+)["""]?',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, response)
            if match:
                extracted = match.group(1).strip()
                if 10 < len(extracted) < 200:
                    return extracted
        
        # 提取最合适的行
        lines = response.split('\n')
        for line in lines:
            line = line.strip()
            if line and not line.startswith('**') and len(line) > 10 and len(line) < 100:
                return line
        
        return response

    @staticmethod
    def _new_invocation_id() -> str:
        """生成新的调用 ID。"""
        return str(uuid.uuid4())

    # =============================================================================
    # 公共接口方法
    # =============================================================================

    async def get_current_session(self) -> Session:
        """获取当前会话（公共方法）。"""
        return await self._fetch_session()

    async def persist_to_memory(self) -> None:
        """将当前会话持久化到长期记忆（公共方法）。"""
        await self._persist_session_to_memory()

    def new_invocation_id(self) -> str:
        """生成新的调用 ID（公共方法）。"""
        return self._new_invocation_id()

    def reset_user_state(self) -> None:
        """重置用户状态计数器，防止内存泄漏。"""
        self.user_state = UserState()

    def get_interaction_count(self) -> int:
        """获取当前交互次数。"""
        return self.user_state.interaction_count
