"""
场景注册表 - 基于配置文件的场景管理

从 scenarios.yaml 配置文件加载场景定义，提供简单的查询接口。

用法示例：
    # 查询场景
    from scenario_registry import scenario_registry
    
    app_class = scenario_registry.get_app_class("chat")
    schema = scenario_registry.get_schema("insurance")
    
    # 添加新场景：只需在 scenarios.yaml 中添加配置
"""

import os
import yaml
import importlib
from typing import Dict, Optional, Callable, Type, Any
from pathlib import Path


class ScenarioRegistry:
    """
    场景注册表 - 从YAML配置文件加载场景
    
    简化设计：
    - 从 scenarios.yaml 自动加载所有场景
    - 支持场景别名
    - 提供简单的查询接口
    """
    
    def __init__(self, config_file: str = "scenarios.yaml"):
        """
        初始化注册表并从配置文件加载场景
        
        Args:
            config_file: 配置文件路径（相对于项目根目录）
        """
        self._scenarios: Dict[str, Dict[str, Any]] = {}
        self._aliases: Dict[str, str] = {}
        self._config_file = config_file
        
        # 加载配置
        self._load_from_config()
    
    def _load_from_config(self) -> None:
        """从YAML配置文件加载场景定义"""
        # 获取配置文件路径（相对于当前文件）
        current_dir = Path(__file__).parent
        config_path = current_dir / self._config_file
        
        if not config_path.exists():
            # 如果配置文件不存在，使用内置场景（向后兼容）
            self._load_builtin_scenarios()
            return
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if not config or 'scenarios' not in config:
                self._load_builtin_scenarios()
                return
            
            # 加载每个场景
            for scenario_name, scenario_config in config['scenarios'].items():
                self._load_scenario(scenario_name, scenario_config)
                
        except Exception as e:
            # 加载失败时降级到内置场景
            print(f"警告: 无法加载配置文件 {config_path}: {e}")
            self._load_builtin_scenarios()
    
    def _load_scenario(self, name: str, config: Dict[str, Any]) -> None:
        """
        加载单个场景配置
        
        Args:
            name: 场景名称
            config: 场景配置字典
        """
        # 动态导入应用类
        app_class = None
        if 'app_class' in config:
            app_class = self._import_class(config['app_class'])
        
        # 动态导入Schema获取函数
        schema_getter = None
        if 'schema_getter' in config:
            schema_getter = self._import_callable(config['schema_getter'])
        
        # 存储场景信息
        self._scenarios[name] = {
            'name': name,
            'app_class': app_class,
            'schema_getter': schema_getter,
            'aliases': config.get('aliases', []),
            'description': config.get('description', ''),
        }
        
        # 注册别名
        for alias in config.get('aliases', []):
            self._aliases[alias.lower().strip()] = name
    
    def _import_class(self, class_path: str) -> Optional[Type]:
        """
        动态导入类
        
        Args:
            class_path: 完整的类路径，如 "apps.chat_app.ChatApplication"
        
        Returns:
            导入的类，失败返回None
        """
        try:
            module_path, class_name = class_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, class_name)
        except Exception as e:
            print(f"警告: 无法导入类 {class_path}: {e}")
            return None
    
    def _import_callable(self, callable_path: str) -> Optional[Callable]:
        """
        动态导入函数
        
        Args:
            callable_path: 完整的函数路径，如 "fnctod.schemas.get_chat_function_schema"
        
        Returns:
            导入的函数，失败返回None
        """
        try:
            module_path, func_name = callable_path.rsplit('.', 1)
            module = importlib.import_module(module_path)
            return getattr(module, func_name)
        except Exception as e:
            print(f"警告: 无法导入函数 {callable_path}: {e}")
            return None
    
    def _load_builtin_scenarios(self) -> None:
        """降级方案：直接加载内置场景（向后兼容）"""
        try:
            from apps.chat_app import ChatApplication
            from apps.callcenter_app import CallCenterApplication
            from apps.insurance_app import InsuranceApplication
            from fnctod.schemas import (
                get_chat_function_schema,
                get_callcenter_function_schema,
                get_insurance_function_schema
            )
            
            # 手动注册内置场景
            builtin_scenarios = {
                'chat': {
                    'name': 'chat',
                    'app_class': ChatApplication,
                    'schema_getter': get_chat_function_schema,
                    'aliases': ['闲聊'],
                    'description': '通用闲聊场景'
                },
                'callcenter': {
                    'name': 'callcenter',
                    'app_class': CallCenterApplication,
                    'schema_getter': get_callcenter_function_schema,
                    'aliases': ['客服'],
                    'description': '客服场景'
                },
                'insurance': {
                    'name': 'insurance',
                    'app_class': InsuranceApplication,
                    'schema_getter': get_insurance_function_schema,
                    'aliases': ['保险', '保险挽回'],
                    'description': '保险挽回场景'
                }
            }
            
            self._scenarios = builtin_scenarios
            for name, info in builtin_scenarios.items():
                for alias in info['aliases']:
                    self._aliases[alias.lower()] = name
                    
        except ImportError:
            pass
    
    def _resolve_name(self, name: str) -> Optional[str]:
        """
        解析场景名称（处理别名）
        
        Args:
            name: 场景名称或别名
        
        Returns:
            规范名称，如果不存在返回None
        """
        name = name.lower().strip()
        
        # 直接匹配
        if name in self._scenarios:
            return name
        
        # 别名匹配
        if name in self._aliases:
            return self._aliases[name]
        
        return None
    
    def get_app_class(self, name: str) -> Optional[Type]:
        """获取场景的应用类（Evolve模式使用）"""
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        return self._scenarios[canonical_name].get('app_class')
    
    def get_schema(self, name: str) -> Optional[Any]:
        """获取场景的Schema（FnCTOD模式使用）"""
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        
        schema_getter = self._scenarios[canonical_name].get('schema_getter')
        if schema_getter is None:
            return None
        
        return schema_getter()
    
    def list_scenarios(self) -> list:
        """列出所有已注册的场景名称"""
        return list(self._scenarios.keys())
    
    def is_registered(self, name: str) -> bool:
        """检查场景是否已注册"""
        return self._resolve_name(name) is not None


# 全局单例
scenario_registry = ScenarioRegistry()


__all__ = [
    'ScenarioRegistry',
    'scenario_registry',
]
