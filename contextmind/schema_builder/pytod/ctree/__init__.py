"""
CodeTree 代码生成器包。

基于 CodeTree（arXiv:2411.04329，2024/2025）在 PyTOD 意图函数生成场景下的适配实现。

算法核心：用树形搜索替代线性或平铺搜索，对每个失败测试用例
独立生成修复分支（子节点），通过 UCB 评分（通过率 + 探索奖励）
在整棵树上选择最优修复路径，有效避免线性修复陷入局部最优。

选择算法来自：
    CodeTree: Agent-guided Tree Search for Code Generation with Large Language Models,
    arXiv:2411.04329, 2024/2025.
"""
