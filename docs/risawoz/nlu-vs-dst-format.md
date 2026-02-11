# RiSAWOZ 数据格式说明：NLU vs DST

## 问题描述

用户报告：`.data/RiSAWOZ/task1-data/val.json` 文件存在，格式与 `resources/data/risawoz_test.json` 一致，但在运行DST评测时被拒绝。

## 原因分析

### 格式不匹配

您的文件格式：**NLU格式**（自然语言理解）
- 用途：意图识别、实体提取
- 格式：`[[tokens], [labels], [intents], [parsed_intents], []]`
- 数据特点：单个对话轮次，无对话结构

DST评测需要：**DST格式**（对话状态追踪）
- 用途：对话状态追踪
- 格式：`{"dialogue_id": "xxx", "dialogue": [...]}`
- 数据特点：完整多轮对话，包含belief_state

## 两种格式对比

### NLU格式示例
```json
[
  [
    ["你", "好", "我", "想", "订", "酒", "店"],     // tokens
    ["O", "O", "O", "O", "O", "B-酒店", "I-酒店"],  // NER labels
    ["Inform+酒店+类型+经济型"],                     // intent labels
    [["Inform", "酒店", "类型", "经济型"]],          // parsed
    []                                               // extra
  ],
  // ... 每条记录是一个独立的轮次
]
```

**特点**:
- ✅ 有意图标注
- ✅ 有实体标注
- ❌ **无对话ID**（不知道哪些轮次属于同一对话）
- ❌ **无系统话语**（只有用户话语）
- ❌ **无belief state**（没有累积的对话状态）
- ❌ **无对话结构**（无法知道轮次顺序）

### DST格式示例
```json
{
  "dialogue_id": "dialogue_001",
  "goal": {...},
  "dialogue": [
    {
      "turn_id": 0,
      "system_utterance": "您好，有什么可以帮您？",
      "user_utterance": "我想找一个酒店",
      "belief_state": [
        {"domain": "酒店", "slot": "类型", "value": ""}
      ]
    },
    {
      "turn_id": 1,
      "system_utterance": "好的，您需要什么类型的酒店？",
      "user_utterance": "经济型的",
      "belief_state": [
        {"domain": "酒店", "slot": "类型", "value": "经济型"}
      ]
    }
  ]
}
```

**特点**:
- ✅ 有对话ID（对话分组）
- ✅ 有系统和用户话语
- ✅ 有belief state（对话状态）
- ✅ 有完整的对话结构
- ✅ 适用于DST评测

## 为什么不能转换？

NLU格式缺少DST所需的关键信息：

| 需要的信息 | NLU格式 | 能否推断 |
|-----------|---------|---------|
| dialogue_id | ❌ 无 | ❌ 无法推断（不知道对话分组）|
| system_utterance | ❌ 无 | ❌ 无法推断（没有系统话语）|
| turn_id | ❌ 无 | ❌ 无法推断（不知道轮次顺序）|
| belief_state | ❌ 无 | ⚠️ 部分推断（可从intent标注提取，但不完整）|

**结论**: 无法可靠地将NLU格式转换为DST格式。

## 解决方案

### 方案1：获取正确格式的数据（推荐）✅

从RiSAWOZ官方仓库下载DST格式数据：

```bash
# 1. 克隆仓库
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 2. 查找DST格式文件
cd RiSAWOZ
ls data/  # 查找 train.json, val.json, test.json

# 3. 复制到项目目录
mkdir -p /path/to/ContextMind/data/RiSAWOZ
cp data/*.json /path/to/ContextMind/data/RiSAWOZ/

# 4. 验证
ls /path/to/ContextMind/data/RiSAWOZ/
# 应该看到: train.json  val.json  test.json
```

**或者下载已处理的数据**：
- 从RiSAWOZ releases下载
- 使用task1-data-**DST**.zip（注意不是task1-data-NLU.zip）

### 方案2：使用NLU格式进行NLU任务

如果您的目标是进行NLU任务（意图识别、实体提取），而不是DST：

1. **使用NLU评测脚本**（如果有）
2. **或者自己实现NLU评测**，使用label_parser处理数据：

```python
from benchmark.datasets.risawoz.label_parser import RiSAWOZLabelParser
import json

# 加载NLU数据
with open('.data/RiSAWOZ/task1-data/val.json', 'r') as f:
    nlu_data = json.load(f)

# 处理每条记录
for record in nlu_data:
    tokens = record[0]
    ner_labels = record[1]
    intent_strings = record[2]
    
    # 解析意图
    intents = RiSAWOZLabelParser.parse_labels(intent_strings)
    
    # 提取槽位-值
    slots = RiSAWOZLabelParser.extract_slot_values(intents)
    
    # 进行NLU评测...
```

### 方案3：明确需求

请确认您的实际需求：

**如果需要DST评测**：
- ✅ 使用方案1，获取DST格式数据
- ✅ 参考 `benchmark/datasets/risawoz/DATASET_SETUP.md`

**如果需要NLU评测**：
- ⚠️ 当前没有NLU评测脚本
- ⚠️ 可以使用label_parser工具处理NLU数据
- ⚠️ 或者实现自己的NLU评测逻辑

## 常见误解

### ❌ "task1-data 就是 RiSAWOZ 数据集"
**纠正**: task1-data是RiSAWOZ的NLU任务数据，不是完整数据集。

### ❌ "NLU数据可以用于DST评测"
**纠正**: NLU数据缺少DST所需的关键信息，无法直接使用。

### ❌ "只要格式转换就可以"
**纠正**: 格式转换需要填充缺失信息（对话ID、系统话语等），这些信息无法从NLU数据中推断。

## 数据集文件对照表

| 文件路径 | 格式 | 用途 | 适用脚本 |
|---------|------|------|---------|
| `data/train.json` | DST | 对话状态追踪 | `run_dst_risawoz.py` ✅ |
| `data/val.json` | DST | 对话状态追踪 | `run_dst_risawoz.py` ✅ |
| `data/test.json` | DST | 对话状态追踪 | `run_dst_risawoz.py` ✅ |
| `task1-data/train.json` | NLU | 意图识别/实体提取 | NLU评测脚本（未提供）❌ |
| `task1-data/val.json` | NLU | 意图识别/实体提取 | NLU评测脚本（未提供）❌ |
| `task1-data/test.json` | NLU | 意图识别/实体提取 | NLU评测脚本（未提供）❌ |

## 如何获取DST格式数据

### 选项1：从GitHub下载

```bash
# 方式1：克隆完整仓库
git clone https://github.com/terryqj0107/RiSAWOZ.git
cd RiSAWOZ/data
ls  # 查看可用文件

# 方式2：只下载数据文件
wget https://github.com/terryqj0107/RiSAWOZ/raw/master/data/train.json
wget https://github.com/terryqj0107/RiSAWOZ/raw/master/data/val.json
wget https://github.com/terryqj0107/RiSAWOZ/raw/master/data/test.json
```

### 选项2：从Releases下载

访问 https://github.com/terryqj0107/RiSAWOZ/releases 下载预打包的数据。

### 选项3：联系数据集作者

如果以上方式都不可行，可以联系RiSAWOZ数据集的维护者获取DST格式数据。

## 验证数据格式

使用以下脚本验证您的数据格式：

```python
import json
from pathlib import Path

def check_format(file_path):
    """检查文件格式"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if isinstance(data, list) and len(data) > 0:
        first_item = data[0]
        
        # 检查NLU格式
        if isinstance(first_item, list) and len(first_item) >= 4:
            if all(isinstance(x, list) for x in first_item[:4]):
                return "NLU格式", "用于意图识别/实体提取，不适用于DST评测"
        
        # 检查DST格式（列表形式）
        if isinstance(first_item, dict):
            if "dialogue" in first_item or "belief_state" in first_item:
                return "DST格式", "✅ 可用于DST评测"
    
    elif isinstance(data, dict):
        # 检查DST格式（字典形式）
        if "dialogue" in data or any("dialogue" in v for v in data.values() if isinstance(v, dict)):
            return "DST格式", "✅ 可用于DST评测"
    
    return "未知格式", "无法确定"

# 使用示例
file_path = ".data/RiSAWOZ/task1-data/val.json"
format_type, description = check_format(file_path)
print(f"文件: {file_path}")
print(f"格式: {format_type}")
print(f"说明: {description}")
```

## 总结

### 核心要点

1. ✅ **NLU格式 ≠ DST格式** - 两种格式用于不同的任务
2. ✅ **task1-data 不适用于 DST评测** - 它是NLU任务数据
3. ✅ **需要正确的DST格式数据** - 从RiSAWOZ官方获取
4. ✅ **适配器的拒绝是正确的** - 保护用户避免使用错误格式

### 下一步

根据您的需求选择：

**如果要做DST评测**：
1. 从RiSAWOZ GitHub获取DST格式数据
2. 参考 `DATASET_SETUP.md` 设置数据集
3. 运行 `python benchmark/run_dst_risawoz.py`

**如果要做NLU评测**：
1. 使用现有的task1-data NLU格式数据
2. 使用label_parser处理数据
3. 实现自己的NLU评测逻辑

### 参考文档

- `benchmark/datasets/risawoz/DATASET_SETUP.md` - 数据集设置完整指南
- `benchmark/datasets/risawoz/README.md` - 适配器使用说明
- `resources/data/RISAWOZ_TEST_README.md` - NLU格式说明
- RiSAWOZ GitHub: https://github.com/terryqj0107/RiSAWOZ

---

**更新时间**: 2026-02-11  
**相关问题**: NLU格式数据无法用于DST评测
