"""
日志工具

ContextMind 统一日志系统
"""

import io
import logging
import sys
from datetime import datetime
from enum import Enum as PyEnum
from pathlib import Path


class LogLevel(PyEnum):
    """Evolve 日志级别。"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class Logger:
    """ContextMind 统一日志系统，支持 INFO/DEBUG 两种模式及文件输出。"""
    
    # 类级别变量，所有 Logger 实例共享同一个权威日志级别，
    # 确保 set_global_log_level() 能即时影响所有已创建的 logger。
    _global_level: LogLevel = LogLevel.INFO
    
    def __init__(self, name: str, level: LogLevel = LogLevel.INFO):
        """
        初始化 Logger
        
        Args:
            name: 模块名称
            level: 日志级别 (DEBUG, INFO, WARNING 或 ERROR)
        """
        self.name = name
        self.level = level
        self._logger = logging.getLogger(name)
        
    def set_level(self, level: LogLevel):
        """设置日志级别"""
        self.level = level
    
    def setLevel(self, level):
        """设置日志级别（兼容标准 logging API）。

        Bridges Python's integer-based ``logging`` levels to the internal
        ``LogLevel`` enum, so third-party code that calls ``logger.setLevel(logging.DEBUG)``
        still works correctly.

        Args:
            level: LogLevel 枚举或标准 logging 整数级别。
        """
        if isinstance(level, int):
            if level >= logging.ERROR:
                self.level = LogLevel.ERROR
            elif level >= logging.WARNING:
                self.level = LogLevel.WARNING
            elif level >= logging.INFO:
                self.level = LogLevel.INFO
            else:
                self.level = LogLevel.DEBUG
            self._logger.setLevel(level)
        elif isinstance(level, LogLevel):
            self.set_level(level)
        else:
            if hasattr(logging, str(level).upper()):
                self.setLevel(getattr(logging, str(level).upper()))
            else:
                self.level = level
    
    @classmethod
    def get_current_level(cls) -> LogLevel:
        """返回当前全局日志级别。"""
        return cls._global_level

    @classmethod
    def set_global_level(cls, level: LogLevel):
        """设置全局日志级别。"""
        cls._global_level = level
    
    def info(self, message: str):
        """记录 INFO 级别日志。"""
        self._logger.info(f"[{self.name}] {message}")

    def debug(self, message: str):
        """记录 DEBUG 级别日志（仅在 DEBUG 模式下输出）。"""
        # 同时检查全局级别和实例级别，允许单个 logger 独立提升为 DEBUG，
        # 而不影响应用中其他 logger 的级别。
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
    
    def error(self, message: str, exc_info=None):
        """记录 ERROR 级别日志。

        Args:
            message: 错误信息
            exc_info: 是否附加异常堆栈（兼容标准 logging）
        """
        if exc_info:
            self._logger.error(f"[{self.name}] {message}", exc_info=exc_info)
        else:
            self._logger.error(f"[{self.name}] {message}")


# 全局日志级别
_GLOBAL_LOG_LEVEL = LogLevel.INFO


def set_global_log_level(level: LogLevel):
    """为所有 ContextMind Logger 设置全局日志级别。"""
    global _GLOBAL_LOG_LEVEL
    _GLOBAL_LOG_LEVEL = level
    Logger.set_global_level(level)


def get_global_log_level() -> LogLevel:
    """返回当前全局日志级别。"""
    return _GLOBAL_LOG_LEVEL


def get_logger(name: str, level: LogLevel = None) -> "Logger":
    """获取 Logger 实例。

    Args:
        name: Logger 名称（通常为模块名）
        level: 日志级别，未指定时使用全局级别

    Returns:
        Logger 实例
    """
    if level is None:
        level = _GLOBAL_LOG_LEVEL
    return Logger(name, level)


def setup_logging(level: LogLevel = LogLevel.INFO, python_log_level=None, save_to_file: bool = True, log_dir: str = "logs"):
    """配置 ContextMind 日志系统。

    Args:
        level: 日志级别（DEBUG/INFO/WARNING/ERROR）
        python_log_level: Python 日志级别（默认基于 level 自动推导）
        save_to_file: 是否将日志保存到文件
        log_dir: 日志文件目录
    """
    set_global_log_level(level)

    if python_log_level is None:
        if level == LogLevel.DEBUG:
            python_log_level = logging.DEBUG
        elif level == LogLevel.WARNING:
            python_log_level = logging.WARNING
        elif level == LogLevel.ERROR:
            python_log_level = logging.ERROR
        else:
            python_log_level = logging.INFO

    handlers = []

    # 使用 UTF-8 编码的 stdout 流，确保中文等非 ASCII 字符在任何终端环境中都能正常显示，
    # 而非以 \uXXXX 形式输出。同时替换 sys.stdout，使 print() 与 logging 共享同一个
    # 行缓冲流，避免 verbose 模式下 print() 输出被块缓冲而不实时显示。
    if hasattr(sys.stdout, 'buffer'):
        utf8_stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True
        )
        sys.stdout = utf8_stdout
    else:
        utf8_stdout = sys.stdout
    console_handler = logging.StreamHandler(utf8_stdout)
    console_handler.setLevel(python_log_level)
    console_formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    handlers.append(console_handler)

    if save_to_file:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)

        log_filename = f"contextmind_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_filepath = log_path / log_filename

        file_handler = logging.FileHandler(log_filepath, encoding='utf-8')
        file_handler.setLevel(python_log_level)
        file_formatter = logging.Formatter(
            '[%(asctime)s] %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

        print(f"📝 日志将自动保存到: {log_filepath}")

    # force=True 确保即使根 logger 已被配置（如第三方库提前调用了 basicConfig），
    # 本次配置仍会生效并覆盖之前的设置。
    logging.basicConfig(
        level=python_log_level,
        format='[%(asctime)s] %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=handlers,
        force=True
    )


INFO = logging.INFO
DEBUG = logging.DEBUG
WARNING = logging.WARNING
ERROR = logging.ERROR


