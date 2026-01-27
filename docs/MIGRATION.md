# 迁移指南：v7.1 → v7.2+

本指南帮助你从旧结构迁移到新的优化架构。

## 有什么变化？

### 1. 项目结构重组

项目已重构以匹配六步流水线架构：

**之前（v7.1）**：
```
contextmind/
├── pipeline.py （所有流水线组件在一个文件中）
├── memory.py （所有记忆组件在一个文件中）
├── strategies/ （extractors、retrievers、updaters）
└── ...

demos/ （示例应用）
```

**之后（v7.2+）**：
```
contextmind/
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
from contextmind.pipeline import InputPreprocessor, ContextCompressor

# ✅ 新（v7.2+）- 推荐
from contextmind.preprocessor import InputPreprocessor
from contextmind.compressor import ContextCompressor

# ✅ 兼容 - 通过向后兼容包装器仍然有效
from contextmind.pipeline import InputPreprocessor, ContextCompressor
```

#### 记忆组件

```python
# ❌ 旧（v7.1）
from contextmind.strategies.extractors import RuleBasedExtractor
from contextmind.strategies.retrievers import SemanticSearchRetriever
from contextmind.strategies.updaters import SimpleUpdater

# ✅ 新（v7.2+）- 推荐
from contextmind.memory import (
    RuleBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
)

# ✅ 兼容 - 通过向后兼容仍然有效
from contextmind.strategies import extractors, retrievers, updaters
extractor = extractors.RuleBasedExtractor()
```

#### 策略基类

```python
# ❌ 旧（v7.1）
from contextmind.strategies.optimization import CompressionStrategy
from contextmind.strategies.base import CompressionStrategy  # 错误位置

# ✅ 新（v7.2+）
from contextmind.strategies.defaults import CompressionStrategy, RerankingStrategy
from contextmind.strategies.base import OptimizationStrategy  # 基础接口
```

### 3. 文件重命名

| 旧名称 | 新名称 | 位置 |
|----------|----------|----------|
| `config_api.py` | `config.py` | `contextmind/` |
| `demos/` | `examples/` | 根目录 |
| `gradio_demo.py` | `gradio_app.py` | `examples/` |
| `interactive_demo.py` | `interactive_app.py` | `examples/` |

## 分步迁移

### 步骤 1：更新导入

在代码库中运行查找-替换：

```bash
# 流水线导入
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.preprocessor import/from contextmind.preprocessor import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.compressor import/from contextmind.compressor import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.reorderer import/from contextmind.reorderer import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.postprocessor import/from contextmind.postprocessor import/g' {} +

# 记忆导入
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.extractors import/from contextmind.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.retrievers import/from contextmind.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.updaters import/from contextmind.memory import/g' {} +

# 策略默认值
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.optimization import/from contextmind.strategies.defaults import/g' {} +
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
from contextmind import (
    ContextMind,
    ContextEngine,
    MemoryBank,
    SessionManager,
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    PostProcessor,
    KVCacheManager,
)

from contextmind.memory import (
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

✅ `from contextmind.pipeline import InputPreprocessor`  
✅ `from contextmind.memory import MemoryBank, KVCacheManager`  
✅ `from contextmind.strategies import extractors, retrievers, updaters`

### 什么改变了？

❌ `contextmind.pipeline` 现在是包装器，而不是包  
❌ `contextmind.strategies.optimization` 不存在（使用 `strategies.defaults`）  
❌ `demos/` 目录重命名为 `examples/`

## 常见迁移问题

### 问题 1：模块未找到

```
ModuleNotFoundError: No module named 'contextmind.pipeline.compressor'
```

**解决方案**：改为：
```python
from contextmind.compressor import ContextCompressor
# 或使用向后兼容导入
from contextmind.pipeline import ContextCompressor
```

### 问题 2：无法导入 CompressionStrategy

```
ImportError: cannot import name 'CompressionStrategy' from 'contextmind.strategies.base'
```

**解决方案**：从 `defaults` 导入：
```python
from contextmind.strategies.defaults import CompressionStrategy
```

### 问题 3：提取器导入失败

```
ModuleNotFoundError: No module named 'contextmind.strategies.extractors'
```

**解决方案**：从 memory 子模块导入：
```python
from contextmind.memory import RuleBasedExtractor, LLMBasedExtractor
```

## 测试你的迁移

运行以下检查：

1. **导入测试**：
   ```bash
   python3 -c "from contextmind import *; print('OK')"
   ```

2. **向后兼容性测试**：
   ```bash
   python3 -c "from contextmind.pipeline import InputPreprocessor; print('OK')"
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
