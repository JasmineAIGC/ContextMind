"""
Evolution Session Manager using google-adk

使用 google-adk 的 InMemorySessionService 来管理会话。
提供与 EvolutionEngine 兼容的接口。

版本: v0.4.1
"""

from typing import List, Optional, Any
from google.adk.sessions import InMemorySessionService, Session

from evolution.core.types import MessageRole
from evolution.core.data_models import Message
from utils.logger import get_logger

logger = get_logger("evolution.memory.adk_session")


class ADKSessionManager:
    """
    基于 google-adk InMemorySessionService 的会话管理器
    
    ADK 负责：
    - 会话的创建和管理
    - 会话状态的存储
    
    本类负责：
    - 提供简化的消息管理接口
    - 与 EvolutionEngine 兼容的 API
    """
    
    def __init__(
        self,
        app_name: str,
        user_id: str,
        session_service: Optional[InMemorySessionService] = None,
        max_recent_events: int = 9999,
        **kwargs
    ):
        """
        初始化会话管理器
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
            session_service: 可选的 ADK Session 服务（如果不提供则创建新的）
            max_recent_events: 最大保留事件数
            **kwargs: 其他参数（向后兼容）
        """
        self.app_name = app_name
        self.user_id = user_id
        self.max_recent_events = max_recent_events
        
        # 使用提供的或创建新的 ADK Session Service
        self.session_service = session_service or InMemorySessionService()
        
        # 创建或获取会话（使用同步方法，因为 __init__ 不能是 async）
        self.session = self.session_service.create_session_sync(
            app_name=app_name,
            user_id=user_id,
            state={"messages": []}  # 初始化消息列表
        )
        
        logger.info(
            f"[ADK Session] 初始化成功 - app:{app_name}, user:{user_id}, "
            f"session:{self.session.id}"
        )
    
    async def add_message(self, role: MessageRole, content: str) -> None:
        """
        添加消息到会话
        
        Args:
            role: 消息角色
            content: 消息内容
        """
        message = Message(role=role, content=content)
        
        # 从 session state 获取消息列表（创建副本以避免直接修改）
        messages = list(self.session.state.get("messages", []))
        
        # 将 Message 对象转换为可序列化的字典
        msg_dict = {
            "role": message.role.value,
            "content": message.content,
            "timestamp": message.timestamp.isoformat(),
            "metadata": message.metadata
        }
        messages.append(msg_dict)
        
        # 限制消息数量（保留最近的消息）
        if len(messages) > self.max_recent_events:
            messages = messages[-self.max_recent_events:]
        
        # 更新 session state
        self.session.state["messages"] = messages
        
        logger.debug(f"[ADK Session] 添加消息 - role:{role.value}, content_len:{len(content)}")
    
    async def get_recent_history(self, limit: Optional[int] = None) -> List[Message]:
        """
        获取最近的对话历史
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            消息列表
        """
        messages = self.session.state.get("messages", [])
        
        if limit:
            messages = messages[-limit:]
        
        # 转换为 Message 对象
        result = []
        for msg in messages:
            try:
                result.append(Message(
                    role=MessageRole(msg.get("role", "user")),
                    content=msg.get("content", ""),
                    metadata=msg.get("metadata", {})
                ))
            except Exception as e:
                logger.warning(f"[ADK Session] 消息转换失败: {e}")
                continue
        
        return result
    
    async def clear(self) -> None:
        """清空对话历史"""
        self.session.state["messages"] = []
        logger.info("[ADK Session] 清空历史")
    
    # 向后兼容别名
    async def clear_history(self) -> None:
        """清空对话历史（别名）"""
        await self.clear()
    
    def get_session_id(self) -> str:
        """获取会话ID"""
        return self.session.id
    
    def get_session(self) -> Session:
        """获取 ADK Session 对象（用于记忆系统）"""
        return self.session
