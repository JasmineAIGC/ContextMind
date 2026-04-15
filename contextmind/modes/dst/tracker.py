"""
对话状态追踪器（Dialogue State Tracker）

基于 ACL 2023 论文的增强实现，使用 Google ADK LlmAgent + InMemoryRunner
进行 LLM 驱动的槽位提取，支持：
- ADK 原生 Session 管理（历史由 InMemoryRunner 自动维护）
- 动态槽位提取
- 多意图追踪
"""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .prompts import PromptManager
from .parser import DSTResponseParser
from contextmind.infra.logger import get_logger
from contextmind.infra.llm_client import create_local_adk_model

from google.adk.agents import LlmAgent  # type: ignore[import]
from google.adk.runners import InMemoryRunner  # type: ignore[import]
from google.genai import types as genai_types  # type: ignore[import]

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 数据模型（原 data_models.py）
# ---------------------------------------------------------------------------

class SpecialValue(Enum):
    """特殊槽位值，遵循 MultiWOZ / DSTC 惯例。

    UNKNOWN ("?") — user is *asking* for this slot rather than providing a value.
    DONTCARE ("dontcare") — user explicitly doesn't care about this slot's value.
    """
    UNKNOWN = "?"
    DONTCARE = "dontcare"


@dataclass
class DialogueTurn:
    """单轮对话数据结构，包含系统/用户发言和槽位状态信息。"""
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str] = field(default_factory=dict)
    turn_updates: Dict[str, str] = field(default_factory=dict)
    # 保留原始 LLM 响应，供调试和离线分析使用；状态追踪本身不依赖此字段。
    raw_llm_response: Optional[str] = None


class DialogueStateTracker:
    """
    对话状态追踪器（优化版 - 减少LLM调用）
    
    实现完整的零样本对话状态追踪系统，符合ACL 2023论文规范。
    支持动态槽位提取、智能历史管理、多意图追踪。
    """
    
    def __init__(self, 
                 llm_client=None,
                 prompt_manager: Optional[PromptManager] = None,
                 domain: str = "general",
                 max_history_turns: int = 10,
                 enable_history_summary: bool = True,
                 enable_dynamic_slots: bool = True,
                 use_llm_summary: bool = False):
        """
        初始化对话状态追踪器
        
        参数:
            llm_client: LLM客户端实例
            prompt_manager: 可选的提示词管理器
            domain: 对话领域
            max_history_turns: 完整保留的最近对话轮数（默认10）
            enable_history_summary: 是否启用历史摘要（默认True）
            enable_dynamic_slots: 是否启用动态槽位（默认True）
            use_llm_summary: 是否使用LLM生成摘要（默认False，使用模板摘要）
        """
        self.llm_client = llm_client
        self.prompt_manager = prompt_manager or PromptManager(
            domain=domain, 
            enable_dynamic_slots=enable_dynamic_slots
        )
        
        categorical_slots = {}
        if hasattr(self.prompt_manager, 'categorical_slots'):
            categorical_slots = self.prompt_manager.categorical_slots
        
        pm_enable_dynamic = self.prompt_manager.enable_dynamic_slots
        
        self.response_parser = DSTResponseParser(
            ontology_slots=self.prompt_manager.get_slot_names(),
            enable_filtering=not pm_enable_dynamic,
            categorical_slots=categorical_slots
        )
        
        self.current_state: Dict[str, str] = {}
        self.dialogue_history: List[DialogueTurn] = []
        
        self.intent_history: List[str] = []
        self.current_intents: List[str] = []
        
        self.intent_states: Dict[str, Dict[str, str]] = {}
        self.enable_intent_namespacing: bool = False
        
        self.max_history_turns = max_history_turns
        self.enable_history_summary = enable_history_summary
        self.use_llm_summary = use_llm_summary
        self.history_summary: Optional[str] = None
        
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.prompt_manager.get_system_instruction()}
        ]
        
        logger.info(
            f"初始化DialogueStateTracker "
            f"(领域={domain}, 动态槽位={enable_dynamic_slots}, "
            f"历史轮数={max_history_turns}, 摘要={enable_history_summary}, "
            f"LLM摘要={use_llm_summary})"
        )

        # ------------------------------------------------------------------ #
        # ADK 原生 Agent 初始化（当 google-adk 可用时）
        # 用 LlmAgent + InMemoryRunner 替代手动消息列表管理：
        # - LlmAgent 持有静态系统指令（槽位提取任务描述）
        # - InMemoryRunner 通过 InMemorySessionService 自动维护多轮会话历史
        # - 每轮仅传入当前对话片段，无需手动构建 full messages array
        # ------------------------------------------------------------------ #
        self._adk_runner: Optional[Any] = None
        self._adk_session_id: Optional[str] = None
        if llm_client is not None:
            adk_model = create_local_adk_model(
                getattr(llm_client, "_config", None)
            )
            adk_agent = LlmAgent(
                name="dst_agent",
                model=adk_model,
                instruction=self.prompt_manager.get_system_instruction(),
            )
            self._adk_runner = InMemoryRunner(
                agent=adk_agent,
                app_name="contextmind_dst",
            )
            logger.info("[DST] ADK LlmAgent + InMemoryRunner 已初始化，使用 ADK 原生会话管理")
    
    @classmethod
    def from_scenario(cls, 
                     llm_client,
                     scenario_config,
                     max_history_turns: int = 10,
                     enable_history_summary: bool = True,
                     use_llm_summary: bool = False):
        """
        从场景配置创建DialogueStateTracker实例的工厂方法
        
        参数:
            llm_client: LLM客户端实例
            scenario_config: 场景配置对象（ScenarioConfig）
            max_history_turns: 完整保留的最近对话轮数（默认10）
            enable_history_summary: 是否启用历史摘要（默认True）
            use_llm_summary: 是否使用LLM生成摘要（默认False）
            
        返回:
            DialogueStateTracker实例
        """
        pm = PromptManager(
            domain=scenario_config.name,
            enable_dynamic_slots=scenario_config.enable_dynamic_slots,
            custom_template=getattr(scenario_config, 'dst_prompt_template', None)
        )
        
        for slot_name, slot_desc in scenario_config.dst_slots.items():
            categorical_values = None
            if scenario_config.dst_categorical_slots and slot_name in scenario_config.dst_categorical_slots:
                categorical_values = scenario_config.dst_categorical_slots[slot_name]
            pm.add_slot(slot_name, slot_desc, categorical_values=categorical_values)
        
        return cls(
            llm_client=llm_client,
            prompt_manager=pm,
            max_history_turns=max_history_turns,
            enable_history_summary=enable_history_summary,
            use_llm_summary=use_llm_summary
        )
    
    @property
    def turns(self) -> List[DialogueTurn]:
        """对话历史列表（只读）。"""
        return self.dialogue_history
    
    def reset(self) -> None:
        """重置对话状态，清空所有历史和状态。"""
        self.messages = [
            {"role": "system", "content": self.prompt_manager.get_system_instruction()}
        ]
        self.current_state = {}
        self.dialogue_history = []
        self.intent_history = []
        self.current_intents = []
        self.intent_states = {}
        self.history_summary = None
        # 重置 ADK 会话（下次 process_turn 时自动重建新 session）
        self._adk_session_id = None
        logger.info("对话状态已重置")

    async def _get_or_create_adk_session(self) -> str:
        """获取或创建 ADK 会话 ID（懒加载，首次调用时创建）。"""
        if self._adk_session_id is None:
            session = await self._adk_runner.session_service.create_session(
                app_name="contextmind_dst",
                user_id="default_user",
            )
            self._adk_session_id = session.id
            logger.debug(f"[DST] 创建 ADK 会话: {self._adk_session_id}")
        return self._adk_session_id

    async def _run_adk_turn(self, turn_prompt: str) -> str:
        """通过 ADK InMemoryRunner 执行单轮 LLM 调用。

        Args:
            turn_prompt: 当前轮次的用户输入（系统话语 + 用户话语 + 提取指令）

        Returns:
            LLM 返回的原始文本（应为 JSON 格式的槽位更新）
        """
        session_id = await self._get_or_create_adk_session()
        content = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=turn_prompt)],
        )
        raw_response = ""
        async for event in self._adk_runner.run_async(
            user_id="default_user",
            session_id=session_id,
            new_message=content,
        ):
            if event.is_final_response() and event.content and event.content.parts:
                for part in event.content.parts:
                    if hasattr(part, "text") and part.text and not getattr(part, "thought", False):
                        raw_response += part.text
        return raw_response.strip()

    async def _fallback_chat_async(self, prompt: str) -> str:
        """直接通过 chat_async 调用 LLM（当 ADK runner 未初始化时使用）。"""
        if self.llm_client is None:
            raise RuntimeError("[DST] llm_client 未提供，无法发起 LLM 调用")
        return await self.llm_client.chat_async(
            messages=self.messages,
            temperature=0.0,
        )

    async def process_turn(
        self,
                          user_utterance: str,
                          system_utterance: str = "",
                          **kwargs) -> Dict[str, str]:
        """
        处理单轮对话（增强版 - 智能历史管理 + 意图追踪）

        执行步骤：
        1. 准备历史对话（智能摘要或完整历史）
        2. 调用LLM提取槽位更新
        3. 解析响应
        4. 更新状态和意图
        5. 管理历史（必要时触发摘要）

        参数:
            user_utterance: 用户的话语（必需）
            system_utterance: 系统的话语（可选，默认空字符串）
            **kwargs: 保留扩展参数

        返回:
            更新后的累积对话状态
        """
        self.step_timings = {}
        
        turn_prompt = f'system: "{system_utterance}"\nuser: "{user_utterance}"'
        
        step_start = time.time()
        history_for_prompt = self._prepare_history_for_prompt()
        self.step_timings['历史准备'] = time.time() - step_start
        
        step_start = time.time()
        if self.history_summary and self.enable_history_summary:
            system_instruction = self.prompt_manager.get_system_instruction(
                history_summary=self.history_summary
            )
            self.messages[0] = {"role": "system", "content": system_instruction}
        
        if history_for_prompt:
            full_prompt = f"{history_for_prompt}\n\n{turn_prompt}"
        else:
            full_prompt = turn_prompt
        
        # 仅保留系统消息；历史对话已嵌入 full_prompt，避免消息列表指数增长。
        self.messages = [self.messages[0]]
        
        self.messages.append({"role": "user", "content": full_prompt})
        self.step_timings['提示词构建'] = time.time() - step_start
        
        step_start = time.time()
        if self._adk_runner is not None:
            # ---------------------------------------------------------- #
            # ADK 路径：通过 LlmAgent + InMemoryRunner 发起 LLM 调用
            # - ADK 的 InMemorySessionService 自动维护多轮会话历史
            # - 仅传入当前轮次的对话片段（无需手动构建完整消息列表）
            # ---------------------------------------------------------- #
            raw_response = await self._run_adk_turn(full_prompt)
            logger.debug(f"[DST ADK] LLM 响应: {raw_response[:200]}")
        elif self.llm_client:
            raw_response = await self._fallback_chat_async(full_prompt)
        else:
            raise RuntimeError("[DST] 未提供 llm_client，无法发起 LLM 调用")
        self.step_timings['LLM槽位提取'] = time.time() - step_start
        
        step_start = time.time()
        logger.debug(f"开始解析响应，长度: {len(raw_response)} 字符")
        turn_updates = self.response_parser.extract_json(raw_response)
        logger.debug(f"解析结果: {turn_updates}")
        
        turn_updates = self.response_parser.normalize_extracted(
            turn_updates,
            self.prompt_manager.get_all_slots(),
            self.prompt_manager.categorical_slots or {}
        )
        logger.debug(f"归一化后: {turn_updates}")
        self.step_timings['响应解析'] = time.time() - step_start
        
        step_start = time.time()
        self._update_state(turn_updates)
        self._track_intents(turn_updates)
        self.step_timings['状态更新'] = time.time() - step_start
        
        turn = DialogueTurn(
            system_utterance=system_utterance,
            user_utterance=user_utterance,
            predicted_state=self.current_state.copy(),
            turn_updates=turn_updates,
            raw_llm_response=raw_response
        )
        self.dialogue_history.append(turn)
        
        await self._manage_history()
        
        intent_info = turn_updates.get('intent') or turn_updates.get('intent_level1', '未识别')
        logger.info(
            f"处理轮次 #{len(self.dialogue_history)}: "
            f"更新={turn_updates}, 意图={intent_info}"
        )

        # 统一结构化日志：scene / mode / dialogue_id / latency / token
        _total_latency = round(sum(self.step_timings.values()), 3)
        logger.info(
            f"[turn_summary] scene={self.prompt_manager.domain} mode=dst "
            f"dialogue_id={len(self.dialogue_history)} latency={_total_latency:.3f}s token=n/a"
        )

        return self.current_state.copy()
    
    def _prepare_history_for_prompt(self) -> str:
        """
        准备用于提示词的对话历史（智能管理）
        
        策略：
        1. 如果历史 <= max_history_turns：返回全部
        2. 如果历史 > max_history_turns：
           - 返回最近 max_history_turns 轮的完整历史
           - （摘要在系统指令中单独提供）
        
        返回:
            格式化的对话历史字符串
        """
        if not self.dialogue_history:
            return ""
        
        # 决定保留多少轮完整历史
        recent_turns = self.dialogue_history[-self.max_history_turns:]
        
        # 格式化历史
        history_lines = []
        for turn in recent_turns:
            history_lines.append(f'system: "{turn.system_utterance}"')
            history_lines.append(f'user: "{turn.user_utterance}"')
        
        if history_lines:
            return "## 最近对话历史\n\n" + "\n".join(history_lines)
        
        return ""
    
    async def _manage_history(self) -> None:
        """
        管理对话历史（必要时触发摘要）
        
        当对话历史超过阈值时，自动摘要旧对话。
        根据use_llm_summary设置选择使用LLM或模板方式。
        """
        if not self.enable_history_summary:
            return
        
        total_turns = len(self.dialogue_history)
        
        # 触发摘要的条件：历史超过阈值 + 没有摘要或摘要过旧
        should_summarize = (
            total_turns > self.max_history_turns and
            (self.history_summary is None or 
             total_turns % (self.max_history_turns * 2) == 0)  # 每2倍阈值重新摘要
        )
        
        if should_summarize:
            old_turns = self.dialogue_history[:-self.max_history_turns]
            if old_turns:
                if self.use_llm_summary and self.llm_client:
                    self.history_summary = await self._summarize_old_turns(old_turns)
                    logger.info(
                        f"生成LLM历史摘要（轮次1-{len(old_turns)}），"
                        f"保留完整历史（轮次{len(old_turns)+1}-{total_turns}）"
                    )
                else:
                    self.history_summary = self._template_based_summary(old_turns)
                    logger.info(
                        f"生成模板历史摘要（轮次1-{len(old_turns)}），"
                        f"保留完整历史（轮次{len(old_turns)+1}-{total_turns}）"
                    )
    
    async def _summarize_old_turns(self, turns: List[DialogueTurn]) -> str:
        """
        使用LLM摘要旧的对话轮次（可选功能，默认不使用）
        
        提取：
        - 主要意图演变
        - 关键信息和决策
        - 重要的槽位值
        
        参数:
            turns: 需要摘要的对话轮次列表
            
        返回:
            摘要文本
        """
        dialogue_text = ""
        for i, turn in enumerate(turns, 1):
            dialogue_text += f"轮次{i}:\n"
            dialogue_text += f"  系统: {turn.system_utterance}\n"
            dialogue_text += f"  用户: {turn.user_utterance}\n"
            if turn.turn_updates:
                dialogue_text += f"  提取信息: {turn.turn_updates}\n"
            dialogue_text += "\n"
        
        summary_prompt = f"""请对以下对话历史进行简洁摘要，提取关键信息：

{dialogue_text}

请提取：
1. 主要意图演变（如：从作业帮助 → 餐饮推荐 → 回到作业）
2. 关键信息和决策
3. 重要的槽位值

用2-3句话概括，突出重点。
"""
        
        messages = [
            {"role": "system", "content": "你是一个对话摘要助手，善于提取对话中的关键信息。"},
            {"role": "user", "content": summary_prompt}
        ]
        
        try:
            summary = await self.llm_client.chat_async(messages=messages, temperature=0.3)
            return summary.strip()
        except Exception as e:
            logger.error(f"摘要生成失败: {e}")
            return f"（轮次1-{len(turns)}的对话历史）"
    
    def _template_based_summary(self, turns: List[DialogueTurn]) -> str:
        """
        使用模板方式生成摘要（不使用LLM，快速且节省资源）
        
        提取：
        - 意图演变序列
        - 关键槽位值
        - 对话轮数
        
        参数:
            turns: 需要摘要的对话轮次列表
            
        返回:
            摘要文本
        """
        intents = []
        for turn in turns:
            if turn.turn_updates and "intent" in turn.turn_updates:
                intent = turn.turn_updates["intent"]
                if intent and intent not in ["其他", "未知"]:
                    intents.append(intent)
        
        key_slots = {}
        for turn in turns:
            if turn.turn_updates:
                for slot, value in turn.turn_updates.items():
                    if slot != "intent" and value and value.strip():
                        key_slots[slot] = value
        
        summary_parts = [f"历史对话（共{len(turns)}轮）"]
        
        if intents:
            unique_intents = []
            seen = set()
            for intent in intents:
                if intent not in seen:
                    unique_intents.append(intent)
                    seen.add(intent)
            summary_parts.append(f"主要意图：{' → '.join(unique_intents)}")
        
        if key_slots:
            important_slots = list(key_slots.items())[:5]
            slot_str = ", ".join([f"{k}={v}" for k, v in important_slots])
            summary_parts.append(f"关键信息：{slot_str}")
        
        return "；".join(summary_parts) + "。"

    
    def _update_state(self, updates: Dict[str, str]) -> None:
        """
        更新累积对话状态
        
        实现 DS_t = update(DS_{t-1}, updates)
        支持两种模式：
        1. 全局命名空间（默认）：所有槽位共享一个字典
        2. 意图命名空间（可选）：按意图分离槽位存储
        
        参数:
            updates: 从当前轮次提取的槽位更新
        """
        if hasattr(self, 'prompt_manager') and self.prompt_manager:
            allowed_slots = self.prompt_manager.get_all_slots()
            categorical_slots = self.prompt_manager.categorical_slots or {}
            updates = self.response_parser.normalize_extracted(
                updates,
                allowed_slots,
                categorical_slots
            )
        
        current_intent = updates.get("intent")
        
        for slot, value in updates.items():
            if value and value.strip():
                self.current_state[slot] = value
        
        if self.enable_intent_namespacing and current_intent:
            if current_intent not in self.intent_states:
                self.intent_states[current_intent] = {}
            for slot, value in updates.items():
                if slot != "intent" and value and value.strip():
                    self.intent_states[current_intent][slot] = value
            logger.debug(f"意图状态更新: {current_intent} -> {self.intent_states[current_intent]}")
    
    def _track_intents(self, updates: Dict[str, str]) -> None:
        """
        追踪意图演变（新增功能）
        
        记录意图变化，支持多意图场景。
        
        参数:
            updates: 当前轮次的槽位更新
        """
        if "intent" in updates:
            new_intent = updates["intent"]
            self.intent_history.append(new_intent)
            if new_intent not in self.current_intents:
                self.current_intents.append(new_intent)
            logger.debug(f"意图追踪: 新意图={new_intent}, 历史={self.intent_history}")
    
    def get_current_state(self) -> Dict[str, str]:
        """
        获取当前累积对话状态
        
        返回:
            当前对话状态的副本
        """
        return self.current_state.copy()
    
    def get_intent_history(self) -> List[str]:
        """
        获取意图演变历史
        
        返回:
            意图历史列表
        """
        return self.intent_history.copy()
    
    def get_current_intents(self) -> List[str]:
        """
        获取当前活跃的意图
        
        返回:
            当前意图列表
        """
        return self.current_intents.copy()
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        获取追踪器统计信息
        
        返回:
            统计信息字典
        """
        return {
            "total_turns": len(self.dialogue_history),
            "current_state_size": len(self.current_state),
            "intent_switches": len(set(self.intent_history)),
            "current_intents": len(self.current_intents),
            "has_summary": self.history_summary is not None,
            "messages_count": len(self.messages),
            "intent_states_count": len(self.intent_states)
        }
    
    def get_intent_state(self, intent: str) -> Dict[str, str]:
        """
        获取特定意图的槽位状态（优化功能）
        
        仅在启用intent_namespacing时返回有意义的结果
        
        参数:
            intent: 意图名称
            
        返回:
            该意图关联的槽位字典（副本）
        """
        if not self.enable_intent_namespacing:
            logger.warning("未启用意图命名空间，返回空字典")
            return {}
        
        return self.intent_states.get(intent, {}).copy()
    
    def get_all_intent_states(self) -> Dict[str, Dict[str, str]]:
        """
        获取所有意图的槽位状态（优化功能）
        
        返回:
            意图到槽位字典的映射（副本）
        """
        if not self.enable_intent_namespacing:
            logger.warning("未启用意图命名空间，返回空字典")
            return {}
        
        # 返回深拷贝
        return {
            intent: slots.copy()
            for intent, slots in self.intent_states.items()
        }
    
    def get_state_at_turn(self, turn_num: int) -> Dict[str, str]:
        """
        获取特定轮次的累积状态（优化功能）
        
        通过重放历史得到该轮次后的状态
        
        参数:
            turn_num: 轮次编号（从1开始）
            
        返回:
            该轮次后的累积状态
        """
        if turn_num < 1 or turn_num > len(self.dialogue_history):
            logger.warning(f"无效轮次号: {turn_num}, 总轮次: {len(self.dialogue_history)}")
            return {}
        
        # 重放历史到指定轮次
        state = {}
        for i, turn in enumerate(self.dialogue_history[:turn_num], 1):
            for slot, value in turn.turn_updates.items():
                if value and value.strip():
                    state[slot] = value
        
        return state
    
    def get_slot_history(self, slot: str) -> List[Tuple[int, str]]:
        """
        获取特定槽位的所有历史值（优化功能）
        
        参数:
            slot: 槽位名称
            
        返回:
            (轮次号, 值) 的列表
        """
        history = []
        for i, turn in enumerate(self.dialogue_history, 1):
            if slot in turn.turn_updates:
                value = turn.turn_updates[slot]
                if value and value.strip():
                    history.append((i, value))
        
        return history

