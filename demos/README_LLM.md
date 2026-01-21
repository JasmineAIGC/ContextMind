# ContextMind v7.1 演示的 LLM 集成

## 概述

在 ContextMind v7.1 中，**LLM 调用在核心框架外部**。这意味着:
- ContextMind 框架处理**上下文工程** (步骤 1-4 + 6)
- 您的应用负责**调用 LLM** (步骤 5)

为了演示目的，我们提供 `SimpleLLMClient` - 一个轻量级的 OpenAI 兼容客户端。

## 快速开始

### 1. 安装依赖

```bash
pip install openai python-dotenv
```

### 2. 配置 .env 文件

在项目根目录创建 `.env` 文件，包含您的 LLM 配置:

```env
# Qwen3 API 配置示例
QWEN3_API_KEY=sk-your-api-key-here
QWEN3_BASE_URL=http://your-server:port/v1
QWEN3_MODEL=Qwen3-32B
QWEN3_MAX_TOKENS=8192

# 或使用通用的 LLM_ 前缀以保持兼容性
LLM_API_KEY=sk-your-api-key-here
LLM_BASE_URL=http://your-server:port/v1
LLM_MODEL=Qwen3-32B
```

### 3. 运行演示

```bash
# 使用真实 LLM (默认)
python interactive_demo.py

# 使用模拟回复 (无需 LLM 进行测试)
python interactive_demo.py --no-llm

# 使用详细日志
python interactive_demo.py --detailed

# 使用调试日志
python interactive_demo.py --debug
```

## 支持的 LLM 提供商

该客户端支持任何 OpenAI 兼容的 API:

- **Qwen** (阿里云)
- **DeepSeek**
- **OpenAI**
- **vLLM** (自托管)
- **LocalAI**
- **Ollama** (具有 OpenAI 兼容性)
- 以及更多...

## 环境变量

客户端按顺序检查这些变量:

### API Key (必需)
- `QWEN3_API_KEY`
- `CONTEXTMIND_API_KEY`
- `LLM_API_KEY`
- `OPENAI_API_KEY`
- `DEEPSEEK_API_KEY`

### Base URL (可选)
- `QWEN3_BASE_URL`
- `CONTEXTMIND_BASE_URL`
- `LLM_BASE_URL`
- `OPENAI_BASE_URL`
- `DEEPSEEK_BASE_URL`

### Model Name (可选, 默认: Qwen3-32B)
- `QWEN3_MODEL`
- `LLM_MODEL`
- `OPENAI_MODEL`

### 其他参数
- `LLM_TEMPERATURE` (默认: 0.6)
- `LLM_MAX_TOKENS` (默认: 8192)
- `LLM_TOP_K` (默认: 20)
- `LLM_ACCESS_KEY` (某些网关需要)

## 在您的应用中使用

```python
from demos.llm_client import SimpleLLMClient, LLMConfig

# 选项 1: 从 .env 加载 (推荐)
llm_client = SimpleLLMClient()

# 选项 2: 手动配置
config = LLMConfig(
    api_key="sk-your-key",
    base_url="http://your-server:port/v1",
    model="Qwen3-32B",
    temperature=0.6,
    max_tokens=8192
)
llm_client = SimpleLLMClient(config)

# 生成回复
reasoning, response = llm_client.generate(prompt)
# 或异步版本
reasoning, response = await llm_client.generate_async(prompt)
```

## 与 ContextMind 集成

演示应用展示了完整的工作流程:

```python
from contextmind import ContextEngine
from demos.callcenter_app import CallCenterApplication

# 1. 创建 ContextMind 引擎 (上下文工程)
engine = ContextEngine(app_name="my-app", user_id="user123")

# 2. 使用 LLM 客户端创建应用
app = CallCenterApplication(
    context_engine=engine,
    use_real_llm=True  # 启用真实 LLM (默认)
)

# 3. 处理用户输入
response = await app.process_turn("Hello!")
# 内部流程:
#   - ContextEngine 优化上下文 (步骤 1-4)
#   - SimpleLLMClient 调用 LLM (步骤 5)
#   - ContextEngine 后处理输出 (步骤 6)
```

## 架构说明

- **ContextMind 框架**: 纯上下文工程 (无 LLM 依赖)
- **演示应用**: 展示如何集成 LLM 调用
- **SimpleLLMClient**: 轻量级演示客户端 (生产环境请考虑使用自己的实现)

这种分离确保了:
✅ ContextMind 适用于任何 LLM 提供商
✅ 您控制 LLM 选择和配置
✅ 无需更改框架即可轻松切换或升级 LLM

## 故障排除

### "Missing API key" 错误
确保 `.env` 文件存在并包含 `LLM_API_KEY` 或支持的变体之一。

### 连接错误
检查 `LLM_BASE_URL` 是否指向有效的 OpenAI 兼容端点。

### 导入错误
安装所需的包: `pip install openai`

### 不使用真实 LLM
对于无需 LLM 访问的测试:
```bash
python interactive_demo.py --no-llm
```

这将使用模拟回复而不是调用真实的 LLM。
