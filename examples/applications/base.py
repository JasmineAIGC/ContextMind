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
            logger.debug("\n" + "╔" + "=" * 98 + "╗")
            logger.debug("║" + "【上下文优化结果】Context Optimization Result".center(98) + "║")
            logger.debug("║" + "说明：这是 ContextMind 从历史对话、长期记忆等源收集并优化后的上下文信息".center(98) + "║")
            logger.debug("╚" + "=" * 98 + "╝")
            
            # 显示优化后的上下文统计
            logger.debug(f"\n【统计信息】")
            logger.debug(f"  - 近期对话: {len(context_result.recent_history)} 条消息")
            logger.debug(f"  - 长期记忆: {len(context_result.long_term_memory)} 项")
            logger.debug(f"  - 外部知识: {len(context_result.external_knowledge)} 项")
            
            # 显示优化后的对话历史详情（如果有）
            if context_result.recent_history:
                logger.debug(f"\n【优化后的对话历史】（共 {len(context_result.recent_history)} 轮对话将被用于构建Prompt）")
                logger.debug(f"  📝 上下文来源: SessionService（会话历史存储）")
                logger.debug(f"  📊 提炼策略: 智能提取关键信息 + 保留完整对话")
                logger.debug(f"  🎯 优化结果: 这些对话将在build_prompt()中被添加到'## 近期对话'部分")
                logger.debug(f"\n  最近 {min(10, len(context_result.recent_history))} 轮内容预览：")
                # 从后往前显示最近的10轮
                recent_msgs = list(reversed(context_result.recent_history[-10:]))
                for i, msg in enumerate(recent_msgs, 1):
                    preview = msg.content[:100] + ('...' if len(msg.content) > 100 else '')
                    logger.debug(f"  {i}. {msg.role.value}: {preview}")
                
                # 显示智能提炼的关键信息
                logger.debug(f"\n  【从对话中智能提炼的关键信息】")
                logger.debug(f"  💡 说明: 以下信息通过NLP技术从对话历史中自动提取")
                # Note: extracted_info is in ProcessedContext metadata, need to access through context_engine
                logger.debug(f"  ✨ 提炼内容: 主题、实体、偏好、状态等（可在context.metadata查看）")
            else:
                logger.debug(f"\n【优化后的对话历史】（无历史对话）")
                logger.debug(f"  💡 说明: 这是对话的第一轮，暂无历史记录")
            
            # 显示长期记忆详情（如果有）
            if context_result.long_term_memory:
                logger.debug(f"\n【优化后的长期记忆】（共 {len(context_result.long_term_memory)} 项记忆将被用于构建Prompt）")
                logger.debug(f"  📝 上下文来源: MemoryService（长期记忆存储）")
                logger.debug(f"  📊 提炼策略: 基于语义相似度检索，按相关性排序")
                logger.debug(f"  🎯 优化结果: 这些记忆将在build_prompt()中被添加到'## 用户历史信息'部分")
                logger.debug(f"\n  前 {min(5, len(context_result.long_term_memory))} 项内容（按相关性排序）：")
                for i, item in enumerate(context_result.long_term_memory[:5], 1):
                    preview = item.content[:100] + ('...' if len(item.content) > 100 else '')
                    logger.debug(f"  {i}. {preview} (相关性: {item.score:.2f})")
            else:
                logger.debug(f"\n【优化后的长期记忆】（无相关记忆）")
                logger.debug(f"  💡 说明: 当前查询未匹配到相关的长期记忆")
            
            # 显示外部知识详情（如果有）
            if context_result.external_knowledge:
                logger.debug(f"\n【优化后的外部知识】（共 {len(context_result.external_knowledge)} 项知识将被用于构建Prompt）")
                logger.debug(f"  📝 上下文来源: 外部知识库（如向量数据库、知识图谱等）")
                logger.debug(f"  📊 提炼策略: 基于查询相关性检索")
                logger.debug(f"  🎯 优化结果: 这些知识将在build_prompt()中被添加到相应部分")
                logger.debug(f"\n  前 {min(5, len(context_result.external_knowledge))} 项内容：")
                for i, item in enumerate(context_result.external_knowledge[:5], 1):
                    preview = item.content[:100] + ('...' if len(item.content) > 100 else '')
                    logger.debug(f"  {i}. {preview}")
            else:
                logger.debug(f"\n【优化后的外部知识】（无外部知识）")
                logger.debug(f"  💡 说明: 当前未配置外部知识库或未检索到相关知识")
            
            logger.debug("")
        
        # 2. 构建Prompt
        prompt = self.build_prompt(user_input, context_result)
        
        # Debug模式：打印完整Prompt及其构成分析
        if logger.isEnabledFor(logging.DEBUG):
            # 先打印Prompt构成分析
            logger.debug("\n" + "╔" + "=" * 98 + "╗")
            logger.debug("║" + "【Prompt构成分析】Prompt Composition Analysis".center(98) + "║")
            logger.debug("║" + "说明：这是对即将发送的Prompt的统计分析，帮助了解各部分内容的占比".center(98) + "║")
            logger.debug("╚" + "=" * 98 + "╝")
            logger.debug(f"\n  - 总字符数: {len(prompt)}")
            logger.debug(f"  - 包含对话历史: {'是' if context_result.recent_history else '否'}" + 
                        (f" ({len(context_result.recent_history)} 轮)" if context_result.recent_history else ""))
            logger.debug(f"  - 包含长期记忆: {'是' if context_result.long_term_memory else '否'}" +
                        (f" ({len(context_result.long_term_memory)} 项)" if context_result.long_term_memory else ""))
            logger.debug(f"  - 包含业务信息: {'是' if '## 业务信息' in prompt else '否'}")
            logger.debug("")
            
            # 再打印完整Prompt
            logger.debug("\n" + "╔" + "=" * 98 + "╗")
            logger.debug("║" + "【完整Prompt】Complete Prompt Sent to LLM".center(98) + "║")
            logger.debug("║" + "说明：这是发送给大语言模型的完整提示词，包含系统指令、上下文和当前用户输入".center(98) + "║")
            logger.debug("╚" + "=" * 98 + "╝")
            logger.debug("\n" + prompt)
            logger.debug("")
        
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
