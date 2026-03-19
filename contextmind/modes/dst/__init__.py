"""
Baseline DST Module - 基础版本（基于 ACL 2023 DST）

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》的增强实现。

核心特点：
1. 完全不进行微调（Zero-shot）
2. 完全基于LLM（无规则方法）
3. 累积式状态追踪（DS_t = update(DS_{t-1}, updates)）
4. 不使用记忆库（与 Evolve 模式的主要区别）

模块组成：
- tracker.py  : 主追踪器 + 数据模型（DialogueTurn、SpecialValue）
- prompts.py  : 提示词管理器（支持动态槽位）
- parser.py   : 响应解析器（鲁棒JSON提取）

使用示例：
    from contextmind.modes.dst import DialogueStateTracker
    tracker = DialogueStateTracker.from_scenario(llm_client, scenario_config)
"""

# 数据模型 + 主追踪器（合并在 tracker.py）
from .tracker import DialogueStateTracker, DSTTracker, DialogueTurn, SpecialValue

# 核心组件
from .prompts import PromptManager, Language, LLMFormat
from .parser import DSTResponseParser, ResponseParser

__all__ = [
    'DialogueStateTracker',
    'DSTTracker',
    'PromptManager',
    'ResponseParser',
    'DSTResponseParser',
    'DialogueTurn',
    'SpecialValue',
    'Language',
    'LLMFormat',
]

__version__ = '0.2.1'
