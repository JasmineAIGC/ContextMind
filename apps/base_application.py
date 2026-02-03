"""
BaseApplication - 基于 ADK 的应用基类

为所有 ContextMind 应用提供统一的基础架构，集成 google-adk 的最佳实践。

主要功能:
- 使用 EvolutionAgent (基于 ADK BaseLlm)
- 统一的 process_turn 流程
- 可扩展的 prompt 构建
- 自动知识提取
- 对话摘要管理

Version: v0.4.1
"""

import logging
from typing import Optional, Dict, List
from abc import ABC, abstractmethod

from evolution import EvolutionEngine, EvolutionAgent
from evolution.core.models import Message, MessageRole, ContextResult, ContextSource, get_logger
from evolution.pipeline.summarizer import ConversationSummarizer, SummarizationConfig

# 禁用HTTP/网络层的debug日志，减少噪音
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai._base_client").setLevel(logging.INFO)

logger = get_logger(__name__)


class BaseApplication(ABC):
    """
    ContextMind 应用基类
    
    基于 google-adk 设计模式，提供统一的应用架构。
    子类只需实现特定领域的 prompt 构建逻辑。
    
    特性:
    - 使用 EvolutionAgent (ADK BaseLlm)
    - 统一的上下文优化流程
    - 自动知识提取
    - 对话摘要管理
    """
    
    def __init__(
        self,
        context_engine: EvolutionEngine,
        system_prompt: str,
        history_turns: int = 10,
        use_real_llm: bool = True,
        extraction_method: Optional[str] = None,
        summarization_config: Optional[SummarizationConfig] = None,
        **config
    ):
        """
        初始化应用基类
        
        Args:
            context_engine: Evolution 上下文引擎
            system_prompt: 系统提示词
            history_turns: Prompt 中包含的历史轮数
            use_real_llm: 是否使用真实 LLM
            extraction_method: 知识提取方式 ('rule' 或 'llm')
            summarization_config: 摘要配置
            **config: 其他配置参数
        """
        self.context_engine = context_engine
        self.system_prompt = system_prompt
        self.history_turns = history_turns
        self.config = config
        self.use_real_llm = use_real_llm
        
        # 知识提取方式
        if extraction_method:
            self.extraction_method = extraction_method
        else:
            self.extraction_method = getattr(context_engine, 'extraction_method', 'rule')
        
        # 初始化 LLM 客户端 (使用 ADK EvolutionAgent)
        if use_real_llm:
            try:
                # 从 context_engine 获取 LLM 客户端
                # 这应该是 EvolutionAgent 实例（基于 ADK BaseLlm）
                self.llm_client = context_engine.llm_client
                if self.llm_client:
                    # 验证是否为 EvolutionAgent
                    if isinstance(self.llm_client, EvolutionAgent):
                        logger.info(
                            f"[{self.__class__.__name__}] ✓ 使用 ADK EvolutionAgent "
                            f"(知识提取: {self.extraction_method})"
                        )
                    else:
                        logger.info(
                            f"[{self.__class__.__name__}] ✓ 使用 LLM 客户端 "
                            f"(类型: {type(self.llm_client).__name__}, "
                            f"知识提取: {self.extraction_method})"
                        )
                else:
                    logger.warning(f"[{self.__class__.__name__}] ⚠ LLM 客户端为 None")
                    logger.warning(f"[{self.__class__.__name__}] 将使用模拟回复")
                    self.use_real_llm = False
                    self.llm_client = None
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] ⚠ LLM 客户端初始化失败: {e}")
                logger.warning(f"[{self.__class__.__name__}] 将使用模拟回复")
                self.use_real_llm = False
                self.llm_client = None
        else:
            self.llm_client = None
            logger.info(
                f"[{self.__class__.__name__}] ✓ 初始化完成 "
                f"(模拟回复, 知识提取: {self.extraction_method})"
            )
        
        # 初始化对话摘要器
        if summarization_config is None:
            summarization_config = SummarizationConfig(
                summarize_threshold=10,
                keep_recent_turns=5,
                method="rule"
            )
        self.summarizer = ConversationSummarizer(
            config=summarization_config,
            llm_client=self.llm_client if use_real_llm else None
        )
    
    async def process_turn(self, user_input: str, debug: bool = False) -> str:
        """
        处理一轮对话（统一流程）
        
        流程:
        1. 上下文优化（检索历史和记忆）
        2. 构建 Prompt（调用子类实现）
        3. 生成回复（使用 ADK Agent）
        4. 更新上下文
        5. 提取知识（可选）
        
        Args:
            user_input: 用户输入
            debug: 是否输出调试信息
            
        Returns:
            助手回复
        """
        logger.info(f"[{self.__class__.__name__}] >>> 用户: {user_input}")
        
        # Step 1: 上下文优化
        logger.debug(f"[{self.__class__.__name__}] [1/5] 开始上下文优化...")
        context = await self.context_engine.optimize(user_input)
        
        if debug:
            self._log_context_debug(context)
        
        # Step 2: 构建 Prompt（调用子类实现）
        logger.debug(f"[{self.__class__.__name__}] [2/5] 构建 Prompt...")
        prompt = await self.build_prompt(user_input, context)
        
        if debug:
            logger.debug(f"[{self.__class__.__name__}] 📝 最终 Prompt:\n{prompt[:500]}...")
        
        # Step 3: 生成回复（使用 ADK Agent）
        logger.debug(f"[{self.__class__.__name__}] [3/5] 调用 LLM 生成回复...")
        response = await self._generate_response(prompt)
        
        logger.info(f"[{self.__class__.__name__}] <<< 助手: {response[:100]}...")
        
        # Step 4: 更新上下文
        logger.debug(f"[{self.__class__.__name__}] [4/5] 更新上下文...")
        await self.context_engine.update(user_input, response)
        
        # Step 5: 提取知识（可选）
        if self.extraction_method in ['rule', 'llm']:
            logger.debug(
                f"[{self.__class__.__name__}] [5/5] "
                f"提取知识 (方法: {self.extraction_method})..."
            )
            try:
                await self.context_engine.extract_knowledge(
                    method=self.extraction_method,
                    auto_store=True
                )
            except Exception as e:
                logger.warning(f"[{self.__class__.__name__}] ⚠ 知识提取失败: {e}")
        
        logger.debug(f"[{self.__class__.__name__}] ✓ 对话轮次处理完成")
        return response
    
    async def _generate_response(self, prompt: str) -> str:
        """
        生成回复（使用 ADK Agent 或模拟）
        
        Args:
            prompt: 完整的 prompt
            
        Returns:
            LLM 回复
        """
        if self.use_real_llm and self.llm_client:
            try:
                # 使用 EvolutionAgent 的 generate_async 方法
                # 返回 (reasoning, response) 元组
                reasoning, response = await self.llm_client.generate_async(prompt)
                return response
            except Exception as e:
                logger.error(f"[{self.__class__.__name__}] ✗ LLM 调用失败: {e}")
                return f"[错误] LLM 调用失败: {e}"
        else:
            # 模拟回复
            return self._get_mock_response(prompt)
    
    def _get_mock_response(self, prompt: str) -> str:
        """
        生成模拟回复（子类可覆盖）
        
        Args:
            prompt: Prompt 内容
            
        Returns:
            模拟回复
        """
        return (
            f"[模拟回复] 这是 {self.__class__.__name__} 的模拟响应。\n"
            f"收到输入长度: {len(prompt)} 字符。\n"
            f"在实际部署中，这里会调用 LLM API。"
        )
    
    @abstractmethod
    async def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """
        构建 Prompt（子类必须实现）
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的 Prompt 字符串
        """
        raise NotImplementedError("子类必须实现 build_prompt 方法")
    
    def _log_context_debug(self, context: ContextResult):
        """输出上下文调试信息"""
        logger.debug(f"[{self.__class__.__name__}] 📊 上下文统计:")
        logger.debug(f"  - 总项数: {len(context.items)}")
        
        # 按来源统计
        by_source = {}
        for item in context.items:
            source = item.source.value if hasattr(item.source, 'value') else str(item.source)
            by_source[source] = by_source.get(source, 0) + 1
        
        for source, count in by_source.items():
            logger.debug(f"  - {source}: {count} 项")
    
    async def get_conversation_summary(self) -> Optional[str]:
        """
        获取对话摘要
        
        Returns:
            对话摘要文本，如果没有则返回 None
        """
        try:
            history = await self.context_engine.session_manager.get_recent_history(
                turns=100  # 获取所有历史
            )
            if not history:
                return None
            
            # 使用摘要器生成摘要
            summary = await self.summarizer.summarize(history)
            return summary
        except Exception as e:
            logger.warning(f"[{self.__class__.__name__}] ⚠ 获取摘要失败: {e}")
            return None


class PromptBuilder:
    """
    通用 Prompt 构建工具类
    
    提供常用的 prompt 构建辅助方法，减少应用层代码重复。
    """
    
    @staticmethod
    def format_history(
        context: ContextResult,
        max_turns: int = 10,
        include_summary: bool = True
    ) -> str:
        """
        格式化对话历史
        
        Args:
            context: 上下文结果
            max_turns: 最大轮数
            include_summary: 是否包含摘要
            
        Returns:
            格式化的历史文本
        """
        history_items = [
            item for item in context.items
            if item.source == ContextSource.HISTORY
        ]
        
        if not history_items:
            return ""
        
        # 限制轮数
        history_items = history_items[-max_turns:]
        
        formatted = []
        if include_summary and hasattr(context, 'summary') and context.summary:
            formatted.append(f"[历史摘要]\n{context.summary}\n")
        
        formatted.append("[最近对话]")
        for item in history_items:
            role = "用户" if "用户" in item.content else "助手"
            formatted.append(f"{role}: {item.content}")
        
        return "\n".join(formatted)
    
    @staticmethod
    def format_memory(
        context: ContextResult,
        relevance_threshold: float = 0.3
    ) -> str:
        """
        格式化长期记忆
        
        Args:
            context: 上下文结果
            relevance_threshold: 相关度阈值
            
        Returns:
            格式化的记忆文本
        """
        memory_items = [
            item for item in context.items
            if item.source == ContextSource.MEMORY
            and item.relevance >= relevance_threshold
        ]
        
        if not memory_items:
            return ""
        
        formatted = ["[相关记忆]"]
        for item in memory_items:
            formatted.append(f"- {item.content} (相关度: {item.relevance:.2f})")
        
        return "\n".join(formatted)
    
    @staticmethod
    def format_knowledge(context: ContextResult) -> str:
        """
        格式化知识库内容
        
        Args:
            context: 上下文结果
            
        Returns:
            格式化的知识文本
        """
        knowledge_items = [
            item for item in context.items
            if item.source == ContextSource.KNOWLEDGE
        ]
        
        if not knowledge_items:
            return ""
        
        formatted = ["[知识库]"]
        for item in knowledge_items:
            formatted.append(f"- {item.content}")
        
        return "\n".join(formatted)


# 便捷导出
__all__ = ["BaseApplication", "PromptBuilder"]
