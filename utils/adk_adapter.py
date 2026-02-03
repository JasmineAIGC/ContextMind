"""
ADK 适配器模块 - google-adk 集成支持

提供与 google-adk (Agent Development Kit) 的集成，简化 Agent 创建和会话管理。
同时保持与现有 SimpleLLMClient 的向后兼容性。

版本: v0.4.0
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, List, Dict, Any, AsyncGenerator
import os

from .logger import get_logger

logger = get_logger(__name__)

# 尝试导入 google-adk
try:
    from google.adk import Agent, Runner
    from google.adk.sessions import InMemorySessionService, Session
    from google.adk.memory import InMemoryMemoryService
    from google.adk.tools import FunctionTool
    ADK_AVAILABLE = True
except ImportError:
    ADK_AVAILABLE = False
    Agent = None  # type: ignore
    Runner = None  # type: ignore
    InMemorySessionService = None  # type: ignore
    InMemoryMemoryService = None  # type: ignore
    Session = None  # type: ignore
    FunctionTool = None  # type: ignore
    logger.warning("google-adk 未安装，ADK 功能不可用")


@dataclass
class ADKConfig:
    """ADK 配置"""
    app_name: str = "contextmind"
    model: str = "gemini-2.0-flash"
    api_key: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> "ADKConfig":
        """从环境变量加载配置"""
        return cls(
            app_name=os.getenv("ADK_APP_NAME", "contextmind"),
            model=os.getenv("ADK_MODEL", os.getenv("GOOGLE_MODEL", "gemini-2.0-flash")),
            api_key=os.getenv("GOOGLE_API_KEY"),
        )


class ADKSessionManager:
    """
    ADK 会话管理器
    
    封装 google-adk 的 InMemorySessionService，提供简化的会话管理 API。
    可作为现有 SessionManager 的替代或补充。
    
    使用示例:
        ```python
        manager = ADKSessionManager(app_name="my-app")
        session = await manager.get_or_create_session("user-123")
        ```
    """
    
    def __init__(
        self,
        app_name: str = "contextmind",
        session_service: Optional[Any] = None,
    ):
        """
        初始化 ADK 会话管理器
        
        Args:
            app_name: 应用名称
            session_service: 可选的自定义会话服务（默认使用 InMemorySessionService）
        """
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "google-adk 未安装。请使用以下命令安装: pip install google-adk"
            )
        
        self.app_name = app_name
        self._session_service = session_service or InMemorySessionService()
        self._sessions: Dict[str, Session] = {}
        
        logger.info(f"[ADKSessionManager] 初始化完成 - app: {app_name}")
    
    async def get_or_create_session(
        self,
        user_id: str,
        session_id: Optional[str] = None,
    ) -> Session:
        """
        获取或创建会话
        
        Args:
            user_id: 用户 ID
            session_id: 可选的会话 ID（默认自动生成）
            
        Returns:
            Session 对象
        """
        import uuid
        
        session_id = session_id or str(uuid.uuid4())
        cache_key = f"{user_id}:{session_id}"
        
        if cache_key in self._sessions:
            return self._sessions[cache_key]
        
        # 尝试获取现有会话
        session = await self._session_service.get_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
        )
        
        if session is None:
            # 创建新会话
            session = await self._session_service.create_session(
                app_name=self.app_name,
                user_id=user_id,
                session_id=session_id,
            )
            logger.debug(f"[ADKSessionManager] 创建新会话: {session_id}")
        
        self._sessions[cache_key] = session
        return session
    
    async def delete_session(self, user_id: str, session_id: str) -> None:
        """删除会话"""
        cache_key = f"{user_id}:{session_id}"
        
        await self._session_service.delete_session(
            app_name=self.app_name,
            user_id=user_id,
            session_id=session_id,
        )
        
        if cache_key in self._sessions:
            del self._sessions[cache_key]
        
        logger.debug(f"[ADKSessionManager] 删除会话: {session_id}")
    
    @property
    def session_service(self) -> Any:
        """获取底层的会话服务"""
        return self._session_service


class ADKAgentBuilder:
    """
    ADK Agent 构建器
    
    简化 google-adk Agent 的创建过程，提供流式 API。
    
    使用示例:
        ```python
        agent = (
            ADKAgentBuilder("my-agent")
            .with_instruction("你是一个友好的助手")
            .with_model("gemini-2.0-flash")
            .add_tool(my_function)
            .build()
        )
        ```
    """
    
    def __init__(self, name: str):
        """
        初始化 Agent 构建器
        
        Args:
            name: Agent 名称
        """
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "google-adk 未安装。请使用以下命令安装: pip install google-adk"
            )
        
        self._name = name
        self._model = "gemini-2.0-flash"
        self._instruction = ""
        self._description = ""
        self._tools: List[Any] = []
        self._sub_agents: List[Any] = []
    
    def with_model(self, model: str) -> "ADKAgentBuilder":
        """设置模型"""
        self._model = model
        return self
    
    def with_instruction(self, instruction: str) -> "ADKAgentBuilder":
        """设置指令"""
        self._instruction = instruction
        return self
    
    def with_description(self, description: str) -> "ADKAgentBuilder":
        """设置描述"""
        self._description = description
        return self
    
    def add_tool(self, tool: Any) -> "ADKAgentBuilder":
        """添加工具"""
        self._tools.append(tool)
        return self
    
    def add_sub_agent(self, agent: Any) -> "ADKAgentBuilder":
        """添加子 Agent"""
        self._sub_agents.append(agent)
        return self
    
    def build(self) -> Agent:
        """构建 Agent"""
        # 清理名称
        sanitized_name = _sanitize_agent_name(self._name)
        
        return Agent(
            name=sanitized_name,
            model=self._model,
            instruction=self._instruction,
            description=self._description,
            tools=self._tools if self._tools else [],
            sub_agents=self._sub_agents if self._sub_agents else [],
        )


class ADKRunner:
    """
    ADK Runner 封装
    
    简化 google-adk Runner 的使用，提供易用的对话 API。
    
    使用示例:
        ```python
        runner = ADKRunner(agent, app_name="my-app")
        async for response in runner.chat("user-1", "你好"):
            print(response)
        ```
    """
    
    def __init__(
        self,
        agent: Agent,
        app_name: str = "contextmind",
        session_service: Optional[Any] = None,
        memory_service: Optional[Any] = None,
    ):
        """
        初始化 ADK Runner
        
        Args:
            agent: ADK Agent 实例
            app_name: 应用名称
            session_service: 可选的会话服务
            memory_service: 可选的记忆服务
        """
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "google-adk 未安装。请使用以下命令安装: pip install google-adk"
            )
        
        self._agent = agent
        self._app_name = app_name
        self._session_service = session_service or InMemorySessionService()
        self._memory_service = memory_service
        
        self._runner = Runner(
            agent=agent,
            app_name=app_name,
            session_service=self._session_service,
            memory_service=self._memory_service,
        )
        
        logger.info(f"[ADKRunner] 初始化完成 - agent: {agent.name}, app: {app_name}")
    
    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """
        发送消息并获取响应
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            session_id: 可选的会话 ID
            
        Yields:
            响应文本片段
        """
        import uuid
        from google.genai import types
        
        session_id = session_id or str(uuid.uuid4())
        
        # 确保会话存在
        session = await self._session_service.get_session(
            app_name=self._app_name,
            user_id=user_id,
            session_id=session_id,
        )
        
        if session is None:
            session = await self._session_service.create_session(
                app_name=self._app_name,
                user_id=user_id,
                session_id=session_id,
            )
        
        # 创建消息内容
        content = types.Content(
            role="user",
            parts=[types.Part(text=message)],
        )
        
        # 运行 Agent
        async for event in self._runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=content,
        ):
            # 提取文本响应
            if hasattr(event, 'content') and event.content:
                if hasattr(event.content, 'parts'):
                    for part in event.content.parts:
                        if hasattr(part, 'text') and part.text:
                            yield part.text
    
    async def chat_complete(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        发送消息并获取完整响应
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            session_id: 可选的会话 ID
            
        Returns:
            完整的响应文本
        """
        response_parts = []
        async for part in self.chat(user_id, message, session_id):
            response_parts.append(part)
        return "".join(response_parts)


def _sanitize_agent_name(name: str) -> str:
    """
    清理 Agent 名称，使其成为有效的标识符
    
    ADK 要求 Agent 名称必须是有效的 Python 标识符：
    - 以字母或下划线开头
    - 只能包含字母、数字和下划线
    
    Args:
        name: 原始名称
        
    Returns:
        清理后的名称
    """
    import re
    # 替换连字符和空格为下划线
    sanitized = re.sub(r'[-\s]+', '_', name)
    # 移除其他非法字符
    sanitized = re.sub(r'[^a-zA-Z0-9_]', '', sanitized)
    # 确保以字母或下划线开头
    if sanitized and not sanitized[0].isalpha() and sanitized[0] != '_':
        sanitized = '_' + sanitized
    # 如果结果为空，使用默认名称
    if not sanitized:
        sanitized = 'agent'
    return sanitized


def create_agent(
    name: str,
    instruction: str,
    model: str = "gemini-2.0-flash",
    tools: Optional[List[Any]] = None,
) -> Agent:
    """
    快速创建 ADK Agent
    
    这是一个便捷函数，用于快速创建简单的 Agent。
    名称会自动清理为有效的标识符格式。
    
    Args:
        name: Agent 名称（会自动清理为有效标识符）
        instruction: 系统指令
        model: 模型名称
        tools: 可选的工具列表
        
    Returns:
        Agent 实例
        
    使用示例:
        ```python
        agent = create_agent(
            name="assistant",
            instruction="你是一个友好的助手",
            model="gemini-2.0-flash",
        )
        ```
    """
    if not ADK_AVAILABLE:
        raise RuntimeError(
            "google-adk 未安装。请使用以下命令安装: pip install google-adk"
        )
    
    # 清理名称
    sanitized_name = _sanitize_agent_name(name)
    
    return Agent(
        name=sanitized_name,
        model=model,
        instruction=instruction,
        tools=tools or [],
    )


def create_function_tool(func: Any) -> Any:
    """
    将 Python 函数转换为 ADK 工具
    
    Args:
        func: Python 函数
        
    Returns:
        FunctionTool 实例
    """
    if not ADK_AVAILABLE:
        raise RuntimeError(
            "google-adk 未安装。请使用以下命令安装: pip install google-adk"
        )
    
    return FunctionTool(func)


# 导出便捷检查函数
def is_adk_available() -> bool:
    """检查 ADK 是否可用"""
    return ADK_AVAILABLE


__all__ = [
    # 配置
    "ADKConfig",
    # 会话管理
    "ADKSessionManager",
    # Agent 构建
    "ADKAgentBuilder",
    "create_agent",
    # Runner
    "ADKRunner",
    # 工具
    "create_function_tool",
    # 检查
    "is_adk_available",
    # 常量
    "ADK_AVAILABLE",
]
