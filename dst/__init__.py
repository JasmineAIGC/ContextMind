"""
Baseline DST Module - 基础版本（基于 ACL 2023 DST）

基于 ACL 2023 论文《ChatGPT for Zero-shot Dialogue State Tracking》的增强实现。

v0.2.1 新特性：
1. 模块化架构 - 拆分为4个独立模块，便于维护
2. 动态槽位提取 - LLM自由提取任何相关信息，不限制槽位类型
3. 智能历史管理 - 自动摘要长对话，保持上下文简洁
4. 多意图追踪 - 追踪意图切换和演变
5. 改进意图识别 - 更准确的意图分类
6. 工厂方法 - from_scenario() 简化创建流程

核心特点：
1. 完全不进行微调（Zero-shot）
2. 完全基于LLM（无规则方法）
3. 累积式状态追踪（DS_t = update(DS_{t-1}, updates)）
4. 不使用记忆库（与 Evolve 模式的主要区别）

模块化组件：
- data_models: 数据模型（DialogueTurn, SpecialValue）
- prompt_manager: 提示词管理器（支持动态槽位）
- response_parser: 响应解析器（鲁棒JSON提取）
- dialogue_state_tracker: 主追踪器（智能历史管理 + 工厂方法）

与 Evolve 模式的区别：
- Evolve: 复杂的五层架构，包含记忆库、检索、压缩等
- DST: 简单的状态追踪，但支持动态槽位和智能历史管理

使用示例：
    # 方式1: 使用工厂方法（推荐）
    from dst import DialogueStateTracker
    tracker = DialogueStateTracker.from_scenario(llm_client, scenario_config)
    
    # 方式2: 手动创建
    from dst import DialogueStateTracker, PromptManager
    pm = PromptManager(domain="chat")
    tracker = DialogueStateTracker(llm_client=llm_client, prompt_manager=pm)
"""

# 数据模型
from dst.data_models import DialogueTurn, SpecialValue

# 核心组件
from dst.prompt_manager import PromptManager, Language, LLMFormat
from dst.response_parser import ResponseParser
from dst.dialogue_state_tracker import DialogueStateTracker

# 别名 - 统一命名风格（推荐使用简短名称）
DSTTracker = DialogueStateTracker

__all__ = [
    'DialogueStateTracker',
    'DSTTracker',  # 推荐使用的简短别名
    'PromptManager',
    'ResponseParser',
    'DialogueTurn',
    'SpecialValue',
    'Language',
    'LLMFormat',
]

__version__ = '0.2.1'
