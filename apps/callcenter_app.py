"""
CallCenterApplication - 客服应用（基于 ADK 重构版）

展示如何使用 BaseApplication 和 ADK 模式构建客服应用。
重点展示上下文工程能力：利用历史、记忆和知识提供连贯回复。

Version: v0.4.2 - 重构为使用 BaseApplication 和 ADK 模式
"""

from apps.base_application import BaseApplication, PromptBuilder
from evolution import EvolutionEngine
from evolution.core.models import ContextResult, ContextSource, get_logger
from evolution.pipeline.summarizer import SummarizationConfig

# 导入统一的系统提示词
from prompts import CALLCENTER_SYSTEM_PROMPT

logger = get_logger(__name__)


class CallCenterApplication(BaseApplication):
    """
    客服应用示例（重构版）
    
    继承 BaseApplication，专注于客服场景的 prompt 构建。
    """
    
    def __init__(
        self,
        context_engine: EvolutionEngine,
        business_info: str = "",
        history_turns: int = 10,
        system_prompt: str = CALLCENTER_SYSTEM_PROMPT,
        llm_config = None,  # 保持向后兼容
        use_real_llm: bool = True,
        extraction_method: str = None,
        **config
    ):
        """
        初始化客服应用
        
        Args:
            context_engine: Evolution 引擎实例
            business_info: 业务信息
            history_turns: 历史轮数
            system_prompt: 系统提示
            llm_config: LLM 配置（保留用于兼容）
            use_real_llm: 是否使用真实 LLM
            extraction_method: 知识提取方式
        """
        self.business_info = business_info
        
        # 客服场景使用规则摘要以提高速度
        summarization_config = SummarizationConfig(
            summarize_threshold=15,  # 超过15轮触发摘要
            keep_recent_turns=5,     # 保留最近5轮
            method="rule"            # 使用规则摘要（快速）
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
        构建客服场景的 Prompt
        
        包含：系统提示词、业务信息、相关记忆、对话历史、当前输入
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的 Prompt
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[CallCenterApp Prompt] 开始构建 Prompt")
        logger.info("=" * 100)
        
        prompt_parts = [self.system_prompt]
        
        # 1. 添加业务信息（如果有）
        if self.business_info:
            prompt_parts.append(f"\n## 业务信息\n{self.business_info}")
            logger.info("[CallCenterApp Prompt] ✓ 添加业务信息")
        
        # 2. 添加相关记忆
        memory_text = PromptBuilder.format_memory(
            context,
            relevance_threshold=0.3
        )
        
        if memory_text:
            prompt_parts.append(f"\n## 已知信息\n{memory_text}")
            logger.info("[CallCenterApp Prompt] ✓ 添加相关记忆")
        else:
            prompt_parts.append("\n## 已知信息\n(暂无相关记忆)")
            logger.info("[CallCenterApp Prompt] - 无相关记忆")
        
        # 3. 添加对话历史
        history_items = [
            item for item in context.items
            if item.source == ContextSource.HISTORY
        ]
        
        if history_items:
            # 客服场景保留更多历史，使用摘要
            try:
                actual_turns = len(history_items)
                summary, recent_history = await self.summarizer.get_summary_and_recent(
                    history_items,
                    actual_turns
                )
                
                if summary:
                    # 有摘要
                    prompt_parts.append(f"\n## 早期对话摘要\n{summary}")
                    logger.info(
                        f"[CallCenterApp Prompt] ✓ 添加对话摘要 "
                        f"(已摘要 {actual_turns - len(recent_history)} 轮)"
                    )
                    
                    if recent_history:
                        history_text = "\n".join(item.content for item in recent_history)
                        prompt_parts.append(f"\n## 最近对话\n{history_text}")
                        logger.info(f"[CallCenterApp Prompt] ✓ 添加最近对话 ({len(recent_history)} 轮)")
                else:
                    # 无摘要
                    max_turns = min(self.history_turns, 15)  # 客服保留更多历史
                    recent = history_items[-max_turns:]
                    history_text = "\n".join(item.content for item in recent)
                    prompt_parts.append(f"\n## 对话历史\n{history_text}")
                    logger.info(f"[CallCenterApp Prompt] ✓ 添加对话历史 ({len(recent)} 轮)")
            except Exception as e:
                logger.warning(f"[CallCenterApp Prompt] ⚠ 处理历史时出错: {e}")
                max_turns = min(self.history_turns, 15)
                recent = history_items[-max_turns:]
                history_text = "\n".join(item.content for item in recent)
                prompt_parts.append(f"\n## 对话历史\n{history_text}")
        else:
            logger.info("[CallCenterApp Prompt] - 无对话历史")
        
        # 4. 添加当前输入
        prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
        logger.info("[CallCenterApp Prompt] ✓ 添加当前用户输入")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[CallCenterApp Prompt] ✓ Prompt 构建完成 (长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    def _get_mock_response(self, prompt: str) -> str:
        """生成客服场景的模拟回复"""
        return (
            "[模拟回复 - 客服模式]\n"
            "您好！我是智能客服助手，很高兴为您服务。\n"
            "我可以帮您：\n"
            "1. 查询订单状态\n"
            "2. 解答产品问题\n"
            "3. 处理售后服务\n"
            "4. 提供技术支持\n\n"
            "请告诉我您需要什么帮助？\n"
            f"(当前 Prompt 长度: {len(prompt)} 字符)"
        )


__all__ = ["CallCenterApplication"]
