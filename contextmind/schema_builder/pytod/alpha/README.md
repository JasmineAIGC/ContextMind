# Alpha 生成器（ACIA 算法）

本目录实现了基于 [AlphaCodium](https://arxiv.org/abs/2401.08500) 论文思路的 **ACIA**（Analyze-Code-Iterate-and-Amend）迭代修复生成器。

## 算法流程

ACIA 将单次代码生成分解为四个阶段，形成闭环迭代：

```
┌─────────────────────────────────────────────────────┐
│                    ACIA 迭代循环                      │
│                                                     │
│  1. Reflection（反思）                               │
│     分析函数规约与测试用例，理解预期行为               │
│         ↓                                           │
│  2. Generation（生成）                               │
│     根据反思结果生成候选代码实现                       │
│         ↓                                           │
│  3. Failure Analysis（失败分析）                     │
│     执行测试，若失败则分析失败原因                     │
│         ↓                                           │
│  4. Repair + Reset（修复 / 重置）                    │
│     针对失败原因修复代码；若无法修复则重置重试          │
│         └──────────────────────────────────────────┘
└─────────────────────────────────────────────────────┘
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `synthesizer.py` | `AlphaSynthesizer` 类，实现 ACIA 四阶段逻辑 |
| `builder.py` | `build_pytod_apis_alpha` 入口函数，批量调用 synthesizer |
| `prompts.py` | ACIA 各阶段专用提示模板 |
| `__init__.py` | 模块导出 |

## 核心优势

- **闭环修复**：自动分析测试失败原因，而非盲目重试。
- **重置机制**：当修复方向错误时，主动重置上下文重新生成，避免陷入局部最优。
- **低 token 消耗**：相比并行采样策略，每次迭代只维护单条候选，资源占用更低。

## 参考文献

> Tal Ridnik et al., "AlphaCodium: From Weak to Strong Code Generation by a Test-Based, Multi-Stage, Code-Oriented Iterative Flow", arXiv:2401.08500, 2024.
