# 迁移指南

本指南帮助你从旧版本迁移到新版本的 Evolution。

---

## 📋 v7.3 → v0.4.0 迁移指南

### 概述

v0.4.0 是一个重要的功能增强版本，包含以下主要变更：
- **Utils 模块独立化** (Breaking Change)
- **知识提取能力** (New Feature)
- **增强的 DST 实现** (Enhancement)
- **ResponseHandler 增强** (Enhancement)

---

### 🚨 Breaking Changes

#### 1. Utils 模块导入路径变更 (必须修改)

**变更说明：**
- utils 模块从 `evolution/utils/` 移至根目录 `utils/`
- `examples/llm_client.py` 移至 `utils/llm_client.py`
- 旧的导入路径不再支持

**迁移步骤：**

```python
# ❌ 旧代码 (v7.3)
from evolution.utils.logger import get_logger, setup_logging, LogLevel
from evolution.utils.embedding import get_embedding
from examples.llm_client import SimpleLLMClient, LLMConfig

# ✅ 新代码 (v0.4.0)
from utils.logger import get_logger, setup_logging, LogLevel
from utils.embedding import get_embedding
from utils.llm_client import SimpleLLMClient, LLMConfig

# 或使用简化导入
from utils import get_logger, SimpleLLMClient, LLMConfig
```

**批量替换脚本：**

```bash
# 更新 logger 导入
find . -name "*.py" -type f -exec sed -i 's/from evolution\.utils\.logger import/from utils.logger import/g' {} +

# 更新 embedding 导入
find . -name "*.py" -type f -exec sed -i 's/from evolution\.utils\.embedding import/from utils.embedding import/g' {} +

# 更新 LLM 客户端导入
find . -name "*.py" -type f -exec sed -i 's/from examples\.llm_client import/from utils.llm_client import/g' {} +
```

**影响文件：**
- 所有使用 logger 的文件（~26个）
- 所有使用 SimpleLLMClient 的文件（~10个）
- 所有使用 embedding 的文件（~5个）

---

### ✨ 新特性

#### 2. 知识提取能力 (可选功能)

**新增功能：**
- 从多轮对话中自动提取结构化知识
- 支持用户偏好、事实、模式、策略、经验提取
- LLM 驱动的智能提取

**使用示例：**

```python
from utils import SimpleLLMClient

class KnowledgeExtractor:
    """知识提取器 - 从多轮对话中提取结构化知识"""
    
    def __init__(self, llm_client: SimpleLLMClient = None):
        self.llm_client = llm_client or SimpleLLMClient()
    
    async def extract_knowledge(self, dialogue: List[Dict[str, str]]) -> Dict:
        """
        从多轮对话中提取知识
        
        Args:
            dialogue: 对话列表 [{"role": "user/assistant", "content": "..."}]
            
        Returns:
            提取的知识字典：
            {
                "user_preferences": ["偏好1", "偏好2"],
                "facts": ["事实1", "事实2"],
                "patterns": ["模式1", "模式2"],
                "strategies": ["策略1", "策略2"],
                "experiences": ["经验1", "经验2"]
            }
        """
        # 实现见 test_knowledge_extraction.py
        pass
```

**测试文件：**
- 参考 `test_knowledge_extraction.py` 了解完整用法
- 包含 3 个实际场景测试（客服、技术支持、咨询）

**集成到现有代码：**

这是可选功能，无需修改现有代码。如需使用：

```python
from evolution import ContextEngine

# 启用自动知识提取
engine = ContextEngine(
    app_name="my-app",
    user_id="user-123",
    llm_client=your_llm_client,
    enable_knowledge_extraction=True  # 新参数
)

# 使用增强的 ResponseHandler
result = await engine.handle_response(
    user_input=user_input,
    llm_response=assistant_response,
    auto_extract=True,   # 自动提取知识
    auto_store=True      # 自动存储到记忆库
)

# 访问提取的知识
print(result.extracted_knowledge)
```

---

#### 3. 增强的 DST 实现 (自动兼容)

**改进说明：**
- dst 模块完整支持 ACL 2023 论文规范
- 100% 文档覆盖率（完整 docstrings）
- 100% 类型提示覆盖率
- 生产级代码质量

**新增数据结构：**

```python
from dst import DialogueStateTracker, SpecialValue, DialogueTurn
from enum import Enum
from dataclasses import dataclass

# 新增特殊值枚举
class SpecialValue(Enum):
    """ACL 2023 论文定义的特殊槽位值"""
    UNKNOWN = "?"        # 用户在询问
    DONTCARE = "dontcare"  # 用户不关心

# 增强的对话轮次
@dataclass
class DialogueTurn:
    """单个对话轮次的完整记录"""
    system_utterance: str
    user_utterance: str
    predicted_updates: Dict[str, str]
    dialogue_state: Dict[str, str]
    timestamp: float
```

**无需修改代码：**
- 所有现有 DST 代码自动兼容
- API 完全向后兼容
- 仅增强了内部实现和文档

---

#### 4. ResponseHandler 增强 (可选升级)

**新的 API：**

```python
# ✅ 旧代码 (v7.3) - 仍然支持
await engine.update(user_input, assistant_response)

# ✅ 新代码 (v0.4.0) - 推荐使用
result = await engine.handle_response(
    user_input=user_input,
    llm_response=assistant_response,
    auto_extract=True,   # 自动提取知识
    auto_store=True      # 自动存储到记忆库
)

# 访问结果
print(f"提取的知识: {result.extracted_knowledge}")
print(f"更新的记忆数: {result.memories_updated}")
```

**功能对比：**

| 方法 | 功能 | v7.3 | v0.4.0 |
|------|------|------|------|
| `update()` | 记录对话 | ✅ | ✅ |
| `update()` | 提取知识 | ❌ | ❌ |
| `handle_response()` | 记录对话 | ❌ | ✅ |
| `handle_response()` | 提取知识 | ❌ | ✅ |
| `handle_response()` | 自动存储 | ❌ | ✅ |

**推荐迁移路径：**
1. 继续使用 `update()` - 无需修改
2. 逐步迁移到 `handle_response()` - 获得知识提取功能

---

#### 5. SimpleLLMClient 增强 (自动兼容)

**新增方法：**

```python
from utils import SimpleLLMClient

client = SimpleLLMClient()

# 新增：同步 chat 方法
response = client.chat(
    messages=[{"role": "user", "content": "你好"}],
    temperature=0.7
)

# 新增：异步 chat_async 方法
response = await client.chat_async(
    messages=[{"role": "user", "content": "你好"}],
    temperature=0.7
)

# 原有方法仍然支持
response = client.generate("你好", temperature=0.7)
response = await client.generate_async("你好", temperature=0.7)
```

**无需修改代码：**
- 所有旧方法仍然支持
- 新方法为可选增强
- 完全向后兼容

---

### 🔍 迁移检查清单

完成以下步骤确保迁移成功：

- [ ] **步骤 1**: 更新所有 utils 导入路径
  ```bash
  # 运行批量替换脚本（见上文）
  ```

- [ ] **步骤 2**: 测试导入
  ```bash
  python3 -c "from utils import get_logger, SimpleLLMClient; print('✓ 导入成功')"
  ```

- [ ] **步骤 3**: 运行现有测试
  ```bash
  pytest tests/
  ```

- [ ] **步骤 4**: 验证演示程序
  ```bash
  python chat_interactive_demo.py --mode evolution
  python baseline_demo.py
  ```

- [ ] **步骤 5** (可选): 集成知识提取功能
  ```bash
  python test_knowledge_extraction.py
  ```

---

### 📊 变更影响评估

| 变更类型 | 影响范围 | 是否必须 | 工作量 |
|---------|---------|---------|--------|
| Utils 导入路径 | 高 (26个文件) | ✅ 必须 | 10分钟 |
| 知识提取功能 | 无 (新功能) | ❌ 可选 | N/A |
| DST 增强 | 无 (自动兼容) | ❌ 可选 | 0分钟 |
| ResponseHandler | 无 (向后兼容) | ❌ 可选 | 0分钟 |
| SimpleLLMClient | 无 (向后兼容) | ❌ 可选 | 0分钟 |

**总结：**
- **必须修改**: 仅 utils 导入路径（10分钟）
- **可选升级**: 知识提取、ResponseHandler（按需）
- **自动兼容**: DST、SimpleLLMClient（无需修改）

---

### 🆘 常见问题

#### Q1: 导入错误 `ModuleNotFoundError: No module named 'evolution.utils'`

**原因**: 使用了旧的导入路径

**解决方案**:
```python
# 将所有 evolution.utils.* 改为 utils.*
from utils.logger import get_logger
from utils.llm_client import SimpleLLMClient
```

#### Q2: 导入错误 `ModuleNotFoundError: No module named 'examples.llm_client'`

**原因**: llm_client 已移至 utils 模块

**解决方案**:
```python
# 将 examples.llm_client 改为 utils.llm_client
from utils.llm_client import SimpleLLMClient
```

#### Q3: 我的代码没有使用 utils，需要修改吗？

**回答**: 如果你只使用 Evolution 的高级 API，可能不需要修改。检查你的导入语句：
- 有 `from evolution.utils.*` → 需要修改
- 有 `from examples.llm_client` → 需要修改
- 只有 `from evolution import *` → 无需修改

#### Q4: 知识提取功能是强制的吗？

**回答**: 不是。这是可选功能，不影响现有代码。要使用需要：
1. 设置 `enable_knowledge_extraction=True`
2. 使用 `handle_response()` 而非 `update()`

#### Q5: 我可以继续使用 `engine.update()` 吗？

**回答**: 可以。`update()` 方法仍然支持，只是不包含知识提取功能。

---

### 📚 参考资料

- [ARCHITECTURE.md](ARCHITECTURE.md) - v0.4.0 架构文档
- [CHANGELOG.md](CHANGELOG.md) - v0.4.0 完整变更日志
- [test_knowledge_extraction.py](../test_knowledge_extraction.py) - 知识提取示例

---

## v7.1 → v7.2+ 迁移指南

## 有什么变化？

### 1. 项目结构重组

项目已重构以匹配六步流水线架构：

**之前（v7.1）**：
```
evolution/
├── pipeline.py （所有流水线组件在一个文件中）
├── memory.py （所有记忆组件在一个文件中）
├── strategies/ （extractors、retrievers、updaters）
└── ...

demos/ （示例应用）
```

**之后（v7.2+）**：
```
evolution/
├── preprocessor.py （步骤 1）
├── retriever.py （步骤 2）
├── compressor.py （步骤 3）
├── reorderer.py （步骤 4）
├── kvcache.py （步骤 5）
├── postprocessor.py （步骤 6）
├── memory/ （具有 4 个子模块的 MemoryBank）
│   ├── bank.py
│   ├── extractor.py
│   ├── retriever.py
│   └── updater.py
└── ...

examples/ （从 demos/ 重命名）
```

### 2. 导入路径变更

#### 流水线组件

```python
# ❌ 旧（v7.1）
from evolution.pipeline import InputPreprocessor, ContextCompressor

# ✅ 新（v7.2+）- 推荐
from evolution.preprocessor import InputPreprocessor
from evolution.compressor import ContextCompressor

# ✅ 兼容 - 通过向后兼容包装器仍然有效
from evolution.pipeline import InputPreprocessor, ContextCompressor
```

#### 记忆组件

```python
# ❌ 旧（v7.1）
from evolution.strategies.extractors import RuleBasedExtractor
from evolution.strategies.retrievers import SemanticSearchRetriever
from evolution.strategies.updaters import SimpleUpdater

# ✅ 新（v7.2+）- 推荐
from evolution.memory import (
    RuleBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
)

# ✅ 兼容 - 通过向后兼容仍然有效
from evolution.strategies import extractors, retrievers, updaters
extractor = extractors.RuleBasedExtractor()
```

#### 策略基类

```python
# ❌ 旧（v7.1）
from evolution.strategies.optimization import CompressionStrategy
from evolution.strategies.base import CompressionStrategy  # 错误位置

# ✅ 新（v7.2+）
from evolution.strategies.defaults import CompressionStrategy, RerankingStrategy
from evolution.strategies.base import OptimizationStrategy  # 基础接口
```

### 3. 文件重命名

| 旧名称 | 新名称 | 位置 |
|----------|----------|----------|
| `config_api.py` | `config.py` | `evolution/` |
| `demos/` | `examples/` | 根目录 |
| `gradio_demo.py` | `gradio_app.py` | `examples/` |
| `interactive_demo.py` | `interactive_app.py` | `examples/` |

## 分步迁移

### 步骤 1：更新导入

在代码库中运行查找-替换：

```bash
# 流水线导入
find . -name "*.py" -exec sed -i 's/from evolution.pipeline.preprocessor import/from evolution.preprocessor import/g' {} +
find . -name "*.py" -exec sed -i 's/from evolution.pipeline.compressor import/from evolution.compressor import/g' {} +
find . -name "*.py" -exec sed -i 's/from evolution.pipeline.reorderer import/from evolution.reorderer import/g' {} +
find . -name "*.py" -exec sed -i 's/from evolution.pipeline.postprocessor import/from evolution.postprocessor import/g' {} +

# 记忆导入
find . -name "*.py" -exec sed -i 's/from evolution.strategies.extractors import/from evolution.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from evolution.strategies.retrievers import/from evolution.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from evolution.strategies.updaters import/from evolution.memory import/g' {} +

# 策略默认值
find . -name "*.py" -exec sed -i 's/from evolution.strategies.optimization import/from evolution.strategies.defaults import/g' {} +
```

### 步骤 2：更新文件引用

如果你导入了 examples/demos：

```python
# ❌ 旧
from demos.llm_client import LLMClient

# ✅ 新
from examples.llm_client import LLMClient
```

### 步骤 3：验证导入

测试你的导入是否正常工作：

```python
# 测试脚本
from evolution import (
    Evolution,
    ContextEngine,
    MemoryBank,
    SessionManager,
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    PostProcessor,
    KVCacheManager,
)

from evolution.memory import (
    RuleBasedExtractor,
    LLMBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
)

print("✓ 所有导入成功！")
```

## 向后兼容性

### 什么仍然有效？

由于向后兼容包装器，以下旧导入模式**仍然有效**：

✅ `from evolution.pipeline import InputPreprocessor`  
✅ `from evolution.memory import MemoryBank, KVCacheManager`  
✅ `from evolution.strategies import extractors, retrievers, updaters`

### 什么改变了？

❌ `evolution.pipeline` 现在是包装器，而不是包  
❌ `evolution.strategies.optimization` 不存在（使用 `strategies.defaults`）  
❌ `demos/` 目录重命名为 `examples/`

## 常见迁移问题

### 问题 1：模块未找到

```
ModuleNotFoundError: No module named 'evolution.pipeline.compressor'
```

**解决方案**：改为：
```python
from evolution.compressor import ContextCompressor
# 或使用向后兼容导入
from evolution.pipeline import ContextCompressor
```

### 问题 2：无法导入 CompressionStrategy

```
ImportError: cannot import name 'CompressionStrategy' from 'evolution.strategies.base'
```

**解决方案**：从 `defaults` 导入：
```python
from evolution.strategies.defaults import CompressionStrategy
```

### 问题 3：提取器导入失败

```
ModuleNotFoundError: No module named 'evolution.strategies.extractors'
```

**解决方案**：从 memory 子模块导入：
```python
from evolution.memory import RuleBasedExtractor, LLMBasedExtractor
```

## 测试你的迁移

运行以下检查：

1. **导入测试**：
   ```bash
   python3 -c "from evolution import *; print('OK')"
   ```

2. **向后兼容性测试**：
   ```bash
   python3 -c "from evolution.pipeline import InputPreprocessor; print('OK')"
   ```

3. **运行测试**：
   ```bash
   pytest tests/
   ```

4. **检查示例**：
   ```bash
   python3 examples/plugin_examples.py
   ```

## 需要帮助？

如果在迁移过程中遇到问题：

1. 查看 `ARCHITECTURE.md` 了解完整的新结构
2. 查看上面的导入示例
3. 暂时使用向后兼容的导入
4. 在 GitHub 上提交问题，附上你的具体错误

## 推荐：逐步迁移

你不必一次性迁移所有内容：

1. **阶段 1**：继续使用向后兼容的导入
2. **阶段 2**：在新代码中更新导入为新风格
3. **阶段 3**：在方便时逐步重构旧代码

旧的导入模式将通过向后兼容包装器无限期地继续工作。
