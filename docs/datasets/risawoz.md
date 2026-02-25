# RiSAWOZ 数据集说明文档

## 概述

**RiSAWOZ**（**Ri**ch **S**emantic **A**nnotation **W**izard-**O**f-**OZ**）是一个大规模中文多领域任务型对话数据集，发表于 EMNLP 2020。

- **GitHub**: https://github.com/terryqj0107/RiSAWOZ
- **主页**: https://terryqj0107.github.io/RiSAWOZ_webpage/
- **论文**: [RiSAWOZ: A Large-Scale Multi-Domain Wizard-of-Oz Dataset with Rich Semantic Annotations for Task-Oriented Dialogue Modeling](https://aclanthology.org/2020.emnlp-main.67)
- **会议**: EMNLP 2020
- **许可证**: CC BY-NC 4.0（署名-非商业性使用）

### 数据集规模

| 统计项 | 数量 |
|--------|------|
| 对话总数 | 11,200 条 |
| 话语总数 | 150,000+ 条 |
| 覆盖领域 | 12 个 |
| 单领域对话 | ~65% |
| 多领域对话 | ~35% |

---

## 数据集获取

RiSAWOZ 的数据文件托管在 GitHub 仓库的 `RiSAWOZ-data/` 目录中，也可通过以下方式下载：

- **Google Drive**: https://drive.google.com/drive/folders/1LFEY2h0WGikOG1-fMAAnF0NkR8zpyoTG
- **百度网盘**: https://pan.baidu.com/s/1BQImRCvnnP_nQzXVM1CTZQ（提取码：73jl）

```bash
git clone https://github.com/terryqj0107/RiSAWOZ.git
```

---

## 目录结构与文件说明

```
RiSAWOZ/
├── README.md                                          # 项目说明文档
├── LICENSE                                            # CC BY-NC 4.0 许可证
└── RiSAWOZ-data/                                      # 所有数据文件目录
    ├── source-data.zip                                # 完整源数据（推荐下载）
    ├── dataset_split_ids_dict.json                    # 数据集划分 ID 索引
    ├── RiSAWOZ-Database-and-Ontology.zip             # 数据库与本体文件
    ├── task1-data-NLU.zip                             # 任务1：自然语言理解数据
    ├── task2-data-DST.zip                             # 任务2：对话状态追踪数据
    ├── task3-data-E2E-Context-to-text.zip             # 任务3：端到端上下文生成数据
    ├── task4-data-Coreference resolution.zip          # 任务4：共指消解数据
    └── task5-data-Unified-generative-ellipsis-and-coreference-resolution.zip  # 任务5：统一省略与共指消解数据
```

### `RiSAWOZ-data/` 目录（数据根目录）

所有数据集文件均存放于此目录，包含源数据和各任务专用数据。

---

### `source-data.zip`（完整源数据）

**推荐下载**，包含 RiSAWOZ 数据集的全部原始标注数据。解压后结构如下：

```
source-data/
├── train.json     # 训练集（约 8,400 条对话）
├── val.json       # 验证集（约 1,400 条对话）
└── test.json      # 测试集（约 1,400 条对话）
```

每条对话的数据格式：

```json
{
  "dialogue_id": "hotel_0001",
  "goal": {
    "description": "您需要预订一家酒店...",
    "域名": "酒店",
    "constraints": {
      "位置": "西城区",
      "价格范围": "经济型"
    }
  },
  "domains": ["酒店"],
  "dialogue": [
    {
      "turn_id": 0,
      "role": "usr",
      "utterance": "我想订一家西城区的经济型酒店",
      "dialogue_act": [
        {
          "act": "Inform",
          "domain": "酒店",
          "slot": "位置",
          "value": "西城区"
        }
      ],
      "belief_state": [
        {
          "domain": "酒店",
          "slot": "位置",
          "value": "西城区"
        },
        {
          "domain": "酒店",
          "slot": "价格范围",
          "value": "经济型"
        }
      ]
    },
    {
      "turn_id": 1,
      "role": "sys",
      "utterance": "好的，我为您找到了几家西城区的经济型酒店...",
      "dialogue_act": [...],
      "belief_state": [...]
    }
  ]
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `dialogue_id` | string | 对话唯一标识符 |
| `goal` | object | 对话目标，包含自然语言描述和约束条件 |
| `goal.description` | string | 任务目标的自然语言描述 |
| `goal.constraints` | object | 槽位约束条件 |
| `domains` | list | 本次对话涉及的领域列表 |
| `dialogue` | list | 对话轮次列表 |
| `dialogue[].turn_id` | int | 轮次编号（从 0 开始） |
| `dialogue[].role` | string | 发言角色：`usr`（用户）或 `sys`（系统） |
| `dialogue[].utterance` | string | 话语文本 |
| `dialogue[].dialogue_act` | list | 对话行为标注（act、domain、slot、value） |
| `dialogue[].belief_state` | list | 累积对话状态（domain、slot、value 三元组列表） |

---

### `dataset_split_ids_dict.json`（数据集划分 ID 索引）

记录训练集、验证集、测试集的对话 ID 列表，用于复现官方数据集划分。

```json
{
  "train": ["hotel_0001", "hotel_0002", ...],
  "val": ["hotel_1001", ...],
  "test": ["hotel_2001", ...]
}
```

---

### `RiSAWOZ-Database-and-Ontology.zip`（数据库与本体）

包含 12 个领域的知识库和槽位本体定义。解压后：

```
RiSAWOZ-Database-and-Ontology/
├── database/           # 各领域知识库（结构化数据）
│   ├── 酒店.json
│   ├── 餐厅.json
│   └── ...
└── ontology/           # 各领域槽位本体（合法槽值列表）
    ├── ontology.json   # 完整本体，包含所有领域的槽位定义与可选值
    └── ...
```

**本体格式示例**：

```json
{
  "酒店": {
    "位置": ["西城区", "东城区", "朝阳区", "海淀区", ...],
    "价格范围": ["经济型", "舒适型", "豪华型"],
    "星级": ["二星级", "三星级", "四星级", "五星级"],
    ...
  }
}
```

---

### `task1-data-NLU.zip`（任务1：自然语言理解）

包含**意图检测**（Intent Detection）和**槽位填充**（Slot Filling）任务的训练数据。数据采用 IOB 标注格式，每个话语带有分词、命名实体标注和意图标签。

**文件结构**：

```
task1-data-NLU/
├── train/
│   ├── seq.in          # 分词后的输入序列（每行一个话语）
│   ├── seq.out         # IOB 槽位标注序列
│   └── label           # 意图标签
├── dev/
│   ├── seq.in
│   ├── seq.out
│   └── label
└── test/
    ├── seq.in
    ├── seq.out
    └── label
```

**数据格式示例**：

```
seq.in:  我 想 订 一 家 西 城 区 的 经 济 型 酒 店
seq.out: O  O  O  O  O  B-位置 I-位置 I-位置 O  B-价格范围 I-价格范围 I-价格范围 O  O
label:   酒店-预订
```

---

### `task2-data-DST.zip`（任务2：对话状态追踪）

包含**对话状态追踪**（Dialogue State Tracking, DST）任务专用数据，格式针对状态追踪任务优化。

**文件结构**：

```
task2-data-DST/
├── train.json     # 训练集，含每轮的 belief_state 标注
├── val.json       # 验证集
└── test.json      # 测试集
```

**数据特点**：
- 每个对话轮次包含当前的累积 `belief_state`（槽位-值对列表）
- 与 ContextMind 的 `RiSAWOZAdapter` 直接兼容
- ContextMind 使用此格式进行 DST 评测

**Belief State 格式**：

```json
"belief_state": [
  {"domain": "酒店", "slot": "位置", "value": "西城区"},
  {"domain": "酒店", "slot": "价格范围", "value": "经济型"}
]
```

ContextMind 适配器会将其转换为字典格式：

```python
{
  "酒店-位置": "西城区",
  "酒店-价格范围": "经济型"
}
```

---

### `task3-data-E2E-Context-to-text.zip`（任务3：端到端上下文生成）

包含**端到端对话生成**任务数据，模型需要基于对话上下文生成系统回复。

**文件结构**：

```
task3-data-E2E-Context-to-text/
├── train.json     # 训练集，含对话历史和目标系统回复
├── val.json       # 验证集
└── test.json      # 测试集
```

---

### `task4-data-Coreference resolution.zip`（任务4：共指消解）

包含**对话共指消解**任务数据，标注了对话中的省略词和代词对应的实体。

**文件结构**：

```
task4-data-Coreference resolution/
├── train.json     # 训练集，含共指标注
├── val.json       # 验证集
└── test.json      # 测试集
```

---

### `task5-data-Unified-generative-ellipsis-and-coreference-resolution.zip`（任务5：统一省略与共指消解）

包含**统一生成式省略消解与共指消解**任务数据，这是 RiSAWOZ 的特色创新任务。

**文件结构**：

```
task5-data-Unified-generative-ellipsis-and-coreference-resolution/
├── train.json     # 训练集
├── val.json       # 验证集
└── test.json      # 测试集
```

---

## 12 个领域详情

RiSAWOZ 涵盖以下 12 个生活服务领域：

| 编号 | 中文名称 | 英文名称 | 说明 |
|------|----------|----------|------|
| 1 | 景点 | Attraction | 旅游景点查询与推荐 |
| 2 | 酒店 | Hotel | 酒店预订与查询 |
| 3 | 餐厅 | Restaurant | 餐厅查询与订座 |
| 4 | 地铁 | Metro | 地铁线路与换乘查询 |
| 5 | 出租 | Taxi | 出租车预约 |
| 6 | 火车 | Train | 火车票查询与预订 |
| 7 | 电视剧 | TV Series | 电视剧信息查询 |
| 8 | 天气 | Weather | 天气查询 |
| 9 | 航班 | Flight | 航班查询与预订 |
| 10 | 医院 | Hospital | 医院查询与挂号 |
| 11 | 电影 | Movie | 电影信息与购票 |
| 12 | 音乐 | Music | 音乐查询与推荐 |

---

## 五项基准任务

RiSAWOZ 为以下五个 NLP 任务提供基准数据：

| 任务编号 | 任务名称 | 数据文件 | 说明 |
|---------|---------|---------|------|
| Task 1 | 自然语言理解（NLU） | `task1-data-NLU.zip` | 意图检测 + 槽位填充 |
| Task 2 | 对话状态追踪（DST） | `task2-data-DST.zip` | 多轮对话状态跟踪 |
| Task 3 | 端到端对话生成（E2E） | `task3-data-E2E-Context-to-text.zip` | 上下文到文本生成 |
| Task 4 | 共指消解 | `task4-data-Coreference resolution.zip` | 对话中的共指标注 |
| Task 5 | 统一省略与共指消解 | `task5-data-Unified-generative-ellipsis-and-coreference-resolution.zip` | 生成式联合任务 |

---

## 在 ContextMind 中使用

ContextMind 的 `RiSAWOZAdapter` 专门适配了 Task 2（DST）格式数据：

### 下载并准备数据

```bash
# 克隆仓库
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 解压 DST 数据
unzip RiSAWOZ/RiSAWOZ-data/task2-data-DST.zip -d ./data/

# 或使用完整源数据
unzip RiSAWOZ/RiSAWOZ-data/source-data.zip -d ./data/RiSAWOZ/
```

数据目录结构应为：

```
./data/RiSAWOZ/
├── train.json
├── val.json
└── test.json
```

### 运行 DST 评测

```bash
# 评测验证集（所有领域）
python benchmark/run_dst_risawoz.py --data-root ./data/RiSAWOZ

# 评测特定领域
python benchmark/run_dst_risawoz.py --domain 酒店 --split val

# 限制数量快速测试
python benchmark/run_dst_risawoz.py --split train --limit 10 --verbose
```

---

## 转换为 SGD 格式（用于 pyTOD 训练和测试）

由于 SGD 数据集是英文的，ContextMind 提供了一个转换工具，可将 RiSAWOZ 转换为 SGD 格式，从而在中文数据集上使用 pyTOD 算法进行训练和测试。

### 格式映射关系

| RiSAWOZ | SGD |
|---------|-----|
| `domain` (如 "景点") | `service_name` (如 "景点_1") |
| 每条 `dialogue` 记录（含 user + system 话语） | 拆分为 2 条 SGD turns（USER + SYSTEM）|
| `belief_state[].{domain, slot, value}` | `state.slot_values.{slot: [value]}` |
| `user_acts[[intent, domain, slot, value]]` | `frames[].actions[{act, slot, values}]` |
| 动态从数据中提取 | `schema.json`（每个域的服务 Schema） |

意图类型映射：RiSAWOZ 的 `Inform/Request/Select/Confirm` 分别对应 SGD 的 `INFORM/REQUEST/SELECT/CONFIRM`。

### 使用转换工具

```bash
# 转换所有划分（train / val / test）
python benchmark/convert_risawoz_to_sgd.py \
    --data-root ./data/RiSAWOZ \
    --output-dir ./data/RiSAWOZ_SGD

# 只转换验证集
python benchmark/convert_risawoz_to_sgd.py --splits val

# 自定义文件名映射（非标准文件名时使用）
python benchmark/convert_risawoz_to_sgd.py \
    --file-mapping train=train_data.json val=val_data.json
```

### 输出目录结构

```
./data/RiSAWOZ_SGD/
├── conversion_summary.json    # 转换汇总报告
├── train/
│   ├── schema.json            # 12 个领域的服务 Schema
│   ├── dialogues_001.json     # 第 1 批对话（每批最多 1000 条）
│   └── dialogues_002.json     # 第 2 批对话（如有）
├── val/
│   ├── schema.json
│   └── dialogues_001.json
└── test/
    ├── schema.json
    └── dialogues_001.json
```

### 生成的 SGD 格式示例

**schema.json**（景点_1 服务）：
```json
{
  "service_name": "景点_1",
  "description": "景点领域对话服务",
  "slots": [
    {"name": "名称", "description": "名称", "is_categorical": false, "possible_values": []},
    {"name": "类型", "description": "类型", "is_categorical": true, "possible_values": ["博物馆", "公园", "寺庙"]}
  ],
  "intents": [
    {"name": "Inform", "description": "景点领域的Inform意图", "required_slots": [], "optional_slots": {}, "result_slots": []}
  ]
}
```

**dialogues_001.json**（转换后的对话）：
```json
{
  "dialogue_id": "risawoz_001",
  "services": ["景点_1"],
  "turns": [
    {
      "turn_id": "0",
      "speaker": "USER",
      "utterance": "我想找一个博物馆",
      "frames": [{
        "service": "景点_1",
        "state": {"active_intent": "Request", "requested_slots": [], "slot_values": {}},
        "actions": [{"act": "REQUEST", "slot": "名称", "values": [], "canonical_values": []}]
      }]
    },
    {
      "turn_id": "1",
      "speaker": "SYSTEM",
      "utterance": "请问您想去哪个博物馆？",
      "frames": [{
        "service": "景点_1",
        "state": {"active_intent": "NONE", "requested_slots": [], "slot_values": {}},
        "actions": [],
        "service_call": null,
        "service_results": []
      }]
    }
  ]
}
```

### 与 pyTOD 配合使用

转换完成后，可以直接将输出目录作为 SGD 数据集路径，供 pyTOD 读取：

```bash
# 将转换后的数据作为 SGD 数据集路径配置到 pyTOD
export SGD_DATA_ROOT=./data/RiSAWOZ_SGD

# 使用 pyTOD 官方脚本进行训练（参考 pyTOD 文档）
# 详见: https://github.com/apple/ml-pytod
```

> **注意**：由于 RiSAWOZ 没有真实的 API 调用记录，`service_call` 和 `service_results` 字段为空。
> pyTOD 的执行引擎部分需要相应调整，或先使用不依赖执行反馈的评测模式。

详见 [pyTOD 算法文档](../algorithms/pytod.md) 和 [SGD 数据集文档](sgd.md)。

---

## 评测指标

ContextMind 对 RiSAWOZ 使用以下指标（与 TransferTOD 对齐）：

| 指标 | 粒度 | 说明 |
|------|------|------|
| 槽位准确率（Slot Accuracy） | Turn-level | 每轮正确槽位数 / 总槽位数 |
| 联合准确率-严格（Joint Accuracy Strict） | Dialogue-level | 最终状态完全匹配 |
| 联合准确率-软匹配（Joint Accuracy Soft） | Dialogue-level | 允许额外槽位的最终状态匹配 |
| 精确率（Precision） | Dialogue-level | TP / (TP + FP) |
| 召回率（Recall） | Dialogue-level | TP / (TP + FN) |
| F1 分数（F1 Score） | Dialogue-level | 2 × P × R / (P + R) |

---

## 参考文献

```bibtex
@inproceedings{quan-etal-2020-risawoz,
    title = "{R}i{SAWOZ}: A Large-Scale Multi-Domain {W}izard-of-{O}z Dataset with Rich Semantic Annotations for Task-Oriented Dialogue Modeling",
    author = "Quan, Jun and Zhang, Shian and Cao, Qian and Li, Zizhong and Xiong, Deyi",
    booktitle = "Proceedings of the 2020 Conference on Empirical Methods in Natural Language Processing (EMNLP)",
    month = nov,
    year = "2020",
    pages = "930--940",
    url = "https://aclanthology.org/2020.emnlp-main.67",
}
```

## 相关资源

- [RiSAWOZ 官方主页](https://terryqj0107.github.io/RiSAWOZ_webpage/)
- [ContextMind DST 评测脚本](../../benchmark/run_dst_risawoz.py)
- [ContextMind RiSAWOZ 适配器](../../benchmark/datasets/risawoz/adapter.py)
- [RiSAWOZ → SGD 转换工具](../../benchmark/convert_risawoz_to_sgd.py)
- [RiSAWOZ → SGD 转换器核心代码](../../benchmark/datasets/risawoz/sgd_converter.py)
- [pyTOD 算法文档](../algorithms/pytod.md)
- [SGD 数据集文档](sgd.md)
- [评测指标说明](../metrics-explanation.md)
