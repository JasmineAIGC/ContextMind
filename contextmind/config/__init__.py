"""
ContextMind 配置管理模块

本模块负责处理:
- 场景注册表：管理场景定义及其相关组件
- 场景配置：从 YAML 文件加载和验证场景配置
"""

from contextmind.config.registry import scenario_registry

__all__ = ["scenario_registry"]
