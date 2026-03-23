"""
TransferTOD 数据集适配器包

将 TransferTOD 格式转换为标准化对话实例，支持 clean / noise 两种数据类型。
"""

from .adapter import TransferTODAdapter
from .utils import DomainIntentConfig, DomainIntentConfigLoader, load_domain_intent_config

__all__ = [
    # 主适配器
    "TransferTODAdapter",
    # 配置工具
    "DomainIntentConfig",
    "DomainIntentConfigLoader",
    "load_domain_intent_config",
]
