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

# 可选：设置超时时间（秒）
QWEN3_TIMEOUT=60

# 可选：设置最大重试次数
QWEN3_MAX_RETRIES=3
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

# 可选配置
OPENAI_TIMEOUT=60
OPENAI_MAX_RETRIES=3
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

# 日志文件路径
LOG_FILE=logs/contextmind.log

# 是否启用彩色日志
LOG_COLOR=True
```

### 其他配置

```bash
# 是否启用调试模式
DEBUG=False

# 默认场景
DEFAULT_SCENARIO=chat

# 默认模式
DEFAULT_MODE=dst
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
    use_two_stage=True  # 启用两阶段处理
)

# 配置历史管理
tracker.max_history_turns = 10
```

**参数说明：**
- `use_two_stage`: 是否使用两阶段处理（先选择domain，再调用函数）

### Evolve 模式配置

```python
from contextmind.modes.evolve import EvolveEngine
from contextmind.infra.llm_client import AdkLLMClient

llm_client = AdkLLMClient()

engine = EvolveEngine(
    app_name="my_app",
    user_id="user_001",
    llm_client=llm_client,
    system_prompt="你是一个友好的助手",
    
    # 记忆配置
    enable_memory=True,  # 启用记忆系统
    memory_limit=50,  # 记忆库大小限制
    
    # 进化配置
    enable_evolution=True,  # 启用进化学习
    evolution_interval=10,  # 每10轮触发一次进化
    
    # 上下文配置
    max_context_length=4000,  # 最大上下文长度
    enable_compression=True,  # 启用上下文压缩
    
    # 检索配置
    retrieval_top_k=5,  # 检索前5条最相关记忆
    retrieval_threshold=0.6  # 相关性阈值
)
```

**参数说明：**
- `enable_memory`: 是否启用长期记忆（默认：True）
- `memory_limit`: 记忆库最大条目数（默认：50）
- `enable_evolution`: 是否启用进化学习（默认：True）
- `evolution_interval`: 进化触发间隔（轮数）（默认：10）

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
from contextmind.scenarios.config import ScenarioConfig, ScenarioType

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

# 减少成本
tracker.max_history_turns = 5  # 减少历史轮数
tracker.use_llm_summary = False  # 不使用 LLM 摘要
engine.memory_limit = 20  # 减少记忆库大小

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
QWEN3_TIMEOUT=60
QWEN3_MAX_RETRIES=3

# 备用 LLM（可选）
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-3.5-turbo

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/contextmind.log
LOG_COLOR=True

# 应用配置
DEBUG=False
DEFAULT_SCENARIO=chat
DEFAULT_MODE=dst

# 性能配置（可选）
MAX_HISTORY_TURNS=10
MEMORY_LIMIT=50
ENABLE_MEMORY=True
ENABLE_EVOLUTION=True
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
DEBUG=True
QWEN3_MODEL=qwen-turbo  # 快速模型，降低成本
MAX_HISTORY_TURNS=5
```

### 生产环境

```bash
# .env.production
LOG_LEVEL=INFO
DEBUG=False
QWEN3_MODEL=qwen-plus  # 平衡性能
MAX_HISTORY_TURNS=10
ENABLE_MEMORY=True
ENABLE_EVOLUTION=True
```

### 测试环境

```bash
# .env.test
LOG_LEVEL=WARNING
DEBUG=False
QWEN3_MODEL=qwen-turbo
MAX_HISTORY_TURNS=3
ENABLE_MEMORY=False
ENABLE_EVOLUTION=False
```

## 相关文档

- [快速开始](quick-start.md)
- [API 参考](api-reference.md)
- [故障排查](troubleshooting.md)

---

**最后更新**: 2026-03-30 | **版本**: 0.3.0
