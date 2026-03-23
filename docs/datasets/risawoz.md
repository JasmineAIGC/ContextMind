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

RiSAWOZ 数据集解压后的**实际**目录结构如下：

```
RiSAWOZ-data/
├── conversion_summary.json                     # 转换摘要（非官方）
├── dataset_split_ids_dict.json                 # 数据集划分 ID 索引
├── RiSAWOZ-Database-and-Ontology/              # 知识库和本体（解压后）
│   ├── DB/                                     # 各领域数据库
│   │   ├── attraction_db.json    # 景点
│   │   ├── car_db.json           # 汽车
│   │   ├── class_db.json         # 辅导班
│   │   ├── flight_db.json        # 航班
│   │   ├── hospital_db.json      # 医院
│   │   ├── hotel_db.json         # 酒店
│   │   ├── movie_db.json         # 电影
│   │   ├── pc_db.json            # 电脑
│   │   ├── restaurant_db.json    # 餐厅
│   │   ├── train_db.json         # 火车
│   │   ├── tv_db.json            # 电视剧
│   │   └── weather_db.json       # 天气
│   └── Ontology/
│       └── ontology.json         # 所有领域的槽位本体定义
├── source-data/                                # 完整原始标注数据（推荐）
│   ├── all_(11200)_new.json      # 完整数据集（全部 11200 条）
│   ├── all_train10000.json       # 训练集（10000 条）
│   ├── all_dev600.json           # 验证集（600 条）
│   ├── all_test600_new.json      # 测试集（全部 600 条）
│   ├── multi_test230_new.json    # 多领域测试集（230 条）
│   └── single_test370_new.json   # 单领域测试集（370 条）
├── task1-data-NLU/                             # 任务1：NLU（IOB 格式）
│   ├── train_data.json
│   ├── val_data.json
│   ├── test_data.json_all
│   ├── test_data.json_multi
│   └── test_data.json_single
├── task2-data-DST/                             # 任务2：DST 专用格式
│   ├── dst_all_train10000.json   # 训练集（10000 条）
│   ├── dst_all_dev600.json       # 验证集（600 条）
│   ├── dst_all_test600_new.json  # 测试集（全部 600 条）
│   ├── dst_multi_test230_new.json   # 多领域测试（230 条）
│   └── dst_single_test370_new.json  # 单领域测试（370 条）
├── task3-data-E2E-Context-to-text/             # 任务3：端到端生成（标准命名）
│   ├── train.json
│   ├── val.json
│   ├── test.json
│   └── preprocessed-data/
│       ├── temp_for_damd.json
│       ├── testListFile.json_all
│       ├── testListFile.json_multi
│       ├── testListFile.json_single
│       └── valListFile.json
├── task4-data-Coreference resolution/          # 任务4：共指消解（CoNLL 格式）
│   ├── train.chinese.v4_gold_conll
│   ├── dev.chinese.v4_gold_conll
│   ├── all_test/
│   │   └── test.chinese.v4_gold_conll
│   ├── multi_test/
│   │   └── test.chinese.v4_gold_conll
│   └── single_test/
│       └── test.chinese.v4_gold_conll
└── task5-data-Unified-generative-ellipsis-and-coreference-resolution/
    ├── all_(11200)_new.json      # 与 source-data 命名相同
    ├── all_train10000.json
    ├── all_dev600.json
    ├── all_test600_new.json
    ├── multi_test230_new.json
    └── single_test370_new.json
```

---

### `source-data/`（完整原始标注数据，**推荐**）

**推荐用于 SGD 格式转换**，包含 RiSAWOZ 数据集的全部原始标注数据。

| 文件 | 对话数 | 说明 |
|------|--------|------|
| `all_(11200)_new.json` | 11,200 | 完整数据集（含所有划分） |
| `all_train10000.json` | 10,000 | 训练集 |
| `all_dev600.json` | 600 | 验证集 |
| `all_test600_new.json` | 600 | 测试集（全部） |
| `multi_test230_new.json` | 230 | 多领域测试子集 |
| `single_test370_new.json` | 370 | 单领域测试子集 |

每条对话的数据格式（每轮分别存储 usr/sys 两个 dict）：

```json
{
  "dialogue_id": "hotel_0001",
  "goal": {
    "description": "您需要预订一家酒店...",
    "constraints": {"位置": "西城区", "价格范围": "经济型"}
  },
  "domains": ["酒店"],
  "dialogue": [
    {
      "turn_id": 0,
      "role": "usr",
      "utterance": "我想订一家西城区的经济型酒店",
      "dialogue_act": [
        {"act": "Inform", "domain": "酒店", "slot": "位置", "value": "西城区"}
      ],
      "belief_state": [
        {"domain": "酒店", "slot": "位置", "value": "西城区"},
        {"domain": "酒店", "slot": "价格范围", "value": "经济型"}
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
| `domains` | list | 本次对话涉及的领域列表 |
| `dialogue` | list | 对话轮次列表（usr/sys 各占一个 dict） |
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

### `RiSAWOZ-Database-and-Ontology/`（数据库与本体）

包含 12 个领域的知识库和槽位本体定义：

```
RiSAWOZ-Database-and-Ontology/
├── DB/
│   ├── attraction_db.json   # 景点知识库
│   ├── hotel_db.json        # 酒店知识库
│   ├── restaurant_db.json   # 餐厅知识库
│   ├── flight_db.json       # 航班知识库
│   ├── hospital_db.json     # 医院知识库
│   ├── movie_db.json        # 电影知识库
│   ├── tv_db.json           # 电视剧知识库
│   ├── train_db.json        # 火车知识库
│   ├── weather_db.json      # 天气知识库
│   ├── car_db.json          # 汽车知识库
│   ├── class_db.json        # 辅导班知识库
│   └── pc_db.json           # 电脑知识库
└── Ontology/
    └── ontology.json        # 所有领域的槽位定义与合法值列表
```

**本体格式示例**：

```json
{
  "酒店": {
    "位置": ["西城区", "东城区", "朝阳区", "海淀区", ...],
    "价格范围": ["经济型", "舒适型", "豪华型"],
    "星级": ["二星级", "三星级", "四星级", "五星级"]
  }
}
```

---

### `task1-data-NLU/`（任务1：自然语言理解）

包含**意图检测**和**槽位填充**任务的训练数据，采用 JSON 格式。

**注意**：❌ 此格式**不支持**转换为 SGD 格式（无完整对话结构）。

```
task1-data-NLU/
├── train_data.json
├── val_data.json
├── test_data.json_all      # 全部测试集
├── test_data.json_multi    # 多领域测试子集
└── test_data.json_single   # 单领域测试子集
```

---

### `task2-data-DST/`（任务2：对话状态追踪）

包含**对话状态追踪**（DST）任务专用数据，每轮合并了 user_utterance 和 system_utterance。

| 文件 | 对话数 | 说明 |
|------|--------|------|
| `dst_all_train10000.json` | 10,000 | 训练集 |
| `dst_all_dev600.json` | 600 | 验证集 |
| `dst_all_test600_new.json` | 600 | 测试集（全部） |
| `dst_multi_test230_new.json` | 230 | 多领域测试子集 |
| `dst_single_test370_new.json` | 370 | 单领域测试子集 |

**数据特点**：每轮 dict 同时包含 `user_utterance`、`system_utterance`、`belief_state` 和 `user_acts`，与 ContextMind 的 `RiSAWOZAdapter` 直接兼容。

**Belief State 格式**：

```json
"belief_state": [
  {"domain": "酒店", "slot": "位置", "value": "西城区"},
  {"domain": "酒店", "slot": "价格范围", "value": "经济型"}
]
```

---

### `task3-data-E2E-Context-to-text/`（任务3：端到端上下文生成）

包含**端到端对话生成**任务数据，使用**标准文件命名**（train/val/test）。

```
task3-data-E2E-Context-to-text/
├── train.json
├── val.json
├── test.json
└── preprocessed-data/
    ├── temp_for_damd.json
    ├── testListFile.json_all
    ├── testListFile.json_multi
    ├── testListFile.json_single
    └── valListFile.json
```

**注意**：⚠️ 此格式缺少 `belief_state`，转换为 SGD 格式时 schema 质量较低。

---

### `task4-data-Coreference resolution/`（任务4：共指消解）

包含**对话共指消解**任务数据，采用 **CoNLL 格式**（不可转换为 SGD）。

```
task4-data-Coreference resolution/
├── train.chinese.v4_gold_conll
├── dev.chinese.v4_gold_conll
├── all_test/
│   └── test.chinese.v4_gold_conll
├── multi_test/
│   └── test.chinese.v4_gold_conll
└── single_test/
    └── test.chinese.v4_gold_conll
```

**注意**：❌ 此格式**不支持**转换为 SGD 格式（CoNLL 格式无对话状态信息）。

---

### `task5-data-Unified-.../`（任务5：统一省略与共指消解）

包含**统一生成式省略消解与共指消解**任务数据，文件命名与 `source-data/` 完全相同：

| 文件 | 对话数 | 说明 |
|------|--------|------|
| `all_(11200)_new.json` | 11,200 | 完整数据集 |
| `all_train10000.json` | 10,000 | 训练集 |
| `all_dev600.json` | 600 | 验证集 |
| `all_test600_new.json` | 600 | 测试集 |
| `multi_test230_new.json` | 230 | 多领域测试 |
| `single_test370_new.json` | 370 | 单领域测试 |

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

ContextMind 支持 `source-data/` 和 `task2-data-DST/` 两种格式，通过 `RiSAWOZAdapter` 和 `RISAWOZ_FILE_MAPPINGS` 自动管理文件名映射。

### 下载并准备数据

```bash
# 克隆仓库
git clone https://github.com/terryqj0107/RiSAWOZ.git

# 将 RiSAWOZ-data 目录复制到 data/
cp -r RiSAWOZ/RiSAWOZ-data ./data/
# 现在 ./data/RiSAWOZ-data/ 下应有 source-data/ task2-data-DST/ 等子目录
```

数据目录结构（使用 source-data/）：

```
./data/RiSAWOZ-data/
└── source-data/
    ├── all_train10000.json      ← 训练集
    ├── all_dev600.json          ← 验证集
    ├── all_test600_new.json     ← 测试集
    ├── multi_test230_new.json
    └── single_test370_new.json
```

### 运行 DST 评测

```bash
# 评测验证集（source-data 格式，自动应用文件映射）
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --source-format source-data

# 评测特定领域
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --source-format source-data --domain 酒店 --split val

# 使用 task2-dst 格式
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ-data/task2-data-DST \
    --source-format task2-dst

# 限制数量快速测试（多领域测试子集）
python benchmark/run_dst_risawoz.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --source-format source-data \
    --test-file multi_test230_new.json \
    --split test --limit 10 --verbose
```

---

## 转换为 SGD 格式（用于 pyTOD 训练和测试）

由于 SGD 数据集是英文的，ContextMind 提供了一个转换工具，可将 RiSAWOZ 转换为 SGD 格式，从而在中文数据集上使用 pyTOD 算法进行训练和测试。

### 哪个数据目录可以转换为 SGD 格式？

| 目录 | 兼容性 | `--source-format` | 文件映射 |
|------|--------|-------------------|---------|
| `source-data/` | ✅ **首选** | `source-data` | train→`all_train10000.json`, val→`all_dev600.json`, test→`all_test600_new.json` |
| `task2-data-DST/` | ✅ 支持 | `task2-dst` | train→`dst_all_train10000.json`, val→`dst_all_dev600.json`, test→`dst_all_test600_new.json` |
| `task5-data-Unified-.../` | ✅ 支持 | `task5-unified` | 与 source-data 相同文件名 |
| `task3-data-E2E-Context-to-text/` | ⚠️ 部分 | `task3-e2e` | train→`train.json`, val→`val.json`, test→`test.json`（缺 belief_state） |
| `task1-data-NLU/` | ❌ **不支持** | — | JSON 格式但无对话状态，无法转换 |
| `task4-data-Coreference resolution/` | ❌ **不支持** | — | CoNLL 格式，无法转换 |

### 两种主要格式的数据结构对比

| 对比项 | `source-data/`（推荐） | `task2-data-DST/` |
|--------|----------------------|-------------------|
| 每轮存储方式 | 两个独立 dict（role=usr + role=sys） | 一个合并 dict |
| 用户行为字段 | `dialogue_act: [{act,domain,slot,value}]` | `user_acts: [[intent,domain,slot,value]]` |
| 训练集文件名 | `all_train10000.json` | `dst_all_train10000.json` |
| 验证集文件名 | `all_dev600.json` | `dst_all_dev600.json` |
| 测试集文件名 | `all_test600_new.json` | `dst_all_test600_new.json` |

### 格式映射关系

| RiSAWOZ | SGD |
|---------|-----|
| `domain` (如 "景点") | `service_name` (如 "景点_1") |
| usr+sys 一对轮次 | 2 条 SGD turns（USER + SYSTEM）|
| `belief_state[].{domain, slot, value}` | `state.slot_values.{slot: [value]}` |
| `dialogue_act` / `user_acts` | `frames[].actions[{act, slot, values}]` |
| 动态从数据中提取 | `schema.json`（每个域的服务 Schema） |

意图类型映射：`Inform/Request/Select/Confirm` → `INFORM/REQUEST/SELECT/CONFIRM`。

### 使用转换工具

```bash
# 使用 source-data/（推荐）
python benchmark/convert_risawoz_to_sgd.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --output-dir ./data/RiSAWOZ_SGD \
    --source-format source-data

# 使用 task2-data-DST/
python benchmark/convert_risawoz_to_sgd.py \
    --data-root ./data/RiSAWOZ-data/task2-data-DST \
    --output-dir ./data/RiSAWOZ_SGD \
    --source-format task2-dst

# 只转换验证集
python benchmark/convert_risawoz_to_sgd.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --source-format source-data --splits val

# 用多领域测试文件覆盖默认测试集
python benchmark/convert_risawoz_to_sgd.py \
    --data-root ./data/RiSAWOZ-data/source-data \
    --source-format source-data \
    --file-mapping test=multi_test230_new.json
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
