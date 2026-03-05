# PyTOD 算法使用 SGD 数据的方式分析
## 及 AnYiHua 数据在 PyTOD 上的运行评估

生成时间：2026-03-05  
参考来源：https://github.com/apple/ml-pytod  
          https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

---

## 一、resources/anyihua_sgd 格式检验结果

### 1.1 已发现并修复的问题（4 项）

| 编号 | Bug 描述 | SGD 规范 | 修复方式 |
|---|---|---|---|
| Bug 1 | 每个 turn 含 `turn_id` 字段 | SGD 的 turn 只有 `speaker` / `utterance` / `frames`，无 `turn_id` | 删除 `turn_id` |
| Bug 2 | SYSTEM frame 含 `state` 字段 | 只有 USER frame 含 `state`；SYSTEM frame 无 `state` | 从 SYSTEM frame 中移除 `state` |
| Bug 3 | frame 缺少 `slots` 字段 | 每个 frame 必须有 `slots: []`（字符级标注，无则留空数组） | 在所有 frame 中添加 `slots: []` |
| Bug 4 | 每个 SYSTEM frame 都有 `service_call`/`service_results` | 仅在实际调用 API 时才有此字段 | 改为按意图条件性添加 |

**修复后验证结果（100 条对话，1330 轮次）**：
```
✅ 所有 100 条对话通过 SGD 格式合规检查
SYSTEM turns: 715, 其中 461 个 (64%) 含 service_call（合理）
```

### 1.2 已知的结构性差异（非 bug，需要文档说明）

| 差异 | SGD 标准行为 | AnYiHua 行为 | 影响 |
|---|---|---|---|
| 对话首发言者 | USER 首先发言 | SYSTEM（坐席）首先发言（外呼） | PyTOD 的 `sgd_annotation.py` 假设 USER turn 在偶数位置，可能影响 DST 标注推断 |
| 扩展字段 `metadata` | SGD 无此字段 | 我们添加了 `metadata` 字段存放 CRM 数据 | 标准 PyTOD 解析器会忽略未知字段，不影响兼容性 |
| `dialogue_id` 格式 | 如 `"1_00000"` | 使用原始 session_id 数字串 | 无功能影响，仅格式不同 |

---

## 二、PyTOD 算法如何使用 SGD 数据

### 2.1 PyTOD 的总体架构

PyTOD（Programmable Task-Oriented Dialogue）是 Apple Research 开发的框架，
将 SGD 对话转换为"可执行 Python 程序"的形式来训练/评估 Action Parser 和 Dialogue Manager。

```
SGD 数据
  ↓ [sgd_conversation_builder.py]
  Conversation 对象（结构化中间格式）
  ↓ [create_pytod_dialogues.py]
  PyTOD Transcript（utterance + PyTOD program）
  ↓ [Action Parser (LLM)]
  PyTOD program 预测
  ↓ [ExecutionEngine]
  API 调用结果
  ↓ [Dialogue Manager (LLM)]
  自然语言回复
```

### 2.2 PyTOD 读取 SGD 数据的关键代码路径

#### 2.2.1 `sgd_utils.py` — 基础迭代器

```python
def dialogue_iterator(dialogue, user=True, system=True):
    """按 speaker 过滤 turns"""
    for turn in dialogue["turns"]:
        if drop_speaker and turn.get("speaker", "") == drop_speaker:
            continue
        yield turn
```

**关键点**：
- PyTOD 直接读取 `dialogue["turns"]` 列表
- 通过 `turn["speaker"]` 区分 USER / SYSTEM
- `turn_id` 字段不被读取（我们之前错误添加了它）

#### 2.2.2 `sgd_annotation.py` — DST 标注推断

```python
for idx, turn in enumerate(dialogue_iterator(dialogue, user=True, system=False)):
    user_turn_idx = 2 * idx  # ← 假设 USER turn 在 2*idx 位置
    for frame in turn["frames"]:
        service = frame["service"]
        intent = frame["state"]["active_intent"]  # ← 只读 USER frame 的 state
        ...
        if user_turn_idx > 0:
            sys_turn = dialogue["turns"][user_turn_idx - 1]
            sys_frame = get_frame(sys_turn, service)
            sys_actions = sys_frame["actions"]  # ← 读 SYSTEM frame 的 actions
```

**关键点**：
- `frame["state"]["active_intent"]` 只从 **USER frame** 读取（Bug 2 如果不修复会崩溃）
- `frame["actions"]` 从 USER 和 SYSTEM frame 都会读取
- 假设 `user_turn_idx = 2 * idx`，即 USER turn 在偶数位置（影响点：我们的对话从 SYSTEM 开始）

#### 2.2.3 `sgd_conversation_builder.py` — 构建 Conversation 对象

- 读取 `service_call` 和 `service_results` 构建 API 调用记录
- 读取 `frame["state"]["slot_values"]` 追踪对话状态
- 读取 `frame["actions"]` 识别对话行为

### 2.3 PyTOD 使用 SGD 数据的 3 个阶段

#### 阶段 1：生成 PyTOD Transcript（`create_pytod_dialogues.py`）

从 SGD 格式读取以下字段：

| SGD 字段 | PyTOD 用途 |
|---|---|
| `turn["utterance"]` | 对话文本 |
| `turn["speaker"]` | 区分 USER / SYSTEM |
| `frame["state"]["active_intent"]` | 确定当前意图，生成对应的 PyTOD 程序行 |
| `frame["state"]["slot_values"]` | DST groundtruth，生成槽位赋值语句 |
| `frame["state"]["requested_slots"]` | 生成 `Hint('request value: slot')` |
| `frame["actions"]` | 生成 CONFIRM/OFFER 提示 |
| `frame["service_call"]` | 生成 `x = service.intent(args)` |
| `frame["service_results"]` | 生成 API 返回结果 |

**示例**（官方 ml-pytod README 中的 PyTOD transcript）：
```
user: I want to make a restaurant reservation for 2 people at half past 11 in the morning.
x1 restaurants_2_reserve_restaurant(time = 'half past 11 in the morning', number_of_seats = 2)
x2 Hint('request value: restaurant_name')
...
agent: What city do you want to dine in? Do you have a preferred restaurant?
```

#### 阶段 2：Action Parser 微调（`create_pytod_text2text_examples.py`）

生成 text2text 训练样本：
- 输入：对话历史 + 当前 USER 话语
- 输出：PyTOD program（如 `x1 = verify_customer(name='高先生', phone='六七八')`）

#### 阶段 3：实时推理（`inference/`）

- Action Parser（LLM）预测 PyTOD program
- ExecutionEngine 执行 program，调用 CRM API
- Dialogue Manager（LLM）基于 API 结果生成回复

---

## 三、AnYiHua 数据在 PyTOD 上的运行评估

### 3.1 可以正常运行的部分

| PyTOD 组件 | AnYiHua 数据适配状态 | 说明 |
|---|---|---|
| `dialogue_iterator` | ✅ 兼容 | 正确读取 `turns[].speaker` 和 `turns[].utterance` |
| `frame["actions"]` 读取 | ✅ 兼容 | USER/SYSTEM 的 actions 均已生成 |
| `frame["state"]` 读取（USER） | ✅ 兼容 | USER frame 有 state.active_intent / slot_values |
| `service_call` / `service_results` | ✅ 兼容 | 按意图条件性生成，非空时格式正确 |
| `frame["slots"]` | ✅ 兼容 | 已添加空数组 `[]`（无字符级标注） |
| Schema 格式 | ✅ 兼容 | 与 SGD schema.json 规范完全一致 |

### 3.2 需要关注的限制

| 限制 | 影响程度 | 说明 |
|---|---|---|
| **对话从 SYSTEM 开始** | ⚠️ 中等 | `sgd_annotation.py` 假设 `user_turn_idx = 2 * idx`（USER 在偶数位），我们的数据 USER 在奇数位（1, 3, 5, ...）。这影响 DST 标注质量，但不影响基础推理 |
| **active_intent 为规则推断** | ⚠️ 中等 | 无 groundtruth DST 标注，意图由关键词规则推断，精度有限（~70-80% 估计）。影响 Action Parser 训练质量 |
| **slot_values 来自 CRM** | ⚠️ 较低 | 槽值从 `用户信息` 提取，非从对话中动态追踪。可能在某些轮次过于完整（提前知道了对话后续的槽值） |
| **`slots: []` 字符级标注缺失** | ⚠️ 较低 | 字符级标注仅用于 SGD-X robustness 评估，PyTOD 的 Action Parser 训练不依赖此字段 |
| **仅单服务（AnYiHua_1）** | 🔵 无影响 | PyTOD 支持多服务，单服务是合法子集 |

### 3.3 对 ContextMind 的 PyTOD 模式的影响

ContextMind 的 PyTOD 实现（`contextmind/modes/pytod/`）与 ml-pytod 的完整 pipeline 不同：

| 层次 | ml-pytod | ContextMind PyTOD |
|---|---|---|
| Action Parser | 微调的 LLM（读取 PyTOD transcript 训练） | `PyTODTracker`（直接调用 LLM，无需预训练） |
| ExecutionEngine | 官方 SGD API 模拟器 | 自定义 CRM API（`generation/engine.py`） |
| Dialogue Manager | 微调的 LLM | 直接调用 LLM（基于 API 结果生成回复） |
| SGD 数据用途 | 训练 + 评估 | 仅用于评估（DST 准确率对比） |

**结论**：  
对于 ContextMind 自身的 PyTOD 运行时（实时对话生成），  
**不需要 SGD 格式数据**——ContextMind 已有自己的运行时。

SGD 格式数据（`resources/anyihua_sgd`）主要用于：
1. **DST 评估**：对比 `PyTODTracker` 预测的 `slot_values` 与 groundtruth
2. **与标准基准对比**：将安逸花数据集纳入 SGD 基准评估体系

### 3.4 如果需要在 ml-pytod 原生框架上运行

需要额外完成：

1. **SGD API 模拟器**：按 ml-pytod 的 `SearchCommand` / `ConfirmedCommand` 框架
   实现安逸花的 7 个 CRM API（参考 `generation/engine.py` 的已有实现）

2. **PyTOD Transcript 生成**：运行 `create_pytod_dialogues.py` 脚本，
   需要提供 `resources/anyihua_sgd` 作为输入 SGD 数据

3. **处理对话首发言者问题**：可在每条对话开头添加一个空 USER turn
   （`utterance = ""`），使 USER turn 恢复到偶数位置：
   ```python
   turns = [{"speaker": "USER", "utterance": "", "frames": [...]}] + turns
   ```

---

## 四、修复后的文件结构

```
resources/anyihua_sgd/
    schema.json            # 15 槽位，10 意图，SGD 规范格式
    dialogues_001.json     # 100 条对话，1330 轮次，通过格式合规检查
    conversion_summary.json  # 转换统计
```

**格式合规性**（对比 dstc8-schema-guided-dialogue 原始数据）：

| SGD 字段规范 | 合规状态 |
|---|---|
| turn 无 turn_id | ✅ 已修复 |
| SYSTEM frame 无 state | ✅ 已修复 |
| 所有 frame 有 slots 字段 | ✅ 已修复 |
| service_call 仅在有 API 调用时存在 | ✅ 已修复 |
| schema.json 格式 | ✅ 完全符合 |
| USER frame 有 state | ✅ 正确 |
| frame actions 格式（act/slot/values/canonical_values） | ✅ 正确 |

---

## 五、参考资料

- SGD 数据集原始格式：https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
- ml-pytod 框架：https://github.com/apple/ml-pytod
  - `src/pytod/sgd_utils.py`：对话迭代器，展示 PyTOD 如何遍历 turns
  - `src/pytod/sgd_annotation.py`：DST 标注推断，展示 PyTOD 如何使用 state/actions
  - `src/pytod/sgd_conversation_builder.py`：构建 Conversation 对象
  - `src/pytod/pytod_conversation_builder.py`：构建 PyTOD transcript
- ContextMind PyTOD 实现：`contextmind/modes/pytod/`
- 安逸花 CRM API：`contextmind/scenarios/anyihua/generation/engine.py`
