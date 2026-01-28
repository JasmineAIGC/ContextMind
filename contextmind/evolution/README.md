# Evolution Module

基于 AlphaEvolve 和 ThetaEvolve 思想的进化式记忆管理模块。

## 概述

这是 ContextMind 的高级功能模块，实现了借鉴进化算法的记忆优化能力，包括：

- **进化式记忆更新器** - 智能的记忆优化和淘汰
- **观测和反馈收集系统** - 追踪记忆的实际使用效果
- **持续学习循环** - 基于观测和反馈动态优化

> 💡 **不理解观测-反馈-学习循环？** 
> 
> 先阅读 [通俗易懂的解释文档](../../docs/UNDERSTANDING_OBSERVATION_FEEDBACK_LEARNING.md)，了解核心概念！

## 模块结构（简化后）

```
evolution/
├── __init__.py                        # 模块入口
├── evolutionary_updater.py            # 进化式更新器
├── feedback_system.py                 # 反馈收集系统（含类型定义）
├── examples/                          # 示例程序
│   ├── evolutionary_memory_demo.py
│   ├── observation_feedback_demo.py
│   └── practical_feedback_collection_demo.py
└── docs/                              # 文档
    ├── EVOLUTIONARY_MEMORY.md
    ├── OBSERVATION_FEEDBACK_ANALYSIS.md
    └── PRACTICAL_FEEDBACK_GUIDE.md
```

> **注意**: 模块已扁平化，不再使用 `updaters/` 和 `feedback/` 子目录。

## 安装和使用

### 导入模块

```python
# 推荐：从 contextmind.evolution 导入
from contextmind.evolution import EvolutionaryMemoryUpdater
from contextmind.evolution import (
    ObservationCollector,
    FeedbackCollector,
    ImplicitFeedbackAnalyzer,
)

# 或者从 contextmind 顶层导入（也可用）
from contextmind import EvolutionaryMemoryUpdater, FeedbackCollector
```

### 基本使用

```python
from contextmind import MemoryBank, EvolutionaryMemoryUpdater

# 创建记忆库，使用进化式更新器
memory_bank = MemoryBank(
    updater=EvolutionaryMemoryUpdater(
        max_memory_size=100,
        elite_ratio=0.7,
        similarity_threshold=0.85
    )
)
```

### 观测和反馈（通过 FitnessCalculator）

```python
from contextmind.memory import FitnessCalculator

# EvolutionaryMemoryUpdater 内部已包含 FitnessCalculator
# 可以通过它进行观测和反馈

updater = EvolutionaryMemoryUpdater()
calculator = updater.fitness_calculator

# 观测记忆使用
calculator.observe_retrieval(memory)
calculator.observe_usage(memory)

# 收集反馈
calculator.record_positive_feedback(memory)
calculator.record_negative_feedback(memory)
```

## 运行示例

```bash
# 设置 PYTHONPATH
export PYTHONPATH=/path/to/ContextMind

# 运行示例
python3 contextmind/evolution/examples/evolutionary_memory_demo.py
python3 contextmind/evolution/examples/observation_feedback_demo.py
python3 contextmind/evolution/examples/practical_feedback_collection_demo.py
```

## 核心特性

### 1. 进化式记忆更新

- **适应度评估**: 多维度评估记忆价值
- **精英选择**: 保留高适应度记忆
- **智能合并**: 使用 embedding 相似度合并相似记忆
- **自动淘汰**: 删除低价值记忆

### 2. 观测和反馈

- **观测收集**: 检索、使用、忽略事件
- **显式反馈**: 点赞、点踩、纠正
- **隐式反馈**: 对话延续、重复、澄清
- **自动评估**: 贡献度评估

### 3. 持续学习

- **动态适应度**: 基于观测和反馈调整
- **质量保证**: 准确性自动更新
- **贡献度跟踪**: 评估实际价值

## 最新改进

### v1.0.0 - 2026-01-28

- ✅ **模块简化**: 扁平化目录结构，从3层减少到1层
- ✅ **相似度计算**: 统一使用 embedding 向量余弦相似度
- ✅ **适应度保存**: 完整保存所有观测和反馈数据
- ✅ **衰减改进**: 基于时间的智能衰减，而非每次更新
- ✅ **类型统一**: 移除重复定义，避免冲突
- ✅ **示例修复**: 所有示例程序导入路径已修正

## 与 ContextMind 核心的关系

- **可选模块**: evolution 是高级扩展，不影响核心
- **核心依赖**: 依赖 contextmind.memory 的基础组件
- **灵活集成**: 可以选择使用 SimpleUpdater 或 EvolutionaryMemoryUpdater

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

另请参阅项目根目录的文档：

- `../../docs/UNDERSTANDING_OBSERVATION_FEEDBACK_LEARNING.md` - 通俗易懂的解释
- `../../docs/EVOLUTION_MODULE_ANALYSIS.md` - 深入分析报告
- `../../docs/EVOLUTION_MODULE_SIMPLIFICATION.md` - 简化说明

## 版本

当前版本: 1.0.0

## 许可

与 ContextMind 主项目相同
