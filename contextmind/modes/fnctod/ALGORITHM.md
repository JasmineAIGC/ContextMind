# FnCTOD — 基于函数调用的零样本对话状态追踪

## 1. 对应论文

> **Large Language Models as Zero-shot Dialogue State Tracker through Function Calling**  
> Zekun Li, Zhiyu Wan, Cao Liu, Zhe Feng, Bing Yin, Liang Huang  
> ACL 2024 · [arXiv:2402.10466](https://arxiv.org/abs/2402.10466)

---

## 2. 算法原理

### 2.1 核心思想：DST ≡ 函数调用

FnCTOD 的创新在于将对话状态追踪（DST）重新表述为 LLM 原生支持的**函数调用（Function Calling）**任务：

- **传统 DST**：LLM 输出 JSON 槽位对，依赖精心设计的提示词格式约束；
- **FnCTOD**：将每个业务域（domain）定义为一个函数，槽位定义为函数参数，LLM 通过「调用函数」来提取槽位值。

```
域: query_order
参数:
  - order_id (str, optional): 订单编号
  - status (str, optional, enum=["待发货","已发货","已完成"]): 订单状态

对话: "我想查一下订单ORD-2024的物流"
→ LLM 调用: query_order(order_id="ORD-2024")
→ 提取状态: {"order_id": "ORD-2024"}
```

### 2.2 优势分析

| 优势 | 说明 |
|------|------|
| 结构化约束 | 函数签名本身即是输出约束，无需额外格式提示词 |
| 枚举合法性 | 通过 `enum` 参数自然限制分类槽位的合法取值 |
| 零样本泛化 | 仅描述函数语义，无需领域内样本 |
| 原生集成 | 直接复用 LLM 提供商的 Function Calling 接口，无额外适配成本 |

### 2.3 论文中的关键发现

1. **函数调用比 JSON 提示词更可靠**：Function Calling 接口天然保证输出符合预定义 schema，减少解析错误；
2. **多域同时追踪**：可一次性注册多个域函数，LLM 在一轮中调用多个函数完成多域槽位提取；
3. **零样本性能**：在 MultiWOZ 2.4 上 Joint Goal Accuracy（JGA）达到约 20%（零样本），与微调的传统方法有差距，但无需任何标注数据。

### 2.4 系统指令设计

FnCTODTracker 自动生成系统指令：

```
你是一个任务型对话助手，通过调用函数提取对话中的关键信息，然后给出自然语言回复。
可用的业务域: query_order, check_inventory。
处理规则：
1. 每轮对话调用相应函数，一次性填入对话中已识别的槽位值；
2. 未在本轮对话中提及的槽位保持为空，不要猜测；
3. 函数调用完成后，立即用简洁的中文给出对话回复。

## 业务场景背景
[来自 ScenarioConfig.system_prompt]
```

### 2.5 降级方案（JSON Fallback）

当 LLM 后端不支持原生函数调用（如 vLLM 未启用 `--enable-auto-tool-choice`）时，`FnCTODTracker` 自动切换至 **JSON 备用方案**：

- 将函数签名改写为文字描述的槽位清单，注入系统提示词；
- 要求 LLM 输出 `<SLOTS>{...}</SLOTS>` + 自然语言回复；
- 正则解析 `<SLOTS>` 块提取槽位值；
- 一旦切换，整个会话保持该模式，避免重复探测开销。

---

## 3. 代码结构

```
fnctod/
├── __init__.py           # 模块入口
├── function_manager.py   # 数据模型（DomainSpec/FunctionParameter）+ FunctionManager
├── schemas.py            # 从外部 JSON 文件加载 DomainSpec 的工具
├── tracker.py            # FnCTODTracker 主追踪器
└── prompts.yaml          # 提示词模板（参考用）
```

### 3.1 数据模型（`function_manager.py`）

```python
@dataclass
class FunctionParameter:
    """函数参数 ≈ 对话槽位。"""
    name: str           # 槽位名
    description: str    # 槽位说明（注入 LLM 的语义理解依据）
    param_type: ParameterType = ParameterType.STRING
    required: bool = False
    enum_values: Optional[List[str]] = None  # 分类槽位的合法取值

@dataclass
class DomainSpec:
    """业务域定义 ≈ 一个函数的完整规格。"""
    name: str
    description: str
    parameters: List[FunctionParameter]

class FunctionManager:
    """管理多个 DomainSpec，支持增删改查。"""
    def add_domain(self, domain_spec: DomainSpec): ...
    def get_all_domains(self) -> List[DomainSpec]: ...
    def get_domain_names(self) -> List[str]: ...
```

### 3.2 DomainSpec → ADK FunctionTool（`tracker.py`）

```python
def _domain_to_adk_tool(domain_spec: DomainSpec) -> FunctionTool:
    """将 DomainSpec 动态转换为 ADK FunctionTool。

    核心技巧：用 inspect.Signature 动态构造 Python 函数签名，
    再包装为 FunctionTool，ADK 自动从签名生成 JSON Schema 传给 LLM。
    """
    param_names = [p.name for p in domain_spec.parameters]
    parameters = [
        inspect.Parameter(name, kind=POSITIONAL_OR_KEYWORD,
                         default=None, annotation=Optional[str])
        for name in param_names
    ]
    func.__signature__ = inspect.Signature(parameters)
    return FunctionTool(func=func)
```

这是 FnCTOD 的关键实现桥梁：`DomainSpec`（业务层抽象）→ Python 函数签名 → ADK JSON Schema → LLM Function Calling。

### 3.3 主追踪器（`tracker.py` · `FnCTODTracker`）

```python
class FnCTODTracker:
    def __init__(self, function_manager, system_instruction=None,
                 scenario_context="", config=None, use_native_tools=True):
        # 自动构建系统指令（含可用域列表和业务背景）
        # 创建 ADK LlmAgent（function_tools=all_domain_tools）
        # 创建 ADK InMemoryRunner（管理会话历史）

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        """从 ScenarioConfig + 外部 domain_spec 构建追踪器。
        scenario_context 优先取 scenario_config.system_prompt。
        """

    async def process_turn(self, user_utterance, agent_utterance=""):
        """处理单轮对话，返回 {"response", "state", "updates"}。
        
        优先使用原生 Function Calling；失败时自动降级到 JSON Fallback。
        """
```

**会话管理**：`_session_id` 跨轮复用，ADK InMemoryRunner 自动维护多轮历史，`process_turn` 只需传入当前话语。

### 3.4 Schema 加载器（`schemas.py`）

```python
def load_domain_spec_from_file(path) -> DomainSpec:
    """支持两种 JSON 格式：
    1. FnCTOD companion 格式（build_schema_data.py 生成）：
       {"name": "...", "parameters": {"properties": {...}, "required": [...]}}
    2. SGD 格式：
       [{"service_name": "...", "slots": [...], "intents": [...]}]
    """
```

外部 Schema 文件完全解耦业务数据与算法代码，更换场景只需替换 JSON 文件。

---

## 4. 运行时数据流

```
用户话语
    ↓
FnCTODTracker.process_turn()
    ↓
[原生模式]  ADK LlmAgent.run_async()
                ↓
            LLM 发出 Function Call → FunctionTool 执行 → 提取 kwargs → turn_updates
                ↓
            LLM 生成最终文本回复
    ↓
[降级模式]  _process_turn_fallback()
                ↓
            LLM 输出 <SLOTS>{...}</SLOTS> + 回复文本
                ↓
            正则解析 → turn_updates
    ↓
current_state.update(turn_updates)
    ↓
return {"response", "state", "updates"}
```

---

## 5. Schema 文件生成

FnCTOD 需要预先生成 `*_fnctod_domain.json` 文件：

```bash
python examples/step2b_build_schema_data.py --schema schema/xxx_schema.json --fnctod-only
```

生成的文件格式：

```json
{
  "name": "query_order",
  "description": "查询订单状态和物流信息",
  "parameters": {
    "type": "object",
    "properties": {
      "order_id": {"type": "string", "description": "订单编号"},
      "status":   {"type": "string", "description": "查询状态", "enum": ["待发货","已发货"]}
    },
    "required": []
  }
}
```

---

## 6. 参考资源

- 论文主页：https://arxiv.org/abs/2402.10466  
- 官方代码：https://github.com/jennycs0830/FnCTOD  
- MultiWOZ 2.4：https://github.com/smartyfh/MultiWOZ2.4  
- Google ADK Function Calling：https://google.github.io/adk-docs/tools/function-tools/
