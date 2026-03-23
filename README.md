# ContextMind

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.3.0-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

**ContextMind** 是一个通用的、高质量的**上下文工程（Context Engineering）**框架，整体设计分为两步：

**第一步：建立知识库**（`contextmind.kb`）——针对任意数据集，通过 LLM 自动发现槽位和意图，合成标准 SGD 格式 `schema.json`。

**第二步：执行**（`contextmind.pipeline` / `contextmind.modes.*`）——基于知识库，在对话中提取有效的上下文，提升对话质量。

推荐使用 **`ContextPipeline`** 作为统一入口——将两步无缝整合，3 行代码完成端到端上下文工程。

---

## 核心特性

- 🚀 **统一流水线** - `ContextPipeline` 一键整合知识库构建 + 对话上下文提取
- 🗄️ **通用知识库构建** - 任意对话数据集 → SGD `schema.json`（两阶段 LLM 抽取+合成）
- 🎯 **四种执行模式** - DST（状态追踪）/ FnCTOD（函数调用）/ Evolve（记忆进化）/ PyTOD（程序执行）
- 🔌 **模型无关** - 适配任何 LLM API（OpenAI、Qwen、Claude 等）
- 🧠 **智能记忆** - 自动知识提取和语义检索（Evolve 模式）
- ⚡ **即插即用** - 可安装包，模块化设计

---

## 快速开始

### 安装

```bash
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind
pip install -r requirements.txt
```

### 配置

创建 `.env` 文件配置 LLM API：

```bash
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus
```

### 最简用法（推荐）

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

pipeline = ContextPipeline(llm_client=AdkLLMClient())

# Phase 1: 从原始对话构建知识库
pipeline.build_kb(dialogues=my_dialogues, scene_name="银行贷款外呼")

# Phase 2: 对话上下文提取
async def chat():
    result = await pipeline.process_turn("我想查询贷款额度")
    print(result["response"])      # 系统回复
    print(result["context"])       # 本轮提取的上下文（槽位、意图）
    print(result["cumulative_context"])  # 累积的全量上下文

asyncio.run(chat())
```

运行演示：

```bash
python examples/context_pipeline_demo.py
```

---

## 两步框架详解

### 第一步：建立知识库

`KnowledgeBaseBuilder` 接受任意格式的对话数据，经过两阶段 LLM 处理，生成标准 SGD `schema.json`：

```python
from contextmind.kb import KnowledgeBaseBuilder

# 支持 chat_test / SGD / 文本列表 / 平铺文本等多种输入格式
dialogues = [
    "坐席：你好，请问是李先生吗？\n用户：是的。\n坐席：您有 5 万元可用额度。",
    ["agent: Hello, is this Mr. Wang?", "user: Yes.", "agent: You have a 30k credit."],
]

builder = KnowledgeBaseBuilder(
    scene_name="银行贷款外呼",
    scene_description="银行客服主动致电老客户推介个人贷款产品",
)
schema_dict = builder.build(dialogues)       # Phase 1: 发现+合成 → schema dict
builder.save(schema_dict, "output/schema.json")
```

命令行方式：

```bash
python examples/build_kb_demo.py --demo
# 或使用真实数据
python examples/build_kb_demo.py \
    --data resources/data/chat_test_100.json \
    --num 10 \
    --scene "安逸花外呼" \
    --output data/my_kb/schema.json
```

### 第二步：执行

**推荐方式：使用 `ContextPipeline`（统一接口）**

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

pipeline = ContextPipeline(
    llm_client=AdkLLMClient(),
    mode="pytod",          # 执行模式：pytod（默认）或 dst
    scene_name="银行贷款外呼",
)

# 从已保存的 schema.json 加载
pipeline.load_kb("output/schema.json")

# 或从 Phase 1 的 schema dict 直接加载
# pipeline.set_schema(schema_dict)

# 注册业务 API（可选，pytod 模式）
@pipeline.register_api("verify_identity")
def verify_identity(customer_name: str) -> dict:
    return {"verified": True, "customer_name": customer_name}

async def main():
    result = await pipeline.process_turn("我是李明，想查询我的贷款额度")
    print(result["response"])            # 系统回复
    print(result["context"])             # 本轮提取的上下文
    print(result["cumulative_context"])  # 全量累积上下文

asyncio.run(main())
```

**底层方式：直接使用 `AdkPyTODTracker`（高级用法）**

```python
import asyncio
from contextmind.kb import KnowledgeBaseBuilder
from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
from contextmind.infra.llm_client import AdkLLMClient

# 从 Phase 1 生成的 schema.json 加载 ServiceSchema（Phase 1→2 桥接）
service_schema = KnowledgeBaseBuilder.load_schema("output/schema.json")
# 也可以直接从 build() 结果转换
# service_schema = KnowledgeBaseBuilder.to_service_schema(schema_dict)

llm = AdkLLMClient()
engine = ExecutionEngine()

@engine.register("verify_identity")
def verify_identity(customer_name: str) -> dict:
    return {"verified": True, "customer_name": customer_name}

tracker = AdkPyTODTracker(llm_client=llm, engine=engine, schema=service_schema)

async def main():
    result = await tracker.process_turn("我是李明，想查询我的贷款额度")
    print(result["response"])

asyncio.run(main())
```

---

## 四种执行模式

### 1. **DST 模式**（对话状态追踪）

从对话中提取结构化信息（槽位-值对）。

```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient

tracker = DialogueStateTracker.from_scenario(
    llm_client=AdkLLMClient(),
    scenario_config=get_callcenter_scenario()
)
state = await tracker.process_turn("我要订明天去北京的票")
```

### 2. **FnCTOD 模式**（函数调用）

基于 Meta AI FnCTOD 论文，将 DST 转化为函数调用。

```python
from contextmind.modes.fnctod import FnCTODTracker

tracker = FnCTODTracker.from_scenario(
    llm_client=AdkLLMClient(),
    scenario_config=get_insurance_scenario()
)
result = await tracker.process_turn("我想买重疾险")
```

### 3. **PyTOD 模式**（可编程任务型对话）

基于 Apple 研究院 PyTOD 论文，将对话建模为程序执行问题。

```python
from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine

engine = ExecutionEngine()
# 注册 API…
tracker = AdkPyTODTracker(llm_client=AdkLLMClient(), engine=engine, schema=service_schema)
result = await tracker.process_turn("查一下我的账户余额")
print(result["program_text"])  # x1 query_balance()
print(result["response"])      # 您的可用余额为…
```

### 4. **Evolve 模式**（演化式上下文）

基于 AlphaEvolve/ThetaEvolve 算法的高级对话管理，支持长对话记忆。

```python
from contextmind.modes.evolve import create_app_for_scenario

app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=AdkLLMClient(),
    scenario_config=get_chat_scenario()
)
response = await app.process_turn("你好，记住我叫张三")
```

---

## 项目结构

```
ContextMind/
├── contextmind/               # 核心包
│   ├── pipeline.py           # 🚀 ContextPipeline（统一上下文工程流水线）
│   ├── kb/                   # 通用知识库构建（Phase 1）
│   │   ├── builder.py        #   KnowledgeBaseBuilder（发现+合成）
│   │   │                     #   + to_service_schema() / load_schema() 桥接方法
│   │   │                     #   + build_async() / build_dataset_async() 异步方法
│   │   ├── discoverer.py     #   GenericDialogueDiscoverer（LLM开放式发现+溯源）
│   │   ├── synthesizer.py    #   SchemaSynthesizer（LLM合成 SGD schema）
│   │   └── normalizer.py     #   多格式对话归一化（4种输入格式）
│   ├── infra/                # 基础设施（LLM 客户端、日志、嵌入向量等）
│   ├── modes/                # 四种执行模式（Phase 2）
│   │   ├── base.py          #   BaseTracker 协议
│   │   ├── dst/             #   对话状态追踪（槽位提取）
│   │   ├── fnctod/          #   函数调用式对话（ADK 原生）
│   │   ├── evolve/          #   演化式上下文（长对话记忆）
│   │   └── pytod/           #   可编程任务型对话（AP→EE→DM）
│   │       ├── tracker.py   #     AdkPyTODTracker
│   │       ├── schemas.py   #     ServiceSchema / SlotDefinition / IntentDefinition
│   │       └── execution_engine.py  # ExecutionEngine
│   ├── scenarios/            # 场景配置与注册
│   └── ui/                  # UI 组件（Gradio）
├── data/                     # 运行时输出
├── examples/                 # 示例程序
│   ├── context_pipeline_demo.py  # 🚀 ContextPipeline 端到端演示
│   ├── build_kb_demo.py         #   Phase 1 演示：任意数据 → schema.json
│   └── pytod_trace_demo.py      #   Phase 2 演示：schema.json + API → 对话
├── benchmark/                # 评测框架
├── resources/                # 静态资源与测试数据
└── docs/                     # 文档
```

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 致谢

- PyTOD 模式基于 Apple 研究院论文 "Task-Oriented Dialogue as Dataflow Synthesis"
- FnCTOD 模式基于 Meta AI 的论文实现
- Evolve 模式采用 AlphaEvolve 和 ThetaEvolve 算法

---

**开发者**: [Jasmine66Bloom](https://github.com/Jasmine66Bloom)  
**项目主页**: https://github.com/Jasmine66Bloom/ContextMind

