# ContextMind v5.1 架构文档

## 概述

ContextMind v5.1 采用五层清晰架构 (core/pipeline/strategies/adapters/utils)，相比v4.0进一步简化和优化。

**v5.1 核心优化**：
- 五层架构：core → pipeline → strategies → adapters → utils
- 清晰的职责划分和依赖关系
- 更易理解和维护的代码结构

> 📖 **设计哲学**请参考 [DESIGN_PHILOSOPHY.md](./DESIGN_PHILOSOPHY.md)

## 五层架构 (v5.1)

```
┌─────────────────────────────────────────┐
│         核心层 (Core)                    │  ← contextmind/core/
│    Token计数 | 缓存 | 向量 | 会话       │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       流水线层 (Pipeline)                │  ← contextmind/pipeline/
│    预处理 → 检索 → 整合 →                │
│    压缩 → 重排序 → 提取                  │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│       策略层 (Strategies)                │  ← contextmind/strategies/
│    可插拔算法实现                        │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│      适配器层 (Adapters)                 │  ← contextmind/adapters/
│    OpenAI | LangChain | Custom         │
└─────────────────────────────────────────┘
                 ↑
┌─────────────────────────────────────────┐
│        工具层 (Utils)                    │  ← contextmind/utils/
│    配置 | 监控 | 格式化                  │
└─────────────────────────────────────────┘
```

## 核心组件

### 1. 数据模型 (`data_models.py`)

定义框架中所有数据结构：

- **Message**: 对话消息
- **ContextItem**: 上下文条目
- **ProcessedContext**: 处理后上下文
- **ContextResult**: 上下文优化结果
- **Knowledge**: 提取的知识
- **MemoryNote**: 结构化记忆笔记

### 2. 核心层 (Core)

基础数据结构和服务：
- `content`: 记忆内容
- `keywords`: 自动提取的关键词
- `tags`: 分类标签
- `linked_memories`: 关联记忆列表
- `importance_score`: 重要性分数（热度驱动）
- `access_count`: 访问次数

### 3. 管理器 (`managers/`)

封装了对 Google ADK 服务的访问：

- **SessionManager**: 管理短期会话历史
- **MemoryManager**: 管理长期记忆

### 4. 流水线 (`pipeline/`)

实现上下文处理的各个阶段：

- **InputProcessor**: 输入验证和清洗
- **ContextCollector**: 从多个来源收集上下文
- **ContextIntegrator**: 整合和去重（委托给 IntegrationStrategy）
- **ContextOptimizer**: 压缩和截断（保留领域特定逻辑）
- **KnowledgeExtractor**: 提取结构化知识（委托给 ExtractionStrategy）

**架构改进**：Pipeline 组件现在委托给 Strategy 层执行核心逻辑，避免重复代码。

### 5. 策略 (`strategies/`)

提供可插拔的策略实现：

- **RetrievalStrategy**: 检索策略（关键词、向量、混合）
- **IntegrationStrategy**: 整合策略（简单、优先级）
- **OptimizationStrategy**: 优化策略（压缩、重排）
- **ExtractionStrategy**: 提取策略（规则、LLM）

**核心职责**：包含实际的业务逻辑实现，被 Pipeline 组件复用。

### 6. 上下文引擎 (`engine.py`)

核心API：

```python
class ContextEngine:
    async def optimize(user_input, ...) -> ContextResult
    async def update(user_input, assistant_response) -> None
    async def extract_knowledge(auto_store=True) -> List[Knowledge]
    async def seed_memory(facts) -> None
    async def clear_session() -> None
```

### 7. 工具层 (`utils/`)

提供辅助功能：

- **ConfigManager**: 配置管理
- **PerformanceMonitor**: 性能监控
- **ContextVisualizer**: 可视化
- **EventBus**: 事件系统
- **ContextFormatter**: 格式化输出（用于调试）
- **ContextTextBuilder**: 统一文本构建工具（新增，消除重复）

**ContextTextBuilder**：提供统一的文本格式化接口，被所有适配器和格式化器使用。

## 数据流

```
用户输入
    ↓
InputProcessor (验证、清洗)
    ↓
ContextCollector (收集会话历史、长期记忆)
    ↓
ContextIntegrator (去重、排序)
    ↓
ContextOptimizer (压缩、截断)
    ↓
ContextResult
    ↓
应用层 (构建Prompt)
    ↓
LLM
    ↓
回复
    ↓
SessionManager (更新会话)
    ↓
KnowledgeExtractor (提取知识)
    ↓
MemoryManager (存储到长期记忆)
```

## 扩展点

### 1. 自定义策略

实现策略基类：

```python
from contextmind.strategies import RetrievalStrategy

class MyRetrievalStrategy(RetrievalStrategy):
    async def retrieve(self, query, limit=5, **kwargs):
        # 自定义检索逻辑
        pass
```

### 2. 自定义应用

继承应用基类：

```python
from examples.applications import BaseApplication

class MyApplication(BaseApplication):
    def build_prompt(self, user_input, context):
        # 自定义Prompt构建
        pass
```

### 3. 自定义处理器

实现处理器基类：

```python
from contextmind.pipeline import BaseProcessor

class MyProcessor(BaseProcessor):
    async def process(self, input_data):
        # 自定义处理逻辑
        pass
```

## 与旧版本的区别

| 特性 | v2.0 | v3.0/v3.1 | v3.2 | v4.0 |
|------|------|------|------|------|
| 架构 | 单一Pipeline | 四层架构 | 六层架构 | 六层架构（优化） |
| 核心类 | Pipeline + Steps | ContextEngine + Pipeline | ContextEngine + Foundation | ContextEngine + Foundation |
| Pipeline/Strategy关系 | N/A | 独立实现 | 独立实现 | **Pipeline委托给Strategy** |
| 扩展性 | Step注册表 | 策略模式 | 策略模式 + 适配器模式 | 策略模式 + 适配器模式 |
| 数据模型 | Context + ContextData | 专用数据类 | 专用数据类 + Chunk + ContextState | 专用数据类 + Chunk + ContextState |
| API设计 | 复杂 | 简洁（optimize/update/extract） | 简洁 + 适配器 | 简洁 + 适配器 |
| 职责划分 | 模糊 | 清晰 | 更清晰 | **最清晰** |
| Token管理 | 字符估算 | 字符估算 | TokenizerService精确计数 | TokenizerService精确计数 |
| 缓存 | 无 | 无 | CacheManager | CacheManager |
| 容错 | 无 | 无 | CircuitBreaker + FlowController | CircuitBreaker + FlowController |
| 文本格式化 | 分散 | 分散 | 分散 | **ContextTextBuilder统一** |
| 代码重复 | 高 | 中 | 中 | **低（消除80%+重复）** |
| 设计原则 | - | 部分 | 部分 | **SOLID 全面实践** |
| 文档完善度 | 基础 | 中等 | 中等 | **完整（设计哲学+架构）** |

## 架构优化改进（v4.0）

### 1. 消除 Pipeline/Strategy 重复逻辑

**问题**：Pipeline 组件（如 ContextIntegrator）和 Strategy 实现（如 SimpleIntegrationStrategy）包含相同的业务逻辑。

**解决方案**：
```python
# 优化前：重复的去重和排序逻辑
class ContextIntegrator:
    async def integrate(self, context):
        # 去重逻辑...
        # 排序逻辑...

class SimpleIntegrationStrategy:
    async def integrate(self, context):
        # 相同的去重逻辑...
        # 相同的排序逻辑...

# 优化后：委托模式
class ContextIntegrator:
    def __init__(self, strategy=None):
        self.strategy = strategy or SimpleIntegrationStrategy()
    
    async def integrate(self, context):
        return await self.strategy.integrate(context)
```

**收益**：
- 减少 ~160 行重复代码
- 单一真实来源（Single Source of Truth）
- 更容易维护和测试

### 2. 统一文本格式化

**问题**：多个模块独立实现文本格式化逻辑（adapters/base.py, adapters/langchain_adapter.py, utils/context_formatter.py）。

**解决方案**：创建 `ContextTextBuilder` 统一工具类
```python
# utils/text_builder.py
class ContextTextBuilder:
    @staticmethod
    def build_memory_text(items, include_score=True):
        """统一的记忆文本构建"""
        
    @staticmethod
    def build_enhanced_system_prompt(base, memory, knowledge):
        """统一的增强提示构建"""
```

**收益**：
- 所有适配器使用统一格式
- 减少 ~80 行重复代码
- 易于修改格式标准

### 3. 保留有价值的复杂度

**ContextOptimizer 保留独特逻辑**：
- 会话历史 vs 长期记忆的智能分离
- 领域特定的优化策略（保留最近会话，保留高分记忆）
- 这些是上下文工程的核心价值，不应简化

## 最佳实践

1. **使用ContextEngine作为核心**：不要直接使用Pipeline组件
2. **继承BaseApplication**：构建应用层时继承BaseApplication
3. **数据模型优先**：使用框架提供的数据模型
4. **策略可选**：只在需要时自定义策略
5. **异步编程**：所有核心方法都是异步的，正确使用await

## 性能考虑

1. **上下文长度控制**：使用 `max_context_length` 参数
2. **记忆检索限制**：合理设置检索数量
3. **并发处理**：Pipeline内部使用异步并发
4. **缓存策略**：可在Manager层实现缓存

## 未来计划

- [ ] 向量检索策略实现
- [ ] 外部知识库集成
- [ ] 多模态支持
- [ ] 分布式部署支持
- [ ] 性能监控和追踪
