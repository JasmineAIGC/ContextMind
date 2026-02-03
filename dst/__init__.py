"""
DST (对话状态追踪) 模式

v0.4.1 - 直接使用 ADK，专注于槽位提取和状态追踪自研逻辑。

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》的增强实现。

核心特点：
1. 完全不进行微调（Zero-shot）
2. 直接使用 ADK Agent 进行 LLM 调用
3. 累积式状态追踪（DS_t = update(DS_{t-1}, updates)）
4. 不使用记忆库（与 Evolution 的主要区别）

模块化组件：
- data_models: 数据模型（DialogueTurn, SpecialValue）
- prompt_manager: 提示词管理器（支持动态槽位）
- response_parser: 响应解析器（鲁棒JSON提取）
- dialogue_state_tracker: 主追踪器（智能历史管理）
- adk_agent: DST 专用 ADK Agent（直接使用 google.adk）

与 Evolution 的区别：
- Evolution: 复杂的五层架构，包含记忆库、检索、压缩等
- DST: 简单的状态追踪，但支持动态槽位和智能历史管理
"""

# 数据模型
from dst.data_models import DialogueTurn, SpecialValue

# 核心组件
from dst.prompt_manager import PromptManager, Language, LLMFormat
from dst.response_parser import ResponseParser
from dst.dialogue_state_tracker import DialogueStateTracker

# ADK Agent
from dst.adk_agent import DSTAgent

# 导入配置（向后兼容）
from utils.adk_config import QwenADKConfig as DSTConfig

__all__ = [
    'DialogueStateTracker',
    'PromptManager',
    'ResponseParser',
    'DialogueTurn',
    'SpecialValue',
    'Language',
    'LLMFormat',
    'DSTAgent',
    'DSTConfig',
]

__version__ = '0.4.1'
