"""
场景注册表 - 动态管理对话场景

提供可扩展的场景注册机制，消除硬编码，支持运行时动态添加场景。

用法示例：
    # 注册新场景
    from scenario_registry import scenario_registry
    
    scenario_registry.register(
        name="custom_domain",
        app_class=CustomApplication,
        schema_getter=get_custom_schema,
        aliases=["自定义", "custom"]
    )
    
    # 使用场景
    app_class = scenario_registry.get_app_class("custom_domain")
    schema = scenario_registry.get_schema("custom_domain")
"""

from typing import Dict, List, Optional, Callable, Type, Any
import warnings


class ScenarioRegistry:
    """
    场景注册表 - 集中管理所有对话场景
    
    功能：
    - 注册场景及其关联的应用类和Schema
    - 支持场景别名
    - 运行时动态添加/修改场景
    - 提供统一的查询接口
    """
    
    def __init__(self):
        """初始化空注册表"""
        # 主存储：name -> scenario_info
        self._scenarios: Dict[str, Dict[str, Any]] = {}
        # 别名映射：alias -> canonical_name
        self._aliases: Dict[str, str] = {}
    
    def register(
        self,
        name: str,
        app_class: Optional[Type] = None,
        schema_getter: Optional[Callable] = None,
        aliases: Optional[List[str]] = None,
        description: str = "",
        **kwargs
    ) -> None:
        """
        注册一个场景
        
        Args:
            name: 场景的规范名称（英文，小写）
            app_class: 应用类（Evolve模式使用）
            schema_getter: Schema获取函数（FnCTOD模式使用）
            aliases: 场景别名列表（支持中文名等）
            description: 场景描述
            **kwargs: 其他自定义属性
        
        Example:
            registry.register(
                name="chat",
                app_class=ChatApplication,
                schema_getter=get_chat_function_schema,
                aliases=["闲聊"],
                description="通用闲聊场景"
            )
        """
        # 规范化名称
        name = name.lower().strip()
        
        if name in self._scenarios:
            warnings.warn(f"场景 '{name}' 已存在，将被覆盖", UserWarning)
        
        # 存储场景信息
        self._scenarios[name] = {
            'name': name,
            'app_class': app_class,
            'schema_getter': schema_getter,
            'aliases': aliases or [],
            'description': description,
            **kwargs
        }
        
        # 注册别名
        if aliases:
            for alias in aliases:
                alias = alias.lower().strip()
                if alias in self._aliases and self._aliases[alias] != name:
                    warnings.warn(
                        f"别名 '{alias}' 已被场景 '{self._aliases[alias]}' 使用，将被覆盖为 '{name}'",
                        UserWarning
                    )
                self._aliases[alias] = name
    
    def add_alias(self, name: str, alias: str) -> None:
        """
        为已注册的场景添加别名
        
        Args:
            name: 场景名称
            alias: 新别名
        
        Raises:
            ValueError: 如果场景不存在
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            raise ValueError(f"场景 '{name}' 不存在，无法添加别名")
        
        alias = alias.lower().strip()
        self._aliases[alias] = canonical_name
        
        # 同时更新场景信息中的aliases列表
        if alias not in self._scenarios[canonical_name]['aliases']:
            self._scenarios[canonical_name]['aliases'].append(alias)
    
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
        """
        获取场景的应用类
        
        Args:
            name: 场景名称或别名
        
        Returns:
            应用类，如果不存在返回None
        
        Example:
            app_class = registry.get_app_class("chat")
            app = app_class(engine=engine, system_prompt=prompt)
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        
        return self._scenarios[canonical_name].get('app_class')
    
    def get_schema(self, name: str) -> Optional[Any]:
        """
        获取场景的Schema（调用schema_getter）
        
        Args:
            name: 场景名称或别名
        
        Returns:
            Schema对象，如果不存在返回None
        
        Example:
            schema = registry.get_schema("insurance")
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        
        schema_getter = self._scenarios[canonical_name].get('schema_getter')
        if schema_getter is None:
            return None
        
        # 调用getter函数获取schema
        return schema_getter()
    
    def get_schema_getter(self, name: str) -> Optional[Callable]:
        """
        获取场景的Schema获取函数
        
        Args:
            name: 场景名称或别名
        
        Returns:
            Schema获取函数，如果不存在返回None
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        
        return self._scenarios[canonical_name].get('schema_getter')
    
    def is_registered(self, name: str) -> bool:
        """
        检查场景是否已注册
        
        Args:
            name: 场景名称或别名
        
        Returns:
            True如果已注册，否则False
        """
        return self._resolve_name(name) is not None
    
    def list_scenarios(self) -> List[str]:
        """
        列出所有已注册的场景名称
        
        Returns:
            场景名称列表
        """
        return list(self._scenarios.keys())
    
    def get_scenario_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取场景的完整信息
        
        Args:
            name: 场景名称或别名
        
        Returns:
            场景信息字典，如果不存在返回None
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return None
        
        return self._scenarios[canonical_name].copy()
    
    def unregister(self, name: str) -> bool:
        """
        注销一个场景
        
        Args:
            name: 场景名称
        
        Returns:
            True如果成功注销，False如果场景不存在
        """
        canonical_name = self._resolve_name(name)
        if canonical_name is None:
            return False
        
        # 删除场景
        scenario_info = self._scenarios.pop(canonical_name)
        
        # 删除所有别名
        aliases_to_remove = [canonical_name]  # 规范名称也在别名中
        if 'aliases' in scenario_info:
            aliases_to_remove.extend(scenario_info['aliases'])
        
        for alias in aliases_to_remove:
            if alias in self._aliases:
                del self._aliases[alias]
        
        return True
    
    def clear(self) -> None:
        """清空注册表"""
        self._scenarios.clear()
        self._aliases.clear()


# 全局单例
scenario_registry = ScenarioRegistry()


def register_builtin_scenarios():
    """
    注册内置场景
    
    这个函数在模块导入时自动调用，注册所有内置场景。
    保持向后兼容性。
    """
    try:
        # 导入应用类
        from apps.chat_app import ChatApplication
        from apps.callcenter_app import CallCenterApplication
        from apps.insurance_app import InsuranceApplication
        
        # 导入Schema获取函数
        from fnctod.schemas import (
            get_chat_function_schema,
            get_callcenter_function_schema,
            get_insurance_function_schema
        )
        
        # 注册闲聊场景
        scenario_registry.register(
            name="chat",
            app_class=ChatApplication,
            schema_getter=get_chat_function_schema,
            aliases=["闲聊"],
            description="通用闲聊场景"
        )
        
        # 注册客服场景
        scenario_registry.register(
            name="callcenter",
            app_class=CallCenterApplication,
            schema_getter=get_callcenter_function_schema,
            aliases=["客服"],
            description="客服场景"
        )
        
        # 注册保险场景
        scenario_registry.register(
            name="insurance",
            app_class=InsuranceApplication,
            schema_getter=get_insurance_function_schema,
            aliases=["保险", "保险挽回"],
            description="保险挽回场景"
        )
        
    except ImportError as e:
        # 如果导入失败（比如在某些测试环境），忽略
        warnings.warn(f"无法注册内置场景: {e}", ImportWarning)


# 自动注册内置场景
register_builtin_scenarios()


__all__ = [
    'ScenarioRegistry',
    'scenario_registry',
    'register_builtin_scenarios',
]
