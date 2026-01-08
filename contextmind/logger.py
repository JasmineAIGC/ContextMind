"""
ContextMind 统一日志配置模块

提供简单易用的日志配置和获取logger的方法，确保所有模块使用一致的日志格式和输出。
"""

import logging
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# 导出 logging 常量，方便其他模块使用
DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL





class ContextMindLogger:
    """ContextMind 统一日志管理器"""
    
    _initialized = False
    _log_file: Optional[Path] = None
    _current_level = logging.INFO
    
    @classmethod
    def setup_logging(
        cls,
        level: int = INFO,
        log_file: Optional[str] = None,
        log_to_console: bool = True,
        auto_create_file: bool = True
    ) -> None:
        """
        设置统一的日志配置
        
        Args:
            level: 日志级别 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            log_file: 日志文件路径（可选，如果为None则自动生成）
            log_to_console: 是否输出到控制台
            auto_create_file: 是否自动创建日志文件
        """
        cls._current_level = level
        
        # 自动生成日志文件名
        if log_file is None and auto_create_file:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_file = f"contextmind_{timestamp}.log"
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        # 清除现有的handlers
        root_logger.handlers.clear()
        
        # 设置日志格式 - 简化格式，不再使用EngineFormatter
        log_format = '%(message)s'
        formatter = logging.Formatter(fmt=log_format)

        # 过滤掉第三方库的冗余日志
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        
        # 完全禁用 asyncio 的 DEBUG 日志
        logging.getLogger('asyncio').setLevel(logging.WARNING)
        
        # 添加控制台handler
        if log_to_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            root_logger.addHandler(console_handler)
        
        # 添加文件handler
        if log_file:
            log_path = Path(log_file)
            if not log_path.is_absolute():
                # 相对路径，放在logs目录下
                log_path = Path("logs") / log_path
            
            # 自动创建目录
            log_path.parent.mkdir(parents=True, exist_ok=True)
            cls._log_file = log_path
            
            file_handler = logging.FileHandler(log_path, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
            
            print(f"📝 日志文件: {log_path.absolute()}")
        
        cls._initialized = True
        print(f"✅ 日志系统初始化完成 (级别: {logging.getLevelName(level)})")
    
    @classmethod
    def get_logger(cls, name: str) -> logging.Logger:
        """
        获取指定名称的logger
        
        Args:
            name: logger名称，通常使用 __name__
        
        Returns:
            logging.Logger实例
        """
        if not cls._initialized:
            cls.setup_logging()
        
        return logging.getLogger(name)
    
    @classmethod
    def debug_mode(cls, enabled: bool = True) -> None:
        """
        切换debug模式
        
        Args:
            enabled: 是否启用debug模式
        """
        new_level = DEBUG if enabled else INFO
        cls.set_level(new_level)
        mode = "DEBUG" if enabled else "INFO"
        print(f"🔧 日志模式切换为: {mode}")
    
    @classmethod
    def set_level(cls, level: int) -> None:
        """
        动态设置日志级别
        
        Args:
            level: 日志级别
        """
        cls._current_level = level
        logging.getLogger().setLevel(level)
        for handler in logging.getLogger().handlers:
            handler.setLevel(level)
    
    @classmethod
    def get_current_level(cls) -> int:
        """获取当前日志级别"""
        return cls._current_level
    
    @classmethod
    def get_log_file(cls) -> Optional[Path]:
        """获取当前日志文件路径"""
        return cls._log_file


# 便捷函数
def get_logger(name: str) -> logging.Logger:
    """获取logger的便捷函数"""
    return ContextMindLogger.get_logger(name)


def setup_logging(
    level: int = INFO,
    log_file: Optional[str] = None,
    log_to_console: bool = True,
    auto_create_file: bool = True
) -> None:
    """设置日志配置的便捷函数"""
    ContextMindLogger.setup_logging(level, log_file, log_to_console, auto_create_file)


def enable_debug_mode(enabled: bool = True) -> None:
    """启用/禁用debug模式的便捷函数"""
    ContextMindLogger.debug_mode(enabled)


def log_info(msg: str, engine_type: str = 'default') -> None:
    """记录INFO级别日志的便捷函数"""
    logger = get_logger(__name__)
    logger.info(msg, extra={'engine_type': engine_type})


def log_debug(msg: str, engine_type: str = 'default') -> None:
    """记录DEBUG级别日志的便捷函数"""
    logger = get_logger(__name__)
    logger.debug(msg, extra={'engine_type': engine_type})


def log_warning(msg: str, engine_type: str = 'default') -> None:
    """记录WARNING级别日志的便捷函数"""
    logger = get_logger(__name__)
    logger.warning(msg, extra={'engine_type': engine_type})


def log_error(msg: str, engine_type: str = 'default') -> None:
    """记录ERROR级别日志的便捷函数"""
    logger = get_logger(__name__)
    logger.error(msg, extra={'engine_type': engine_type})
