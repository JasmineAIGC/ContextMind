# SGD 数据集说明文档

## 概述

**SGD**（Schema-Guided Dialogue，模式引导对话）是由 Google Research 发布的大规模任务型对话数据集，是 pyTOD 算法的官方数据集。

- **发布方**: Google Research
- **GitHub**: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
- **论文**: [Towards Scalable Multi-Domain Conversational Agents: The Schema-Guided Dialogue Dataset](https://arxiv.org/abs/1909.05855)（AAAI 2020）
- **pyTOD 官方源码**: https://github.com/apple/ml-pytod
- **DSTC 竞赛**: DSTC8 Track 4

### 数据集规模

| 划分 | 对话数 | 轮次数 | 服务数 |
|------|--------|--------|--------|
| 训练集（train） | 16,142 | 48,426 | 26 |
| 验证集（dev） | 2,482 | 7,446 | 17 |
| 测试集（test） | 4,201 | 12,603 | 21 |

| 统计项 | 数量 |
|--------|------|
| 总对话数 | 22,825 |
| 总话语数 | 68,475+ |
| 覆盖服务数 | 26 个服务 |
| 覆盖领域数 | 16 个领域 |
| 槽位总数 | 214 个 |
| 单服务对话 | ~70% |
| 多服务对话 | ~30% |

---

## 数据集特色

### 1. Schema 引导（Schema-Guided）

每个服务都有预定义的 JSON Schema，描述可调用的 API 及其参数：

```json
{
  "service_name": "Hotels_1",
  "description": "Hotel Service for searching and booking hotels",
  "slots": [
    {
      "name": "hotel_name",
      "description": "Name of the hotel.",
      "is_categorical": false,
      "possible_values": []
    },
    {
      "name": "star_rating",
      "description": "Star rating of the hotel property.",
      "is_categorical": true,
      "possible_values": ["1", "2", "3", "4", "5"]
    }
  ],
  "intents": [
    {
      "name": "SearchHotel",
      "description": "Search for hotels based on criteria",
      "required_slots": ["location"],
      "optional_slots": {
        "number_of_rooms": "1",
        "star_rating": "dontcare"
      },
      "result_slots": ["hotel_name", "price_per_night", "phone_number", "address"]
    },
    {
      "name": "ReserveHotel",
      "description": "Reserve a hotel",
      "required_slots": ["hotel_name", "location", "check_in_date", "number_of_days", "number_of_rooms"],
      "optional_slots": {"pets_welcome": "dontcare"},
      "result_slots": ["total_price"]
    }
  ]
}
```

### 2. 丰富的对话标注

每个对话轮次包含完整的结构化标注：

- **对话行为（Dialogue Acts）**：`INFORM`、`REQUEST`、`SELECT`、`CONFIRM` 等
- **槽位状态（Slot State）**：每个轮次的当前槽位填充情况
- **服务调用记录（Service Call）**：实际调用的 API 名称和参数
- **服务结果（Service Results）**：API 返回的结果数据

### 3. 多服务对话

SGD 的独特之处是支持**单次对话跨多个服务**：

```
用户："我想订明天去旧金山的机票，然后帮我在那边订个酒店。"

对话流程：
  Turn 1-4：Flights_1 服务（查询和预订航班）
  Turn 5-8：Hotels_1 服务（查询和预订酒店）

涉及服务：Flights_1、Hotels_1
涉及 API：SearchFlight → ReserveFlight → SearchHotel → ReserveHotel
```

---

## 目录结构

```
sgd/
├── train/                    # 训练集（16,142 对话）
│   ├── schema.json           # 所有服务的 Schema 定义
│   ├── dialogues_001.json    # 对话文件（每个约 1000 条）
│   ├── dialogues_002.json
│   └── ...（共约 127 个文件）
├── dev/                      # 验证集（2,482 对话）
│   ├── schema.json
│   ├── dialogues_001.json
│   └── ...
└── test/                     # 测试集（4,201 对话）
    ├── schema.json
    ├── dialogues_001.json
    └── ...
```

---

## 关键文件说明

### `schema.json`（服务 Schema 定义）

定义本划分中所有可用服务的 API Schema。训练集包含 26 个服务，验证集和测试集包含子集（用于零样本测试）。

**文件格式**：

```json
[
  {
    "service_name": "Hotels_1",
    "description": "...",
    "slots": [...],
    "intents": [...]
  },
  {
    "service_name": "Restaurants_1",
    "description": "...",
    "slots": [...],
    "intents": [...]
  }
]
```

**注意**：验证集和测试集的 `schema.json` 包含训练集中**未出现**的服务，用于评估零样本泛化能力。

### `dialogues_*.json`（对话数据文件）

每个文件包含一批对话，单条对话结构：

```json
{
  "dialogue_id": "1_00000",
  "services": ["Hotels_1", "Restaurants_1"],
  "turns": [
    {
      "turn_id": 0,
      "speaker": "USER",
      "utterance": "I'd like to find a hotel to stay in.",
      "frames": [
        {
          "service": "Hotels_1",
          "state": {
            "active_intent": "SearchHotel",
            "requested_slots": [],
            "slot_values": {}
          },
          "actions": [
            {
              "act": "INFORM_INTENT",
              "slot": "intent",
              "values": ["SearchHotel"],
              "canonical_values": ["SearchHotel"]
            }
          ]
        }
      ]
    },
    {
      "turn_id": 1,
      "speaker": "SYSTEM",
      "utterance": "Sure! What city would you like to stay in?",
      "frames": [
        {
          "service": "Hotels_1",
          "state": {...},
          "actions": [
            {
              "act": "REQUEST",
              "slot": "location",
              "values": [],
              "canonical_values": []
            }
          ],
          "service_call": null,
          "service_results": []
        }
      ]
    },
    {
      "turn_id": 2,
      "speaker": "USER",
      "utterance": "I need a place in San Jose.",
      "frames": [...]
    },
    {
      "turn_id": 3,
      "speaker": "SYSTEM",
      "utterance": "I found 5 hotels in San Jose...",
      "frames": [
        {
          "service": "Hotels_1",
          "service_call": {
            "method": "SearchHotel",
            "parameters": {"location": "San Jose"}
          },
          "service_results": [
            {"hotel_name": "Marriott", "price_per_night": "200", ...},
            {"hotel_name": "Hilton", "price_per_night": "150", ...}
          ]
        }
      ]
    }
  ]
}
```

**关键字段说明**：

| 字段 | 说明 |
|------|------|
| `dialogue_id` | 对话唯一标识符（格式：`{对话序号}_{对话编号}`） |
| `services` | 本次对话涉及的服务列表 |
| `turns[].speaker` | 发言者：`USER` 或 `SYSTEM` |
| `turns[].utterance` | 话语文本 |
| `turns[].frames` | 每个涉及服务的标注帧 |
| `frames[].service` | 当前帧对应的服务名 |
| `frames[].state` | 当前累积的对话状态（`active_intent`、`slot_values`） |
| `frames[].actions` | 对话行为标注列表 |
| `frames[].service_call` | 实际调用的 API（仅系统轮次） |
| `frames[].service_results` | API 返回的结果（仅系统轮次） |

---

## 26 个服务详情

SGD 数据集涵盖以下 26 个服务（16 个领域）：

| 服务名称 | 领域 | API 类型 | 说明 |
|---------|------|---------|------|
| Hotels_1 | 酒店 | 搜索+预订 | 酒店搜索和预订 |
| Hotels_2 | 酒店 | 搜索 | 另一家酒店供应商 |
| Hotels_3 | 酒店 | 搜索+预订 | 第三家酒店供应商 |
| Restaurants_1 | 餐厅 | 搜索+预订 | 餐厅搜索和预订 |
| Restaurants_2 | 餐厅 | 搜索+预订 | 另一家餐厅供应商 |
| Flights_1 | 航班 | 搜索+预订 | 航班搜索和预订 |
| Flights_2 | 航班 | 搜索+预订 | 另一家航班供应商 |
| Flights_3 | 航班 | 搜索 | 第三家航班供应商 |
| Trains_1 | 火车 | 搜索+预订 | 火车票搜索和购买 |
| Buses_1 | 巴士 | 搜索+预订 | 巴士票搜索和购买 |
| Buses_2 | 巴士 | 搜索+预订 | 另一家巴士供应商 |
| RideSharing_1 | 打车 | 预订 | 叫车服务 |
| RideSharing_2 | 打车 | 预订 | 另一家打车服务 |
| Cars_1 | 租车 | 搜索+预订 | 租车服务 |
| Events_1 | 活动 | 搜索+购票 | 活动查询和购票 |
| Events_2 | 活动 | 搜索+购票 | 另一家活动供应商 |
| Events_3 | 活动 | 搜索 | 第三家活动供应商 |
| Movies_1 | 电影 | 搜索+购票 | 电影查询和购票 |
| Movies_2 | 电影 | 搜索 | 另一家电影供应商 |
| Movies_3 | 电影 | 搜索 | 第三家电影供应商 |
| Music_1 | 音乐 | 播放 | 音乐播放 |
| Music_2 | 音乐 | 播放 | 另一家音乐服务 |
| Media_1 | 媒体 | 播放 | 媒体播放 |
| Services_1 | 服务 | 预约 | 牙医预约 |
| Services_2 | 服务 | 预约 | 理发预约 |
| Services_3 | 服务 | 预约 | 银行账户管理 |

---

## 与 TransferTOD / RiSAWOZ 对比

| 对比项 | SGD | TransferTOD | RiSAWOZ |
|--------|-----|-------------|---------|
| **语言** | 英文 | 中文 | 中文 |
| **领域数** | 16 | 30 | 12 |
| **对话数** | 22,825 | ~9,013 | 11,200 |
| **API 调用标注** | ✅ 有 | ❌ 无 | ❌ 无 |
| **零样本域测试** | ✅ 有 | ✅ 有（OOD） | ❌ 无 |
| **多服务对话** | ✅ 有 | ❌ 无 | ✅ 有 |
| **Schema 定义** | ✅ 官方提供 | 需自行提取 | ✅ 提供 |
| **关联算法** | pyTOD | DST、FnCTOD | DST |

---

## 数据获取

### 方法 1：通过 pyTOD 官方脚本（推荐）

```bash
# 克隆 pyTOD 仓库
git clone https://github.com/apple/ml-pytod.git
cd ml-pytod

# 使用官方脚本下载 SGD 数据
chmod +x scripts/fetch_data.sh
bash scripts/fetch_data.sh
```

### 方法 2：直接从 GitHub 下载

```bash
# 克隆 SGD 官方仓库
git clone https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.git

# 数据位于仓库根目录下
ls dstc8-schema-guided-dialogue/
# train/  dev/  test/
```

### 方法 3：从 HuggingFace Datasets 加载

```python
from datasets import load_dataset

# 加载 SGD 数据集
dataset = load_dataset("schema_guided_diaog")

# 查看训练集
print(dataset["train"][0])
```

---

## 在 ContextMind 中使用（计划中）

> ⚠️ **注意**：SGDAdapter 尚未实现，以下为计划接口。

预期目录结构：

```
./data/SGD/
├── train/
│   ├── schema.json
│   └── dialogues_*.json
├── dev/
│   ├── schema.json
│   └── dialogues_*.json
└── test/
    ├── schema.json
    └── dialogues_*.json
```

计划评测命令：

```bash
# pyTOD on SGD（待实现）
python benchmark/run_pytod_sgd.py --split dev

# DST on SGD（待实现）
python benchmark/run_dst_sgd.py --split dev --limit 100
```

---

## 评测指标

SGD 使用 DSTC8 官方评测指标：

| 指标 | 说明 |
|------|------|
| **Joint Goal Accuracy** | 所有槽位完全正确的对话比例 |
| **Slot Tagging F1** | 槽位值提取的 F1 分数 |
| **Intent Accuracy** | 意图识别准确率 |
| **Requested Slots F1** | 请求槽位的 F1 分数 |
| **Average Goal Accuracy** | 跨所有服务的平均目标准确率 |

---

## 参考文献

```bibtex
@inproceedings{rastogi2020towards,
  title={Towards Scalable Multi-Domain Conversational Agents: The Schema-Guided Dialogue Dataset},
  author={Rastogi, Abhinav and Zang, Xiaoxue and Sunkara, Srinivas and Gupta, Raghav and Khaitan, Pranav},
  booktitle={AAAI 2020},
  year={2020},
  url={https://arxiv.org/abs/1909.05855}
}
```

## 相关资源

- [SGD 官方 GitHub](https://github.com/google-research-datasets/dstc8-schema-guided-dialogue)
- [pyTOD 官方 GitHub](https://github.com/apple/ml-pytod)
- [pyTOD 论文](https://arxiv.org/abs/2508.15456)
- [pyTOD 算法文档](../algorithms/pytod.md)
- [DST 算法文档](../algorithms/dst.md)
- [FnCTOD 算法文档](../algorithms/fnctod.md)
