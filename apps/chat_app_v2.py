"""
ChatApplication - 通用闲聊应用（基于 ADK 重构版）

展示如何使用 BaseApplication 和 ADK 模式构建应用。
适用于日常闲聊、知识问答、娱乐互动等场景。

Version: v0.4.2 - 重构为使用 BaseApplication 和 ADK 模式
"""

from typing import Optional, Dict

from apps.base_application import BaseApplication, PromptBuilder
from evolution import EvolutionEngine
from evolution.core.models import ContextResult, ContextSource, get_logger
from evolution.pipeline.summarizer import SummarizationConfig

# 导入统一的系统提示词
from prompts import CHAT_SYSTEM_PROMPT

logger = get_logger(__name__)


class ChatApplication(BaseApplication):
    """
    通用闲聊应用示例（重构版）
    
    继承 BaseApplication，只需实现特定的 prompt 构建逻辑。
    其他流程（上下文优化、LLM 调用、知识提取等）由基类统一处理。
    """
    
    def __init__(
        self,
        context_engine: EvolutionEngine,
        system_prompt: str = CHAT_SYSTEM_PROMPT,
        history_turns: int = 10,
        llm_config = None,  # 保持向后兼容
        use_real_llm: bool = True,
        extraction_method: str = None,
        **config
    ):
        """
        初始化闲聊应用
        
        Args:
            context_engine: 上下文引擎
            system_prompt: 系统提示词
            history_turns: Prompt 中包含的历史轮数
            llm_config: LLM 配置（保留用于兼容，实际从 engine 获取）
            use_real_llm: 是否使用真实 LLM
            extraction_method: 知识提取方式
            **config: 其他配置参数
        """
        # 闲聊场景使用 LLM 摘要以获得更高质量
        summarization_config = SummarizationConfig(
            summarize_threshold=5,  # 超过5轮触发摘要
            keep_recent_turns=3,    # 保留最近3轮
            method="llm"            # 使用LLM摘要
        )
        
        super().__init__(
            context_engine=context_engine,
            system_prompt=system_prompt,
            history_turns=history_turns,
            use_real_llm=use_real_llm,
            extraction_method=extraction_method,
            summarization_config=summarization_config,
            **config
        )
    
    async def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """
        构建闲聊场景的 Prompt
        
        包含：系统提示词、相关记忆、对话历史、当前输入
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的 Prompt
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[ChatApp Prompt] 开始构建 Prompt")
        logger.info("=" * 100)
        
        prompt_parts = [self.system_prompt]
        
        # 1. 添加相关记忆（使用 PromptBuilder 工具类）
        memory_text = PromptBuilder.format_memory(
            context,
            relevance_threshold=0.3
        )
        
        if memory_text:
            prompt_parts.append(f"\n## 已知信息\n{memory_text}")
            logger.info("[ChatApp Prompt] ✓ 添加相关记忆")
        else:
            prompt_parts.append("\n## 已知信息\n(暂无相关记忆)")
            logger.info("[ChatApp Prompt] - 无相关记忆")
        
        # 2. 添加对话历史（使用摘要器）
        history_items = [
            item for item in context.items
            if item.source == ContextSource.HISTORY
        ]
        
        if history_items:
            # 使用摘要器获取摘要和最近对话
            try:
                # 获取实际轮数
                session = self.context_engine.session_manager.get_session()
                actual_turns = len(history_items)  # 简化处理
                
                summary, recent_history = await self.summarizer.get_summary_and_recent(
                    history_items,
                    actual_turns
                )
                
                if summary:
                    # 有摘要
                    prompt_parts.append(f"\n## 早期对话摘要\n{summary}")
                    logger.info(
                        f"[ChatApp Prompt] ✓ 添加对话摘要 "
                        f"(已摘要 {actual_turns - len(recent_history)} 轮)"
                    )
                    
                    # 添加最近对话
                    if recent_history:
                        history_text = "\n".join(item.content for item in recent_history)
                        prompt_parts.append(f"\n## 最近对话\n{history_text}")
                        logger.info(f"[ChatApp Prompt] ✓ 添加最近对话 ({len(recent_history)} 轮)")
                else:
                    # 无摘要，使用最近 N 轮
                    max_turns = min(self.history_turns, 10)
                    recent = history_items[-max_turns:]
                    history_text = "\n".join(item.content for item in recent)
                    prompt_parts.append(f"\n## 对话历史\n{history_text}")
                    logger.info(f"[ChatApp Prompt] ✓ 添加对话历史 ({len(recent)} 轮)")
            except Exception as e:
                logger.warning(f"[ChatApp Prompt] ⚠ 处理历史时出错: {e}")
                # 降级处理
                max_turns = min(self.history_turns, 10)
                recent = history_items[-max_turns:]
                history_text = "\n".join(item.content for item in recent)
                prompt_parts.append(f"\n## 对话历史\n{history_text}")
        else:
            logger.info("[ChatApp Prompt] - 无对话历史")
        
        # 3. 添加当前输入
        prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
        logger.info("[ChatApp Prompt] ✓ 添加当前用户输入")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[ChatApp Prompt] ✓ Prompt 构建完成 (长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    def _get_mock_response(self, prompt: str) -> str:
        """
        生成闲聊场景的模拟回复
        
        Args:
            prompt: Prompt 内容
            
        Returns:
            模拟回复
        """
        return (
            "[模拟回复 - 闲聊模式]\n"
            "很高兴和你聊天！我可以：\n"
            "1. 回答各种问题\n"
            "2. 进行日常对话\n"
            "3. 分享知识和信息\n\n"
            "在实际部署中，这里会调用真实的 LLM API。\n"
            f"(当前 Prompt 长度: {len(prompt)} 字符)"
        )


# 向后兼容：保留旧的导出名称
__all__ = ["ChatApplication"]
