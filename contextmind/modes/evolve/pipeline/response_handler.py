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
    """响应处理器，解析 LLM 响应、提取知识并更新记忆库，形成完整的记忆更新闭环。"""

    def __init__(
        self,
        session_manager: Any = None,
        memory_bank: Any = None,
        extractor: Any = None
    ):
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
        处理 LLM 响应的完整流程。

        Args:
            user_input: 原始用户输入
            llm_response: LLM 生成的响应
            context: 使用的上下文结果（可选）
            auto_extract: 是否自动提取知识
            auto_store: 是否自动存储到记忆库

        Returns:
            处理结果字典，包含 recorded、extracted_knowledge、stored 字段
        """
        result = {
            'recorded': False,
            'extracted_knowledge': [],
            'stored': False
        }

        if self.session_manager:
            await self._record_conversation(user_input, llm_response)
            result['recorded'] = True
        else:
            logger.warning("[ResponseHandler] ⚠️  未配置会话管理器，跳过对话记录")

        if auto_extract and self.extractor:
            knowledge_list = await self._extract_from_conversation(
                user_input,
                llm_response
            )
            result['extracted_knowledge'] = knowledge_list

            if knowledge_list:
                if auto_store and self.memory_bank:
                    await self.memory_bank.store(knowledge_list)
                    result['stored'] = True
                elif not auto_store:
                    logger.info("[ResponseHandler] ℹ️  auto_store=False，不自动存储知识")
                elif not self.memory_bank:
                    logger.warning("[ResponseHandler] ⚠️  未配置记忆库，无法存储知识")
        else:
            logger.info("[ResponseHandler] ℹ️  auto_extract=False 或未配置提取器，跳过知识提取")

        logger.info(
            f"[ResponseHandler] ✅ 响应处理完成 - "
            f"已记录: {result['recorded']}, "
            f"提取: {len(result['extracted_knowledge'])}条, "
            f"入库: {result['stored']}"
        )

        return result

    async def _record_conversation(
        self,
        user_input: str,
        assistant_response: str
    ) -> None:
        await self.session_manager.add_message(
            role=MessageRole.USER,
            content=user_input
        )

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

        knowledge_list = await self.extractor.extract(messages)

        logger.debug(f"[ResponseHandler] 从对话中提取到 {len(knowledge_list)} 条知识")

        return knowledge_list

    async def extract_from_response(
        self,
        llm_response: str
    ) -> List[Knowledge]:
        """仅从响应中提取知识（不记录对话）。"""
        if not self.extractor:
            logger.warning("[ResponseHandler] 未配置提取器，无法提取知识")
            return []

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
        """直接存储已提取的知识到记忆库。"""
        if not self.memory_bank:
            logger.warning("[ResponseHandler] 未配置记忆库，无法存储知识")
            return False

        if not knowledge_list:
            logger.info("[ResponseHandler] 知识列表为空，无需存储")
            return False

        await self.memory_bank.store(knowledge_list)
        logger.info(f"[ResponseHandler] 已存储 {len(knowledge_list)} 条知识到记忆库")

        return True
