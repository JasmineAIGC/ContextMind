# Benchmark — 对话系统评测框架

在标准数据集上对四种对话算法进行系统评测的轻量框架。

## 目录结构

```
benchmark/
├── algorithms/               # 算法评测器（指标数据类 + 评测器类）
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
│   ├── transfertod/          # TransferTOD 数据集
│   │   ├── adapter.py        # 数据适配器（TransferTODAdapter）
│   │   └── utils.py          # 领域意图配置加载器
│   ├── risawoz/              # RiSAWOZ 数据集
│   │   ├── adapter.py        # 数据适配器（RiSAWOZAdapter）
│   │   ├── label_parser.py   # 标签解析器
│   │   ├── nlu_adapter.py    # NLU 格式适配器
│   │   └── sgd_converter.py  # SGD 格式转换器
│
├── shared/                   # 跨算法/数据集共享组件
│   ├── intent_evaluator.py   # 意图评测器（IntentEvaluator）
│   ├── intent_label_loader.py # 意图标签加载器（IntentLabelLoader）
│   └── configs/              # 意图标签 JSON 配置文件
│
├── runners/                  # 评测运行脚本（算法 × 数据集）
│   ├── run_dst_transfertod.py
│   ├── run_dst_risawoz.py
│   └── run_fnctod_transfertod.py
│
└── tools/                    # 辅助工具脚本（数据预处理 / 诊断）
    ├── convert_risawoz_to_sgd.py
    ├── diagnose_dialogue_count.py
    └── extract_transfertod_schemas.py
```

## 使用方法

### DST 评测

```bash
# TransferTOD 数据集
python benchmark/runners/run_dst_transfertod.py
python benchmark/runners/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 10

# RiSAWOZ 数据集
python benchmark/runners/run_dst_risawoz.py
python benchmark/runners/run_dst_risawoz.py --domain 景点 --split val --limit 10
```

### FnCTOD 评测

```bash
python benchmark/runners/run_fnctod_transfertod.py
python benchmark/runners/run_fnctod_transfertod.py --domain 酒店 --limit 10
```

### PyTOD 评测

```bash
# 目前暂无开放数据集评测脚本，PyTOD 可通过 examples/step3_pytod_trace.py 运行单条追踪演示
```

### 辅助工具

```bash
# 将 RiSAWOZ 转换为 SGD 格式
python benchmark/tools/convert_risawoz_to_sgd.py --data-root ./data/RiSAWOZ

# 诊断数据集对话数量
python benchmark/tools/diagnose_dialogue_count.py --data-root ./data/TransferTOD

# 提取 TransferTOD Schema 信息
python benchmark/tools/extract_transfertod_schemas.py --data-root ./data/TransferTOD
```

### Python API

```python
from benchmark.algorithms import DSTEvaluator, EvolveEvaluator
from benchmark.datasets import TransferTODAdapter
from benchmark.shared import IntentEvaluator

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

1. 在 `datasets/` 下创建新目录，继承 `BaseDatasetAdapter` 实现 `adapter.py` 和 `__init__.py`
2. 在 `datasets/__init__.py` 中导出新适配器
3. 在 `runners/` 下创建 `run_<algorithm>_<dataset>.py`

### 添加新算法

1. 在 `algorithms/` 下创建 `<algorithm>.py`，继承 `BaseEvaluator` 实现 `<Name>Metrics` + `<Name>Evaluator`
2. 在 `algorithms/__init__.py` 中导出新评测器
3. 在 `runners/` 下创建对应的运行脚本


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

`benchmark/shared/intent_evaluator.py` 提供独立的意图评测器，可与任意算法组合使用。

```python
from benchmark.shared import IntentEvaluator

evaluator = IntentEvaluator()

# 添加预测结果
evaluator.add_prediction(
    predicted_intents=["查询酒店", "订房"],
    ground_truth_intents=["查询酒店"],
    domain="酒店"
)

# 计算指标
metrics = evaluator.calculate_metrics()
print(f"Intent Accuracy: {metrics.intent_accuracy:.3f}")
print(f"Intent F1: {metrics.intent_f1:.3f}")
```

意图标签配置文件位于 `benchmark/shared/configs/`，按领域区分（TransferTOD 格式）。
