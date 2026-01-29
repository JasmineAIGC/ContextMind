# ContextMind 变更日志

## [2026-01-29] - Utils 模块重组和统一工具使用 🔧

### 重大变更 (Major Changes)

**将 utils 移动到根目录作为通用工具模块：**
- 移动 `contextmind/utils/` → `utils/` (根目录)
- 移动 `examples/llm_client.py` → `utils/llm_client.py`
- 所有模式（DST 和 ContextMind）现在使用相同的工具

**新的 utils 模块结构：**
```
utils/  (根目录)
├── __init__.py       # 导出所有工具
├── logger.py         # 统一的日志系统
├── llm_client.py     # 统一的 LLM 客户端
└── embedding.py      # 嵌入向量工具
```

### 改进 (Changed)

**统一导入模式：**
```python
# Before
from contextmind.utils.logger import get_logger
from examples.llm_client import SimpleLLMClient

# After
from utils.logger import get_logger
from utils.llm_client import SimpleLLMClient
```

**更新的文件（26 个）：**
- Demo 文件（5 个）
- Examples（2 个）
- contextmind/core/（5 个）
- contextmind/memory/（6 个）
- contextmind/pipeline/（6 个）
- contextmind/evolution/（2 个）

### 新增 (Added)

**utils/__init__.py 导出：**
- Logger: get_logger, setup_logging, LogLevel, ContextMindLogger
- LLM Client: SimpleLLMClient, LLMConfig
- Embedding: (通过内部导入)

### 删除 (Removed)

- `contextmind/utils/` 目录（已移到根目录）
- `examples/llm_client.py`（已移到 utils/）

### 影响 (Impact)

- ✅ DST 基础模式和 ContextMind 完整模式使用相同的 logger
- ✅ 所有模式从 .env 读取 LLM 配置
- ✅ 统一的工具模块，便于维护
- ✅ 更简洁的导入路径

### 迁移指南 (Migration Guide)

如果你的代码使用了旧的导入路径，请更新：
```python
# 更新 logger 导入
from contextmind.utils.logger import get_logger
→ from utils.logger import get_logger

# 更新 LLM 客户端导入
from examples.llm_client import SimpleLLMClient
→ from utils.llm_client import SimpleLLMClient
```

---

## [2026-01-29] - DST 模式错误修复 🔧

### 修复 (Fixed)

**问题 1: Gradio Demo DST 模式报错**
- **错误**: `'SimpleLLMClient' object has no attribute 'chat_async'`
- **位置**: chat_gradio_demo.py, callcenter_gradio_demo.py
- **原因**: SimpleLLMClient 缺少 chat_async 方法
- **修复**: 
  - 为 SimpleLLMClient 添加 `chat(messages, temperature)` 方法
  - 为 SimpleLLMClient 添加 `chat_async(messages, temperature)` 方法
  - 支持标准的消息列表格式调用

**问题 2: Interactive Demo DST 模式无真实回复**
- **错误**: 只显示 "[基础模式模拟回复] 收到您的消息"
- **位置**: chat_interactive_demo.py, callcenter_interactive_demo.py
- **原因**: 未初始化 LLM 客户端，使用硬编码模拟回复
- **修复**:
  - 初始化 SimpleLLMClient 并传递给 DialogueStateTracker
  - 使用真实 LLM 生成回复而非模拟回复
  - 构建包含对话历史和状态的提示词

### 新增 (Added)
- 新增 test_dst_fixes.py 测试文件，验证 DST 修复

### 改进 (Changed)
- SimpleLLMClient 现在完全兼容 DialogueStateTracker
- 所有 demo 的基础 DST 模式现在都能正常工作

### 影响
- ✅ 所有 DST 模式错误已修复
- ✅ Interactive 和 Gradio demos 都能正常工作
- ✅ 基础 DST 模式可以生成真实的 LLM 回复

---

# ContextMind 变更日志

## 2026-01-29 - 移除槽位模板代码

### 重大变更

**简化项目结构，现在只有两个版本：**
1. **基于 DST 的基础版本**（baseline） - ACL 2023 论文实现
2. **基于 ContextMind 的完整版本** - 五层架构上下文工程

#### 删除的文件
- `slot_template_demo.py` - 槽位模板演示
- `comparison_experiment.py` - 对比实验（使用了槽位模板）
- `baseline/engine.py` - SlotTemplateEngine
- `baseline/template_manager.py` - TemplateManager
- `baseline/intent_extractor.py` - IntentExtractor

#### 保留的文件
- `baseline/dialogue_state_tracker.py` - 基础 DST 实现（这是基础版本）
- `baseline_demo.py` - 基础版本演示

#### 更新的文件
- `baseline/__init__.py` - 只导出 DST 相关类
- `prompts.py` - 删除 SLOT_TEMPLATE_SYSTEM_PROMPT
- `README.md` - 更新项目结构和说明

### 说明

**现在只有两个版本：**
- **基础版本（Baseline）** - 基于 ACL 2023 DST 论文的 Zero-shot 对话状态追踪
- **完整版本（ContextMind）** - 五层架构的上下文工程框架

槽位模板是一个中间实验方案，已经不再需要。基础版本指的就是基于 DST 的实现。

### 如何更新你的代码

如果你之前使用了这些文件：

```bash
# 不再可用
python slot_template_demo.py
python comparison_experiment.py

# 请使用
python baseline_demo.py  # 基础 DST 版本
python chat_interactive_demo.py --mode basic  # 在演示中使用基础模式
```

### 影响评估

- ✅ 项目结构更清晰
- ✅ 只有两个明确的版本对比
- ✅ 减少代码维护负担
- ⚠️ 删除了槽位模板相关代码（已不再需要）

---

## 2026-01-29 - 文档清理和简化

### 重大变更

#### 1. 文档清理
- **删除了 15 个不必要的文档**，保留 3 个核心文档：
  - `ARCHITECTURE.md` - 详细架构说明
  - `BASIC_DST_DOCUMENTATION.md` - 基础 DST 实现文档
  - `MIGRATION.md` - 版本迁移指南

#### 2. README 精简
- README.md 从 584 行减少到 238 行（减少 59%）
- 删除冗余内容，突出核心特性
- 简化示例代码
- 更清晰的项目结构说明

#### 3. 演示文件重命名（重要！）

**基础版本明确化：**
- `basic_dst_demo.py` → `baseline_demo.py` ⭐
  - **这是 ContextMind 项目的基础版本（baseline）**
  - 基于 ACL 2023 论文的对话状态追踪（DST）实现
  - 用于与 ContextMind 完整框架进行对比

- `baseline_demo.py` → `slot_template_demo.py`
  - 槽位模板引擎演示
  - 简单的槽位填充方法
  - 不是主要的基础版本

**重要说明：**
- **基础版本** = 基于 ACL 2023 DST 的实现
- 只有一个"基础版本"，就是 `baseline_demo.py`（原 `basic_dst_demo.py`）

### 如何更新你的代码

如果你之前引用了这些文件，请更新：

```bash
# 旧命令
python basic_dst_demo.py

# 新命令
python baseline_demo.py
```

### 文件对照表

| 旧文件名 | 新文件名 | 说明 |
|---------|---------|------|
| `basic_dst_demo.py` | `baseline_demo.py` | 基础版本演示（ACL 2023 DST）|
| `baseline_demo.py` | `slot_template_demo.py` | 槽位模板演示 |

### 删除的文档

以下文档已被删除（不再需要）：
- ANALYSIS_AND_DESIGN.md
- ARCHITECTURE_REFACTORING_PLAN.md
- BASELINE_IMPLEMENTATION.md
- BASELINE_QUICKSTART.md
- BASELINE_README.md
- BASIC_DST_SUMMARY.md
- DESIGN.md
- EVOLUTION_MODULE_ANALYSIS.md
- EVOLUTION_MODULE_SIMPLIFICATION.md
- IMPLEMENTATION_SUMMARY.md
- MODULE_REORGANIZATION.md
- RENAME_AND_MODE_SUMMARY.md
- REPOSITORY_CLEANUP_SUMMARY.md
- UNDERSTANDING_OBSERVATION_FEEDBACK_LEARNING.md
- arch_by_me.md

这些是历史记录和内部分析文档，对用户不重要。

### 影响评估

- ✅ 所有核心功能保持不变
- ✅ API 接口完全兼容
- ✅ 只是文档和演示文件的重命名
- ⚠️ 需要更新脚本中的演示文件名引用

### 优势

1. **更清晰的文档结构** - 只保留必要文档
2. **更简洁的 README** - 更易于快速理解项目
3. **明确的基础版本定义** - 不再混淆
4. **更好的维护性** - 减少文档维护负担
