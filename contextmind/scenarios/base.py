"""
场景配置基础类

定义场景配置的数据结构和接口
"""

from dataclasses import dataclass, field
from typing import Dict, List
from enum import Enum


class ScenarioType(Enum):
    """场景类型枚举。

    内置场景类型使用预定义枚举值；自定义业务场景使用
    ``ScenarioType.CUSTOM`` 并通过 ``ScenarioConfig.name`` 加以区分：

    .. code-block:: python

        config = ScenarioConfig(
            name="my_outbound",
            scenario_type=ScenarioType.CUSTOM,
            ...
        )
    """
    CHAT = "chat"           # 闲聊场景
    CALLCENTER = "callcenter"  # 客服场景
    INSURANCE = "insurance"    # 保险挽回场景
    CUSTOM = "custom"          # 自定义/扩展场景（通过 name 字段区分）


@dataclass
class ScenarioConfig:
    """
    场景配置类
    
    定义一个对话场景的所有配置信息
    """
    
    # 基础信息
    name: str  # 场景名称
    scenario_type: ScenarioType  # 场景类型
    description: str  # 场景描述
    
    # DST模式配置（预定义意图和槽位）
    dst_intents: Dict[str, List[str]]  # 一级意图 -> 二级意图列表
    dst_slots: Dict[str, str]  # 槽位名 -> 槽位描述
    dst_categorical_slots: Dict[str, List[str]] = field(default_factory=dict)  # 分类槽位
    enable_dynamic_slots: bool = True  # 是否启用动态槽位提取（False=使用预定义槽位）
    
    # 提示词配置
    system_prompt: str = ""  # 系统提示词
    dst_prompt_template: str = ""  # DST专用提示词模板
    
    # ContextMind模式配置
    enable_memory: bool = True  # 是否启用记忆功能
    enable_evolution: bool = True  # 是否启用演化功能
    
    # UI配置
    ui_title: str = ""  # UI标题
    ui_description: str = ""  # UI描述
    welcome_message: str = ""  # 欢迎消息
    
    # 其他配置
    max_history_turns: int = 10  # 最大历史轮数
    temperature: float = 0.7  # LLM温度参数
    
    def __post_init__(self):
        """初始化后处理"""
        if not self.ui_title:
            self.ui_title = f"{self.name}对话系统"
        if not self.ui_description:
            self.ui_description = self.description
