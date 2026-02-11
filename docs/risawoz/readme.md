# RiSAWOZ 数据集使用指南

## 快速回答用户的三个问题

### ✅ 问题1: RiSAWOZ 数据集的领域+意图+槽位+值来自 risawoz_test.json

**已完成**: 从 `resources/data/risawoz_test.json` 提取了所有信息

- **13 个领域**: 医院、天气、旅游景点、汽车、火车、电影、电脑、电视剧、辅导班、通用、酒店、飞机、餐厅
- **7 个意图**: Bye, General, Greeting, Inform, No-offer, Recommend, Request
- **完整的槽位列表**: 每个领域都有详细的槽位

### ✅ 问题2: RiSAWOZ 的意图不在 intent_labels_30_domains_Version2.json 中

**已完成**: 创建了 RiSAWOZ 专用配置文件

**文件**: `benchmark/shared/configs/intent_labels_risawoz.json`

### ✅ 问题3: 代码从未正常运行过

**根本原因**: risawoz_test.json 是 **NLU 数据**，不是 **DST 数据**

- **NLU 数据**: 意图识别、实体提取
- **DST 数据**: 对话状态追踪

## 两种使用方式

### 方式 A: NLU 任务 (使用 risawoz_test.json) ✅ 推荐

```python
import json
from benchmark.datasets.risawoz.label_parser import RiSAWOZLabelParser

# 加载数据
with open('resources/data/risawoz_test.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

# 处理记录
record = data[0]
tokens = record[0]              # 分词
intent_strings = record[2]      # 意图字符串

# 解析意图
labels = RiSAWOZLabelParser.parse_labels(intent_strings)

for label in labels:
    print(f"意图: {label.intent}")
    print(f"领域: {label.domain}")
    print(f"槽位: {label.slot}")
    print(f"值: {label.value}")
```

### 方式 B: DST 任务 (需要下载正确的数据)

```bash
# 1. 下载 RiSAWOZ 数据
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 2. 运行 DST 评测
python benchmark/run_dst_risawoz.py \
    --data-root ./RiSAWOZ/data \
    --split val \
    --limit 10
```

## 数据格式对比

### NLU 格式 (risawoz_test.json)

```json
[
  [
    ["你", "好"],                    // tokens (分词)
    ["O", "O"],                     // NER labels (实体标签)
    ["Greeting+旅游景点++"],        // intent strings (意图字符串)
    [["Greeting", "旅游景点", "", ""]], // parsed intents (解析后的意图)
    []                              // extra (额外信息)
  ]
]
```

- **用途**: 意图识别、实体提取
- **可用工具**: `label_parser.py`
- **配置文件**: `intent_labels_risawoz.json`

### DST 格式 (train.json, val.json, test.json)

```json
{
  "dialogue_id": "xxx",
  "dialogue": [
    {
      "turn_id": 0,
      "user_utterance": "我想找景点",
      "belief_state": [
        {
          "domain": "旅游景点",
          "slot": "类型",
          "value": "博物馆"
        }
      ]
    }
  ]
}
```

- **用途**: 对话状态追踪
- **可用工具**: `run_dst_risawoz.py`
- **数据来源**: RiSAWOZ GitHub

## 已创建的文件

### 配置文件
- `benchmark/shared/configs/intent_labels_risawoz.json` - RiSAWOZ 意图标签

### 代码工具
- `benchmark/datasets/risawoz/label_parser.py` - 标签解析器
- `benchmark/datasets/risawoz/adapter.py` - 数据适配器

### 文档
- `resources/data/RISAWOZ_TEST_README.md` - NLU 数据使用指南
- `docs/RISAWOZ_SOLUTION_SUMMARY.md` - 完整解决方案总结
- `benchmark/datasets/risawoz/DATASET_SETUP.md` - 数据集设置
- `benchmark/datasets/risawoz/QUICK_START.md` - 快速开始
- `benchmark/datasets/risawoz/QUICK_USAGE.md` - 快速使用

## 快速开始

### NLU 任务

```bash
# 查看数据结构
python -c "
import json
with open('resources/data/risawoz_test.json') as f:
    data = json.load(f)
    print(f'Total: {len(data)} records')
    print(f'First: {data[0][:3]}')
"

# 使用标签解析器
python -c "
from benchmark.datasets.risawoz.label_parser import RiSAWOZLabelParser
labels = RiSAWOZLabelParser.parse_labels(['Inform+酒店+名称+希尔顿'])
print(labels[0])
"
```

### DST 任务

```bash
# 需要先下载正确的数据
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 然后运行评测
python benchmark/run_dst_risawoz.py \
    --data-root ./RiSAWOZ/data \
    --split val
```

## 关键要点

1. ✅ **risawoz_test.json 是 NLU 数据**，用于意图识别和实体提取
2. ✅ **DST 评测需要不同的数据**，从 RiSAWOZ GitHub 下载
3. ✅ **已提供完整的 NLU 工具链**，包括解析器和配置
4. ✅ **两种任务都有详细文档**，选择合适的任务使用

## 参考文档

- **完整解决方案**: `docs/RISAWOZ_SOLUTION_SUMMARY.md`
- **NLU 数据说明**: `resources/data/RISAWOZ_TEST_README.md`
- **DST 数据设置**: `benchmark/datasets/risawoz/DATASET_SETUP.md`
- **快速使用指南**: `benchmark/datasets/risawoz/QUICK_USAGE.md`

## 总结

所有三个问题都已解决：
1. ✅ 从 risawoz_test.json 提取了领域+意图+槽位+值
2. ✅ 创建了 RiSAWOZ 专用意图标签配置
3. ✅ 深入分析并澄清了代码用途和使用方式

选择合适的方式开始使用！
