# Genie Worksheets — 声明式策略驱动的任务型对话

## 1. 对应论文

> **Unleashing the Potential of Large Language Models through Genie Worksheets**  
> Harshit Joshi, Shicheng Liu, James Chen, Robert Weigle, Monica Lam  
> Stanford University · 2024 · [arXiv:2407.05674](https://arxiv.org/abs/2407.05674)

官方代码仓库：https://github.com/stanford-oval/worksheets  
官方演示：https://worksheets.cs.stanford.edu/

---

## 2. 算法原理

### 2.1 核心思想：Worksheet 即策略声明

Genie Worksheets 的核心洞察是：**业务对话策略可以完全声明式描述**，无需用流程图、状态机代码或大量提示词工程来定义对话流程。

一个 Worksheet 就是一张「**表单**」，每行定义一个需要收集的字段：

```
字段名        描述              类型      是否必填   on_success
user_name     请输入您的姓名    str       True
phone         请输入手机号      str       True
loan_amount   贷款金额（元）    float     False
intent        借款意图          enum      True       book_loan
```

系统在对话中**按策略顺序**引导用户填写表单，直到所有必填字段完成，触发 `on_success` API 调用。

### 2.2 系统架构：双 LLM + 确定性状态机

```
用户话语
    ↓
[LLM-1 SemanticParser]  ← 理解用户意图，提取字段值
    ↓
[PolicyExecutor]         ← 无 LLM，确定性状态机，管理 Worksheet 字段状态
    ↓
[AgentActs 计算]         ← 确定性规则：Ask / Confirm / Report
    ↓
[LLM-2 ResponseGenerator] ← 将 AgentActs 转换为自然语言回复
    ↓
用户回复
```

**确定性 PolicyExecutor 的意义**：对话策略（要问什么字段、什么时候确认、什么时候触发 API）完全由 Worksheet 声明控制，**不依赖 LLM 判断**，因此行为可预期、可审计，解决了 LLM 对话流程不可控的核心问题。

### 2.3 六步执行流程（对齐论文 Figure 2）

每轮对话按以下顺序执行：

**Step 1 · 意图路由**  
当 Worksheet 中定义了多个意图（Intent）时，用 LLM 根据用户话语选择当前最合适的意图。单意图场景跳过此步（避免不必要的 LLM 调用）。

**Step 2 · 语义解析（LLM-1）**  
`SemanticParser` 分析用户话语，结合当前 Worksheet 填写状态，输出 JSON 格式的字段赋值：

```json
{"user_name": "张三", "phone": "138xxxx5678"}
```

原版 Genie 使用 SUQL（SQL-like 语言 + LLM 混合）查询知识库；本实现降级为直接 JSON 字段提取，在无 PostgreSQL 环境下功能等同。

**Step 3 · Worksheet 状态更新**  
`PolicyExecutor` 处理：
- 待确认字段：检测用户是否在回应上轮确认请求（yes/no 检测）；
- 应用本轮提取的字段值（`fill_batch()`）；
- 校验枚举值合法性。

**Step 4 · on_success API 分发**  
当某字段填写完成且配置了 `on_success` 回调时，自动调用注册的 API 函数（如触发订单查询、预约服务等）。

**Step 5 · AgentActs 计算**  
`PolicyExecutor` 按确定性规则计算本轮应执行的动作列表：
- `AskField(field)`：引导用户填写指定字段；
- `AskForFieldConfirmation(field, value)`：请求用户确认已填值；
- `Report(field, result)`：报告 API 调用结果。

**Step 6 · 回复生成（LLM-2）**  
`ResponseGenerator` 将 AgentActs 列表转换为自然、流畅的中文回复，业务场景背景由 `scene_description` 注入提示词。

### 2.4 预填充（Prefill）机制

对于「外呼」等主动发起场景，系统已知用户信息（如姓名、账号）可通过 `prefill_from_scene_description()` 预先注入 Worksheet，避免重复询问已知信息：

```python
tracker.prefill_from_scene_description()
# → Worksheet 自动填入 scene_description 中识别到的字段值
```

### 2.5 与传统方法的对比

| 维度 | 传统提示词工程 | Genie Worksheets |
|------|--------------|-----------------|
| 对话策略定义 | 嵌入提示词，难以维护 | Worksheet 表格，声明式 |
| 策略可控性 | LLM 可能偏离预设策略 | 确定性 PolicyExecutor 保证 |
| 业务人员可维护 | 需要懂提示词工程 | 只需维护 CSV/JSON 表格 |
| 多意图切换 | 靠提示词提示 | intent_routing 自动路由 |
| API 触发 | 每次手动判断 | on_success 声明式绑定 |

---

## 3. 代码结构

```
genie/
├── __init__.py           # 模块入口
├── tracker.py            # GenieTracker：六步流程协调器
├── policy_executor.py    # PolicyExecutor：确定性 Worksheet 状态机
├── semantic_parser.py    # SemanticParser：LLM-1 字段提取
├── agent_acts.py         # AgentActs 数据模型
└── prompts/
    ├── README.md
    ├── semantic_parsing.prompt   # LLM-1 提示词模板
    └── response_generator.prompt # LLM-2 提示词模板
```

### 3.1 PolicyExecutor（`policy_executor.py`）

```python
class FieldStatus:
    EMPTY = "empty"
    FILLED = "filled"
    PENDING_CONFIRM = "pending_confirm"
    CONFIRMED = "confirmed"

@dataclass
class WorksheetState:
    field_values: Dict[str, Any]    # 已填写的字段值
    field_statuses: Dict[str, str]  # 每字段的 FieldStatus
    confirmed_fields: Set[str]      # 已确认的字段集合

class PolicyExecutor:
    """纯 Python 确定性状态机，不调用任何 LLM。"""

    def fill_batch(self, assignments: Dict[str, Any]):
        """批量填写字段，触发校验和状态转换。"""

    def get_next_field(self) -> Optional[PolicyField]:
        """按 Worksheet 顺序返回下一个需要填写的字段。"""

    def get_agent_acts(self) -> AgentActs:
        """确定性计算本轮 AgentActs（Ask/Confirm/Report）。"""

    def is_complete(self) -> bool:
        """判断 Worksheet 是否全部完成。"""
```

### 3.2 SemanticParser（`semantic_parser.py`）

```python
class SemanticParser:
    async def parse(self, user_utterance, executor, history, scene_description):
        """调用 LLM-1，从用户话语中提取字段赋值。
        
        提示词包含：
        1. 当前 Worksheet 状态（已填/待填字段）
        2. 对话历史（最近 N 轮）
        3. 业务场景描述
        4. JSON 输出格式要求
        """
        # 返回: {"field_name": "value", ...} 或 {}

    async def prefill_from_description(self, description, executor):
        """从 scene_description 预提取已知字段值，在对话开始前注入 Worksheet。"""
```

### 3.3 AgentActs（`agent_acts.py`）

```python
class AgentActs:
    """本轮系统应执行的动作列表，传给 ResponseGenerator。"""
    actions: List[AgentAct]

class AskAgentAct(AgentAct):
    field: PolicyField          # 需要询问的字段

class AskForConfirmationAgentAct(AgentAct):
    field: PolicyField
    value: Any                  # 已填值，请求用户确认

class ReportAgentAct(AgentAct):
    field: PolicyField
    result: Any                 # API 执行结果
```

### 3.4 GenieTracker（`tracker.py`）

```python
class GenieTracker:
    def __init__(self, llm_client, schema, scene_description="",
                 intent_name=None, max_history_turns=10):
        self._executor = PolicyExecutor(schema, intent_name)
        self._semantic_parser = SemanticParser(llm_client)

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, schema=None,
                      worksheet_path=None, ...):
        """支持从 ScenarioConfig + schema 对象或 worksheet 文件路径创建。
        scene_description 优先取 system_prompt，再取 description，最后取 name。
        """

    async def process_turn(self, user_utterance):
        """执行六步流程，返回 {"response","worksheet_state","is_complete","agent_acts"}。"""

    def register_api(self, func_name, callable_func):
        """注册 on_success API 回调。"""

    async def prefill(self):
        """从 scene_description 预填 Worksheet（外呼场景使用）。"""
```

---

## 4. Worksheet 文件格式

支持两种格式：

**CSV 格式**（业务人员友好）：

```csv
field_name,description,field_type,required,on_success,confirm_on_fill,enum_values
user_name,用户姓名,str,True,,,
phone,手机号,str,True,,,
loan_amount,贷款金额,float,False,,,
intent,借款意图,str,True,apply_loan,,审核通过|拒绝|待审核
```

**JSON 格式**（程序化生成）：

```json
{
  "service_name": "loan_application",
  "description": "贷款申请 Worksheet",
  "intents": [{
    "name": "apply_loan",
    "description": "申请贷款",
    "policy_fields": [
      {"name": "user_name", "description": "用户姓名", "required": true},
      {"name": "amount", "description": "贷款金额", "required": false,
       "on_success": "check_credit"}
    ]
  }]
}
```

---

## 5. 运行时数据流

```
用户话语
    ↓
GenieTracker.process_turn()
    │
    ├─ Step 1: 意图路由（多意图时调用 LLM）
    │          _route_intent() → 切换 PolicyExecutor.intent
    │
    ├─ Step 2: 语义解析（LLM-1）
    │          SemanticParser.parse() → {field: value, ...}
    │
    ├─ Step 3: Worksheet 状态更新
    │          ├─ 3a: 处理待确认字段（yes/no 检测）
    │          └─ 3b: executor.fill_batch(extracted)
    │
    ├─ Step 4: on_success API 分发
    │          _dispatch_on_success() → 调用注册的 API 函数
    │
    ├─ Step 5: AgentActs 计算
    │          executor.get_agent_acts() → [Ask/Confirm/Report, ...]
    │
    └─ Step 6: 回复生成（LLM-2）
               _generate_response() → 自然语言回复

return {"response", "worksheet_state", "is_complete", "agent_acts"}
```

---

## 6. 参考资源

- 论文主页：https://arxiv.org/abs/2407.05674  
- 官方代码：https://github.com/stanford-oval/worksheets  
- 官方演示：https://worksheets.cs.stanford.edu/  
- SUQL 语言：https://github.com/stanford-oval/suql
