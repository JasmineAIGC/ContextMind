# DST 算法文档

## 概述

**DST**（Dialogue State Tracking，对话状态追踪）是 ContextMind 中已实现的第一个基准评测算法。DST 是对话系统中的核心技术，旨在从多轮对话历史中持续追踪用户的意图和需求（即槽位-值对）。该算法通过提示词工程驱动大语言模型（LLM），从多轮对话中逐轮提取槽位-值对，构建累积的对话状态。

- **实现状态**: ✅ 已实现
- **核心代码**: `benchmark/evaluators/dst.py`
- **评测脚本**: `benchmark/run_benchmark.py --algorithm dst`
- **支持数据集**: TransferTOD、RiSAWOZ
- **技术概念**: DST（Dialogue State Tracking）是任务型对话中的基础技术，不对应单一论文，而是业界广泛使用的对话状态追踪方法论

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ✅ 可选 | 可从原始对话自动生成槽位定义，也可手动定义 |
| **② Schema 数据生成** | ❌ 不需要 | DST 不需要生成算法专用代码文件 |
| **③ 算法执行（DST）** | ✅ 必须 | 零样本 LLM 槽位提取与状态追踪 |

DST 是最轻量的使用方式——可以完全跳过第一步和第二步，直接手动定义槽位后进入第三步执行。

---

## 算法原理

### 核心思想

DST 算法的本质是**零样本提示词槽位提取**（Zero-shot Prompt-based Slot Filling）：

1. **输入**：当前轮次的用户话语 + 系统话语 + 历史对话上下文
2. **处理**：构建包含槽位定义的提示词，调用 LLM 提取 JSON 格式的槽位-值对
3. **累积**：将本轮新提取的槽位与历史状态合并（新值覆盖旧值）
4. **输出**：更新后的完整对话状态（所有轮次的累积槽位集合）

---

## 处理流程

```
用户输入（本轮话语）
       ↓
  1. 历史准备
     获取最近 N 轮对话历史，格式化为上下文
       ↓
  2. 提示词构建
     注入槽位定义 + 对话历史 + 当前输入
       ↓
  3. LLM 调用
     发送提示词，LLM 返回 JSON 格式槽位
       ↓
  4. 响应解析
     解析 JSON，提取 {slot: value} 字典
       ↓
  5. 状态更新
     新槽位与历史状态合并 → 累积对话状态
       ↓
  输出：更新后的对话状态（Dict[str, str]）
```

---

## 评测指标

DST 算法使用以下指标评估性能（详见 [`metrics-explanation.md`](../reference/benchmark.md)）：

| 指标 | 粒度 | 说明 |
|------|------|------|
| **槽位准确率**（Slot Accuracy） | Turn-level | 每轮正确槽位数 / 总槽位数 |
| **联合准确率-严格**（Joint Accuracy Strict） | Dialogue-level | 最终状态需与标注完全一致 |
| **联合准确率-软匹配**（Joint Accuracy Soft） | Dialogue-level | 允许预测有额外槽位 |
| **精确率**（Precision） | Dialogue-level | TP / (TP + FP) |
| **召回率**（Recall） | Dialogue-level | TP / (TP + FN) |
| **F1 分数** | Dialogue-level | 2 × P × R / (P + R) |

---

## 代码实现

### `DSTMetrics` 数据类

```python
@dataclass
class DSTMetrics:
    slot_accuracy: float = 0.0          # 槽位准确率
    slot_precision: float = 0.0         # 槽位精确率
    slot_recall: float = 0.0            # 槽位召回率
    slot_f1: float = 0.0                # 槽位 F1
    joint_accuracy: float = 0.0         # 联合准确率（软匹配）
    joint_accuracy_strict: float = 0.0  # 联合准确率（严格）
    total_slots: int = 0
    correct_slots: int = 0
    total_turns: int = 0
    correct_turns: int = 0
    domain_metrics: Dict[str, Dict[str, float]]  # 分领域指标
```

### `DSTEvaluator` 评测器

```python
from benchmark.evaluators import DSTEvaluator

evaluator = DSTEvaluator()

# 逐条添加预测结果
evaluator.add_prediction(
    predicted={"酒店-名称": "希尔顿", "酒店-星级": "四星级"},
    ground_truth={"酒店-名称": "希尔顿", "酒店-星级": "四星级", "酒店-价格": "800元"},
    domain="酒店"
)

# 计算所有指标
metrics = evaluator.calculate_metrics()
print(metrics.to_dict())
```

---

## 运行评测

### 在 TransferTOD 数据集上评测

```bash
# 评测所有领域（clean 数据，推荐）
python benchmark/run_benchmark.py --algorithm dst --dataset transfertod --data-type clean

# 评测特定领域，限制数量
python benchmark/run_benchmark.py --algorithm dst --dataset transfertod --domain 酒店 --limit 100

# 使用噪声数据评测（鲁棒性测试）
python benchmark/run_benchmark.py --algorithm dst --dataset transfertod --data-type noise
```

### 在 RiSAWOZ 数据集上评测

```bash
# 评测验证集
python benchmark/run_benchmark.py --algorithm dst --dataset risawoz

# 评测特定领域
python benchmark/run_benchmark.py --algorithm dst --dataset risawoz --domain 景点 --split val --limit 50

# 详细输出
python benchmark/run_benchmark.py --algorithm dst --dataset risawoz --domain 酒店 --verbose
```

---

## 性能特点

### 优势

- ✅ **零样本**：无需标注数据和模型训练，直接调用 LLM
- ✅ **动态槽位**：不预定义槽位，LLM 自由提取信息
- ✅ **多域适应**：同一套提示词框架适配多个领域
- ✅ **实现简单**：代码结构清晰，易于理解和维护

### 局限性

- ❌ **槽位名不一致**：LLM 可能用不同名称表示同一槽位（如 "hotel_name" vs "酒店名称"）
- ❌ **格式不稳定**：LLM 有时不遵循 JSON 格式，导致解析失败
- ❌ **性能瓶颈**：每轮都需要一次 LLM 调用，延迟较高
- ❌ **累积误差**：早期错误的槽位可能在后续轮次中持续存在

### 与 FnCTOD 对比

| 特性 | DST | FnCTOD |
|------|-----|--------|
| 槽位约束 | 无预定义 | 需预定义 Schema |
| 输出格式 | 自由 JSON | 结构化函数调用 |
| 一致性 | 较低 | 高 |
| 典型 F1 | ~75-80% | ~85-90% |
| 适用场景 | 探索性任务 | 业务明确的任务 |

---

## 相关文件

| 文件 | 说明 |
|------|------|
| `benchmark/evaluators/dst.py` | DST 评测核心逻辑（DSTMetrics、DSTEvaluator） |
| `benchmark/run_benchmark.py` | 统一评测入口（--algorithm dst --dataset ...） |
| `benchmark/datasets/transfertod.py` | TransferTOD 数据适配器 |
| `benchmark/datasets/risawoz.py` | RiSAWOZ 数据适配器 |
| `contextmind/modes/dst/` | DST 模式实现（DialogueStateTracker 等） |

## 参考资料

- [评测指标说明](../reference/benchmark.md)
- [TransferTOD 数据集](../datasets/datasets.md)
- [RiSAWOZ 数据集](../datasets/datasets.md)
- [API 参考](../reference/api-reference.md)
