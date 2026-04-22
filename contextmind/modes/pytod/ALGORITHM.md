# PyTOD — 数据流合成驱动的任务型对话

## 1. 对应论文

> **Task-Oriented Dialogue as Dataflow Synthesis**  
> Jacob Andreas, John Bufe, David Burkett, Charles Chen, Josh Clausman, Jean Crawford, Kate Crim, Jordan DeLoach, Leah Dorner, Nikita Durme, et al.  
> TACL 2020 / NAACL 2021 · [arXiv:2009.11423](https://arxiv.org/abs/2009.11423)

官方代码仓库：https://github.com/microsoft/task_oriented_dialogue_as_dataflow_synthesis

---

## 2. 算法原理

### 2.1 核心思想：对话即程序

PyTOD 将任务型对话建模为**数据流程序合成**（Dataflow Synthesis）：对话的每一轮产生一个可执行的 Python-like 程序，程序的执行结果代表 API 调用的返回值，自然语言回复基于执行结果生成。

```
用户: "帮我查一下账户余额"
↓ AP（动作解析器）
x1 = query_balance(account_id="ACC-001")
say(x1.balance)
↓ EE（执行引擎）
x1 = {"balance": "¥8,230.00", "status": "正常"}
↓ DM（对话管理器）
"您的账户余额为 ¥8,230.00，账户状态正常。"
```

### 2.2 三步流程（AP → EE → DM）

#### Step 1 · Action Parser（AP）—— LLM 生成程序

AP 是本模式的核心。它输入：
- 对话历史；
- ServiceSchema（函数签名 + 意图描述）；
- 已计算变量的 Dataflow Context（先前轮次变量绑定，如 `x1 = {...}`）。

输出一段 PyTOD 伪代码程序：

```python
x1 = verify_identity(user_name="张三", phone="138xxxx5678")
x2 = query_account(user_id=x1.user_id)     # 引用上一轮变量
say(x2.balance, x2.due_date)               # 指定 DM 要传达的信息
```

**关键语句类型**：

| 语句 | 含义 | 示例 |
|------|------|------|
| `xN = func(...)` | 调用 API，绑定结果 | `x1 = query_order(id="ORD-001")` |
| `say(xN.field)` | 告诉 DM 要传达的内容 | `say(x1.balance)` |
| `hint(msg)` | 向 DM 提供补充说明 | `hint("用户已确认身份")` |
| `confirm(xN.field, val)` | 请求用户确认某个值 | `confirm(x1.amount, 500)` |
| `xN.slot = val` | 槽位赋值 | `x2.city = "北京"` |

#### Step 2 · Execution Engine（EE）—— 纯 Python 执行

EE 是**无 LLM 的确定性组件**，通过 AST 解析程序文本并安全执行（不使用 `eval()`）：

1. 解析 `xN = func(kwargs)` 语句，调用已注册的 API 函数；
2. 管理变量绑定表 `{x1: {...}, x2: {...}}`；
3. 收集 `say()`、`hint()` 内容，传递给 DM；
4. 对无法解析的语句降级为「存根执行」（返回成功标记），保证流程不中断。

**安全性设计**：仅允许调用已通过 `engine.registry[name] = func` 显式注册的函数；参数值只能是字符串、数字、布尔等常量（不允许任意表达式），防止代码注入。

#### Step 3 · Dialogue Manager（DM）—— LLM 生成回复

DM 接收：
- 对话历史；
- AP 生成的程序文本；
- EE 执行结果（API 返回值）。

生成自然语言回复，**优先传达 `say()` 指定的内容**，使 AP 能精确控制 DM 的信息传达。

### 2.3 Dataflow Context（跨轮变量引用）

PyTOD 的最大特色是**跨轮次的数据流依赖**：

```
第1轮: x1 = verify_identity(...)  → {"user_id": "U001", "name": "张三"}
第2轮: x2 = query_loan(user_id=x1.user_id)  ← 引用第1轮结果
第3轮: x3 = apply_loan(amount=5000, user_id=x1.user_id)
```

AP 的 prompt 中包含先前轮次的变量绑定快照（`prior_dataflow`），使 AP 能感知已有信息，避免重复询问用户。

### 2.4 Top-K 意图检索（BM25 优化）

当 Schema 包含大量 API 时，全量注入 prompt 会超出 Token 限制。本实现加入**多信号 BM25 意图检索**：

1. **BM25 词汇分**（主信号）：对 API 名称、描述、槽位名分别建立 token 集合，对当前查询打分；
2. **依赖就绪加成**（×2 或 ×1.3）：若某 API 的 `required_slots` 已被先前调用的 API `result_slots` 覆盖，认为「依赖已就绪」，提升排名；
3. **槽位提及加成**（最高 ×1.5）：当前话语中已提及某 API 的必填槽位名，提升排名；
4. **已调用惩罚**（×0.2）：已成功调用过的 API 降权，避免重复推荐。

仅将 top-K（默认 5）个意图注入 AP prompt，大幅节省 Token。

---

## 3. 代码结构

```
pytod/
├── __init__.py           # 模块入口
├── schemas.py            # ServiceSchema / IntentDefinition / SlotDefinition
├── execution_engine.py   # EE：程序解析 + 安全执行
├── prompts.py            # PyTODPromptBuilder：AP/DM 提示词构建
├── tracker.py            # AdkPyTODTracker：三步流程协调器
└── registry.py           # 场景 API 注册表（现为空，由外部文件传入）
```

### 3.1 Schema 数据模型（`schemas.py`）

```python
@dataclass
class SlotDefinition:
    name: str
    description: str
    is_categorical: bool = False
    possible_values: List[str] = []

@dataclass
class IntentDefinition:
    name: str               # 函数名（如 query_balance）
    description: str        # 意图说明
    required_slots: List[str]
    optional_slots: List[str]
    result_slots: List[str]  # API 返回的字段名（用于 Dataflow 依赖分析）

@dataclass
class ServiceSchema:
    service_name: str
    description: str
    intents: List[IntentDefinition]
    slots: List[SlotDefinition]
```

### 3.2 执行引擎（`execution_engine.py` · `ExecutionEngine`）

```python
class ExecutionEngine:
    registry: Dict[str, Callable]  # 已注册的 API 函数

    def execute_program(self, program_text: str) -> ProgramExecutionResult:
        """解析并执行 PyTOD 程序，返回结构化执行结果。"""
        # 1. 逐行解析语句（正则 + AST，不使用 eval）
        # 2. 查 registry 执行函数调用
        # 3. 管理变量绑定 {x1: val, x2: val}
        # 4. 收集 say/hint 内容
        # 5. 安全处理执行失败（降级为存根）
```

**模糊匹配**：EE 支持对函数名的模糊匹配（基于 `difflib.get_close_matches`），容忍 AP 轻微的命名差异（如 `confirm_identity` → `verify_identity`）。

### 3.3 提示词构建器（`prompts.py` · `PyTODPromptBuilder`）

```python
class PyTODPromptBuilder:
    def build_action_parser_prompt(self, history, user_utterance,
                                   scenario_context="", prior_dataflow=None,
                                   relevant_intent_names=None):
        """构建 AP 消息列表（系统消息 + 用户消息静动态分离）。
        
        系统消息（静态）: AP 语法规则 + 业务背景 + [全量函数签名]
        用户消息（动态）: 对话历史 + [top-K 函数签名] + 已计算变量 + 当前话语
        """

    def build_dm_prompt(self, history, user_utterance, program, execution_result,
                        scenario_context=""):
        """构建 DM 消息列表，say() 优先原则确保信息传达准确。"""
```

### 3.4 主追踪器（`tracker.py` · `AdkPyTODTracker`）

```python
class AdkPyTODTracker:
    def __init__(self, llm_client, engine, schema, scenario_context="",
                 max_history_turns=10, top_k_intents=5):
        self.llm_client = llm_client
        self.engine = engine         # ExecutionEngine
        self.schema = schema         # ServiceSchema
        self.prompt_builder = PyTODPromptBuilder(schema)

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        """从 ScenarioConfig + schema= + schema_path= 构建追踪器。
        scenario_context 优先取 scenario_config.system_prompt。
        """

    async def process_turn(self, user_utterance, system_utterance=""):
        """执行 AP → EE → DM 三步流程，返回 {"response","program_text","state","execution"}。"""
        # Step 1: AP
        ap_messages = self.prompt_builder.build_action_parser_prompt(...)
        program_text = await self.llm_client.chat_async(ap_messages)

        # Step 2: EE
        execution_result = self.engine.execute_program(program_text)
        self.current_state.update(execution_result.variable_bindings)

        # Step 3: DM
        dm_messages = self.prompt_builder.build_dm_prompt(...)
        response = await self.llm_client.chat_async(dm_messages)

        return {"response": response, "program_text": program_text, ...}
```

---

## 4. 运行时数据流

```
用户话语
    ↓
AdkPyTODTracker.process_turn()
    ├── Step 1: AP
    │   ├── top-K 意图检索（BM25）→ relevant_intent_names
    │   ├── build_action_parser_prompt(history, prior_dataflow, ...)
    │   └── llm_client.chat_async() → program_text
    │
    ├── Step 2: EE
    │   ├── engine.execute_program(program_text)
    │   ├── 更新变量绑定 {x1: val, ...}
    │   └── 收集 say/hint 内容
    │
    └── Step 3: DM
        ├── build_dm_prompt(history, program_text, execution_result, ...)
        └── llm_client.chat_async() → response

return {"response", "program_text", "state", "execution"}
```

---

## 5. Schema 和 API 文件生成

```bash
# 生成 schema.json 的 companion 文件（PyTOD API 函数）
python examples/build_schema_data.py --schema schema/xxx_schema.json

# 生成后的 companion 文件
schema/xxx_pytod_apis.py   ← 包含每个意图对应的 Python 函数
```

PyTOD API 函数示例（由 build_schema_data.py 自动生成或手动编写）：

```python
def verify_identity(user_name: str = None, phone: str = None):
    """核实用户身份。返回: user_id, verified"""
    # 实际业务逻辑或 mock 实现
    return {"user_id": "U001", "verified": True, "name": user_name}
```

---

## 6. 参考资源

- 论文主页：https://arxiv.org/abs/2009.11423  
- 官方代码：https://github.com/microsoft/task_oriented_dialogue_as_dataflow_synthesis  
- SMCalFlow 数据集（论文使用）：https://microsoft.github.io/task_oriented_dialogue_as_dataflow_synthesis/
