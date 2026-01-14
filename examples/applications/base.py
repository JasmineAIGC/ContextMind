"""
BaseApplication - 应用层基类

定义了基于ContextEngine构建应用的标准模式。
应用层负责：
1. 业务逻辑（如何使用上下文）
2. Prompt构建（如何将上下文转换为模型输入）
3. 回复处理（如何处理模型输出）
"""

from abc import ABC, abstractmethod
from typing import Optional

from contextmind import ContextEngine, Client, ContextResult
from contextmind.logger import get_logger

logger = get_logger(__name__)


class BaseApplication(ABC):
    """
    应用层基类
    
    封装了使用ContextEngine构建应用的标准模式：
    1. 优化上下文
    2. 构建Prompt
    3. 调用LLM
    4. 后处理回复
    5. 更新上下文
    
    子类只需实现 build_prompt 方法即可。
    """
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        system_prompt: str = "",
        **config
    ):
        """
        初始化应用
        
        Args:
            context_engine: 上下文引擎实例
            llm_client: LLM客户端实例
            system_prompt: 系统提示词（定义角色和任务）
            **config: 其他配置参数
        """
        self.context_engine = context_engine
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.config = config
        
        logger.info(f"Application initialized: {self.__class__.__name__}")
    
    async def process_turn(self, user_input: str) -> str:
        """
        处理一轮对话
        
        完整的对话处理流程：
        1. 优化上下文
        2. 构建Prompt
        3. 调用LLM
        4. 后处理回复
        5. 更新上下文
        
        Args:
            user_input: 用户输入
            
        Returns:
            助手回复
        """
        logger.debug(f"Processing turn for input: {user_input[:50]}...")
        
        # 1. 优化上下文
        context_result = await self.context_engine.optimize(
            user_input=user_input,
            include_session=True,
            include_memory=True,
        )
        
        # 2. 构建Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # 3. 调用LLM
        _, response = self.llm_client.generate(prompt)
        
        # 4. 后处理回复
        response = self.post_process_response(response)
        
        # 5. 更新上下文
        await self.context_engine.update(
            user_input=user_input,
            assistant_response=response
        )
        
        # 6. 提取知识（可选）
        if self.config.get('auto_extract_knowledge', False):
            await self.context_engine.extract_knowledge(auto_store=True)
        
        logger.debug(f"Turn processed, response: {response[:50]}...")
        
        return response
    
    @abstractmethod
    def build_prompt(self, user_input: str, context: ContextResult) -> str:
        """
        构建Prompt - 由子类实现
        
        定义如何将用户输入和上下文转换为模型输入。
        
        Args:
            user_input: 用户输入
            context: 优化后的上下文
            
        Returns:
            完整的Prompt字符串
        """
        pass
    
    def post_process_response(self, response: str) -> str:
        """
        后处理回复
        
        可以在子类中重写以实现自定义的回复处理逻辑。
        
        Args:
            response: 模型原始输出
            
        Returns:
            处理后的回复
        """
        # 默认实现：去除首尾空白
        return response.strip()
