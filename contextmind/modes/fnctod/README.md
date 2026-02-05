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
