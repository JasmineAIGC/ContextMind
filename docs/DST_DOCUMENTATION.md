# 对话状态追踪 (Dialogue State Tracking) 文档

## 概述

基于 **ACL 2023 论文** 《ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?》的实现。

本实现采用 **Zero-shot** 方式，完全不进行微调，仅通过精心设计的 Prompt 和 ChatGPT 的对话上下文能力来完成对话状态追踪（DST）。

## 核心组件

### 1. PromptManager (提示词管理器)

负责构建论文附录中定义的复杂 Prompt。

**主要功能：**
- 定义槽位本体 (ontology_slots)
- 定义分类约束 (categorical_constraints)
- 构建系统指令 Prompt
- 值归一化处理

**示例：**

```python
from slot_template import PromptManager

# 创建提示词管理器
pm = PromptManager(domain="restaurant")

# 添加自定义槽位
pm.add_slot(
    slot_name="restaurant_name",
    description="餐厅名称",
    categorical_values=None
)

pm.add_slot(
    slot_name="food_type",
    description="菜系类型",
    categorical_values=["中餐", "西餐", "日料", "韩餐"]
)

# 获取系统指令
instruction = pm.get_system_instruction()
```

**Prompt 设计（遵循论文 Figure 2）：**

```
请考虑以下槽位（"slots"）列表，以 JSON 格式提供：

"slots": {
  "intent": "用户的主要意图",
  "location": "地点或位置",
  ...
}

某些槽位只能从预定义列表中取值：

"categorical": {
  "intent": ["询问", "预订", "修改", "取消"],
  ...
}

现在考虑以下系统（"system"）和用户（"user"）之间的对话。

请告诉我用户在最新回复中更新了哪些槽位？
以 JSON 格式呈现更新内容。如果没有槽位被更新，返回空的 JSON 对象。

特殊规则：
1. 如果用户请求某个槽位信息（但未提供具体值），用 "?" 填充
2. 如果用户表示不关心某个槽位，用 "dontcare" 填充
3. 只更新明确提到或可从上下文推断的槽位
4. 保持与之前对话的一致性，注意共指消解

请直接返回 JSON 格式的槽位更新，不要包含其他解释。
```

### 2. ResponseParser (响应解析器)

从 ChatGPT 的自然语言回复中提取 JSON 格式的状态更新。

**主要功能：**
- 鲁棒的 JSON 提取（处理不稳定输出）
- 幻觉过滤（只保留有效槽位）
- 多种 JSON 格式支持

**示例：**

```python
from slot_template import ResponseParser, PromptManager

pm = PromptManager()
parser = ResponseParser(pm)

# 各种格式的响应都能正确解析
response1 = '{"intent": "预订", "location": "北京"}'
response2 = '根据对话，更新了 {"intent": "询问"} 槽位。'
response3 = '[{"intent": "预订"}, {"location": "上海"}]'

result1 = parser.extract_json(response1)
result2 = parser.extract_json(response2)
result3 = parser.extract_json(response3)

# 过滤幻觉（只保留本体中定义的槽位）
filtered = parser.filter_hallucinations(result1)
```

**处理的问题：**

1. **解析不稳定性**：ChatGPT 的输出形式多样，不总是直接返回 JSON
   - 使用多种正则模式提取
   - 支持嵌套 JSON
   - 支持列表格式

2. **幻觉处理**：约 90.4% 的预测是有效槽位，9.6% 为幻觉
   - 过滤未在本体中定义的槽位
   - 保持状态一致性

### 3. DialogueStateTracker (对话状态追踪器)

实现完整的 Zero-shot 对话状态追踪流程。

**主要功能：**
- 维护对话历史（messages）
- 累积式状态更新
- 完整的上下文管理
- 支持共指消解

**示例：**

```python
from slot_template import DialogueStateTracker
import asyncio

async def track_dialogue():
    # 初始化追踪器
    tracker = DialogueStateTracker(
        llm_client=your_llm_client,  # 可选
        domain="general"
    )
    
    # 重置对话
    tracker.reset_dialogue()
    
    # 处理对话轮次
    state1 = await tracker.process_turn(
        system_utterance="您好，有什么可以帮您？",
        user_utterance="我想订酒店"
    )
    # state1: {"intent": "预订"}
    
    state2 = await tracker.process_turn(
        system_utterance="去哪个城市？",
        user_utterance="北京"
    )
    # state2: {"intent": "预订", "destination": "北京"}
    
    # 获取最终状态
    final_state = tracker.get_current_state()
    
    return final_state

asyncio.run(track_dialogue())
```

## 核心流程

### 对话状态追踪流程

```
┌─────────────────────────────────────────────────────────────┐
│  步骤 1: 重置对话                                            │
│  - 初始化 messages 列表                                      │
│  - 添加系统指令 Prompt                                        │
│  - 清空当前状态                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 2: 处理每轮对话                                        │
│  输入: system_utterance, user_utterance                      │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 3: 构建当前轮次 Prompt                                 │
│  格式: system: "..." \n user: "..."                          │
│  添加到 messages 历史                                        │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 4: 调用 ChatGPT API                                    │
│  - 发送完整 messages 历史                                    │
│  - temperature=0.0 保持确定性                                │
│  - 获取响应                                                  │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 5: 将响应加入历史                                      │
│  - 保持上下文连贯                                            │
│  - 支持共指消解                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 6: 解析响应提取 JSON                                   │
│  - 使用 ResponseParser                                       │
│  - 提取槽位更新                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 7: 过滤幻觉                                            │
│  - 只保留有效槽位                                            │
│  - 应用值归一化                                              │
└─────────────────────────────────────────────────────────────┘
                           ↓
┌─────────────────────────────────────────────────────────────┐
│  步骤 8: 累积更新状态                                        │
│  DS_t = update(DS_{t-1}, predicted_updates)                  │
│  - 处理特殊值 (?, dontcare)                                  │
│  - 合并到当前状态                                            │
└─────────────────────────────────────────────────────────────┘
                           ↓
                    返回当前状态
```

## 关键实现细节

### 1. 共指消解 (Coreference Resolution)

**问题：** 用户说 "taxi 也一样" 时如何理解？

**解决方案：** 
- 维护完整的 `messages` 历史
- ChatGPT 利用上下文自行推理
- 代码不需要额外逻辑

```python
# 轮次 1
await tracker.process_turn(
    "去哪里？",
    "我要去北京"
)  # {"destination": "北京"}

# 轮次 2  
await tracker.process_turn(
    "出租车去哪？",
    "也去那里"  # ChatGPT 通过历史推断：北京
)  # {"destination": "北京"}
```

### 2. 幻觉处理

**问题：** ChatGPT 可能返回未定义的槽位

**解决方案：**
- 在 `_update_state` 中过滤
- 只更新本体中存在的槽位

```python
def filter_hallucinations(self, updates: Dict[str, str]) -> Dict[str, str]:
    filtered = {}
    valid_slots = set(self.prompt_manager.ontology_slots.keys())
    
    for slot, value in updates.items():
        if slot in valid_slots:  # 只保留有效槽位
            filtered[slot] = self.prompt_manager.normalize_value(value)
    
    return filtered
```

### 3. 值归一化 (Normalization)

**问题：** ChatGPT 可能输出 "guest house" 或 "guesthouse"

**解决方案：**
- 引入归一化映射字典
- 统一不同表述

```python
value_normalization = {
    "便宜的": "便宜",
    "贵的": "昂贵",
    "很贵": "昂贵",
    "不贵": "中等",
}

def normalize_value(self, value: str) -> str:
    value = value.strip()
    if value in self.value_normalization:
        return self.value_normalization[value]
    return value
```

### 4. 特殊值处理

根据论文规则：

- **"?"**: 用户在询问，不更新状态
- **"dontcare"**: 用户不关心，记录这个状态

```python
def _update_state(self, updates: Dict[str, str]):
    for slot, value in updates.items():
        if value == "?":
            # 用户在询问，不更新
            continue
        elif value == "dontcare":
            # 用户不关心
            self.current_state[slot] = "dontcare"
        elif value:
            # 正常更新
            self.current_state[slot] = value
```

## 使用示例

### 完整对话示例

```python
import asyncio
from slot_template import DialogueStateTracker, PromptManager

async def restaurant_booking_example():
    # 1. 创建自定义提示词管理器
    pm = PromptManager(domain="restaurant")
    pm.add_slot("restaurant_name", "餐厅名称")
    pm.add_slot("food_type", "菜系", ["中餐", "西餐", "日料"])
    pm.add_slot("party_size", "人数")
    pm.add_slot("time", "时间")
    
    # 2. 初始化追踪器
    tracker = DialogueStateTracker(
        llm_client=None,  # 使用规则提取
        prompt_manager=pm
    )
    tracker.reset_dialogue()
    
    # 3. 模拟对话
    print("对话开始...")
    
    # 轮次 1
    state = await tracker.process_turn(
        "您好，需要预订餐厅吗？",
        "是的，我想订一家中餐厅"
    )
    print(f"轮次 1 状态: {state}")
    # {"food_type": "中餐", "intent": "预订"}
    
    # 轮次 2
    state = await tracker.process_turn(
        "好的，几位？",
        "4个人"
    )
    print(f"轮次 2 状态: {state}")
    # {"food_type": "中餐", "intent": "预订", "quantity": "4"}
    
    # 轮次 3
    state = await tracker.process_turn(
        "什么时间？",
        "明天晚上7点"
    )
    print(f"轮次 3 状态: {state}")
    # {"food_type": "中餐", "intent": "预订", "quantity": "4", "time": "明天晚上7点"}
    
    # 4. 获取最终状态
    final_state = tracker.get_current_state()
    print(f"最终状态: {final_state}")
    
    return final_state

asyncio.run(restaurant_booking_example())
```

### 运行演示

```bash
# 运行 DST 演示
python dst_demo.py

# 选择演示模式
# 1 - 基础对话状态追踪
# 2 - Prompt 设计展示
# 3 - 响应解析演示
# 4 - 对比演示
# 5 - 运行所有演示
```

## 与基础槽位模板的对比

| 特性 | 基础槽位模板 | DST (对话状态追踪) |
|------|------------|-------------------|
| **槽位定义** | 固定 3 个通用槽位 | 可扩展的本体定义 |
| **状态管理** | 无状态累积 | 累积式状态更新 |
| **上下文** | 简单历史 | 完整对话历史 |
| **共指消解** | ❌ 不支持 | ✅ 通过上下文支持 |
| **值归一化** | ❌ 无 | ✅ 有 |
| **幻觉过滤** | ❌ 无 | ✅ 有 |
| **分类约束** | ❌ 无 | ✅ 有 |
| **特殊值** | ❌ 无 | ✅ ?, dontcare |
| **适用场景** | 简单对话 | 复杂多轮对话 |

## 扩展和自定义

### 添加领域特定槽位

```python
# 酒店预订领域
pm = PromptManager(domain="hotel")
pm.add_slot("hotel_name", "酒店名称")
pm.add_slot("check_in", "入住日期")
pm.add_slot("check_out", "退房日期")
pm.add_slot("room_type", "房间类型", ["单人间", "双人间", "套房"])
pm.add_slot("price_range", "价格范围", ["经济", "中档", "豪华"])

# 出租车预订领域
pm = PromptManager(domain="taxi")
pm.add_slot("departure", "出发地")
pm.add_slot("destination", "目的地")
pm.add_slot("departure_time", "出发时间")
pm.add_slot("car_type", "车辆类型", ["经济型", "舒适型", "豪华型"])
```

### 自定义值归一化

```python
pm = PromptManager()

# 添加自定义归一化规则
pm.value_normalization.update({
    "明天": "tomorrow",
    "后天": "day_after_tomorrow",
    "周一": "Monday",
    "周二": "Tuesday",
})
```

## 论文参考

本实现基于以下论文：

**标题**: ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?

**会议**: ACL 2023

**核心思想**:
1. 完全不进行微调（Zero-shot）
2. 通过 Prompt Engineering 实现 DST
3. 利用 ChatGPT 的上下文理解能力
4. 从自然语言响应中提取结构化状态

**关键创新**:
- 精心设计的 Prompt 包含槽位定义和约束
- 维护完整对话历史实现共指消解
- 鲁棒的 JSON 解析处理输出不稳定性
- 幻觉过滤保证预测有效性

## 总结

DST 模块提供了一个完整的、基于论文的对话状态追踪实现：

✅ **遵循论文设计**: 完全按照 ACL 2023 论文实现  
✅ **Zero-shot**: 无需微调，即插即用  
✅ **可扩展**: 支持自定义槽位和领域  
✅ **鲁棒**: 处理各种边界情况  
✅ **文档完整**: 详细的使用说明和示例  

适用于需要精确对话状态追踪的多轮对话系统。
