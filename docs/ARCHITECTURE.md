# ContextMind 架构 (v7.3+)

本文档描述基于 `docs/arch_by_me.md` 架构设计文档的优化项目结构。

## 概述

ContextMind 遵循**五步流水线架构**进行上下文优化：

```
原始用户输入
    ↓
1. InputPreprocessor      (输入清理和规范化)
    ↓
2. ContextRetriever       (外部检索)
   + MemoryBank          (长期记忆管理)
    ↓
3. ContextCompressor      (上下文压缩与对话摘要器)
    ↓
4. ContextReorderer       (上下文重排序)
    ↓
构建最终提示 → [用户调用 LLM] → 获得响应
    ↓
5. ResponseHandler        (响应处理和记忆更新)
    ↓
最终结果 + 记忆已更新
```

**架构变更（v7.3）：**
- ❌ **移除** KVCacheManager - KV缓存管理属于LLM推理框架职责
- ✅ **新增** ResponseHandler - 处理响应并更新记忆库

## 项目结构

```
ContextMind/
├── contextmind/              # 核心框架
│   ├── __init__.py          # 主要导出
│   ├── config.py            # 易集成 API（ContextMind 类）
│   ├── engine.py            # 主编排引擎（ContextEngine）
│   ├── models.py            # 数据模型
│   ├── registry.py          # 组件注册表
│   │
│   │ # 流水线架构 - 5 步
│   ├── preprocessor.py      # 步骤 1：InputPreprocessor
│   ├── retriever.py         # 步骤 2：ContextRetriever（占位符）
│   ├── compressor.py        # 步骤 3：ContextCompressor
│   ├── reorderer.py         # 步骤 4：ContextReorderer
│   ├── response_handler.py  # 步骤 5：ResponseHandler (v7.3新增)
│   │
│   ├── summarizer.py        # ConversationSummarizer（由压缩器使用）
│   │
│   │ # MemoryBank 模块 - 4 个子模块
│   ├── memory/
│   │   ├── __init__.py      # 导出所有记忆组件
│   │   ├── bank.py          # 主 MemoryBank 类
│   │   ├── session.py       # SessionManager
│   │   ├── extractor.py     # 提取高价值信息
│   │   ├── retriever.py     # 检索相关记忆
│   │   └── updater.py       # 记忆更新（添加/删除/更新）
│   │
│   ├── strategies/          # 策略接口
│   │   ├── __init__.py      # 从 memory 重新导出
│   │   ├── base.py          # 基础策略接口
│   │   └── defaults.py      # 默认实现
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   └── embedding.py
│   │
│   │ # 向后兼容包装器
│   ├── pipeline.py          # 从模块化组件重新导出
│   └── memory.py            # 从 memory/ 子模块重新导出
│
├── examples/                # 示例和演示
│   ├── chat_app.py
│   ├── callcenter_app.py
│   ├── gradio_app.py
│   ├── interactive_app.py
│   ├── plugin_examples.py
│   └── llm_client.py
│
├── tests/                   # 单元和集成测试
├── docs/                    # 文档
└── logs/                    # 日志文件
```

## 核心组件

### 1. 流水线组件（5 步）

#### 步骤 1：InputPreprocessor (`preprocessor.py`)
- **目的**：输入清理和规范化
- **方法**：文本清理、验证、规范化
- **常用技术**：基于正则的清理、动态提示模板、语义分块

#### 步骤 2：上下文检索
- **ContextRetriever** (`retriever.py`)：外部知识检索（占位符）
- **MemoryBank** (`memory/bank.py`)：长期记忆管理
  - 使用 4 个子模块：Extractor、Retriever、Updater、Bank

#### 步骤 3：ContextCompressor (`compressor.py`)
- **目的**：上下文压缩以减少 token 使用
- **使用**：ConversationSummarizer 用于最近对话摘要
- **技术**：滑动窗口、摘要、智能过滤

#### 步骤 4：ContextReorderer (`reorderer.py`)
- **目的**：重排序上下文以突出关键信息
- **技术**：时间戳排序、来源优先级、相关性评分
- **缓解**："中间丢失"问题

#### 步骤 5：ResponseHandler (`response_handler.py`) - v7.3 新增
- **目的**：处理 LLM 响应并更新记忆库
- **职责**：
  1. 解析 LLM 响应
  2. 从响应中提取知识
  3. 自动更新记忆库
  4. 记录完整对话轮次
- **特点**：形成完整的记忆更新闭环

### 2. MemoryBank 模块 (`memory/`)

MemoryBank 实现了 4 子模块架构：

#### 2.1 Extractor (`memory/extractor.py`)
- **目的**：提取高价值信息用于长期存储
- **实现**：
  - `RuleBasedExtractor`：模式匹配（轻量级）
  - `LLMBasedExtractor`：大语言模型辅助提取（高端）
  - `ImportancePredictorExtractor`：基于机器学习的重要性评分

#### 2.2 Retriever (`memory/retriever.py`)
- **目的**：基于查询检索相关记忆
- **实现**：
  - `SemanticSearchRetriever`：基于嵌入的相似性
  - `HybridRetriever`：语义 + 关键词匹配
  - `LocatorMechanism`：带上下文加权的精确定位

#### 2.3 Updater (`memory/updater.py`)
- **目的**：智能记忆更新（添加/删除/更新）
- **操作**：
  - **添加**：插入新的高价值记忆
  - **删除**：删除过时/低价值记忆
  - **更新**：处理冲突和信息演化
- **实现**：
  - `SimpleUpdater`：基本添加/更新/去重逻辑
  - `ConflictResolver`：基于大语言模型的冲突检测
  - `AdaptiveEviction`：预测性修剪

#### 2.4 Bank (`memory/bank.py`)
- **目的**：协调所有子模块的主 MemoryBank 类
- **功能**：
  - 持久化用户/对话记忆存储
  - 结构化记忆笔记（偏好、事实、事件）
  - 记忆生命周期管理
  - 跨会话连续性

### 3. 支持组件

#### SessionManager (`memory/session.py`)
- 管理对话会话
- 存储消息历史
- 提供最近历史访问

#### ConversationSummarizer (`summarizer.py`)
- 摘要最近对话
- 由 ContextCompressor 使用
- 在保留上下文的同时减少 token 使用

#### ContextEngine (`engine.py`)
- 主编排引擎
- 协调所有流水线组件
- 提供高级 API：`optimize()`、`update()`、`extract_knowledge()`

#### ContextMind (`config.py`)
- 易集成 API
- 简化配置
- 插件注册表集成

## 导入模式

### 推荐（新代码）

```python
# 流水线组件
from contextmind.preprocessor import InputPreprocessor
from contextmind.compressor import ContextCompressor
from contextmind.reorderer import ContextReorderer
from contextmind.response_handler import ResponseHandler

# 记忆组件
from contextmind.memory import (
    MemoryBank,
    SessionManager,
    BaseExtractor,
    RuleBasedExtractor,
    LLMBasedExtractor,
    BaseRetriever,
    SemanticSearchRetriever,
    BaseUpdater,
    SimpleUpdater,
)

# 高级 API
from contextmind import ContextMind, ContextEngine
```

### 向后兼容（遗留代码）

```python
# 旧流水线导入仍然有效
from contextmind.pipeline import (
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,  # 替代 PostProcessor
)

# 旧记忆导入仍然有效
from contextmind.memory import MemoryBank, SessionManager

# 旧策略导入重定向到 memory
from contextmind.strategies import extractors, retrievers, updaters
```

**注意：** `KVCacheManager` 和 `PostProcessor` 已在 v7.3 中移除。

## 迁移指南

### 从 v7.2 迁移到 v7.3

**重要变更：**

1. **KVCacheManager 已移除**
   - KV 缓存管理属于 LLM 推理框架（vLLM, sglang等）职责
   - 请在您的 LLM 推理层配置 KV 缓存策略

2. **PostProcessor 替换为 ResponseHandler**
   ```python
   # 旧代码 (v7.2)
   await engine.update(user_input, assistant_response)
   
   # 新代码 (v7.3) - 推荐
   result = await engine.handle_response(
       user_input=user_input,
       llm_response=assistant_response,
       auto_extract=True,   # 自动提取知识
       auto_store=True      # 自动存储到记忆库
   )
   
   # 或继续使用 update() (仅记录对话，不提取知识)
   await engine.update(user_input, assistant_response)
   ```

3. **流水线步骤调整**
   - 步骤数量从 6 步减少到 5 步
   - 最后一步现在是 ResponseHandler（响应处理和记忆更新）

### 从 v7.1 迁移到 v7.2+

1. **流水线导入**：从 `contextmind.pipeline.X` 改为 `contextmind.X`
   ```python
   # 旧
   from contextmind.pipeline.compressor import ContextCompressor
   # 新
   from contextmind.compressor import ContextCompressor
   ```

2. **记忆导入**：使用 `contextmind.memory` 子模块
   ```python
   # 旧
   from contextmind.strategies.extractors import RuleBasedExtractor
   # 新
   from contextmind.memory import RuleBasedExtractor
   ```

3. **策略导入**：从 `strategies.defaults` 导入
   ```python
   # 旧
   from contextmind.strategies.optimization import CompressionStrategy
   # 新
   from contextmind.strategies.defaults import CompressionStrategy
   ```

## 设计原则

1. **模块化**：流水线中的每一步都是独立模块
2. **插件架构**：所有组件都是可插拔和可替换的
3. **向后兼容**：旧导入仍通过包装模块工作
4. **清晰分离**：Pipeline、Memory、Strategies 和 Utils 是独立的
5. **类型安全**：使用 dataclass 进行强类型检查
6. **异步优先**：所有 I/O 操作使用 async/await

## 架构优势

1. **清晰的结构**：易于理解从输入到输出的流程
2. **易于测试**：每个组件都可以独立测试
3. **灵活性**：组件可以被替换或扩展
4. **可维护性**：相关代码组织在一起
5. **可扩展性**：可以添加新组件而不破坏现有代码

## 后续步骤

- 为外部知识库实现完整的 ContextRetriever
- 添加更多 Extractor/Retriever/Updater 策略
- 增强 ResponseHandler 的响应分析能力
- 完善基于响应质量的记忆策略调整机制
