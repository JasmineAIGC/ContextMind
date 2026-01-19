# ContextMind v5.1 Quick Start Guide

## 安装

```bash
pip install -r requirements.txt
```

## 基本使用

### 1. 初始化引擎

```python
from contextmind.core import ContextEngine
from contextmind.adapters import OpenAIAdapter

# 初始化适配器
llm_adapter = OpenAIAdapter(api_key="your-api-key")

# 创建引擎
engine = ContextEngine(
    llm_adapter=llm_adapter
)
```

### 2. 处理对话

```python
# 优化上下文
result = await engine.optimize(
    query="用户当前问题",
    session_id="unique-session-id"
)

# 访问优化后的上下文
recent_history = result.recent_history
long_term_memory = result.long_term_memory
external_knowledge = result.external_knowledge
```

### 3. 运行演示

**命令行演示:**
```bash
python interactive_demo.py
```

**Web UI 演示:**
```bash
python gradio_demo.py
```

## 配置

```python
from contextmind.core import ContextEngine

engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    max_recent_events=10,
)
```

## 架构概览

```
┌─────────────────────────────────────────┐
│         核心层 (Core)                    │
│    Token | 缓存 | 向量 | 会话           │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       流水线层 (Pipeline)                │
│    预处理 → 检索 → 整合 →                │
│    压缩 → 重排序 → 提取                  │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       策略层 (Strategies)                │
│    可插拔算法                            │
└─────────────────────────────────────────┘
```

## 核心概念

### ProcessedContext vs ContextResult

- **ProcessedContext**: Pipeline中间状态
  - 有 `items` 列表
  
- **ContextResult**: 最终优化输出
  - 有 `recent_history`, `long_term_memory`, `external_knowledge`

### 策略系统

- **提取**: 基于规则、基于LLM
- **重排序**: 基于分数、基于时间
- **压缩**: 按来源截断
- **整合**: 合并多来源上下文

## 下一步

- 阅读 [ARCHITECTURE.md](ARCHITECTURE.md) 了解系统设计
- 阅读 [API_REFERENCE.md](API_REFERENCE.md) 查看详细API
- 查看 [examples/](../examples/) 了解更多使用模式
