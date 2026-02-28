# PyTOD engine.py API 详解：定义、执行、作用

> **文档目的**：回答以下三个问题：
> 1. `engine.py` 里的 API 是**如何定义**的？
> 2. API 是**如何运行**的？
> 3. API 是**如何起到作用**的？
>
> 可配合 `examples/anyihua_engine_api_demo.py` 直接运行验证（无需 LLM）。

---

## 1. API 是如何定义的？

### 1.1 核心机制：`@engine.register` + 闭包

`engine.py` 中的 API 定义遵循一个统一模式：在 `build_anyihua_engine(session)` 函数内，用 `@engine.register` 装饰器将 Python 函数注册到 `ExecutionEngine` 实例上。

```python
# contextmind/scenarios/anyihua/engine.py（精简版）

def build_anyihua_engine(session: Dict[str, Any]) -> ExecutionEngine:
    engine = ExecutionEngine()            # ① 创建空引擎
    info    = parse_user_info(session["用户信息"])  # 解析 CRM 数据
    history = session.get("对话历史", [])            # 对话历史列表

    @engine.register                      # ② 装饰器注册
    def query_account(customer_name: str = None) -> dict:
        # ③ 闭包：捕获 info 变量（当前会话的 CRM 数据）
        return {
            "customer_name":    info["customer_name"],
            "available_credit": info["available_credit"],
            "annual_rate_pct":  info["annual_rate_pct"],
            ...
        }

    @engine.register
    def check_repetition(utterance: str = None, threshold: float = 0.85) -> dict:
        # ③ 闭包：捕获 history 变量（对话历史）
        agent_turns = [t.removeprefix("坐席：") for t in history if t.startswith("坐席：")]
        is_exact = (utterance or "").strip() in agent_turns
        ...

    # ... 其余 4 个 API 同样方式注册
    return engine
```

**三步总结**：

| 步骤 | 内容 |
|------|------|
| ① 创建空引擎 | `ExecutionEngine()` 初始化空的 `self.registry = {}` |
| ② 装饰器注册 | `@engine.register` 等价于 `engine.registry["query_account"] = query_account` |
| ③ 闭包捕获数据 | 函数体内引用 `info` 和 `history`（来自外层 `build_anyihua_engine` 的局部变量） |

### 1.2 装饰器的实现原理

```python
# contextmind/modes/pytod/execution_engine.py

class ExecutionEngine:
    def __init__(self) -> None:
        self.registry: Dict[str, Callable] = {}   # 函数注册表

    def register(self, func: Callable) -> Callable:
        self.registry[func.__name__] = func        # 以函数名为 key 存入注册表
        return func                                 # 返回原函数（装饰器语义）
```

因此 `@engine.register` 本质上是 `query_account = engine.register(query_account)`，
执行后 `engine.registry["query_account"]` 就指向那个闭包函数。

### 1.3 为什么用闭包而不是参数传递？

- **简洁**：每次调用 API 时不需要重复传入会话数据
- **隔离**：每次调用 `build_anyihua_engine(session)` 都生成一个独立的引擎实例，不同会话的数据完全隔离
- **一致**：API 接口签名与 PyTOD 论文保持一致（`query_account(customer_name)` 而非 `query_account(session, customer_name)`）

### 1.4 六个 API 一览

| API 函数 | 捕获变量 | 用途 |
|---------|---------|------|
| `query_account(customer_name)` | `info` | 返回系统真实额度、利率、绑定银行 |
| `query_loan_records(customer_name, target_date)` | `info` | 核实借款记录、争议日期 |
| `calculate_monthly_payment(amount, term_months, annual_rate_pct)` | `info` | 等额还款公式计算 |
| `check_farewell_preconditions(customer_name)` | `history` | 扫描用户历史诉求词 |
| `check_repetition(utterance, threshold)` | `history` | 精确/模糊匹配历史重复 |
| `escalate_to_human(customer_name, issue, priority)` | `info`, `session_id` | 生成转人工工单 |

---

## 2. API 是如何运行的？

已注册的 API 有两条调用路径，对应两种使用场景。

### 2.1 路径 A：直接调用（纯规则预测）

```python
engine = build_anyihua_engine(session)

# 直接通过 registry 字典调用
acct = engine.registry["query_account"]()
rep  = engine.registry["check_repetition"](utterance=reply.strip())
fare = engine.registry["check_farewell_preconditions"]()
```

**典型输出**：

```python
# query_account() 返回值
{
    "customer_name":    "潘女士",
    "available_credit": 25440,    # ← 这个值是防止数据错误的关键基准
    "annual_rate_pct":  24,
    "bound_bank":       "工商银行",
    ...
}

# check_repetition(utterance="您点立即借款...") 返回值
{
    "is_exact_repeat": True,      # ← True 时直接判断「重复询问」，无需 LLM
    "repeat_count":    2,
    "max_similarity":  1.0,
    "recommendation":  "已重复 3 次，建议换方式解释或转人工",
}
```

这条路径被 `predict_label_pytod(session)` 使用，**零 LLM 调用**，对 100 条数据集有 32% 的会话（精度 81%）可直接输出预测标签。

### 2.2 路径 B：`execute_program()`（完整 PyTOD 流程）

```
动作解析器（LLM）生成程序文本
       ↓
engine.execute_program(program_text)
       ↓
  parse_program()  →  逐行解析语句（正则 + Python ast 模块，不 eval）
       ↓
  逐条执行：
    ProgramStatement  → engine.registry[func_name](**kwargs)
    HintStatement     → 收集"请用户补充"的信息
    SayStatement      → 拼接输出变量
       ↓
ProgramExecutionResult（变量值 + say 输出 + 错误列表）
       ↓
to_context_text()  →  格式化为对话管理器 prompt
```

**示例**：

```python
program = """
x1 query_account(customer_name='潘女士')
x2 check_repetition(utterance='您好，我是安逸花客服')
x3 say(x1)
"""

result = engine.execute_program(program)
# result.variable_values["x1"] → {"available_credit": 25440, ...}
# result.variable_values["x2"] → {"is_exact_repeat": False, ...}
# result.say_output             → x1 的值（用于对话管理器输出）

# 注入对话管理器 prompt 的格式化文本
print(result.to_context_text())
```

```
[程序执行结果]
API 调用结果:
  x1 = {"customer_name": "潘女士", "available_credit": 25440, ...}
  x2 = {"is_exact_repeat": false, "repeat_count": 0, ...}
say 输出: {"customer_name": "潘女士", "available_credit": 25440, ...}
```

**安全保证**：`execute_program` 用 Python `ast` 模块解析（不 `eval`），只允许常量参数（str/int/float/bool/None），只能调用已显式注册的函数，无法执行任意代码。

### 2.3 两条路径对比

| 维度 | 路径 A（直接调用） | 路径 B（execute_program） |
|------|-----------------|------------------------|
| 调用者 | `predict_label_pytod()` / `detect_session_llm()` | `PyTODTracker`（在线生成） |
| LLM 依赖 | 无（纯规则） | 动作解析器 LLM 生成程序文本 |
| 使用场景 | 离线质检 Hybrid 模式 | 在线坐席回复生成 |
| 输出 | 原始 dict | `ProgramExecutionResult` |

---

## 3. API 是如何起到作用的？

### 3.1 在质量标签预测中的直接作用（路径 A）

```
session 数据
     ↓
build_anyihua_engine()     ← 注册 6 个 API（闭包绑定 CRM 数据）
     ↓
predict_label_pytod()
  ├── query_account()       → 获取系统真实额度
  │     compare with        → 坐席回复中提到的金额
  │     if 偏差 > 300 元    → 预测「数据错误」（P=87%, R=87%）
  │
  └── check_repetition()   → is_exact_repeat == True
        if True             → 预测「重复询问」（P=87%, R=87%）

  → 其他标签（不当告别/答非所问/无标签命中）
        返回 None → 交由 detect_session_llm() 处理
```

**实测效果**（100 条安逸花数据集）：

| 标签 | 规则精度 | 规则召回 | 依赖 API |
|------|---------|---------|---------|
| 数据错误 | 87% | 87% | `query_account()` |
| 重复询问 | 87% | 87% | `check_repetition()` |
| 不当告别 | — | — | `check_farewell_preconditions()`（作为 LLM hint） |
| 答非所问 | — | — | `query_account()`（作为 LLM 背景信息） |

### 3.2 在在线回复生成中的防幻觉作用（路径 B）

```
用户: "我能借多少钱？"

无 PyTOD:                        有 PyTOD:
  LLM 直接生成回复                 动作解析器 → execute_program
  → 可能回答错误金额（幻觉）           x1 query_account()
                                       ↓ 返回 available_credit=25440
                                   对话管理器 LLM 基于真实数据生成:
                                   → "您当前可提现额度为 25,440 元"（正确）
```

`query_account()` 提供的是系统数据库中的**不可伪造真实值**，彻底消除 AI 坐席在额度数字上的幻觉风险。

### 3.3 在 LLM 质检（方式 A）中的 hint 作用

即使不做纯规则预测，API 调用结果也会作为结构化提示注入 LLM prompt：

```python
# detect_session_llm() 中（detectors.py）
engine = build_anyihua_engine(session)
acct   = engine.registry["query_account"]()
rep    = engine.registry["check_repetition"](utterance=reply)
fare   = engine.registry["check_farewell_preconditions"]()

# 构造 hint 字符串注入 prompt：
hints = f"""
系统额度: {acct['available_credit']} 元
重复检测: {rep['is_exact_repeat']}（相似度 {rep['max_similarity']}）
告别前提: {'可以' if fare['can_farewell'] else '不可以'}，{fare['recommendation']}
"""
```

这样 LLM 无需从对话文本中推断这些数值信息，减少错误判断的概率。

### 3.4 整体数据流总结

```
┌──────────────────────────────────────────────────────────────────┐
│  输入：chat_test_100.json 单条会话                                │
└───────────────────────────┬──────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────────┐
│  build_anyihua_engine(session)                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  parse_user_info() → info（CRM 数据字典）                   │  │
│  │  session["对话历史"] → history（历史轮次列表）               │  │
│  │                                                            │  │
│  │  @register query_account      — 闭包捕获 info              │  │
│  │  @register query_loan_records — 闭包捕获 info              │  │
│  │  @register calculate_monthly  — 闭包捕获 info              │  │
│  │  @register check_farewell     — 闭包捕获 history           │  │
│  │  @register check_repetition   — 闭包捕获 history           │  │
│  │  @register escalate_to_human  — 闭包捕获 info + session_id │  │
│  └──────────────────────────┬─────────────────────────────────┘  │
└─────────────────────────────┼────────────────────────────────────┘
                              ↓
              ┌───────────────┴───────────────┐
              ↓                               ↓
  ┌─────────────────────┐         ┌─────────────────────────┐
  │  路径 A              │         │  路径 B                  │
  │  直接调用 registry   │         │  execute_program()       │
  │                     │         │                         │
  │  predict_label_pytod│         │  PyTODTracker（在线生成）│
  │  → 标签预测          │         │  → 防幻觉回复生成         │
  └─────────────────────┘         └─────────────────────────┘
```

---

## 4. 快速验证

```bash
# 零 LLM 调用，直接运行演示
cd /path/to/ContextMind
python examples/anyihua_engine_api_demo.py
```

演示脚本输出包括：
- 所有 6 个 API 的真实调用结果
- `execute_program()` 多行程序的完整执行过程
- 数据错误、重复询问、不当告别三类标签的规则检测实例

---

## 5. 相关文件索引

| 文件 | 内容 |
|------|------|
| `contextmind/scenarios/anyihua/engine.py` | 6 个 API 的完整实现（本文核心） |
| `contextmind/modes/pytod/execution_engine.py` | `ExecutionEngine` 源码（register / parse / execute） |
| `contextmind/scenarios/anyihua/detectors.py` | `predict_label_pytod()` — 调用路径 A 的规则预测器 |
| `contextmind/scenarios/anyihua/quality_checker.py` | `PyTODQualityChecker` — Hybrid 模式质检器 |
| `examples/anyihua_engine_api_demo.py` | 可运行演示（本文示例均来源于此） |
| `examples/anyihua_online_demo.py` | 含 LLM 的在线生成完整流程 |
