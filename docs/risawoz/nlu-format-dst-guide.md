# RiSAWOZ NLU格式 DST评测指南

## 概述

现在支持使用NLU格式的RiSAWOZ数据（`resources/data/risawoz_test.json`）进行DST（对话状态追踪）评测。该文件包含每个对话轮次的意图、领域、槽位、值信息。

## 数据格式

### NLU格式结构

```json
[
  [
    ["你", "好", "我", "想", "找", "酒", "店"],     // tokens - 分词结果
    ["O", "O", "O", "O", "O", "B-酒店", "I-酒店"],  // labels - NER标签
    ["Inform+酒店+类型+经济型"],                     // intent_strings - 意图字符串
    [["Inform", "酒店", "类型", "经济型"]],          // parsed_intents - 解析后的意图
    []                                               // extra - 额外信息
  ],
  ...  // 9,286条轮次记录
]
```

### 提取的信息

每个轮次包含：

| 字段 | 说明 | 示例 |
|-----|------|------|
| `intent` | 意图类型 | Inform, Request, Greeting |
| `domain` | 领域 | 旅游景点, 酒店, 火车 |
| `slot` | 槽位名称 | 区域, 名称, 价格 |
| `value` | 槽位值 | 昆山, 希尔顿, 500 |

## 使用方法

### 基本评测

```bash
# 评测所有轮次（仅包含槽位值的轮次）
python benchmark/run_dst_risawoz_nlu.py

# 限制评测数量
python benchmark/run_dst_risawoz_nlu.py --limit 100

# 详细输出
python benchmark/run_dst_risawoz_nlu.py --limit 10 --verbose
```

### 领域过滤

```bash
# 仅评测旅游景点领域
python benchmark/run_dst_risawoz_nlu.py --domain 旅游景点

# 仅评测酒店领域
python benchmark/run_dst_risawoz_nlu.py --domain 酒店 --limit 50
```

### 自定义数据文件

```bash
# 使用自定义NLU格式文件
python benchmark/run_dst_risawoz_nlu.py --data-path path/to/your/nlu_data.json
```

## 评测指标

### 核心指标

1. **槽位准确率 (Slot Accuracy)**
   - 计算方式：正确提取的槽位数 / 总槽位数
   - 范围：0-100%

2. **联合准确率 (Joint Accuracy)**
   - 计算方式：belief state完全匹配的轮次比例
   - 范围：0-100%

3. **意图准确率 (Intent Accuracy)**
   - 计算方式：正确识别意图的轮次比例
   - 范围：0-100%

4. **精确率/召回率/F1 (Precision/Recall/F1)**
   - 基于slot-value对的匹配
   - 范围：0-100%

### 输出示例

```
======================================================================
📊 NLU格式 DST 评测指标汇总
======================================================================

领域: 所有领域
评测轮次数: 100

【核心指标】
----------------------------------------------------------------------
槽位准确率 (Slot Accuracy):       85.32%
联合准确率 (Joint Accuracy):      72.00%
意图准确率 (Intent Accuracy):     89.00%
精确率 (Precision):               88.45%
召回率 (Recall):                  86.22%
F1分数 (F1 Score):                87.32%

【详细统计】
----------------------------------------------------------------------
总槽位数: 243
正确槽位数: 207
槽位级别准确率: 85.19%

意图识别:
  正确: 89/100 (89.00%)

======================================================================
```

## 数据集统计

### 总体统计

- **总轮次数**: 9,286
- **包含槽位的轮次**: 5,467 (58.9%)
- **总槽位-值对**: 7,538
- **平均每轮槽位数**: 0.81
- **唯一意图数**: 7
- **唯一领域数**: 14

### 意图分布

| 意图类型 | 数量 | 占比 |
|---------|------|------|
| Inform | 6,648 | 41.8% |
| Request | 4,126 | 25.9% |
| Bye | 1,056 | 6.6% |
| General | 1,023 | 6.4% |
| Recommend | 881 | 5.5% |
| Greeting | 759 | 4.8% |
| Confirm | 394 | 2.5% |

### 领域分布

| 领域 | 数量 | 占比 |
|------|------|------|
| 通用 | 2,194 | 13.8% |
| 酒店 | 1,384 | 8.7% |
| 火车 | 1,358 | 8.5% |
| 飞机 | 1,310 | 8.2% |
| 天气 | 1,107 | 7.0% |

## 技术实现

### NLU格式适配器

**文件**: `benchmark/datasets/risawoz/nlu_adapter.py`

主要功能：
- 加载NLU格式数据
- 提取意图、领域、槽位、值
- 构建belief state
- 创建单轮对话

关键类：
```python
from benchmark.datasets.risawoz.nlu_adapter import NLUFormatAdapter

# 初始化适配器
adapter = NLUFormatAdapter("resources/data/risawoz_test.json")

# 获取单个轮次
turn = adapter.get_turn(0)
print(f"话语: {turn.utterance}")
print(f"意图: {turn.intents}")
print(f"belief state: {turn.belief_state}")

# 获取所有轮次
all_turns = adapter.get_all_turns()

# 按领域过滤
hotel_turns = adapter.get_turns_by_domain("酒店")

# 获取统计信息
stats = adapter.get_statistics()
```

### 评测脚本

**文件**: `benchmark/run_dst_risawoz_nlu.py`

特点：
- 支持LLM驱动的DST评测
- 每个轮次独立评测
- 提供详细的指标统计
- 支持领域过滤和数量限制

## NLU格式 vs 标准DST格式

### 格式对比

| 特性 | NLU格式 | 标准DST格式 |
|-----|---------|-------------|
| **数据来源** | task1-data / risawoz_test.json | train.json, val.json, test.json |
| **结构** | [[tokens], [labels], ...] | {"dialogue_id": ..., "dialogue": ...} |
| **对话组织** | 单个轮次 | 完整多轮对话 |
| **系统话语** | ❌ 无 | ✅ 有 |
| **dialogue_id** | ❌ 无 | ✅ 有 |
| **belief_state** | 从intents提取 | 直接提供 |
| **适用评测** | 轮次级别 | 对话级别 |

### 使用场景

**使用NLU格式** 当：
- ✅ 只有NLU标注数据
- ✅ 需要轮次级别的评测
- ✅ 关注意图和槽位提取
- ✅ 数据量大（9,286轮次）

**使用标准DST格式** 当：
- ✅ 有完整对话数据
- ✅ 需要对话级别的评测
- ✅ 关注状态追踪的连续性
- ✅ 需要系统话语上下文

## 常见问题

### Q1: 为什么需要NLU格式支持？

**答**: `resources/data/risawoz_test.json` 包含了丰富的意图和槽位标注，可以用于DST评测。虽然格式是NLU，但每个轮次都包含完整的意图、领域、槽位、值信息，足够进行状态追踪评测。

### Q2: NLU格式评测和标准DST评测有什么区别？

**答**: 主要区别：
- **NLU格式**: 轮次级别评测，每个轮次独立
- **标准DST**: 对话级别评测，考虑多轮上下文

NLU格式更适合评测模型的槽位提取和意图识别能力，标准DST更适合评测对话状态管理能力。

### Q3: 如何解释评测结果？

**答**: 
- **高槽位准确率** → 模型能准确提取槽位值
- **高联合准确率** → 模型能完整匹配所有槽位
- **高意图准确率** → 模型能正确识别用户意图
- **高F1分数** → 模型在精确率和召回率之间平衡良好

### Q4: 为什么有些轮次不参与评测？

**答**: 只有包含槽位值的轮次（5,467/9,286）参与评测，因为：
- 没有槽位值的轮次（如纯问候）无法评测状态追踪
- 这些轮次主要是Greeting、Bye、General等无信息类意图

### Q5: 如何提高评测性能？

**答**: 
```bash
# 限制评测数量
python benchmark/run_dst_risawoz_nlu.py --limit 100

# 选择特定领域（减少数据量）
python benchmark/run_dst_risawoz_nlu.py --domain 酒店 --limit 50

# 关闭详细输出（提高速度）
python benchmark/run_dst_risawoz_nlu.py --limit 100
```

## 进阶使用

### 编程接口

```python
import asyncio
from benchmark.run_dst_risawoz_nlu import DSTNLUTest

async def custom_evaluation():
    # 创建测试实例
    test = DSTNLUTest("resources/data/risawoz_test.json")
    
    # 运行评测
    metrics = await test.run_evaluation(limit=50, verbose=False)
    
    # 自定义分析
    avg_f1 = sum(m['f1'] for m in metrics) / len(metrics)
    print(f"平均F1分数: {avg_f1*100:.2f}%")

asyncio.run(custom_evaluation())
```

### 批处理

```python
from benchmark.datasets.risawoz.nlu_adapter import NLUFormatAdapter

# 加载数据
adapter = NLUFormatAdapter("resources/data/risawoz_test.json")

# 按领域分批处理
domains = adapter.get_domains()
for domain in domains:
    turns = adapter.get_turns_by_domain(domain)
    print(f"{domain}: {len(turns)} 轮次")
    
    # 进行特定领域的分析...
```

## 参考资料

- **NLU格式说明**: `resources/data/RISAWOZ_TEST_README.md`
- **标签解析器**: `benchmark/datasets/risawoz/label_parser.py`
- **DST模式文档**: `benchmark/datasets/risawoz/README.md`
- **RiSAWOZ GitHub**: https://github.com/terryqj0107/RiSAWOZ

## 总结

NLU格式的DST评测提供了：
- ✅ 利用现有NLU标注数据进行DST评测
- ✅ 轮次级别的细粒度指标
- ✅ 意图和槽位的联合评测
- ✅ 大规模测试数据（9,286轮次）

这是对标准DST评测的有力补充，特别适合评测模型的基础槽位提取和意图识别能力。
