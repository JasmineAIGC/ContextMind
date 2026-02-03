"""
ContextMind Framework - 上下文工程与记忆进化框架

v0.4.1 - 直接使用 ADK，专注于上下文工程和记忆进化自研逻辑。

核心特点：
1. 五层上下文架构（感知、记忆、上下文、生成、进化）
2. 直接使用 ADK Agent 进行 LLM 调用
3. 记忆库和记忆进化系统（自研）
4. Pipeline 算法（预处理、压缩、重排序等，自研）

主要组件：
- engine: ContextEngine 核心引擎
- agent: ContextMind 专用 ADK Agent（直接使用 google.adk）
- pipeline: 上下文处理流水线（自研算法）
- memory: 记忆库和会话管理（自研）
- evolution: 记忆进化系统（自研）

与 DST 的区别：
- DST: 简单的状态追踪，专注于槽位提取
- ContextMind: 复杂的上下文工程，包含记忆库、进化学习等
"""

# ADK Agent (先导入，避免循环依赖)
from .agent import ContextMindAgent, ContextMindConfig

# 核心数据模型和类型 (直接从子模块导入，避免 core.__init__ 的循环)
from .core.data_models import (
    Message,
    ContextResult,
    ContextItem,
    ProcessedContext,
    Knowledge,
)
from .core.types import MessageRole, ContextSource
from .core.configs import DEFAULT_MEMORY_CONFIG

# 核心引擎 (最后导入)
from .engine import ContextEngine

__all__ = [
    # ADK Agent
    "ContextMindAgent",
    "ContextMindConfig",
    
    # 核心引擎
    "ContextEngine",
    
    # 数据模型
    "Message",
    "ContextResult",
    "ContextItem",
    "ProcessedContext",
    "Knowledge",
    
    # 类型
    "MessageRole",
    "ContextSource",
    
    # 配置
    "DEFAULT_MEMORY_CONFIG",
]

__version__ = "0.4.1"
