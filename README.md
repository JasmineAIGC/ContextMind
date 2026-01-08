# ContextMind 快速开始指南

欢迎使用 **ContextMind** —— 一个基于 Google ADK 的智能对话上下文管理框架！

## 📋 目录

- [项目简介](#项目简介)
- [核心特性](#核心特性)
- [快速开始](#快速开始)
- [使用示例](#使用示例)
- [API 文档](#api-文档)
- [常见问题](#常见问题)

---

## 🎯 项目简介

ContextMind 是一个专为多轮对话场景设计的上下文管理框架，它能够：

- 🧠 **智能记忆管理**: 自动管理短期和长期对话记忆
- 🔍 **语义检索**: 根据对话内容智能检索相关历史信息
- 🎨 **灵活配置**: 支持多种 LLM 提供商（Qwen、OpenAI、DeepSeek 等）
- 📊 **可视化演示**: 提供 Web UI 和 CLI 两种演示方式
- 🔧 **易于扩展**: 模块化设计，方便定制和扩展

### 应用场景

- ✅ 智能客服系统
- ✅ 个人助手应用
- ✅ 教育辅导机器人
- ✅ 企业内部知识问答
- ✅ 任何需要上下文记忆的对话系统

---

## ✨ 核心特性

### 1. 三层记忆架构

| 记忆层级 | 容量 | 生命周期 | 用途 |
|---------|------|----------|------|
| **即时上下文** | 单轮 | 单次请求 | 当前对话输入 |
| **短期记忆** | 6-50 轮 | 单次会话 | 最近对话历史 |
| **长期记忆** | 无限制 | 跨会话 | 重要事实和知识 |

### 2. 智能上下文整合

自动整合多种上下文信息：
- 📝 对话历史
- 👤 用户画像
- 📋 业务规则
- 🕐 时间上下文
- 🧠 长期记忆

### 3. 专业日志系统

- 🔵 基础对话引擎
- 🟡 短期记忆引擎  
- 🟢 长期记忆引擎
- 分级日志输出 (DEBUG/INFO/WARNING/ERROR)

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- pip 或 conda

### 2. 安装依赖

```bash
# 克隆项目
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

创建 `.env` 文件：

```bash
# LLM API 配置
QWEN3_API_KEY=your-api-key-here
QWEN3_BASE_URL=http://your-api-endpoint/v1
QWEN3_MODEL=Qwen3-32B
QWEN3_TEMPERATURE=0.6
QWEN3_MAX_TOKENS=8192
QWEN3_TOP_K=20
```

**支持的环境变量前缀**:
- `QWEN3_*` - Qwen 模型
- `OPENAI_*` - OpenAI 模型
- `DEEPSEEK_*` - DeepSeek 模型
- `LLM_*` - 通用 LLM 配置
- `CONTEXTMIND_*` - 项目专用配置

### 4. 运行演示

#### 方式 1: Web UI (推荐)

```bash
python gradio_demo.py
```

然后访问 `http://localhost:7860`

#### 方式 2: CLI 交互式

```bash
python interactive_demo.py
```

---

## 📖 使用示例

### 示例 1: 基本使用

```python
import asyncio
from contextmind import Client, ContextEngine

async def main():
    # 创建 LLM 客户端
    client = Client()
    
    # 创建上下文引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-001",
        llm_client=client,
        base_system_prompt="你是一个友好的助手。"
    )
    
    # 处理对话
    result = await engine.process_turn("你好，请介绍一下自己")
    print(f"机器人回复: {result.response}")
    
    # 继续对话（自动记住上下文）
    result = await engine.process_turn("我刚才问了什么？")
    print(f"机器人回复: {result.response}")

# 运行
asyncio.run(main())
```

### 示例 2: 带用户画像和业务规则

```python
from contextmind import Client, ContextEngine

async def create_customer_service_bot():
    client = Client()
    
    # 定义用户画像
    user_profile = {
        "姓名": "张三",
        "年龄": "30岁",
        "会员等级": "VIP",
        "历史购买": "已购买过3次"
    }
    
    # 定义业务规则
    business_rules = {
        "服务态度": "专业、礼貌、耐心",
        "回复要求": "简洁明了，一次性解决问题",
        "禁止事项": "不得泄露其他用户信息"
    }
    
    # 创建引擎
    engine = ContextEngine(
        app_name="customer-service",
        user_id="zhang-san",
        llm_client=client,
        base_system_prompt="你是一名专业的客服人员。",
        user_profile=user_profile,
        business_rules=business_rules,
        max_recent_events=10  # 保留最近10轮对话
    )
    
    return engine
```

### 示例 3: 启用长期记忆

```python
from contextmind import Client, ContextEngine
from google.adk.memory import InMemoryMemoryService

async def create_bot_with_long_term_memory():
    client = Client()
    
    # 创建独立的记忆服务
    memory_service = InMemoryMemoryService()
    
    # 创建引擎
    engine = ContextEngine(
        app_name="assistant",
        user_id="user-123",
        llm_client=client,
        base_system_prompt="你是一个有记忆的助手。",
        memory_service=memory_service,  # 启用长期记忆
        max_recent_events=20
    )
    
    # 植入初始记忆
    await engine.seed_memory([
        "用户喜欢简短的回答",
        "用户是一名程序员",
        "用户关注 AI 技术发展"
    ])
    
    return engine
```

### 示例 4: 对比三种引擎效果

参考 `gradio_demo.py` 或 `interactive_demo.py` 中的实现：

```python
# 基础引擎：只有最近对话
engine_basic = ContextEngine(
    app_name="basic",
    user_id="user",
    llm_client=client,
    max_recent_events=6
)

# 短期记忆引擎：对话 + 画像 + 规则
engine_short = ContextEngine(
    app_name="short-term",
    user_id="user",
    llm_client=client,
    max_recent_events=6,
    user_profile={...},
    business_rules={...}
)

# 长期记忆引擎：全功能
engine_long = ContextEngine(
    app_name="long-term",
    user_id="user",
    llm_client=client,
    max_recent_events=50,
    user_profile={...},
    business_rules={...},
    memory_service=InMemoryMemoryService()
)
```

---

## 📚 API 文档

### `Client` - LLM 客户端

```python
from contextmind import Client, ClientConfig

# 从环境变量创建
client = Client()

# 手动配置
config = ClientConfig(
    api_key="your-key",
    base_url="http://api.example.com/v1",
    model="Qwen3-32B",
    temperature=0.7,
    max_tokens=4096
)
client = Client(config=config)
```

### `ContextEngine` - 上下文引擎

#### 初始化参数

```python
engine = ContextEngine(
    app_name: str,              # 应用名称
    user_id: str,               # 用户 ID
    llm_client: Client,         # LLM 客户端
    session_service: Optional[BaseSessionService] = None,  # 会话服务
    memory_service: Optional[BaseMemoryService] = None,    # 记忆服务
    session_id: Optional[str] = None,                      # 会话 ID
    max_recent_events: int = 6,                            # 最大保留事件数
    base_system_prompt: str = "",                          # 基础系统提示词
    user_profile: Optional[dict] = None,                   # 用户画像
    business_rules: Optional[dict] = None,                 # 业务规则
    temporal_context: Optional[dict] = None,               # 时间上下文
    use_preset_info: bool = True,                          # 是否使用预设信息
)
```

#### 主要方法

```python
# 处理单轮对话
result = await engine.process_turn(user_input: str) -> ContextTurnResult

# 植入长期记忆
await engine.seed_memory(facts: List[str])

# 获取当前会话
session = await engine.get_current_session() -> Session

# 持久化到记忆
await engine.persist_to_memory()

# 重置用户状态
engine.reset_user_state()

# 获取交互次数
count = engine.get_interaction_count() -> int
```

### `ContextTurnResult` - 对话结果

```python
@dataclass
class ContextTurnResult:
    prompt: str          # 生成的完整 prompt
    reasoning: str       # 推理过程（可选）
    response: str        # LLM 的回复
    memory_hits: List[str]  # 命中的记忆条目
```

### 日志配置

```python
from contextmind.logger import setup_logging, get_logger, DEBUG, INFO

# 配置日志
setup_logging(
    level=DEBUG,              # 日志级别
    log_to_console=True,      # 输出到控制台
    auto_create_file=True     # 自动创建日志文件
)

# 获取 logger
logger = get_logger(__name__)
logger.info("Hello ContextMind!")
```

---

## ❓ 常见问题

### Q1: 如何切换 LLM 提供商？

只需修改环境变量即可：

```bash
# 使用 OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4

# 使用 DeepSeek
DEEPSEEK_API_KEY=your-key
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

### Q2: 如何自定义系统提示词？

在创建引擎时设置：

```python
engine = ContextEngine(
    app_name="my-app",
    user_id="user-001",
    llm_client=client,
    base_system_prompt="你的自定义提示词"
)
```

### Q3: 记忆会永久保存吗？

当前使用 `InMemoryMemoryService`，记忆仅在程序运行期间保存。如需持久化，可以：

1. 实现自定义的 `BaseMemoryService`
2. 使用数据库（Redis、PostgreSQL 等）
3. 使用向量数据库（Chroma、FAISS 等）

### Q4: 如何控制对话历史长度？

通过 `max_recent_events` 参数：

```python
engine = ContextEngine(
    # ...
    max_recent_events=10  # 保留最近10轮对话
)
```

### Q5: 如何调试和查看详细日志？

```python
from contextmind.logger import setup_logging, DEBUG

setup_logging(level=DEBUG, log_to_console=True)
```

### Q6: 支持流式输出吗？

当前版本不支持，但可以扩展 `Client` 类实现流式调用。

### Q7: 如何处理多用户并发？

为每个用户创建独立的引擎实例：

```python
engines = {}

async def get_user_engine(user_id: str):
    if user_id not in engines:
        engines[user_id] = ContextEngine(
            app_name="app",
            user_id=user_id,
            llm_client=Client()
        )
    return engines[user_id]
```

---

## 🤝 贡献指南

欢迎贡献代码、报告问题或提出建议！

### 开发环境设置

```bash
# 克隆项目
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind

# 安装开发依赖
pip install -r requirements.txt

# 运行测试（TODO: 添加测试）
# pytest tests/
```

### 提交 Issue

如果遇到问题，请提供：
- 问题描述
- 复现步骤
- 环境信息（Python 版本、依赖版本等）
- 错误日志

### 提交 Pull Request

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 开启 Pull Request

---

## 📄 许可证

[添加许可证信息]

---

## 📞 联系方式

- **GitHub**: https://github.com/Jasmine66Bloom/ContextMind
- **Issues**: https://github.com/Jasmine66Bloom/ContextMind/issues

---

## 🙏 致谢

- **Google ADK** - 提供强大的 Agent 开发工具包
- **OpenAI** - 提供优秀的 LLM API
- **Gradio** - 提供简单易用的 UI 框架

---

**快乐编码！** 🚀

如有任何问题，欢迎提 Issue 或加入讨论！
