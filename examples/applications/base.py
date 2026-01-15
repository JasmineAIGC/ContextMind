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
import logging

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
        
        # Debug模式：打印详细的上下文优化结果
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("\n" + "=" * 100)
            logger.debug("CONTEXT OPTIMIZATION RESULT".center(100))
            logger.debug("=" * 100)
            
            # 显示优化后的上下文统计
            logger.debug(f"\n【统计信息】")
            logger.debug(f"  - 近期对话: {len(context_result.recent_history)} 条消息")
            logger.debug(f"  - 长期记忆: {len(context_result.long_term_memory)} 项")
            logger.debug(f"  - 外部知识: {len(context_result.external_knowledge)} 项")
            
            # 显示优化后的对话历史详情（如果有）
            if context_result.recent_history:
                logger.debug(f"\n【近期对话内容】（共 {len(context_result.recent_history)} 轮）")
                for i, msg in enumerate(context_result.recent_history[-10:], 1):  # 显示最近10轮
                    logger.debug(f"  {i}. {msg.role.value}: {msg.content[:80]}{'...' if len(msg.content) > 80 else ''}")
            
            # 显示长期记忆详情（如果有）
            if context_result.long_term_memory:
                logger.debug(f"\n【长期记忆内容】")
                for i, item in enumerate(context_result.long_term_memory[:5], 1):  # 显示前5项
                    logger.debug(f"  {i}. {item.content[:80]}{'...' if len(item.content) > 80 else ''} (相关性: {item.score:.2f})")
            
            # 显示外部知识详情（如果有）
            if context_result.external_knowledge:
                logger.debug(f"\n【外部知识内容】")
                for i, item in enumerate(context_result.external_knowledge[:5], 1):  # 显示前5项
                    logger.debug(f"  {i}. {item.content[:80]}{'...' if len(item.content) > 80 else ''}")
            
            logger.debug("=" * 100)
        
        # 2. 构建Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # Debug模式：打印完整Prompt及其构成分析
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("\n" + "=" * 100)
            logger.debug("COMPLETE PROMPT SENT TO LLM".center(100))
            logger.debug("=" * 100)
            logger.debug(prompt)
            logger.debug("=" * 100)
            
            # 分析Prompt的构成
            logger.debug(f"\n【Prompt构成分析】")
            logger.debug(f"  - 总字符数: {len(prompt)}")
            logger.debug(f"  - 包含对话历史: {'是' if '## 近期对话' in prompt or 'recent_history' in prompt.lower() else '否'}")
            logger.debug(f"  - 包含长期记忆: {'是' if '## 用户历史信息' in prompt or 'long_term_memory' in prompt.lower() else '否'}")
            logger.debug(f"  - 包含业务信息: {'是' if '## 业务信息' in prompt or 'business_info' in prompt.lower() else '否'}")
            logger.debug("=" * 100 + "\n")
        
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
