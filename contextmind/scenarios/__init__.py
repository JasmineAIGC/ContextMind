"""
ContextMind 场景定义

每个场景提供：
  - ``get_<name>_scenario()`` — 返回 ScenarioConfig 配置对象
  - Application 类（实际均为 EvolveApplication 别名）

内置场景：chat（闲聊）/ callcenter（客服）/ insurance（保险）
扩展方式：在 scenarios.yaml 中添加新场景条目，无需修改此文件。
"""

from .base import ScenarioConfig, ScenarioType
from .registry import scenario_registry
from .app import EvolveApplication, ChatApplication, CallCenterApplication, InsuranceApplication
from .chat import get_chat_scenario
from .callcenter import get_callcenter_scenario
from .insurance import get_insurance_scenario

__all__ = [
    "ScenarioConfig",
    "ScenarioType",
    "scenario_registry",
    "EvolveApplication",
    "ChatApplication",
    "CallCenterApplication",
    "InsuranceApplication",
    "get_chat_scenario",
    "get_callcenter_scenario",
    "get_insurance_scenario",
]
