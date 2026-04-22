# 循环修复五阶段流水线（Loop Generator）

## 方法名称

**循环修复五阶段流水线**（Loop Repair Pipeline）

## 使用方式

```bash
python -m contextmind ... --generator loop（默认）
```

或在代码中：

```python
from contextmind.schema_builder import SchemaDataBuilder

builder = SchemaDataBuilder(generator="loop")
```

## 五个阶段说明

| 阶段 | 名称 | 说明 |
|------|------|------|
| Phase 1 | 解析 schema | 从 `*_schema.json` 中提取所有意图（Intent）和槽位（Slot）定义 |
| Phase 2 | LLM 生成测试用例 | 为每个意图调用 LLM，生成包含真实业务值的测试用例（`TestCaseItem`） |
| Phase 3 | 逐函数 LLM 生成代码 | 逐意图调用 LLM 生成初始函数体，可选带入 few-shot 测试用例作为上下文 |
| Phase 4 | 验证 + 迭代修复 | 执行生成的函数、计算测试通过率，对失败函数迭代调用 LLM 修复，直至预算耗尽 |
| Phase 5 | 组装 + 可选报告 | 将所有函数拼装为完整 `.py` 文件，可选写入验证报告（JSON） |

## 核心文件

| 文件 | 说明 |
|------|------|
| `builder.py` | `build_pytod_apis` 函数，五阶段流水线主入口 |
| `prompts.py` | 基础流水线各阶段 LLM 提示词模板 |

共享文件（位于 `pytod/` 层级，供所有生成器使用）：

| 文件 | 说明 |
|------|------|
| `../generator.py` | `PyTODApiCodeGenerator`，测试用例生成与 LLM 调用封装 |
| `../helpers.py` | `SHARED_HELPERS`，注入函数体的公共辅助工具库 |
| `../models.py` | `FuncValidation`、`TestCaseItem` 数据模型 |
| `../validator.py` | `validate_function`、`write_validation_report` 验证工具 |

## 为什么效果好

基础五阶段流水线在大多数场景下综合表现最优，主要原因：

1. **修复信号最直接**：`REPAIR_SYSTEM` 提示词直接提供完整函数代码 + 失败信息 + 业务语义要求，LLM 无需额外推理步骤。

2. **迭代预算全用于修复**：其他策略（尤其 S\*）将预算分配给中间阶段（反思、并行草稿、区分性测试生成），减少了直接修复的迭代次数；基础流水线将全部迭代预算投入到实际修复中。

3. **修复提示词包含完整函数上下文**：基础流水线的 `REPAIR` 提示包含当前完整函数体，使 LLM 能在正确的基础上做改进，而非从头推断。

4. **避免中间层噪声**：Alpha 的反思（Reflection）和失败分析（Analysis）阶段有时会产生不准确的推断，将修复引向错误方向；基础流水线直接用失败用例驱动重写，更为精准。
