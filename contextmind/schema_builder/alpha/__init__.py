"""
AlphaCodium 风格 PyTOD API 代码合成器（ACIA）。

相比 pytod/ 的简单「生成-测试-修复」循环，本包实现了四项关键改进：

1. **反思步骤（Reflection）**：
   生成代码前，先让 LLM 分析函数的业务语义、所需计算逻辑、返回值默认值，
   将分析结果作为生成上下文，大幅提升初始代码质量。

2. **骨架约束生成（Skeleton-constrained Generation）**：
   预先从 schema.result_slots 构建返回字典骨架，在提示词中明确指定
   函数必须返回哪些键，从根本上消除「缺少 result_slots 字段」类失败。

3. **失败模式分析（Failure Pattern Analysis）**：
   修复前先对失败测试用例进行结构化分类（缺少键/值错误/运行时异常），
   将分析结果注入修复提示词，使 LLM 针对具体问题进行定向修复，
   而非盲目重写整个函数体。

4. **收敛检测 + 全新重启（Convergence Reset）**：
   连续 2 轮修复通过率无提升时，完全丢弃当前代码，从新的反思开始重新生成，
   彻底避免 docstring 累积、补丁叠加等退化问题，跳出局部最优。

使用方式（命令行）::

    # 使用 ACIA 生成器
    python examples/build_schema_data.py --with-llm --generator alpha

    # 与其他选项组合
    python examples/build_schema_data.py --with-llm --generator alpha \\
        --kb-dir output/kb_output --max-iterations 5 --verbose
"""

from contextmind.schema_builder.alpha.builder import build_pytod_apis_alpha

__all__ = ["build_pytod_apis_alpha"]
