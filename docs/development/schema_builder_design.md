# Schema 数据生成器设计文档（第二步）

> **ContextMind 三步框架中的第二步**：
> - **第一步**（`contextmind.knowledge`）：任意数据集 → 知识库（`schema.json`）
> - **第二步**（`contextmind.schema_builder`，本文档）：知识库 → 适配不同算法的 Schema 数据
> - **第三步**（`contextmind.modes.*`）：算法执行（DST / FnCTOD / PyTOD / Evolve）
>
> 注意：第二步为可选步骤，仅 PyTOD 等需要自动生成 API 代码的算法才用到；DST、FnCTOD、Evolve 可跳过此步直接进入第三步。

## 目录结构

```
contextmind/schema_builder/
├── builder.py           # SchemaDataBuilder — 顶层入口，通过 generator 参数选择策略
├── utils.py             # companion_path 工具函数
├── fnctod/              # FnCTOD companion 生成（stub）
├── genie_worksheets/    # Genie Worksheets schema 类型与加载器
└── pytod/               # PyTOD 所有代码生成策略
    ├── README.md        # 四种策略总览及使用说明
    ├── ALGORITHMS.md    # 各生成策略算法原理详解（见 docs/algorithms/pytod-codegen.md）
    ├── __init__.py
    ├── codegen/         # 代码生成策略（四种）
    │   ├── shared/      # 共享组件
    │   │   ├── generator.py   # PyTODApiCodeGenerator（LLM 调用封装）
    │   │   ├── helpers.py     # SHARED_HELPERS 工具函数库
    │   │   ├── cleaner.py     # 代码清理工具
    │   │   └── kb_loader.py   # KB 加载工具
    │   ├── loop/        # 基础五阶段循环修复流水线（默认）
    │   ├── alpha/       # ACIA 生成器（AlphaCodium 风格）
    │   ├── sstar/       # S* 生成器（arXiv:2502.14382）
    │   └── ctree/       # CodeTree 生成器（arXiv:2411.04329）
    └── testcase/        # 测试用例生成与缓存
        ├── generator.py # LLM 测试用例生成
        ├── models.py    # FuncValidation / TestCaseItem 数据模型
        ├── validator.py # validate_function / write_validation_report
        ├── cache.py     # 测试用例缓存管理
        ├── kb_loader.py # KB 数据加载
        └── prompts.py   # 测试用例生成提示词
```

## 生成策略对比

| 策略 | `generator` 参数值 | 核心思路 | 适用场景 |
|------|--------------------|---------|----|
| 基础循环修复 | `"loop"`（默认） | 全模块生成 + 逐函数迭代修复 | 通用场景，稳定性最高 |
| ACIA | `"alpha"` | 反思 → 生成 → 失败分析 → 定向修复 | 业务语义复杂、需深度理解场景 |
| S\* | `"sstar"` | 并行草稿 + 执行追踪修复 + 区分性选择 | 高质量要求、算法预算充足场景 |
| CodeTree | `"ctree"` | UCB 引导树搜索、每失败用例独立修复 | 多测试用例、需多样化探索场景 |

### 基础循环修复（loop）表现更好的原因

通过测试对比，`loop` 策略在大多数情况下综合表现最优，主要原因：

1. **修复信号最直接**：`REPAIR_SYSTEM` 提示词直接提供完整函数代码 + 失败信息 + 业务语义要求，LLM 无需额外推理步骤。
2. **迭代预算全用于修复**：其他策略（尤其 S\*）将预算分配给中间阶段（反思、并行草稿、区分性测试生成），减少了直接修复的迭代次数。
3. **修复提示词包含完整函数上下文**：使 LLM 能在正确的基础上做改进，而非从头推断。
4. **避免中间层噪声**：Alpha 的反思和失败分析阶段有时会产生不准确的推断；基础流水线直接用失败用例驱动重写，更为精准。

## Step 2 整体目标

将第一步生成的 `xxx_schema.json`（包含意图和槽位）转换为一个包含所有意图具体实现函数的 Python 文件 `xxx_pytod_apis.py`，每个函数具备清晰入参、具体运算逻辑和统一出参格式。

## Step 2 完整运行步骤（共 5 个阶段）

**阶段 1：解析 schema.json**
- 读取第一步输出的 `xxx_schema.json` 文件
- 解析所有 `services` 和其中的 `intents`
- 提取每个 intent 的核心信息：`intent_name`、`intent_description`、`slots` 列表（每个 slot 包含 `name`、`description`、`required` 等）

**阶段 2：构建测试用例**
- 读取一个或多个真实的业务测试数据文件（JSON 格式）
- 按 intent_name 聚合对话 turn，为 schema.json 中每个 intent 提取 5~10 条高质量测试用例
- 每条测试用例包含：`input_slots`（实际填充的槽位值）和 `expected_result`（预期返回结果 / label）

**阶段 3：初始函数生成**
- 对 schema.json 中的每一个 intent 逐一处理，调用 LLM 生成函数体
- 生成统一返回格式：`{"status": "success"|"error", "message": "...", "result": {...}}`

**阶段 4：验证与迭代优化**
- 使用阶段 2 构建的测试用例，对已生成的函数进行批量执行验证
- 计算每个 intent 的 pass_rate（通过率）
- 对于未达阈值（默认 90%）的 intent，收集失败案例并调用 LLM 修复，最多迭代 N 轮（默认 3）

**阶段 5：生成最终输出文件**
- 组装完整 Python 代码文件 `xxx_pytod_apis.py`，包含每个 intent 的函数定义
- 文件底部添加 `INTENT_REGISTRY` 字典（intent_name → 函数名映射）
- 可选：同时生成 `validation_report.json`，记录每个 intent 的通过率和迭代情况

## 伪代码概述

```python
def run_step2(schema_path, test_data_paths=None, output_path="xxx_pytod_apis.py"):
    # 阶段1
    schema = parse_schema(schema_path)

    # 阶段2
    test_cases = build_test_cases(test_data_paths, schema) if test_data_paths else {}

    # 阶段3 + 阶段4
    functions = {}
    for intent in schema.all_intents:
        body = initial_generate(intent, test_cases.get(intent.name))
        if test_cases.get(intent.name):
            body = iterative_optimize(intent, body, test_cases[intent.name])
        functions[intent.name] = build_full_function(intent, body)

    # 阶段5
    final_code = assemble_python_file(functions, schema)
    save_to_file(final_code, output_path)
```

## 运行注意事项

- 整个过程以 `schema.json`（第一步输出）中的意图和槽位为核心依据
- 测试数据仅用于增强生成质量和迭代优化，不强制要求
- 最终输出仅为一个 `xxx_pytod_apis.py` 文件，结构清晰、函数独立、可直接执行
- 迭代优化仅针对有测试用例且初始验证失败的意图，控制计算成本
- **第三步**（`contextmind.modes.pytod`）可直接 import 该文件，通过 `INTENT_REGISTRY` 调用任意意图函数
- DST、FnCTOD、Evolve 等算法**不需要**执行第二步，可从第一步直接进入第三步

## 相关文档

- [PyTOD 代码生成算法原理](../algorithms/pytod-codegen.md) — 四种生成策略详解
- [PyTOD 算法说明](../algorithms/pytod.md) — PyTOD 运行时算法
