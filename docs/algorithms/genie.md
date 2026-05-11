# Genie 模式（声明式策略驱动对话）

## 概述

**Genie**（GenieWorksheets，声明式策略驱动的任务型对话）是 ContextMind 中已实现的第五种执行模式。该算法将对话业务策略完全声明化：业务规则写在 Worksheet 表单中，由确定性状态机（PolicyExecutor）驱动对话流程，LLM 仅负责语义解析和自然语言回复生成，不参与任何控制流决策。

- **实现状态**: ✅ 已实现
- **官方源码**: https://github.com/stanford-oval/worksheets
- **论文**: [Coding Reliable LLM-based Integrated Task and Knowledge Agents with GenieWorksheets](https://arxiv.org/abs/2407.05674)（ACL 2025）

### 三步框架依赖

| 步骤 | 是否需要 | 说明 |
|------|:-------:|------|
| **① 建立知识库** | ✅ 可选 | 可从原始对话自动生成 Worksheet 字段定义 |
| **② Schema 数据生成** | ❌ 不需要 | Genie 不需要生成额外的算法专用代码文件 |
| **③ 算法执行（Genie）** | ✅ 必须 | 六步 Worksheet 状态机流程 |

Genie 可直接使用手写的 Worksheet（CSV 或 JSON 格式）进入第三步执行，也可利用第一步从原始对话自动发现字段定义。

---

## 核心思想

Genie 的创新在于将**对话控制流与 LLM 语义理解彻底分离**：

```
传统提示词工程：
  用户输入 → LLM（同时负责：理解 + 策略决策 + 回复） → 输出
  → 问题：LLM 可能偏离预设策略，行为不可预测

Genie 流程：
  用户输入
    ↓
  SemanticParser（LLM-1）
    → 仅做语义理解，提取字段值
    ↓
  PolicyExecutor（确定性状态机，无 LLM）
    → 按 Worksheet 声明决定下一步动作
    ↓
  ResponseGenerator（LLM-2）
    → 仅做自然语言生成
    ↓
  系统输出
```

**核心优势**：业务策略由声明式 Worksheet 控制，行为完全可预期、可审计，解决了 LLM 对话控制流不可控的根本问题。

---

## 与其他模式的对比

| 维度 | DST | FnCTOD | Genie |
|------|-----|--------|-------|
| **策略控制** | LLM 决策 | LLM 决策 | 确定性状态机 |
| **业务规则定义** | 嵌入提示词 | Schema 参数 | Worksheet 表格 |
| **可预测性** | 低 | 中 | 高（完全确定性） |
| **业务人员可维护** | 需懂提示词 | 需懂 Schema | 仅需维护 CSV 表格 |
| **API 触发** | 手动判断 | 手动判断 | on_success 声明式绑定 |
| **LLM 调用次数** | 1 次/轮 | 1-2 次/轮 | 2 次/轮（解析+生成） |

---

## 算法架构

Genie 包含以下核心组件：

### 1. PolicyExecutor（确定性状态机）

**纯 Python 实现，不调用任何 LLM**，负责：
- 管理 Worksheet 字段的填写状态（EMPTY / FILLED / PENDING_CONFIRM / CONFIRMED）
- 按 Worksheet 声明顺序决定下一个需要填写的字段
- 计算本轮 AgentActs（Ask / Confirm / Report）
- 校验枚举值合法性

### 2. SemanticParser（LLM-1，语义理解）

调用 LLM 从用户话语中提取字段赋值，输出 JSON 格式：

```json
{"user_name": "张三", "phone": "138xxxx5678"}
```

提示词包含当前 Worksheet 状态、对话历史和业务场景描述，使 LLM 聚焦于语义理解，不参与策略决策。

### 3. ResponseGenerator（LLM-2，自然语言生成）

将 AgentActs 列表（Ask / Confirm / Report）转换为自然、流畅的回复。业务场景背景通过 `scene_description` 注入提示词。

### 4. GenieTracker（流程协调器）

协调六步执行流程，对外暴露统一的 `process_turn()` 接口。

---

## 六步执行流程

```
用户话语
    ↓
Step 1: 意图路由（多意图时调用 LLM，单意图跳过）
    ↓
Step 2: 语义解析（LLM-1）
        SemanticParser → {field: value, ...}
    ↓
Step 3: Worksheet 状态更新
        3a. 处理待确认字段（yes/no 检测）
        3b. executor.fill_batch(extracted)
    ↓
Step 4: on_success API 分发
        当字段完成且配置了 on_success 时，调用注册 API
    ↓
Step 5: AgentActs 计算（确定性规则）
        Ask / Confirm / Report
    ↓
Step 6: 回复生成（LLM-2）
        自然语言回复

return {"response", "worksheet_state", "is_complete", "agent_acts"}
```

---

## Worksheet 格式

Genie 支持两种 Worksheet 格式：

### CSV 格式（业务人员友好）

```csv
field_name,description,field_type,required,on_success,confirm_on_fill,enum_values
user_name,用户姓名,str,True,,,
phone,手机号,str,True,,,
loan_amount,贷款金额,float,False,,,
intent,借款意图,str,True,apply_loan,,审核通过|拒绝|待审核
```

### JSON 格式（程序化生成）

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

## ContextMind 中的实现

```
contextmind/modes/genie/
├── __init__.py           # 模块入口
├── tracker.py            # GenieTracker：六步流程协调器
├── policy_executor.py    # PolicyExecutor：确定性 Worksheet 状态机
├── semantic_parser.py    # SemanticParser：LLM-1 字段提取
├── agent_acts.py         # AgentActs 数据模型
└── prompts/
    ├── semantic_parsing.prompt    # LLM-1 提示词模板
    └── response_generator.prompt  # LLM-2 提示词模板
```

---

## 使用示例

### 基础用法

```python
from contextmind.modes.genie import GenieTracker
from contextmind.infra.llm_client import AdkLLMClient

tracker = GenieTracker.from_scenario(
    llm_client=AdkLLMClient(),
    scenario_config=get_anyihua_scenario()
)

# 外呼场景：从 scene_description 预填已知信息
await tracker.prefill()

result = await tracker.process_turn("我要申请贷款")
print(result["response"])
# 输出：您好，请问您的贷款金额是多少？
```

### 注册 on_success API

```python
tracker.register_api("check_credit", check_credit_func)
tracker.register_api("apply_loan", apply_loan_func)
```

### 查看 Worksheet 状态

```python
result = await tracker.process_turn("我叫张三")
state = result["worksheet_state"]
print(state["field_values"])   # {"user_name": "张三"}
print(state["field_statuses"]) # {"user_name": "filled", "phone": "empty"}
print(result["is_complete"])   # False
```

---

## 性能特点

### 优势

1. **策略可靠**：确定性 PolicyExecutor 保证业务策略严格执行
2. **行为可审计**：每轮 AgentActs 明确记录系统决策依据
3. **业务友好**：Worksheet 表格可由业务人员直接维护，无需提示词工程
4. **外呼支持**：Prefill 机制避免重复询问已知用户信息

### 适用场景

- ✅ 外呼营销（已知用户信息，主动发起对话）
- ✅ 业务流程严格的客服场景（贷款申请、保险咨询）
- ✅ 需要审计和合规的对话系统
- ✅ 多意图、多字段的复杂信息收集

### 局限性

- ❌ 灵活性低于纯 LLM 驱动的模式
- ❌ 需要提前定义 Worksheet 字段
- ❌ 开放域闲聊场景不适合（策略过于结构化）

---

## 参考资料

- [GenieWorksheets 论文：Coding Reliable LLM-based Integrated Task and Knowledge Agents with GenieWorksheets](https://arxiv.org/abs/2407.05674)（ACL 2025）
- [官方代码仓库](https://github.com/stanford-oval/worksheets)
- [Genie 算法分析](../research/genie_worksheets_analysis.md)
- [DST 算法文档](dst.md)
- [FnCTOD 算法文档](fnctod.md)
- [API 参考](../reference/api-reference.md)
