"""
ContextMind Configuration API - 简单的框架配置

提供一个简单、统一的 API 来配置整个 ContextMind 框架。
通过合理的默认值和最少的样板代码使集成变得简单。

ContextMind 专注于上下文工程 (步骤 1-4 + 步骤 6):
- 步骤 1-4: 构建高效 Prompt (上下文工程核心) - 在 ContextMind 内部
- 步骤 5: LLM 调用 (含 KV cache) - 外部实现 (用户的 LLM)
- 步骤 6: 输出后处理 - 在 ContextMind 内部

使用示例:
    ```python
    from contextmind import ContextMind
    
    # 设置
    cm = ContextMind()
    
    # 步骤 1-4: ContextMind 构建优化后的 Context
    context = await cm.prepare_context("Hello", session_id="user123")
    
    # 步骤 5: 用户调用外部 LLM (vLLM, OpenAI 等)
    llm_output = await your_llm.generate(
        system_prompt=context['system_prompt'],
        messages=context['optimized_context'],
        user_input=context['user_input']
    )
    
    # 步骤 6: ContextMind 后处理
    final_response = await cm.post_process(
        llm_output,
        session_id="user123"
    )
    ```
"""

from typing import Optional, Dict, Any
from ..engine import ContextEngine
from .registry import registry
from .data_models import Message
from .types import MessageRole
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ContextMind:
    """
    ContextMind 上下文工程框架的统一接口
    
    ContextMind 专注于上下文工程 (步骤 1-4 + 步骤 6):
    - 步骤 1-4: 构建高效 Prompt (InputPreprocessor → Retriever → Compressor → Reorderer)
    - 步骤 5: LLM 调用是外部的 (用户调用自己的 LLM)
    - 步骤 6: 后处理 LLM 输出 (PostProcessor)
    
    这种设计使 ContextMind 保持通用性 - 适用于任何 LLM 提供商。
    
    功能特性:
    - 自动插件选择，合理的默认配置
    - prepare_context() 用于步骤 1-4 (返回优化后的 Context)
    - post_process() 用于步骤 6 (处理 LLM 输出)
    - 内置 Session 管理
    - 简单的插件切换
    
    属性:
        engine: 底层的 ContextEngine 实例
        session_id: 当前 Session ID (如果已设置)
    """
    
    def __init__(
        self,
        llm_client: Any,
        extractor: str = 'rule_based',
        retriever: str = 'semantic',
        updater: str = 'simple',
        enable_memory: bool = True,
        enable_compression: bool = True,
        enable_reordering: bool = True,
        enable_postprocessing: bool = True,
        enable_summarization: bool = False,
        **engine_kwargs
    ):
        """
        使用配置初始化 ContextMind
        
        Args:
            llm_client: 用于生成回复的 LLM 客户端
            extractor: 提取器插件名称 (默认: 'rule_based')
            retriever: 检索器插件名称 (默认: 'semantic')
            updater: 更新器插件名称 (默认: 'simple')
            enable_memory: 启用记忆管理 (默认: True)
            enable_compression: 启用上下文压缩 (默认: True)
            enable_reordering: 启用上下文重排序 (默认: True)
            enable_postprocessing: 启用输出后处理 (默认: True)
            enable_summarization: 启用对话摘要 (默认: False)
            **engine_kwargs: ContextEngine 的额外参数
        """
        logger.info(f"[ContextMind] 正在初始化，extractor={extractor}, retriever={retriever}")
        
        # 创建引擎
        self.engine = ContextEngine(llm_client=llm_client, **engine_kwargs)
        
        # 配置插件
        if enable_memory:
            # 提取器已在 engine 初始化时设置
            # 不需要额外配置
            
            # 为 Memory Bank 设置检索器和更新器
            retriever_plugin = registry.get_retriever(retriever)
            updater_plugin = registry.get_updater(updater)
            if self.engine.memory and retriever_plugin and updater_plugin:
                self.engine.memory.set_retriever(retriever_plugin)
                self.engine.memory.set_updater(updater_plugin)
        
        # 配置 Pipeline 组件
        if not enable_compression and hasattr(self.engine, 'compressor'):
            self.engine.compressor = None
        
        if not enable_reordering and hasattr(self.engine, 'reorderer'):
            self.engine.reorderer = None
        
        if enable_postprocessing:
            from ..pipeline.postprocessor import PostProcessor
            self.engine.postprocessor = PostProcessor()
        
        if enable_summarization:
            from ..pipeline.summarizer import ConversationSummarizer
            self.engine.summarizer = ConversationSummarizer()
        
        self.session_id: Optional[str] = None
        logger.info("[ContextMind] ✓ 初始化完成")
    
    async def prepare_context(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        步骤 1-4: 为 LLM 调用构建优化的 Context
        
        此方法运行上下文工程 Pipeline:
        1. InputPreprocessor - 清理和规范化输入
        2. ContextRetriever + MemoryBank - 检索相关 Context
        3. ContextCompressor - 压缩以适应 Context 窗口
        4. ContextReorderer - 重排序以获得最佳注意力
        
        之后，用户应调用他们的 LLM (步骤 5)，然后对 LLM 输出调用
        post_process() (步骤 6)。
        
        Args:
            user_input: 用户消息
            session_id: 用于对话跟踪的 Session ID
            system_prompt: 可选的系统提示词覆盖
            
        Returns:
            包含以下内容的字典:
                - 'optimized_context': List - 准备好供 LLM 使用的 Context 项
                - 'system_prompt': str - 系统指令
                - 'user_input': str - 处理后的用户输入
                - 'messages': List - 完整的消息历史
                - 'metadata': Dict - 附加元数据
        
        使用示例:
            ```python
            cm = ContextMind()
            # 步骤 1-4: ContextMind 构建优化的 Context
            context = await cm.prepare_context("Hello", session_id="user123")
            
            # 步骤 5: 用户调用外部 LLM
            llm_output = await your_llm.generate(
                system_prompt=context['system_prompt'],
                messages=context['optimized_context'],
                user_input=context['user_input']
            )
            
            # 步骤 6: ContextMind 后处理
            final = cm.post_process(llm_output, session_id="user123")
            ```
        """
        # 使用提供的 session_id 或存储的
        sid = session_id or self.session_id
        if sid:
            self.session_id = sid
        
        # 创建用户消息
        user_msg = Message(role=MessageRole.USER, content=user_input)
        
        # 获取对话历史
        messages = []
        if sid and self.engine.session:
            messages = await self.engine.session.get_messages(sid)
        
        # 添加当前消息
        messages.append(user_msg)
        
        # 步骤 1-4: 优化 Context (核心上下文工程)
        optimized = await self.engine.optimize_context(
            messages=messages,
            query=user_input,
            session_id=sid,
            system_prompt=system_prompt,
        )
        
        logger.info(
            f"[ContextMind] ✓ Context 已优化: {len(optimized.context)} 项准备供 LLM 使用"
        )
        
        # 返回结构化的 Context 用于外部 LLM 调用
        return {
            'optimized_context': optimized.context,
            'system_prompt': system_prompt or "",
            'user_input': user_input,
            'messages': messages,
            'metadata': {
                'session_id': sid,
                'context_items': len(optimized.context),
                'compression_applied': hasattr(optimized, 'compression_ratio'),
            }
        }
    
    async def post_process(
        self,
        llm_output: str,
        session_id: Optional[str] = None,
        extract_knowledge: bool = True,
    ) -> str:
        """
        步骤 6: 后处理 LLM 输出并更新记忆
        
        应用 PostProcessor 以确保输出质量:
        - 格式验证和纠正
        - 删除重复内容
        - 生成引用 (如适用)
        - 一致性检查
        
        还处理知识提取和 Session 更新。
        
        Args:
            llm_output: LLM 的原始输出
            session_id: 用于对话跟踪的 Session ID
            extract_knowledge: 是否从对话中提取知识
            
        Returns:
            处理后准备供用户使用的最终回复
        
        使用示例:
            ```python
            # 调用 LLM 后
            final_response = await cm.post_process(
                llm_output,
                session_id="user123",
                extract_knowledge=True
            )
            ```
        """
        logger.info(f"[ContextMind] 步骤 6: 正在后处理 LLM 输出 ({len(llm_output)} 字符)...")
        
        # 如果可用则应用 PostProcessor
        processed_output = llm_output
        if hasattr(self.engine, 'postprocessor') and self.engine.postprocessor:
            processed_output = self.engine.postprocessor.process(llm_output)
            logger.debug(f"[ContextMind] PostProcessor 已应用")
        
        # 使用提供的 session_id 或存储的
        sid = session_id or self.session_id
        
        # 创建助手消息用于 Session 存储
        if sid and self.engine.session:
            assistant_msg = Message(role=MessageRole.ASSISTANT, content=processed_output)
            await self.engine.session.add_message(sid, assistant_msg)
            logger.debug(f"[ContextMind] 回复已保存到 Session: {sid}")
        
        # 如果启用则提取知识
        if extract_knowledge and self.engine.extractor and self.engine.memory:
            # 从 Session 获取最后一条用户消息
            if sid and self.engine.session:
                recent_messages = await self.engine.session.get_messages(sid, limit=2)
                if len(recent_messages) >= 2:
                    user_msg = recent_messages[-2]
                    assistant_msg = Message(role=MessageRole.ASSISTANT, content=processed_output)
                    
                    knowledge = await self.engine.extractor.extract([user_msg, assistant_msg])
                    if knowledge:
                        for k in knowledge:
                            await self.engine.memory.add(k)
                        logger.info(f"[ContextMind] ✓ 已提取并存储 {len(knowledge)} 条知识项")
        
        logger.info(f"[ContextMind] ✓ 后处理完成")
        return processed_output
    
    def set_extractor(self, extractor_name: str):
        """切换提取器插件"""
        extractor = registry.get_extractor(extractor_name)
        if extractor:
            # Extractor is set via engine initialization
            # This method is deprecated
            logger.warning(f"[ContextMind] set_extractor is deprecated. Use engine initialization parameters instead.")
            logger.info(f"[ContextMind] 提取器: {extractor_name}")
    
    def set_retriever(self, retriever_name: str):
        """切换检索器插件"""
        retriever = registry.get_retriever(retriever_name)
        if retriever and self.engine.memory:
            self.engine.memory.set_retriever(retriever)
            logger.info(f"[ContextMind] 已切换到检索器: {retriever_name}")
    
    def set_updater(self, updater_name: str):
        """切换更新器插件"""
        updater = registry.get_updater(updater_name)
        if updater and self.engine.memory:
            self.engine.memory.set_updater(updater)
            logger.info(f"[ContextMind] 已切换到更新器: {updater_name}")
    
    def list_available_plugins(self) -> Dict[str, list]:
        """列出所有可用插件"""
        return registry.get_all_plugins()
