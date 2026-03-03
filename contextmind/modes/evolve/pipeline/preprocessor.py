"""
InputPreprocessor - 管道架构步骤1

输入预处理和标准化。
"""

import re
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class InputPreprocessor:
    """
    输入预处理器，对用户输入进行标准化处理（去空白、验证、清洗）。

    先验证边界再规范化，确保下游组件拿到干净且长度可预期的字符串。
    """

    def __init__(
        self,
        min_length: int = 1,
        max_length: int = 10000,  # 约等于 ~7500 tokens，防止超出常见 LLM 上下文窗口
    ):
        self.min_length = min_length
        self.max_length = max_length

    async def process(self, user_input: str) -> str:
        """
        处理用户输入。

        Args:
            user_input: 原始输入

        Returns:
            处理后的输入

        Raises:
            ValueError: 输入无效
        """
        processed = user_input.strip()

        if len(processed) < self.min_length:
            raise ValueError(f"输入过短 (最小 {self.min_length} 字符)")

        if len(processed) > self.max_length:
            raise ValueError(f"输入过长 (最大 {self.max_length} 字符)")

        processed = re.sub(r'\s+', ' ', processed)  # 将换行、Tab、多余空格统一为单个空格

        logger.debug(f"[InputPreprocessor] 输出: '{processed}'")

        return processed
