"""
InputPreprocessor - 管道架构步骤1

输入预处理和标准化。
"""

import re
from contextmind.common.logger import get_logger

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
        logger.debug(f"[InputPreprocessor] === 开始预处理 ===")
        logger.debug(f"[InputPreprocessor] 输入: '{user_input}'")
        logger.debug(f"[InputPreprocessor] 输入长度: {len(user_input)} 字符")
        
        # 去除首尾空白
        processed = user_input.strip()
        
        # 验证长度
        if len(processed) < self.min_length:
            raise ValueError(f"输入过短 (最小 {self.min_length} 字符)")
        
        if len(processed) > self.max_length:
            raise ValueError(f"输入过长 (最大 {self.max_length} 字符)")
        
        # 移除多余空白
        processed = re.sub(r'\s+', ' ', processed)
        
        logger.debug(f"[InputPreprocessor] 输出: '{processed}'")
        logger.debug(f"[InputPreprocessor] 处理后长度: {len(processed)} 字符")
        logger.debug(f"[InputPreprocessor] === 预处理完成 ===")
        
        return processed
