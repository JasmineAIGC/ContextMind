# Genie 完整实现规划

> 生成时间：2026-04-21  
> 参考：Genie 论文 [arXiv:2407.05674](https://arxiv.org/abs/2407.05674) ·
>  源码 [stanford-oval/genie-worksheets](https://github.com/stanford-oval/genie-worksheets)  
> 状态：**实施中**

---

## 一、原始 Genie 架构 vs ContextMind 现有 Genie 实现

### 1.1 原始 Genie 完整架构（源码层面）

```
stanford-oval/genie-worksheets/src/worksheets/
├── core/
│   ├── worksheet.py        — GenieWorksheet 基类（Python 类 + @geniews 装饰器）
│   ├── fields.py           — GenieField / GenieValue（富类型字段系统）
│   ├── runtime.py          — GenieRuntime（主运行时：execute DSL 代码）
│   ├── agent_acts.py       — AgentAct 层（Ask/AskForConfirmation/Report/Propose）
│   ├── context.py          — GenieContext（全局 / 局部命名空间）
│   ├── dialogue.py         — 对话历史
│   └── builtin_functions.py — say / confirm / propose / no_response / chitchat
├── specification/
│   └── from_spreadsheet.py — 从 Google Sheets / CSV 加载 Worksheet 规范
├── prompts/
│   ├── semantic_parser.prompt      — LLM-1：生成 Plan + Python DSL 代码
│   ├── response_generator.prompt   — LLM-2：根据 AgentActs + State 生成回复
│   ├── validation_check.prompt     — LLM-3：校验 DSL 合法性
│   └── suql_parser.prompt          — SUQL 查询生成
├── knowledge/              — SUQL + PostgreSQL 知识库
└── agent/                  — 高层 Agent 协调器
```

**Genie 关键数据流（每轮）**：

```
用户输入
   │
   ▼
SemanticParser (LLM-1)
  → 输出: Plan + Python DSL ("Code" block)
  → DSL 语法: Constructor 风格更新字段 + answer() + confirm() 等内置函数
   │
   ▼
GenieRuntime.execute(dsl_code)
  → 更新 GenieContext 中的 Worksheet 实例
  → 运行内置函数副作用（confirm → PENDING_CONFIRM，answer → SUQL 查询）
   │
   ▼
AgentActs 计算（确定性，无 LLM）
  → 遍历所有 Worksheet，生成动作列表：
    AskField / AskForConfirmation / AskForFieldConfirmation / Report / ProposeWorksheet
   │
   ▼
ResponseGenerator (LLM-2)
  → 输入: State + AgentActs + 对话历史
  → 输出: 自然语言回复（按照 AgentActs 顺序逐条 verbalize）
   │
   ▼
系统回复 + 更新对话历史
```

### 1.2 ContextMind 现有 Genie 实现

```
contextmind/modes/genie/
├── __init__.py
├── policy_executor.py      ✅ 已实现（无 LLM 状态机）
├── semantic_parser.py      ⚠️ 简化（单次 JSON 提取，无 Plan/DSL 步骤）
└── tracker.py              ⚠️ 部分（缺少确认流程 + on_success dispatch）

contextmind/schema_builder/genie_worksheets/
├── models.py               ✅ 已实现（PolicyField）
├── schema_types.py         ✅ 已实现（GenieSchema/Intent/Slot）
└── loader.py               ✅ 已实现（CSV/JSON 导入/导出）
```

---

## 二、差距对比分析

| 功能 | 原始 Genie | ContextMind 现状 | 优先级 | 备注 |
|------|-----------|-----------------|--------|------|
| **Worksheet 定义格式** | Python 类 + 装饰器 | CSV/JSON + PolicyField | ✅ 满足 | ContextMind 更适合业务人员维护 |
| **语义解析输出格式** | Plan + Python DSL | 直接 JSON 提取 | P2 | 加入推理步骤（Plan+Extract） |
| **AgentActs 层** | 完整（Ask/Confirm/Report/Propose） | 缺失 | **P1** | 影响确认流程和回复质量 |
| **确认流程** | PENDING_CONFIRM → CONFIRMED | PolicyExecutor 有状态，但 Tracker 未处理 | **P1** | 关键功能，现在无法工作 |
| **on_success dispatch** | backend_api + 后端调用 | PolicyField 有字段，Tracker 从不调用 | **P1** | API 触发完全未实现 |
| **状态 verbalize** | State 渲染为 Python-dataclass 格式 | Worksheet 字典直接注入 | P2 | 改善回复质量 |
| **Pipeline Bug** | 不涉及 | `_service_schema_to_genie_schema` raw dict 未转为 PolicyField | **P1** | AttributeError 在此处触发 |
| **Prompts 目录** | 独立 .prompt 文件 | 嵌入 Python 代码 | P2 | 可维护性，非功能性 |
| **示例文件** | examples/ 目录 | 无 | P2 | 用户引导 |
| **SUQL 知识库** | PostgreSQL + pgvector | 无（LLM 降级） | P3 | 可选扩展，已在 research doc 记录 |
| **嵌套 Worksheet** | worksheet_type 字段 | 无 | P3 | 复杂场景，稳健后可加 |

---

## 三、需要实现的内容（分优先级）

### P1：关键功能完整性修复（当前有 Bug 或功能缺失）

#### 3.1 Bug 修复：`pipeline.py` raw dict → PolicyField 转换

**位置**：`contextmind/pipeline.py` 函数 `_service_schema_to_genie_schema`

**问题**：从 `ServiceSchema.IntentDefinition.policy_fields` 复制字段时，
原始格式是 `List[dict]`（由 `from_dict` 路径保留），未转换为 `PolicyField` 对象。
`PolicyExecutor.__init__` 接收后访问 `pf.required` 会抛 `AttributeError`。

**修复**：
```python
from contextmind.schema_builder.genie_worksheets.models import PolicyField

policy_fields=[
    pf if isinstance(pf, PolicyField) else PolicyField.from_dict(pf)
    for pf in i.policy_fields
],
```

#### 3.2 新增 AgentActs 层

**位置**：`contextmind/modes/genie/agent_acts.py`（新文件）

移植 Genie `agent_acts.py` 中的：
- `AgentAct`（基类）
- `AskAgentAct`（主动询问字段）
- `AskForConfirmationAgentAct`（请求确认字段值）
- `ReportAgentAct`（报告 API 执行结果）
- `AgentActs`（动作队列容器，含互斥规则）

适配为 ContextMind 风格（不依赖 `loguru`，不依赖 `GenieField`）。

#### 3.3 实现确认流程（`tracker.py` + `policy_executor.py`）

**当前问题**：`PolicyExecutor.fill_field` 在 `confirm=True` 时设置 `PENDING_CONFIRM` 状态，
但 `GenieTracker.process_turn` 完全不检查此状态，确认逻辑死路。

**实现步骤**：

1. `PolicyExecutor` 新增 `get_pending_confirm_fields() -> List[PolicyField]`
2. `GenieTracker.process_turn` 改造：
   - 每轮先检查是否存在 `PENDING_CONFIRM` 字段
   - 若有：解析用户话语中的 yes/no 确认意图
   - yes → `executor.confirm_field(name)` 将状态改为 `CONFIRMED`
   - no → `executor.reject_field(name)` 清空字段值（新增方法）
3. 在 `AgentActs` 列表中加入 `AskForConfirmationAgentAct`
4. 回复生成器接收 `AgentActs` 列表，按顺序 verbalize

#### 3.4 实现 `on_success` API dispatch

**当前问题**：`PolicyField.on_success` 存储了字段填完后要调用的函数名，
但 `GenieTracker` 从未检查或调用它。

**实现步骤**：

1. `GenieTracker` 新增 `register_api(func_name: str, func: Callable)` 方法
2. `PolicyExecutor` 新增 `get_on_success_actions() -> List[Tuple[str, str]]`，
   返回所有已填且有 `on_success` 字段的 `(field_name, api_name)` 对
3. `GenieTracker.process_turn` 每轮检查是否有新填字段触发 `on_success`
4. 调用注册的 API 函数，将结果放入 `ReportAgentAct`

---

### P2：质量改进（不影响核心功能，但显著提升效果）

#### 3.5 增强 SemanticParser（加入 Plan 推理步骤）

**当前问题**：单次 JSON 提取，LLM 没有推理空间，容易漏提取字段。

**改进**：仿照 Genie `semantic_parser.prompt` 中的 Plan + Code 结构，
让 LLM 先输出 `# 思考:` 段落（Reason），再输出 `# 提取结果:` JSON（Act）。
增加一个 `_parse_output_with_reason` 方法。

#### 3.6 新增 `prompts/` 目录

**位置**：`contextmind/modes/genie/prompts/`

将 `semantic_parser.py` 和 `tracker.py` 中的提示词常量移入独立 `.prompt` 文件：

```
contextmind/modes/genie/prompts/
├── semantic_parsing.prompt      ← 字段提取提示词（中文优化）
└── response_generator.prompt    ← 回复生成提示词（基于 AgentActs）
```

#### 3.7 新增示例 Worksheet 文件

**位置**：`resources/worksheets/`

```
resources/worksheets/
├── restaurant_booking.csv       ← 餐厅预订（演示 enum + confirm）
├── customer_service.csv         ← 客服工单（演示 depends_on）
└── restaurant_booking.json      ← 同上但 JSON 格式
```

---

## 四、修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `contextmind/pipeline.py` | **修改** | Bug 修复：PolicyField dict 转换 |
| `contextmind/modes/genie/agent_acts.py` | **新增** | AgentAct 类层次 |
| `contextmind/modes/genie/policy_executor.py` | **修改** | 新增 `get_pending_confirm_fields`, `reject_field`, `get_on_success_actions` |
| `contextmind/modes/genie/semantic_parser.py` | **修改** | 增加 Plan+Reason 推理步骤 |
| `contextmind/modes/genie/tracker.py` | **修改** | 确认流程 + on_success dispatch + AgentActs |
| `contextmind/modes/genie/__init__.py` | **修改** | 导出 AgentActs 新类 |
| `contextmind/modes/genie/prompts/` | **新增** | 提示词文件目录 |
| `resources/worksheets/` | **新增** | 示例 Worksheet 文件 |
| `tests/test_genie_tracker.py` | **修改** | 新增确认流程 + on_success 测试 |

---

## 五、不引入到 ContextMind 的原始 Genie 组件

| Genie 组件 | 不引入原因 |
|-----------|---------|
| `GenieWorksheet` Python 类 + `@geniews` 装饰器 | ContextMind 的 CSV/JSON + PolicyField 方案对业务人员更友好，功能等价 |
| `GenieRuntime.execute()` Python DSL 解释器 | 复杂度高，依赖自定义 AST 重写；ContextMind JSON 提取已满足需求 |
| `GenieField` 富类型系统 | 与 `PolicyField` 功能重叠；Genie 依赖 `loguru`/`BeautifulSoup` 等额外依赖 |
| `SUQLKnowledgeBase` + PostgreSQL | Phase 3（可选扩展），当前降级模式足够 |
| Chainlit / uvicorn 前端 | ContextMind 已有 Gradio UI |
| Google Sheets 同步 | 企业场景不适合；CSV 格式已足够 |

---

## 六、实现完成后的效果对比

| 场景 | 修复前 | 修复后 |
|------|--------|--------|
| `confirm=True` 字段确认 | 设置 PENDING_CONFIRM 但从不处理 → 永远不会请求确认 | 检测到 PENDING_CONFIRM → 生成确认问题 → yes/no 处理 → CONFIRMED |
| `on_success="book_api"` 字段 | 字段填完后什么都不发生 | 自动调用注册的 `book_api` 函数，结果作为 ReportAgentAct 呈现 |
| `ServiceSchema` → Genie 路径 | `AttributeError: 'dict' object has no attribute 'required'` | 正常运行 |
| 语义解析 | 单次 JSON 提取，复杂话语容易漏 | Plan→Extract 两步，推理后提取更准确 |
| 回复生成 | 固定模板，不感知 AgentActs | 按 AgentActs 列表结构化 verbalize，与原版 Genie 对齐 |
