# Genie Schema 分析报告

> 生成时间：2026-04-21  
> 分析对象：`contextmind/modes/genie/`、`contextmind/schema_builder/genie_worksheets/`、`contextmind/pipeline.py`  
> 关联 PR 分支：`copilot/optimize-pytod-api-selection`

---

## 一、Genie Schema 对比 FnCTOD、PyTOD Schema 的核心优势

### 1.1 三种 Schema 本质差异对比

| 维度 | **FnCTOD** (`DomainSpec`) | **PyTOD** (`ServiceSchema / SGD`) | **Genie** (`Worksheet`) |
|------|--------------------------|----------------------------------|------------------------|
| 格式来源 | OpenAI Function Calling JSON Schema | Google SGD（Schema-Guided Dialogue）标准 | Google Sheets / CSV / JSON（自创表格格式）|
| 描述的是什么 | "有哪些槽位，每个槽位类型和约束" | "有哪些意图，每个意图需要哪些槽位" | **"字段收集策略"：按什么顺序问、什么条件下问、是否需要二次确认** |
| 策略在哪里 | 全在 LLM Prompt 里（隐式） | 全在 LLM Prompt 里（隐式，AP 自己决定） | **在 Worksheet 表格里（显式声明，deterministic 执行）** |
| 控制流 | LLM 一次性函数调用，无多轮控制 | LLM 生成 Python-like 程序，EE 执行 | `PolicyExecutor`（纯 Python 状态机，**无 LLM**）按 Worksheet 定义驱动 |
| 维护者 | 开发人员（JSON） | 开发人员（JSON） | **业务人员可直接编辑（CSV/Google Sheets）** |

### 1.2 Genie Worksheet 独有字段（FnCTOD/PyTOD 均无）

```
PolicyField 独有属性：
  confirm       → 填完后是否需要用户二次确认才调用 API
  ask_by_system → 是否由系统主动发起询问（false = 被动等用户提）
  depends_on    → 条件依赖：仅当某字段已填后本字段才生效（动态表单）
  on_success    → 填完后触发哪个 API 函数名
  field_type    → 运行时类型校验（int/float/bool/enum）+ 自动类型强转
```

### 1.3 五大核心优势

#### 优势①：消除控制流幻觉（最重要）
- **FnCTOD/PyTOD**：LLM 的动作预测器（AP）可能在用户未提供必填字段时直接调用 API，或随意跳过收集顺序
- **Genie**：`PolicyExecutor.next_required_field()` 是纯 Python 确定性计算，LLM 只负责「提取字段值」，不负责「决定下一步做什么」，彻底杜绝跳步幻觉

#### 优势②：强制确认流程（`confirm=True`）
- PyTOD 虽有 `ConfirmStatement`，但需 LLM 在 AP 中主动生成 `x2 confirm(x1)` 语句，LLM 时常遗漏
- Genie：在 Worksheet 表格中声明 `confirm=true`，`PolicyExecutor` 会**强制**将字段置为 `PENDING_CONFIRM` 状态，流程无法被绕过

#### 优势③：动态表单 `depends_on`（FnCTOD/PyTOD 完全不支持）
```csv
# 示例：只有选了「国际配送」后，才问「清关文件」
clearance_doc,str,清关文件,true,false,true,shipping_type,,
```
字段 B 依赖字段 A 的值这种条件依赖，FnCTOD/PyTOD 均无法在 schema 层声明。

#### 优势④：业务人员可维护
FnCTOD 的 `DomainSpec` 和 PyTOD 的 `ServiceSchema` 本质是 JSON，需开发人员生成维护；
Genie Worksheet 是 CSV 表格，业务人员直接编辑即可修改询问策略，无需改代码。

#### 优势⑤：运行时类型校验
`PolicyExecutor._coerce_value()` 在填写时自动做类型转换和枚举合法性校验（含模糊匹配），
FnCTOD/PyTOD 的校验逻辑均依赖 LLM 输出正确格式，不做硬校验。

---

## 二、SUQL + PostgreSQL 是否必须实现才能使用 Genie Schema？

### 结论：**不需要**

ContextMind 当前实现已做明确的「降级设计」，Genie 的核心价值（Worksheet 策略声明式执行）
**完全不依赖 SUQL 或 PostgreSQL**。

### Genie 整体架构分层

```
Genie 架构（论文版 vs ContextMind 实现版）
─────────────────────────────────────────────────────
层1 - 策略层（Worksheet 驱动）← ContextMind 已完整实现
  PolicyExecutor     ── 纯 Python 状态机，零 DB 依赖
  SemanticParser     ── LLM 字段提取（JSON 格式输出，非 SUQL）
  GenieTracker       ── 整合以上两者，实现 BaseTracker 协议

层2 - 知识层（SUQL 查询）← ContextMind 未实现，也无需实现
  SUQLReActParser    ── 生成 SUQL 查询语句
  SUQLKnowledgeBase  ── PostgreSQL + pgvector 向量数据库
─────────────────────────────────────────────────────
```

### 何时才需要 SUQL？

仅当场景是**知识密集型**（Knowledge-Intensive）时才有必要：
- 「找到价格低于 100 元、有素食选项的意大利餐厅」（跨结构化 + 语义混合查询）
- 「从 1000 条课程中过滤满足多条件的课程」

**纯槽位收集型场景**（订单查询、表单填写、预约登记）**完全不需要 SUQL**，
`SemanticParser` 直接让 LLM 输出 JSON 字段赋值即可，功能等同于 Worksheet 约束驱动的增强版 DST。

### 降级实现代码依据

`contextmind/modes/genie/tracker.py` 文件头注释明确：
```
降级设计
--------
当没有 PostgreSQL 时（默认），SUQL 检索降级为 LLM 直接语义回答，
功能等同于 Worksheet 约束驱动的增强版 DST。
```

---

## 三、Genie 实现完整性检查

### 3.1 已正确实现的组件

| 组件 | 文件 | 状态 | 说明 |
|------|------|------|------|
| `PolicyField` 数据模型 | `schema_builder/genie_worksheets/models.py` | ✅ 完整 | 9 个字段含完整序列化/反序列化 |
| `WorksheetLoader` | `schema_builder/genie_worksheets/loader.py` | ✅ 完整 | 支持 CSV/JSON 双格式加载和导出 |
| `GenieSlot/GenieIntent/GenieSchema` | `schema_builder/genie_worksheets/schema_types.py` | ✅ 完整 | 独立于 PyTOD，与 SGD 解耦 |
| `PolicyExecutor` 状态机 | `modes/genie/policy_executor.py` | ✅ 完整 | `next_required_field/fill_field/confirm_field/is_complete/depends_on` 全部实现 |
| `SemanticParser` | `modes/genie/semantic_parser.py` | ✅ 完整 | JSON 提取 + markdown 代码块处理 + 错误降级 + `_find_first_json_object` 嵌套解析 |
| `GenieTracker` | `modes/genie/tracker.py` | ✅ 完整 | LLM-1（解析）+ LLM-2（回复生成）双步骤，含 `from_scenario` 工厂方法 |
| `pipeline.py` 集成 | `pipeline.py` | ✅ 完整 | `mode="genie"` 路由正确；`_service_schema_to_genie_schema` 桥接函数正确携带 `policy_fields` |
| EE 策略约束检查 | `modes/pytod/execution_engine.py` | ✅ 完整 | `_check_policy_constraints` 同时处理 `PolicyField` 对象和原始 dict |
| 单元测试 | `tests/test_genie_tracker.py` | ✅ 完整 | 覆盖 PolicyExecutor / SemanticParser / GenieTracker，含 mock LLM |

### 3.2 发现的潜在 Bug（1 处，有条件触发）

#### Bug：`policy_fields` raw dict 未转换为 `PolicyField` 对象

**触发路径**：当 Genie 模式通过 `ServiceSchema`（而非直接加载 Worksheet CSV/JSON）初始化时：

```
pipeline.load_kb("schema.json")          # 生成 ServiceSchema
pipeline.mode = "genie"                  # 无 worksheet_path 参数
→ _service_schema_to_genie_schema()      # 将 ServiceSchema 转为 GenieSchema
→ GenieIntent.policy_fields = [dict, …] # ← 原始 dict，非 PolicyField 对象！
→ PolicyExecutor.__init__()
→ self._policy_fields = intent.policy_fields  # 拿到 List[dict]
→ pf.required / pf.name                 # ← AttributeError 在此处爆发
```

**不触发的路径**（安全路径）：
```python
# 直接通过 worksheet_path 加载 → WorksheetLoader 正确构造 PolicyField 对象
ContextPipeline(mode="genie", worksheet_path="xxx.csv")
```

**修复方案**（`pipeline.py` 的 `_service_schema_to_genie_schema`）：
```python
from contextmind.schema_builder.genie_worksheets.models import PolicyField

policy_fields=[
    pf if isinstance(pf, PolicyField) else PolicyField.from_dict(pf)
    for pf in i.policy_fields
],
```

### 3.3 次要设计备注

**① `SemanticParser` 是单轮提取，不是 Genie 原版的 ReAct 多轮循环**

Genie 原版 `SUQLReActParser` 采用 ReAct（Reason→Act→Observe→Reason...）多轮循环。
当前实现是单次 LLM 调用，对简单场景无影响，已在文档注释中明确说明为「有意降级」。

**② `next_required_field()` 在 `is_complete()=True` 后仍可能返回可选字段**

行为正确（可选的 `ask_by_system=True` 字段理应继续询问），
但调用方需注意：`is_complete=True` 并不代表 `next_required_field()` 一定返回 `None`，
需在两个条件均满足后才视为完全结束。

---

## 四、总结

| 问题 | 结论 |
|------|------|
| Genie schema 相比 FnCTOD/PyTOD 有何优势 | 通过 Worksheet 将**对话策略显式声明化**（confirm/depends_on/ask_by_system），PolicyExecutor 确定性执行，消除 LLM 控制流幻觉，业务人员可维护 |
| 是否必须实现 SUQL + PostgreSQL | **不需要**。SUQL 仅在知识密集型场景（复杂多条件查询）时才有价值；纯槽位收集场景 LLM JSON 提取已足够 |
| Genie 实现是否完整正确 | **主体完整正确**，存在 1 处有条件触发的 Bug：通过 `ServiceSchema` 路径（非 Worksheet 文件路径）初始化时，`policy_fields` 中的 raw dict 未被转换为 `PolicyField` 对象，会导致 `AttributeError`。始终使用 `worksheet_path=` 参数则不受影响 |
