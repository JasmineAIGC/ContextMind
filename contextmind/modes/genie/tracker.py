"""
GenieTracker — Genie Worksheets 驱动的对话追踪器

实现 BaseTracker 协议，将 Genie 的 Worksheet 声明式策略执行嵌入
ContextMind 框架，作为第五种执行模式（mode="genie"）。

执行流程（每轮）
-----------------
1. PolicyExecutor 确认流检查                ← 检测 PENDING_CONFIRM 字段，处理 yes/no
2. SemanticParser(LLM-1)                   ← 从用户话语提取字段赋值
3. PolicyExecutor.fill_batch()             ← 更新 Worksheet 状态
4. on_success dispatch                     ← 触发字段关联的 API 回调
5. AgentActs 计算                          ← 确定性：Ask/Confirm/Report
6. ResponseGenerator(LLM-2)               ← 根据 AgentActs + 状态生成自然语言回复

降级设计
--------
当没有 PostgreSQL 时（默认），SUQL 检索降级为 LLM 直接语义回答，
功能等同于 Worksheet 约束驱动的增强版 DST。

与 ContextPipeline 集成
------------------------
通过 ``ContextPipeline(mode="genie", worksheet_path="xxx.csv")``
或 ``pipeline.load_kb("schema.json", worksheet_path="xxx.csv")``
激活本追踪器。

API 注册（on_success dispatch）
--------------------------------
通过 ``tracker.register_api("func_name", callable)`` 注册函数，
当 Worksheet 中 ``on_success="func_name"`` 的字段被成功填写后自动调用::

    tracker = GenieTracker(...)
    tracker.register_api("book_restaurant", my_booking_func)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING, Union

from contextmind.modes.genie.agent_acts import (
    AgentActs,
    AskAgentAct,
    AskForConfirmationAgentAct,
    ReportAgentAct,
)
from contextmind.modes.genie.policy_executor import FieldStatus, PolicyExecutor, WorksheetState
from contextmind.modes.genie.semantic_parser import SemanticParser
from contextmind.schema_builder.genie_worksheets.schema_types import GenieSchema

if TYPE_CHECKING:
    from contextmind.infra.llm_client import AdkLLMClient
    from contextmind.scenarios import ScenarioConfig

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 回复生成器提示词
# ---------------------------------------------------------------------------

_RESPONSE_SYSTEM = """你是一个任务型对话的助手（对话管理器）。
根据对话历史、当前 Worksheet 填写状态、本轮动作指令（Agent Actions），
生成一条自然、友好的中文回复。

## 回复要求
- 严格按照 Agent Actions 列表的顺序逐条 verbalize（不要遗漏任何一条）
- AskField：自然地引导用户提供指定字段的值（枚举字段请列出可选值）
- AskForFieldConfirmation：重述字段值，以 yes/no 方式请求用户确认
- Report：报告 API 调用结果，如无数据则明确说明
- 语气友好、专业，不要冗长解释
- 直接输出回复文本，不要任何前缀或格式标记
"""

_RESPONSE_USER_TEMPLATE = """\
## 业务场景
{scene_description}

## Worksheet 当前状态
{worksheet_status}

## 本轮 Agent Actions（按顺序 verbalize）
{agent_actions}

## 对话历史（最近 {history_turns} 轮）
{history}

## 用户最新话语
{user_utterance}

## 本轮新提取的字段
{extracted_fields}

请生成回复："""

# 确认意图识别提示词（用于 yes/no 检测）
_CONFIRM_SYSTEM = """你是一个意图分类器。判断用户话语是否是对前一条问题的"确认（是）"或"拒绝（否）"回答。
只输出 YES 或 NO，不要任何其他文字。"""

_CONFIRM_USER_TEMPLATE = """\
上一轮系统询问：{prev_system_utterance}
用户回复：{user_utterance}
用户是否在确认（YES）或拒绝（NO）？"""


# ---------------------------------------------------------------------------
# GenieTracker
# ---------------------------------------------------------------------------

class GenieTracker:
    """Genie Worksheets 驱动的对话追踪器。

    实现 ``BaseTracker`` 协议（结构子类型），可直接用于 ``ContextPipeline``。

    参数
    ----
    llm_client :
        ``AdkLLMClient`` 实例，供语义解析器和回复生成器使用。
    schema :
        含 ``policy_fields`` 的 ``ServiceSchema``（由 ``WorksheetLoader`` 加载）。
    scene_description :
        业务场景描述，注入回复生成器提示词。
    intent_name :
        指定执行哪个意图（Worksheet 中的一节）；为 None 时使用第一个含
        policy_fields 的意图。
    max_history_turns :
        构建提示词时保留的最近历史轮次数（默认 10）。
    """

    def __init__(
        self,
        llm_client: "AdkLLMClient",
        schema: GenieSchema,
        scene_description: str = "",
        intent_name: Optional[str] = None,
        max_history_turns: int = 10,
    ) -> None:
        self._llm = llm_client
        self._schema = schema
        self._scene_description = scene_description
        self._max_history_turns = max_history_turns

        # 初始化子组件
        self._executor = PolicyExecutor(schema, intent_name=intent_name)
        self._semantic_parser = SemanticParser(llm_client, max_history_turns=max_history_turns)

        # on_success API 注册表：{func_name: callable}
        self._api_registry: Dict[str, Callable[..., Any]] = {}

        # 对话历史（用于 LLM 提示词上下文）
        self._history: List[Dict[str, str]] = []

    # ------------------------------------------------------------------
    # BaseTracker 协议实现
    # ------------------------------------------------------------------

    @classmethod
    def from_scenario(
        cls,
        llm_client: "AdkLLMClient",
        scenario_config: Any,
        schema: Optional[GenieSchema] = None,
        worksheet_path: Optional[Union[str, Path]] = None,
        intent_name: Optional[str] = None,
        **kwargs: Any,
    ) -> "GenieTracker":
        """从场景配置创建 ``GenieTracker`` 实例（工厂方法）。

        Args:
            llm_client:     LLM 客户端。
            scenario_config: 场景配置（``ScenarioConfig``）。
            schema:          ``GenieSchema``（可选，优先于 worksheet_path）。
            worksheet_path:  Worksheet 文件路径（CSV 或 JSON）；若 schema 未提供，
                             则从此路径加载 schema。
            intent_name:     目标意图名称（可选）。

        Returns:
            初始化完成的 ``GenieTracker``。
        """
        scene_desc = getattr(scenario_config, "scene_description", "") or ""
        scene_name = getattr(scenario_config, "scene_name", "") or ""

        loaded_schema: Optional[GenieSchema] = schema

        if loaded_schema is None and worksheet_path is not None:
            from contextmind.schema_builder.genie_worksheets import WorksheetLoader
            ws_path = Path(worksheet_path)
            if ws_path.suffix.lower() == ".csv":
                loaded_schema = WorksheetLoader.from_csv(
                    ws_path,
                    service_name=scene_name or "WorksheetService",
                    service_description=scene_desc,
                )
            elif ws_path.suffix.lower() in (".json", ".jsonl"):
                loaded_schema = WorksheetLoader.from_json(ws_path)
            else:
                raise ValueError(
                    f"worksheet_path 只支持 .csv 或 .json 文件，得到: {ws_path.suffix}"
                )
            logger.info(
                f"[GenieTracker] 从 Worksheet 文件加载 schema: {ws_path.name}"
            )

        if loaded_schema is None:
            raise ValueError(
                "GenieTracker 需要 schema 或 worksheet_path 参数之一"
            )

        return cls(
            llm_client=llm_client,
            schema=loaded_schema,
            scene_description=scene_desc or scene_name,
            intent_name=intent_name,
            max_history_turns=kwargs.get("max_history_turns", 10),
        )

    # ------------------------------------------------------------------
    # on_success API 注册
    # ------------------------------------------------------------------

    def register_api(self, func_name: str, func: Callable[..., Any]) -> None:
        """注册 on_success 回调函数。

        当 Worksheet 中 ``on_success=func_name`` 的字段被成功填写后，
        ``process_turn`` 会自动调用此函数，并将结果以 ``ReportAgentAct`` 呈现。

        Args:
            func_name: 与 ``PolicyField.on_success`` 对应的函数名称。
            func:      要调用的函数（可以是同步或无参函数）。
        """
        self._api_registry[func_name] = func
        logger.debug(f"[GenieTracker] 注册 on_success API: {func_name!r}")

    async def process_turn(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理单轮用户输入，推进 Worksheet 填写状态。

        完整步骤：
        1. 确认流检查：检测 PENDING_CONFIRM 字段，解析用户的 yes/no 意图
        2. SemanticParser(LLM-1) 提取字段赋值
        3. PolicyExecutor.fill_batch() 更新 Worksheet 状态
        4. on_success dispatch：触发字段关联的 API 回调
        5. AgentActs 计算（确定性）
        6. ResponseGenerator(LLM-2) 生成自然语言回复

        Returns:
            字典，包含：

            - ``response``         : 系统生成的自然语言回复
            - ``worksheet_state``  : 当前 Worksheet 字段值字典
            - ``extracted_fields`` : 本轮提取的字段赋值字典
            - ``is_complete``      : Worksheet 是否已完成（bool）
            - ``next_field``       : 下一个待填字段名（或 None）
            - ``missing_required`` : 未填必填字段名列表
            - ``errors``           : 本轮校验错误列表
            - ``agent_acts``       : 本轮 AgentActs 文本列表（调试用）
            - ``confirmed_fields`` : 本轮确认的字段名列表
            - ``rejected_fields``  : 本轮拒绝的字段名列表
            - ``dispatched_apis``  : 本轮触发的 on_success API 名称列表
        """
        agent_acts = AgentActs()
        confirmed_fields: List[str] = []
        rejected_fields: List[str] = []
        dispatched_apis: List[str] = []

        # ------------------------------------------------------------------
        # Step 1: 确认流检查（PENDING_CONFIRM 字段的 yes/no 处理）
        # ------------------------------------------------------------------
        pending_confirm = self._executor.get_pending_confirm_fields()
        if pending_confirm:
            pf_to_confirm = pending_confirm[0]  # 每轮处理一个确认
            is_yes = await self._detect_confirm_intent(user_utterance)
            if is_yes:
                self._executor.confirm_field(pf_to_confirm.name)
                confirmed_fields.append(pf_to_confirm.name)
                logger.debug(f"[GenieTracker] 用户确认字段: {pf_to_confirm.name!r}")
            else:
                self._executor.reject_field(pf_to_confirm.name)
                rejected_fields.append(pf_to_confirm.name)
                logger.debug(f"[GenieTracker] 用户拒绝字段: {pf_to_confirm.name!r}")

        # ------------------------------------------------------------------
        # Step 2: 语义解析（LLM-1）— 只在没有待确认字段时正常提取
        # ------------------------------------------------------------------
        extracted: Dict[str, Any] = {}
        parse_errors: List[str] = []
        if not pending_confirm:
            try:
                extracted = await self._semantic_parser.parse(
                    user_utterance,
                    self._executor,
                    history=self._history,
                )
            except Exception as exc:
                logger.error(f"[GenieTracker] 语义解析失败: {exc}")

            # ------------------------------------------------------------------
            # Step 3: 更新 Worksheet 状态
            # ------------------------------------------------------------------
            if extracted:
                parse_errors = self._executor.fill_batch(extracted)

        # ------------------------------------------------------------------
        # Step 4: on_success dispatch（触发字段关联 API 回调）
        # ------------------------------------------------------------------
        for field_name, api_name in self._executor.get_on_success_actions():
            func = self._api_registry.get(api_name)
            if func is None:
                logger.debug(
                    f"[GenieTracker] on_success API '{api_name}' 未注册，跳过"
                )
                continue
            try:
                import asyncio
                import inspect as _inspect
                if _inspect.iscoroutinefunction(func):
                    result = await func()
                else:
                    result = await asyncio.get_event_loop().run_in_executor(
                        None, func
                    )
                agent_acts.add(ReportAgentAct(api_name=api_name, result=result,
                                              field_name=field_name))
                self._executor.mark_on_success_dispatched(field_name)
                dispatched_apis.append(api_name)
                logger.info(f"[GenieTracker] on_success API '{api_name}' 调用成功")
            except Exception as exc:
                logger.error(f"[GenieTracker] on_success API '{api_name}' 调用失败: {exc}")
                agent_acts.add(ReportAgentAct(api_name=api_name,
                                              result={"error": str(exc)},
                                              field_name=field_name))

        # ------------------------------------------------------------------
        # Step 5: AgentActs 计算（确定性，无 LLM）
        # ------------------------------------------------------------------
        intent_name = self._executor.intent.name if self._executor.intent else ""

        # 检查新出现的 PENDING_CONFIRM 字段（本轮刚被填写 + confirm=True）
        new_pending = self._executor.get_pending_confirm_fields()
        for pf in new_pending:
            if pf.name not in confirmed_fields and pf.name not in rejected_fields:
                act = AskForConfirmationAgentAct(
                    field=pf,
                    value=self._executor.state.get_value(pf.name),
                    intent_name=intent_name,
                )
                if agent_acts.add(act):
                    break  # 每轮最多一个确认请求

        # 若没有确认请求，则寻找下一个需要询问的字段
        if agent_acts.can_ask():
            next_field = self._executor.next_required_field()
            if next_field:
                agent_acts.add(AskAgentAct(field=next_field, intent_name=intent_name))

        # ------------------------------------------------------------------
        # Step 6: 回复生成（LLM-2）
        # ------------------------------------------------------------------
        response = await self._generate_response(user_utterance, extracted, agent_acts)

        # 更新历史
        self._history.append({"role": "user", "content": user_utterance})
        self._history.append({"role": "assistant", "content": response})

        # 构建返回字典
        state = self._executor.state
        next_field_final = self._executor.next_required_field()
        missing = self._executor.get_missing_required()

        return {
            "response": response,
            "worksheet_state": state.field_values,
            "extracted_fields": extracted,
            "is_complete": self._executor.is_complete(),
            "next_field": next_field_final.name if next_field_final else None,
            "missing_required": [pf.name for pf in missing],
            "errors": parse_errors,
            "agent_acts": agent_acts.to_prompt_lines(),
            "confirmed_fields": confirmed_fields,
            "rejected_fields": rejected_fields,
            "dispatched_apis": dispatched_apis,
            # 兼容 BaseTracker 通用字段
            "state": state.field_values,
            "turn_updates": extracted,
        }

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前 Worksheet 累积字段值（实现 BaseTracker 协议）。"""
        return dict(self._executor.state.field_values)

    def reset(self) -> None:
        """清空对话历史和 Worksheet 状态（实现 BaseTracker 协议）。"""
        self._executor.reset()
        self._history.clear()
        logger.debug("[GenieTracker] 会话状态已重置")

    # ------------------------------------------------------------------
    # 公共辅助方法
    # ------------------------------------------------------------------

    @property
    def worksheet_state(self) -> WorksheetState:
        """当前 Worksheet 状态（含字段值、状态标记等）。"""
        return self._executor.state

    @property
    def is_complete(self) -> bool:
        """Worksheet 是否已完成所有必填字段。"""
        return self._executor.is_complete()

    def update_schema(self, schema: GenieSchema, intent_name: Optional[str] = None) -> None:
        """替换当前 schema 和意图，重置状态机（不清空对话历史）。"""
        self._schema = schema
        self._executor = PolicyExecutor(schema, intent_name=intent_name)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    async def _generate_response(
        self,
        user_utterance: str,
        extracted: Dict[str, Any],
        agent_acts: Optional[AgentActs] = None,
    ) -> str:
        """调用 LLM-2 生成自然语言回复。"""
        state = self._executor.state
        next_field = self._executor.next_required_field()

        # Worksheet 状态摘要
        status_lines: List[str] = []
        for pf in self._executor._policy_fields:
            status_code = state.field_statuses.get(pf.name, FieldStatus.EMPTY)
            if state.is_filled(pf.name):
                status_label = {
                    FieldStatus.FILLED: "已填",
                    FieldStatus.PENDING_CONFIRM: "待确认",
                    FieldStatus.CONFIRMED: "已确认",
                }.get(status_code, "已填")
                status_lines.append(
                    f"  [{status_label}] {pf.name}: {state.get_value(pf.name)!r}"
                )
            else:
                mark = "必填" if pf.required else "可选"
                status_lines.append(f"  [待填/{mark}] {pf.name}")
        worksheet_status = "\n".join(status_lines) or "（无字段）"

        # Agent Actions 文本列表
        if agent_acts and len(agent_acts) > 0:
            agent_actions_text = "\n".join(
                f"  {i+1}. {line}"
                for i, line in enumerate(agent_acts.to_prompt_lines())
            )
        elif self._executor.is_complete():
            agent_actions_text = "  Worksheet 已完成，总结并确认所有已填信息。"
        else:
            agent_actions_text = "  （无明确动作，根据状态自然引导对话）"

        # 对话历史
        recent = self._history[-self._max_history_turns * 2:]
        hist_lines = []
        for turn in recent:
            role = "用户" if turn.get("role") == "user" else "助手"
            hist_lines.append(f"{role}：{turn.get('content', '')}")
        hist_text = "\n".join(hist_lines) or "（无历史）"

        # 本轮提取结果
        if extracted:
            ext_lines = [f"  {k}: {v!r}" for k, v in extracted.items()]
            extracted_text = "\n".join(ext_lines)
        else:
            extracted_text = "（未提取到新字段值）"

        user_prompt = _RESPONSE_USER_TEMPLATE.format(
            scene_description=self._scene_description or "通用任务型对话",
            worksheet_status=worksheet_status,
            agent_actions=agent_actions_text,
            history_turns=self._max_history_turns,
            history=hist_text,
            user_utterance=user_utterance,
            extracted_fields=extracted_text,
        )

        try:
            if hasattr(self._llm, "chat"):
                return str(await self._llm.chat(
                    system_prompt=_RESPONSE_SYSTEM,
                    user_message=user_prompt,
                ))
            messages = [
                {"role": "system", "content": _RESPONSE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ]
            if hasattr(self._llm, "generate_async"):
                return str(await self._llm.generate_async(messages))
            import asyncio
            return str(await asyncio.get_event_loop().run_in_executor(
                None, lambda: self._llm.generate(messages)
            ))
        except Exception as exc:
            logger.error(f"[GenieTracker] 回复生成失败: {exc}")
            if next_field:
                return f"请问您能提供{next_field.description or next_field.name}吗？"
            return "好的，请问还有什么需要确认的信息吗？"

    async def _detect_confirm_intent(self, user_utterance: str) -> bool:
        """判断用户话语是否表示确认（YES），否则为拒绝（NO）。

        使用 LLM 进行分类，失败时默认返回 False（拒绝），更安全。
        """
        prev_system = ""
        if len(self._history) >= 1:
            last = self._history[-1]
            if last.get("role") == "assistant":
                prev_system = last.get("content", "")

        # 快速启发式检查（避免不必要 LLM 调用）
        low = user_utterance.strip().lower()
        if low in ("是", "对", "确认", "好的", "ok", "yes", "确定", "没问题", "正确", "嗯"):
            return True
        if low in ("否", "不", "错误", "重新填", "no", "不对", "取消", "修改"):
            return False

        user_prompt = _CONFIRM_USER_TEMPLATE.format(
            prev_system_utterance=prev_system or "（系统询问确认）",
            user_utterance=user_utterance,
        )
        try:
            if hasattr(self._llm, "chat"):
                raw = str(await self._llm.chat(
                    system_prompt=_CONFIRM_SYSTEM,
                    user_message=user_prompt,
                ))
            else:
                messages = [
                    {"role": "system", "content": _CONFIRM_SYSTEM},
                    {"role": "user", "content": user_prompt},
                ]
                if hasattr(self._llm, "generate_async"):
                    raw = str(await self._llm.generate_async(messages))
                else:
                    import asyncio
                    raw = str(await asyncio.get_event_loop().run_in_executor(
                        None, lambda: self._llm.generate(messages)
                    ))
            return raw.strip().upper().startswith("YES")
        except Exception as exc:
            logger.error(f"[GenieTracker] 确认意图检测失败: {exc}")
            return False
