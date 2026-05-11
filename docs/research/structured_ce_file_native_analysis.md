# Structured Context Engineering for File-Native Agentic Systems × ContextMind 集成分析

> **论文**：D McMillan 等  
> *"Structured Context Engineering for File-Native Agentic Systems"*  
> arXiv:2602.05447（2026年2月）

---

## 一、论文核心思想

### 1.1 问题：文件原生 Agent 系统的结构化数据格式选择

"文件原生 Agent 系统（File-Native Agentic Systems）"是指：AI Agent 直接操作文件系统，需要读取、修改、导航多个文件（代码库、配置文件、文档）。

**核心问题**：当 Agent 需要处理结构化数据时，用什么格式注入上下文最有效？

### 1.2 大规模实证研究设计

这是一篇**以实验为主**的论文，规模在上下文工程领域罕见：

| 维度 | 规格 |
|------|------|
| 总实验次数 | 9,649 次 |
| 测试模型数 | 11 个（覆盖 GPT-4o、Claude 3.5、Gemini 等主流模型）|
| 数据格式 | 4 种：YAML、Markdown、JSON、TOON（自定义） |
| 评估任务 | 多文件导航（Multi-File Navigation）、Schema 准确性 |

### 1.3 四种数据格式对比

| 格式 | 描述 | 优势 | 劣势 |
|------|------|------|------|
| **YAML** | 缩进式层次结构 | 人类可读、层次清晰 | 缩进错误敏感 |
| **Markdown** | 标题/列表/代码块 | LLM 训练数据中大量出现 | 嵌套结构表达弱 |
| **JSON** | 标准键值对 | 机器解析友好 | 冗余字符多（大括号/引号）|
| **TOON** | 自定义树状表示法 | 极度紧凑、低 token | 非标准，LLM 理解依赖训练 |

### 1.4 主要实验发现

**关键结论**：

1. **Markdown 在多文件导航任务中表现最佳**（在大多数模型上），原因是 LLM 训练数据中含有大量 Markdown 格式的代码文档

2. **YAML 在 Schema 准确性任务中表现最佳**，特别是当数据有层次结构时

3. **JSON 在高度结构化数据（精确查找）场景表现好**，但在自由文本任务中表现差

4. **TOON 在 token 效率上最高**，但不同模型的理解差异大（非标准格式）

5. **模型差异显著**：没有一种格式在所有 11 个模型上都最优，格式选择应该**与目标 LLM 匹配**

6. **格式对长上下文的影响更大**：短 context 下格式差异小；长 context（>4K tokens）时 Markdown 优势明显

### 1.5 TOON 格式介绍

TOON（Tree-Oriented Object Notation）是论文提出的自定义格式：

```
# JSON 格式（冗余）
{"user": {"name": "张三", "balance": 1234.56, "account_type": "savings"}}

# TOON 格式（紧凑）
user: 张三 | balance: 1234.56 | type: savings
```

TOON 的核心设计原则：用管道符 `|` 分隔字段，用缩进表示层次，避免 JSON 的冗余括号和引号。

---

## 二、与 ContextMind 现有架构对照

### 数据格式使用现状

| 上下文组件 | 当前格式 | 实验建议 |
|-----------|---------|---------|
| **API 函数签名** | 自定义文本格式 | 可尝试 Markdown 代码块格式 |
| **prior_dataflow（变量）** | 自定义文本（`x1 = {...}`）| JSON 类格式，可优化为 YAML/TOON |
| **对话历史** | `role: content` 文本格式 | Markdown 列表格式，与 LLM 训练习惯吻合 |
| **意图上下文** | 自定义文本描述 | 可尝试 YAML 列表（层次结构清晰）|
| **系统 prompt** | 自然语言 + 规则列表 | Markdown（`##` 标题分区）|
| **Schema（KB）** | JSON 存储 | 注入 prompt 时可转为 YAML |

### Schema 格式的特殊重要性

ContextMind 的 `schema_builder` 产出的 Schema 是 JSON 格式，但当这些 Schema 被注入到 LLM prompt 时（如在 `build_schema_data.py` 中），格式选择直接影响：
1. LLM 理解 Schema 的准确性
2. 生成代码的正确率（PyTOD 函数生成）

**论文结论**：YAML 在 Schema 准确性任务上表现最佳，这对 `schema_builder` 的 prompt 设计有直接指导意义。

---

## 三、集成机会分析

### 机会 A：Schema 注入格式改为 YAML ⭐⭐⭐ 最高价值

**当前做法**：`schema_builder` 的各阶段 prompt 中，Schema 描述使用 JSON 格式或自定义文本。

**基于论文实验**：YAML 在 Schema 准确性任务上表现最佳，且可读性更好。

**改进方案**（`contextmind/schema_builder/pytod/codegen/shared/generator.py`）：

```python
import yaml

def format_schema_for_prompt(schema: dict, format: str = "yaml") -> str:
    """
    将 Schema 格式化为 prompt 注入格式。
    默认使用 YAML（基于 McMillan 等的实验结论）。
    """
    if format == "yaml":
        return yaml.dump(schema, allow_unicode=True, default_flow_style=False)
    elif format == "json":
        return json.dumps(schema, ensure_ascii=False, indent=2)
    elif format == "toon":
        return _to_toon_format(schema)
    else:
        return str(schema)

# 在 Phase 1/2/3 的 prompt 构建中使用
schema_str = format_schema_for_prompt(intent_schema, format="yaml")
```

---

### 机会 B：prior_dataflow 格式改为 TOON/YAML ⭐⭐ 高价值

**当前 prior_dataflow 格式**：
```
x1 = {"user_name": "张三", "user_id": "U001", "verify_status": "success", "timestamp": "2026-04-07"}
```

**TOON 格式（更紧凑）**：
```
x1 [verify_identity]: user_name=张三 | user_id=U001 | status=success
```

**token 节省估算**：原格式约 40 tokens，TOON 格式约 18 tokens，节省 55%。

**YAML 格式（更可读）**：
```yaml
x1:  # verify_identity 结果
  user_name: 张三
  user_id: U001
  status: success
```

---

### 机会 C：对话历史格式优化 ⭐ 中等价值

**当前格式**：
```
user: 我想查账户余额
assistant: 好的，请先完成身份验证
```

**Markdown 格式（与论文建议一致）**：
```markdown
**用户**：我想查账户余额
**助手**：好的，请先完成身份验证
```

或使用 Markdown 列表：
```markdown
- 👤 用户：我想查账户余额
- 🤖 助手：好的，请先完成身份验证
```

**理由**：Markdown 格式在大多数 LLM 的训练数据中频繁出现，多文件/多轮对话导航时表现更好。

---

### 机会 D：A/B 测试不同格式对 AP 准确率的影响 ⭐⭐ 高价值

**McMillan 等的研究方法论**最重要的贡献是提供了**可重复的实验框架**。ContextMind 可以借鉴这个实验设计，对自己的系统做格式 A/B 测试：

```python
# contextmind/evaluation/format_experiment.py（新增）

class ContextFormatExperiment:
    """
    对不同 prior_dataflow 格式进行 A/B 测试。
    参考 McMillan 等的实验设计。
    """
    
    formats = ["current_custom", "yaml", "json", "toon"]
    
    def run_experiment(
        self,
        test_dialogues: List[Dialogue],
        metrics: List[str] = ["api_call_accuracy", "none_rate", "token_count"],
    ) -> ExperimentReport:
        """
        对每种格式跑相同的测试对话，收集评估指标。
        """
        results = {}
        for fmt in self.formats:
            results[fmt] = self._run_with_format(test_dialogues, fmt)
        return ExperimentReport(results=results)
```

---

## 四、精准架构映射

```
McMillan 等研究                    ContextMind 对应层
──────────────────────────────────────────────────────────────
多文件导航任务                  →   多轮对话 + 多 API 调用链
Schema 准确性任务               →   schema_builder PyTOD 代码生成
YAML 格式推荐（Schema 任务）     →   schema_builder prompt 格式（改进：机会 A）
Markdown 格式推荐（导航任务）    →   对话历史格式（改进：机会 C）
TOON 格式（token 效率）          →   prior_dataflow 格式（改进：机会 B）
JSON 格式（精确查找）            →   API 返回值格式（当前适合）
实验框架（9649次）              →   ContextFormatExperiment（新增：机会 D）
11 个模型对比                   →   ContextMind 支持的多 LLM 对比
```

---

## 五、综合评估

| 机会 | 数据格式 | 目标 | 难度 | 优先级 |
|------|---------|------|------|-------|
| **A** Schema 注入改为 YAML | YAML | 提升代码生成准确率 | ⭐ | 🥇 P1 |
| **B** prior_dataflow 改为 TOON | TOON | 减少 token 消耗 | ⭐⭐ | 🥇 P1 |
| **C** 对话历史改为 Markdown | Markdown | 提升导航准确率 | ⭐ | 🥈 P2 |
| **D** 格式 A/B 测试框架 | 所有格式 | 数据驱动格式选择 | ⭐⭐ | 🥈 P2 |

---

## 六、对 ContextMind 的核心洞察

**McMillan 等最重要的贡献**是**实证数据**，而非理论框架：

> **数据格式不是细节问题，而是对 LLM 准确率有显著影响的核心变量。**

具体对 ContextMind 的指导：

1. **schema_builder 的 Schema 注入应改为 YAML**：这是最直接的低风险改进，YAML 在 Schema 任务上的优势显著
2. **prior_dataflow 的 JSON 格式是次优选择**：切换为 TOON 或 YAML 可节省 40-55% 的 token
3. **格式选择需要与具体 LLM 匹配**：Claude 和 GPT-4o 对格式的偏好不同，理想情况下应按模型动态选择

---

## 七、重要注意事项

| 注意事项 | 描述 | 影响 |
|---------|------|------|
| **TOON 是非标准格式** | 不同 LLM 对 TOON 理解差异大 | 需要先测试目标 LLM 的 TOON 理解能力 |
| **格式切换需要回归测试** | 改变数据格式可能影响现有测试 | 必须在 benchmark 上验证不退化 |
| **模型差异大** | 11 个模型中没有一种格式全胜 | 需要针对 ContextMind 实际使用的模型测试 |

---

## 八、不适合直接移植的部分

| 组件 | 原因 | 说明 |
|------|------|------|
| **TOON 格式（全面推广）** | 非标准，风险高 | 先在 prior_dataflow 单个组件试点 |
| **9649 次完整实验** | 成本高 | 针对核心场景做 100-200 次定向测试 |
| **文件系统导航专项优化** | ContextMind 的"文件"是对话，非实际文件 | 核心原则可用，具体任务不同 |

---

## 九、结论

McMillan 等的实证研究为 ContextMind 提供了**格式选择的数据依据**。最直接的改进是：

1. **机会 A**（schema_builder 的 Schema 注入改为 YAML）：一行代码改变，潜在准确率提升
2. **机会 B**（prior_dataflow 改为 TOON）：token 节省 40-55%，成本降低

这两个改进应该先通过 `τ-Knowledge` benchmark 验证，确认改进后再部署到生产环境。
