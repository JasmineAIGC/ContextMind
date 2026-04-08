# CodeTree 生成器

本目录实现了 **CodeTree** 代码合成算法，来源于论文 [arXiv:2411.04329](https://arxiv.org/abs/2411.04329)。

## 算法流程

CodeTree 将代码生成建模为一棵搜索树，使用 UCB（Upper Confidence Bound）策略引导扩展：

```
根节点生成（Root Generation）
  └─ 生成初始候选实现作为树的根节点

      ┌──────────────── UCB 引导循环 ────────────────┐
      │                                             │
      │  选择（Selection）                           │
      │    根据 UCB 分数选择最具潜力的节点             │
      │        ↓                                   │
      │  扩展（Expansion）                           │
      │    对选中节点生成子代码变体（修复 / 重写）      │
      │        ↓                                   │
      │  评估（Evaluation）                          │
      │    执行测试，计算节点得分并更新 UCB 统计信息    │
      │        └────────────────────────────────── ┘
      │
      └─ 返回得分最高的叶节点实现
```

## 文件说明

| 文件 | 说明 |
|------|------|
| `synthesizer.py` | `CodeTreeSynthesizer` 类，实现 UCB 树搜索逻辑 |
| `builder.py` | `build_pytod_apis_ctree` 入口函数，批量调用 synthesizer |
| `prompts.py` | CodeTree 各阶段专用提示模板 |
| `__init__.py` | 模块导出 |

## 核心优势

- **结构化探索**：树结构天然记录生成历史，避免重复尝试相同方向。
- **UCB 平衡探索与利用**：既充分探索潜在正确路径，又集中资源深化有希望的候选。
- **适合复杂函数**：对于逻辑复杂、边界条件多的函数，树搜索能更系统地覆盖各种实现思路。

## 参考文献

> Li et al., "CodeTree: Agent-guided Tree Search for Code Generation with Large Language Models", arXiv:2411.04329, 2024.
