# TransferTOD 数据集说明文档

## 概述

**TransferTOD** 是一个大规模中文多领域任务型对话数据集，发表于 EMNLP 2024，重点研究跨领域迁移能力。

- **GitHub**: https://github.com/KongLongGeFDU/TransferTOD
- **论文**: [TransferTOD: A Generalizable Chinese Multi-Domain Task-Oriented Dialogue System with Transfer Capabilities](https://aclanthology.org/2024.emnlp-main.710.pdf)
- **ArXiv**: https://arxiv.org/abs/2407.21693
- **会议**: EMNLP 2024 (Main)
- **模型**: [TransferTOD-7B](https://www.modelscope.cn/models/Mee1ong/TransferTOD-7B)（基于 Qwen-7B 微调）

### 数据集规模

| 划分 | 领域数 | 槽位数 | 对话数 | 总轮次数 | 均摊槽位/对话 | 均摊 Token/轮次 |
|------|--------|--------|--------|---------|--------------|----------------|
| 训练集 | 27 | 188 | 4,320 | 28,680 | 10.3 | 66.4 |
| 域内测试集（ID Test） | 27 | 188 | 540 | 3,585 | 10.3 | 66.4 |
| 域外测试集（OOD Test） | 3 | 27 | 600 | 3,700 | 9.7 | 76.8 |

> **ID Test**：域内测试，测试集与训练集使用相同领域。
> **OOD Test**：域外测试，测试集包含训练时未见过的 3 个领域（送水、保洁、快递）。

---

## 数据集获取

```bash
git clone https://github.com/KongLongGeFDU/TransferTOD.git
```

---

## 目录结构与文件说明

```
TransferTOD/
├── README.md                          # 项目说明文档
├── .gitattributes                     # Git 属性配置（LFS 大文件配置）
├── .gitignore                         # Git 忽略文件配置
├── data/                              # 所有数据文件目录（核心）
│   ├── data_generate_template.ipynb   # 数据生成模板（Jupyter Notebook）
│   ├── data_process.py                # 数据处理脚本
│   ├── gpt_generate.ipynb             # GPT 数据生成脚本（Jupyter Notebook）
│   ├── utils.py                       # 数据处理工具函数
│   ├── raw_data/                      # 原始对话数据（核心评测数据）
│   │   ├── clean/                     # 干净对话数据（~6,000 条，标准评测用）
│   │   │   ├── 1-hotel/               # 领域1：酒店
│   │   │   ├── 2-restaurant/          # 领域2：餐厅
│   │   │   ├── 3-gastronomy/          # 领域3：美食
│   │   │   ├── 4-takeaways/           # 领域4：外卖
│   │   │   ├── 5-train_ticket/        # 领域5：火车票
│   │   │   ├── 6-air_ticket/          # 领域6：机票
│   │   │   ├── 7-ocean_liner/         # 领域7：邮轮
│   │   │   ├── 8-car_rent/            # 领域8：租车
│   │   │   ├── 9-house_rent/          # 领域9：租房
│   │   │   ├── 10-movie/              # 领域10：电影
│   │   │   ├── 11-concert/            # 领域11：音乐会
│   │   │   ├── 12-museum/             # 领域12：博物馆
│   │   │   ├── 13-vacation_villages/  # 领域13：度假村
│   │   │   ├── 14-shopping/           # 领域14：购物
│   │   │   ├── 15-calling_card/       # 领域15：电话卡
│   │   │   ├── 16-hospital/           # 领域16：医院
│   │   │   ├── 17-dentistry/          # 领域17：牙科
│   │   │   ├── 18-beautysalon/        # 领域18：美容院
│   │   │   ├── 19-gym/                # 领域19：健身房
│   │   │   ├── 20-photography/        # 领域20：摄影
│   │   │   ├── 21-appliance_repair/   # 领域21：家电维修
│   │   │   ├── 22-lawyer/             # 领域22：律师
│   │   │   ├── 23-tutoring/           # 领域23：培训班
│   │   │   ├── 24-moving/             # 领域24：搬家
│   │   │   ├── 25-housekeeping/       # 领域25：家政保洁
│   │   │   ├── 26-hairdresser/        # 领域26：理发店
│   │   │   ├── 27-laundry/            # 领域27：洗衣
│   │   │   ├── 28-water_delivery/     # 领域28：送水（OOD 测试域）
│   │   │   ├── 29-sanitation/         # 领域29：保洁（OOD 测试域）
│   │   │   └── 30-courier/            # 领域30：快递（OOD 测试域）
│   │   ├── noise/                     # 含噪声对话数据（~3,013 条，鲁棒性测试用）
│   │   │   └── [同 clean/ 的领域目录结构]
│   │   ├── clean_gpt/                 # GPT 生成的干净对话（未经人工校验）
│   │   ├── clean_gpt_human/           # GPT 生成 + 人工校验的干净对话
│   │   ├── noise_gpt/                 # GPT 生成的含噪声对话（未经人工校验）
│   │   ├── noise_gpt_human/           # GPT 生成 + 人工校验的含噪声对话
│   │   └── belle_data/                # BELLE 通用对话数据（用于混合训练）
│   ├── fine_tune_1/                   # 第一阶段微调数据（27 个 ID 领域）
│   │   ├── v1/                        # 版本 1（基础版）
│   │   ├── v2/                        # 版本 2（改进版）
│   │   ├── v3/                        # 版本 3
│   │   └── v4/                        # 版本 4（最新版）
│   └── fine_tune_2/                   # 第二阶段微调数据（3 个 OOD 领域）
│       ├── 28_water_delivery/         # OOD 领域：送水
│       ├── 29_sanitation/             # OOD 领域：保洁
│       └── 30_courier/               # OOD 领域：快递
├── fine_tune/                         # 模型微调代码
│   └── scripts/
│       ├── finetune_full.sh           # 全参数微调脚本
│       └── finetune_lora.sh           # LoRA 微调脚本
└── inference/                         # 推理与评测代码
    ├── inference.py                   # 推理主脚本
    ├── eval.py                        # 评测脚本
    ├── examples.json                  # Few-shot 示例文件
    └── inference_and_eval.sh          # 推理+评测一键脚本
```

---

## 详细文件说明

### `data/` 目录（数据根目录）

所有原始数据、处理脚本和微调数据均位于此目录。

#### `data/data_generate_template.ipynb`

数据生成模板 Jupyter Notebook，展示如何基于领域本体和对话模板生成新的对话数据，供研究者扩展数据集时参考。

#### `data/data_process.py`

数据处理 Python 脚本，负责：
- 将原始对话数据转换为微调所需的指令格式
- 合并 clean/noise 数据
- 与 BELLE 通用数据混合

#### `data/gpt_generate.ipynb`

使用 GPT API 生成对话数据的 Jupyter Notebook，包含：
- Prompt 模板设计
- GPT 生成调用示例
- 生成结果后处理

#### `data/utils.py`

数据处理工具函数库，包含：
- 数据格式转换函数
- 槽位提取和验证工具
- 数据统计分析函数

---

### `data/raw_data/` 目录（原始对话数据）

ContextMind 主要使用此目录中的数据进行 DST 和 FnCTOD 评测。

#### `data/raw_data/clean/`（干净对话数据，约 6,000 条）

高质量的规范化对话，适合标准模型评测。每个领域子目录包含若干 JSON 文件：

```
clean/1-hotel/
├── hotel_clean_1.json   # 批次1的酒店领域对话
├── hotel_clean_2.json   # 批次2的酒店领域对话
├── hotel_clean_3.json   # 批次3的酒店领域对话
└── hotel_clean_4.json   # 批次4的酒店领域对话
```

每个 JSON 文件包含该领域的对话列表，单条对话格式：

```json
{
  "dialogue_id": "hotel_clean_1_001",
  "domain": "酒店",
  "goal": "帮我预订一家位于市中心的四星级酒店，需要大床房，入住时间是明天",
  "dialogue": [
    {
      "turn_id": 0,
      "role": "user",
      "utterance": "我想订一家市中心的四星级酒店",
      "expected_slots": {
        "酒店-位置": "市中心",
        "酒店-星级": "四星级"
      }
    },
    {
      "turn_id": 1,
      "role": "system",
      "utterance": "好的，请问您需要哪种房型？"
    },
    {
      "turn_id": 2,
      "role": "user",
      "utterance": "大床房，明天入住",
      "expected_slots": {
        "酒店-位置": "市中心",
        "酒店-星级": "四星级",
        "酒店-房型": "大床房",
        "酒店-入住日期": "明天"
      }
    }
  ],
  "final_state": {
    "酒店-位置": "市中心",
    "酒店-星级": "四星级",
    "酒店-房型": "大床房",
    "酒店-入住日期": "明天"
  }
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `dialogue_id` | 对话唯一标识符 |
| `domain` | 所属领域 |
| `goal` | 对话目标（自然语言描述） |
| `dialogue` | 对话轮次列表 |
| `dialogue[].turn_id` | 轮次编号 |
| `dialogue[].role` | 发言角色（user/system） |
| `dialogue[].utterance` | 话语文本 |
| `dialogue[].expected_slots` | 该轮次的累积槽位状态（仅用户轮次有此字段） |
| `final_state` | 对话最终槽位状态 |

#### `data/raw_data/noise/`（含噪声对话数据，约 3,013 条）

模拟真实场景中的非规范输入，包含：
- 拼写错误（如"酒店" → "酒旅"）
- 口语化表达（如"那个啥" "随便"）
- 不完整句子
- 方言词汇

| 数据类型 | 数量 | 适用场景 |
|---------|------|---------|
| clean | ~6,000 | 标准评测、模型训练 |
| noise | ~3,013 | 鲁棒性测试 |
| clean + noise | ~9,013 | 全量评测 |

#### `data/raw_data/clean_gpt/` 和 `data/raw_data/clean_gpt_human/`

- `clean_gpt/`：使用 GPT 自动生成的干净对话，未经人工校验
- `clean_gpt_human/`：GPT 生成后由人工校验和修正的干净对话，质量更高

#### `data/raw_data/noise_gpt/` 和 `data/raw_data/noise_gpt_human/`

- `noise_gpt/`：使用 GPT 自动生成的含噪声对话，未经人工校验
- `noise_gpt_human/`：GPT 生成后由人工校验的含噪声对话

#### `data/raw_data/belle_data/`

[BELLE](https://github.com/LianjiaTech/BELLE) 通用中文指令对话数据，用于第一阶段微调时与 TOD 数据混合，增强模型的通用对话能力。

---

### `data/fine_tune_1/`（第一阶段微调数据）

27 个域内领域的微调数据，包含多个版本（v1~v4），逐版本改进数据质量和格式。

每个版本目录结构：

```
fine_tune_1/v1/
├── train.json       # 训练集（混合了 TOD 数据和 BELLE 通用数据）
├── train_slot.json  # 纯 TOD 槽位提取训练数据（无 BELLE 数据）
├── valid.json       # 验证集
├── test.json        # 域内测试集（27 个领域，540 条对话）
└── info.json        # 数据集元信息（版本、统计信息）
```

**文件说明**：

| 文件 | 说明 |
|------|------|
| `train.json` | 完整训练集，`train_slot.json` 与等量 BELLE 数据的混合 |
| `train_slot.json` | 纯 TOD 对话的槽位提取训练数据 |
| `valid.json` | 验证集，用于训练过程中的模型选择 |
| `test.json` | 域内测试集（In-Domain），540 条对话，27 个领域各 20 条 |
| `info.json` | 数据集信息，包含版本号、统计数量、领域列表等元数据 |

**数据格式**（指令微调格式）：

```json
{
  "instruction": "你是一个任务型对话系统，请从以下对话中提取槽位信息...",
  "input": "用户：我想订一家市中心的四星级酒店\n系统：...",
  "output": "{\"酒店-位置\": \"市中心\", \"酒店-星级\": \"四星级\"}"
}
```

---

### `data/fine_tune_2/`（第二阶段微调数据）

3 个域外（OOD）领域的微调数据，用于测试模型的跨领域迁移能力。

```
fine_tune_2/
├── 28_water_delivery/   # 送水领域（OOD）
├── 29_sanitation/       # 保洁领域（OOD）
└── 30_courier/          # 快递领域（OOD）
```

每个领域目录包含 OOD 领域的训练和测试数据（格式与 `fine_tune_1` 相同）。OOD 测试集共 600 条对话，每个领域 200 条。

---

### `fine_tune/` 目录（微调代码）

包含对 Qwen-7B 进行微调的代码和脚本：

| 文件 | 说明 |
|------|------|
| `scripts/finetune_full.sh` | 全参数微调启动脚本（GPU 需求高） |
| `scripts/finetune_lora.sh` | LoRA 高效微调启动脚本（资源需求低） |

---

### `inference/` 目录（推理与评测代码）

| 文件 | 说明 |
|------|------|
| `inference.py` | 推理主脚本，加载模型并对测试集进行预测 |
| `eval.py` | 评测脚本，计算 Joint Accuracy、Slot Accuracy、F1 等指标 |
| `examples.json` | Few-shot 示例文件，包含各领域的 in-context 示例 |
| `inference_and_eval.sh` | 一键运行推理+评测的 Shell 脚本 |

---

## 30 个领域详情

TransferTOD 涵盖 30 个中文生活服务领域（前 27 个为 ID 领域，后 3 个为 OOD 领域）：

| 编号 | 英文名称 | 中文名称 | 训练/测试 |
|------|---------|---------|----------|
| 1 | hotel | 酒店 | ID |
| 2 | restaurant | 餐厅 | ID |
| 3 | gastronomy | 美食 | ID |
| 4 | takeaways | 外卖 | ID |
| 5 | train_ticket | 火车票 | ID |
| 6 | air_ticket | 机票 | ID |
| 7 | ocean_liner | 邮轮 | ID |
| 8 | car_rent | 租车 | ID |
| 9 | house_rent | 租房 | ID |
| 10 | movie | 电影 | ID |
| 11 | concert | 音乐会 | ID |
| 12 | museum | 博物馆 | ID |
| 13 | vacation_villages | 度假村 | ID |
| 14 | shopping | 购物 | ID |
| 15 | calling_card | 电话卡 | ID |
| 16 | hospital | 医院 | ID |
| 17 | dentistry | 牙科 | ID |
| 18 | beautysalon | 美容院 | ID |
| 19 | gym | 健身房 | ID |
| 20 | photography | 摄影 | ID |
| 21 | appliance_repair | 家电维修 | ID |
| 22 | lawyer | 律师 | ID |
| 23 | tutoring | 培训班 | ID |
| 24 | moving | 搬家 | ID |
| 25 | housekeeping | 家政保洁 | ID |
| 26 | hairdresser | 理发店 | ID |
| 27 | laundry | 洗衣 | ID |
| 28 | water_delivery | 送水 | **OOD** |
| 29 | sanitation | 保洁 | **OOD** |
| 30 | courier | 快递 | **OOD** |

---

## 在 ContextMind 中使用

### 数据目录结构要求

ContextMind 的 `TransferTODAdapter` 要求数据按如下结构存放：

```
./data/TransferTOD/
└── data/
    └── raw_data/
        ├── clean/
        │   ├── 1-hotel/
        │   ├── 2-restaurant/
        │   └── ...（共 30 个领域目录）
        └── noise/
            └── ...（同 clean/ 结构）
```

### DST 评测

```bash
# 使用干净数据评测所有领域（推荐）
python benchmark/run_dst_transfertod.py --data-root ./data/TransferTOD --data-type clean

# 使用全部数据（clean + noise）
python benchmark/run_dst_transfertod.py --data-root ./data/TransferTOD

# 评测特定领域，限制 100 条
python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 100
```

### FnCTOD 评测

```bash
# 运行 FnCTOD 评测
python benchmark/run_fnctod_transfertod.py --data-root ./data/TransferTOD --data-type clean
```

### 提取领域 Schema

```bash
# 提取所有领域的 Schema 定义
python benchmark/extract_transfertod_schemas.py \
    --data-root ./data/TransferTOD \
    --output transfertod_schemas.json
```

### 对话数量说明

| 参数 `--data-type` | 含义 | 对话数量 |
|-------------------|------|---------|
| `clean` | 仅 clean 数据 | ~6,000 |
| `noise` | 仅 noise 数据 | ~3,013 |
| 未指定（默认） | clean + noise 全量 | ~9,013 |

> 详见本文末尾"数据数量差异说明"章节

---

## 评测指标

TransferTOD 使用以下评测指标：

| 指标 | 粒度 | 说明 |
|------|------|------|
| 槽位准确率（Slot Accuracy） | Turn-level | 每轮正确槽位数 / 总槽位数 |
| 联合准确率-严格（Joint Accuracy Strict） | Dialogue-level | 最终状态完全匹配 |
| 联合准确率-软匹配（Joint Accuracy Soft） | Dialogue-level | 允许额外槽位的匹配 |
| 精确率（Precision） | Dialogue-level | TP / (TP + FP) |
| 召回率（Recall） | Dialogue-level | TP / (TP + FN) |
| F1 分数（F1 Score） | Dialogue-level | 2 × P × R / (P + R) |

---

## 参考文献

```bibtex
@inproceedings{DBLP:conf/emnlp/ZhangHWLZDSDZYZ24,
  author = {Ming Zhang and Caishuang Huang and Yilong Wu and Shichun Liu and Huiyuan Zheng and Yurui Dong and Yujiong Shen and Shihan Dou and Jun Zhao and Junjie Ye and Qi Zhang and Tao Gui and Xuanjing Huang},
  title = {TransferTOD: A Generalizable Chinese Multi-Domain Task-Oriented Dialogue System with Transfer Capabilities},
  booktitle = {Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing, EMNLP 2024},
  pages = {12750--12771},
  year = {2024},
  url = {https://aclanthology.org/2024.emnlp-main.710},
}
```

## 相关资源

- [TransferTOD GitHub](https://github.com/KongLongGeFDU/TransferTOD)
- [TransferTOD-7B 模型](https://www.modelscope.cn/models/Mee1ong/TransferTOD-7B)
- [ContextMind DST 评测脚本](../../benchmark/run_dst_transfertod.py)
- [ContextMind FnCTOD 评测脚本](../../benchmark/run_fnctod_transfertod.py)
- [ContextMind TransferTOD 适配器](../../benchmark/datasets/transfertod/adapter.py)
- [评测指标说明](../metrics-explanation.md)

---

## 数据数量差异说明

**常见问题**：DST 评测找到 9013 个对话，FnCTOD 评测找到 6000 个对话，为什么不同？

TransferTOD 包含两种数据类型：

| 类型 | 数量（约） | 特点 |
|------|-----------|------|
| Clean | ~6000 | 干净、高质量，适合标准评测 |
| Noise | ~3013 | 含拼写错误、口语化表达，适合鲁棒性测试 |

- 未指定 `--data-type` 时默认加载全部（clean + noise）→ 约 9013 条
- 指定 `--data-type clean` 时只加载 clean 数据 → 约 6000 条

**建议**：始终明确指定 `--data-type` 参数，以确保评测结果可复现。
