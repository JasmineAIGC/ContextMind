"""
InputPreprocessor - Step 1 of Pipeline Architecture

Input preprocessing and normalization.
"""

import re
from ..utils.logger import get_logger

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
            raise ValueError(f"输入过短 (最小 {self.min_length} 字符)")
        
        if len(processed) > self.max_length:
            raise ValueError(f"输入过长 (最大 {self.max_length} 字符)")
        
        # 移除多余空白
        processed = re.sub(r'\s+', ' ', processed)
        
        logger.debug(f"预处理输入: '{processed[:50]}...'")
        
        return processed
