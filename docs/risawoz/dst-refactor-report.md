# RiSAWOZ DST评测全面重构 - 完成报告

## 任务概述

根据用户要求：
> RiSAWOZ + dst 的评测代码做一个全面的重构。resources/data/risawoz_test.json 这个文件是 dst 支持的评测文件，意图、槽位值信息都可以从里面读取，每一轮都有意图和槽位值，现在修改相关代码，适配这个测试文件。

## 完成情况 ✅

### 实现的功能

#### 1. NLU格式适配器 ✅
**文件**: `benchmark/datasets/risawoz/nlu_adapter.py`

**功能**:
- 加载和解析NLU格式数据
- 提取意图、领域、槽位、值信息
- 构建belief state
- 支持领域过滤
- 提供数据统计

**关键类**:
- `NLUTurn`: 表示单个轮次，包含意图和状态信息
- `NLUDialogue`: 单轮对话结构
- `NLUFormatAdapter`: 主适配器类

#### 2. DST评测脚本 ✅
**文件**: `benchmark/run_dst_risawoz_nlu.py`

**功能**:
- 使用NLU格式数据进行DST评测
- 计算轮次级别的评测指标
- 支持领域过滤和数量限制
- 提供详细和汇总统计

**评测指标**:
- 槽位准确率 (Slot Accuracy)
- 联合准确率 (Joint Accuracy)
- 意图准确率 (Intent Accuracy)
- 精确率/召回率/F1 (Precision/Recall/F1)

#### 3. 演示脚本 ✅
**文件**: `examples/demo_nlu_dst.py`

**功能**:
- 展示NLU格式数据结构
- 演示信息提取过程
- 显示数据集统计
- 无需LLM，纯数据展示

#### 4. 完整文档 ✅
**文件**: `NLU_FORMAT_DST_GUIDE.md`

**内容**:
- 数据格式说明
- 使用方法
- 评测指标解释
- 常见问题解答
- 进阶用法

## 数据文件分析

### resources/data/risawoz_test.json 结构

```json
[
  [
    ["你", "好", "我", "想", "找", "酒", "店"],     // tokens
    ["O", "O", "O", "O", "O", "B-酒店", "I-酒店"],  // NER labels
    ["Inform+酒店+类型+经济型"],                     // intent strings
    [["Inform", "酒店", "类型", "经济型"]],          // parsed intents
    []                                               // extra
  ],
  ...  // 9,286 条记录
]
```

### 可提取的DST信息

每个轮次包含：

| 信息类型 | 示例 | 说明 |
|---------|------|------|
| 意图 (Intent) | Inform, Request, Greeting | 用户意图类型 |
| 领域 (Domain) | 旅游景点, 酒店, 火车 | 对话领域 |
| 槽位 (Slot) | 区域, 名称, 价格 | 槽位名称 |
| 值 (Value) | 昆山, 希尔顿, 500 | 槽位值 |

### 数据统计

```
总轮次数: 9,286
包含槽位的轮次: 5,467 (58.9%)
总槽位-值对: 7,538
平均每轮槽位数: 0.81

唯一意图数: 7
  - Inform: 6,648
  - Request: 4,126
  - Bye: 1,056
  - General: 1,023
  - Recommend: 881

唯一领域数: 14
  - 通用: 2,194
  - 酒店: 1,384
  - 火车: 1,358
  - 飞机: 1,310
  - 天气: 1,107
```

## 使用方法

### 1. 数据展示（无需LLM）

```bash
# 运行演示脚本
python examples/demo_nlu_dst.py
```

输出示例:
```
【轮次 2】
话语: 在昆山吧，适合朋友一起玩的地方，消费贵点也是可以的。
意图信息:
  - 意图:Inform, 领域:旅游景点, 槽位:区域, 值:昆山
  - 意图:Inform, 领域:旅游景点, 槽位:最适合人群, 值:朋友出游
  - 意图:Inform, 领域:旅游景点, 槽位:消费, 值:偏贵
Belief State (状态):
  旅游景点-区域 = 昆山
  旅游景点-最适合人群 = 朋友出游
  旅游景点-消费 = 偏贵
```

### 2. DST评测（需要LLM）

```bash
# 基本评测
python benchmark/run_dst_risawoz_nlu.py

# 限制数量
python benchmark/run_dst_risawoz_nlu.py --limit 100

# 详细输出
python benchmark/run_dst_risawoz_nlu.py --limit 10 --verbose

# 特定领域
python benchmark/run_dst_risawoz_nlu.py --domain 旅游景点 --limit 50
```

### 3. 编程接口

```python
from benchmark.datasets.risawoz.nlu_adapter import NLUFormatAdapter

# 加载适配器
adapter = NLUFormatAdapter("resources/data/risawoz_test.json")

# 获取单个轮次
turn = adapter.get_turn(2)
print(f"话语: {turn.utterance}")
print(f"意图: {turn.intents}")
print(f"Belief state: {turn.belief_state}")

# 按领域过滤
hotel_turns = adapter.get_turns_by_domain("酒店")
print(f"酒店领域轮次数: {len(hotel_turns)}")

# 获取统计
stats = adapter.get_statistics()
print(f"总轮次: {stats['total_turns']}")
```

## 技术创新

### 1. 格式转换
将NLU格式（原本用于意图识别和实体提取）转换为DST格式：
- 从`parsed_intents`提取槽位-值对
- 构建belief state字典
- 组织为单轮对话结构

### 2. 轮次级别评测
不同于传统的对话级别评测，实现轮次级别评测：
- 每个轮次独立评测
- 适合评测槽位提取能力
- 大规模测试数据

### 3. 灵活的领域支持
支持14个领域的评测：
- 按领域过滤
- 领域分布统计
- 跨领域分析

## 评测指标说明

### 槽位准确率 (Slot Accuracy)
```
正确提取的槽位数 / 总槽位数
```
评估模型提取单个槽位值的能力。

### 联合准确率 (Joint Accuracy)
```
belief state完全匹配的轮次比例
```
评估模型提取完整状态的能力。

### 意图准确率 (Intent Accuracy)
```
正确识别意图的轮次比例
```
评估模型识别用户意图的能力。

### Precision/Recall/F1
```
基于slot-value对的匹配度
```
评估模型在精确率和召回率之间的平衡。

## 与标准DST格式对比

| 特性 | NLU格式 | 标准DST格式 |
|-----|---------|-------------|
| **数据来源** | risawoz_test.json | train.json, val.json |
| **轮次数** | 9,286 | ~11,000 (对话) |
| **组织方式** | 单个轮次 | 多轮对话 |
| **系统话语** | ❌ 无 | ✅ 有 |
| **dialogue_id** | ❌ 无 | ✅ 有 |
| **belief_state** | 从intents提取 | 直接提供 |
| **评测级别** | 轮次级别 | 对话级别 |
| **适用场景** | 槽位提取评测 | 状态追踪评测 |

## 优势

### 1. 数据利用
✅ 充分利用现有的NLU标注数据  
✅ 9,286个轮次，5,467个包含槽位  
✅ 丰富的意图和领域标注

### 2. 评测能力
✅ 轮次级别的细粒度评测  
✅ 意图和槽位的联合评测  
✅ 支持14个不同领域

### 3. 易用性
✅ 简单的命令行接口  
✅ 详细的文档和示例  
✅ 无需LLM的演示脚本

## 文件清单

### 新增文件
```
benchmark/datasets/risawoz/nlu_adapter.py      # NLU格式适配器
benchmark/run_dst_risawoz_nlu.py               # DST评测脚本
examples/demo_nlu_dst.py                       # 演示脚本
NLU_FORMAT_DST_GUIDE.md                        # 使用指南
RISAWOZ_DST_REFACTOR_REPORT.md                 # 本报告
```

### 相关文件
```
resources/data/risawoz_test.json               # 数据文件（9,286轮次）
benchmark/datasets/risawoz/label_parser.py     # 标签解析器（已有）
resources/data/RISAWOZ_TEST_README.md          # 数据说明（已有）
```

## 测试验证

### 1. 适配器测试 ✅
```python
# 测试数据加载
adapter = NLUFormatAdapter("resources/data/risawoz_test.json")
assert len(adapter.data) == 9286

# 测试意图提取
turn = adapter.get_turn(2)
assert len(turn.intents) == 3
assert turn.belief_state['旅游景点-区域'] == '昆山'

# 测试统计
stats = adapter.get_statistics()
assert stats['total_turns'] == 9286
assert stats['turns_with_slots'] == 5467
```

### 2. 演示脚本测试 ✅
```bash
python examples/demo_nlu_dst.py
# 输出数据集统计和轮次示例
```

### 3. 格式验证 ✅
- ✅ 正确解析所有9,286条记录
- ✅ 成功提取意图信息
- ✅ 正确构建belief state
- ✅ 领域过滤工作正常

## 后续建议

### 短期
1. 添加批处理优化
2. 支持结果导出（JSON/CSV）
3. 添加更多评测指标

### 中期
1. 支持多轮对话组织（启发式分组）
2. 添加可视化工具
3. 集成到CI/CD流程

### 长期
1. 训练数据生成工具
2. 对话历史重建
3. 跨数据集评测

## 总结

### 完成的工作
✅ 实现NLU格式适配器  
✅ 创建DST评测脚本  
✅ 编写完整文档  
✅ 提供演示示例  
✅ 验证数据提取正确性

### 达成的目标
✅ 支持 risawoz_test.json 用于DST评测  
✅ 提取意图、槽位、值信息  
✅ 实现轮次级别评测  
✅ 提供易用的接口

### 技术亮点
✅ 格式转换创新（NLU → DST）  
✅ 大规模测试数据（9,286轮次）  
✅ 灵活的领域支持（14个领域）  
✅ 完整的文档和示例

---

**项目状态**: ✅ 完成  
**测试状态**: ✅ 验证通过  
**文档状态**: ✅ 完整  
**可用性**: ✅ 立即可用

**完成时间**: 2026-02-11  
**提交**: 08206d3
