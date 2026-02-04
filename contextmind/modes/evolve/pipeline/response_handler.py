"""
ResponseHandler - 流水线步骤5

响应处理和记忆更新模块。
处理 LLM 响应并基于响应内容更新记忆库。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from ..core.data_models import ContextResult, Message, Knowledge
from ..core.types import MessageRole
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class ResponseHandler:
    """
    响应处理器
    
    职责：
    1. 解析 LLM 响应
    2. 从响应中提取知识
    3. 更新记忆库
    4. 记录对话轮次
    
    这是流水线的最后一步，形成完整的记忆更新闭环。
    """
    
    def __init__(
        self,
        session_manager: Any = None,
        memory_bank: Any = None,
        extractor: Any = None
    ):
        """
        初始化响应处理器
        
        Args:
            session_manager: 会话管理器实例
            memory_bank: 记忆库实例
            extractor: 知识提取器实例
        """
        self.session_manager = session_manager
        self.memory_bank = memory_bank
        self.extractor = extractor
        
        logger.info("[ResponseHandler] 初始化完成")
    
    async def handle_response(
        self,
        user_input: str,
        llm_response: str,
        context: Optional[ContextResult] = None,
        auto_extract: bool = True,
        auto_store: bool = True
    ) -> Dict[str, Any]:
        """
        处理 LLM 响应的完整流程
        
        Args:
            user_input: 原始用户输入
            llm_response: LLM 生成的响应
            context: 使用的上下文结果（可选）
            auto_extract: 是否自动提取知识
            auto_store: 是否自动存储到记忆库
            
        Returns:
            处理结果字典，包含：
            - recorded: 是否已记录对话
            - extracted_knowledge: 提取的知识列表
            - stored: 是否已存储到记忆库
        """
        logger.info("")
        logger.info("=" * 100)
        logger.info("[ResponseHandler] ========== 开始响应处理 ==========")
        logger.info(f"[ResponseHandler] 📝 用户输入: {len(user_input)} 字符")
        logger.info(f"[ResponseHandler] 🤖 LLM响应: {len(llm_response)} 字符")
        logger.info("=" * 100)
        logger.info("")
        
        result = {
            'recorded': False,
            'extracted_knowledge': [],
            'stored': False
        }
        
        # 1. 记录对话轮次到会话
        logger.info("[ResponseHandler] 💾 步骤 1/3: 记录对话轮次")
        if self.session_manager:
            await self._record_conversation(user_input, llm_response)
            result['recorded'] = True
            logger.info("[ResponseHandler] ✓ 对话记录完成")
        else:
            logger.warning("[ResponseHandler] ⚠️  未配置会话管理器，跳过对话记录")
        logger.info("")
        
        # 2. 从对话中提取知识（如果启用）
        if auto_extract and self.extractor:
            logger.info("[ResponseHandler] 🧠 步骤 2/3: 提取对话知识")
            knowledge_list = await self._extract_from_conversation(
                user_input,
                llm_response
            )
            result['extracted_knowledge'] = knowledge_list
            
            if knowledge_list:
                logger.info(f"[ResponseHandler] ✓ 知识提取完成 - 提取到 {len(knowledge_list)} 条知识")
                
                # 3. 存储到记忆库（如果启用）
                if auto_store and self.memory_bank:
                    logger.info("")
                    logger.info("[ResponseHandler] 📥 步骤 3/3: 存储知识到记忆库")
                    await self.memory_bank.store(knowledge_list)
                    result['stored'] = True
                    logger.info("[ResponseHandler] ✓ 知识入库完成")
                else:
                    logger.info("")
                    if not auto_store:
                        logger.info("[ResponseHandler] ℹ️  auto_store=False，不自动存储知识")
                    elif not self.memory_bank:
                        logger.warning("[ResponseHandler] ⚠️  未配置记忆库，无法存储知识")
            else:
                logger.info("[ResponseHandler] ℹ️  未提取到有效知识")
                logger.info("")
        else:
            logger.info("[ResponseHandler] ℹ️  auto_extract=False 或未配置提取器，跳过知识提取")
            logger.info("")
        
        logger.info("-" * 100)
        logger.info(
            f"[ResponseHandler] ✅ 响应处理完成 - "
            f"已记录: {result['recorded']}, "
            f"提取: {len(result['extracted_knowledge'])}条, "
            f"入库: {result['stored']}"
        )
        logger.info("-" * 100)
        logger.info("")
        
        return result
    
    async def _record_conversation(
        self,
        user_input: str,
        assistant_response: str
    ) -> None:
        """
        记录对话轮次到会话管理器
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
        """
        # 添加用户消息
        await self.session_manager.add_message(
            role=MessageRole.USER,
            content=user_input
        )
        
        # 添加助手消息
        await self.session_manager.add_message(
            role=MessageRole.ASSISTANT,
            content=assistant_response
        )
        
        logger.debug(
            f"[ResponseHandler] 对话已记录: "
            f"用户({len(user_input)}字) + 助手({len(assistant_response)}字)"
        )
    
    async def _extract_from_conversation(
        self,
        user_input: str,
        assistant_response: str
    ) -> List[Knowledge]:
        """
        从对话中提取知识
        
        Args:
            user_input: 用户输入
            assistant_response: 助手回复
            
        Returns:
            提取的知识列表
        """
        # 构建消息列表用于提取
        messages = [
            Message(
                role=MessageRole.USER,
                content=user_input,
                timestamp=datetime.now()
            ),
            Message(
                role=MessageRole.ASSISTANT,
                content=assistant_response,
                timestamp=datetime.now()
            )
        ]
        
        # 使用提取器提取知识
        knowledge_list = await self.extractor.extract(messages)
        
        logger.debug(f"[ResponseHandler] 从对话中提取到 {len(knowledge_list)} 条知识")
        
        return knowledge_list
    
    async def extract_from_response(
        self,
        llm_response: str
    ) -> List[Knowledge]:
        """
        仅从响应中提取知识（不记录对话）
        
        这是一个辅助方法，用于只需要提取知识而不需要记录对话的场景。
        
        Args:
            llm_response: LLM 响应内容
            
        Returns:
            提取的知识列表
        """
        if not self.extractor:
            logger.warning("[ResponseHandler] 未配置提取器，无法提取知识")
            return []
        
        # 构建助手消息用于提取
        messages = [
            Message(
                role=MessageRole.ASSISTANT,
                content=llm_response,
                timestamp=datetime.now()
            )
        ]
        
        knowledge_list = await self.extractor.extract(messages)
        logger.info(f"[ResponseHandler] 从响应中提取到 {len(knowledge_list)} 条知识")
        
        return knowledge_list
    
    async def update_memory(
        self,
        knowledge_list: List[Knowledge]
    ) -> bool:
        """
        直接更新记忆库
        
        这是一个辅助方法，用于直接存储已提取的知识。
        
        Args:
            knowledge_list: 知识列表
            
        Returns:
            是否成功存储
        """
        if not self.memory_bank:
            logger.warning("[ResponseHandler] 未配置记忆库，无法存储知识")
            return False
        
        if not knowledge_list:
            logger.info("[ResponseHandler] 知识列表为空，无需存储")
            return False
        
        await self.memory_bank.store(knowledge_list)
        logger.info(f"[ResponseHandler] 已存储 {len(knowledge_list)} 条知识到记忆库")
        
        return True
