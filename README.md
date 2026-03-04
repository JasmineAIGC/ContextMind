# ContextMind

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Version](https://img.shields.io/badge/version-0.2.1-green.svg)](https://github.com/Jasmine66Bloom/ContextMind)

**ContextMind** 是一个专为大语言模型设计的通用对话上下文管理框架，提供四种先进的对话处理模式。

---

## 核心特性

- 🎯 **四种模式** - DST（状态追踪）/ FnCTOD（函数调用）/ Evolve（记忆进化）/ PyTOD（程序执行）
- 🔌 **模型无关** - 适配任何 LLM API（OpenAI、Qwen、Claude等）
- 🧠 **智能记忆** - 自动知识提取和语义检索（Evolve模式）
- ⚡ **即插即用** - 可安装包，模块化设计
- 📊 **性能可视** - 详细的步骤计时和性能统计

---

## 快速开始

### 安装

```bash
# 克隆仓库
git clone https://github.com/Jasmine66Bloom/ContextMind.git
cd ContextMind

# 安装依赖
pip install -r requirements.txt

# 或作为包安装
pip install -e .
```

### 配置

创建 `.env` 文件配置 LLM API：

```bash
QWEN3_API_KEY=your_api_key
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN3_MODEL=qwen-plus
```

### 运行示例

```bash
# Web 界面（推荐）
python examples/web_demo.py

# 命令行界面
python examples/cli_demo.py --scenario chat --mode evolve
```

---

## 四种模式

### 1. **DST 模式**（对话状态追踪）
从对话中提取结构化信息（槽位-值对）。

**适用场景**：客服系统、订票系统、表单填写

**示例**：
```python
from contextmind.modes.dst import DialogueStateTracker
from contextmind.infra.llm_client import SimpleLLMClient

tracker = DialogueStateTracker.from_scenario(
    llm_client=SimpleLLMClient(),
    scenario_config=get_callcenter_scenario()
)

state = await tracker.process_turn("我要订明天去北京的票")
# 输出: {'destination': '北京', 'date': '明天'}
```

### 2. **FnCTOD 模式**（函数调用）
基于 Meta AI FnCTOD 论文，将 DST 转化为函数调用。

**适用场景**：任务导向对话、API 集成、多步骤流程

**示例**：
```python
from contextmind.modes.fnctod import FnCTODTracker

tracker = FnCTODTracker.from_scenario(
    llm_client=SimpleLLMClient(),
    scenario_config=get_insurance_scenario()
)

result = await tracker.process_turn("我想买重疾险")
# 自动调用 insurance 函数并提取参数
```

### 3. **Evolve 模式**（演化式上下文）
基于 AlphaEvolve/ThetaEvolve 算法的高级对话管理。

**适用场景**：开放域聊天、长对话、个性化助手

**示例**：
```python
from contextmind.modes.evolve import create_app_for_scenario

app = create_app_for_scenario(
    scenario_name="chat",
    llm_client=SimpleLLMClient(),
    scenario_config=get_chat_scenario()
)

response = await app.process_turn("你好，记住我叫张三")
# 系统会记住用户信息并在后续对话中使用
```

### 4. **PyTOD 模式**（可编程任务型对话）
基于 Apple 研究院 PyTOD 论文，将对话建模为程序执行问题，支持真实 API 调用。

**适用场景**：需要调用外部 API 的任务型对话、高准确性场景

**示例**：
```python
from contextmind.modes.pytod import PyTODTracker, ExecutionEngine

tracker = PyTODTracker(llm_client=SimpleLLMClient())
response = await tracker.process_turn("查一下北京今天的天气")
# 动作解析器生成程序语句 → 执行引擎调用 API → 对话管理器生成回复
```

---

## 文档

- 📖 [快速开始](docs/quick-start.md) - 5分钟上手指南
- 🏗️ [模式对比](docs/modes.md) - 系统架构与模式详解
- 📚 [API参考](docs/api-reference.md) - 完整API文档
- 🔧 [配置指南](docs/configuration.md) - 配置选项说明
- 💡 [示例代码](docs/examples.md) - 丰富的代码示例
- 🐛 [故障排查](docs/troubleshooting.md) - 常见问题解答
- 🤝 [贡献指南](docs/CONTRIBUTING.md) - 如何参与贡献

### 模式深入

- [DST 模式详解](contextmind/modes/dst/README.md)
- [FnCTOD 模式详解](contextmind/modes/fnctod/README.md)
- [Evolve 模式详解](contextmind/modes/evolve/README.md)

---

## 项目结构

```
ContextMind/
├── contextmind/          # 核心包
│   ├── infra/           # 基础设施（LLM客户端、日志等）
│   ├── modes/           # 四种对话模式
│   │   ├── dst/        # 对话状态追踪（3文件）
│   │   ├── fnctod/     # 函数调用（4文件）
│   │   ├── evolve/     # 演化式上下文
│   │   └── pytod/      # 可编程任务型对话（6文件）
│   ├── scenarios/       # 场景配置与应用（registry.py + scenarios.yaml + chat/、callcenter/、insurance/）
│   └── ui/              # UI组件
├── examples/            # 示例程序
├── benchmark/           # 评测框架
└── docs/                # 文档
```

---

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

## 致谢

- FnCTOD 模式基于 Meta AI 的论文实现
- PyTOD 模式基于 Apple 研究院的论文实现
- Evolve 模式采用 AlphaEvolve 和 ThetaEvolve 算法
- 感谢所有贡献者的支持

---

**开发者**: [Jasmine66Bloom](https://github.com/Jasmine66Bloom)  
**项目主页**: https://github.com/Jasmine66Bloom/ContextMind
