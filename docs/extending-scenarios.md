# 扩展新场景指南

本文档说明如何在 ContextMind 中添加新的对话场景，使用配置文件方式，无需修改核心代码。

## 概述

ContextMind v0.2.1+ 使用 **配置文件驱动** 的场景管理机制。所有场景定义在 `scenarios.yaml` 配置文件中，系统自动加载。

## 快速开始

### 添加新场景只需3步

#### 步骤1: 创建应用类（Evolve模式）

```python
# apps/medical_app.py
from apps.chat_app import ChatApplication

class MedicalApplication(ChatApplication):
    """医疗咨询场景应用"""
    
    def __init__(self, context_engine, system_prompt: str = ""):
        super().__init__(
            context_engine, 
            system_prompt or "你是一个专业的医疗咨询助手"
        )
```

#### 步骤2: 定义Schema（FnCTOD模式）

```python
# fnctod/schemas.py（在文件中添加）
def get_medical_function_schema() -> DomainSpec:
    """获取医疗场景的函数Schema"""
    schema = DomainSpec(name="medical", description="医疗咨询")
    
    schema.add_parameter(FunctionParameter(
        name="symptom",
        description="症状描述",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="duration",
        description="持续时间",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema
```

#### 步骤3: 在配置文件中注册

编辑 `scenarios.yaml` 文件，添加新场景：

```yaml
scenarios:
  # ... 现有场景 ...
  
  # 新增医疗场景
  medical:
    name: medical
    description: 医疗咨询场景
    aliases:
      - 医疗
      - 医疗咨询
    app_class: apps.medical_app.MedicalApplication
    schema_getter: fnctod.schemas.get_medical_function_schema
```

**完成！** 重启应用后，新场景立即可用。

## 配置文件详解

### scenarios.yaml 结构

```yaml
scenarios:
  场景名称:
    name: 场景名称           # 必填，唯一标识符（小写英文）
    description: 场景描述    # 必填，场景说明
    aliases:                # 可选，别名列表
      - 中文名1
      - 中文名2
    app_class: 完整类路径   # 必填，Evolve模式的应用类
    schema_getter: 完整函数路径  # 必填，FnCTOD模式的Schema函数
```

### 配置示例

```yaml
scenarios:
  # 示例1: 教育场景
  education:
    name: education
    description: 在线教育辅导场景
    aliases:
      - 教育
      - 辅导
      - 学习
    app_class: apps.education_app.EducationApplication
    schema_getter: fnctod.schemas.get_education_function_schema
  
  # 示例2: 法律咨询
  legal:
    name: legal
    description: 法律咨询场景
    aliases:
      - 法律
      - 律师
    app_class: apps.legal_app.LegalApplication
    schema_getter: fnctod.schemas.get_legal_function_schema
```

## 创建场景配置（DST模式）

虽然DST模式不需要在 `scenarios.yaml` 中配置，但您需要创建场景配置文件：

```python
# scenarios/medical_scenario.py
from scenarios.config import ScenarioConfig, ScenarioType

def get_medical_scenario() -> ScenarioConfig:
    """获取医疗场景配置"""
    return ScenarioConfig(
        name="medical",
        scenario_type=ScenarioType.CHAT,  # 复用现有类型
        description="医疗咨询场景",
        system_prompt="你是一个专业的医疗咨询助手",
        
        # DST模式的slot定义
        dst_intents={
            "咨询": ["症状咨询", "用药咨询", "检查咨询"],
            "预约": ["挂号", "检查预约"],
            "其他": ["闲聊", "投诉"]
        },
        
        dst_slots={
            "intent_level1": "一级意图",
            "intent_level2": "二级意图",
            "symptom": "症状描述",
            "duration": "持续时间",
            "patient_name": "患者姓名",
        },
        
        dst_categorical_slots={
            "intent_level1": ["咨询", "预约", "其他"]
        }
    )
```

## 使用新场景

添加配置后，新场景自动可用：

```python
# 使用Evolve模式
from evolve import create_app_for_scenario
app = create_app_for_scenario("medical", llm_client, config)

# 使用FnCTOD模式
from fnctod import FnCTODTracker
tracker = FnCTODTracker.from_scenario(llm_client, config)

# 使用DST模式
from dst import DSTTracker
tracker = DSTTracker.from_scenario(llm_client, config)
```

### 命令行使用

```bash
# 交互式Demo
python interactive_demo.py --scenario medical --mode dst
python interactive_demo.py --scenario medical --mode fnctod
python interactive_demo.py --scenario medical --mode evolve

# Gradio Web界面
python gradio_demo.py
# 在界面中选择 "medical" 或 "医疗" 场景
```

## 完整示例：添加"技术支持"场景

### 1. 创建应用类

```python
# apps/tech_support_app.py
from apps.callcenter_app import CallCenterApplication

class TechSupportApplication(CallCenterApplication):
    """技术支持场景"""
    
    def __init__(self, context_engine, system_prompt: str = ""):
        super().__init__(
            context_engine,
            system_prompt or "你是一个专业的技术支持工程师"
        )
```

### 2. 定义Schema

```python
# 在 fnctod/schemas.py 中添加
def get_tech_support_function_schema() -> DomainSpec:
    """技术支持Schema"""
    schema = DomainSpec(name="tech_support", description="技术支持")
    
    schema.add_parameter(FunctionParameter(
        name="issue_type",
        description="问题类型",
        param_type=ParameterType.STRING,
        required=True,
        enum_values=["软件问题", "硬件问题", "网络问题", "其他"]
    ))
    
    schema.add_parameter(FunctionParameter(
        name="product",
        description="产品名称",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    schema.add_parameter(FunctionParameter(
        name="error_message",
        description="错误信息",
        param_type=ParameterType.STRING,
        required=False
    ))
    
    return schema
```

### 3. 更新配置文件

```yaml
# scenarios.yaml
scenarios:
  # ... 现有场景 ...
  
  tech_support:
    name: tech_support
    description: 技术支持场景
    aliases:
      - 技术支持
      - tech
      - support
    app_class: apps.tech_support_app.TechSupportApplication
    schema_getter: fnctod.schemas.get_tech_support_function_schema
```

### 4. 创建场景配置

```python
# scenarios/tech_support_scenario.py
from scenarios.config import ScenarioConfig, ScenarioType

def get_tech_support_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        name="tech_support",
        scenario_type=ScenarioType.CALLCENTER,
        description="技术支持场景",
        system_prompt="你是一个专业的技术支持工程师",
        
        dst_intents={
            "故障报告": ["软件故障", "硬件故障", "网络故障"],
            "使用咨询": ["功能咨询", "操作指导"],
            "投诉": ["服务投诉", "产品投诉"]
        },
        
        dst_slots={
            "intent_level1": "一级意图",
            "issue_type": "问题类型",
            "product": "产品名称",
            "error_message": "错误信息",
            "customer_name": "客户姓名",
        }
    )
```

### 5. 重启应用

```bash
# 重启后立即可用
python interactive_demo.py --scenario tech_support --mode evolve
```

## 配置文件优势

相比之前的代码注册方式，使用配置文件具有以下优势：

### Before（代码注册）
```python
# 需要在Python代码中注册
from scenario_registry import scenario_registry

scenario_registry.register(
    name="medical",
    app_class=MedicalApp,
    schema_getter=get_medical_schema,
    aliases=["医疗"]
)
```

### After（配置文件）
```yaml
# 只需在YAML中添加
scenarios:
  medical:
    name: medical
    aliases: [医疗]
    app_class: apps.medical_app.MedicalApp
    schema_getter: fnctod.schemas.get_medical_schema
```

### 优势对比

| 特性 | 代码注册 | 配置文件 |
|------|---------|---------|
| 易于理解 | 需要理解Python | YAML更直观 |
| 修改成本 | 需要修改代码 | 只改配置文件 |
| 代码行数 | 354行 | 约150行 |
| 维护性 | 中等 | 高 |
| 配置集中 | 分散 | 集中在yaml |

## 最佳实践

### 1. 命名规范

- **场景名称**: 使用小写英文，如 `medical`, `tech_support`
- **别名**: 可以使用中文或其他语言
- **类路径**: 使用完整的模块路径，如 `apps.medical_app.MedicalApplication`

### 2. 目录组织

```
ContextMind/
├── scenarios.yaml          # 场景配置文件
├── apps/                   # 应用类
│   ├── medical_app.py
│   └── tech_support_app.py
├── fnctod/
│   └── schemas.py          # Schema定义
└── scenarios/              # 场景配置
    ├── medical_scenario.py
    └── tech_support_scenario.py
```

### 3. 测试新场景

添加场景后，建议进行测试：

```bash
# 1. 验证配置加载
python -c "from scenario_registry import scenario_registry; print(scenario_registry.list_scenarios())"

# 2. 测试各模式
python interactive_demo.py --scenario your_scenario --mode dst
python interactive_demo.py --scenario your_scenario --mode fnctod
python interactive_demo.py --scenario your_scenario --mode evolve
```

## 故障排查

### 配置文件未生效

1. 检查 `scenarios.yaml` 文件是否在项目根目录
2. 检查YAML语法是否正确（使用YAML验证器）
3. 检查缩进是否使用空格（不要用Tab）

### 类或函数找不到

1. 检查模块路径是否正确
2. 确保相关文件已创建
3. 检查导入路径是否完整

### 别名不工作

1. 确保别名在 `aliases` 列表中
2. 别名会自动转为小写，注意大小写
3. 检查是否有重复的别名

## 总结

使用配置文件添加新场景的流程：

1. ✅ 创建应用类（apps/）
2. ✅ 定义Schema（fnctod/schemas.py）
3. ✅ 在 scenarios.yaml 中注册
4. ✅ 创建场景配置（scenarios/）
5. ✅ 重启应用

**零核心代码修改，完全配置驱动！**
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
