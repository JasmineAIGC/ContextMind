# PyTOD engine.py API 详解：定义、执行、作用

> **文档目的**：回答以下三个问题：
> 1. `engine.py` 里的 API 是**如何定义**的？
> 2. API 是**如何运行**的？
> 3. API 是**如何起到作用**的？
>
> 可配合 `examples/anyihua_engine_api_demo.py` 直接运行验证（无需 LLM）。

---

## 设计决策：为什么 API 应对应 5 个标签类别

PyTOD 执行引擎的 API 表示"系统可执行的操作"。当任务目标是**标签预测（QC 质检分类）**时：

- 旧设计（CRM 查询）：`query_account` / `check_repetition` / `check_farewell_preconditions` 等
  → API 处于"数据层"，标签预测逻辑散落在 `predict_label_pytod()` 的手动组合代码中
  → 引擎 API 目的 ≠ 任务目标

- **新设计（标签检测）**：`predict_data_error` / `predict_repetition` / `predict_improper_farewell` / `predict_off_topic` / `predict_no_issue`
  → 每个 API = 一个标签检测器，引擎直接服务于分类任务
  → 引擎 API 目的 ≡ 任务目标 ✓

---

## 1. API 是如何定义的？

### 1.1 核心机制：`@engine.register` + 闭包

`engine.py` 中的 API 定义遵循一个统一模式：在 `build_anyihua_engine(session)` 函数内，用 `@engine.register` 装饰器将 Python 函数注册到 `ExecutionEngine` 实例上。

```python
# contextmind/scenarios/anyihua/engine.py（精简版）

def build_anyihua_engine(session: Dict[str, Any]) -> ExecutionEngine:
    engine  = ExecutionEngine()            # ① 创建空引擎
    info    = parse_user_info(session["用户信息"])  # 解析 CRM 数据
    history = session.get("对话历史", [])   # 对话历史列表
    reply   = session.get("坐席回复", "")   # 待检测回复

    @engine.register                       # ② 装饰器注册
    def predict_data_error(customer_name=None):
        # ③ 闭包：捕获 info / history / reply
        # 比较 reply 中的金额与 info["available_credit"] 的偏差
        ...
        return {"label": "数据错误", "detected": True, "confidence": 0.87, ...}

    @engine.register
    def predict_repetition(utterance=None):
        # ③ 闭包：捕获 history / reply
        # 精确/模糊匹配 reply 与历史坐席发言
        ...

    @engine.register
    def predict_improper_farewell(customer_name=None): ...

    @engine.register
    def predict_off_topic(customer_name=None): ...

    @engine.register
    def predict_no_issue(customer_name=None):
        return {"label": "无标签命中", "detected": True, "confidence": 0.75, ...}

    return engine
```

**三步总结**：

| 步骤 | 内容 |
|------|------|
| ① 创建空引擎 | `ExecutionEngine()` 初始化空的 `self.registry = {}` |
| ② 装饰器注册 | `@engine.register` 等价于 `engine.registry["predict_data_error"] = predict_data_error` |
| ③ 闭包捕获数据 | 函数体内引用 `info`、`history`、`reply`（来自外层 `build_anyihua_engine` 的局部变量） |

### 1.2 五个 API 一览

| API 函数 | 捕获变量 | 检测逻辑 | 规则精度 |
|---------|---------|---------|---------|
| `predict_data_error(customer_name)` | `info`, `history`, `reply` | reply 金额与系统额度偏差 > 300 元 | P=87% R=87% |
| `predict_repetition(utterance)` | `history`, `reply` | 精确字符串匹配历史坐席发言 | P=87% R=87% |
| `predict_improper_farewell(customer_name)` | `history`, `reply` | 告别词 + 用户未解决诉求词 | FP 较高，提供 LLM hint |
| `predict_off_topic(customer_name)` | `history`, `reply` | 疑问词 → 无关回复模式 | 召回≈60%，提供 LLM hint |
| `predict_no_issue(customer_name)` | 无 | 默认标签（catch-all） | — |

### 1.3 标准返回结构

每个 API 返回包含以下字段的字典：

```python
{
    "label":      str | None,   # 对应标签名；未检出时为 None
    "detected":   bool,         # 是否检出该类问题
    "confidence": float,        # 规则置信度（0.0 ~ 0.87）
    "evidence":   str,          # 检出依据描述
    # API 专属字段（供 LLM 预分析提示使用）：
    # predict_data_error:        data_error_hints, system_credit, temp_credit
    # predict_repetition:        is_exact_repeat, repeat_count, max_similarity, repetition_hint
    # predict_improper_farewell: can_farewell, unresolved_issues, farewell_hint
}
```

---

## 2. API 是如何运行的？

### 2.1 路径 A：直接调用（纯规则预测）

```python
engine = build_anyihua_engine(session)

# 直接通过 registry 字典调用
data_err = engine.registry["predict_data_error"]()
rep      = engine.registry["predict_repetition"]()
```

**典型输出**：

```python
# predict_data_error() → 检出数据错误时
{
    "label":          "数据错误",
    "detected":       True,
    "confidence":     0.87,
    "evidence":       "回复提及「五万两千五百」(52,500元)，系统额度23,988元，偏差28,512元",
    "system_credit":  23988,
    "data_error_hints": ["坐席最终回复提到「...」⚠️", "历史坐席发言提到「...」⚠️"],
}

# predict_repetition() → 检出重复询问时
{
    "label":          "重复询问",
    "detected":       True,
    "confidence":     0.87,
    "evidence":       "坐席回复与历史发言精确匹配，已重复 3 次",
    "is_exact_repeat": True,
    "repeat_count":   2,
    "max_similarity": 1.0,
    "repetition_hint": "⚠️ 坐席最终回复与历史某条坐席发言完全一致（精确匹配）",
}
```

### 2.2 路径 B：`execute_program()`（完整 PyTOD 流程）

```
动作解析器（LLM）生成程序文本：
  x1 predict_data_error()
  x2 predict_repetition()
  x3 predict_improper_farewell()
  x4 predict_off_topic()
  x5 say(x1)
       ↓
engine.execute_program(program_text)
       ↓
  parse_program()  →  逐行解析（正则 + ast，不 eval）
       ↓
  ProgramStatement → engine.registry[name](**kwargs)
  SayStatement     → 拼接输出变量
       ↓
ProgramExecutionResult（5 个变量值 + say 输出）
       ↓
to_context_text()  →  格式化为对话管理器 prompt
```

### 2.3 两条路径对比

| 维度 | 路径 A（直接调用） | 路径 B（execute_program） |
|------|-----------------|------------------------|
| 调用者 | `predict_label_pytod()` / `detect_session_llm()` | PyTOD 动作解析器（在线生成） |
| LLM 依赖 | 无（纯规则） | 动作解析器 LLM 生成程序文本 |
| 使用场景 | 离线质检 Hybrid 模式 | 在线坐席回复生成 |
| 输出 | 原始 dict | `ProgramExecutionResult` |

---

## 3. API 是如何起到作用的？

### 3.1 在 predict_label_pytod() 中的直接预测作用

```python
def predict_label_pytod(session):
    engine = build_anyihua_engine(session)

    # 直接调用标签 API，结果即为预测标签
    data_err = engine.registry["predict_data_error"]()
    if data_err["detected"]:
        return data_err["label"], data_err["confidence"], data_err["evidence"]

    rep = engine.registry["predict_repetition"]()
    if rep["detected"]:
        return rep["label"], rep["confidence"], rep["evidence"]

    # 规则无法判断的标签 → 交由 LLM
    return None, 0.0, "规则无法判断，需 LLM 语义推理"
```

**实测效果**（100 条安逸花数据集）：

| 标签 | 规则精度 | 规则召回 | API |
|------|---------|---------|-----|
| 数据错误 | 87% | 87% | `predict_data_error()` |
| 重复询问 | 87% | 87% | `predict_repetition()` |
| 不当告别 | — | — | `predict_improper_farewell()`（LLM hint） |
| 答非所问 | — | — | `predict_off_topic()`（LLM hint） |

总覆盖：32/100 会话无需 LLM（81% 精度），节省约 32% LLM 调用。

### 3.2 在 detect_session_llm() 中的 hint 注入作用

```python
async def detect_session_llm(session, llm_client, ...):
    engine   = build_anyihua_engine(session)
    data_err = engine.registry["predict_data_error"]()
    rep      = engine.registry["predict_repetition"]()
    fare     = engine.registry["predict_improper_farewell"]()

    # 直接使用 API 的结构化输出作为 LLM hint
    data_error_hints = data_err["data_error_hints"]   # 金额偏差列表
    repetition_hint  = rep["repetition_hint"]          # 重复匹配描述
    farewell_hint    = fare["farewell_hint"]            # 未解决诉求描述
    credit_yuan      = data_err["system_credit"]       # 系统真实额度（防幻觉）

    # 注入 LLM prompt → 提升 LLM 在数值偏差和重复模式上的感知精度
```

### 3.3 整体数据流总结

```
┌──────────────────────────────────────────────────────────────────┐
│  输入：chat_test_100.json 单条会话                                │
└───────────────────────────┬──────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│  build_anyihua_engine(session)                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  parse_user_info() → info（CRM 数据字典）                   │  │
│  │  session["对话历史"] → history                              │  │
│  │  session["坐席回复"] → reply（待检测文本）                   │  │
│  │                                                            │  │
│  │  @register predict_data_error       — 数据错误检测 API     │  │
│  │  @register predict_repetition       — 重复询问检测 API     │  │
│  │  @register predict_improper_farewell — 不当告别检测 API    │  │
│  │  @register predict_off_topic        — 答非所问检测 API     │  │
│  │  @register predict_no_issue         — 默认标签 API         │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
  ┌─────────────────────┐         ┌─────────────────────────┐
  │  路径 A              │         │  路径 B                  │
  │  直接调用            │         │  execute_program()       │
  │  predict_label_pytod │         │  PyTOD 程序执行          │
  │  → 标签预测（无 LLM）│         │  → hint + 防幻觉         │
  └─────────────────────┘         └─────────────────────────┘
```

---

## 4. 快速验证

```bash
# 零 LLM 调用，直接运行演示
cd /path/to/ContextMind
python examples/anyihua_engine_api_demo.py
```

---

## 5. 相关文件索引

| 文件 | 内容 |
|------|------|
| `contextmind/scenarios/anyihua/engine.py` | 5 个标签 API 的完整实现（本文核心） |
| `contextmind/scenarios/anyihua/utils.py` | 数据解析 + 共享常量（FAREWELL_KEYWORDS 等） |
| `contextmind/modes/pytod/execution_engine.py` | `ExecutionEngine` 源码（register / parse / execute） |
| `contextmind/scenarios/anyihua/detectors.py` | `predict_label_pytod()` + `detect_session_llm()` |
| `contextmind/scenarios/anyihua/quality_checker.py` | `PyTODQualityChecker` — Hybrid 模式质检器 |
| `examples/anyihua_engine_api_demo.py` | 可运行演示（本文示例均来源于此） |
