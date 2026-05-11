# FnCTOD 算法文档

## 概述

**FnCTOD**（Function-Calling for Task-Oriented Dialogue，任务型对话函数调用）是 ContextMind 中已实现的第二个基准评测算法。该算法将对话理解建模为**函数调用**问题：每个对话领域定义为一个函数，槽位定义为函数参数，LLM 根据对话上下文填充参数。

- **实现状态**: ✅ 已实现
- **核心代码**: `benchmark/evaluators/fnctod.py`
- **评测脚本**: `benchmark/run_benchmark.py --algorithm fnctod`
- **支持数据集**: TransferTOD
- **论文**: [Large Language Models as Zero-shot Dialogue State Tracker through Function Calling](https://arxiv.org/pdf/2402.10466)（ACL 2024）

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ✅ 可选 | 可从原始对话自动生成函数 Schema，也可使用预定义 Schema |
| **② Schema 数据生成** | ❌ 不需要 | FnCTOD 不需要生成额外的算法专用代码文件 |
| **③ 算法执行（FnCTOD）** | ✅ 必须 | 两阶段函数调用：领域选择 + 参数填充 |

FnCTOD 可选使用第一步从原始对话自动发现槽位；也可直接使用预定义的 TransferTOD Schema 进入第三步执行。

---

## 算法原理

### 核心思想

FnCTOD 将槽位填充转化为**结构化函数调用**问题：

1. **预定义 Schema**：为每个对话领域（domain）预先定义槽位名称、类型和约束
2. **两阶段处理**：Stage 1 选择领域，Stage 2 用结构化提示词填充参数
3. **函数调用格式**：LLM 输出 `<function_call>` 标签包裹的 JSON 参数
4. **累积状态**：每轮参数与历史状态合并，形成完整的对话状态

### 与 DST 的核心差异

FnCTOD 相比 DST 的最大改进是引入了**预定义 Schema**：

```
DST 输入：
  "请从以下对话中提取槽位信息（JSON格式）..."
  → LLM 自由发挥，槽位名称不稳定

FnCTOD 输入：
  "请调用函数 book_hotel，填充以下参数：
   - hotel_name (string, 必需): 酒店名称
   - check_in_date (date, 必需): 入住日期（YYYY-MM-DD）
   - room_type (string, 可选): ['标准间', '大床房', '套房']"
  → LLM 在约束内填充，槽位名称统一
```

---

## 处理流程

### 两阶段模式（多领域）

```
用户输入
    ↓
━━━ Stage 1: 领域选择 ━━━
    ↓
1. 构建领域选择提示词
   （包含所有可用 domain 的简要描述）
    ↓
2. LLM 调用（领域选择）
   输出：<domain>酒店</domain>
    ↓
3. 解析响应，确定目标 domain
    ↓
━━━ Stage 2: 函数调用 ━━━
    ↓
4. 构建函数调用提示词
   （包含选定 domain 的完整 Schema 定义）
    ↓
5. LLM 调用（参数填充）
   输出：<function_call name="酒店">{"hotel_name": "希尔顿"}</function_call>
    ↓
6. 解析函数调用，提取 {slot: value}
    ↓
7. 状态更新
   新参数与历史状态合并
    ↓
  输出：更新后的对话状态
```

### 单阶段模式（单领域）

当只有一个 domain 或 domain 已知时，跳过 Stage 1，直接进行函数调用。性能提升约 30%（少一次 LLM 调用）。

---

## 评测指标

FnCTOD 使用与 DST 相同的评测指标体系（详见 [`metrics-explanation.md`](../reference/benchmark.md)）：

| 指标 | 粒度 | 说明 |
|------|------|------|
| **槽位准确率**（Slot Accuracy） | Turn-level | 每轮正确槽位数 / 总槽位数 |
| **联合准确率-严格**（Joint Accuracy Strict） | Dialogue-level | 最终状态需与标注完全一致 |
| **联合准确率-软匹配**（Joint Accuracy Soft） | Dialogue-level | 允许预测有额外槽位 |
| **精确率**（Precision） | Dialogue-level | TP / (TP + FP) |
| **召回率**（Recall） | Dialogue-level | TP / (TP + FN) |
| **F1 分数** | Dialogue-level | 2 × P × R / (P + R) |

---

## Schema 定义

### Schema 格式

```python
{
    "domain": "酒店",
    "description": "酒店预订领域对话处理",
    "slots": {
        "hotel_name": {
            "type": "string",
            "description": "酒店名称（如：希尔顿酒店、万豪酒店）",
            "occurrence_count": 150,
            "example_values": ["希尔顿酒店", "万豪酒店"]
        },
        "check_in_date": {
            "type": "string",
            "description": "入住日期（如：2024-01-15、明天）",
            "occurrence_count": 145
        }
    },
    "metadata": {
        "dialogue_count": 300,
        "slot_count": 12,
        "source": "TransferTOD数据集自动提取"
    }
}
```

### 手动定义 Schema

```python
from contextmind.modes.fnctod import FunctionManager, DomainSpec, FunctionParameter, ParameterType

manager = FunctionManager()
manager.add_domain_from_slots(
    domain_name="酒店",
    domain_description="酒店预订场景",
    slots={
        "hotel_name": "酒店名称",
        "check_in_date": "入住日期（YYYY-MM-DD）",
        "room_type": "房间类型",
    },
    categorical_slots={
        "room_type": ["标准间", "大床房", "套房"]
    },
    required_slots=["hotel_name", "check_in_date"]
)
```

---

## 代码实现

### `FnCTODMetrics` 数据类

```python
@dataclass
class FnCTODMetrics:
    slot_accuracy: float = 0.0
    slot_precision: float = 0.0
    slot_recall: float = 0.0
    slot_f1: float = 0.0
    joint_accuracy: float = 0.0
    joint_accuracy_strict: float = 0.0
    total_slots: int = 0
    correct_slots: int = 0
    total_turns: int = 0
    correct_turns: int = 0
    domain_metrics: Dict[str, Dict[str, float]]
```

### `FnCTODEvaluator` 评测器

```python
from benchmark.evaluators import FnCTODEvaluator

evaluator = FnCTODEvaluator()

evaluator.add_prediction(
    predicted={"hotel_name": "希尔顿", "room_type": "大床房"},
    ground_truth={"hotel_name": "希尔顿", "room_type": "大床房", "check_in_date": "2024-03-15"},
    domain="酒店"
)

metrics = evaluator.calculate_metrics()
print(f"F1: {metrics.slot_f1:.2%}")
print(f"Joint Accuracy: {metrics.joint_accuracy:.2%}")
```

---

## 运行评测

```bash
# 评测所有领域（TransferTOD，推荐）
python benchmark/run_benchmark.py --algorithm fnctod --dataset transfertod

# 评测特定领域，限制数量
python benchmark/run_benchmark.py --algorithm fnctod --dataset transfertod --domain 酒店 --limit 100

# 详细输出（逐对话打印）
python benchmark/run_benchmark.py --algorithm fnctod --dataset transfertod --domain 酒店 --limit 10 --verbose
```

---

## 性能特点

### 优势

- ✅ **一致性高**：预定义 Schema 保证槽位名称统一
- ✅ **约束明确**：枚举值和类型约束减少 LLM 幻觉
- ✅ **准确率高**：相比 DST 通常高 10-15%
- ✅ **业务对齐**：Schema 与实际业务系统 API 自然对应

### 局限性

- ❌ **需要预定义**：必须提前知道领域和槽位
- ❌ **维护成本**：Schema 变化时需要同步更新
- ❌ **领域覆盖**：未预定义的领域无法处理
- ❌ **对 LLM 要求高**：需要 LLM 具有良好的指令遵循能力

### 与 DST 对比

| 特性 | DST | FnCTOD |
|------|-----|--------|
| 前置准备 | 无需准备 | 需定义 Schema |
| 槽位名称 | 不稳定 | 固定统一 |
| 准确率 | ~75-80% | ~85-90% |
| LLM 调用次数 | 1 次/轮 | 1-2 次/轮 |
| 适用场景 | 探索/研究 | 生产环境 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `benchmark/evaluators/fnctod.py` | FnCTOD 评测核心逻辑 |
| `benchmark/run_benchmark.py` | 统一评测入口（--algorithm fnctod --dataset ...） |
| `benchmark/datasets/transfertod.py` | TransferTOD 数据适配器 |
| `contextmind/modes/fnctod/` | FnCTOD 模式完整实现 |

## 参考资料

- [评测指标说明](../reference/benchmark.md)
- [TransferTOD 数据集](../datasets/datasets.md)
- [API 参考](../reference/api-reference.md)
- [FnCTOD 论文：Large Language Models as Zero-shot Dialogue State Tracker through Function Calling](https://arxiv.org/pdf/2402.10466)（ACL 2024）
