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
git clone https://github.com/Jasmine66Bloom/ContextMind.git
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
# Qwen API 配置（示例）
QWEN3_API_KEY=your_api_key_here
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus

# 或 OpenAI API 配置
# OPENAI_API_KEY=your_api_key_here
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-3.5-turbo
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
print(f"API Key: {os.getenv('QWEN3_API_KEY')[:10]}...")  # 只显示前10个字符
print(f"Base URL: {os.getenv('QWEN3_BASE_URL')}")
print(f"Model: {os.getenv('QWEN3_MODEL')}")
```

运行验证：
```bash
python test_config.py
```

## 第一个示例

### 选项 1：命令行界面

最简单的方式是使用命令行界面：

```bash
# 运行 DST 模式的闲聊场景
python examples/cli_demo.py --scenario chat --mode dst

# 运行 Evolve 模式的客服场景
python examples/cli_demo.py --scenario callcenter --mode evolve

# 运行 FnCTOD 模式的保险场景
python examples/cli_demo.py --scenario insurance --mode fnctod
```

**交互示例：**
```
你: 你好
助手: 你好！很高兴认识你。有什么我可以帮助你的吗？

你: 我想了解一下保险产品
助手: 好的，我可以为您介绍我们的保险产品...
```

输入 `退出`、`quit` 或 `exit` 结束对话。

### 选项 2：Web 界面（Gradio）

更直观的图形界面：

```bash
# 启动 Web 界面
python examples/web_demo.py
```

浏览器自动打开 `http://localhost:7860`，您可以：
- 选择不同的场景（闲聊、客服、保险）
- 切换不同的模式（DST、Evolve、FnCTOD）
- 调整高级参数
- 查看对话状态

### 选项 3：编写代码

创建 `my_first_app.py`：

```python
import asyncio
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import SimpleLLMClient
from contextmind.scenarios import get_chat_scenario

async def main():
    # 初始化
    llm_client = SimpleLLMClient()
    config = get_chat_scenario()
    tracker = DialogueStateTracker.from_scenario(llm_client, config)
    
    # 处理对话
    result = await tracker.process_turn("你好，我想了解一下你们的服务")
    
    # 查看状态
    state = tracker.get_state()
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

1. **理解三种模式**
   - 阅读 [模式对比文档](modes.md)
   - 了解 DST、Evolve、FnCTOD 的区别和适用场景

2. **查看更多示例**
   - 浏览 [示例代码集合](examples.md)
   - 学习不同场景的使用方法

3. **深入 API**
   - 查看 [API 参考文档](api-reference.md)
   - 了解所有可用的类和方法

4. **扩展场景**
   - 阅读 [扩展场景指南](extending-scenarios.md)
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
python examples/cli_demo.py --scenario chat --mode dst --verbose
```

**更多问题？** 查看 [故障排查指南](troubleshooting.md)

## 相关资源

- [完整文档](README.md)
- [GitHub 仓库](https://github.com/Jasmine66Bloom/ContextMind)
- [问题反馈](https://github.com/Jasmine66Bloom/ContextMind/issues)

---

**最后更新**: 2026-02-10 | **版本**: 0.2.1
