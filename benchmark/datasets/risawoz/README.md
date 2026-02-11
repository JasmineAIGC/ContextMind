# RiSAWOZ 数据集评测

## 概述

RiSAWOZ（**Ri**ch **S**emantic **A**nnotation **W**izard-**O**f-O**Z**）是一个面向任务型对话的中文数据集，包含12个领域的多轮对话数据。

- **GitHub**: https://github.com/terryqj0107/RiSAWOZ
- **论文**: [RiSAWOZ: A Large-Scale Chinese Dataset for Multi-Domain Task-Oriented Dialogue](https://arxiv.org/abs/2010.08738)
- **领域数量**: 12个
- **数据规模**: ~11K 对话

## 数据集结构

### 文件组织

```
data/RiSAWOZ/
├── train.json          # 训练集
├── val.json            # 验证集
└── test.json           # 测试集
```

### 12个领域

1. 景点 (Attraction)
2. 酒店 (Hotel)
3. 餐厅 (Restaurant)
4. 地铁 (Metro)
5. 出租 (Taxi)
6. 火车 (Train)
7. 电视剧 (TV Series)
8. 天气 (Weather)
9. 航班 (Flight)
10. 医院 (Hospital)
11. 电影 (Movie)
12. 音乐 (Music)

### 数据格式

```json
{
  "dialogue_id": "xxx",
  "goal": {
    "description": "...",
    "constraints": {...}
  },
  "dialogue": [
    {
      "turn_id": 0,
      "user_utterance": "我想找一个景点",
      "system_utterance": "请问您想去什么类型的景点？",
      "belief_state": [
        {
          "domain": "景点",
          "slot": "类型",
          "value": "博物馆"
        }
      ]
    },
    ...
  ]
}
```

## DST 评测

### 运行评测

```bash
# 基本使用 - 评测验证集所有领域
python benchmark/run_dst_risawoz.py --data-root ./data/RiSAWOZ

# 评测特定领域
python benchmark/run_dst_risawoz.py --domain 景点 --split val

# 评测训练集（快速测试）
python benchmark/run_dst_risawoz.py --split train --limit 10

# 评测测试集
python benchmark/run_dst_risawoz.py --split test

# 详细输出
python benchmark/run_dst_risawoz.py --domain 酒店 --limit 5 --verbose
```

### 评测指标

RiSAWOZ 使用以下评测指标（与官方评测一致）：

#### 1. 槽位准确率 (Slot Accuracy) - Turn-level

**定义**: 所有轮次中正确槽位的比例

**计算公式**:
```
Slot Accuracy = Σ(correct_slots) / Σ(total_slots)
```

**含义**: 衡量模型在每个轮次提取槽位值的准确性

#### 2. 联合准确率 (Joint Accuracy) - Turn-level

**定义**: 完全匹配的轮次比例

**计算公式**:
```
Joint Accuracy = Σ(exact_match_turns) / Σ(total_turns)
```

**含义**: 每轮的状态必须完全正确（所有槽位值都匹配），不允许任何错误或遗漏

**注意**: RiSAWOZ 使用 turn-level Joint Accuracy，与 TransferTOD 的 dialogue-level Joint Accuracy 不同

#### 3. 精确率 (Precision) - Dialogue-level

**定义**: 预测正确的 slot-value pairs 占所有预测的比例

**计算公式**:
```
Precision = TP / (TP + FP)
```

#### 4. 召回率 (Recall) - Dialogue-level

**定义**: 预测正确的 slot-value pairs 占所有真实 pairs 的比例

**计算公式**:
```
Recall = TP / (TP + FN)
```

#### 5. F1分数 (F1 Score) - Dialogue-level

**定义**: Precision 和 Recall 的调和平均

**计算公式**:
```
F1 = 2 * Precision * Recall / (Precision + Recall)
```

### 评测输出示例

```
📊 RiSAWOZ DST 评测指标汇总
======================================================================

数据集划分: val
领域: 景点
对话数: 100

【核心指标】
----------------------------------------------------------------------
槽位准确率 (Slot Accuracy):  85.50%
联合准确率 (Joint Accuracy):  70.00%
精确率 (Precision):          88.20%
召回率 (Recall):             90.00%
F1分数 (F1 Score):           89.09%

【详细统计】
----------------------------------------------------------------------
总槽位数: 1500
正确槽位数: 1283
总轮次数: 500
完全匹配轮次数: 350

【分领域统计】
----------------------------------------------------------------------

景点 (对话数: 50):
  槽位准确率: 86.30%
  联合准确率: 72.00%
  F1分数: 90.50%

酒店 (对话数: 50):
  槽位准确率: 84.70%
  联合准确率: 68.00%
  F1分数: 87.68%

======================================================================
```

## 与 TransferTOD 的对比

### 数据集对比

| 特性 | RiSAWOZ | TransferTOD |
|------|---------|-------------|
| 语言 | 中文 | 中文 |
| 领域数 | 12 | 24 |
| 对话数 | ~11K | ~9K |
| 标注风格 | MultiWOZ | 自定义 |
| Belief State | 列表格式 | 字典格式 |

### 评测指标对比

| 指标 | RiSAWOZ | TransferTOD |
|------|---------|-------------|
| Slot Accuracy | Turn-level | Turn-level |
| Joint Accuracy | **Turn-level** | **Dialogue-level** |
| Precision/Recall/F1 | Dialogue-level | Dialogue-level |

**关键差异**: RiSAWOZ 的 Joint Accuracy 是 turn-level（每轮状态必须完全匹配），而 TransferTOD 是 dialogue-level（只要求最终状态匹配）。

## 适配器实现

### 核心类

#### RiSAWOZAdapter

```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

# 初始化适配器
adapter = RiSAWOZAdapter(data_root="./data/RiSAWOZ")

# 加载对话
dialogue = adapter.load_dialogue("0", split="val")

# 获取领域对话
景点_dialogues = adapter.get_dialogues_by_domain("景点", split="val")

# 获取所有领域
domains = adapter.get_all_domains()
```

#### DialogueInstance

标准化的对话实例格式：

```python
@dataclass
class DialogueInstance:
    dialogue_id: str              # 对话ID
    domain: str                   # 主领域
    turns: List[DialogueTurn]     # 对话轮次列表
    description: str              # 对话描述
    final_state: Dict[str, Any]   # 最终状态
    metadata: Dict[str, Any]      # 元数据
```

#### DialogueTurn

单个对话轮次：

```python
@dataclass
class DialogueTurn:
    turn_id: int                  # 轮次ID
    user_utterance: str           # 用户话语
    system_utterance: str         # 系统话语
    expected_slots: Dict[str, str] # 期望的槽位状态（累积）
```

### Belief State 处理

RiSAWOZ 的 belief_state 格式：

```json
"belief_state": [
  {
    "domain": "景点",
    "slot": "名称",
    "value": "故宫"
  },
  {
    "domain": "景点",
    "slot": "类型",
    "value": "博物馆"
  }
]
```

适配器会自动转换为：

```python
{
  "景点-名称": "故宫",
  "景点-类型": "博物馆"
}
```

## 常见问题

### Q1: 如何下载 RiSAWOZ 数据集？

```bash
git clone https://github.com/terryqj0107/RiSAWOZ.git
cd RiSAWOZ
# 数据文件在 data/ 目录下
```

### Q2: 数据集目录结构应该是什么样的？

```
./data/RiSAWOZ/
├── train.json
├── val.json
└── test.json
```

### Q3: 为什么 Joint Accuracy 比 TransferTOD 低很多？

RiSAWOZ 使用 turn-level Joint Accuracy，每轮状态都必须完全正确。这比 dialogue-level 更严格，因此通常会低于 TransferTOD 的 Joint Accuracy。

### Q4: 如何评测特定领域？

```bash
# 评测单个领域
python benchmark/run_dst_risawoz.py --domain 景点

# 评测多个领域（需要多次运行）
for domain in 景点 酒店 餐厅; do
    python benchmark/run_dst_risawoz.py --domain $domain
done
```

### Q5: 如何解读评测结果？

- **Slot Accuracy**: 槽位级别的准确性，越高越好
- **Joint Accuracy**: 完整对话状态的准确性，要求严格
- **Precision**: 预测的准确性，避免过度预测
- **Recall**: 覆盖的完整性，避免遗漏
- **F1**: 综合指标，平衡 P 和 R

一般来说：
- Slot Accuracy 应该在 80-95% 之间
- Joint Accuracy 应该在 60-85% 之间（turn-level）
- F1 Score 应该在 75-90% 之间

## 参考资料

- [RiSAWOZ GitHub](https://github.com/terryqj0107/RiSAWOZ)
- [RiSAWOZ 论文](https://arxiv.org/abs/2010.08738)
- [MultiWOZ 数据集](https://github.com/budzianowski/multiwoz)
- [对话状态追踪 (DST) 综述](https://arxiv.org/abs/2103.04656)

## 版本历史

- **0.1.0** (2026-02-11): 初始实现
  - RiSAWOZ 适配器
  - DST 评测脚本
  - RiSAWOZ 官方指标
