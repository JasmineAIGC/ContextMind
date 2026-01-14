"""
InputProcessor - 输入预处理器

对用户输入进行验证、清洗和标准化处理。
"""

import re
from ..logger import get_logger

logger = get_logger(__name__)


class InputProcessor:
    """
    输入预处理器
    
    对用户输入进行标准化处理，包括：
    - 去除多余空白
    - 验证输入有效性
    - 清洗特殊字符（可选）
    """
    
    def __init__(self, min_length: int = 1, max_length: int = 10000):
        """
        初始化输入处理器
        
        Args:
            min_length: 最小输入长度，默认为1
            max_length: 最大输入长度，默认为10000
        """
        self.min_length = min_length
        self.max_length = max_length
    
    async def process(self, user_input: str) -> str:
        """
        处理用户输入
        
        Args:
            user_input: 原始用户输入
            
        Returns:
            处理后的用户输入
            
        Raises:
            ValueError: 如果输入无效（太短或太长）
        """
        # 去除首尾空白
        processed = user_input.strip()
        
        # 验证长度
        if len(processed) < self.min_length:
            raise ValueError(f"Input too short (minimum {self.min_length} characters)")
        
        if len(processed) > self.max_length:
            raise ValueError(f"Input too long (maximum {self.max_length} characters)")
        
        # 移除多余的空白字符
        processed = re.sub(r'\s+', ' ', processed)
        
        logger.debug(f"Processed input: {processed[:100]}...")
        
        return processed
