"""
PyTOD Schema 适配模块

将 PyTOD schema（service/intent/slot 格式）迁移到直接支持
zero/few-shot 大模型（如 Qwen-3）prompt 工程模式的适配模块。

无需依赖 PyTOD 官方代码，仅以 schema + prompt 驱动主流程。

子模块:
    schema       - PyTOD schema 数据模型（Service/Intent/Slot）
    prompt_builder - Prompt 组装工具
    validator    - 模型生成 action 的合法性校验与反馈解析
"""

from .schema import SlotDefinition, IntentDefinition, ServiceSchema, load_schema_from_dict
from .prompt_builder import PyTODPromptBuilder, ConversationTurn, FewShotExample
from .validator import ActionValidator, ValidationResult

__all__ = [
    "SlotDefinition",
    "IntentDefinition",
    "ServiceSchema",
    "load_schema_from_dict",
    "PyTODPromptBuilder",
    "ConversationTurn",
    "FewShotExample",
    "ActionValidator",
    "ValidationResult",
]
