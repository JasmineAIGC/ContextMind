# ContextMind - TransferTOD 测试框架

## ⚠️ 重要通知

**DST模式评测已迁移到 `benchmark/run_dst_transfertod.py`**

原 `tests/test_dst_transfertod.py` 已被废弃，请使用统一的评测脚本：

```bash
# 推荐使用方式
python benchmark/run_dst_transfertod.py
python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 10
```

---

## 📋 目录结构

```
tests/
├── __init__.py                      # 测试包初始化
├── adapters/                        # 数据集适配器
│   ├── __init__.py                  # 适配器包导出
│   ├── base_adapter.py              # 适配器抽象基类
│   └── transfertod_adapter.py       # TransferTOD数据集适配器
├── test_dst_transfertod.py          # [已废弃] DST模式测试脚本 -> 使用 benchmark/run_dst_transfertod.py
├── test_fnctod_transfertod.py       # FnCTOD模式测试脚本
├── intent_evaluator.py              # 意图评测器
├── intent_label_loader.py           # 意图标签加载器
└── README.md                        # 本文档

benchmark/                           # 评测脚本（推荐）
├── run_dst_transfertod.py           # DST模式评测脚本（推荐）
└── run_fnctod_transfertod.py        # FnCTOD模式评测脚本

tests_legacy/                        # 原有测试（已重命名）
├── test_dst_mode.py                 # 原DST模式测试
├── test_evolve_mode.py              # 原进化模式测试
└── ...
```

---

## 🎯 功能概述

本测试框架为 ContextMind 项目提供基于 **TransferTOD数据集** 的标准化测试能力，支持：

1. **数据集适配器架构**：统一的数据加载接口，便于扩展其他数据集
2. **DST模式评测**：测试 DialogueStateTracker 的槽位提取准确性（推荐使用 `benchmark/run_dst_transfertod.py`）
3. **FnCTOD模式测试**：测试 FnCTODTracker 的函数调用和槽位填充能力
4. **完整评估指标**：Slot Accuracy、Joint Goal Accuracy、Precision/Recall/F1
5. **对话级别意图评测**：基于关键词匹配推断对话整体意图

---

## 📦 TransferTOD 数据集

### 数据集介绍

TransferTOD 是一个中文任务型对话数据集，包含多个领域的对话场景。

### 数据集结构

```
data/TransferTOD/
└── data/
    └── raw_data/
        ├── clean/                   # 清洁数据
        │   ├── 1-hotel/
        │   ├── 2-restaurant/
        │   └── ...
        └── noise/                   # 噪声数据
            ├── 1-hotel/
            └── ...
```

### 数据格式

每个JSON文件包含多个对话实例，格式如下：

```json
{
  "id": 1,
  "task": "酒店",
  "extract_slot": 4,
  "content": [
    {
      "Turn": 0,
      "origin_slots": {"姓名": null, "入住日期": null},
      "conversations": [
        {"from": "user", "value": ""},
        {"from": "assistant", "value": "您的名字是什么？..."}
      ],
      "new_slots": {"姓名": null, "入住日期": null}
    }
  ]
}
```

---

## 🚀 快速开始

### 1. 准备数据集

将 TransferTOD 数据集放置在项目根目录的 `data/TransferTOD/` 目录下：

```bash
# 确保数据集路径正确
ls data/TransferTOD/data/raw_data/clean/
ls data/TransferTOD/data/raw_data/noise/
```

### 2. 运行 DST 模式评测（推荐使用 benchmark 版本）

```bash
# 测试酒店领域的清洁数据（默认）
python benchmark/run_dst_transfertod.py

# 指定领域和数据类型
python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean

# 限制测试数量（快速验证）
python benchmark/run_dst_transfertod.py --limit 5

# 查看详细输出
python benchmark/run_dst_transfertod.py --limit 3 --verbose
```

**注意**：`tests/test_dst_transfertod.py` 已被废弃，会自动重定向到 `benchmark/run_dst_transfertod.py`

### 3. 运行 FnCTOD 模式测试

```bash
# 测试酒店领域的清洁数据（默认）
python tests/test_fnctod_transfertod.py

# 指定领域和数据类型
python tests/test_fnctod_transfertod.py --domain 餐厅 --data-type clean

# 限制测试数量并查看详细输出
python tests/test_fnctod_transfertod.py --limit 3 --verbose
```

### 4. 自定义数据集路径

```bash
python benchmark/run_dst_transfertod.py --data-root /path/to/your/TransferTOD
python tests/test_fnctod_transfertod.py --data-root /path/to/your/TransferTOD
```

---

## 📊 评估指标说明

**注意：指标计算已对齐TransferTOD论文标准**

### 1. Slot Accuracy（槽位准确率）

- **定义**：所有轮次中正确提取的槽位数占总槽位数的比例
- **计算公式**：`matched_slots / total_slots`
- **含义**：衡量模型在槽位级别的提取准确性
- **用途**：用于分析模型的细粒度性能

### 2. Joint Accuracy（联合准确率）⭐ TransferTOD论文主要指标

- **定义**：对话最终状态完全匹配的对话数占总对话数的比例
- **计算方法**：
  ```python
  # 将状态转换为slot-value pairs集合
  expected_pairs = set([(k, v) for k, v in final_state.items()])
  predicted_pairs = set([(k, v) for k, v in predicted_state.items()])
  # 完全匹配才算正确
  joint_accuracy = 1.0 if expected_pairs == predicted_pairs else 0.0
  ```
- **含义**：衡量对话级别的完整正确性（最严格的指标）
- **对齐**：与TransferTOD论文的Joint Accuracy定义一致

### 3. Precision（精确率）⭐ 基于slot-value pairs

- **定义**：提取的slot-value pairs中正确的比例
- **计算公式**：`TP / (TP + FP)`
- **含义**：衡量模型提取结果的准确性
- **对齐**：使用slot-value pairs作为比较单元（与TransferTOD论文一致）

### 4. Recall（召回率）⭐ 基于slot-value pairs

- **定义**：应该提取的slot-value pairs中被正确提取的比例
- **计算公式**：`TP / (TP + FN)`
- **含义**：衡量模型提取的完整性
- **对齐**：使用slot-value pairs作为比较单元（与TransferTOD论文一致）

### 5. F1 Score ⭐ 基于slot-value pairs

- **定义**：Precision 和 Recall 的调和平均值
- **计算公式**：`2 * P * R / (P + R)`
- **含义**：综合评估模型性能
- **对齐**：与TransferTOD论文的f1_calculator实现一致

### 与TransferTOD论文对齐说明

本测试框架的指标计算已完全对齐TransferTOD论文（EMNLP 2024）的评估标准：

1. **Joint Accuracy**：对话级别评估，要求最终状态的所有slot-value pairs完全匹配
2. **F1/Precision/Recall**：基于slot-value pairs的集合运算，而非简单的槽位名称比较
3. **特殊情况处理**：当expected为空且predicted也为空时，P/R/F1 = 1.0（完全对齐论文）

参考论文：
- Zhang et al. (2024). "TransferTOD: A Generalizable Chinese Multi-Domain Task-Oriented Dialogue System with Transfer Capabilities". EMNLP 2024.
- 官方代码：https://github.com/KongLongGeFDU/TransferTOD

---

## 🔧 适配器架构

### 基础适配器（base_adapter.py）

定义了三个核心数据类：

1. **DialogueTurn**：标准化的对话轮次
   - `turn_id`: 轮次编号
   - `system_utterance`: 系统回复
   - `user_utterance`: 用户输入
   - `expected_slots`: 期望提取的槽位

2. **DialogueInstance**：标准化的对话实例
   - `dialogue_id`: 对话唯一标识
   - `domain`: 领域名称
   - `description`: 对话描述
   - `turns`: 轮次列表
   - `final_state`: 最终状态
   - `metadata`: 元数据

3. **DatasetAdapter**：抽象基类
   - `load_dialogue()`: 加载对话
   - `get_all_dialogue_ids()`: 获取所有对话ID
   - `get_domain_schema()`: 获取领域Schema

### TransferTOD适配器（transfertod_adapter.py）

实现了 TransferTOD 数据集的加载和转换：

- **数据加载**：支持按 dialogue_id 加载对话
- **格式转换**：将 TransferTOD 格式转换为标准格式
- **槽位变化提取**：自动识别每轮的槽位变化
- **Schema生成**：自动提取领域的槽位定义
- **缓存机制**：避免重复加载相同数据

---

## 💡 使用示例

### 示例1：批量测试所有对话

```python
from tests.adapters import TransferTODAdapter

# 初始化适配器
adapter = TransferTODAdapter(data_root="./data/TransferTOD")

# 获取所有酒店领域的对话
dialogue_ids = adapter.get_dialogues_by_domain("酒店", "clean")
print(f"找到 {len(dialogue_ids)} 个对话")

# 测试每个对话
for dialogue_id in dialogue_ids[:5]:  # 只测试前5个
    dialogue = adapter.load_dialogue(dialogue_id)
    print(f"对话ID: {dialogue.dialogue_id}")
    print(f"领域: {dialogue.domain}")
    print(f"轮次数: {len(dialogue.turns)}")
```

### 示例2：检查领域Schema

```python
from tests.adapters import TransferTODAdapter

adapter = TransferTODAdapter(data_root="./data/TransferTOD")

# 获取酒店领域的Schema
schema = adapter.get_domain_schema("酒店")
print(f"领域: {schema['domain']}")
print(f"槽位数: {len(schema['slots'])}")
print("槽位列表:")
for slot_name in schema['slots']:
    print(f"  - {slot_name}")
```

### 示例3：单个对话详细分析

```python
from tests.adapters import TransferTODAdapter

adapter = TransferTODAdapter(data_root="./data/TransferTOD")

# 加载特定对话
dialogue = adapter.load_dialogue("clean/1-hotel/hotel_clean_4.json:1")

# 查看每一轮
for turn in dialogue.turns:
    print(f"\n轮次 {turn.turn_id}:")
    print(f"用户: {turn.user_utterance}")
    print(f"系统: {turn.system_utterance}")
    print(f"期望槽位: {turn.expected_slots}")
```

---

## 🧪 测试输出示例

运行 `python benchmark/run_dst_transfertod.py --limit 3 --verbose` 后的输出：

```
======================================================================
DST 模式测试 - TransferTOD 数据集 (酒店)
======================================================================

找到 130 个对话实例
限制测试数量: 3

============================================================
测试对话: clean/1-hotel/hotel_clean_4.json:1
领域: 酒店
描述: 酒店场景对话 (extract_slot=4)
============================================================

--- 轮次 0 ---
系统: 您的名字是什么？您想要从哪天开始预定呢？...
用户: 
期望状态: {}
提取状态: {}
匹配数: 0/0

--- 轮次 1 ---
系统: 您对于酒店的服务有什么要求吗？...
用户: 请称呼我为韩金虎。我计划在这个月20号入住...
期望状态: {'姓名': '韩金虎', '入住日期': '这个月20号'}
提取状态: {'姓名': '韩金虎', '入住日期': '这个月20号'}
匹配数: 2/2

--- 测试结果（对齐TransferTOD论文指标）---
槽位准确率 (Slot Accuracy): 95.00%
联合准确率 (Joint Accuracy): 1.00 (100%)
精确率 (Precision): 94.50%
召回率 (Recall): 95.50%
F1分数 (F1 Score): 95.00%

======================================================================
📊 测试指标汇总（对齐TransferTOD论文）
======================================================================

测试对话数: 3
平均槽位准确率 (Slot Accuracy): 93.45%
平均联合准确率 (Joint Accuracy): 66.67%
平均精确率 (Precision): 92.87%
平均召回率 (Recall): 94.12%
平均F1分数 (F1 Score): 93.49%

注：指标计算方法已对齐TransferTOD论文
  - Joint Accuracy: 对话级别（最终状态完全匹配）
  - F1/Precision/Recall: 基于slot-value pairs计算
```

---

## ⚠️ 注意事项

### 数据集路径

- 确保 TransferTOD 数据集的目录结构正确
- 默认路径为 `./data/TransferTOD/data/raw_data/`
- 可以通过 `--data-root` 参数指定自定义路径

### LLM 配置

- 测试脚本需要 LLM API 才能运行
- 确保 `.env` 文件中配置了正确的 API 密钥
- LLM 调用可能需要较长时间，请耐心等待

### 内存使用

- 适配器使用缓存机制，测试大量对话时可能占用较多内存
- 可以通过 `--limit` 参数限制测试数量

### 测试时间

- 每个对话的测试时间取决于轮次数和 LLM 响应速度
- 建议先用 `--limit` 参数进行小规模测试

---

## 🔄 扩展其他数据集

要支持新的数据集，只需：

1. 继承 `DatasetAdapter` 基类
2. 实现三个抽象方法：
   - `load_dialogue()`
   - `get_all_dialogue_ids()`
   - `get_domain_schema()`
3. 将数据转换为标准的 `DialogueInstance` 格式

示例：

```python
from tests.adapters.base_adapter import DatasetAdapter, DialogueInstance

class MyDatasetAdapter(DatasetAdapter):
    def load_dialogue(self, dialogue_id: str) -> DialogueInstance:
        # 加载并转换数据
        pass
    
    def get_all_dialogue_ids(self) -> List[str]:
        # 返回所有对话ID
        pass
    
    def get_domain_schema(self, domain: str) -> Dict[str, Any]:
        # 返回领域Schema
        pass
```

---

## 📚 相关文档

- [ContextMind 主文档](../README.md)
- [DST 模式说明](../docs/dst_mode.md)
- [FnCTOD 模式说明](../docs/fnctod_mode.md)
- [TransferTOD 数据集论文](https://arxiv.org/abs/...)

---

## 🤝 贡献

欢迎贡献新的数据集适配器或改进现有测试脚本！

---

**最后更新**: 2026-02-05
