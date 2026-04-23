# 配置指南

本文档详细说明 ContextMind 的各种配置选项。

## 环境变量配置

### LLM API 配置

ContextMind 支持多种 LLM 提供商，通过环境变量进行配置。

#### Qwen API（推荐）

```bash
# .env 文件
QWEN3_API_KEY=your_qwen_api_key
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus
```

**模型选择：**
- `qwen-turbo` - 快速，成本低
- `qwen-plus` - 平衡性能和成本（推荐）
- `qwen-max` - 最强性能

#### OpenAI API

```bash
# .env 文件
OPENAI_API_KEY=your_openai_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo
```

**模型选择：**
- `gpt-3.5-turbo` - 快速，成本低
- `gpt-4` - 高性能
- `gpt-4-turbo` - 平衡性能和成本

#### 其他兼容 OpenAI 格式的 API

```bash
# Claude (通过第三方代理)
OPENAI_API_KEY=your_claude_key
OPENAI_BASE_URL=https://your-claude-proxy.com/v1
OPENAI_MODEL=claude-3-sonnet

# 本地部署的模型
OPENAI_API_KEY=not-needed
OPENAI_BASE_URL=http://localhost:8000/v1
OPENAI_MODEL=local-model
```

### 日志配置

```bash
# 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO
```

## 程序化配置

### 自定义 LLM 客户端

```python
from contextmind.infra.llm_client import AdkLLMClient

# 方式1：从 .env 自动加载配置（推荐）
client = AdkLLMClient()

# 方式2：显式传入配置
from contextmind.infra.llm_client import LLMConfig
client = AdkLLMClient(
    config=LLMConfig(
        api_key="your_key",
        base_url="https://api.example.com/v1",
        model="model-name",
        temperature=0.7,     # 温度参数（默认 0.3）
        max_tokens=2000,     # 最大生成 token 数（默认 4096）
    )
)
```

### DST 模式配置

```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

llm_client = AdkLLMClient()
config = get_chat_scenario()

tracker = DialogueStateTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config
)

# 配置历史管理
tracker.max_history_turns = 10  # 保留最近10轮对话
tracker.enable_history_summary = True  # 启用历史摘要
tracker.use_llm_summary = False  # 使用模板摘要（不使用LLM）
```

**参数说明：**
- `max_history_turns`: 保留的完整对话轮数（默认：10）
- `enable_history_summary`: 是否启用历史摘要（默认：True）
- `use_llm_summary`: 是否使用 LLM 生成摘要（默认：False）

### FnCTOD 模式配置

```python
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_insurance_scenario

llm_client = AdkLLMClient()
config = get_insurance_scenario()

tracker = FnCTODTracker.from_scenario(
    llm_client=llm_client,
    scenario_config=config,
)
```

### SchemaDataBuilder 配置（第二步，PyTOD 可选）

```python
from contextmind.schema_builder import SchemaDataBuilder
from contextmind.infra.llm_client import AdkLLMClient

llm_client = AdkLLMClient()

builder = SchemaDataBuilder(
    llm_client=llm_client,
    schema_path="output/schema.json",         # 第一步输出的 schema 文件
    test_data_paths=[                          # 可选：真实业务数据，提升生成质量
        "resources/data/chat_test_100.json"
    ],
)

# 生成 PyTOD API 代码文件
result = builder.build_pytod_apis(
    output_path="output/my_pytod_apis.py",
    max_iterations=3,             # 最大优化迭代次数（默认：3）
    pass_rate_threshold=0.9,      # 验证通过率阈值（默认：0.9）
    max_test_cases_per_intent=5,  # 每意图最大测试用例数（默认：5）
    generate_report=False,        # 是否生成验证报告（默认：False）
)
```

**参数说明：**
- `schema_path`: 第一步 `KnowledgeBaseBuilder.save()` 输出的 `schema.json` 路径
- `test_data_paths`: 真实业务数据文件列表，用于构建测试用例（可选）
- `max_iterations`: 函数迭代优化的最大轮数（默认：3）
- `pass_rate_threshold`: 函数验证通过率阈值，低于此值触发重新生成（默认：0.9）
- `generate_report`: 是否生成 `validation_report.json`（默认：False）

> **注意**：此步骤仅适用于 **PyTOD** 算法；DST、FnCTOD、Evolve 不需要此步骤。

### Evolve 模式配置

```python
from contextmind.modes.evolve.core.engine import EvolveEngine
from contextmind.infra.llm_client import AdkLLMClient

llm_client = AdkLLMClient()

engine = EvolveEngine(
    app_name="my_app",
    user_id="user_001",
    llm_client=llm_client,
    max_recent_events=9999,   # 会话历史保留上限
    use_summarizer=False,     # 是否启用对话摘要器
    extraction_method="llm",  # 知识提取方式
)
```

## 场景配置

### 使用预定义场景

```python
from contextmind.scenarios import (
    get_chat_scenario,
    get_callcenter_scenario,
    get_insurance_scenario
)

# 闲聊场景
chat_config = get_chat_scenario()

# 客服场景
callcenter_config = get_callcenter_scenario()

# 保险场景
insurance_config = get_insurance_scenario()
```

### 自定义场景

```python
from contextmind.scenarios.base import ScenarioConfig, ScenarioType

custom_config = ScenarioConfig(
    name="custom",
    scenario_type=ScenarioType.CHAT,
    description="自定义场景",
    system_prompt="你是一个专业的助手",
    
    # DST 槽位定义
    dst_slots={
        "user_name": "用户姓名",
        "user_phone": "用户电话",
        "intent": "用户意图"
    },
    
    # 分类槽位（枚举值）
    dst_categorical_slots={
        "intent": ["查询", "预订", "投诉", "其他"]
    },
    
    # 意图定义
    dst_intents={
        "查询": ["产品查询", "价格查询", "库存查询"],
        "预订": ["预订服务", "预订产品"],
        "投诉": ["服务投诉", "产品投诉"],
        "其他": ["闲聊", "其他"]
    }
)
```

## 高级配置

### 性能优化

```python
# 减少延迟：使用更快的模型（通过 .env 配置 QWEN3_MODEL=qwen-turbo）
client = AdkLLMClient()

# 减少上下文长度
tracker.max_history_turns = 5

# 提高质量：使用更强模型，降低随机性
from contextmind.infra.llm_client import LLMConfig
client = AdkLLMClient(
    config=LLMConfig(model="qwen-max", temperature=0.3)
)
tracker.max_history_turns = 20  # 增加上下文
```

### 日志配置

```python
from contextmind.infra.logger import get_logger, setup_logger
import logging

# 全局日志级别
setup_logger(level=logging.DEBUG)

# 模块日志级别
logger = get_logger(__name__)
logger.setLevel(logging.INFO)

# 自定义日志格式
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
```

### 错误处理

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker

async def safe_process(tracker, user_input):
    try:
        result = await tracker.process_turn(user_input)
        return result
    except ValueError as e:
        print(f"参数错误: {e}")
        return None
    except TimeoutError as e:
        print(f"超时错误: {e}")
        return None
    except Exception as e:
        print(f"未知错误: {e}")
        return None
```

## 配置文件示例

### 完整的 .env 文件

```bash
# LLM 配置
QWEN3_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus

# 备用 LLM（可选）
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# 日志配置
LOG_LEVEL=INFO
```

## 环境变量优先级

配置的加载顺序（优先级从高到低）：

1. 代码中直接指定的参数
2. 环境变量
3. .env 文件
4. 默认值

**示例：**
```python
# 1. 代码中指定（优先级最高）
from contextmind.infra.llm_client import LLMConfig
client = AdkLLMClient(config=LLMConfig(model="qwen-max"))

# 2. 环境变量
os.environ['QWEN3_MODEL'] = "qwen-plus"

# 3. .env 文件
QWEN3_MODEL=qwen-turbo

# 4. 默认值（优先级最低）
default_model = "qwen-plus"
```

## 配置验证

### 验证环境变量

```python
import os
from dotenv import load_dotenv

load_dotenv()

required_vars = ['QWEN3_API_KEY', 'QWEN3_BASE_URL', 'QWEN3_MODEL']

for var in required_vars:
    value = os.getenv(var)
    if value:
        print(f"✓ {var}: {value[:20]}...")
    else:
        print(f"✗ {var}: 未设置")
```

### 验证 LLM 连接

```python
import asyncio
from contextmind.infra.llm_client import AdkLLMClient

async def test_connection():
    try:
        client = AdkLLMClient()
        response = await client.chat_async([
            {"role": "user", "content": "Hello"}
        ])
        print(f"✓ LLM 连接成功")
        print(f"响应: {response[:50]}...")
        return True
    except Exception as e:
        print(f"✗ LLM 连接失败: {e}")
        return False

asyncio.run(test_connection())
```

## 常见配置场景

### 开发环境

```bash
# .env.development
LOG_LEVEL=DEBUG
QWEN3_MODEL=qwen-turbo  # 快速模型，降低成本
```

### 生产环境

```bash
# .env.production
LOG_LEVEL=INFO
QWEN3_MODEL=qwen-plus  # 平衡性能
```

### 测试环境

```bash
# .env.test
LOG_LEVEL=WARNING
QWEN3_MODEL=qwen-turbo
```

---

## 扩展新场景

ContextMind v0.3.0+ 使用 **配置文件驱动** 的场景管理机制。所有场景在 `scenarios.yaml` 中定义，无需修改核心代码。新场景可根据算法选择灵活使用三步框架：

### 添加新场景（三步框架）

**框架第一步（可选）**：从真实业务对话构建知识库

```python
from contextmind.knowledge import KnowledgeBaseBuilder
from contextmind.infra.llm_client import AdkLLMClient

builder = KnowledgeBaseBuilder(
    scene_name="医疗咨询",
    scene_description="医疗问诊场景",
    llm_client=AdkLLMClient(),
)
schema_dict = builder.build(my_medical_dialogues)
builder.save(schema_dict, "resources/schemas/medical.json")
```

**框架第二步（PyTOD 可选）**：生成算法专用 API 代码

```python
from contextmind.schema_builder import SchemaDataBuilder

schema_builder = SchemaDataBuilder(
    llm_client=AdkLLMClient(),
    schema_path="resources/schemas/medical.json",
)
schema_builder.build_pytod_apis(output_path="output/medical_apis.py")
```

**框架第三步**：在 `scenarios.yaml` 中注册场景并执行

在 `scenarios.yaml` 中注册场景：

```yaml
scenes:
  - name: 医疗咨询
    description: 医疗问诊场景
    schema_path: resources/schemas/medical.json
    mode: pytod
```

注册 API 并执行：

```python
from contextmind import ContextPipeline
from contextmind.infra.llm_client import AdkLLMClient

pipeline = ContextPipeline(llm_client=AdkLLMClient())
pipeline.set_schema(schema_dict)  # 从第一步输出加载

# 手写 API 或加载第二步生成的 API
pipeline.register_api("query_symptoms", query_symptoms_fn)

result = await pipeline.process_turn("我最近头疼，该怎么办？")
```

### 场景 Schema 格式

```json
{
  "scene_name": "医疗咨询",
  "intents": [
    {
      "intent": "query_symptoms",
      "description": "查询症状",
      "required_slots": ["symptom"],
      "optional_slots": ["duration"],
      "result_slots": ["diagnosis", "recommendation"]
    }
  ]
}
```

---

## 相关文档

- [快速开始](quick-start.md)
- [API 参考](../reference/api-reference.md)
- [故障排查](troubleshooting.md)

---

**最后更新**: 2026-03-31 | **版本**: 0.3.0
