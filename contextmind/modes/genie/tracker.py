"""
GenieTracker — Genie Worksheets 驱动的对话追踪器

实现 BaseTracker 协议，将 Genie 的 Worksheet 声明式策略执行嵌入
ContextMind 框架，作为第五种执行模式（mode="genie"）。

执行流程（每轮）
-----------------
1. PolicyExecutor.next_required_field()    ← 确定性，无 LLM
2. SemanticParser(LLM-1)                  ← 从用户话语提取字段赋值
3. PolicyExecutor.fill_batch()            ← 更新 Worksheet 状态
4. ResponseGenerator(LLM-2)              ← 根据状态生成自然语言回复

降级设计
--------
当没有 PostgreSQL 时（默认），SUQL 检索降级为 LLM 直接语义回答，
功能等同于 Worksheet 约束驱动的增强版 DST。

与 ContextPipeline 集成
------------------------
通过 ``ContextPipeline(mode="genie", worksheet_path="xxx.csv")``
或 ``pipeline.load_kb("schema.json", worksheet_path="xxx.csv")``
激活本追踪器。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Union

from contextmind.modes.genie.policy_executor import PolicyExecutor, WorksheetState
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
根据对话历史、当前 Worksheet 填写状态和系统提示，生成一条自然、友好的中文回复。

## 回复要求
- 若 Worksheet 尚未完成，在回复中自然地引导用户提供下一个缺失字段
- 若 Worksheet 已完成，总结用户提供的信息并给予确认回复
- 语气友好、专业，1-3 句话，不要冗长解释
- 直接输出回复文本，不要任何前缀或格式标记
"""

_RESPONSE_USER_TEMPLATE = """\
## 业务场景
{scene_description}

## Worksheet 当前状态
{worksheet_status}

{next_field_hint}
## 对话历史（最近 {history_turns} 轮）
{history}

## 用户最新话语
{user_utterance}

## 本轮新提取的字段
{extracted_fields}

请生成回复："""


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

    async def process_turn(
        self,
        user_utterance: str,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """处理单轮用户输入，推进 Worksheet 填写状态。

        步骤：
        1. SemanticParser(LLM-1) 提取字段赋值
        2. PolicyExecutor 更新状态
        3. ResponseGenerator(LLM-2) 生成回复

        Returns:
            字典，包含：

            - ``response``         : 系统生成的自然语言回复
            - ``worksheet_state``  : 当前 Worksheet 字段值字典
            - ``extracted_fields`` : 本轮提取的字段赋值字典
            - ``is_complete``      : Worksheet 是否已完成（bool）
            - ``next_field``       : 下一个待填字段名（或 None）
            - ``missing_required`` : 未填必填字段名列表
            - ``errors``           : 本轮校验错误列表
        """
        # Step 1: 语义解析（LLM-1）
        extracted: Dict[str, Any] = {}
        try:
            extracted = await self._semantic_parser.parse(
                user_utterance,
                self._executor,
                history=self._history,
            )
        except Exception as exc:
            logger.error(f"[GenieTracker] 语义解析失败: {exc}")

        # Step 2: 更新 Worksheet 状态
        parse_errors: List[str] = []
        if extracted:
            parse_errors = self._executor.fill_batch(extracted)

        # Step 3: 生成回复（LLM-2）
        response = await self._generate_response(user_utterance, extracted)

        # 更新历史
        self._history.append({"role": "user", "content": user_utterance})
        self._history.append({"role": "assistant", "content": response})

        # 构建返回字典
        state = self._executor.state
        next_field = self._executor.next_required_field()
        missing = self._executor.get_missing_required()

        return {
            "response": response,
            "worksheet_state": state.field_values,
            "extracted_fields": extracted,
            "is_complete": self._executor.is_complete(),
            "next_field": next_field.name if next_field else None,
            "missing_required": [pf.name for pf in missing],
            "errors": parse_errors,
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
    ) -> str:
        """调用 LLM-2 生成自然语言回复。"""
        state = self._executor.state
        next_field = self._executor.next_required_field()

        # Worksheet 状态摘要
        status_lines: List[str] = []
        for pf in self._executor._policy_fields:
            if state.is_filled(pf.name):
                status_lines.append(f"  [已填] {pf.name}: {state.get_value(pf.name)!r}")
            else:
                mark = "必填" if pf.required else "可选"
                status_lines.append(f"  [待填/{mark}] {pf.name}")
        worksheet_status = "\n".join(status_lines) or "（无字段）"

        # 下一个待填字段提示
        if next_field:
            hint = f"## 下一个待填字段\n请询问用户提供：{next_field.name}"
            if next_field.description:
                hint += f"（{next_field.description}）"
            if next_field.field_type == "enum" and next_field.possible_values:
                hint += f"\n可选值：{', '.join(next_field.possible_values)}"
            hint += "\n"
        elif self._executor.is_complete():
            hint = "## Worksheet 已完成\n所有必填字段已收集，可以进行后续操作。\n"
        else:
            hint = ""

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
            next_field_hint=hint,
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
