# ContextMind

**通用的上下文优化框架** - 基于 Google ADK，提供可扩展的多轮对话上下文管理能力，支持灵活集成各种上下文优化算法和论文方案。

## ✨ 核心特性

- 🔄 **完整的上下文优化流程**: 包含11个核心步骤，60+个操作
- 🧠 **智能记忆管理**: 短期记忆（Session）+ 长期记忆（Memory）
- 🎯 **多策略支持**: 灵活切换检索、Prompt生成、知识提取等策略
- 🔌 **高度可扩展**: 易于集成新的上下文优化算法
- ⚡ **异步高性能**: 全异步设计，支持并发优化

## 📚 文档

- [上下文优化步骤分析](docs/上下文优化步骤总结.md) - 详细分析11个核心步骤和所有操作
- [框架设计文档](docs/FRAMEWORK_DESIGN.md) - 通用框架架构设计
- [集成指南](docs/INTEGRATION_GUIDE.md) - 如何集成新的算法和论文方案
- [技术分析](docs/CONTEXT_OPTIMIZATION_ANALYSIS.md) - 深入的技术分析

## 🚀 快速开始

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

2. 运行交互式演示：
   ```bash
   python interactive_demo.py
   ```

3. 或运行网页演示：
   ```bash
   python gradio_demo.py
   ```

## 📁 项目结构

```
ContextMind/
├── contextmind/           # 核心代码目录
│   ├── client.py          # LLM客户端实现
│   ├── engine.py          # 上下文引擎（包含11个核心步骤）
│   └── logger.py          # 日志功能
├── docs/                  # 文档目录
│   ├── 上下文优化步骤总结.md    # 完整步骤分析
│   ├── FRAMEWORK_DESIGN.md      # 框架设计
│   ├── INTEGRATION_GUIDE.md     # 集成指南
│   └── CONTEXT_OPTIMIZATION_ANALYSIS.md  # 技术分析
├── data/                  # 示例数据
├── interactive_demo.py    # 命令行演示
├── gradio_demo.py         # 网页演示
└── requirements.txt       # 项目依赖
```

## 🧩 核心步骤

ContextMind 的上下文优化流程包含11个核心步骤：

1. **输入验证与预处理** - 输入清洗和规范化
2. **会话管理** - 会话生命周期管理
3. **上下文信息收集** - 多源上下文收集（历史、记忆、画像等）
4. **上下文整合** - 整合为结构化知识
5. **Prompt生成** - 智能Prompt生成（Agent + 模板）
6. **响应生成** - LLM调用和重试
7. **响应后处理** - 格式清洗和规范化
8. **会话状态更新** - 记录到会话历史
9. **知识提取与持久化** - 提取并存储知识
10. **定期总结** - 生成对话摘要
11. **结果封装与返回** - 组织结果和元数据

详细信息请查看 [上下文优化步骤总结](docs/上下文优化步骤总结.md)

## 🔧 可扩展性

框架支持集成多种上下文优化算法：

### 检索增强
- RAG (Retrieval-Augmented Generation)
- DPR (Dense Passage Retrieval)
- ColBERT
- REALM

### Prompt优化
- Chain-of-Thought
- Tree-of-Thought
- ReAct
- Self-Consistency

### 上下文压缩
- LongLLMLingua
- Selective Context
- RECOMP
- AutoCompressors

查看 [集成指南](docs/INTEGRATION_GUIDE.md) 了解如何集成新算法。

## 📊 使用示例

### 基础使用

```python
from contextmind import Client, ContextEngine
from google.adk.memory import InMemoryMemoryService

# 创建客户端
client = Client()

# 创建引擎
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=client,
    memory_service=InMemoryMemoryService(),
    base_system_prompt="你是一个专业的客服助手"
)

# 处理用户输入
result = await engine.process_turn("你好，有什么可以帮助的？")
print(result.response)
```

### 自定义配置

```python
# 配置用户画像和业务规则
engine = ContextEngine(
    app_name="callcenter",
    user_id="user-456",
    llm_client=client,
    max_recent_events=10,  # 保留最近10轮对话
    user_profile={
        "姓名": "张先生",
        "年龄": "30-40岁",
        "偏好": "简洁高效"
    },
    business_rules={
        "合规要求": "必须礼貌专业",
        "核心职责": "解决用户问题"
    },
    agent_timeout=15.0  # Agent Prompt生成超时15秒
)
```

## 🎯 未来规划

我们计划将 ContextMind 发展为一个通用的上下文优化平台：

- [ ] **Pipeline架构**: 实现可配置的Pipeline系统
- [ ] **策略注册**: 支持动态注册和切换策略
- [ ] **向量检索**: 集成FAISS/Milvus等向量数据库
- [ ] **知识图谱**: 支持知识图谱增强
- [ ] **多模态**: 支持图像、语音等多模态上下文
- [ ] **分布式**: 支持分布式部署和扩展

详细设计请查看 [框架设计文档](docs/FRAMEWORK_DESIGN.md)