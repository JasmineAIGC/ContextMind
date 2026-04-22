# PyTOD 代码生成器

本目录包含 ContextMind 的 PyTOD 函数代码生成系统，共提供四种生成策略。

详细算法原理请参阅：**[docs/algorithms/pytod-codegen.md](../../../../docs/algorithms/pytod-codegen.md)**

## 目录结构

```
pytod/
├── __init__.py
├── codegen/             # 代码生成策略（四种）
│   ├── shared/          # 共享组件
│   │   ├── generator.py # PyTODApiCodeGenerator 主类（LLM 调用封装）
│   │   ├── helpers.py   # SHARED_HELPERS 工具函数库
│   │   ├── cleaner.py   # 代码清理工具
│   │   └── kb_loader.py # KB 数据加载工具
│   ├── loop/            # 基础循环修复五阶段流水线（默认）
│   ├── alpha/           # AlphaCodium 风格的 ACIA 生成器
│   ├── sstar/           # S* 生成器（arXiv:2502.14382）
│   └── ctree/           # CodeTree 生成器（arXiv:2411.04329）
└── testcase/            # 测试用例生成与缓存
    ├── generator.py     # LLM 测试用例生成
    ├── models.py        # FuncValidation / TestCaseItem 数据模型
    ├── validator.py     # validate_function / write_validation_report
    ├── cache.py         # 测试用例缓存管理
    ├── kb_loader.py     # KB 数据加载
    └── prompts.py       # 测试用例生成提示词
```

## 四种生成策略

| 策略 | 目录 | `generator` 参数值 | 说明 |
|------|------|----------------------|------|
| 基础循环修复 | `codegen/loop/` | `"loop"`（默认） | 顺序执行的五阶段流水线，适合一般场景 |
| ACIA | `codegen/alpha/` | `"alpha"` | AlphaCodium 风格的迭代修复，鲁棒性强 |
| S\* | `codegen/sstar/` | `"sstar"` | 并行采样 + 区分性选择，适合高质量要求场景 |
| CodeTree | `codegen/ctree/` | `"ctree"` | UCB 引导的树搜索，适合复杂函数生成 |

## 使用方式

通过 `generator` 参数选择生成策略：

```python
from contextmind.schema_builder import SchemaDataBuilder

# 使用默认基础生成器（loop）
builder = SchemaDataBuilder()

# 使用 ACIA 生成器
builder = SchemaDataBuilder(generator="alpha")

# 使用 S* 生成器
builder = SchemaDataBuilder(generator="sstar")

# 使用 CodeTree 生成器
builder = SchemaDataBuilder(generator="ctree")
```

