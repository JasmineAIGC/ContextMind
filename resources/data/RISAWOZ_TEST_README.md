# RiSAWOZ 测试数据说明

## 文件信息

- **文件名**: `risawoz_test.json`
- **大小**: 7.9 MB
- **记录数**: 9,286 条对话轮次
- **用途**: NLU（自然语言理解）任务的标注数据

## 数据格式

这个文件是一个 JSON 列表，每个元素代表一个对话轮次的 NLU 标注数据。

### 数据结构

每条记录包含 5 个元素：

```python
[
    tokens,          # 索引 0: 分词后的文本（字符列表）
    labels,          # 索引 1: NER 标签序列
    intents,         # 索引 2: 意图字符串列表
    parsed_intents,  # 索引 3: 解析后的意图信息
    extra            # 索引 4: 额外信息（通常为空列表）
]
```

### 详细说明

#### 1. tokens (分词结果)
- **类型**: `List[str]`
- **说明**: 将用户话语按字符分割的结果
- **示例**: `["你", "好", "!", "我", "想", "订", "酒", "店"]`

#### 2. labels (标签序列)
- **类型**: `List[str]`
- **说明**: 与 tokens 对应的 NER（命名实体识别）标签
- **常见标签**:
  - `"O"`: Outside（非实体）
  - `"B-{实体类型}"`: Begin（实体开始）
  - `"I-{实体类型}"`: Inside（实体内部）
- **示例**: `["O", "O", "O", "O", "O", "O", "B-酒店名称", "I-酒店名称"]`

#### 3. intents (意图列表)
- **类型**: `List[str]`
- **说明**: 该轮次涉及的意图，格式为 `"意图类型+领域+槽位+槽位值"`
- **格式**: 用 `+` 分隔四个部分
- **示例**: 
  - `"Greeting+旅游景点++"`（问候，旅游景点领域，无槽位）
  - `"General+旅游景点++"`（一般询问，旅游景点领域）

#### 4. parsed_intents (解析后的意图)
- **类型**: `List[List[str]]`
- **说明**: 将意图字符串解析为 4 元组列表
- **格式**: `[[意图类型, 领域, 槽位, 槽位值], ...]`
- **示例**: 
  ```json
  [
    ["Greeting", "旅游景点", "", ""],
    ["General", "旅游景点", "", ""]
  ]
  ```

#### 5. extra (额外信息)
- **类型**: `List`
- **说明**: 预留字段，通常为空列表
- **示例**: `[]`

## 完整示例

```json
[
  [
    ["你", "好", "!", "我", "是", "从", "外", "地", "来", "苏", "州", "旅", "游", "的", "，", "能", "推", "荐", "个", "好", "玩", "的", "地", "方", "吗", "？"],
    ["O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O", "O"],
    ["Greeting+旅游景点++", "General+旅游景点++"],
    [
      ["Greeting", "旅游景点", "", ""],
      ["General", "旅游景点", "", ""]
    ],
    []
  ]
]
```

## 使用场景

这个数据文件适用于以下任务：

### 1. 意图识别（Intent Recognition）
- 从对话轮次中识别用户意图
- 多意图检测和分类

### 2. 命名实体识别（NER）
- 识别话语中的实体（如酒店名称、地点等）
- 实体边界检测

### 3. 分词质量验证
- 检查中文分词的准确性
- 验证字符级别的分词结果

### 4. 数据标注参考
- 了解 RiSAWOZ 数据集的标注规范
- 作为标注新数据的参考

## 与对话状态追踪（DST）数据的区别

| 特性 | risawoz_test.json | DST 数据格式 |
|------|-------------------|-------------|
| **粒度** | 单个对话轮次 | 完整多轮对话 |
| **内容** | 分词、NER标签、意图 | dialogue_id, turns, belief_state |
| **任务** | NLU（理解） | DST（状态追踪） |
| **结构** | 扁平列表 | 嵌套字典/对象 |

**注意**: 这个文件**不能**直接用于 DST 评测，需要先转换为 DST 数据格式。

## 数据统计

- **总轮次**: 9,286
- **平均 tokens 长度**: 约 20-40 个字符
- **常见领域**: 旅游景点、酒店、餐厅、地铁等
- **常见意图**: Greeting, General, Request, Inform 等

## 读取示例

### Python 读取

```python
import json

# 读取数据
with open('resources/data/risawoz_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 访问第一条记录
first_record = data[0]
tokens = first_record[0]
labels = first_record[1]
intents = first_record[2]
parsed_intents = first_record[3]

print(f"话语: {''.join(tokens)}")
print(f"意图: {intents}")
```

### 遍历所有记录

```python
for i, record in enumerate(data):
    tokens, labels, intents, parsed_intents, extra = record
    
    # 重建原始文本
    text = ''.join(tokens)
    
    # 提取实体
    entities = []
    current_entity = []
    current_label = None
    
    for token, label in zip(tokens, labels):
        if label.startswith('B-'):
            if current_entity:
                entities.append((''.join(current_entity), current_label))
            current_entity = [token]
            current_label = label[2:]
        elif label.startswith('I-') and current_entity:
            current_entity.append(token)
        else:
            if current_entity:
                entities.append((''.join(current_entity), current_label))
            current_entity = []
            current_label = None
    
    if current_entity:
        entities.append((''.join(current_entity), current_label))
    
    print(f"记录 {i+1}: {text}")
    print(f"  实体: {entities}")
    print(f"  意图: {intents}")
    print()
```

## 相关资源

- RiSAWOZ 数据集: https://github.com/terryqj0107/RiSAWOZ
- RiSAWOZ 论文: [链接到论文]
- DST 评测文档: `benchmark/datasets/risawoz/README.md`

## 注意事项

1. **文件较大**: 7.9 MB，读取时注意内存使用
2. **编码格式**: UTF-8，包含中文字符
3. **不是 DST 数据**: 这是 NLU 级别的标注，不包含 belief_state
4. **意图格式**: 使用特殊的 `+` 分隔符，需要解析

## 更新日志

- 2026-02-11: 创建文档，说明数据格式和使用方法
