# Evolution Module

基于 AlphaEvolve 和 ThetaEvolve 思想的进化式记忆管理模块。

## 概述

这是一个独立的模块，不影响 ContextMind 核心框架。实现了借鉴进化算法的记忆优化能力，包括：

- 进化式记忆更新器
- 观测和反馈收集系统
- 隐式反馈分析

## 模块结构

```
evolution/
├── __init__.py                # 模块入口
├── updaters/                  # 进化式更新器
│   ├── __init__.py
│   └── evolutionary.py        # EvolutionaryMemoryUpdater
├── feedback/                  # 反馈收集系统
│   ├── __init__.py
│   ├── types.py              # 数据类型定义
│   └── collector.py          # 收集器实现
├── examples/                  # 示例程序
│   ├── evolutionary_memory_demo.py
│   ├── observation_feedback_demo.py
│   └── practical_feedback_collection_demo.py
└── docs/                      # 文档
    ├── EVOLUTIONARY_MEMORY.md
    ├── OBSERVATION_FEEDBACK_ANALYSIS.md
    └── PRACTICAL_FEEDBACK_GUIDE.md
```

## 安装和使用

### 导入模块

```python
# 进化式更新器
from evolution.updaters import EvolutionaryMemoryUpdater

# 反馈收集
from evolution.feedback import (
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
    FeedbackEvent,
    ObservationEvent,
)

# 或者从顶层导入
from evolution import (
    EvolutionaryMemoryUpdater,
    ObservationCollector,
    FeedbackCollector,
)
```

### 基本使用

```python
from contextmind.memory import MemoryBank, FitnessCalculator
from evolution.updaters import EvolutionaryMemoryUpdater

# 创建记忆库，使用进化式更新器
memory_bank = MemoryBank(
    updater=EvolutionaryMemoryUpdater(
        max_memory_size=100,
        elite_ratio=0.7,
        similarity_threshold=0.85
    )
)
```

### 观测和反馈

```python
from evolution.feedback import ObservationCollector, FeedbackCollector
from contextmind.memory import FitnessCalculator

# 初始化
calculator = FitnessCalculator()
obs_collector = ObservationCollector(calculator)
feedback_collector = FeedbackCollector(calculator)

# 观测记忆使用
obs_collector.observe_retrieval(memory, query)
obs_collector.observe_usage(memory)

# 收集反馈
feedback_collector.collect_positive_feedback([memory])
feedback_collector.collect_negative_feedback([memory])
```

## 运行示例

```bash
# 设置 PYTHONPATH
export PYTHONPATH=/path/to/ContextMind

# 运行示例
python3 evolution/examples/evolutionary_memory_demo.py
python3 evolution/examples/observation_feedback_demo.py
python3 evolution/examples/practical_feedback_collection_demo.py
```

## 核心特性

### 1. 进化式记忆更新

- **适应度评估**: 多维度评估记忆价值
- **精英选择**: 保留高适应度记忆
- **智能合并**: 合并相似记忆
- **自动淘汰**: 删除低价值记忆

### 2. 观测和反馈

- **观测收集**: 检索、使用、忽略事件
- **显式反馈**: 点赞、点踩、纠正
- **隐式反馈**: 对话延续、重复、澄清
- **自动评估**: LLM贡献度评估

### 3. 持续学习

- **动态适应度**: 基于观测和反馈调整
- **质量保证**: 准确性自动更新
- **贡献度跟踪**: 评估实际价值

## 与 ContextMind 核心的关系

- **独立模块**: evolution 是可选扩展，不影响核心
- **核心依赖**: 依赖 contextmind 的基础组件
- **灵活集成**: 可以选择使用或不使用

## 设计参考

基于以下论文的核心思想：

1. **AlphaEvolve** (Google DeepMind)
   - 使用 LLM 作为变异算子
   - 进化搜索优化
   
2. **ThetaEvolve** 
   - 测试时学习
   - 持续适应

## 文档

详细文档请查看 `evolution/docs/` 目录：

- `EVOLUTIONARY_MEMORY.md` - 进化式记忆系统完整文档
- `OBSERVATION_FEEDBACK_ANALYSIS.md` - 观测和反馈分析
- `PRACTICAL_FEEDBACK_GUIDE.md` - 实践指南

## 版本

当前版本: 0.1.0

## 许可

与 ContextMind 主项目相同
