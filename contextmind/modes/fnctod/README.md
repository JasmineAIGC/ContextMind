# FnCTOD模式（任务型对话的函数调用）

## 概述

FnCTOD（Function Calling for Task-Oriented Dialogue，任务型对话的函数调用）是一种基于Function Calling机制的对话处理模式。它利用LLM的函数调用能力，让LLM直接生成结构化的函数调用，实现更灵活和智能的对话处理。

## 核心原理

FnCTOD模式的核心思想是**将对话理解转化为函数调用**：

1. **函数定义**：为每个场景定义可调用的函数及其参数Schema
2. **智能调用**：LLM根据用户输入判断应该调用哪个函数，传入什么参数
3. **累积状态**：每次调用都包含之前所有参数，实现状态累积
4. **自然回复**：函数调用后，LLM生成自然语言响应

FnCTOD支持两种模式：
- **两阶段模式**：先选择Domain，再进行函数调用
- **单阶段模式**：直接进行函数调用（适合单domain场景）

## ⚠️ 重要：函数预定义要求

### FnCTOD 是否需要预定义函数（域-槽位信息）？

**答案：是的，必须预定义。**

FnCTOD模式要求在使用前预定义好以下信息：

1. **Domain（领域）定义**：每个领域作为一个函数
2. **Slot（槽位）定义**：每个槽位作为函数的参数
3. **参数类型和约束**：类型、是否必需、可选值等

这是因为：
- LLM需要知道可以调用哪些函数
- LLM需要知道每个函数接受什么参数
- 系统需要验证LLM生成的函数调用是否合法

### 三种预定义方式

#### 1. 使用内置预定义Schema（最简单）

系统内置了三个场景的Schema：

```python
from contextmind.modes.fnctod import (
    get_chat_function_schema,          # 闲聊场景
    get_callcenter_function_schema,    # 客服场景
    get_insurance_function_schema      # 保险场景
)

# 直接使用内置Schema
chat_schema = get_chat_function_schema()
print(f"Domain: {chat_schema.name}")
print(f"参数数量: {len(chat_schema.parameters)}")
```

#### 2. 动态创建Schema（灵活）

从现有的槽位定义动态创建：

```python
from contextmind.modes.fnctod import FunctionManager, DomainSpec, FunctionParameter, ParameterType

# 方式A: 使用 add_domain_from_slots 方法
function_manager = FunctionManager()
function_manager.add_domain_from_slots(
    domain_name="酒店",
    domain_description="酒店预订场景",
    slots={
        "hotel_name": "酒店名称",
        "check_in_date": "入住日期",
        "check_out_date": "退房日期",
        "room_type": "房间类型",
        "guest_count": "入住人数"
    },
    categorical_slots={
        "room_type": ["单人间", "双人间", "套房", "豪华套房"]
    },
    required_slots=["hotel_name", "check_in_date"]
)

# 方式B: 手动构建 DomainSpec
hotel_schema = DomainSpec(
    name="酒店",
    description="酒店预订场景"
)

hotel_schema.add_parameter(FunctionParameter(
    name="hotel_name",
    description="酒店名称",
    param_type=ParameterType.STRING,
    required=True
))

hotel_schema.add_parameter(FunctionParameter(
    name="room_type",
    description="房间类型",
    param_type=ParameterType.STRING,
    required=False,
    enum_values=["单人间", "双人间", "套房", "豪华套房"]
))

function_manager.add_domain(hotel_schema)
```

#### 3. 从外部数据源转换（适合集成）

从TransferTOD或其他数据集转换：

```python
def create_domain_from_external_schema(domain: str, external_schema: Dict) -> DomainSpec:
    """从外部schema创建DomainSpec"""
    domain_spec = DomainSpec(
        name=domain,
        description=external_schema.get("description", f"{domain}领域对话")
    )
    
    # 转换槽位定义
    for slot_name, slot_info in external_schema["slots"].items():
        param = FunctionParameter(
            name=slot_name,
            description=slot_info.get("description", slot_name),
            param_type=ParameterType.STRING,
            required=slot_info.get("required", False)
        )
        domain_spec.add_parameter(param)
    
    return domain_spec
```

### 为什么必须预定义？

与传统的开放式对话不同，任务型对话具有明确的结构：

| 对比项 | 开放式对话 | 任务型对话（FnCTOD） |
|--------|-----------|---------------------|
| 槽位 | 不确定 | 预定义明确 |
| 输出格式 | 自由文本 | 结构化JSON |
| 验证 | 无需验证 | 需要Schema验证 |
| LLM理解 | 语义理解 | 结构化填充 |

预定义的好处：
- ✅ **准确性**：LLM知道确切的参数名称和类型
- ✅ **一致性**：所有对话使用相同的槽位定义
- ✅ **可验证**：可以检查输出是否符合规范
- ✅ **可维护**：集中管理槽位定义，易于更新

### 预定义的灵活性

虽然需要预定义，但系统提供了足够的灵活性：

1. **槽位可选性**：可以标记槽位为必需或可选
2. **类型多样性**：支持string、number、boolean、array、object
3. **枚举约束**：可以限定槽位的可选值
4. **动态添加**：运行时可以添加新的domain
5. **场景切换**：可以根据需要切换不同的Schema

```python
# 示例：动态添加新domain
function_manager.add_domain_from_slots(
    domain_name="新场景",
    domain_description="新添加的场景",
    slots={"slot1": "描述1", "slot2": "描述2"}
)
```

## 架构设计

FnCTOD模式由以下核心组件构成：

### 1. FnCTODTracker

主追踪器，负责整体流程：
- 管理对话历史
- 选择处理模式（两阶段/单阶段）
- 调用LLM生成函数调用
- 维护累积状态

### 2. FunctionManager

函数管理器，负责函数相关操作：
- 加载函数Schema定义
- 验证函数调用
- 管理函数参数

### 3. ResponseParser

响应解析器，负责解析LLM输出：
- 提取function call标签
- 解析函数名和参数
- 提取自然语言回复
- 支持宽松模式匹配

### 4. Schema系统

场景Schema定义（from scenarios.yaml）：
- 函数名称和描述
- 参数定义（类型、描述、是否必需）
- 示例调用

## 计算流程

### FnCTOD论文流程（重要：顺序不可颠倒）

根据Meta AI的FnCTOD论文（ACL 2024），正确的处理顺序是：

**核心原则**：**提示词构建 → LLM调用 → 响应解析**

这个顺序是固定的，不能颠倒。提示词必须在LLM调用之前完全构建好。

### 两阶段模式流程（参考论文Fig.2）

#### Stage 1: Domain Selection（域选择）

1. **步骤1：构建提示词**（在LLM调用之前）
   - 包含所有可用domain的简要描述
   - 不包含详细的函数规格
   - 添加对话历史和当前用户输入

2. **步骤2：调用LLM**（在提示词构建之后）
   - 模型根据完整提示词选择相关domain
   - 输出格式：`<domain>domain_name</domain>`

3. **步骤3：解析响应**（在LLM调用之后）
   - 提取选中的domain名称

#### Stage 2: Function Calling（函数调用）

1. **步骤1：构建提示词**（在LLM调用之前）
   - 只包含Stage 1选中的domain规格
   - 包含完整的函数定义和参数说明（JSON schema格式）
   - 添加few-shot示例（开源模型需要，参考论文Fig.3）
   - 添加对话历史和累积状态
   - 添加当前用户输入

2. **步骤2：调用LLM**（在提示词构建之后）
   - 模型根据完整提示词填充槽位参数
   - 输出格式：`<function_call name="domain">{"param": "value"}</function_call> 自然语言回复`

3. **步骤3：解析响应**（在LLM调用之后）
   - 提取 `<function_call>` 标签内的JSON参数
   - 提取标签后的自然语言回复
   - 更新累积状态

### 单阶段模式流程（优化）

当只有一个domain或场景已知时，跳过域选择，直接进行函数调用：

1. **步骤1：构建提示词**（在LLM调用之前）
   - 包含已知domain的完整规格
   - 包含few-shot示例
   - 添加对话历史和当前用户输入

2. **步骤2：调用LLM**（在提示词构建之后）
   - 直接填充参数并生成回复

3. **步骤3：解析响应**（在LLM调用之后）
   - 提取function call + 自然语言回复

**性能优势**：相比两阶段模式，节省1次LLM调用，响应时间减少约30%。

### 流程图

```
用户输入
    ↓
1. 历史准备
   准备对话历史
    ↓
[两阶段模式]             [单阶段模式]
    ↓                        ↓
2a. 构建提示词(domain)    2b. 构建提示词(完整)
    ↓                        ↓
3. 域选择(LLM调用)         (跳过)
    ↓                        ↓
4. 构建提示词(完整)        3. 函数调用(LLM调用)
    ↓                        ↓
5. 函数调用(LLM调用)       4. 响应解析
    ↓                        ↓
6. 响应解析               5. 状态更新
    ↓                        ↓
7. 状态更新               输出结果
    ↓
输出结果
```

### 详细步骤说明

#### 步骤1：历史准备
- 获取对话历史
- 格式化为上下文
- 典型耗时：~0.01s

#### 步骤2：提示词构建（关键步骤）
- 加载fnctod_prompts.yaml中的模板
- 插入函数Schema定义
- 添加few-shot示例（参考论文Fig.3、Fig.4）
- 构建完整的system prompt和对话历史
- **重要**：必须在LLM调用之前完成
- 典型耗时：~0.05s

#### 步骤3：LLM调用（在提示词构建之后）
- 发送完整提示词给LLM
- 根据模式不同：
  - 两阶段：先调用域选择，再调用函数填充
  - 单阶段：直接调用函数填充
- 典型耗时：~0.5-1.5s（取决于LLM）
- 返回domain名称
- 典型耗时：~0.5-1s

#### 步骤4：函数调用
- LLM生成`<function_call>`标签
- 包含函数名和JSON参数
- 包含自然语言响应
- 典型耗时：~1-1.5s

#### 步骤5：响应解析
- 使用正则表达式提取function call
- 解析JSON参数
- 提取自然语言部分
- 典型耗时：~0.03s

#### 步骤6：状态更新
- 合并新参数到累积状态
- 更新对话历史
- 典型耗时：~0.02s

## 提示词系统

FnCTOD使用YAML配置文件`fnctod_prompts.yaml`管理提示词：

### 系统提示词

```yaml
system_prompt: |
  你是一个具有函数调用能力的任务型对话助手。
  使用提供的函数来追踪对话状态并生成适当的响应。
```

### 输出格式要求

```yaml
output_format:
  importance_note: |
    重要要求：你必须始终为每个用户输入输出一个函数调用。
    不要只用自然语言回复 - 你必须包含 <function_call> 标签。
```

### 示例模板

提供单轮和多轮示例，引导LLM正确输出格式。

## 数据模型

### FunctionCall

```python
@dataclass
class FunctionCall:
    """函数调用"""
    name: str                     # 函数名
    arguments: Dict[str, Any]     # 参数字典
    raw_response: str             # 原始LLM响应
```

### FnCTODState

```python
@dataclass
class FnCTODState:
    """FnCTOD状态"""
    function_calls: List[FunctionCall]  # 历史函数调用
    cumulative_params: Dict[str, Any]   # 累积参数
    current_domain: str = None          # 当前domain
```

## 使用示例

### 基础用法（单阶段模式）

```python
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_insurance_scenario

# 初始化
llm_client = SimpleLLMClient()
scenario = get_insurance_scenario()
tracker = FnCTODTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=scenario,
    mode='single_stage'  # 单阶段模式
)

# 处理对话
user_input = "我想了解重疾险"
result = tracker.process_turn(user_input)

print(f"函数调用：{result.function_call.name}")
print(f"参数：{result.function_call.arguments}")
print(f"回复：{result.reply}")
# 输出：
# 函数调用：insurance
# 参数：{'intent_level1': '咨询', 'insurance_type': '重疾险'}
# 回复：好的，我来为您介绍重疾险...
```

### 两阶段模式

```python
tracker = FnCTODTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=scenario,
    mode='two_stage'  # 两阶段模式
)

# 第一轮会先选择domain，然后调用函数
result = tracker.process_turn("我的订单有问题")
```

### 查看步骤耗时

```python
print(f"步骤耗时：{tracker.step_timings}")
# 输出：
# {
#   '历史准备': 0.01,
#   '提示词构建': 0.05,
#   '领域选择': 0.52,  # 仅两阶段模式
#   '函数调用': 1.15,
#   '响应解析': 0.03,
#   '状态更新': 0.02
# }
```

### 完整示例：从零开始定义和使用

```python
from contextmind.modes.fnctod import (
    FnCTODTracker, 
    FunctionManager, 
    DomainSpec, 
    FunctionParameter,
    ParameterType
)
from contextmind.infra.llm_client import SimpleLLMClient

# 步骤1: 定义函数Schema（预定义域-槽位信息）
hotel_schema = DomainSpec(
    name="hotel_booking",
    description="酒店预订场景，处理酒店查询和预订相关的对话"
)

# 添加必需参数
hotel_schema.add_parameter(FunctionParameter(
    name="hotel_name",
    description="酒店名称",
    param_type=ParameterType.STRING,
    required=True  # 必需参数
))

hotel_schema.add_parameter(FunctionParameter(
    name="check_in_date",
    description="入住日期，格式：YYYY-MM-DD",
    param_type=ParameterType.STRING,
    required=True
))

# 添加可选参数
hotel_schema.add_parameter(FunctionParameter(
    name="check_out_date",
    description="退房日期，格式：YYYY-MM-DD",
    param_type=ParameterType.STRING,
    required=False
))

hotel_schema.add_parameter(FunctionParameter(
    name="room_type",
    description="房间类型",
    param_type=ParameterType.STRING,
    required=False,
    enum_values=["标准间", "大床房", "套房", "豪华套房"]  # 限定可选值
))

hotel_schema.add_parameter(FunctionParameter(
    name="guest_count",
    description="入住人数",
    param_type=ParameterType.NUMBER,
    required=False,
    default=1
))

# 步骤2: 创建FunctionManager并注册函数
function_manager = FunctionManager()
function_manager.add_domain(hotel_schema)

# 步骤3: 初始化FnCTODTracker
llm_client = SimpleLLMClient()
tracker = FnCTODTracker(
    llm_client=llm_client,
    function_manager=function_manager,
    use_two_stage=False,  # 单domain场景使用单阶段
    max_history_turns=10
)

# 步骤4: 处理对话
async def run_dialogue():
    # 第一轮
    result1 = await tracker.process_turn("我想预订明天的酒店")
    print(f"轮次1 - 函数调用: {result1['function_call'].function_name}")
    print(f"轮次1 - 参数: {result1['function_call'].arguments}")
    print(f"轮次1 - 回复: {result1['reply']}\n")
    
    # 第二轮（累积状态）
    result2 = await tracker.process_turn("华盛顿酒店，要一间大床房")
    print(f"轮次2 - 函数调用: {result2['function_call'].function_name}")
    print(f"轮次2 - 参数: {result2['function_call'].arguments}")
    print(f"轮次2 - 当前完整状态: {result2['state']}")
    print(f"轮次2 - 回复: {result2['reply']}\n")
    
    # 第三轮（继续填充）
    result3 = await tracker.process_turn("两个人住")
    print(f"轮次3 - 参数: {result3['function_call'].arguments}")
    print(f"轮次3 - 最终状态: {result3['state']}")

# 运行
import asyncio
asyncio.run(run_dialogue())

# 预期输出：
# 轮次1 - 函数调用: hotel_booking
# 轮次1 - 参数: {'check_in_date': '2026-02-11'}
# 轮次1 - 回复: 好的，您想预订明天（2026-02-11）的酒店...
#
# 轮次2 - 函数调用: hotel_booking
# 轮次2 - 参数: {'check_in_date': '2026-02-11', 'hotel_name': '华盛顿酒店', 'room_type': '大床房'}
# 轮次2 - 当前完整状态: {'check_in_date': '2026-02-11', 'hotel_name': '华盛顿酒店', 'room_type': '大床房'}
# 轮次2 - 回复: 华盛顿酒店的大床房，明天入住...
#
# 轮次3 - 参数: {'check_in_date': '2026-02-11', 'hotel_name': '华盛顿酒店', 'room_type': '大床房', 'guest_count': 2}
# 轮次3 - 最终状态: {'check_in_date': '2026-02-11', 'hotel_name': '华盛顿酒店', 'room_type': '大床房', 'guest_count': 2}
```

### 简化方式：使用 add_domain_from_slots

```python
from contextmind.modes.fnctod import FunctionManager, FnCTODTracker
from contextmind.infra.llm_client import SimpleLLMClient

# 更简洁的方式定义Schema
function_manager = FunctionManager()

function_manager.add_domain_from_slots(
    domain_name="restaurant",
    domain_description="餐厅预订场景",
    slots={
        "restaurant_name": "餐厅名称",
        "reservation_date": "预订日期",
        "reservation_time": "预订时间",
        "party_size": "就餐人数",
        "special_requests": "特殊要求（如过敏、座位偏好等）"
    },
    categorical_slots={
        "meal_type": ["早餐", "午餐", "晚餐", "下午茶"]
    },
    required_slots=["restaurant_name", "reservation_date", "reservation_time"]
)

# 初始化tracker
llm_client = SimpleLLMClient()
tracker = FnCTODTracker(
    llm_client=llm_client,
    function_manager=function_manager,
    use_two_stage=False
)

# 使用
result = await tracker.process_turn("我想订明晚7点的海底捞，4个人")
print(result['state'])
# 输出: {'restaurant_name': '海底捞', 'reservation_date': '2026-02-11', 
#        'reservation_time': '19:00', 'party_size': 4}
```
#   '状态更新': 0.02
# }
```

## Function Call格式

### 标准格式

```xml
<function_call name="function_name">
{"param1": "value1", "param2": "value2"}
</function_call>
自然语言响应
```

### 示例

```xml
<function_call name="insurance">
{"intent_level1": "咨询", "customer_name": "张三", "insurance_type": "重疾险"}
</function_call>
好的，张三先生，我来为您介绍重疾险产品。
```

## 性能特点

### 优势

1. **灵活智能**：LLM自主判断调用逻辑，适应复杂场景
2. **结构化**：输出标准化的函数调用，易于后续处理
3. **自然交互**：同时生成自然语言，用户体验好
4. **可扩展**：通过Schema定义轻松添加新功能

### 适用场景

- ✅ 复杂任务型对话（多意图、多参数）
- ✅ 需要调用外部API的场景
- ✅ 需要结构化输出的场景
- ✅ 希望利用LLM智能性的场景

### 对比DST模式

| 特性 | DST | FnCTOD |
|------|-----|--------|
| 提取方式 | 槽位填充 | 函数调用 |
| 灵活性 | 较低 | 高 |
| LLM要求 | 较低 | 较高（需支持function calling） |
| 输出格式 | JSON | Function Call + 自然语言 |
| 适用场景 | 简单任务 | 复杂任务 |

### 局限性

- ❌ 对LLM要求较高（需要好的指令遵循能力）
- ❌ 提示词工程复杂度较高
- ❌ 解析可能失败（如果LLM不遵循格式）

## 配置和扩展

### 自定义Schema

在scenarios.yaml中定义：

```yaml
scenarios:
  my_scenario:
    name: "我的场景"
    schema_getter: "path.to.get_my_schema"
```

Schema定义示例：

```python
def get_my_schema():
    return {
        "name": "my_function",
        "description": "我的函数描述",
        "parameters": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "参数1描述"
                }
            },
            "required": ["param1"]
        }
    }
```

### 自定义提示词

修改`fnctod_prompts.yaml`中的模板，或在初始化时传入自定义提示词。

## 调试技巧

### 启用DEBUG日志

```bash
python examples/web_demo.py --log-level DEBUG
```

### 查看LLM响应

```python
# 在DEBUG模式下，会记录：
# - LLM原始响应
# - 解析过程
# - 提取的函数调用
# - 参数详情
```

### 常见问题

1. **未检测到function call标签**
   - 检查LLM是否支持指令遵循
   - 尝试使用更强的模型
   - 检查提示词是否清晰

2. **参数解析失败**
   - 查看LLM返回的JSON格式
   - 检查Schema定义是否正确
   - 使用DEBUG日志查看详细错误

## 总结

FnCTOD模式是利用LLM函数调用能力的先进对话处理方案。它结合了结构化输出和自然语言生成，在灵活性和智能性之间取得了良好平衡，特别适合复杂的任务型对话场景。
