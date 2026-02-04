# 扩展新场景指南

本文档说明如何在 ContextMind 中添加新的对话场景，无需修改核心代码。

## 概述

ContextMind v0.2.1+ 使用 **场景注册表** 机制，允许您动态注册新场景。这消除了硬编码，使系统具有更好的通用性和可扩展性。

## 快速开始

### 1. 创建自定义应用类（Evolve模式）

```python
# custom_app.py
from apps.chat_app import ChatApplication  # 或继承基础Application

class CustomApplication(ChatApplication):
    """自定义场景应用"""
    
    def __init__(self, context_engine, system_prompt: str = ""):
        super().__init__(context_engine, system_prompt or "你是一个专业的助手")
    
    # 可以覆盖或添加自定义方法
    async def process_turn(self, user_input: str) -> str:
        # 自定义处理逻辑
        response = await super().process_turn(user_input)
        return response
```

### 2. 定义Schema（FnCTOD模式）

```python
# custom_schema.py
from fnctod.data_models import DomainSpec, FunctionParameter, ParameterType

def get_custom_function_schema() -> DomainSpec:
    """获取自定义场景的函数Schema"""
    schema = DomainSpec(
        name="custom",
        description="自定义场景的对话状态跟踪"
    )
    
    # 添加参数
    schema.add_parameter(FunctionParameter(
        name="intent",
        description="用户意图",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["咨询", "投诉", "建议"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="topic",
        description="话题",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema
```

### 3. 创建场景配置

```python
# scenarios/custom_scenario.py
from scenarios.scenario_config import ScenarioConfig

def get_custom_scenario() -> ScenarioConfig:
    """获取自定义场景配置"""
    return ScenarioConfig(
        name="custom",
        description="自定义场景",
        system_prompt="你是一个专业的自定义场景助手",
        
        # DST模式的slot定义
        dst_slots={
            "intent": "用户意图",
            "topic": "讨论话题",
            "user_name": "用户姓名",
        },
        
        # 可选：分类slot的取值范围
        dst_categorical_slots={
            "intent": ["咨询", "投诉", "建议"]
        },
        
        # 可选：启用动态slot
        enable_dynamic_slots=False
    )
```

### 4. 注册场景

有两种注册方式：

#### 方式A: 在代码中注册（推荐）

```python
# 在您的应用入口文件中
from scenario_registry import scenario_registry
from custom_app import CustomApplication
from custom_schema import get_custom_function_schema

# 注册场景
scenario_registry.register(
    name="custom",
    app_class=CustomApplication,
    schema_getter=get_custom_function_schema,
    aliases=["自定义", "custom-domain"],
    description="自定义场景"
)
```

#### 方式B: 创建注册模块

```python
# scenarios/register_custom.py
from scenario_registry import scenario_registry
from custom_app import CustomApplication
from custom_schema import get_custom_function_schema

def register_custom_scenario():
    """注册自定义场景"""
    scenario_registry.register(
        name="custom",
        app_class=CustomApplication,
        schema_getter=get_custom_function_schema,
        aliases=["自定义"],
        description="自定义场景"
    )

# 自动注册
register_custom_scenario()
```

然后在应用启动时导入：
```python
import scenarios.register_custom  # 自动注册
```

### 5. 使用新场景

注册后，新场景可以像内置场景一样使用：

```python
from scenarios import get_custom_scenario
from utils.llm_client import SimpleLLMClient

# 创建配置和客户端
config = get_custom_scenario()
llm_client = SimpleLLMClient(api_key="your-key")

# DST模式
from dst import DSTTracker
tracker = DSTTracker.from_scenario(llm_client, config)
result = await tracker.process_turn("你好")

# FnCTOD模式
from fnctod import FnCTODTracker
tracker = FnCTODTracker.from_scenario(llm_client, config)
result = await tracker.process_turn("你好")

# Evolve模式
from evolve import create_app_for_scenario
app = create_app_for_scenario("custom", llm_client, config)
response = await app.process_turn("你好")
```

## 高级用法

### 仅注册部分模式

如果您的场景只支持某些模式，可以只提供相应的组件：

```python
# 仅支持DST模式
scenario_registry.register(
    name="dst_only",
    app_class=None,  # 不支持Evolve
    schema_getter=None,  # 不支持FnCTOD
    description="仅DST场景"
)

# 仅支持Evolve模式
scenario_registry.register(
    name="evolve_only",
    app_class=CustomApp,
    schema_getter=None,  # 不支持FnCTOD
    description="仅Evolve场景"
)
```

### 动态添加别名

```python
scenario_registry.add_alias("custom", "自定义场景")
scenario_registry.add_alias("custom", "custom_v2")
```

### 查询场景信息

```python
from scenario_registry import scenario_registry

# 列出所有场景
scenarios = scenario_registry.list_scenarios()
print(f"可用场景: {scenarios}")

# 检查场景是否存在
if scenario_registry.is_registered("custom"):
    print("场景已注册")

# 获取场景详细信息
info = scenario_registry.get_scenario_info("custom")
print(f"场景信息: {info}")
```

### 注销场景

```python
scenario_registry.unregister("custom")
```

## 完整示例

### 示例1: 医疗咨询场景

```python
# medical_app.py
from apps.chat_app import ChatApplication

class MedicalApplication(ChatApplication):
    """医疗咨询应用"""
    
    def __init__(self, context_engine, system_prompt: str = ""):
        super().__init__(
            context_engine,
            system_prompt or "你是一个专业的医疗咨询助手，请提供准确的医疗建议。"
        )


# medical_schema.py
from fnctod.data_models import DomainSpec, FunctionParameter, ParameterType

def get_medical_function_schema() -> DomainSpec:
    schema = DomainSpec(
        name="medical",
        description="医疗咨询对话状态跟踪"
    )
    
    schema.add_parameter(FunctionParameter(
        name="symptom",
        description="症状描述",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="severity",
        description="严重程度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["轻微", "中等", "严重", "紧急"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="patient_age",
        description="患者年龄",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema


# scenarios/medical_scenario.py
from scenarios.scenario_config import ScenarioConfig

def get_medical_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="medical",
        description="医疗咨询场景",
        system_prompt="你是一个专业的医疗咨询助手",
        dst_slots={
            "symptom": "症状描述",
            "severity": "严重程度",
            "patient_age": "患者年龄",
            "medical_history": "既往病史",
        },
        dst_categorical_slots={
            "severity": ["轻微", "中等", "严重", "紧急"]
        }
    )


# 注册
from scenario_registry import scenario_registry
from medical_app import MedicalApplication
from medical_schema import get_medical_function_schema

scenario_registry.register(
    name="medical",
    app_class=MedicalApplication,
    schema_getter=get_medical_function_schema,
    aliases=["医疗", "医疗咨询"],
    description="医疗咨询场景"
)
```

### 示例2: 教育辅导场景

```python
# education_app.py
from apps.chat_app import ChatApplication

class EducationApplication(ChatApplication):
    """教育辅导应用"""
    pass


# education_schema.py
from fnctod.data_models import DomainSpec, FunctionParameter, ParameterType

def get_education_function_schema() -> DomainSpec:
    schema = DomainSpec(
        name="education",
        description="教育辅导对话状态跟踪"
    )
    
    schema.add_parameter(FunctionParameter(
        name="subject",
        description="学科",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["数学", "语文", "英语", "物理", "化学", "生物"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="grade",
        description="年级",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="difficulty",
        description="问题难度",
        param_type=ParameterType.STRING,
        required=False,
        enum_values=["简单", "中等", "困难"]
    ))
    
    return schema


# 注册
scenario_registry.register(
    name="education",
    app_class=EducationApplication,
    schema_getter=get_education_function_schema,
    aliases=["教育", "辅导"],
    description="教育辅导场景"
)
```

## 最佳实践

1. **命名规范**
   - 使用英文小写作为规范名称（如 "medical"）
   - 使用中文作为别名（如 "医疗"）
   - 避免使用特殊字符和空格

2. **模块组织**
   - 将应用类放在 `apps/` 目录
   - 将Schema定义放在 `fnctod/schemas/` 或独立模块
   - 将场景配置放在 `scenarios/` 目录

3. **注册时机**
   - 在应用启动早期注册场景
   - 可以创建专门的注册模块
   - 确保在使用前完成注册

4. **测试**
   - 为新场景编写单元测试
   - 测试所有三种模式（DST、FnCTOD、Evolve）
   - 验证别名功能正常

5. **文档**
   - 记录场景的用途和特点
   - 说明支持的参数和取值
   - 提供使用示例

## 迁移指南

### 从旧版本迁移

如果您有旧版本的硬编码场景，可以这样迁移：

**旧代码**（需要修改源码）:
```python
# evolve/__init__.py
if scenario_lower == "myapp":
    return MyApplication(...)
```

**新代码**（使用注册表）:
```python
# my_registration.py
from scenario_registry import scenario_registry
from my_app import MyApplication

scenario_registry.register(
    name="myapp",
    app_class=MyApplication,
    description="我的应用"
)
```

## 常见问题

### Q: 可以在运行时动态添加场景吗？
A: 可以！场景注册表支持运行时注册，但建议在应用启动时完成注册。

### Q: 场景名称有什么限制？
A: 场景名称建议使用英文小写字母和下划线，避免特殊字符。别名可以使用中文。

### Q: 如何处理场景冲突？
A: 如果注册同名场景，会覆盖旧的注册。系统会发出警告。

### Q: 可以禁用某个内置场景吗？
A: 可以使用 `scenario_registry.unregister("chat")` 注销场景。

### Q: 场景注册会影响性能吗？
A: 注册操作只在启动时执行一次，对运行时性能几乎没有影响。

## 参考

- [命名标准](naming-standards.md)
- [架构文档](architecture.md)
- [模式说明](modes.md)
- [ScenarioConfig 文档](../scenarios/README.md)
