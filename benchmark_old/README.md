# ContextMind 评测框架 (Benchmark)

## 📋 目录概述

本目录包含 ContextMind 项目的标准化评测框架，用于在多个数据集上评估不同的对话算法。

## 🏗️ 目录结构

```
benchmark/
├── algorithms/              # 算法评测代码
│   ├── dst/                # DST (Dialogue State Tracking) 算法
│   │   ├── evaluators/     # DST评测器
│   │   └── metrics/        # DST指标计算
│   └── fnctod/             # FnCTOD (Function-based TOD) 算法
│       ├── evaluators/     # FnCTOD评测器
│       └── metrics/        # FnCTOD指标计算
│
├── datasets/                # 数据集相关代码
│   ├── transfertod/        # TransferTOD数据集
│   │   ├── configs/        # 配置文件（意图标签等）
│   │   ├── adapters/       # TransferTOD数据适配器
│   │   └── utils/          # 工具函数
│   └── risawoz/            # RiSAWOZ数据集（待实现）
│       ├── configs/        # 配置文件
│       ├── adapters/       # RiSAWOZ数据适配器
│       └── utils/          # 工具函数
│
├── adapters/                # 算法-数据集适配层
│   ├── base_adapter.py     # 基础适配器接口
│   ├── dst_transfertod.py  # DST + TransferTOD
│   ├── dst_risawoz.py      # DST + RiSAWOZ（待实现）
│   ├── fnctod_transfertod.py   # FnCTOD + TransferTOD
│   └── fnctod_risawoz.py   # FnCTOD + RiSAWOZ（待实现）
│
├── shared/                  # 共享组件
│   ├── intent_evaluator.py # 意图评测器
│   └── intent_label_loader.py  # 意图标签加载器
│
└── runners/                 # 评测运行脚本
    ├── run_dst_transfertod.py      # 运行 DST on TransferTOD
    ├── run_dst_risawoz.py          # 运行 DST on RiSAWOZ（待实现）
    ├── run_fnctod_transfertod.py   # 运行 FnCTOD on TransferTOD
    └── run_fnctod_risawoz.py       # 运行 FnCTOD on RiSAWOZ（待实现）
```

## 🎯 支持的算法

### 1. DST (Dialogue State Tracking)
对话状态追踪算法，用于从对话中提取和维护槽位信息。

**评测指标：**
- Slot Accuracy: 槽位准确率
- Joint Goal Accuracy: 联合目标准确率
- Precision/Recall/F1: 精确率、召回率、F1分数

### 2. FnCTOD (Function-based Task-Oriented Dialogue)
基于函数的任务型对话算法，支持函数调用和槽位填充。

**评测指标：**
- Function Call Accuracy: 函数调用准确率
- Slot Filling Accuracy: 槽位填充准确率
- End-to-End Success Rate: 端到端成功率

## 📊 支持的数据集

### 1. TransferTOD ✅
中文任务型对话数据集，包含多个领域。

**状态：** 已实现

**领域：**
- 酒店 (Hotel)
- 餐厅 (Restaurant)
- 景点 (Attraction)
- 出租车 (Taxi)
- 地铁 (Metro)
- 火车 (Train)
- 等30个领域

### 2. RiSAWOZ ⏳
中文任务型对话数据集。

**状态：** 待实现

## 🚀 快速开始

### 运行 DST 在 TransferTOD 上的评测

```bash
# 评测所有领域
python benchmark/runners/run_dst_transfertod.py

# 评测特定领域
python benchmark/runners/run_dst_transfertod.py --domain 酒店 --limit 10

# 使用不同数据类型
python benchmark/runners/run_dst_transfertod.py --data-type clean --limit 50
```

### 运行 FnCTOD 在 TransferTOD 上的评测

```bash
# 评测所有领域
python benchmark/runners/run_fnctod_transfertod.py

# 评测特定领域
python benchmark/runners/run_fnctod_transfertod.py --domain 酒店 --limit 10
```

## 🔧 适配器架构

适配器负责连接算法和数据集，处理格式转换和特殊逻辑：

```python
# 算法-数据集适配器示例
from benchmark.adapters.dst_transfertod import DSTTransferTODAdapter

# 初始化适配器
adapter = DSTTransferTODAdapter(data_root=".data/TransferTOD/")

# 加载对话
dialogue = adapter.load_dialogue("hotel_001")

# 格式转换
dst_format_data = adapter.convert_to_dst_format(dialogue)
```

## 📝 添加新数据集

要添加新数据集（如RiSAWOZ），需要：

1. **创建数据集适配器**
   - 在 `benchmark/datasets/<dataset_name>/adapters/` 创建适配器
   - 实现数据加载和解析逻辑

2. **创建配置文件**
   - 在 `benchmark/datasets/<dataset_name>/configs/` 添加配置

3. **创建算法-数据集适配器**
   - 在 `benchmark/adapters/` 创建对应的适配器
   - 例如：`dst_<dataset>.py`, `fnctod_<dataset>.py`

4. **创建运行脚本**
   - 在 `benchmark/runners/` 创建运行脚本
   - 例如：`run_dst_<dataset>.py`

## 📈 评测报告

评测完成后会生成详细报告，包括：

- 各项指标统计
- 分领域性能对比
- 混淆矩阵可视化
- 详细的错误分析

## 🔍 更多信息

- [TransferTOD数据集说明](datasets/transfertod/README.md)
- [算法评测指南](algorithms/README.md)
- [适配器开发文档](adapters/README.md)

## 📧 联系方式

如有问题或建议，请提交 Issue 或 Pull Request。
