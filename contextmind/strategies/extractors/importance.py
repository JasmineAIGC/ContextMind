"""
重要性感知提取器
"""

from typing import List, Optional

from .base import BaseExtractor
from .rule import RuleBasedExtractor
from ...core.models import Message, ExtractionConfig, DEFAULT_MEMORY_CONFIG, get_logger
from ...core.types import Knowledge

logger = get_logger(__name__)


class ImportancePredictorExtractor(BaseExtractor):
    """
    重要性感知提取器（未来实现的占位符）
    
    使用训练好的模型预测提取信息的长期重要性
    在存储前过滤低价值记忆
    
    未来增强功能：
    - 用于重要性预测的微调 BERT 模型
    - 多因素评分（新近性、频率、用户参与度）
    - 基于记忆容量的自适应阈值
    """
    
    def __init__(
        self,
        model: Optional[any] = None,
        config: Optional[ExtractionConfig] = None
    ):
        """
        初始化重要性预测提取器
        
        Args:
            model: 训练好的重要性预测模型
            config: 提取配置
        """
        self.model = model
        self.config = config or DEFAULT_MEMORY_CONFIG.extraction
        logger.info("[ImportancePredictorExtractor] 已初始化（占位符实现）")
    
    async def extract(self, messages: List[Message]) -> List[Knowledge]:
        """
        使用重要性预测提取知识
        
        当前实现是占位符，会回退到基于规则的提取
        
        未来待做事项：
        - 训练/加载重要性预测模型
        - 为每个提取项评分长期价值
        - 基于预测的重要性阈值进行过滤
        
        Args:
            messages: 对话消息列表
            
        Returns:
            提取的知识（当前使用回退方案）
        """
        logger.debug("[ImportancePredictorExtractor] 使用回退到 RuleBasedExtractor（尚未实现）")
        
        # 目前回退到基于规则的提取
        fallback = RuleBasedExtractor(self.config)
        knowledge = await fallback.extract(messages)
        
        # 未来：在此处添加重要性预测评分
        # 这将涉及：
        # 1. 加载/初始化重要性预测模型
        # 2. 根据预测的长期价值为每个知识项评分
        # 3. 过滤低于重要性阈值的项
        # 示例实现（当模型可用时）：
        #   for item in knowledge:
        #       importance_score = self._predict_importance(item)
        #       item.confidence *= importance_score
        
        return knowledge
    
    def _predict_importance(self, knowledge: Knowledge) -> float:
        """
        预测知识项的重要性分数（占位符）
        
        此方法将使用训练好的模型来预测此知识对未来对话的重要性
        
        Args:
            knowledge: 要评分的知识项
            
        Returns:
            重要性分数（0-1）
        """
        # TODO: 当模型可用时实现
        # 实现步骤：
        # 1. 提取知识的特征（类型、内容长度、置信度等）
        # 2. 使用训练好的模型预测长期价值
        # 3. 返回 0-1 之间的重要性分数
        # 当前返回默认值（占位符实现）
        logger.warning("[ImportancePredictorExtractor] 使用占位符实现，返回默认重要性分数 1.0")
        return 1.0
