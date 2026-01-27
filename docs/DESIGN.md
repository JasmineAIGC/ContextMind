# ContextMind 设计文档

本文档整合了 ContextMind 框架的核心设计信息。

---

## 目录

1. [概述](#overview)
2. [6步流水线架构](#6-step-pipeline-architecture)
3. [MemoryBank 模块](#memorybank-module)
4. [知识提取](#knowledge-extraction)
5. [日志系统](#logging-system)
6. [上下文优化策略](#context-optimization-strategies)

---

## 概述

ContextMind 是一个纯粹的上下文工程框架，专注于**步骤1-4**（上下文构建）和**步骤6**（输出后处理），而**步骤5**（LLM 推理）由用户在外部处理。

### 设计原则

1. **模块化** - 每个组件都有单一职责
2. **可扩展性** - 插件架构便于自定义
3. **关注点分离** - 上下文工程 ≠ LLM 推理
4. **类型安全** - 使用数据模型的强类型
5. **异步优先** - 原生 async/await 支持
6. **代码复用** - 组合优于继承

---

## 6步流水线架构

该框架通过6个不同的步骤处理上下文：

```
用户输入
    ↓
[步骤 1] InputPreprocessor
    ↓
[步骤 2] ContextRetriever + MemoryBank
    ↓
[步骤 3] ContextCompressor (with ConversationSummarizer)
    ↓
[步骤 4] ContextReorderer
    ↓
优化后的上下文 → 外部 LLM (步骤 5，用户控制)
    ↓
[步骤 6] PostProcessor
    ↓
最终响应
```

### 步骤 1: 输入预处理

**目的**：在处理前清理、规范化和验证用户输入。

**常用技术**：
- 基于正则表达式的文本清理
- 动态提示模板 (Jinja2)
- 语义分块
- 系统指令注入

### 步骤 2: 上下文检索

**组件**：
- **ContextRetriever**：外部知识检索（可扩展占位符）
- **MemoryBank**：长期记忆管理（核心组件）

**检索策略**：
- 语义搜索（密集检索）
- 混合搜索（BM25 + 语义）
- 基于定位器的检索

### 步骤 3: 上下文压缩

**目的**：减少 token 数量同时保留关键信息。

**技术**：
- 对话总结
- Token 级截断
- 基于重要性的过滤
- LLM 辅助压缩（可选）

### 步骤 4: 上下文重排序

**目的**：优化上下文顺序以解决"中间遗失"问题。

**策略**：
- 基于相关性的排序
- 基于时效性的排序
- 重要性评分
- 混合策略

### 步骤 5: LLM 推理（外部）

这一步**不是** ContextMind 的一部分。用户使用优化后的上下文调用自己的 LLM。

### 步骤 6: 后处理

**目的**：确保输出质量并提取知识存入记忆。

**操作**：
- 格式验证和修正
- 去重
- 引用生成
- 知识提取
- 记忆更新

---

## MemoryBank 模块

MemoryBank 是核心记忆管理组件，处理跨会话的长期信息持久化。

### 架构

```
MemoryBank
├── Extractor    - 从对话中提取高价值知识
├── Retriever    - 通过语义搜索检索相关记忆
├── Updater      - 添加/更新/删除记忆并处理冲突
└── Bank         - 主存储和协调
```

### 知识类型

```python
class KnowledgeType(Enum):
    PREFERENCE = "preference"  # 用户偏好 (例如："喜欢辣的食物")
    FACT = "fact"              # 事实性信息 (例如："生日：10月1日")
    EVENT = "event"            # 事件 (例如："2024年访问过巴黎")
    GOAL = "goal"              # 目标 (例如："想学习 Python")
    ENTITY = "entity"          # 命名实体
```

### 记忆格式

```json
{
  "memory_id": "uuid",
  "type": "preference",
  "content": "User prefers spicy food",
  "embedding": [0.1, 0.2, ...],
  "metadata": {
    "user_id": "user-123",
    "timestamp": "2024-01-20T10:00:00Z",
    "importance_score": 0.95,
    "last_accessed": "2024-01-20T10:00:00Z",
    "frequency": 3
  }
}
```

### 提取策略

#### 1. 基于规则的提取器（默认）
- 快速、确定性的模式匹配
- 基于模板的提取
- 关键词频率分析
- 无 API 成本

#### 2. 基于 LLM 的提取器
- 通过 LLM 进行语义理解
- 实体和关系提取
- 适应复杂场景
- 需要 API 成本

#### 3. 基于重要性的提取器
- 预测"持久性价值"分数
- 结合时间衰减和显式性
- 小模型微调（BERT 风格）

### 检索策略

#### 1. 语义检索器
- 密集向量搜索
- 余弦相似度
- Top-k 结果

#### 2. 混合检索器
- 结合 BM25 + 语义搜索
- 加权分数融合
- 更好的召回率和精确度

#### 3. 定位器检索器
- 基于图的记忆导航
- 上下文记忆链
- 高级记忆链接

### 更新策略

#### 1. 简单更新器
- 直接添加/更新/删除
- 无冲突处理
- 快速直接

#### 2. 冲突解决更新器
- 检测矛盾
- 保留更新的信息
- 版本跟踪

#### 3. 自适应更新器
- 基于学习的更新
- 频率和重要性加权
- 智能记忆整合

---

## 知识提取

### 提取方法比较

| 特性 | 基于规则 | 基于 LLM |
|---------|-----------|-----------|
| 速度 | 快速 | 较慢（API 调用） |
| 准确性 | 高（明确模式） | 高（语义） |
| 灵活性 | 低（预定义） | 高（自适应） |
| 成本 | 免费 | API 成本 |
| 复杂场景 | 受限 | 强大 |
| 实体关系 | 不支持 | 支持 |

### 配置

```python
from contextmind import ExtractionConfig

config = ExtractionConfig(
    extraction_method="llm",  # or "rule"
    min_confidence=0.7,
    extract_preferences=True,
    extract_facts=True,
    extract_events=True,
    extract_entities=True,      # LLM only
    extract_relationships=True, # LLM only
)
```

### 使用示例

```python
from contextmind import ContextMind

# 使用基于规则的提取（默认）
cm = ContextMind(llm_client=None, extractor='rule_based')

# 使用基于 LLM 的提取
cm = ContextMind(llm_client=your_llm, extractor='llm_entity')

# 在后处理期间自动提取
final = await cm.post_process(
    llm_output,
    session_id="user-123",
    extract_knowledge=True  # 启用提取
)
```

---

## 日志系统

ContextMind 提供了一个针对上下文工程工作流优化的三级日志系统。

### 日志级别

#### 1. BASIC（默认）
- 仅流水线级事件
- 输入和输出
- 主要处理里程碑
- 生产就绪

**使用场景**：在生产环境运行，需要高级概览

#### 2. DETAILED
- BASIC + 步骤级日志
- 单独的步骤执行
- 步骤输入/输出
- 中间结果

**使用场景**：调试工作流，理解流程

#### 3. DEBUG
- DETAILED + 内部细节
- Token 计数
- 记忆操作
- 完整跟踪信息

**使用场景**：深度调试，性能分析

### 配置

```python
from contextmind import setup_logging, LogLevel

# 基本模式（默认）
setup_logging(LogLevel.BASIC)

# 详细模式
setup_logging(LogLevel.DETAILED)

# 调试模式
setup_logging(LogLevel.DEBUG)
```

### 模块特定日志

每个模块都有前缀标识符：
- `[MemoryBank]` - 记忆操作
- `[Retriever]` - 检索操作
- `[ContextEngine]` - 引擎协调
- `[Extractor]` - 知识提取
- `[Prompt]` - 提示构建

### 状态指示器

- ✓ 成功
- ✗ 失败
- ━━━ 阶段分隔符

---

## 上下文优化策略

### 压缩策略

1. **基于规则的压缩**
   - TF-IDF 关键词选择
   - 句子重要性评分
   - 快速、确定性

2. **LLM 辅助压缩**
   - LLMLingua2 / LongLLMLingua
   - AutoCompressor
   - 质量更高、速度较慢

3. **基于总结的压缩**
   - 对话总结
   - 渐进式总结
   - 内存高效

### 重排序策略

1. **基于相关性**
   - 查询-上下文相似度
   - 语义匹配
   - 注意力优化

2. **基于时效性**
   - 时间衰减加权
   - 最新优先排序
   - 简单有效

3. **基于重要性**
   - 重要性评分
   - 关键信息优先
   - PPR（个性化 PageRank）

### 集成策略

1. **朴素集成**
   - 简单拼接
   - 无去重
   - 快速基线

2. **智能集成**
   - 重复检测
   - 冲突解决
   - 源优先级

3. **语义集成**
   - 语义去重
   - 信息融合
   - 最大信息密度

---

## 最佳实践

### 1. 从简单开始，智能扩展
- 从基于规则的提取开始
- 在需要时启用 LLM 提取
- 监控 API 成本与质量收益

### 2. 明智配置记忆
- 设置适当的 `max_memory_items`（默认：1000）
- 根据使用场景调整 `similarity_threshold`（0.6-0.8）
- 大多数情况下使用 3-10 的 `retrieval_top_k`

### 3. 优化 Token 使用
- 为长对话启用压缩
- 使用总结来减少 token
- 在 DEBUG 模式下监控 token 计数

### 4. 插件选择
- **简单应用**：rule_based + semantic + simple
- **高级应用**：llm_entity + hybrid + conflict_resolver
- **生产环境**：从简单开始，分析后再升级

### 5. 测试和监控
- 部署前运行测试
- 开发期间使用 DETAILED 日志
- 生产环境切换到 BASIC 日志
- 监控记忆大小和检索延迟

---

## 架构演进

### v7.0 - 纯上下文工程
- 将 LLM 推理与框架分离
- 引入 6 步流水线
- 可插拔策略系统

### v7.1 - 代码质量
- 消除代码重复
- 改进类型安全
- 增强文档

### v7.2 - 增强可观测性
- 模块特定日志
- 完整的记忆生命周期跟踪
- 透明的上下文优化

### v7.3 - 模块化结构（当前）
- 将 models.py 拆分为 types、data_models、configs
- 重组引擎层
- 改进导入结构
- 框架级配置（framework_config.py）

---

## 未来方向

### 短期
- 高级压缩算法（LLMLingua3）
- 多模态记忆支持
- 分布式记忆后端

### 长期
- 联邦记忆系统
- 跨用户知识图谱
- 自动策略选择

---

**详细架构信息请参阅 [ARCHITECTURE.md](ARCHITECTURE.md)**

**迁移指南请参阅 [MIGRATION.md](MIGRATION.md)**

**原始架构参考请参阅 [arch_by_me.md](arch_by_me.md)**
