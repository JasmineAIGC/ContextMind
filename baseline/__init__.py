"""
Baseline DST Module - 基础版本（基于 ACL 2023 DST）

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》的增强实现。

v7.4.0 新特性：
1. 模块化架构 - 拆分为4个独立模块，便于维护
2. 动态槽位提取 - LLM自由提取任何相关信息，不限制槽位类型
3. 智能历史管理 - 自动摘要长对话，保持上下文简洁
4. 多意图追踪 - 追踪意图切换和演变
5. 改进意图识别 - 更准确的意图分类

核心特点：
1. 完全不进行微调（Zero-shot）
2. 完全基于LLM（无规则方法）
3. 累积式状态追踪（DS_t = update(DS_{t-1}, updates)）
4. 不使用记忆库（与 ContextMind 的主要区别）

模块化组件：
- data_models: 数据模型（DialogueTurn, SpecialValue）
- prompt_manager: 提示词管理器（支持动态槽位）
- response_parser: 响应解析器（鲁棒JSON提取）
- dialogue_state_tracker: 主追踪器（智能历史管理）

与 ContextMind 的区别：
- ContextMind: 复杂的五层架构，包含记忆库、检索、压缩等
- Baseline DST: 简单的状态追踪，但支持动态槽位和智能历史管理
"""

# 数据模型
from baseline.data_models import DialogueTurn, SpecialValue

# 核心组件
from baseline.prompt_manager import PromptManager, Language, LLMFormat
from baseline.response_parser import ResponseParser
from baseline.dialogue_state_tracker import DialogueStateTracker

__all__ = [
    'DialogueStateTracker',
    'PromptManager',
    'ResponseParser',
    'DialogueTurn',
    'SpecialValue',
    'Language',
    'LLMFormat',
]

__version__ = '7.4.0'
