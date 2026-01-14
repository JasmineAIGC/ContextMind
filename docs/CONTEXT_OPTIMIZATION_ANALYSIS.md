# ContextMind 上下文优化分析文档

## 1. 项目概述

ContextMind 是一个基于 Google ADK 的上下文工程框架，当前实现了多轮对话的短期记忆（Session）和长期记忆（Memory）管理。

## 2. 上下文优化流程分析

通过分析现有代码（特别是 `engine.py` 中的 `process_turn` 方法），我们识别出以下上下文优化的核心步骤：

### 2.1 上下文优化的通用步骤（Pipeline Steps）

#### 步骤1: **输入验证与预处理** (Input Validation & Preprocessing)
**目的**: 确保输入有效性，进行必要的清洗和规范化

**操作**:
- 输入非空验证
- 文本清洗（去除空白字符、特殊字符）
- 长度检查和截断
- 编码规范化

**当前实现**: `process_turn()` 开头的输入验证

#### 步骤2: **会话管理** (Session Management)
**目的**: 管理对话会话的生命周期

**操作**:
- 创建新会话
- 获取现有会话
- 会话状态更新
- 会话持久化

**当前实现**: `_ensure_session()`, `_fetch_session()`

#### 步骤3: **上下文信息收集** (Context Collection)
**目的**: 从多个来源收集相关的上下文信息

**操作**:
- **短期历史收集**: 获取最近N轮对话历史
  - 当前实现: `_collect_recent_history()`
  - 可配置参数: `max_recent_events`
  
- **长期记忆检索**: 从记忆库检索相关信息
  - 当前实现: `_retrieve_memory()`
  - 子操作:
    - 查询构建 (`_build_search_queries()`)
    - 并发多查询检索
    - 结果去重
    - 相关性评分 (`_calculate_relevance_score()`)
    - 结果排序和截断
  
- **用户画像获取**: 获取用户属性和偏好
  - 当前实现: `user_profile` 字典
  
- **业务规则加载**: 加载业务约束和规则
  - 当前实现: `business_rules` 字典
  
- **时间上下文获取**: 获取时间相关信息
  - 当前实现: `get_temporal_context()`

#### 步骤4: **上下文整合** (Context Integration)
**目的**: 将收集的多源上下文信息整合为结构化知识

**操作**:
- 信息结构化组织
- 预置信息提取
- 扩展上下文收集
- 知识对象构建

**当前实现**: `integrate_context_to_knowledge()`
**输出**: `IntegratedKnowledge` 对象

#### 步骤5: **Prompt生成** (Prompt Generation)
**目的**: 基于整合的上下文生成优化的prompt

**操作**:
- **智能Prompt生成** (Agent-based):
  - 使用LLM作为meta-prompt工程师
  - 根据上下文重要性智能组织信息
  - 当前实现: `_generate_prompt_with_agent()`
  
- **模板Prompt生成** (Template-based):
  - 使用预定义模板拼接
  - 上下文权重计算 (`_calculate_context_weights()`)
  - 按权重排序上下文
  - 当前实现: `_build_prompt()`
  
- **Prompt优化**:
  - 长度控制
  - 重要性标记
  - 格式化
  
- **回退机制**:
  - Agent超时处理
  - Agent失败回退到模板

**当前实现**: `generate_prompt_from_knowledge()`

#### 步骤6: **响应生成** (Response Generation)
**目的**: 调用LLM生成回复

**操作**:
- LLM调用
- 重试机制
- 响应质量验证
- 响应提取和清洗

**当前实现**: `_generate_response_with_retry()`, `_extract_actual_response()`

#### 步骤7: **响应后处理** (Post-processing)
**目的**: 处理生成的响应，确保质量和格式

**操作**:
- 格式清洗（去除markdown、JSON等标记）
- 内容验证（长度、关键词检查）
- 分析内容过滤
- 响应规范化

**当前实现**: `_extract_actual_response()`

#### 步骤8: **会话状态更新** (Session State Update)
**目的**: 将新的交互记录到会话中

**操作**:
- 添加用户输入事件
- 添加助手回复事件
- 历史事件清理（保留最近N条）
- 交互计数更新

**当前实现**: `process_turn()` 中的事件追加, `_cleanup_old_events()`

#### 步骤9: **知识提取与持久化** (Knowledge Extraction & Persistence)
**目的**: 从对话中提取知识并存储到长期记忆

**操作**:
- **知识提取**:
  - 用户画像更新
  - 关键事件识别
  - 用户偏好提取
  - 重要事实提取
  - 情绪状态识别
  - 当前实现: `_extract_knowledge_from_session()`
  
- **知识持久化**:
  - 结构化知识存储
  - 记忆索引更新
  - 当前实现: `_persist_session_to_memory()`

#### 步骤10: **定期总结** (Periodic Summarization)
**目的**: 定期生成对话总结，压缩历史信息

**操作**:
- 触发条件检查（按轮次间隔）
- 对话历史聚合
- 摘要生成
- 摘要存储

**当前实现**: `_periodic_summary()`

#### 步骤11: **结果封装与返回** (Result Packaging)
**目的**: 组织结果数据，返回给调用方

**操作**:
- 元数据收集（处理时间、历史数量等）
- 结果对象构建
- 性能指标计算

**当前实现**: `ContextTurnResult` 构建

### 2.2 上下文优化的关键技术点

#### 2.2.1 记忆检索优化
- **多查询策略**: 构建多个语义相关的查询以提高召回率
- **相关性评分**: 综合考虑关键词匹配、重要性标签、时间衰减
- **并发检索**: 使用 `asyncio.gather` 并发执行多个查询

#### 2.2.2 上下文权重计算
- **动态权重**: 根据用户输入内容调整各上下文源的权重
- **业务关键词匹配**: 特定关键词触发权重调整
- **情绪关键词检测**: 负面情绪触发记忆权重提升

#### 2.2.3 Prompt生成策略
- **双模式**: Agent智能生成 + 模板拼接回退
- **超时控制**: 防止Agent生成耗时过长
- **质量验证**: 验证生成的prompt长度和有效性

#### 2.2.4 知识提取
- **结构化提取**: 使用LLM提取结构化知识
- **JSON解析**: 支持JSON格式输出
- **正则回退**: JSON解析失败时使用正则表达式提取
- **知识分类**: 分类存储不同类型的知识（事实、事件、偏好等）

## 3. 当前架构的优势

1. **模块化设计**: 每个步骤相对独立，便于理解和维护
2. **异步支持**: 大量使用异步操作，提高性能
3. **容错机制**: 多处使用try-except和回退策略
4. **可配置性**: 关键参数可配置（如历史长度、超时时间等）
5. **双模式支持**: Agent和模板两种prompt生成方式

## 4. 通用化改造方向

### 4.1 抽象化层次设计

```
├── Pipeline层 (框架核心)
│   ├── ContextOptimizationPipeline (主流程编排)
│   ├── StepRegistry (步骤注册管理)
│   └── StrategyRegistry (策略注册管理)
│
├── Step层 (步骤抽象)
│   ├── BaseStep (步骤基类)
│   ├── InputValidationStep
│   ├── SessionManagementStep
│   ├── ContextCollectionStep
│   ├── ContextIntegrationStep
│   ├── PromptGenerationStep
│   ├── ResponseGenerationStep
│   ├── PostProcessingStep
│   ├── StateUpdateStep
│   ├── KnowledgeExtractionStep
│   ├── SummarizationStep
│   └── ResultPackagingStep
│
├── Strategy层 (策略实现)
│   ├── Collection Strategies (收集策略)
│   │   ├── RecentHistoryCollector
│   │   ├── SemanticMemoryRetriever
│   │   ├── VectorMemoryRetriever (新增)
│   │   └── HybridMemoryRetriever (新增)
│   │
│   ├── Integration Strategies (整合策略)
│   │   ├── TemplateIntegrator
│   │   ├── GraphIntegrator (新增)
│   │   └── HierarchicalIntegrator (新增)
│   │
│   ├── Prompt Strategies (Prompt策略)
│   │   ├── AgentPromptGenerator
│   │   ├── TemplatePromptGenerator
│   │   ├── ChainOfThoughtPrompt (新增)
│   │   └── TreeOfThoughtPrompt (新增)
│   │
│   ├── Retrieval Strategies (检索策略)
│   │   ├── KeywordRetrieval
│   │   ├── SemanticRetrieval
│   │   ├── DenseRetrieval (新增)
│   │   └── HybridRetrieval (新增)
│   │
│   └── Knowledge Strategies (知识提取策略)
│       ├── LLMExtractor
│       ├── RuleBasedExtractor
│       └── HybridExtractor
│
└── Component层 (可复用组件)
    ├── Scorers (评分器)
    ├── Rankers (排序器)
    ├── Filters (过滤器)
    └── Validators (验证器)
```

### 4.2 关键接口定义

#### Pipeline接口
```python
class ContextOptimizationPipeline:
    def add_step(name: str, step: BaseStep)
    def remove_step(name: str)
    def replace_step(name: str, step: BaseStep)
    async def execute(input: Any) -> PipelineResult
```

#### Step接口
```python
class BaseStep:
    async def execute(context: PipelineContext) -> StepResult
    def validate_input(input: Any) -> bool
    def get_dependencies() -> List[str]
```

#### Strategy接口
```python
class BaseStrategy:
    async def apply(context: StrategyContext) -> StrategyResult
    def get_config() -> Dict
    def set_config(config: Dict)
```

### 4.3 扩展点设计

1. **新增检索算法**: 实现 `BaseRetrievalStrategy`
2. **新增Prompt方法**: 实现 `BasePromptStrategy`
3. **新增知识提取方法**: 实现 `BaseExtractionStrategy`
4. **新增整合方法**: 实现 `BaseIntegrationStrategy`
5. **自定义步骤**: 继承 `BaseStep` 添加到Pipeline

## 5. 未来可集成的论文方案

### 5.1 检索增强方案
- RAG (Retrieval-Augmented Generation)
- DPR (Dense Passage Retrieval)
- ColBERT
- REALM

### 5.2 Prompt优化方案
- Chain-of-Thought
- Tree-of-Thought
- Self-Consistency
- ReAct

### 5.3 记忆管理方案
- MemoryBank
- Hierarchical Memory
- Memory Networks
- Neural Turing Machines

### 5.4 上下文压缩方案
- Selective Context
- LongLLMLingua
- RECOMP
- AutoCompressors

### 5.5 多模态上下文
- Vision-Language Context
- Audio-Text Context
- Multi-modal Fusion

## 6. 总结

ContextMind 已经实现了一个相对完整的上下文优化流程，包含11个核心步骤和数十个操作。通过抽象化、模块化、策略化的改造，可以将其转变为一个通用的上下文优化框架，支持快速集成各种新的上下文优化算法和论文方案。
