# 安逸花外呼场景 × PyTOD 完整运行流程

> 文档版本：2026-03-20  
> 对应代码路径：`contextmind/modes/pytod/`  
> 入口脚本：`examples/pytod_trace_demo.py`

---

## 一、总体架构

```
examples/pytod_trace_demo.py
  └─ run_trace()
       ├─ ExecutionEngine                    # 注册安逸花外呼 API
       ├─ AdkLLMClient                       # LLM 后端（litellm → 任意 OpenAI 兼容模型）
       └─ AdkPyTODTracker.process_turn()     # 每轮执行 AP → EE → DM
            ├─ Step 1  Action Parser (AP)
            ├─ Step 2  Execution Engine (EE)
            └─ Step 3  Dialogue Manager (DM)
```

---

## 二、初始化流程

### 2.1 加载数据

`_load_session()` 从 `resources/data/chat_test_100.json` 中读取一条会话，包含：
- `session_id`：会话 ID
- `对话历史`：`["用户：…", "坐席：…", …]` 列表
- `用户信息`：结构化用户画像字符串（姓名、手机尾号、额度、账单日等）
- `坐席回复`：人工坐席的参考回复

### 2.2 构建场景上下文

```python
scenario_context = (
    "这是一个外呼小额借款推介场景（安逸花外呼促活）……"
    "\n\n## 本次通话用户信息\n{user_info}"
)
```

`用户信息` 被注入 `scenario_context`，使 AP 能直接读到用户账户数据（额度、利率等），
从而在数据已知时优先用 `say()` 传达，而不是重复调用查询 API。

### 2.3 注册 API

```python
engine = ExecutionEngine()
_register_anyihua_outbound_apis(engine)   # 来自 registry.py
```

注册的 API 函数：

| 函数名 | 用途 |
|--------|------|
| `verify_customer(name, phone_suffix)` | 核实客户身份 |
| `query_account(customer_name)` | 查询账户信息（可用额度、利率等） |
| `query_loan_records(disputed_date)` | 查询借款记录 |
| `calculate_repayment(amount, months)` | 计算每月还款额 |
| `handle_complaint(complaint_type, description)` | 受理投诉，生成工单 |
| `end_call(outcome)` | 结束通话，记录结果 |
| `get_agent_history()` | 获取已用话术列表（防重复） |
| `query_unresolved_issues()` | 查询未解决诉求（用于判断能否告别） |

### 2.4 创建追踪器

```python
agent = AdkPyTODTracker(
    llm_client=llm_client,
    engine=engine,
    scenario_context=scenario_context,
)
```

`AdkPyTODTracker.__init__()` 内部：
- 创建 `PyTODPromptBuilder`（注入实际函数签名 `engine.to_prompt_text()`）
- 初始化 `_history`（对话历史），`current_state`（累积状态），`step_timings`

---

## 三、逐轮处理流程（`process_turn()`）

每个用户话语触发一次完整的 **AP → EE → DM** 三步流水线：

```
用户话语 (user_utterance)
     │
     ▼
┌─────────────────────────────────────────────┐
│  Step 1  Action Parser (AP)                 │
│                                             │
│  输入：对话历史 + 用户话语 + API签名         │
│         + 场景背景 + 已计算变量（跨轮上下文）│
│  调用：llm_client.chat_async(ap_messages)   │
│  输出：PyTOD 程序文本                        │
│                                             │
│  示例输出：                                  │
│    x1 verify_customer(name='张女士',         │
│                 phone_suffix='八零二')       │
│    x2 say(x1)                               │
└──────────────────┬──────────────────────────┘
                   │ program_text
                   ▼
┌─────────────────────────────────────────────┐
│  Step 2  Execution Engine (EE)              │
│                                             │
│  输入：program_text                          │
│  解析：ExecutionEngine.execute_program()    │
│  执行：调用已注册 API 函数                   │
│  输出：ProgramExecutionResult               │
│    .variable_values  变量名→返回值           │
│    .say_output       say() 指定的输出        │
│    .hint_messages    Hint 提示列表           │
│    .errors           执行错误列表            │
└──────────────────┬──────────────────────────┘
                   │ execution_result
                   ▼
┌─────────────────────────────────────────────┐
│  Step 3  Dialogue Manager (DM)              │
│                                             │
│  输入：对话历史 + 用户话语 + 程序 + 执行结果 │
│  调用：llm_client.chat_async(dm_messages)   │
│  规则：say() 输出内容必须优先体现在回复中    │
│  输出：自然语言回复（坐席话术）              │
└──────────────────┬──────────────────────────┘
                   │ response
                   ▼
          更新对话历史 _history
          更新累积状态 current_state
```

---

## 四、PyTOD 程序语法

AP 输出的程序遵循以下语法（执行引擎 `execution_engine.py` 支持）：

| 语句形式 | 含义 |
|----------|------|
| `x1 func(param='v')` | 调用注册函数，结果绑定到变量 x1 |
| `x1.slot = 'v'; x1.b = 'v2'` | 槽位赋值（支持分号多槽位） |
| `x2 Hint('request value: slot')` | 提示 DM 需向用户询问的信息 |
| `x3 say(x1, x2)` | 组合变量生成 DM 输出 |
| `x3 say(x1.field)` | 引用变量的某个字段 |
| `x3 say('字面量')` | 直接输出字符串 |
| `x2 confirm(x1)` | 请用户确认 x1 的参数（事务型 API） |
| `x3 perform(x1)` | 实际执行 x1 的 API（事务型 API） |
| `conversation_pause()` | 暂停，等待用户操作 |
| `NONE()` | 本轮无需任何 API 调用 |

---

## 五、Prompt 结构

### AP Prompt

```
[system]
你是一个任务型对话的动作解析器（Action Parser）。
{程序语法规则}

## 业务背景
{scenario_context}  ← 含本次通话用户信息

## 可调用 API 函数（程序中的函数名必须与此处完全一致）
{engine.to_prompt_text()}  ← 实际注册的函数签名

## 业务场景说明
{schema 意图描述}

注意：Hint 内容和 say() 字符串字面量请使用中文。

[user]
## 对话历史
{history}

## 已计算变量（本对话中已通过 API 获取的数据）  ← 官方 PyTOD 对齐
{prior_dataflow_context}

## 当前用户话语
{user_utterance}

请输出 PyTOD 程序：
```

### DM Prompt

```
[system]
你是一个任务型对话的对话管理器（Dialogue Manager）。
{DM 回复规则}
回复语言：中文

## 业务背景
{scenario_context}

[user]
## 对话历史
{history}

## 当前用户话语
{user_utterance}

## AP 生成程序
{program}

## 程序执行结果
{execution_result}  ← say() 输出置于首位

请生成坐席回复：
```

---

## 六、安逸花外呼场景的典型对话流程

```
Turn 1  用户打招呼
  AP → x1 verify_customer(name='张女士', phone_suffix='八零二')
  EE → 身份核实成功
  DM → 您好，张女士，…已核实身份…

Turn 2  用户确认
  AP → x2 say('您当前授信额度为6600元，…')      ← 直接用场景上下文中已知数据
  DM → 您当前授信额度为6600元，…

Turn N  用户询问借款记录
  AP → x3 query_loan_records()
  EE → 返回借款记录
  DM → 根据记录回答

Turn Last  结束通话
  AP → x4 query_unresolved_issues()
       x5 end_call(outcome='…')
       x6 say(x5.farewell_message)
  DM → 感谢您接听，再见！
```

---

## 七、与官方 PyTOD 实现的差异分析

### 7.1 官方实现要点（apple/ml-pytod）

官方 PyTOD 的 AP 输入包含：
1. 对话历史（文本）
2. Schema（意图 + 槽位描述）
3. **全对话的已计算变量绑定（dataflow context）**

关键特征：**变量编号在整个对话中全局递增**。如官方示例：

```
# Turn 1
x1 restaurants_2_reserve_restaurant(time='half past 11 in the morning', number_of_seats=2)
x2 Hint('request value: restaurant_name')
x4 say(x2, x3)

# Turn 2（x1 来自 Turn 1，AP 可继续引用）
x5 x1.location = 'San Jose'; x1.restaurant_name = 'Sino'

# Turn 3（AP 仍能引用 x1 的字段）
x14 say(x1.phone_number, x13)

# Turn 4（AP 直接读取已有字段，无需重新查询）
x15 say(x1.has_vegetarian_options, x1.address)
```

### 7.2 差异一（**最关键**）：AP 无法访问跨轮已计算变量 ← 已修复

| | 官方 PyTOD | 修复前 | 修复后 |
|-|-----------|--------|--------|
| AP 能否引用上轮变量 | ✅ x1.field 跨轮可用 | ❌ 每轮重新生成 x1 | ✅ AP prompt 含已计算变量 |
| 变量编号 | 全局累积（x1→xN） | 每轮从 x1 重置 | 全局累积（_global_var_counter）|
| 重复查询问题 | 不会重复查询已知数据 | 会反复调用 query_account | AP 可见先前结果，避免重复 |

**日志中 AP 问题的根因**：Turn 4、5 再次调用 `query_account()` 并得到 mock 值
（available_credit=18000），与 scenario_context 里用户的实际数据（6600元）矛盾，
导致 DM 输出错误数字。修复后 AP 能看到 Turn 1 已完成身份核实、Turn 4 已查到账户数据，
从而跳过重复查询。

### 7.3 差异二：无 Few-Shot 示例

| | 官方 PyTOD | 当前实现 |
|-|-----------|---------|
| AP few-shot | ✅ 注入对话-程序范例 | ❌ 零样本 |

官方论文通过 few-shot 示例大幅提升 AP 准确率。当前实现为零样本，适合原型验证。
`PyTODPromptBuilder` 预留了 `FewShotExample` 扩展点，生产环境可按安逸花外呼场景
定制 few-shot 样本后注入 AP prompt。

### 7.4 差异三：无 ActionValidator 重试

| | 官方 PyTOD | 当前实现 |
|-|-----------|---------|
| AP 输出校验 | ✅ ActionValidator 校验 + 重试 | ❌ 无校验，直接执行 |

当 AP 生成不合法语句（函数未注册、语法错误）时，官方会将错误反馈给 AP 并重试。
当前 EE 会记录错误并继续，由 DM 降级处理。可在后续版本中按需补充校验重试逻辑。

---

## 八、数据流简图（修复后）

```
会话初始化
  scene_context ←── 用户信息
  engine        ←── 注册 8 个 API
  tracker       ←── global_var_counter = 0

每轮 process_turn(user_utterance)
  ┌────────────────────────────────────────────┐
  │ AP                                         │
  │  输入：history + user_utt                  │
  │         + prior_dataflow（已计算变量）      │  ← 关键修复
  │  输出：program_text（全局变量编号连续）      │
  └──────────────┬─────────────────────────────┘
                 │
  ┌──────────────▼─────────────────────────────┐
  │ EE                                         │
  │  解析 program_text                         │
  │  执行注册 API                               │
  │  输出：variable_values, say_output, errors │
  └──────────────┬─────────────────────────────┘
                 │ execution_result 合并进 current_state
  ┌──────────────▼─────────────────────────────┐
  │ DM                                         │
  │  输入：history + user_utt + program        │
  │         + execution_result                  │
  │  规则：say() 优先                           │
  │  输出：response（坐席话术）                  │
  └──────────────┬─────────────────────────────┘
                 │
  更新 _history, current_state
```
