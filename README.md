# ContextMind

**ContextMind v3.2** - 让上下文优化变得简单而强大 ✨

## 简介

ContextMind 是一个**通用的上下文工程实现框架**，具有**可扩展**、**易集成**、**模块化**的特点。核心的 contextmind 部分可以便捷地嵌入到任何对话系统中，提升对话质量。

### 核心定位

**解决 LLM 对话系统中的上下文优化问题**：
- 🎯 上下文窗口限制（4K/8K/32K tokens）
- 🎯 信息过载（不是所有历史都相关）
- 🎯 多源整合（会话/记忆/知识统一管理）

### 架构特色

- ✅ **无代码重复**：Pipeline 委托给 Strategy，消除 ~240 行重复代码
- ✅ **统一格式化**：ContextTextBuilder 提供一致的文本构建接口
- ✅ **精准 Token 管理**：TokenizerService 准确计数，杜绝溢出
- ✅ **高性能缓存**：5-400x 性能提升
- ✅ **六层架构**：职责清晰，易于扩展

## 核心特性

- 🎯 **专注上下文优化**：专为对话系统设计的上下文工程框架
- 🔌 **可插拔策略**：检索、整合、优化、提取策略均可自定义
- 🔄 **多源整合**：支持会话历史、长期记忆、外部知识的统一管理
- ⚡ **高性能**：TokenizerService 精确计数 + CacheManager 智能缓存
- 🛡️ **容错机制**：CircuitBreaker 熔断器 + FlowController 流程控制
- 📦 **易于集成**：提供 OpenAI、LangChain 等适配器

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基本使用

```python
import asyncio
from contextmind import ContextEngine, Client, ClientConfig

async def main():
    # 初始化客户端
    client = Client(config=ClientConfig.from_env())
    
    # 初始化引擎
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123",
        llm_client=client,
    )
    
    # 优化上下文
    context_result = await engine.optimize("你好")
    
    # 更新会话
    await engine.update(
        user_input="你好",
        assistant_response="你好，有什么可以帮助你的？"
    )

asyncio.run(main())
```

### 使用演示

```bash
# 命令行交互式演示
python interactive_demo.py

# Gradio Web UI 演示
python gradio_demo.py
```

## 架构设计

```
┌─────────────────────────────────────────┐
│        应用层 (Application Layer)       │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│       适配器层 (Adapter Layer)          │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│       引擎层 (Engine Layer)             │
│         ContextEngine                   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│      流水线层 (Pipeline Layer)          │
│  InputProcessor → ContextCollector →    │
│  ContextIntegrator → ContextOptimizer   │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│       策略层 (Strategy Layer)           │
└─────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────┐
│   基础层 + 控制层                       │
│  TokenizerService | VectorClient |      │
│  CacheManager | FlowController |        │
│  CircuitBreaker                         │
└─────────────────────────────────────────┘
```

## 核心组件

### 数据模型

- `Message` - 对话消息
- `ContextItem` - 上下文条目
- `ContextResult` - 优化结果
- `Knowledge` - 提取的知识
- `Chunk` - 上下文块 (v3.2)
- `ContextState` - 状态对象 (v3.2)

### 策略类型

- `RetrievalStrategy` - 检索策略（关键词、向量、混合）
- `IntegrationStrategy` - 整合策略（简单、优先级）
- `OptimizationStrategy` - 优化策略（压缩、重排）
- `ExtractionStrategy` - 提取策略（规则、LLM）

### 基础服务 (v3.2)

- `TokenizerService` - Token 精确计数，避免上下文溢出
- `VectorClient` - 向量数据库统一接口
- `CacheManager` - LRU + TTL 智能缓存

### 控制组件 (v3.2)

- `FlowController` - 根据查询类型动态决定执行路径
- `CircuitBreaker` - 熔断器，防止级联故障

## 文档

### 核心文档
- [📐 设计哲学与架构思想](docs/DESIGN_PHILOSOPHY.md) ⭐ **必读**
- [🏗️ 架构文档](docs/ARCHITECTURE.md)
- [📚 API 参考](docs/API_REFERENCE.md)
- [✨ 最佳实践](docs/BEST_PRACTICES.md)

### 专题文档
- [🔧 基础层详解](docs/FOUNDATION_LAYER.md)
- [🔍 日志分析指南](docs/LOG_ANALYSIS_GUIDE.md)
- [📊 上下文流程详解](docs/CONTEXT_FLOW_DETAILED.md)

## 环境变量

创建 `.env` 文件并配置以下变量：

```bash
# API Key（必需）
QWEN3_API_KEY=your-api-key

# 模型配置（可选）
QWEN3_MODEL=Qwen3-32B
QWEN3_BASE_URL=https://api.example.com

# 其他参数（可选）
QWEN3_TEMPERATURE=0.6
QWEN3_MAX_TOKENS=8192
```

## 版本历史

- **v3.2 优化版** - 消除代码冗余（~240行），统一文本格式化，改进架构
- **v3.2** - 新增 Foundation Layer、Control Layer、增强数据模型
- **v3.1** - 重构引擎层，优化 API 设计
- **v3.0** - 完全重构，引入六层架构

## 项目状态

- ✅ 代码质量：无重复代码，单一真实来源
- ✅ 测试覆盖：23/23 测试通过
- ✅ 安全验证：CodeQL 0 告警
- ✅ 文档完善：完整的设计文档和 API 参考

## 许可证

MIT License
