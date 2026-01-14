"""
ContextMind - Universal Context Optimization Framework

专注于上下文优化的独立模块，可嵌入任何对话系统。

Core Components:
- ContextEngine: 上下文优化引擎
- Data Models: Message, Memory, ContextResult
- Client: LLM 客户端（可选）
- Logger: 日志工具
"""

# 核心引擎
from .engine import ContextEngine

# 数据模型
from .data_models import Message, Memory, ContextResult

# LLM 客户端（可选）
from .client import Client, ClientConfig

# 日志工具
from .logger import get_logger, setup_logging, ContextMindLogger, INFO, DEBUG

__all__ = [
    # 核心引擎
    "ContextEngine",
    
    # 数据模型
    "Message",
    "Memory", 
    "ContextResult",
    
    # LLM 客户端
    "Client",
    "ClientConfig",
    
    # 日志
    "get_logger",
    "setup_logging",
    "ContextMindLogger",
    "INFO",
    "DEBUG",
]

__version__ = "2.0.0"
