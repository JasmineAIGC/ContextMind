# PyTOD 安逸花外呼场景：双任务引擎架构

> **文档目的**：说明安逸花外呼场景的两个独立任务如何各自使用 PyTOD ExecutionEngine，
> 以及两者在设计上的区别和隔离原因。
>
> 可配合 `examples/anyihua_engine_api_demo.py` 直接运行验证（无需 LLM）。

---

## 1. 整体架构

安逸花外呼场景包含**两个完全隔离的任务**：

```
contextmind/scenarios/anyihua/
    utils.py                   ← 共享工具（cn2int, parse_user_info, 检测常量）
    qc/                        ← 任务一：离线质检（Label Prediction）
        engine.py              ← build_qc_engine()：5 个标签检测 API
        predictor.py           ← predict_label_pytod / detect_session_llm / PyTODQualityChecker
    generation/                ← 任务二：在线生成（Response Generation）
        engine.py              ← build_generation_engine()：5 个 CRM 查询 API
        schema.py              ← ANYIHUA_SCHEMA：约束动作解析器意图范围

examples/
    anyihua_qc_pipeline.py     ← 任务一入口（批量质检）
    anyihua_online_demo.py     ← 任务二入口（Gradio 坐席回复生成）
    anyihua_engine_api_demo.py ← 双引擎演示（零 LLM）
```

---

## 2. 为什么两个任务需要不同的引擎？

| 维度 | 任务一（QC） | 任务二（Generation） |
|------|------------|---------------------|
| **目标** | 判断坐席回复的质量标签 | 生成更好的坐席回复 |
| **API 类型** | 标签检测器 | CRM 数据查询器 |
| **API 数量** | 5 个（对应 5 个标签类别） | 5 个（对应业务数据需求） |
| **返回值** | `{label, detected, confidence, evidence}` | CRM 结构化数据 |
| **被调用者** | `predict_label_pytod()` / `detect_session_llm()` | `PyTODTracker`（动作解析器 + 对话管理器） |

两个引擎**目的不同、数据不同、不可共用**。

---

## 3. 任务一：QC 引擎（`qc/engine.py`）

### 3.1 注册的 5 个 API

| API | 对应标签 | 规则精度 | 用途 |
|-----|---------|---------|------|
| `predict_data_error()` | 数据错误 | P=87% R=87% | 规则直接预测 + LLM hint |
| `predict_repetition()` | 重复询问 | P=87% R=87% | 规则直接预测 + LLM hint |
| `predict_improper_farewell()` | 不当告别 | FP 较高 | 仅提供 LLM hint |
| `predict_off_topic()` | 答非所问 | 召回≈60% | 仅提供 LLM hint |
| `predict_no_issue()` | 无标签命中 | — | 兜底标签 |

### 3.2 两种调用路径

**路径 A：纯规则预测（`predict_label_pytod`）**
```python
from contextmind.scenarios.anyihua.qc import predict_label_pytod

label, conf, reason = predict_label_pytod(session)
# label="数据错误" → 直接输出，无需 LLM
# label=None → 规则无法判断，交由 detect_session_llm
```

**路径 B：LLM 质检（`detect_session_llm`）**
```python
from contextmind.scenarios.anyihua.qc import detect_session_llm

label, reason = await detect_session_llm(session, llm_client)
# QC 引擎的 API 结果作为结构化 hint 注入 LLM prompt
```

**实测性能（100 条安逸花数据集）**：
- 规则可预测会话：32/100（32%）
- 规则预测精度：26/32（81%）
- 节省 LLM 调用：约 32%

---

## 4. 任务二：Generation 引擎（`generation/engine.py`）

### 4.1 注册的 5 个 CRM 查询 API

| API | 用途 | 对应 Schema 意图 |
|-----|------|----------------|
| `query_account()` | 获取账户额度信息（防数据错误） | `explain_credit_limit`, `explain_displayed_amount` |
| `calculate_repayment(amount, months)` | 计算月还款额 | `calculate_repayment`, `explain_interest_rate` |
| `check_repetition(utterance)` | 检测话术是否重复 | `guide_loan_operation` |
| `check_farewell_preconditions()` | 检查告别前提 | `say_goodbye` |
| `query_loan_records()` | 查询借款记录 | `handle_loan_dispute` |

### 4.2 PyTOD 三步流程

```
动作解析器（LLM）根据 ANYIHUA_SCHEMA 生成程序
    x1 query_account()
    x2 check_farewell_preconditions()
    x3 say(x1)
       ↓
执行引擎（build_generation_engine）调用真实 CRM 数据
    x1 = {available_credit: 25440, temp_credit: 25500, ...}
    x2 = {can_farewell: False, recommendation: "请先解决用户问题"}
       ↓
对话管理器（LLM）基于真实数据生成坐席回复
    "您目前的可提现额度是 25,440 元..."
```

### 4.3 Schema 的作用

`ANYIHUA_SCHEMA`（`generation/schema.py`）约束动作解析器：
- 只能生成 9 种预定义意图（`verify_identity`, `explain_credit_limit` 等）
- 槽位值受枚举约束（`temp_credit_status` 只能是 "有效"/"已过期"/"无临时额度"）
- `explain_credit_limit` 意图强制要求先调用 `query_account`（防数据错误）

---

## 5. 快速验证

```bash
# 零 LLM 调用，直接运行双引擎演示
cd /path/to/ContextMind
python examples/anyihua_engine_api_demo.py

# 任务一入口（需要 LLM 配置）
python examples/anyihua_qc_pipeline.py

# 任务二入口（需要 LLM 配置 + gradio）
python examples/anyihua_online_demo.py
```

---

## 6. 文件索引

| 文件 | 内容 |
|------|------|
| `contextmind/scenarios/anyihua/qc/engine.py` | QC 引擎：5 个标签检测 API |
| `contextmind/scenarios/anyihua/qc/predictor.py` | `predict_label_pytod` + `detect_session_llm` + `PyTODQualityChecker` |
| `contextmind/scenarios/anyihua/generation/engine.py` | Generation 引擎：5 个 CRM 查询 API |
| `contextmind/scenarios/anyihua/generation/schema.py` | `ANYIHUA_SCHEMA`：意图/槽位约束 |
| `contextmind/scenarios/anyihua/utils.py` | 共享工具：数据解析 + 检测常量 |
| `contextmind/modes/pytod/execution_engine.py` | `ExecutionEngine` 框架（不可修改） |
