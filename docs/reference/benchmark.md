# Benchmark — 对话系统评测框架

在标准数据集上对四种对话算法进行系统评测的轻量框架。

## 目录结构

```
benchmark/
├── evaluators/               # 算法评测器（指标数据类 + 评测器类）
│   ├── __init__.py           # 统一导出 4 个评测器
│   ├── base.py               # BaseMetrics、BaseEvaluator 抽象基类
│   ├── dst.py                # DST — 对话状态追踪
│   ├── fnctod.py             # FnCTOD — 函数调用型 TOD
│   ├── pytod.py              # PyTOD — 程序执行型 TOD
│   └── evolve.py             # Evolve — 进化式上下文优化
│
├── datasets/                 # 数据集适配器
│   ├── __init__.py           # 统一导出适配器
│   ├── base.py               # BaseDatasetAdapter 抽象基类
│   ├── transfertod.py        # TransferTOD 数据集适配器
│   ├── risawoz.py            # RiSAWOZ 数据集适配器
│   └── sgd.py                # SGD 数据集适配器
│
├── run_benchmark.py          # 统一评测入口（--algorithm × --dataset）
└── prepare_datasets.py       # 数据集下载与解析工具
```

## 使用方法

### DST 评测

```bash
# RiSAWOZ 数据集（内置，开箱即用）
python benchmark/run_benchmark.py --algorithm dst --dataset risawoz
python benchmark/run_benchmark.py --algorithm dst --dataset risawoz --domain 景点 --split val --limit 10

# TransferTOD 数据集（需先下载，见 benchmark/prepare_datasets.py）
python benchmark/run_benchmark.py --algorithm dst --dataset transfertod
python benchmark/run_benchmark.py --algorithm dst --dataset transfertod --domain 酒店 --data-type clean --limit 10
```

### FnCTOD 评测

```bash
python benchmark/run_benchmark.py --algorithm fnctod --dataset risawoz
python benchmark/run_benchmark.py --algorithm fnctod --dataset transfertod --domain 酒店 --limit 10
```

### PyTOD 评测

```bash
python benchmark/run_benchmark.py --algorithm pytod --dataset sgd --split test --limit 20
# 单条追踪演示也可通过 examples/step3_pytod_trace.py 运行
```

### 数据集准备

```bash
# 查看各数据集的下载说明
python benchmark/prepare_datasets.py --help
```

### Python API

```python
from benchmark.evaluators import DSTEvaluator, EvolveEvaluator
from benchmark.datasets import TransferTODAdapter

# DST 评测器
ev = DSTEvaluator()
ev.add_prediction(predicted={"酒店-名称": "希尔顿"}, ground_truth={"酒店-名称": "希尔顿"}, domain="酒店")
metrics = ev.calculate_metrics()
print(metrics.to_dict())

# Evolve 评测器
ev2 = EvolveEvaluator()
ev2.add_turn(extracted_knowledge_count=3, context_items_used=2, response="好的", scenario="chat")
print(ev2.calculate_metrics().to_dict())
```

## 算法步骤依赖矩阵

评测前，请确认所用算法需要哪些前置步骤：

| 算法 | ① 建立知识库 | ② Schema 数据生成 | ③ 算法执行（评测） |
|------|:-----------:|:----------------:|:----------------:|
| **DST** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **FnCTOD** | ✅ 可选 | ❌ 不需要 | ✅ 必须 |
| **PyTOD** | ✅ 可选 | ✅ 可选 | ✅ 必须 |
| **Evolve** | ❌ 不需要 | ❌ 不需要 | ✅ 必须 |

## 算法 × 数据集 支持矩阵

| 算法 / 数据集 | TransferTOD | RiSAWOZ | 安逸花外呼 |
|--------------|-------------|---------|-----------|
| DST          | ✅           | ✅       | ⏳ 待实现 |
| FnCTOD       | ✅           | ⏳ 待实现 | ⏳ 待实现 |
| PyTOD        | ⏳ 待实现    | ⏳ 待实现 | ✅         |
| Evolve       | ⏳ 待实现    | ⏳ 待实现 | ⏳ 待实现 |

## 扩展指南

### 添加新数据集

1. 在 `datasets/` 下创建新文件，继承 `BaseDatasetAdapter` 实现适配器
2. 在 `datasets/__init__.py` 中导出新适配器
3. 在 `run_benchmark.py` 中注册新 `--dataset` 选项

### 添加新算法

1. 在 `evaluators/` 下创建 `<algorithm>.py`，继承 `BaseEvaluator` 实现 `<Name>Metrics` + `<Name>Evaluator`
2. 在 `evaluators/__init__.py` 中导出新评测器
3. 在 `run_benchmark.py` 中注册新 `--algorithm` 选项


---

## 评测指标说明

### DST 指标

| 指标 | 说明 |
|------|------|
| **Slot Accuracy** | 每轮次中所有槽位值都预测正确的比例 |
| **Joint Goal Accuracy (JGA)** | 所有槽位在所有轮次均正确的对话比例（最严格指标） |
| **Slot F1** | 槽位预测的 F1 分数（精确率与召回率的调和平均） |

**JGA 计算示意**：

```
对话 1: 轮次1✅ 轮次2✅ 轮次3❌ → JGA=0（任一轮次出错即整条对话失败）
对话 2: 轮次1✅ 轮次2✅ 轮次3✅ → JGA=1
整体 JGA = 1/2 = 0.5
```

### 意图识别指标

| 指标 | 说明 |
|------|------|
| **Intent Accuracy** | 预测意图与真实意图完全匹配的比例 |
| **Intent F1** | 意图预测的 F1 分数（含局部匹配） |

### Evolve 指标

| 指标 | 说明 |
|------|------|
| **Knowledge Extraction Rate** | 成功从对话中提取知识的比例 |
| **Context Utilization Rate** | 历史上下文被有效引用的比例 |

---

## 意图评测（IntentEvaluator）

```python
from benchmark.evaluators import DSTEvaluator

evaluator = DSTEvaluator()
evaluator.add_prediction(
    predicted={"酒店-意图": "查询"},
    ground_truth={"酒店-意图": "查询"},
    domain="酒店"
)
metrics = evaluator.calculate_metrics()
print(f"Slot F1: {metrics.slot_f1:.3f}")
```
