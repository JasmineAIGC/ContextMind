# S* 生成器

本目录实现了 **S\*** 代码合成算法，来源于论文 [arXiv:2502.14382](https://arxiv.org/abs/2502.14382)。

## 算法流程

S\* 将生成过程分为四个阶段（Phase P / D / S / R）：

```
Phase P：并行草稿生成（Parallel Drafting）
  └─ 同时采样 N 条候选代码实现

Phase D：执行轨迹修复（Trace-based Repair）
  └─ 对每条候选执行测试，收集失败轨迹
     根据轨迹信息对各候选独立修复

Phase S：区分性选择（Discriminating Selection）
  └─ 构造区分性测试，在候选集合中选出最优实现
     利用候选之间的行为差异进行交叉验证

Phase R：精化（Refinement）
  └─ 对选中实现执行最终精化，确保通过全部测试
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `synthesizer.py` | `SStarSynthesizer` 类，实现 P/D/S/R 四阶段逻辑 |
| `builder.py` | `build_pytod_apis_sstar` 入口函数，批量调用 synthesizer |
| `prompts.py` | S\* 各阶段专用提示模板 |
| `__init__.py` | 模块导出 |

## 核心优势

- **并行采样**：Phase P 同时生成多条候选，增大解空间覆盖率。
- **轨迹驱动修复**：Phase D 利用执行轨迹精准定位错误，修复质量高。
- **区分性选择**：Phase S 通过构造对抗性测试消除等价错误实现，选出真正正确的候选。
- **适合高召回场景**：多候选机制在测试较复杂时仍能稳定产出正确实现。

## 参考文献

> Deng et al., "S*: Test Time Scaling for Code Generation", arXiv:2502.14382, 2025.
