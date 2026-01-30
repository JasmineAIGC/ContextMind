"""
日志工具

ContextMind v0.4.0 统一日志系统
"""

import logging
from datetime import datetime
from enum import Enum as PyEnum
from pathlib import Path


class LogLevel(PyEnum):
    """ContextMind 日志级别"""
    INFO = "INFO"      # 信息模式：记录关键信息和流程
    DEBUG = "DEBUG"    # 调试模式：记录所有详细日志


class ContextMindLogger:
    """
    ContextMind v0.4.0 统一日志系统
    
    功能特性：
    - 信息模式：记录关键信息、Pipeline 输入输出和重要事件
    - 调试模式：记录所有内部细节和调试信息
    
    使用示例：
        logger = ContextMindLogger("MyModule", level=LogLevel.INFO)
        logger.info("关键信息")
        logger.debug("调试信息")
    """
    
    # 类级别变量：追踪全局日志级别
    _global_level: LogLevel = LogLevel.INFO
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """
        初始化 Logger
        
        Args:
            name: 模块名称
            level: 日志级别 (INFO 或 DEBUG)
        """
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self.level = level
    
    @classmethod
    def get_current_level(cls) -> LogLevel:
        """
        获取当前全局日志级别
        
        Returns:
            LogLevel: 当前的全局日志级别
        """
        return cls._global_level
    
    @classmethod
    def set_global_level(cls, level: LogLevel):
        """
        设置全局日志级别
        
        Args:
            level: 要设置的日志级别
        """
        cls._global_level = level
    
    def info(self, message: str):
        """
        信息日志（在 INFO 和 DEBUG 模式下显示）
        用于关键信息、Pipeline 事件、输入输出
        """
        self._logger.info(f"[{self.name}] {message}")
    
    def debug(self, message: str):
        """
        调试日志（仅在 DEBUG 模式下显示）
        用于内部细节和调试信息
        """
        # 检查全局级别而非实例级别，确保DEBUG日志能被保存到文件
        if self._global_level == LogLevel.DEBUG or self.level == LogLevel.DEBUG:
            self._logger.debug(f"[{self.name}] {message}")
    
    def separator(self, char="=", length=100):
        """打印分隔线（在所有模式下显示）"""
        self._logger.info(char * length)
    
    def section_start(self, title: str):
        """开始主要章节（在所有模式下显示）"""
        self.separator("=")
        self._logger.info(f"[{self.name}] ========== {title} ==========")
        self.separator("=")
    
    def section_end(self, title: str = None):
        """结束主要章节（在所有模式下显示）"""
        if title:
            self.separator("-")
            self._logger.info(f"[{self.name}] ========== {title} 结束 ==========")
            self.separator("-")
        else:
            self.separator("-")
    
    def warning(self, message: str):
        """警告日志（在所有模式下显示）"""
        self._logger.warning(f"[{self.name}] {message}")
    
    def error(self, message: str):
        """错误日志（在所有模式下显示）"""
        self._logger.error(f"[{self.name}] {message}")


# 全局日志级别
_GLOBAL_LOG_LEVEL = LogLevel.INFO


def set_global_log_level(level: LogLevel):
    """
    为所有 ContextMind Logger 设置全局日志级别
    
    Args:
        level: LogLevel.INFO 或 LogLevel.DEBUG
    """
    global _GLOBAL_LOG_LEVEL
    _GLOBAL_LOG_LEVEL = level
    # 同时更新类级别变量
    ContextMindLogger.set_global_level(level)


def get_global_log_level() -> LogLevel:
    """获取当前全局日志级别"""
    return _GLOBAL_LOG_LEVEL


def get_logger(name: str, level: LogLevel = None) -> ContextMindLogger:
    """
    获取 ContextMind Logger 实例
    
    Args:
        name: Logger 名称（通常为模块名）
        level: 日志级别（未指定时使用全局级别）
        
    Returns:
        ContextMindLogger 实例
    """
    if level is None:
        level = _GLOBAL_LOG_LEVEL
    return ContextMindLogger(name, level)


def setup_logging(level: LogLevel = LogLevel.INFO, python_log_level=None, save_to_file: bool = True, log_dir: str = "logs"):
    """
    设置 ContextMind 日志配置
    
    Args:
        level: ContextMind 日志级别（INFO 或 DEBUG）
        python_log_level: Python 日志级别（默认基于 ContextMind 级别）
        save_to_file: 是否自动保存日志到文件（默认：True）
        log_dir: 日志文件保存目录（默认："logs"）
    """
    # 设置全局 ContextMind 日志级别
    set_global_log_level(level)
    
    # 将 ContextMind 级别映射到 Python 日志级别
    if python_log_level is None:
        if level == LogLevel.DEBUG:
            python_log_level = logging.DEBUG
        else:
            python_log_level = logging.INFO
    
    # 配置处理器
    handlers = []
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(python_log_level)
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)
    
    # 文件处理器（如果启用）
    if save_to_file:
        # 创建日志目录
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        
        # 生成日志文件名（包含时间戳）
        log_filename = f"contextmind_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_filepath = log_path / log_filename
        
        # 创建文件处理器
        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(python_log_level)
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)
        
        print(f"📝 日志将自动保存到: {log_filepath}")
    
    # 配置 Python 日志
    logging.basicConfig(
        level=python_log_level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
        force=True  # 覆盖任何现有配置
    )


# 导出日志级别以保持向后兼容
INFO = logging.INFO
DEBUG = logging.DEBUG
