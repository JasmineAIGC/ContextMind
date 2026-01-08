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


class EngineFormatter(logging.Formatter):
    """为不同引擎添加标识的格式化器"""

    ENGINE_COLORS = {
        'basic': '\033[94m',      # 蓝色
        'short_term': '\033[93m', # 黄色
        'long_term': '\033[92m',  # 绿色
        'default': '\033[0m'      # 默认
    }
    
    ENGINE_SYMBOLS = {
        'basic': '🔵',
        'short_term': '🟡',
        'long_term': '🟢',
        'default': '📝'
    }
    
    LEVEL_SYMBOLS = {
        logging.INFO: '📋',
        logging.DEBUG: '🔍',
        logging.WARNING: '⚠️',
        logging.ERROR: '❌',
        logging.CRITICAL: '💥'
    }
    
    RESET = '\033[0m'

    def format(self, record):
        # 从record中获取引擎类型
        engine_type = getattr(record, 'engine_type', 'default')
        symbol = self.ENGINE_SYMBOLS.get(engine_type, self.ENGINE_SYMBOLS['default'])
        level_symbol = self.LEVEL_SYMBOLS.get(record.levelno, '')
        
        # 添加引擎标识到日志消息
        original_msg = record.msg
        
        # 对不同级别的日志应用不同的格式化策略
        if record.levelno == logging.INFO:
            # INFO级别为主日志，使用更明显的格式和间隔
            if '开始处理用户输入' in original_msg:
                # 对话开始时使用更长的分隔线，突出显示
                record.msg = f"\n{'='*80}\n{level_symbol} {symbol} [{engine_type.upper()}] {original_msg}\n{'='*80}"
            elif '机器人输出' in original_msg:
                # 对话结束时同样使用长分隔线
                record.msg = f"{level_symbol} {symbol} [{engine_type.upper()}] {original_msg}\n{'='*80}\n"
            elif original_msg.strip() == '='*40 or original_msg.strip() == '='*80:
                # 如果是分隔线，保持原样
                record.msg = f"{original_msg}"
            else:
                # 普通INFO日志，使用标准格式并添加空行
                record.msg = f"\n{level_symbol} {symbol} [{engine_type.upper()}] {original_msg}"
        elif record.levelno == logging.DEBUG:
            # DEBUG级别为次日志，使用缩进区分
            if any(keyword in original_msg for keyword in ['生成的prompt:', '当前对话历史', '检索到的记忆', '成功提取知识', '重要事实详情', '关键事件']):
                # 重要的DEBUG信息，使用较少缩进
                record.msg = f"\n  {level_symbol} {symbol} [{engine_type.upper()}] {original_msg}"
            else:
                # 普通DEBUG信息，使用更多缩进
                record.msg = f"    {level_symbol} {symbol} [{engine_type.upper()}] {original_msg}"
        else:
            # WARNING、ERROR、CRITICAL级别，使用醒目的格式
            record.msg = f"\n{level_symbol} {symbol} [{engine_type.upper()}] {original_msg}"
        
        # 格式化
        result = super().format(record)
        
        # 恢复原始消息
        record.msg = original_msg
        
        return result


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
        
        # 设置日志格式
        log_format = '%(asctime)s - %(levelname)-8s - %(name)-15s - %(message)s'
        formatter = EngineFormatter(fmt=log_format, datefmt='%Y-%m-%d %H:%M:%S')

        # 过滤掉第三方库的冗余日志
        logging.getLogger('httpx').setLevel(logging.WARNING)
        logging.getLogger('httpcore').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)
        logging.getLogger('openai').setLevel(logging.WARNING)
        
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
