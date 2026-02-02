"""
对话状态追踪器（Dialogue State Tracker）

基于 ACL 2023 论文的增强实现，支持：
- 动态槽位提取
- 智能历史管理（模板摘要或LLM摘要）
- 多意图追踪
- 优化的LLM使用（默认仅在槽位提取时调用）

版本: v0.4.0
"""

from typing import Dict, List, Optional, Tuple

from dst.data_models import DialogueTurn
from dst.prompt_manager import PromptManager
from dst.response_parser import ResponseParser
from utils.logger import get_logger

logger = get_logger(__name__)


class DialogueStateTracker:
    """
    对话状态追踪器（优化版 - 减少LLM调用）
    
    实现完整的零样本对话状态追踪系统，符合ACL 2023论文规范，并优化：
    1. 动态槽位提取 - LLM自由提取任何相关信息
    2. 智能历史管理 - 模板摘要（默认）或LLM摘要（可选）
    3. 多意图追踪 - 追踪意图切换和演变
    4. 优化LLM使用 - 默认仅在槽位提取时调用LLM
    
    核心特性：
    - 完全零样本（无需训练或微调）
    - 基于提示词工程
    - 智能历史管理（模板摘要 + 完整最近历史）
    - 支持多意图场景
    - 优化LLM调用次数（默认每轮仅1次）
    
    属性:
        prompt_manager: 提示词管理器
        llm_client: LLM客户端
        messages: 完整的对话历史消息
        current_state: 当前累积的对话状态
        dialogue_history: 所有轮次的对话历史
        intent_history: 意图演变历史
        current_intents: 当前活跃的意图列表
        history_summary: 旧对话的摘要
        max_history_turns: 完整保留的最近对话轮数
        enable_history_summary: 是否启用历史摘要
        use_llm_summary: 是否使用LLM生成摘要（默认False）
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
        
        # 获取分类槽位用于归一化（优化）
        categorical_slots = {}
        if hasattr(self.prompt_manager, 'categorical_slots'):
            categorical_slots = self.prompt_manager.categorical_slots
        
        self.response_parser = ResponseParser(
            ontology_slots=self.prompt_manager.get_slot_names(),
            enable_filtering=not enable_dynamic_slots,  # 动态模式不过滤
            categorical_slots=categorical_slots  # 传递分类槽位
        )
        
        # 对话状态
        self.current_state: Dict[str, str] = {}
        self.dialogue_history: List[DialogueTurn] = []
        
        # 意图追踪（新增）
        self.intent_history: List[str] = []
        self.current_intents: List[str] = []
        
        # 多意图槽位存储（优化）- 支持按意图分离槽位
        self.intent_states: Dict[str, Dict[str, str]] = {}  # intent -> slots
        self.enable_intent_namespacing: bool = False  # 向后兼容，默认关闭
        
        # 历史管理（新增）
        self.max_history_turns = max_history_turns
        self.enable_history_summary = enable_history_summary
        self.use_llm_summary = use_llm_summary  # 新增：控制是否用LLM摘要
        self.history_summary: Optional[str] = None
        
        # 初始化消息列表，包含系统指令（关键修复：确保LLM收到JSON格式要求）
        self.messages: List[Dict[str, str]] = [
            {"role": "system", "content": self.prompt_manager.get_system_instruction()}
        ]
        
        logger.info(
            f"初始化DialogueStateTracker "
            f"(领域={domain}, 动态槽位={enable_dynamic_slots}, "
            f"历史轮数={max_history_turns}, 摘要={enable_history_summary}, "
            f"LLM摘要={use_llm_summary})"
        )
    
    @property
    def turns(self) -> List[DialogueTurn]:
        """
        获取对话历史（别名属性，用于向后兼容）
        
        返回:
            对话历史列表
        """
        return self.dialogue_history
    
    def reset_dialogue(self) -> None:
        """
        重置对话状态（开始新对话）
        """
        self.messages = [
            {"role": "system", "content": self.prompt_manager.get_system_instruction()}
        ]
        self.current_state = {}
        self.dialogue_history = []
        self.intent_history = []
        self.current_intents = []
        self.intent_states = {}  # 重置意图状态
        self.history_summary = None
        logger.info("对话状态已重置")
    
    async def process_turn(self, 
                          system_utterance: str, 
                          user_utterance: str) -> Dict[str, str]:
        """
        处理单轮对话（增强版 - 智能历史管理 + 意图追踪）
        
        执行步骤：
        1. 准备历史对话（智能摘要或完整历史）
        2. 调用LLM提取槽位更新
        3. 解析响应
        4. 更新状态和意图
        5. 管理历史（必要时触发摘要）
        
        参数:
            system_utterance: 系统的话语
            user_utterance: 用户的话语
            
        返回:
            更新后的累积对话状态
        """
        # 格式化当前轮次
        turn_prompt = f'system: "{system_utterance}"\nuser: "{user_utterance}"'
        
        # 准备历史对话（智能管理）
        history_for_prompt = self._prepare_history_for_prompt()
        
        # 如果有历史摘要，更新系统指令
        if self.history_summary and self.enable_history_summary:
            system_instruction = self.prompt_manager.get_system_instruction(
                history_summary=self.history_summary
            )
            # 更新系统消息
            self.messages[0] = {"role": "system", "content": system_instruction}
        
        # 添加历史对话到提示
        if history_for_prompt:
            full_prompt = f"{history_for_prompt}\n\n{turn_prompt}"
        else:
            full_prompt = turn_prompt
        
        # 添加到消息历史
        self.messages.append({"role": "user", "content": full_prompt})
        
        # 调用LLM（所有理解由LLM完成）
        if self.llm_client:
            try:
                # DEBUG: 记录发送给LLM的完整消息
                logger.debug("=" * 60)
                logger.debug("发送给LLM的消息:")
                for i, msg in enumerate(self.messages):
                    logger.debug(f"  [{i}] {msg['role']}: {msg['content'][:200]}...")
                logger.debug("=" * 60)
                
                raw_response = await self.llm_client.chat_async(
                    messages=self.messages,
                    temperature=0.0
                )
                
                # DEBUG: 记录LLM的完整响应
                logger.debug("=" * 60)
                logger.debug(f"LLM完整响应:\n{raw_response}")
                logger.debug("=" * 60)
                
            except Exception as e:
                logger.error(f"LLM调用失败: {e}")
                raw_response = "{}"
        else:
            logger.warning("未提供LLM客户端，使用空响应")
            raw_response = "{}"
        
        # 添加助手响应到历史
        self.messages.append({"role": "assistant", "content": raw_response})
        
        # 解析响应
        logger.debug(f"开始解析响应，长度: {len(raw_response)} 字符")
        turn_updates = self.response_parser.extract_json(raw_response)
        logger.debug(f"解析结果: {turn_updates}")
        
        # 归一化槽位值（优化）- 应用严格分类约束
        turn_updates = self.response_parser.normalize_extracted(
            turn_updates,
            self.prompt_manager.get_all_slots(),
            self.prompt_manager.categorical_slots or {}
        )
        logger.debug(f"归一化后: {turn_updates}")
        
        # 更新累积状态
        self._update_state(turn_updates)
        
        # 追踪意图（新增）
        self._track_intents(turn_updates)
        
        # 记录本轮对话
        turn = DialogueTurn(
            system_utterance=system_utterance,
            user_utterance=user_utterance,
            predicted_state=self.current_state.copy(),
            turn_updates=turn_updates,
            raw_llm_response=raw_response
        )
        self.dialogue_history.append(turn)
        
        # 智能历史管理（新增）
        await self._manage_history()
        
        logger.info(
            f"处理轮次 #{len(self.dialogue_history)}: "
            f"更新={turn_updates}, 意图={turn_updates.get('intent', '未识别')}"
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
            # 摘要旧的对话轮次
            old_turns = self.dialogue_history[:-self.max_history_turns]
            if old_turns:
                if self.use_llm_summary and self.llm_client:
                    # 使用LLM生成智能摘要（更详细但消耗资源）
                    self.history_summary = await self._summarize_old_turns(old_turns)
                    logger.info(
                        f"生成LLM历史摘要（轮次1-{len(old_turns)}），"
                        f"保留完整历史（轮次{len(old_turns)+1}-{total_turns}）"
                    )
                else:
                    # 使用模板方式生成摘要（快速且不消耗LLM）
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
        # 构建摘要提示
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
        # 提取意图演变
        intents = []
        for turn in turns:
            if turn.turn_updates and "intent" in turn.turn_updates:
                intent = turn.turn_updates["intent"]
                if intent and intent not in ["其他", "未知"]:
                    intents.append(intent)
        
        # 提取关键槽位
        key_slots = {}
        for turn in turns:
            if turn.turn_updates:
                for slot, value in turn.turn_updates.items():
                    if slot != "intent" and value and value.strip():
                        # 保留最新值
                        key_slots[slot] = value
        
        # 构建摘要
        summary_parts = [f"历史对话（共{len(turns)}轮）"]
        
        if intents:
            # 去重并保持顺序
            unique_intents = []
            seen = set()
            for intent in intents:
                if intent not in seen:
                    unique_intents.append(intent)
                    seen.add(intent)
            summary_parts.append(f"主要意图：{' → '.join(unique_intents)}")
        
        if key_slots:
            # 只显示最重要的几个槽位
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
        # 应用严格归一化（如果有prompt_manager）
        if hasattr(self, 'prompt_manager') and self.prompt_manager:
            # 获取允许的槽位和分类槽位
            allowed_slots = self.prompt_manager.get_all_slots()
            categorical_slots = self.prompt_manager.categorical_slots or {}
            
            # 使用strict模式进行归一化
            updates = self.response_parser.normalize_extracted(
                updates,
                allowed_slots,
                categorical_slots
            )
        
        # 提取当前意图
        current_intent = updates.get("intent")
        
        # 更新全局状态（保持向后兼容）
        for slot, value in updates.items():
            if value and value.strip():  # 只更新非空值
                self.current_state[slot] = value
        
        # 如果启用意图命名空间，同时维护按意图分离的状态
        if self.enable_intent_namespacing and current_intent:
            # 初始化该意图的状态字典
            if current_intent not in self.intent_states:
                self.intent_states[current_intent] = {}
            
            # 存储非intent字段到对应意图下
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
            
            # 添加到意图历史
            self.intent_history.append(new_intent)
            
            # 更新当前活跃意图
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
    
    def get_statistics(self) -> Dict[str, any]:
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
            "intent_states_count": len(self.intent_states)  # 新增
        }
    
    # 新增：意图特定状态查询方法
    
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
