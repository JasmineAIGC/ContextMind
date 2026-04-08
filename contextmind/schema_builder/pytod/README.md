# PyTOD 代码生成器

本目录包含 ContextMind 的 PyTOD 函数代码生成系统，共提供四种生成策略。

## 目录结构

```
pytod/
├── generator.py     # PyTODApiCodeGenerator 主类（共享）
├── helpers.py       # 共享辅助函数（SHARED_HELPERS）
├── models.py        # 数据模型（FuncValidation、TestCaseItem）
├── prompts.py       # 基础提示模板（共享，供 generator.py 使用）
├── validator.py     # 函数验证与报告（共享）
├── base/            # 基础五阶段流水线生成器
├── alpha/           # AlphaCodium 风格的 ACIA 生成器
├── sstar/           # S* 生成器（arXiv:2502.14382）
└── ctree/           # CodeTree 生成器（arXiv:2411.04329）
```

## 四种生成策略

| 策略 | 目录 | `--generator` 参数值 | 说明 |
|------|------|----------------------|------|
| 基础五阶段 | `base/` | `pytod`（默认） | 顺序执行的五阶段流水线，适合一般场景 |
| ACIA | `alpha/` | `alpha` | AlphaCodium 风格的迭代修复，鲁棒性强 |
| S\* | `sstar/` | `sstar` | 并行采样 + 区分性选择，适合高质量要求场景 |
| CodeTree | `ctree/` | `ctree` | UCB 引导的树搜索，适合复杂函数生成 |

## 使用方式

通过 `--generator` 参数选择生成策略：

```bash
# 使用默认基础生成器
python -m contextmind ... --generator pytod

# 使用 ACIA 生成器
python -m contextmind ... --generator alpha

# 使用 S* 生成器
python -m contextmind ... --generator sstar

# 使用 CodeTree 生成器
python -m contextmind ... --generator ctree
```

也可在代码中通过 `SchemaDataBuilder` 的 `generator` 参数指定：

```python
from contextmind.schema_builder import SchemaDataBuilder

builder = SchemaDataBuilder(generator="alpha")
```
