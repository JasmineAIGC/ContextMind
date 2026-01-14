"""
Base Application Class

定义应用层的标准对话处理流程。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from contextmind.engine import ContextEngine
from contextmind.client import Client
from contextmind.data_models import ContextResult


class BaseApplication(ABC):
    """应用层基类 - 定义标准的对话处理流程
    
    该基类封装了使用 ContextMind 进行对话处理的标准流程：
    1. 使用 ContextMind 优化上下文
    2. 应用层构建 Prompt
    3. 调用 LLM 生成回复
    4. 后处理响应
    5. 更新上下文
    
    子类需要实现 build_prompt() 方法来定义具体的业务逻辑。
    
    Attributes:
        context_engine: ContextMind 引擎实例
        llm_client: LLM 客户端实例
        system_prompt: 系统提示词
        config: 额外配置参数
    """
    
    def __init__(
        self,
        context_engine: ContextEngine,
        llm_client: Client,
        system_prompt: str = "",
        **config
    ):
        """初始化应用
        
        Args:
            context_engine: ContextMind 引擎实例，负责上下文优化
            llm_client: LLM 客户端实例，负责生成回复
            system_prompt: 系统提示词，定义 AI 的角色和行为
            **config: 额外配置参数
        """
        self.context_engine = context_engine
        self.llm_client = llm_client
        self.system_prompt = system_prompt
        self.config = config
    
    async def process_turn(self, user_input: str) -> str:
        """处理一轮对话 - 标准流程
        
        这是应用层处理对话的主要入口方法，封装了完整的对话处理流程。
        
        Args:
            user_input: 用户输入
            
        Returns:
            str: AI 的回复
        """
        # 1. 使用 ContextMind 优化上下文
        context_result = await self.context_engine.optimize(user_input)
        
        # 2. 应用层构建 Prompt（由子类实现具体业务逻辑）
        prompt = self.build_prompt(
            user_input=user_input,
            context=context_result
        )
        
        # 3. 调用 LLM 生成回复
        _, response = self.llm_client.generate(prompt)
        
        # 4. 后处理响应
        response = self.post_process_response(response)
        
        # 5. 更新上下文
        await self.context_engine.update(user_input, response)
        
        return response
    
    @abstractmethod
    def build_prompt(
        self,
        user_input: str,
        context: ContextResult
    ) -> str:
        """构建最终 Prompt - 由子类实现具体业务逻辑
        
        这是应用层的核心方法，负责将用户输入和优化后的上下文组织成
        适合 LLM 处理的 Prompt。不同的应用可以有不同的 Prompt 组织方式。
        
        Args:
            user_input: 用户输入
            context: ContextMind 优化后的上下文信息
            
        Returns:
            str: 构建好的 Prompt
        """
        pass
    
    def post_process_response(self, response: str) -> str:
        """后处理响应 - 可由子类覆盖
        
        对 LLM 的原始输出进行后处理，如去除格式标记、提取实际回复等。
        默认实现只做简单的空白字符清理。
        
        Args:
            response: LLM 的原始输出
            
        Returns:
            str: 处理后的回复
        """
        return response.strip()
