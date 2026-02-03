"""
InsuranceApplication - 保险应用（基于 ADK 重构版）

展示如何使用 BaseApplication 和 ADK 模式构建保险咨询应用。
专注于保险领域的专业对话和知识管理。

Version: v0.4.2 - 重构为使用 BaseApplication 和 ADK 模式
"""

from apps.base_application import BaseApplication, PromptBuilder
from evolution import EvolutionEngine
from evolution.core.models import ContextResult, ContextSource, get_logger
from evolution.pipeline.summarizer import SummarizationConfig

# 导入统一的系统提示词
from prompts import INSURANCE_SYSTEM_PROMPT

logger = get_logger(__name__)


class InsuranceApplication(BaseApplication):
    """
    保险应用示例（重构版）
    
    继承 BaseApplication，专注于保险场景的 prompt 构建。
    """
    
    def __init__(
        self,
        context_engine: EvolutionEngine,
        insurance_products: str = "",
        history_turns: int = 10,
        system_prompt: str = INSURANCE_SYSTEM_PROMPT,
        llm_config = None,  # 保持向后兼容
        use_real_llm: bool = True,
        extraction_method: str = None,
        **config
    ):
        """
        初始化保险应用
        
        Args:
            context_engine: Evolution 引擎实例
            insurance_products: 保险产品信息
            history_turns: 历史轮数
            system_prompt: 系统提示
            llm_config: LLM 配置（保留用于兼容）
            use_real_llm: 是否使用真实 LLM
            extraction_method: 知识提取方式
        """
        self.insurance_products = insurance_products
        
        # 保险场景使用规则摘要，保留较多历史
        summarization_config = SummarizationConfig(
            summarize_threshold=12,  # 超过12轮触发摘要
            keep_recent_turns=5,     # 保留最近5轮
            method="rule"            # 使用规则摘要
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
        构建保险场景的 Prompt
        
        包含：系统提示词、产品信息、相关记忆、对话历史、当前输入
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的 Prompt
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[InsuranceApp Prompt] 开始构建 Prompt")
        logger.info("=" * 100)
        
        prompt_parts = [self.system_prompt]
        
        # 1. 添加保险产品信息（如果有）
        if self.insurance_products:
            prompt_parts.append(f"\n## 保险产品信息\n{self.insurance_products}")
            logger.info("[InsuranceApp Prompt] ✓ 添加保险产品信息")
        
        # 2. 添加相关记忆和知识
        memory_text = PromptBuilder.format_memory(
            context,
            relevance_threshold=0.3
        )
        knowledge_text = PromptBuilder.format_knowledge(context)
        
        if memory_text or knowledge_text:
            info_parts = []
            if memory_text:
                info_parts.append(memory_text)
            if knowledge_text:
                info_parts.append(knowledge_text)
            prompt_parts.append(f"\n## 已知信息\n{chr(10).join(info_parts)}")
            logger.info("[InsuranceApp Prompt] ✓ 添加相关信息")
        else:
            prompt_parts.append("\n## 已知信息\n(暂无相关信息)")
            logger.info("[InsuranceApp Prompt] - 无相关信息")
        
        # 3. 添加对话历史
        history_items = [
            item for item in context.items
            if item.source == ContextSource.HISTORY
        ]
        
        if history_items:
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
                        f"[InsuranceApp Prompt] ✓ 添加对话摘要 "
                        f"(已摘要 {actual_turns - len(recent_history)} 轮)"
                    )
                    
                    if recent_history:
                        history_text = "\n".join(item.content for item in recent_history)
                        prompt_parts.append(f"\n## 最近对话\n{history_text}")
                        logger.info(f"[InsuranceApp Prompt] ✓ 添加最近对话 ({len(recent_history)} 轮)")
                else:
                    # 无摘要
                    max_turns = min(self.history_turns, 12)
                    recent = history_items[-max_turns:]
                    history_text = "\n".join(item.content for item in recent)
                    prompt_parts.append(f"\n## 对话历史\n{history_text}")
                    logger.info(f"[InsuranceApp Prompt] ✓ 添加对话历史 ({len(recent)} 轮)")
            except Exception as e:
                logger.warning(f"[InsuranceApp Prompt] ⚠ 处理历史时出错: {e}")
                max_turns = min(self.history_turns, 12)
                recent = history_items[-max_turns:]
                history_text = "\n".join(item.content for item in recent)
                prompt_parts.append(f"\n## 对话历史\n{history_text}")
        else:
            logger.info("[InsuranceApp Prompt] - 无对话历史")
        
        # 4. 添加当前输入
        prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
        logger.info("[InsuranceApp Prompt] ✓ 添加当前用户输入")
        
        final_prompt = "\n".join(prompt_parts)
        
        logger.info("-" * 100)
        logger.info(f"[InsuranceApp Prompt] ✓ Prompt 构建完成 (长度: {len(final_prompt)} 字符)")
        logger.info("-" * 100)
        logger.info("")
        
        return final_prompt
    
    def _get_mock_response(self, prompt: str) -> str:
        """生成保险场景的模拟回复"""
        return (
            "[模拟回复 - 保险模式]\n"
            "您好！我是保险咨询专家，很高兴为您服务。\n"
            "我可以帮您：\n"
            "1. 了解各类保险产品\n"
            "2. 分析保障需求\n"
            "3. 比较产品优劣\n"
            "4. 解答投保疑问\n\n"
            "请告诉我您对哪方面的保险感兴趣？\n"
            f"(当前 Prompt 长度: {len(prompt)} 字符)"
        )


__all__ = ["InsuranceApplication"]
