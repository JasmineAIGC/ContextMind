"""
InputPreprocessor - 输入预处理模块

职责：
- 输入清洗、验证
- 提示词优化
- 前置固定指令

可插拔策略：
- 基础清洗策略
- 提示工程策略
- 动态prompt模板
"""

import re
from typing import Optional
from ..models import get_logger

logger = get_logger(__name__)


class InputPreprocessor:
    """
    输入预处理器
    
    对用户输入进行标准化处理：
    - 去除多余空白
    - 验证有效性
    - 清洗特殊字符
    """
    
    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 10000,
    ):
        """
        初始化预处理器
        
        Args:
            min_length: 最小输入长度
            max_length: 最大输入长度
        """
        self.min_length = min_length
        self.max_length = max_length
    
    async def process(self, user_input: str) -> str:
        """
        处理用户输入
        
        Args:
            user_input: 原始输入
            
        Returns:
            处理后的输入
            
        Raises:
            ValueError: 输入无效
        """
        # 去除首尾空白
        processed = user_input.strip()
        
        # 验证长度
        if len(processed) < self.min_length:
            raise ValueError(f"Input too short (minimum {self.min_length} characters)")
        
        if len(processed) > self.max_length:
            raise ValueError(f"Input too long (maximum {self.max_length} characters)")
        
        # 移除多余空白
        processed = re.sub(r'\s+', ' ', processed)
        
        logger.debug(f"Preprocessed input: '{processed[:50]}...'")
        
        return processed
