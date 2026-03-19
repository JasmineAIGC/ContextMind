"""
Evolve 应用基类 — 所有场景共享的对话处理逻辑

三个内置场景（chat / callcenter / insurance）共用此基类，
无需各自维护近乎相同的 app.py 文件。

使用示例::

    from contextmind.scenarios.app import EvolveApplication
    from contextmind.scenarios import get_chat_scenario
    from contextmind.infra.llm_client import AdkLLMClient

    config = get_chat_scenario()
    llm = AdkLLMClient()
    app = EvolveApplication.from_scenario(llm, config)
    reply = await app.process_turn("你好！")
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from contextmind.modes.evolve import (
    EvolveEngine,
    Message,
    MessageRole,
    ContextResult,
    ContextSource,
    ConversationSummarizer,
    SummarizationConfig,
    get_logger,
)
from contextmind.infra.llm_client import AdkLLMClient, LLMConfig

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = get_logger(__name__)

RELEVANCE_THRESHOLD = 0.3


class EvolveApplication:
    """通用 Evolve 对话应用。

    封装 EvolveEngine 的「检索 → 构建 Prompt → LLM 生成 → 更新 → 知识提取」
    五步流水线，所有场景（chat / callcenter / insurance 及自定义场景）共用同一实现。

    参数
    ----
    evolve_engine : EvolveEngine
        已初始化的 Evolve 引擎。
    system_prompt : str
        系统提示词；通常从 ``ScenarioConfig.system_prompt`` 读取。
    llm_client : AdkLLMClient | None
        LLM 客户端实例；若为 None 则仅使用模拟回复。
    history_turns : int
        Prompt 中最多保留的历史对话轮数。
    summarize_threshold : int
        触发对话摘要的最小轮数（超过后自动摘要早期历史）。
    keep_recent_turns : int
        摘要后保留的最近原始轮数。
    """

    def __init__(
        self,
        evolve_engine: EvolveEngine,
        system_prompt: str = "你是一个智能对话助手。",
        llm_client: Optional[AdkLLMClient] = None,
        history_turns: int = 10,
        summarize_threshold: int = 15,
        keep_recent_turns: int = 5,
    ) -> None:
        self.evolve_engine = evolve_engine
        self.system_prompt = system_prompt
        self.history_turns = history_turns
        self.step_timings: Dict[str, float] = {}

        self.llm_client = llm_client
        self.use_real_llm = llm_client is not None

        summarization_config = SummarizationConfig(
            summarize_threshold=summarize_threshold,
            keep_recent_turns=keep_recent_turns,
            method="rule",
        )
        self.summarizer = ConversationSummarizer(
            config=summarization_config,
            llm_client=self.llm_client,
        )

        logger.info(
            f"[EvolveApplication] 初始化完成 (LLM: {'✓' if self.use_real_llm else '模拟'},"
            f" 摘要阈值: {summarize_threshold} 轮)"
        )

    # ------------------------------------------------------------------ #
    # 工厂方法
    # ------------------------------------------------------------------ #

    @classmethod
    def from_scenario(
        cls,
        llm_client: Any,
        scenario_config: Any,
        **kwargs: Any,
    ) -> "EvolveApplication":
        """从场景配置创建 EvolveApplication 实例（标准工厂接口）。

        实现 BaseTracker.from_scenario 协议，与 DST / FnCTOD / PyTOD 统一。

        Args:
            llm_client:      LLM 客户端实例（AdkLLMClient / SimpleLLMClient）。
            scenario_config: ScenarioConfig 场景配置对象。
            **kwargs:        传递给构造函数的额外参数。
        """
        return cls.create_from_config(llm_client, scenario_config)

    @classmethod
    def create_from_config(cls, llm_client: Any, scenario_config: Any) -> "EvolveApplication":
        """从场景配置创建 EvolveApplication 实例。

        Args:
            llm_client:      LLM 客户端实例（AdkLLMClient / SimpleLLMClient）。
            scenario_config: ScenarioConfig 场景配置对象。
        """
        engine = EvolveEngine(
            app_name=f"demo_{scenario_config.name}",
            user_id="demo_user",
            llm_client=llm_client,
        )
        return cls(
            evolve_engine=engine,
            system_prompt=scenario_config.system_prompt,
            llm_client=llm_client,
        )

    # ------------------------------------------------------------------ #
    # Prompt 构建
    # ------------------------------------------------------------------ #

    async def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """将 EvolveEngine 检索结果组装为最终 Prompt。

        结构：
        1. 系统提示词
        2. 相关长期记忆（≥ RELEVANCE_THRESHOLD）
        3. 对话历史（超长时自动摘要）
        4. 当前用户输入
        """
        parts: List[str] = [self.system_prompt]

        # --- 长期记忆 ---
        memory_items = [i for i in context.items if i.source == ContextSource.MEMORY]
        relevant = [i for i in memory_items if i.score >= RELEVANCE_THRESHOLD]
        if relevant:
            mem_text = "\n".join(f"- {i.content}" for i in relevant[:5])
            parts.append(f"\n## 已知信息\n{mem_text}")
            logger.debug(f"[Prompt] 长期记忆: {len(relevant)} 条")

        # --- 对话历史（含摘要）---
        history_items = [i for i in context.items if i.source == ContextSource.HISTORY]
        if history_items:
            summary, recent = await self.summarizer.get_summary_and_recent(history_items)
            if summary:
                parts.append(f"\n## 早期对话摘要\n{summary}")
            if recent:
                parts.append("\n## 最近对话\n" + "\n".join(i.content for i in recent))
            else:
                keep = history_items[-self.history_turns:]
                parts.append("\n## 对话历史\n" + "\n".join(i.content for i in keep))

        # --- 当前输入 ---
        parts.append(f"\n## 当前问题\n{user_input}")
        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # 主处理流程
    # ------------------------------------------------------------------ #

    async def process_turn(
        self,
        user_input: str,
        debug: bool = False,
    ) -> Any:
        """处理单轮对话，返回助手回复文本。

        流程：检索 → Prompt → LLM → 更新 → 知识提取。

        Args:
            user_input: 用户本轮输入。
            debug:      若为 True，同时返回调试信息字典。

        Returns:
            ``str``（debug=False）或 ``(str, dict)``（debug=True）。
        """
        self.step_timings = {}
        debug_info: Dict[str, Any] = {} if debug else {}

        # 步骤 1：上下文检索
        t = time.time()
        context_result = await self.evolve_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        self.step_timings["上下文检索"] = time.time() - t

        # 步骤 2：Prompt 构建
        t = time.time()
        prompt = await self.build_prompt(user_input, context_result)
        self.step_timings["上下文整合"] = time.time() - t
        if debug:
            debug_info["prompt"] = prompt

        # 步骤 3：LLM 生成
        t = time.time()
        if self.use_real_llm and self.llm_client:
            try:
                _, response = await self.llm_client.generate_async(prompt)
            except Exception as exc:
                logger.error(f"[LLM Error] {exc}")
                response = f"[LLM调用失败] {exc}"
        else:
            response = f"[模拟回复] 收到：{user_input}"
        self.step_timings["LLM生成"] = time.time() - t

        # 步骤 4：对话更新
        t = time.time()
        await self.evolve_engine.update(
            user_input=user_input, assistant_response=response
        )
        self.step_timings["对话更新"] = time.time() - t

        # 步骤 5：知识提取
        t = time.time()
        try:
            await self.evolve_engine.extract_knowledge(auto_store=True)
        except Exception as exc:
            logger.warning(f"知识提取失败: {exc}")
        self.step_timings["知识提取"] = time.time() - t

        if debug:
            return response, debug_info
        return response

    # ------------------------------------------------------------------ #
    # 协议方法（BaseTracker 接口）
    # ------------------------------------------------------------------ #

    def get_current_state(self) -> Dict[str, Any]:
        """返回当前记忆库缓存中的知识摘要（实现 BaseTracker 协议）。

        Returns:
            记忆条目列表（以 content 字符串为值）组成的字典；
            若记忆库尚无内容则返回空字典。
        """
        memory_cache = self.evolve_engine.memory_bank.get_memory_cache()
        if not memory_cache:
            return {}
        return {
            f"memory_{i}": item.content
            for i, item in enumerate(memory_cache)
        }

    async def reset(self) -> None:  # type: ignore[override]
        """重置对话，清空会话历史（实现 BaseTracker 协议的异步版本）。

        注意：长期记忆库（MemoryBank）不会被清空，仅当前会话历史被重置。
        由于底层 EvolveEngine.clear_session() 是协程，此方法为 async。
        在同步上下文中，可以使用 asyncio.run(app.reset()) 调用。
        """
        try:
            await self.evolve_engine.clear_session()
        except Exception as exc:
            logger.warning(f"[EvolveApplication] reset 失败: {exc}")


# ---------------------------------------------------------------------------
# 向后兼容别名（旧代码通过 scenarios.chat.app 导入的类名）
# ---------------------------------------------------------------------------

ChatApplication = EvolveApplication
CallCenterApplication = EvolveApplication
InsuranceApplication = EvolveApplication

__all__ = [
    "EvolveApplication",
    "ChatApplication",
    "CallCenterApplication",
    "InsuranceApplication",
]
