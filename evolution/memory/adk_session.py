"""
Evolution Session Manager using google-adk

使用 google-adk 的 InMemorySessionService 来管理会话。
简化了原有的 session.py 实现，从 ~150 行减少到 ~50 行。

版本: v0.4.1
"""

from typing import List, Optional
from google.adk.sessions import InMemorySessionService, Session
from evolution.core.data_models import Message, MessageRole
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
    - 兼容 Evolution 的数据模型
    """
    
    def __init__(self, app_name: str, user_id: str):
        """
        初始化会话管理器
        
        Args:
            app_name: 应用名称
            user_id: 用户ID
        """
        self.app_name = app_name
        self.user_id = user_id
        
        # 使用 ADK 的 Session Service
        self.session_service = InMemorySessionService()
        
        # 创建或获取会话
        self.session = self.session_service.create_session(
            app_name=app_name,
            user_id=user_id,
            state={"messages": []}  # 初始化消息列表
        )
        
        logger.info(f"[ADK Session] 初始化成功 - app:{app_name}, user:{user_id}, session:{self.session.session_id}")
    
    async def add_message(self, role: MessageRole, content: str) -> None:
        """
        添加消息到会话
        
        Args:
            role: 消息角色
            content: 消息内容
        """
        message = Message(role=role, content=content)
        
        # 从 session state 获取消息列表
        messages = self.session.state.get("messages", [])
        messages.append(message.dict())
        
        # 更新 session state
        self.session.state.update({"messages": messages})
        
        logger.debug(f"[ADK Session] 添加消息 - role:{role}, content_len:{len(content)}")
    
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
        return [Message(**msg) for msg in messages]
    
    async def clear_history(self) -> None:
        """清空对话历史"""
        self.session.state.update({"messages": []})
        logger.info("[ADK Session] 清空历史")
    
    def get_session_id(self) -> str:
        """获取会话ID"""
        return self.session.session_id
    
    def get_session(self) -> Session:
        """获取 ADK Session 对象（用于记忆系统）"""
        return self.session
