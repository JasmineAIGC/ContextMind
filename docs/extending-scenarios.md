# 扩展新场景指南

本文档说明如何在 ContextMind 中添加新的对话场景，使用配置文件方式，无需修改核心代码。

## 概述

ContextMind v0.3.0+ 使用 **配置文件驱动** 的场景管理机制。所有场景定义在 `scenarios.yaml` 配置文件中，系统自动加载。

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

---

## 添加全新追踪模式

如果需要添加一种**全新的追踪算法**（而非仅增加场景），需要实现 `BaseTracker` 协议。

### 最小实现

```python
# contextmind/modes/my_mode/tracker.py
from typing import Any, Dict

class MyTracker:
    """
    自定义追踪器示例。
    结构上满足 contextmind.modes.base.BaseTracker 协议，
    无需显式继承。
    """

    def __init__(self, llm_client, **kwargs):
        self.llm_client = llm_client
        self._state: Dict[str, Any] = {}

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        """工厂方法：从场景配置创建实例（必须实现）。"""
        return cls(llm_client=llm_client, **kwargs)

    async def process_turn(self, user_utterance: str, **kwargs) -> Dict[str, Any]:
        """处理单轮对话，返回本轮更新的槽位（必须实现）。"""
        # 在此调用 LLM 并解析结果
        updates = {}
        self._state.update(updates)
        return updates

    def get_current_state(self) -> Dict[str, Any]:
        """返回累积的对话状态（必须实现）。"""
        return dict(self._state)

    def reset(self) -> None:
        """重置所有状态（必须实现）。"""
        self._state = {}
```

### 验证协议满足

```python
from contextmind.modes.base import BaseTracker

tracker = MyTracker(llm_client=None)  # None 仅用于协议验证，实际使用需传入 AdkLLMClient()
assert isinstance(tracker, BaseTracker), "未满足 BaseTracker 协议！"
print("✅ MyTracker 协议验证通过")
```

### 在示例中使用

由于所有追踪器共享相同接口，现有示例代码无需修改即可使用新追踪器：

```python
from contextmind.modes.base import BaseTracker
from my_module import MyTracker
from contextmind.scenarios import get_chat_scenario
from contextmind.infra.llm_client import AdkLLMClient

llm = AdkLLMClient()
config = get_chat_scenario()

# 工厂方法创建实例
tracker: BaseTracker = MyTracker.from_scenario(llm, config)

result = await tracker.process_turn("你好")
print(tracker.get_current_state())
```

---

**最后更新**: 2026-03-30 | **版本**: 0.3.0

#### 步骤1: 创建应用类（Evolve模式）

```python
