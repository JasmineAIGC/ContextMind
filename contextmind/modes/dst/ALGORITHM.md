# DST — 零样本对话状态追踪

## 1. 对应论文

> **ChatGPT for Zero-shot Dialogue State Tracking: A Solution or an Opportunity?**  
> Michael Heck, Nurul Lubis, Benjamin Ruppik, Renato Vukovic, Shutong Feng, Christian Geishauser, Hsien-Chin Lin, Carel van Niekerk, Milica Gašić  
> ACL 2023 Findings · [arXiv:2306.01386](https://arxiv.org/abs/2306.01386)

---

## 2. 算法原理

### 2.1 问题定义

对话状态追踪（DST）的目标是：给定对话历史 $H_t = \{(u_1, s_1), \ldots, (u_t, s_t)\}$，在每轮结束时输出结构化对话状态 $B_t$（一组槽位–值对，如 `{"出发城市": "北京", "目的地": "上海"}`）。

传统 DST 方法需要大量标注数据微调专用模型，而本论文验证了「**纯提示词驱动的零样本 DST**」的可行性。

### 2.2 核心思想：累积状态追踪

论文的关键贡献是揭示了 ChatGPT 在零样本 DST 上既有潜力又有局限：

1. **累积更新**（本实现采用）：每轮只提取「**增量更新**」，与前一轮状态合并：

   ```
   B_t = update(B_{t-1}, ΔB_t)
   ```

   LLM 无需在每轮重新输出全部槽位，只需识别本轮新提及或更改的槽位，大幅降低提示词长度和 Token 消耗。

2. **特殊值处理**：沿用 MultiWOZ 惯例：
   - `"?"` （`UNKNOWN`）：用户在询问该槽位的值；
   - `"dontcare"`：用户明确表示不关心该槽位。

3. **零样本 vs 少样本**：论文对比了两种策略，本实现选择零样本（无固定示例），结合**动态槽位模式**（LLM 自由命名），以适应任意对话场景。

### 2.3 提示词设计

提示词由 `PromptManager.get_system_instruction()` 动态构造，包含四段：

| 段落 | 内容 |
|------|------|
| 角色定义 | "你是一个专业的对话信息提取系统，只输出纯 JSON" |
| 槽位本体 | 预定义槽位（固定模式）或说明 LLM 可自由提取（动态模式） |
| 历史摘要 | 可选：当历史过长时注入摘要以节省 Token |
| 输出格式 | JSON 格式约束 + 正确/错误示例 |

**动态槽位模式**是本实现的关键扩展：不固定槽位列表，LLM 可自由提取任何相关信息，输出含 `"intent"` 字段的 JSON，从而支持任意对话场景而无需重新定义本体。

### 2.4 历史管理策略

为避免超出 LLM 上下文窗口，采用双层历史管理：

```
[历史摘要（早期对话压缩）] + [最近 N 轮完整历史]
```

摘要模式默认使用「模板摘要」（抽取最后一轮状态），可切换为 LLM 摘要。

---

## 3. 代码结构

```
dst/
├── __init__.py          # 模块入口，导出 DialogueStateTracker
├── tracker.py           # 主追踪器 + 数据模型
├── prompts.py           # 提示词管理器（PromptManager）
└── parser.py            # JSON 响应解析器（DSTResponseParser）
```

### 3.1 核心数据模型（`tracker.py`）

```python
class SpecialValue(Enum):
    UNKNOWN = "?"        # 用户在询问此值
    DONTCARE = "dontcare"  # 用户不关心此值

@dataclass
class DialogueTurn:
    system_utterance: str
    user_utterance: str
    predicted_state: Dict[str, str]   # 累积状态
    turn_updates: Dict[str, str]      # 本轮增量
    raw_llm_response: Optional[str]   # 原始 LLM 输出（调试用）
```

### 3.2 主追踪器（`tracker.py` · `DialogueStateTracker`）

```python
class DialogueStateTracker:
    def __init__(self, llm_client, prompt_manager, ...):
        self.current_state = {}        # 累积状态 B_t
        self.dialogue_history = []     # DialogueTurn 列表

    @classmethod
    def from_scenario(cls, llm_client, scenario_config, ...):
        """工厂方法：从 ScenarioConfig 自动构建 PromptManager 并返回实例。"""
        pm = PromptManager(domain=scenario_config.name, ...)
        for slot_name, slot_desc in scenario_config.dst_slots.items():
            pm.add_slot(slot_name, slot_desc, ...)
        return cls(llm_client=llm_client, prompt_manager=pm, ...)

    async def process_turn(self, system_utterance, user_utterance):
        """核心方法：处理单轮对话，返回增量更新和新累积状态。"""
        # 1. 构建含历史的消息列表（ADK LlmAgent 管理 session）
        # 2. 调用 LLM 提取本轮槽位增量 ΔB_t
        # 3. 合并：B_t = update(B_{t-1}, ΔB_t)
        # 4. 记录 DialogueTurn，更新历史摘要
```

关键实现细节：
- 使用 Google ADK `LlmAgent` + `InMemoryRunner` 管理对话 session，历史由 ADK 自动维护，无需手动拼接；
- `_adk_session_id` 跨轮复用同一 session，确保 LLM 感知多轮上下文；
- 每轮调用后通过 `DSTResponseParser` 鲁棒解析 JSON（处理 markdown 代码块、前缀文字等干扰）。

### 3.3 提示词管理器（`prompts.py` · `PromptManager`）

```python
class PromptManager:
    def __init__(self, domain, enable_dynamic_slots=True, ...):
        self.ontology_slots = {}       # 槽位名 → 描述
        self.categorical_constraints = {}  # 槽位名 → 允许值列表

    def add_slot(self, name, description, categorical_values=None):
        """注册槽位定义（固定模式下约束 LLM 提取范围）。"""

    def get_system_instruction(self, history_summary=None):
        """动态构建系统指令，根据模板风格选择 structured/concise/conversational。"""
```

**RiSAWOZ 适配**：当 `domain` 属于 RiSAWOZ 基准的中文领域（医院、天气、酒店等）时，自动切换输出格式为 `"领域-槽位名"` 前缀格式，与标准评测对齐。

### 3.4 JSON 解析器（`parser.py` · `DSTResponseParser`）

鲁棒的 JSON 提取器，依次尝试：
1. 直接 `json.loads()`；
2. 提取 markdown 代码块中的 JSON；
3. 正则表达式找第一个 `{...}` 块；
4. 失败时返回空字典（不抛异常，确保系统鲁棒性）。

---

## 4. 与其他模式的对比

| 维度 | DST | FnCTOD | PyTOD | Genie | Evolve |
|------|-----|--------|-------|-------|--------|
| LLM 调用次数/轮 | 1 | 1（函数调用） | 2（AP+DM） | 2（解析+生成） | 1+后台 |
| 状态追踪方式 | 累积 JSON | 函数参数 | 数据流程序 | Worksheet 状态机 | 隐式记忆 |
| 需要 Schema 文件 | 否 | 是（fnctod_domain.json） | 是（schema.json） | 是（worksheet） | 否 |
| 适用场景 | 通用 DST | 结构化槽位提取 | 复杂业务流程 | 表单填写流程 | 开放域闲聊 |

---

## 5. 参考资源

- 论文主页：https://arxiv.org/abs/2306.01386  
- MultiWOZ 基准数据集：https://github.com/budzianowski/multiwoz  
- RiSAWOZ 基准数据集：https://github.com/terryqj0107/RiSAWOZ
