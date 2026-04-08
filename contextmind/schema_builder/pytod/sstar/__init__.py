"""
S*（S-star）PyTOD API 代码生成器包。

基于论文：S*: Test Time Scaling for Code Generation（arXiv:2502.14382，2025）
在 PyTOD 意图函数生成场景下的适配实现。

入口：
    :func:`contextmind.schema_builder.sstar.builder.build_pytod_apis_sstar`

算法说明：
    Phase P — 并行草稿生成（以不同思维模式生成 N 个候选实现）
    Phase D — 执行追踪驱动修复（基于实际执行输出精准定位并修复 bug）
    Phase S — 区分性测试选择（S* 核心：生成能区分两候选的输入，通过执行行为选优）
    Phase R — 最优候选精炼（对选出的最优候选继续修复直至达到通过率阈值）
"""
