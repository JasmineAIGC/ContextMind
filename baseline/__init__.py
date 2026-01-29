"""
Baseline DST Module - 基础版本（基于 ACL 2023 DST）

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》的实现。

这是一个 Zero-shot 的对话状态追踪方案，作为 ContextMind 的基础版本对比。

核心特点：
1. 完全不进行微调（Zero-shot）
2. 仅通过精心设计的 Prompt 和 ChatGPT 的对话上下文能力
3. 累积式状态追踪（DS_t = update(DS_{t-1}, updates)）
4. 不使用记忆库（与 ContextMind 的主要区别）

主要组件：
- DialogueStateTracker: 对话状态追踪器
- PromptManager: 提示词管理器
- ResponseParser: 响应解析器
- DialogueTurn: 对话轮次数据结构

与 ContextMind 的区别：
- ContextMind: 复杂的五层架构，包含记忆库、检索、压缩等
- Baseline DST: 简单的状态追踪，不使用记忆库，作为 baseline
"""

from .dialogue_state_tracker import (
    DialogueStateTracker,
    PromptManager,
    ResponseParser,
    DialogueTurn
)

__all__ = [
    'DialogueStateTracker',
    'PromptManager',
    'ResponseParser',
    'DialogueTurn',
]

__version__ = '1.0.0'  # DST 基础版本
