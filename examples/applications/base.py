"""
BaseApplication - 应用层基类

定义基于ContextEngine构建应用的标准模式。
应用层负责业务逻辑、Prompt构建和回复处理。
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

from contextmind import ContextEngine, Client, ContextResult
from contextmind.utils import (
    get_logger,
    format_context_result,
    format_memory_cache,
    format_prompt_analysis,
    format_complete_prompt,
)

logger = get_logger(__name__)


class BaseApplication(ABC):
    """应用层基类"""
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        system_prompt: str = "",
        **config
    ):
        """初始化应用"""
        self.context_engine = context_engine
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.config = config
        
        logger.info(f"Application initialized: {self.__class__.__name__}")
    
    async def process_turn(self, user_input: str) -> str:
        """处理一轮对话"""
        logger.debug(f"[处理中] 用户输入: {user_input}")
        
        # 优化上下文
        context_result = await self.context_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        
        # 调试模式
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(format_context_result(context_result))
            
            memory_cache = self.context_engine.memory_bank.get_memory_cache() if hasattr(self.context_engine, 'memory_bank') else []
            logger.debug(format_memory_cache(memory_cache))
        
        # 构建 Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # 调试模式
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(format_prompt_analysis(prompt, context_result))
            logger.debug(format_complete_prompt(prompt))
        
        # 调用 LLM
        _, response = self.llm_client.generate(prompt)
        
        # 后处理
        response = self.post_process_response(response)
        
        # 更新上下文
        await self.context_engine.update(
            user_input=user_input,
            assistant_response=response
        )
        
        # 提取知识
        if self.config.get('auto_extract_knowledge', False):
            await self.context_engine.extract_knowledge(auto_store=True)
        
        logger.debug(f"[完成] 助手回复: {response}")
        
        return response
    
    @abstractmethod
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """构建 Prompt - 子类实现"""
        pass
    
    def post_process_response(self, response: str) -> str:
        """后处理回复"""
        return response.strip()
