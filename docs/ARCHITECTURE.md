# ContextMind 架构 (v0.4.0)

本文档描述 ContextMind v0.4.0 的架构设计和实现细节。

## 版本信息

- **当前版本**: v0.4.0
- **发布日期**: 2026-01-29
- **主要更新**: Utils独立化、知识提取能力、DST增强

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

**架构变更（v0.4.0）：**
- ✅ **Utils独立化** - utils模块移至根目录，完全不依赖contextmind/baseline
- ✅ **知识提取增强** - 新增LLM驱动的知识提取能力
- ✅ **DST完整实现** - 完整的ACL 2023论文合规性实现
- ✅ **ResponseHandler增强** - 完整的响应处理和知识提取流程
- ❌ **移除** KVCacheManager - KV缓存管理属于LLM推理框架职责

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
│   ├── pipeline/
│   │   ├── preprocessor.py      # 步骤 1：InputPreprocessor
│   │   ├── context_retriever.py # 步骤 2：ContextRetriever（占位符）
│   │   ├── compressor.py        # 步骤 3：ContextCompressor
│   │   ├── reorderer.py         # 步骤 4：ContextReorderer
│   │   ├── response_handler.py  # 步骤 5：ResponseHandler (v7.4增强)
│   │   └── summarizer.py        # ConversationSummarizer（由压缩器使用）
│   │
│   │ # MemoryBank 模块 - 4 个子模块
│   ├── memory/
│   │   ├── __init__.py      # 导出所有记忆组件
│   │   ├── bank.py          # 主 MemoryBank 类
│   │   ├── session.py       # SessionManager
│   │   ├── extractor.py     # 知识提取器 (v7.4增强)
│   │   ├── retriever.py     # 检索相关记忆
│   │   └── updater.py       # 记忆更新（添加/删除/更新）
│   │
│   ├── strategies/          # 策略接口
│   │   ├── __init__.py      # 从 memory 重新导出
│   │   ├── base.py          # 基础策略接口
│   │   └── defaults.py      # 默认实现
│   │
│   ├── core/                # 核心系统组件
│   │   ├── __init__.py
│   │   ├── configs.py       # 配置类
│   │   ├── data_models.py   # 数据模型
│   │   ├── models.py        # 领域模型
│   │   ├── registry.py      # 注册系统
│   │   └── types.py         # 类型定义
│   │
│   └── evolution/           # 进化式优化（高级功能）
│       ├── __init__.py
│       ├── evolutionary_updater.py
│       └── feedback_system.py
│
├── utils/                   # 独立工具模块 (v7.4 移至根目录)
│   ├── __init__.py          # 导出所有工具
│   ├── logger.py            # 统一日志系统
│   ├── llm_client.py        # 统一 LLM 客户端 (v7.4增强)
│   ├── embedding.py         # 嵌入向量工具
│   └── data_models.py       # 数据模型
│
├── dst/                # 增强的 DST 实现 (v7.4)
│   ├── __init__.py
│   └── dialogue_state_tracker.py  # 完整 ACL 2023 实现
│
├── examples/                # 示例和演示
│   ├── chat_app.py
│   ├── callcenter_app.py
│   ├── gradio_app.py
│   ├── interactive_app.py
│   └── plugin_examples.py
│
├── docs/                    # 文档
│   ├── ARCHITECTURE.md      # 本文档 (v0.4.0)
│   ├── BASIC_DST_DOCUMENTATION.md  # DST文档
│   ├── CHANGELOG.md         # 变更日志 (v0.4.0)
│   ├── MIGRATION.md         # 迁移指南 (v0.4.0)
│   └── DST_*.md            # DST 增强文档
│
├── test_knowledge_extraction.py  # 知识提取测试 (v7.4新增)
├── baseline_demo.py         # 基础版本演示
├── chat_interactive_demo.py # 聊天命令行演示
├── chat_gradio_demo.py      # 聊天 Web 演示
├── callcenter_*_demo.py     # 客服场景演示
├── tests/                   # 单元和集成测试
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

#### 步骤 5：ResponseHandler (`response_handler.py`) - v7.4 增强
- **目的**：处理 LLM 响应并更新记忆库
- **职责**：
  1. 解析 LLM 响应
  2. 从响应中提取知识（新增）
  3. 自动更新记忆库
  4. 记录完整对话轮次
- **特点**：形成完整的记忆更新闭环
- **v7.4 新特性**：
  - 支持自动知识提取 (`auto_extract=True`)
  - 集成 LLM 驱动的知识提取器
  - 提取用户偏好、事实、模式、策略和经验
  - 可选的自动存储到记忆库

### 2. MemoryBank 模块 (`memory/`)

MemoryBank 实现了 4 子模块架构：

#### 2.1 Extractor (`memory/extractor.py`) - v7.4 增强
- **目的**：提取高价值信息用于长期存储
- **实现**：
  - `RuleBasedExtractor`：模式匹配（轻量级）
  - `LLMBasedExtractor`：大语言模型辅助提取（高端，v7.4增强）
  - `ImportancePredictorExtractor`：基于机器学习的重要性评分
- **v7.4 新特性**：
  - 增强的 LLM 驱动知识提取
  - 支持从多轮对话中提取结构化知识
  - 提取用户偏好、事实、对话模式、策略和经验
  - 可自定义提取策略和模板

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

## v0.4.0 核心特性

### 1. 独立的 Utils 模块

**变更说明：**
- utils 模块从 `contextmind/utils/` 移至根目录 `utils/`
- 完全独立，不依赖 contextmind 或 dst 模块
- 统一的工具供所有模式使用（DST 和 ContextMind）

**新结构：**
```python
utils/
├── __init__.py       # 导出所有工具
├── logger.py         # 统一日志系统
├── llm_client.py     # 统一 LLM 客户端
├── embedding.py      # 嵌入向量工具
└── data_models.py    # 数据模型
```

**导入示例：**
```python
# v7.4 新导入方式
from utils import get_logger, SimpleLLMClient, LLMConfig
from utils.embedding import get_embedding

# 旧方式不再支持
# from contextmind.utils.logger import get_logger  ❌
```

### 2. 知识提取能力

**新增功能：**
- 从多轮对话中自动提取结构化知识
- LLM 驱动的智能提取
- 支持多种知识类型

**知识类型：**
1. **user_preferences**: 用户偏好和需求
2. **facts**: 事实性知识和信息
3. **patterns**: 对话模式和流程
4. **strategies**: 有效的策略和方法
5. **experiences**: 经验总结和教训

**使用示例：**
```python
from utils import SimpleLLMClient

class KnowledgeExtractor:
    async def extract_knowledge(self, dialogue):
        # 从对话中提取结构化知识
        return {
            "user_preferences": ["偏好1", "偏好2"],
            "facts": ["事实1", "事实2"],
            "patterns": ["模式1", "模式2"],
            "strategies": ["策略1", "策略2"],
            "experiences": ["经验1", "经验2"]
        }
```

**测试文件：**
- `test_knowledge_extraction.py` - 包含3个实际场景测试：
  - 客服对话知识提取
  - 技术支持知识提取
  - 咨询对话知识提取

### 3. 增强的 DST 实现

**完整的 ACL 2023 论文合规性：**
- ✅ 100% 文档覆盖率（完整的 docstrings）
- ✅ 100% 类型提示覆盖率
- ✅ 生产级代码质量
- ✅ 增强的数据结构

**改进组件：**
1. **PromptManager** - 槽位管理和约束验证
2. **ResponseParser** - 鲁棒的 JSON 解析和幻觉过滤
3. **DialogueStateTracker** - 完整的状态追踪实现

**新增数据结构：**
```python
from enum import Enum
from dataclasses import dataclass

class SpecialValue(Enum):
    """Special slot values (ACL 2023 paper)."""
    UNKNOWN = "?"        # 用户在询问
    DONTCARE = "dontcare"  # 用户不关心

@dataclass
class DialogueTurn:
    """单个对话轮次的完整记录."""
    system_utterance: str
    user_utterance: str
    predicted_updates: Dict[str, str]
    dialogue_state: Dict[str, str]
    timestamp: float
```

### 4. ResponseHandler 增强

**新的 API：**
```python
# v7.4 推荐方式 - 自动知识提取
result = await engine.handle_response(
    user_input=user_input,
    llm_response=assistant_response,
    auto_extract=True,   # 自动提取知识
    auto_store=True      # 自动存储到记忆库
)

# 兼容方式 - 仅记录对话
await engine.update(user_input, assistant_response)
```

**功能增强：**
- 自动知识提取开关
- 自动存储到记忆库
- 完整的对话轮次记录
- 提取结果返回

## 导入模式

### 推荐（v7.4+）

```python
# Utils 模块 - 从根目录导入
from utils import get_logger, SimpleLLMClient, LLMConfig
from utils.embedding import get_embedding
from utils.data_models import Message, KnowledgeItem

# 流水线组件
from contextmind.pipeline import (
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,
)

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

# DST 组件（增强实现）
from dst import (
    DialogueStateTracker,
    PromptManager,
    ResponseParser,
    SpecialValue,
    DialogueTurn,
)
```

### 向后兼容（遗留代码）

```python
# 旧流水线导入仍然有效
from contextmind.pipeline import (
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    ResponseHandler,
)

# 旧记忆导入仍然有效
from contextmind.memory import MemoryBank, SessionManager

# 旧策略导入重定向到 memory
from contextmind.strategies import extractors, retrievers, updaters
```

**注意：** 
- `KVCacheManager` 和 `PostProcessor` 已在 v7.4 中移除
- Utils 的旧导入路径 (`contextmind.utils.*`, `examples.llm_client`) 不再支持

## 迁移指南

### 从 v7.3 迁移到 v0.4.0

**重要变更：**

1. **Utils模块独立化** (Breaking Change)
   - utils模块已移至根目录
   - 完全不依赖contextmind或baseline模块
   - 必须更新所有导入路径
   
   ```python
   # ❌ 旧代码 (v7.3)
   from contextmind.utils.logger import get_logger
   from examples.llm_client import SimpleLLMClient
   
   # ✅ 新代码 (v7.4)
   from utils.logger import get_logger
   from utils.llm_client import SimpleLLMClient
   ```

2. **知识提取能力** (New Feature)
   - 新增 LLM 驱动的知识提取
   - 可选功能，不影响现有代码
   - 参考 `test_knowledge_extraction.py` 了解用法

3. **增强的DST实现** (Enhancement)
   - baseline模块现在完整支持ACL 2023规范
   - 100% 文档和类型提示覆盖
   - 向后兼容，无需修改代码

4. **ResponseHandler 增强** (Enhancement)
   ```python
   # 旧代码 (v7.3) - 仍然支持
   await engine.update(user_input, assistant_response)
   
   # 新代码 (v7.4) - 推荐
   result = await engine.handle_response(
       user_input=user_input,
       llm_response=assistant_response,
       auto_extract=True,   # 自动提取知识
       auto_store=True      # 自动存储到记忆库
   )
   ```

5. **SimpleLLMClient 新方法** (Enhancement)
   - 新增 `chat(messages, temperature)` 同步方法
   - 新增 `chat_async(messages, temperature)` 异步方法
   - 支持标准消息列表格式
   - 自动兼容，无需修改现有代码

### 从 v7.2 迁移到 v7.4

**重要变更：**

1. **KVCacheManager 已移除**
   - KV 缓存管理属于 LLM 推理框架（vLLM, sglang等）职责
   - 请在您的 LLM 推理层配置 KV 缓存策略

2. **PostProcessor 替换为 ResponseHandler**
   ```python
   # 旧代码 (v7.2)
   await engine.update(user_input, assistant_response)
   
   # 新代码 (v7.4) - 推荐
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
