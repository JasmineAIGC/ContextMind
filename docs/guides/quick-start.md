# 快速开始

欢迎使用 ContextMind！本指南将帮助您在 5 分钟内完成安装并运行第一个示例。

## 环境要求

- Python 3.8 或更高版本
- pip 包管理器
- （可选）虚拟环境

## 安装

### 方法 1：从源码安装（推荐）

```bash
# 1. 克隆仓库
git clone https://github.com/JasmineAIGC/ContextMind.git
cd ContextMind

# 2. 创建虚拟环境（推荐）
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 3. 安装依赖
pip install -r requirements.txt

# 4. 以可编辑模式安装包
pip install -e .
```

### 方法 2：直接安装依赖

```bash
# 如果只想快速试用，不需要修改代码
pip install -r requirements.txt
```

## 配置

### 1. 创建配置文件

在项目根目录创建 `.env` 文件：

```bash
# 创建配置文件
touch .env
```

### 2. 配置 LLM API

编辑 `.env` 文件，添加以下配置：

```bash
# 通用配置（推荐，适用于任何 OpenAI 兼容端点）
LLM_API_KEY=your_api_key_here
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
LLM_MODEL=qwen-plus

# 或使用模型专用配置（与通用配置等效，优先级更高）
# QWEN3_API_KEY=your_api_key_here
# QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
# QWEN3_MODEL=qwen-plus

# 或 OpenAI API 配置
# OPENAI_API_KEY=your_api_key_here
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o
```

**获取 API Key：**
- **Qwen**: 访问 [阿里云DashScope](https://dashscope.aliyun.com/)
- **OpenAI**: 访问 [OpenAI Platform](https://platform.openai.com/)

### 3. 验证配置

```python
# test_config.py
from dotenv import load_dotenv
import os

load_dotenv()
api_key = os.getenv("LLM_API_KEY") or os.getenv("QWEN3_API_KEY") or os.getenv("OPENAI_API_KEY")
base_url = os.getenv("LLM_BASE_URL") or os.getenv("QWEN3_BASE_URL") or os.getenv("OPENAI_BASE_URL")
model = os.getenv("LLM_MODEL") or os.getenv("QWEN3_MODEL") or os.getenv("OPENAI_MODEL")
print(f"API Key: {api_key[:10] if api_key else '未设置'}...")
print(f"Base URL: {base_url}")
print(f"Model: {model}")
```

运行验证：
```bash
python test_config.py
```

## 第一个示例

### 三步框架概述

ContextMind 的三个核心步骤及其对不同算法的适用情况：

| 步骤 | 内容 | DST | FnCTOD | PyTOD | Evolve |
|------|------|:---:|:------:|:-----:|:------:|
| **① 建立知识库** | 任意数据集 → `schema.json` | ✅ 可选 | ✅ 可选 | ✅ 可选 | ❌ |
| **② Schema 数据生成** | `schema.json` → 算法专用数据 | ❌ | ❌ | ✅ 可选 | ❌ |
| **③ 算法执行** | 对话上下文提取与管理 | ✅ | ✅ | ✅ | ✅ |

### 选项 1：推荐方式 — ContextPipeline（端到端流水线）

`ContextPipeline` 是 ContextMind 推荐的统一入口，3 行代码完成端到端上下文工程：

```python
import asyncio
from contextmind import ContextPipeline, AdkLLMClient

# 步骤1：创建流水线
pipeline = ContextPipeline(llm_client=AdkLLMClient())

# 步骤2a：从原始对话构建知识库（第一步）
my_dialogues = [
    "坐席：你好，请问是张先生吗？\n用户：是的。\n坐席：您有 5 万元可用额度。",
]
pipeline.build_kb(dialogues=my_dialogues, scene_name="银行贷款外呼")

# 或步骤2b：从已有 schema.json 加载（跳过第一步）
# pipeline.load_kb("output/schema.json")

# 步骤3：对话上下文提取（第三步）
async def main():
    result = await pipeline.process_turn("我想查询我的贷款额度")
    print(result["response"])           # 系统回复
    print(result["context"])            # 本轮提取的上下文（槽位、意图等）
    print(result["cumulative_context"]) # 全量累积上下文

asyncio.run(main())
```

运行完整演示：
```bash
python examples/step0_pipeline_demo.py
```

### 选项 2：命令行界面

```bash
# 运行 DST 模式的闲聊场景
python examples/step3_cli_demo.py --scenario chat --mode dst

# 运行 Evolve 模式的客服场景
python examples/step3_cli_demo.py --scenario callcenter --mode evolve

# 运行 FnCTOD 模式的保险场景
python examples/step3_cli_demo.py --scenario insurance --mode fnctod

# 运行 PyTOD 模式的保险场景
python examples/step3_cli_demo.py --scenario insurance --mode pytod
```

**交互示例：**
```
你: 你好
助手: 你好！很高兴认识你。有什么我可以帮助你的吗？

你: 我想了解一下保险产品
助手: 好的，我可以为您介绍我们的保险产品...
```

输入 `退出`、`quit` 或 `exit` 结束对话。

### 选项 3：Web 界面（Gradio）

更直观的图形界面：

```bash
# 启动 Web 界面
python examples/step3_web_demo.py
```

浏览器自动打开 `http://localhost:7860`，您可以：
- 选择不同的场景（闲聊、客服、保险）
- 切换不同的模式（DST、Evolve、FnCTOD）
- 调整高级参数
- 查看对话状态

### 选项 4：直接使用追踪器（底层 API）

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.scenarios import get_chat_scenario

async def main():
    # 初始化
    llm_client = AdkLLMClient()
    config = get_chat_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    # 处理对话
    result = await tracker.process_turn("你好，我想了解一下你们的服务")
    
    # 查看状态
    state = tracker.get_current_state()
    print(f"提取的状态: {state}")

# 运行
if __name__ == "__main__":
    asyncio.run(main())
```

运行：
```bash
python my_first_app.py
```

## 下一步

恭喜！您已经成功运行了第一个 ContextMind 示例。

### 学习路径

1. **理解三步框架**
   - 阅读 [文档中心](../README.md) 了解三步框架概述
   - 了解 DST、FnCTOD、PyTOD、Evolve 的区别和适用场景

2. **查看更多示例**
   - 浏览 [示例代码目录](../../examples/) 中的 `.py` 脚本
   - 学习不同场景的使用方法

3. **深入 API**
   - 查看 [API 参考文档](../reference/api-reference.md)
   - 了解所有可用的类和方法

4. **扩展场景**
   - 阅读 [扩展场景指南](configuration.md)
   - 创建自己的对话场景

### 常见问题

**Q: 遇到 `ModuleNotFoundError` 怎么办？**

A: 确保已安装所有依赖：
```bash
pip install -r requirements.txt
pip install -e .
```

**Q: API 调用失败怎么办？**

A: 检查：
1. `.env` 文件是否在正确位置
2. API Key 是否有效
3. 网络连接是否正常
4. API 配额是否充足

**Q: 想要更详细的调试信息？**

A: 启用详细日志：
```bash
python examples/step3_cli_demo.py --scenario chat --mode dst --verbose
```

**更多问题？** 查看 [故障排查指南](troubleshooting.md)

## 更多示例

### 完整三步流程示例（PyTOD）

```python
import asyncio
from contextmind.knowledge import KnowledgeBaseBuilder
from contextmind.schema_builder import SchemaDataBuilder
from contextmind.modes.pytod import AdkPyTODTracker, ExecutionEngine
from contextmind.infra.llm_client import AdkLLMClient

llm = AdkLLMClient()

# 第一步：建立知识库
builder = KnowledgeBaseBuilder(scene_name="银行贷款外呼", llm_client=llm)
schema_dict = builder.build(my_dialogues)
builder.save(schema_dict, "output/schema.json")

# 第二步：Schema 数据生成（PyTOD 专用，可选）
schema_builder = SchemaDataBuilder(llm_client=llm, schema_path="output/schema.json")
schema_builder.build_pytod_apis(output_path="output/loan_apis.py")

# 第三步：算法执行
engine = ExecutionEngine()
# 加载第二步生成的 API 或手写实现
from output.loan_apis import INTENT_REGISTRY
for name, fn in INTENT_REGISTRY.items():
    engine.register(name)(fn)

service_schema = KnowledgeBaseBuilder.load_schema("output/schema.json")
tracker = AdkPyTODTracker(llm_client=llm, engine=engine, schema=service_schema)

async def main():
    result = await tracker.process_turn("我想查询我的贷款额度")
    print(result["response"])

asyncio.run(main())
```

### 批量处理多轮对话

```python
import asyncio
from contextmind import ContextPipeline
from contextmind.infra.llm_client import AdkLLMClient

async def process_session(utterances: list[str]) -> list[dict]:
    pipeline = ContextPipeline(llm_client=AdkLLMClient())
    pipeline.set_schema(my_schema)

    results = []
    for utterance in utterances:
        result = await pipeline.process_turn(utterance)
        results.append(result)
    return results
```

### 从已有 Schema 启动（跳过第一步）

```python
from contextmind import ContextPipeline
from contextmind.infra.llm_client import AdkLLMClient
from contextmind.knowledge.builder import KnowledgeBaseBuilder
import json

# 加载已存在的 schema
schema = KnowledgeBaseBuilder.load_schema("output/schema.json")

pipeline = ContextPipeline(llm_client=AdkLLMClient())
pipeline.set_schema(schema)

result = await pipeline.process_turn("帮我查一下贷款额度")
```

### 直接使用 AdkPyTODTracker（仅第三步）

```python
from contextmind.modes.pytod import AdkPyTODTracker
from contextmind.infra.llm_client import AdkLLMClient

tracker = AdkPyTODTracker(llm_client=AdkLLMClient())
tracker.from_scenario("安逸花外呼")

result = await tracker.process_turn(
    system_utterance="您好，请问有什么可以帮您？",
    user_utterance="我想查一下我的贷款额度"
)
print(result["response"])
```

---

## 相关资源

- [完整文档](../README.md)
- [API 参考](../reference/api-reference.md)
- [配置指南](configuration.md)
- [GitHub 仓库](https://github.com/JasmineAIGC/ContextMind)
- [问题反馈](https://github.com/JasmineAIGC/ContextMind/issues)

---

**最后更新**: 2026-04-22 | **版本**: 0.3.0
