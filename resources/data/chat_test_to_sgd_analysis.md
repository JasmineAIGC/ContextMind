# chat_test_100.json → SGD 格式转换分析报告

生成时间：2026-03-05  
作者：分析工具自动生成

---

## 一、SGD 数据集格式详解

SGD（Schema-Guided Dialogue）是 Google 发布的多领域任务型对话数据集，
分为两种文件类型：**schema.json**（服务模式定义）和 **dialogues_*.json**（对话数据）。

### 1.1 schema.json 格式

```json
[
  {
    "service_name": "AnYiHua_1",
    "description": "安逸花外呼促活服务",
    "slots": [
      {
        "name": "customer_name",
        "description": "客户姓名",
        "is_categorical": false,
        "possible_values": []
      },
      {
        "name": "available_credit",
        "description": "可提现额度（元）",
        "is_categorical": false,
        "possible_values": []
      }
    ],
    "intents": [
      {
        "name": "verify_identity",
        "description": "开场身份核实",
        "is_transactional": false,
        "required_slots": ["customer_name"],
        "optional_slots": {"phone_suffix": ""},
        "result_slots": ["identity_confirmed"]
      }
    ]
  }
]
```

### 1.2 dialogues_*.json 格式

```json
[
  {
    "dialogue_id": "anyihua_0001",
    "services": ["AnYiHua_1"],
    "turns": [
      {
        "turn_id": "0",
        "speaker": "SYSTEM",
        "utterance": "诶您好，打扰一下，请问您这边是高先生吗？",
        "frames": [
          {
            "service": "AnYiHua_1",
            "state": {
              "active_intent": "NONE",
              "requested_slots": [],
              "slot_values": {}
            },
            "actions": [
              {
                "act": "REQUEST",
                "slot": "customer_name",
                "values": [],
                "canonical_values": []
              }
            ]
          }
        ]
      },
      {
        "turn_id": "1",
        "speaker": "USER",
        "utterance": "喂你说。",
        "frames": [
          {
            "service": "AnYiHua_1",
            "state": {
              "active_intent": "verify_identity",
              "requested_slots": [],
              "slot_values": {}
            },
            "actions": []
          }
        ]
      }
    ]
  }
]
```

### 1.3 SGD 字段完整清单

#### dialogue 级别

| 字段 | 类型 | 描述 | 必填 |
|---|---|---|---|
| `dialogue_id` | string | 对话唯一标识 | ✅ |
| `services` | list[str] | 本对话涉及的服务名称列表 | ✅ |
| `turns` | list[Turn] | 对话轮次列表 | ✅ |

#### turn 级别

| 字段 | 类型 | 描述 | 必填 |
|---|---|---|---|
| `turn_id` | string | 轮次序号（字符串形式） | ✅ |
| `speaker` | "USER" \| "SYSTEM" | 发言者 | ✅ |
| `utterance` | string | 自然语言发言内容 | ✅ |
| `frames` | list[Frame] | 每个服务对应的状态帧 | ✅ |

#### frame 级别（USER turn）

| 字段 | 类型 | 描述 | 必填 |
|---|---|---|---|
| `service` | string | 对应的服务名称 | ✅ |
| `state.active_intent` | string | 用户当前激活的意图（"NONE" 表示无） | ✅ |
| `state.requested_slots` | list[str] | 用户正在询问的槽位 | ✅ |
| `state.slot_values` | dict | 累积对话状态 `{slot_name: [value]}` | ✅ |
| `actions` | list[Action] | 用户行为动作列表 | ✅ |

#### frame 级别（SYSTEM turn）

| 字段 | 类型 | 描述 | 必填 |
|---|---|---|---|
| `service` | string | 对应的服务名称 | ✅ |
| `actions` | list[Action] | 系统行为动作列表 | ✅ |
| `service_call` | dict \| null | 系统调用的 API（方法名 + 参数） | 可选 |
| `service_results` | list[dict] | API 返回结果列表 | 可选 |

#### action 对象

| 字段 | 类型 | 描述 |
|---|---|---|
| `act` | string | 动作类型（INFORM/REQUEST/CONFIRM/OFFER 等） |
| `slot` | string | 涉及的槽位名称 |
| `values` | list[str] | 自然语言值 |
| `canonical_values` | list[str] | 规范化值 |

---

## 二、chat_test_100.json 格式分析

### 2.1 原始格式结构

```json
{
  "session_id": "2025102811215858702023182",
  "用户信息": "现在是上午十一点二十一分#高先生#手机尾号是六七八#...",
  "对话历史": [
    "坐席：诶您好，打扰一下，请问您这边是高先生吗？来电是有事情找一下高先生本人。",
    "用户：喂你说。",
    "坐席：诶高先生您好，我是马上消费安逸花的工作人员...",
    "..."
  ],
  "坐席回复": "那我这边就先不打扰您了，祝您生活愉快...",
  "人工校验": "不当告别"
}
```

### 2.2 字段统计

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | 会话唯一 ID，可映射为 `dialogue_id` |
| `用户信息` | string | `#` 分隔的 CRM 信息，包含用户姓名、额度、利率等 |
| `对话历史` | list[str] | 格式为 `"坐席：..."` / `"用户：..."` 的对话历史 |
| `坐席回复` | string | **当前轮** 的参考坐席回复（待预测目标） |
| `人工校验` | string | QC 质量标签（不当告别/答非所问/重复询问/数据错误/无标签命中） |

**数据规模**：100 条记录，平均 12.3 轮对话历史（min=2, max=52）

**人工校验标签分布**：
- 无标签命中：40 条
- 不当告别：15 条  
- 答非所问：15 条
- 重复询问：15 条
- 数据错误：15 条

---

## 三、格式差异对比与缺失信息分析

### 3.1 可直接映射的字段

| SGD 字段 | chat_test_100.json 来源 | 转换方式 |
|---|---|---|
| `dialogue_id` | `session_id` | 直接使用 |
| `services` | 固定值 | `["AnYiHua_1"]`（单服务场景） |
| `turn.speaker` | `对话历史` 前缀 | `"坐席："` → `"SYSTEM"`, `"用户："` → `"USER"` |
| `turn.utterance` | `对话历史` 内容 | 去除前缀后直接使用 |

### 3.2 **缺失的核心字段（必须补充）**

| SGD 字段 | 缺失原因 | 补充方案 |
|---|---|---|
| **`state.active_intent`** | 原始数据无意图标注 | 用 LLM 从对话内容推断（参考 ml-pytod 的 `create_pytod_dialogues.py`），或基于规则映射到安逸花意图体系（`verify_identity` / `explain_credit_limit` / `handle_loan_dispute` / `guide_loan_operation` / `say_goodbye` 等） |
| **`state.slot_values`** | 无 DST 标注，无对话状态追踪 | 用 LLM 或规则引擎提取槽值；`用户信息` 字段包含完整 CRM 数据，可作为金标准验证槽值是否正确 |
| **`state.requested_slots`** | 无标注 | 规则检测：发现用户询问型话语时提取 |
| **`actions`（用户/系统动作）** | 无对话行为标注 | 用 LLM 识别（参考 ml-pytod 中的 NLU 标注逻辑）；或对 DST 任务省略该字段（设为空列表） |
| **`service_call`** | 原数据为真实通话，无 API 调用记录 | 根据 `active_intent` + `slot_values` 推断：如意图为 `explain_credit_limit` 则 `service_call = {method: "query_account", parameters: {}}` |
| **`service_results`** | 同上 | 从 `用户信息` 字段解析 CRM 数据填充 |

### 3.3 额外上下文字段（SGD 无对应，但对本场景有价值）

| chat_test_100.json 字段 | SGD 无对应 | 处理方式 |
|---|---|---|
| `用户信息` | SGD 无 CRM 数据概念 | 存入 SGD 扩展字段 `metadata.user_info_parsed`，供 PyTOD 执行引擎使用 |
| `坐席回复` | SGD 无"参考回复"概念 | 存入 `metadata.reference_response`，供评估使用 |
| `人工校验` | SGD 无 QC 标签 | 存入 `metadata.qc_label`，供质量分析使用 |

---

## 四、转换可行性结论

### 4.1 基本转换：**完全可行**

将 `chat_test_100.json` 转换为 SGD **对话结构**（`dialogue_id` / `services` / `turns` 中的 `speaker` 和 `utterance`）**完全可行**，不需要任何外部信息补充。

### 4.2 完整 DST 标注转换：**需要补充 3 类信息**

要生成包含完整 DST 标注（`active_intent` + `slot_values` + `actions`）的 SGD 格式，需要补充：

#### 补充 1：意图标注（active_intent）

**方法 A（规则推断，推荐用于快速原型）**：
基于关键词匹配将每轮对话映射到安逸花意图体系：

```python
intent_rules = [
    (["身份", "您是", "本人", "核实"], "verify_identity"),
    (["额度", "提额", "提现", "多少钱"], "explain_credit_limit"),
    (["利率", "利息", "还款", "分期"], "explain_interest_rate"),
    (["借款", "异常", "没借", "没贷"], "handle_loan_dispute"),
    (["APP", "操作", "怎么借"], "guide_loan_operation"),
    (["再见", "不打扰", "告别"], "say_goodbye"),
]
```

**方法 B（LLM 推断，参考 ml-pytod）**：
ml-pytod 的 `create_pytod_dialogues.py` 通过读取 SGD 已有的 `active_intent` 标注生成 PyTOD 程序。对于 chat_test_100.json，需先用 LLM 为每轮对话打意图标签，再将其嵌入 SGD 格式。

#### 补充 2：槽值标注（slot_values）

`用户信息` 字段包含完整的 CRM 数据，可由 `parse_user_info()` 函数解析为结构化字典。
将解析后的数据注入为 SYSTEM turn 的 `service_results`，即可模拟 API 调用返回结果。

#### 补充 3：对话行为标注（actions）

对于 PyTOD 用途（Action Parser 训练/评估），`actions` 字段可以留为**空列表**——PyTOD 只需要 `utterance` + `state` 即可运行 Action Parser。完整的 action 标注仅用于 DST baseline 评估，对 PyTOD 不是必须的。

### 4.3 PyTOD 算法适配评估

ml-pytod 的核心运行链路（参考其 README 和代码结构）：

```
SGD schema.json
    ↓（定义服务/意图/槽位）
SGD dialogues_*.json
    ↓（提供 utterance + state groundtruth）
create_pytod_dialogues.py
    ↓（生成 PyTOD transcript：utterance + PyTOD program）
PyTOD Action Parser（LLM）
    ↓（读取 transcript 学习/预测 PyTOD 程序）
ExecutionEngine
    ↓（执行程序，调用 API）
Dialogue Manager（LLM）
    ↓（生成自然语言回复）
```

**对本项目（ContextMind）的适配**：  
ContextMind 已经在 `contextmind/modes/pytod/` 实现了 PyTOD 的 Action Parser + ExecutionEngine + Dialogue Manager，并在 `contextmind/scenarios/anyihua/` 实现了安逸花场景的 CRM API。因此：

- 不需要完整的 SGD 格式来 **运行** PyTOD——ContextMind 已有自己的运行时
- 需要 SGD 格式来 **评估** PyTOD 的 DST 准确率（对比预测的 slot_values 与 groundtruth）
- 需要 SGD 格式来 **微调** PyTOD 的 Action Parser（按 ml-pytod 的训练数据格式）

---

## 五、转换工具说明

已创建转换工具：`benchmark/tools/convert_chat_test_to_sgd.py`

### 5.1 用法

```bash
# 基本转换（仅 speaker + utterance，无 DST 标注）
python benchmark/tools/convert_chat_test_to_sgd.py \
    --input resources/data/chat_test_100.json \
    --output data/anyihua_sgd

# 完整转换（含 LLM 辅助意图推断）
python benchmark/tools/convert_chat_test_to_sgd.py \
    --input resources/data/chat_test_100.json \
    --output data/anyihua_sgd \
    --with-intent-inference

# 只转换前 10 条（调试用）
python benchmark/tools/convert_chat_test_to_sgd.py \
    --input resources/data/chat_test_100.json \
    --output /tmp/anyihua_sgd_debug \
    --limit 10
```

### 5.2 输出目录结构

```
data/anyihua_sgd/
    schema.json           # 安逸花外呼场景的 SGD schema
    dialogues_001.json    # 转换后的对话数据
    conversion_summary.json  # 转换统计
```

### 5.3 生成信息的策略

| 字段 | 策略 | 说明 |
|---|---|---|
| `active_intent` | 规则推断 | 按关键词匹配安逸花意图；可选 LLM 推断 |
| `slot_values` | parse_user_info 解析 | CRM 数据已在 `用户信息` 中，解析后注入 |
| `requested_slots` | 规则检测 | 检测用户问句提取 |
| `actions` | 从 intent 推断 | 根据意图生成对应的 REQUEST/INFORM 动作 |
| `service_call` | 从 intent 映射 | 意图 → API 名称的固定映射表 |
| `service_results` | parse_user_info 解析 | 直接用 CRM 数据作为 API 返回结果 |

---

## 六、参考资料

- SGD 数据集格式：https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
- ml-pytod 官方仓库：https://github.com/apple/ml-pytod
- 现有 RiSAWOZ→SGD 转换器：`benchmark/datasets/risawoz/sgd_converter.py`
- 安逸花场景 ServiceSchema：`contextmind/scenarios/anyihua/generation/schema.py`
- 安逸花 CRM API 实现：`contextmind/scenarios/anyihua/generation/engine.py`
- 用户信息解析工具：`contextmind/scenarios/anyihua/utils.py`（`parse_user_info`）

---

_本文档由分析工具生成，记录 chat_test_100.json → SGD 格式转换的完整分析过程。_
