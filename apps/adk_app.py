"""
ADK Application - 基于 google-adk 的应用示例

展示如何使用 google-adk (Agent Development Kit) 构建对话应用。
这是最简洁的方式来创建基于 Agent 的对话系统。

特点:
- 使用 ADK Agent 和 Runner 管理对话
- 自动会话管理
- 工具集成支持
- 多 Agent 编排

版本: v0.4.0
"""

import asyncio
import logging
from typing import Optional, List, Dict, Any

from utils.logger import get_logger
from utils.adk_adapter import (
    is_adk_available,
    ADK_AVAILABLE,
    ADKAgentBuilder,
    ADKRunner,
    ADKSessionManager,
    create_agent,
    create_function_tool,
)

# 禁用 HTTP/网络层的 debug 日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = get_logger(__name__)

# 导入统一的系统提示词
try:
    from prompts import CHAT_SYSTEM_PROMPT
except ImportError:
    CHAT_SYSTEM_PROMPT = "你是一个友好的助手。"


class ADKChatApplication:
    """
    基于 ADK 的聊天应用
    
    这是使用 google-adk 构建对话应用的推荐方式。
    相比传统的 ChatApplication，代码更简洁清晰。
    
    使用示例:
        ```python
        app = ADKChatApplication(
            agent_name="assistant",
            instruction="你是一个友好的助手",
            model="gemini-2.0-flash",
        )
        
        response = await app.chat("user-123", "你好")
        print(response)
        ```
    """
    
    def __init__(
        self,
        agent_name: str = "contextmind-agent",
        instruction: str = CHAT_SYSTEM_PROMPT,
        model: str = "gemini-2.0-flash",
        app_name: str = "contextmind",
        tools: Optional[List[Any]] = None,
        enable_memory: bool = False,
    ):
        """
        初始化 ADK 聊天应用
        
        Args:
            agent_name: Agent 名称
            instruction: 系统指令
            model: 模型名称 (如 gemini-2.0-flash)
            app_name: 应用名称
            tools: 可选的工具列表
            enable_memory: 是否启用 ADK 内置记忆 (需要 Google Cloud 配置)
        """
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "google-adk 未安装或不可用。"
                "请使用以下命令安装: pip install google-adk\n"
                "或者使用传统的 ChatApplication。"
            )
        
        self.agent_name = agent_name
        self.instruction = instruction
        self.model = model
        self.app_name = app_name
        
        # 创建 Agent
        self._agent = create_agent(
            name=agent_name,
            instruction=instruction,
            model=model,
            tools=tools or [],
        )
        
        # 创建 Runner
        self._runner = ADKRunner(
            agent=self._agent,
            app_name=app_name,
        )
        
        # 会话管理
        self._session_manager = ADKSessionManager(app_name=app_name)
        self._user_sessions: Dict[str, str] = {}  # user_id -> session_id
        
        logger.info(
            f"[ADKChatApplication] ✓ 初始化完成 "
            f"(agent: {agent_name}, model: {model})"
        )
    
    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        发送消息并获取响应
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            session_id: 可选的会话 ID
            
        Returns:
            助手的响应
        """
        # 使用缓存的会话 ID 或创建新的
        if session_id is None:
            session_id = self._user_sessions.get(user_id)
        
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())
            self._user_sessions[user_id] = session_id
        
        # 调用 Runner 获取响应
        response = await self._runner.chat_complete(
            user_id=user_id,
            message=message,
            session_id=session_id,
        )
        
        return response
    
    async def chat_stream(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ):
        """
        发送消息并流式获取响应
        
        Args:
            user_id: 用户 ID
            message: 用户消息
            session_id: 可选的会话 ID
            
        Yields:
            响应文本片段
        """
        if session_id is None:
            session_id = self._user_sessions.get(user_id)
        
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())
            self._user_sessions[user_id] = session_id
        
        async for chunk in self._runner.chat(
            user_id=user_id,
            message=message,
            session_id=session_id,
        ):
            yield chunk
    
    async def new_session(self, user_id: str) -> str:
        """
        为用户创建新会话
        
        Args:
            user_id: 用户 ID
            
        Returns:
            新的会话 ID
        """
        import uuid
        session_id = str(uuid.uuid4())
        self._user_sessions[user_id] = session_id
        return session_id
    
    @property
    def agent(self):
        """获取底层的 ADK Agent"""
        return self._agent
    
    @property
    def runner(self) -> ADKRunner:
        """获取底层的 ADK Runner"""
        return self._runner


class ADKMultiAgentApplication:
    """
    多 Agent 应用示例
    
    展示如何使用 ADK 构建多 Agent 系统，支持 Agent 间的转移。
    
    使用示例:
        ```python
        app = ADKMultiAgentApplication()
        app.add_agent("greeter", "负责问候用户")
        app.add_agent("helper", "负责回答问题")
        
        response = await app.chat("user-123", "你好")
        ```
    """
    
    def __init__(
        self,
        app_name: str = "multi-agent-app",
        root_agent_name: str = "coordinator",
        root_instruction: str = "你是一个协调者，负责将用户请求转发给合适的专家。",
        model: str = "gemini-2.0-flash",
    ):
        """
        初始化多 Agent 应用
        
        Args:
            app_name: 应用名称
            root_agent_name: 根 Agent 名称
            root_instruction: 根 Agent 指令
            model: 默认模型
        """
        if not ADK_AVAILABLE:
            raise RuntimeError(
                "google-adk 未安装或不可用。"
                "请使用以下命令安装: pip install google-adk"
            )
        
        self.app_name = app_name
        self.model = model
        self._sub_agents: List[Any] = []
        
        self._root_instruction = root_instruction
        self._root_agent_name = root_agent_name
        self._root_agent = None
        self._runner = None
        
        logger.info(f"[ADKMultiAgentApplication] 初始化 - app: {app_name}")
    
    def add_agent(
        self,
        name: str,
        instruction: str,
        tools: Optional[List[Any]] = None,
        model: Optional[str] = None,
    ) -> "ADKMultiAgentApplication":
        """
        添加子 Agent
        
        Args:
            name: Agent 名称
            instruction: Agent 指令
            tools: 可选的工具列表
            model: 可选的模型名称
            
        Returns:
            self (支持链式调用)
        """
        agent = create_agent(
            name=name,
            instruction=instruction,
            model=model or self.model,
            tools=tools or [],
        )
        self._sub_agents.append(agent)
        logger.debug(f"[ADKMultiAgentApplication] 添加子 Agent: {name}")
        return self
    
    def build(self) -> "ADKMultiAgentApplication":
        """
        构建多 Agent 系统
        
        必须在添加完所有子 Agent 后调用。
        
        Returns:
            self
        """
        from google.adk import Agent
        
        # 创建根 Agent，包含所有子 Agent
        self._root_agent = Agent(
            name=self._root_agent_name,
            model=self.model,
            instruction=self._root_instruction,
            sub_agents=self._sub_agents,
        )
        
        # 创建 Runner
        self._runner = ADKRunner(
            agent=self._root_agent,
            app_name=self.app_name,
        )
        
        logger.info(
            f"[ADKMultiAgentApplication] ✓ 构建完成 "
            f"(根 Agent: {self._root_agent_name}, 子 Agent: {len(self._sub_agents)})"
        )
        
        return self
    
    async def chat(
        self,
        user_id: str,
        message: str,
        session_id: Optional[str] = None,
    ) -> str:
        """
        发送消息并获取响应
        """
        if self._runner is None:
            raise RuntimeError("请先调用 build() 构建多 Agent 系统")
        
        return await self._runner.chat_complete(
            user_id=user_id,
            message=message,
            session_id=session_id,
        )


# 便捷函数：快速创建聊天应用
def create_chat_app(
    instruction: str = CHAT_SYSTEM_PROMPT,
    model: str = "gemini-2.0-flash",
) -> ADKChatApplication:
    """
    快速创建 ADK 聊天应用
    
    Args:
        instruction: 系统指令
        model: 模型名称
        
    Returns:
        ADKChatApplication 实例
    """
    return ADKChatApplication(
        instruction=instruction,
        model=model,
    )


# 示例用法
async def _demo():
    """示例演示"""
    print("=" * 60)
    print("ADK Chat Application Demo")
    print("=" * 60)
    
    if not ADK_AVAILABLE:
        print("❌ google-adk 未安装，无法运行示例")
        print("   请安装: pip install google-adk")
        return
    
    # 创建应用
    app = ADKChatApplication(
        agent_name="demo-assistant",
        instruction="你是一个友好的中文助手。请用中文回复用户。",
        model="gemini-2.0-flash",
    )
    
    # 模拟对话
    messages = [
        "你好！",
        "今天天气怎么样？",
        "谢谢！",
    ]
    
    for msg in messages:
        print(f"\n用户: {msg}")
        try:
            response = await app.chat("demo-user", msg)
            print(f"助手: {response}")
        except Exception as e:
            print(f"错误: {e}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(_demo())


__all__ = [
    "ADKChatApplication",
    "ADKMultiAgentApplication",
    "create_chat_app",
]
