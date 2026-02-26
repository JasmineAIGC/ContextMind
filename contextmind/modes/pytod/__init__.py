"""
PyTOD Schema 适配模块

将 PyTOD schema（service/intent/slot 格式）迁移到直接支持
zero/few-shot 大模型（如 Qwen-3）prompt 工程模式的适配模块。

无需依赖 PyTOD 官方代码，仅以 schema + prompt 驱动主流程。

**重要：** function / action / 意图 / 槽位**不需要预定义**。

本模块完整实现 PyTOD 算法的四步流程：

    用户输入
      ↓
    动作解析器（Action Parser）— build_action_parser_messages()
      → 生成程序语句（如：restaurants_1_find(city='San Jose')）
      ↓
    执行引擎（Execution Engine）— ExecutionEngine.execute()
      → 实际调用已注册的 API 函数 / 数据库查询
      → 返回执行结果（如：[{"name": "海底捞", "rating": 4.8}]）
      ↓
    对话管理器（Dialogue Manager）— build_dialogue_manager_messages()
      → 基于执行结果生成系统回复
      ↓
    系统输出

此外还支持两种简化运行模式：

1. **Schema 驱动模式**（传入 ``ServiceSchema``）
   - 将预定义的意图列表、槽位描述和枚举值注入 prompt
   - ``ActionValidator`` 根据 schema 校验意图合法性和枚举槽位值
   - 适合有明确业务场景的生产环境

2. **开放域模式**（``schema=None``，默认）
   - **无需预定义任何意图、action 或槽位**
   - LLM 根据对话上下文自由命名意图并提取任意信息槽位
   - ``ActionValidator`` 仅校验 JSON 结构，不约束内容
   - 适合快速原型开发或意图/槽位尚未确定的早期阶段

子模块:
    schema           - PyTOD schema 数据模型（Service/Intent/Slot）
    execution_engine - 执行引擎（安全解析并执行程序语句，对接 API/数据库）
    prompt_builder   - Prompt 组装工具（Action Parser / Dialogue Manager）
    validator        - 模型生成 action 的合法性校验与反馈解析
"""

from .schema import SlotDefinition, IntentDefinition, ServiceSchema, load_schema_from_dict
from .execution_engine import (
    ExecutionEngine,
    ProgramStatement,
    ExecutionResult,
    SlotAssignment,
    HintStatement,
    SayStatement,
    ProgramBlock,
    ProgramExecutionResult,
)
from .prompt_builder import PyTODPromptBuilder, ConversationTurn, FewShotExample
from .validator import ActionValidator, ValidationResult

__all__ = [
    "SlotDefinition",
    "IntentDefinition",
    "ServiceSchema",
    "load_schema_from_dict",
    "ExecutionEngine",
    "ProgramStatement",
    "ExecutionResult",
    "SlotAssignment",
    "HintStatement",
    "SayStatement",
    "ProgramBlock",
    "ProgramExecutionResult",
    "PyTODPromptBuilder",
    "ConversationTurn",
    "FewShotExample",
    "ActionValidator",
    "ValidationResult",
]
