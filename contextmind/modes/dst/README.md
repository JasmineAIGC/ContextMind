# DST模式（对话状态追踪）

## 概述

DST（Dialogue State Tracking，对话状态追踪）是一种基于槽位填充的对话管理模式。它通过追踪对话过程中的关键信息（槽位），逐步构建完整的对话状态，从而实现精准的任务型对话管理。

## 核心原理

DST模式的核心思想是**槽位提取和状态累积**：

1. **槽位定义**：预先定义任务所需的所有信息槽位（如客服场景中的"客户姓名"、"问题类型"等）
2. **渐进式提取**：在每轮对话中，从用户输入中提取新的槽位值
3. **状态累积**：将新提取的槽位与历史状态合并，形成累积的对话状态
4. **值归一化**：对提取的槽位值进行标准化处理（如"李四"、"小李"统一为规范形式）

## 架构设计

DST模式由以下核心组件构成：

### 1. DialogueStateTracker

主追踪器，负责整体流程协调，同时包含 `DialogueTurn` 和 `SpecialValue` 数据模型：
- 管理对话历史
- 调用LLM进行槽位提取
- 维护累积对话状态
- 记录步骤耗时

### 2. PromptManager

提示词管理器，负责构建LLM输入：
- 格式化对话历史
- 构建槽位提取提示词
- 包含槽位定义和示例

### 3. ResponseParser

响应解析器，负责解析LLM输出：
- 解析JSON格式的槽位值
- 值归一化处理
- 错误处理和降级

## 计算流程

DST模式的处理流程包含以下步骤：

```
用户输入
    ↓
1. 历史准备
   准备对话历史上下文
    ↓
2. 提示词构建
   构建包含槽位定义的LLM提示词
    ↓
3. LLM槽位提取
   调用LLM提取槽位信息
    ↓
4. 响应解析
   解析JSON响应并归一化值
    ↓
5. 状态更新
   将新槽位合并到累积状态
    ↓
对话状态输出
```

### 详细步骤说明

#### 步骤1：历史准备
- 获取最近N轮对话历史
- 格式化为LLM可理解的格式
- 典型耗时：~0.01s

#### 步骤2：提示词构建
- 包含系统提示词（槽位定义）
- 包含对话历史
- 包含当前用户输入
- 典型耗时：~0.01s

#### 步骤3：LLM槽位提取
- 发送提示词给LLM
- LLM分析并提取槽位
- 返回JSON格式结果
- 典型耗时：~1-2s（占总时间90%+）

#### 步骤4：响应解析
- 解析JSON字符串
- 提取每个槽位的值
- 对值进行归一化处理
- 典型耗时：~0.03s

#### 步骤5：状态更新
- 将新槽位与历史状态合并
- 更新值（新值覆盖旧值）
- 生成完整的对话状态
- 典型耗时：~0.02s

## 数据模型

### SlotValue

```python
@dataclass
class SlotValue:
    """槽位值"""
    value: Any                    # 原始值
    normalized_value: Any = None  # 归一化后的值
    confidence: float = 1.0       # 置信度
```

### DialogueState

```python
@dataclass  
class DialogueState:
    """对话状态"""
    slots: Dict[str, SlotValue]   # 槽位字典
    turn_number: int              # 当前轮次
    updated_at: datetime          # 更新时间
```

## 使用示例

### 基础用法

```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_callcenter_scenario

# 初始化
llm_client = SimpleLLMClient()
scenario = get_callcenter_scenario()
tracker = DialogueStateTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=scenario
)

# 处理对话
user_input = "我的订单有问题"
state = tracker.process_turn(user_input)

print(f"提取的槽位：{state.slots}")
# 输出：{'intent_level1': SlotValue(value='投诉'), 'issue_type': SlotValue(value='订单问题')}

# 下一轮
user_input = "订单号是12345"
state = tracker.process_turn(user_input)

print(f"累积状态：{state.slots}")
# 输出：{'intent_level1': ..., 'issue_type': ..., 'order_number': SlotValue(value='12345')}
```

### 查看步骤耗时

```python
# 处理后查看详细耗时
print(f"步骤耗时：{tracker.step_timings}")
# 输出：
# {
#   '历史准备': 0.01,
#   '提示词构建': 0.02,
#   'LLM槽位提取': 1.23,
#   '响应解析': 0.03,
#   '状态更新': 0.02
# }
```

## 性能特点

### 优势

1. **精准提取**：利用LLM的理解能力，准确提取结构化信息
2. **渐进式**：支持多轮对话，逐步完善状态
3. **可扩展**：易于添加新的槽位类型
4. **鲁棒性**：包含值归一化和错误处理

### 适用场景

- ✅ 任务型对话（订单查询、预订、客服等）
- ✅ 需要收集多个信息的场景
- ✅ 信息可结构化为槽位的场景
- ✅ 对话状态需要持久化的场景

### 局限性

- ❌ 开放域闲聊（槽位无法覆盖）
- ❌ 非结构化信息提取
- ❌ 实时性要求极高的场景（LLM调用有延迟）

## 配置和扩展

### 自定义槽位

在场景配置中定义：

```python
from contextmind.scenarios.config import ScenarioConfig

config = ScenarioConfig(
    name="custom_scenario",
    slots={
        "customer_name": "客户姓名",
        "product_type": "产品类型",
        "quantity": "数量"
    },
    # ...
)
```

### 自定义归一化

可以在ResponseParser中实现自定义归一化逻辑：

```python
def normalize_value(self, slot_name: str, value: Any) -> Any:
    """自定义归一化逻辑"""
    if slot_name == "customer_name":
        # 姓名标准化
        return value.strip().title()
    elif slot_name == "quantity":
        # 数量转整数
        return int(value)
    return value
```

## 总结

DST模式是任务型对话系统的经典方案，通过槽位提取和状态累积实现精准的对话管理。它简单直观，易于理解和扩展，适合大多数结构化的任务型对话场景。
