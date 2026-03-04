"""
ContextMind 配置管理模块

本模块负责处理:
- 场景注册表：从 scenarios.yaml 加载场景定义，管理场景查询接口

提示词（prompts）已移至 contextmind.scenarios.prompts。
"""

from contextmind.config.registry import scenario_registry

__all__ = ["scenario_registry"]
