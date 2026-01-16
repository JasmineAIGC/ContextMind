# ContextMind v3.2 架构文档

## 概述

ContextMind v3.2 是一个完全重构的上下文优化框架，专注于支持上下文工程的所有核心能力。

**最新优化（架构简化）**：
- Pipeline 层组件现在委托给 Strategy 层，消除重复逻辑
- 统一的 ContextTextBuilder 工具类用于所有文本格式化
- 更清晰的职责划分，减少代码冗余

## 设计哲学

1. **职责清晰**：每个组件都有明确的职责边界
2. **模块解耦**：组件之间通过清晰的接口通信
3. **易于扩展**：支持策略模式，方便替换和扩展
4. **数据驱动**：使用强类型的数据模型
5. **异步优先**：全面使用 async/await
6. **容错机制**：FlowController 和 CircuitBreaker 保障稳定性
7. **代码复用**：避免重复，使用委托和组合模式

## 六层架构

```
┌─────────────────────────────────────────┐
│        应用层 (Application Layer)       │
│     定义业务逻辑和Prompt构建策略         │
└─────────────────────────────────────────┘
                    ↓ 使用
┌─────────────────────────────────────────┐
│       适配器层 (Adapter Layer)          │
│  OpenAIAdapter, LangChainAdapter, etc.  │
└─────────────────────────────────────────┘
                    ↓ 使用
┌─────────────────────────────────────────┐
│       引擎层 (Engine Layer)              │
│    ContextEngine - 统一的上下文优化接口   │
└─────────────────────────────────────────┘
                    ↓ 使用
┌─────────────────────────────────────────┐
│      流水线层 (Pipeline Layer)           │
│  • InputProcessor - 输入预处理           │
│  • ContextCollector - 上下文收集         │
│  • ContextIntegrator - 上下文整合        │
│  • ContextOptimizer - 上下文优化         │
│  • KnowledgeExtractor - 知识提取        │
└─────────────────────────────────────────┘
                    ↓ 使用
┌─────────────────────────────────────────┐
│       策略层 (Strategy Layer)            │
│  • RetrievalStrategy - 检索策略          │
│  • IntegrationStrategy - 整合策略        │
│  • OptimizationStrategy - 优化策略       │
│  • ExtractionStrategy - 提取策略         │
└─────────────────────────────────────────┘
                    ↓ 使用
┌─────────────────────────────────────────┐
│   基础层 (Foundation) + 控制层 (Control) │
│  • TokenizerService - Token精确计数      │
│  • VectorClient - 向量检索               │
│  • CacheManager - 智能缓存               │
│  • FlowController - 流程控制             │
│  • CircuitBreaker - 熔断器               │
└─────────────────────────────────────────┘
```

## 核心组件

### 1. 数据模型 (`data_models.py`)

定义了框架中所有的数据结构：

- **Message**: 对话消息
- **ContextItem**: 上下文条目
- **ProcessedContext**: 处理后的上下文
- **ContextResult**: 上下文优化结果
- **Knowledge**: 提取的知识
- **MemoryNote**: 结构化记忆笔记（v3.2 Agent Memory System）
- **MemoryType**: 记忆类型枚举（Working/Semantic/Episodic）

### 2. Agent Memory System（v3.2新增）

基于A-MEM架构设计的三层记忆模型：

```
┌─────────────────────────────────────────────────────┐
│               Agent Memory System                    │
├─────────────────────────────────────────────────────┤
│  工作记忆 (Working Memory)                           │
│  • 当前任务的即时上下文                              │
│  • 由SessionManager管理                             │
│  • 短期存储，任务结束后清空                          │
├─────────────────────────────────────────────────────┤
│  语义记忆 (Semantic Memory)                          │
│  • 结构化知识网络                                   │
│  • MemoryNote结构：关键词、标签、链接、重要性       │
│  • 支持动态演化和关联                               │
├─────────────────────────────────────────────────────┤
│  情节记忆 (Episodic Memory)                          │
│  • 时间序列的事件历史                               │
│  • 支持因果链追溯                                   │
│  • 长期持久化存储                                   │
└─────────────────────────────────────────────────────┘
```

**MemoryNote结构（参考Zettelkasten笔记法）**：
- `id`: 唯一标识符
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

| 特性 | v2.0 | v3.0/v3.1 | v3.2 | v3.2 优化版 |
|------|------|------|------|------------|
| 架构 | 单一Pipeline | 四层架构 | 六层架构 | 六层架构（简化） |
| 核心类 | Pipeline + Steps | ContextEngine + Pipeline | ContextEngine + Foundation | ContextEngine + Foundation |
| Pipeline/Strategy关系 | N/A | 独立实现 | 独立实现 | Pipeline委托给Strategy |
| 扩展性 | Step注册表 | 策略模式 | 策略模式 + 适配器模式 | 策略模式 + 适配器模式 |
| 数据模型 | Context + ContextData | 专用数据类 | 专用数据类 + Chunk + ContextState | 专用数据类 + Chunk + ContextState |
| API设计 | 复杂 | 简洁（optimize/update/extract） | 简洁 + 适配器 | 简洁 + 适配器 |
| 职责划分 | 模糊 | 清晰 | 更清晰 | 最清晰 |
| Token管理 | 字符估算 | 字符估算 | TokenizerService精确计数 | TokenizerService精确计数 |
| 缓存 | 无 | 无 | CacheManager | CacheManager |
| 容错 | 无 | 无 | CircuitBreaker + FlowController | CircuitBreaker + FlowController |
| 文本格式化 | 分散 | 分散 | 分散 | **ContextTextBuilder统一** |
| 代码重复 | 高 | 中 | 中 | **低（消除80%+重复）** |

## 架构优化改进（最新）

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
