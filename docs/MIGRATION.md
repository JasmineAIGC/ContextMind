# Migration Guide: v7.1 → v7.2+

This guide helps you migrate from the old structure to the new optimized architecture.

## What Changed?

### 1. Project Structure Reorganization

The project has been restructured to match the 6-step pipeline architecture:

**Before (v7.1)**:
```
contextmind/
├── pipeline.py (all pipeline components in one file)
├── memory.py (all memory components in one file)
├── strategies/ (extractors, retrievers, updaters)
└── ...

demos/ (example applications)
```

**After (v7.2+)**:
```
contextmind/
├── preprocessor.py (Step 1)
├── retriever.py (Step 2)
├── compressor.py (Step 3)
├── reorderer.py (Step 4)
├── kvcache.py (Step 5)
├── postprocessor.py (Step 6)
├── memory/ (MemoryBank with 4 sub-modules)
│   ├── bank.py
│   ├── extractor.py
│   ├── retriever.py
│   └── updater.py
└── ...

examples/ (renamed from demos/)
```

### 2. Import Path Changes

#### Pipeline Components

```python
# ❌ OLD (v7.1)
from contextmind.pipeline import InputPreprocessor, ContextCompressor

# ✅ NEW (v7.2+) - Recommended
from contextmind.preprocessor import InputPreprocessor
from contextmind.compressor import ContextCompressor

# ✅ COMPATIBLE - Still works via backward compatibility wrapper
from contextmind.pipeline import InputPreprocessor, ContextCompressor
```

#### Memory Components

```python
# ❌ OLD (v7.1)
from contextmind.strategies.extractors import RuleBasedExtractor
from contextmind.strategies.retrievers import SemanticSearchRetriever
from contextmind.strategies.updaters import SimpleUpdater

# ✅ NEW (v7.2+) - Recommended
from contextmind.memory import (
    RuleBasedExtractor,
    SemanticSearchRetriever,
    SimpleUpdater,
)

# ✅ COMPATIBLE - Still works via backward compatibility
from contextmind.strategies import extractors, retrievers, updaters
extractor = extractors.RuleBasedExtractor()
```

#### Strategy Base Classes

```python
# ❌ OLD (v7.1)
from contextmind.strategies.optimization import CompressionStrategy
from contextmind.strategies.base import CompressionStrategy  # Wrong location

# ✅ NEW (v7.2+)
from contextmind.strategies.defaults import CompressionStrategy, RerankingStrategy
from contextmind.strategies.base import OptimizationStrategy  # Base interface
```

### 3. File Renames

| Old Name | New Name | Location |
|----------|----------|----------|
| `config_api.py` | `config.py` | `contextmind/` |
| `demos/` | `examples/` | Root directory |
| `gradio_demo.py` | `gradio_app.py` | `examples/` |
| `interactive_demo.py` | `interactive_app.py` | `examples/` |

## Step-by-Step Migration

### Step 1: Update Imports

Run a find-replace in your codebase:

```bash
# Pipeline imports
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.preprocessor import/from contextmind.preprocessor import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.compressor import/from contextmind.compressor import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.reorderer import/from contextmind.reorderer import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.pipeline.postprocessor import/from contextmind.postprocessor import/g' {} +

# Memory imports
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.extractors import/from contextmind.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.retrievers import/from contextmind.memory import/g' {} +
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.updaters import/from contextmind.memory import/g' {} +

# Strategy defaults
find . -name "*.py" -exec sed -i 's/from contextmind.strategies.optimization import/from contextmind.strategies.defaults import/g' {} +
```

### Step 2: Update File References

If you import examples/demos:

```python
# ❌ OLD
from demos.llm_client import LLMClient

# ✅ NEW
from examples.llm_client import LLMClient
```

### Step 3: Verify Imports

Test that your imports work:

```python
# Test script
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

print("✓ All imports successful!")
```

## Backward Compatibility

### What Still Works?

The following old import patterns **still work** due to backward compatibility wrappers:

✅ `from contextmind.pipeline import InputPreprocessor`  
✅ `from contextmind.memory import MemoryBank, KVCacheManager`  
✅ `from contextmind.strategies import extractors, retrievers, updaters`

### What Changed?

❌ `contextmind.pipeline` is now a wrapper, not a package  
❌ `contextmind.strategies.optimization` doesn't exist (use `strategies.defaults`)  
❌ `demos/` directory renamed to `examples/`

## Common Migration Issues

### Issue 1: Module Not Found

```
ModuleNotFoundError: No module named 'contextmind.pipeline.compressor'
```

**Solution**: Change to:
```python
from contextmind.compressor import ContextCompressor
# OR use backward compatible import
from contextmind.pipeline import ContextCompressor
```

### Issue 2: Cannot Import CompressionStrategy

```
ImportError: cannot import name 'CompressionStrategy' from 'contextmind.strategies.base'
```

**Solution**: Import from `defaults` instead:
```python
from contextmind.strategies.defaults import CompressionStrategy
```

### Issue 3: Extractor Import Fails

```
ModuleNotFoundError: No module named 'contextmind.strategies.extractors'
```

**Solution**: Import from memory submodule:
```python
from contextmind.memory import RuleBasedExtractor, LLMBasedExtractor
```

## Testing Your Migration

Run the following checks:

1. **Import Test**:
   ```bash
   python3 -c "from contextmind import *; print('OK')"
   ```

2. **Backward Compatibility Test**:
   ```bash
   python3 -c "from contextmind.pipeline import InputPreprocessor; print('OK')"
   ```

3. **Run Your Tests**:
   ```bash
   pytest tests/
   ```

4. **Check Examples**:
   ```bash
   python3 examples/plugin_examples.py
   ```

## Need Help?

If you encounter issues during migration:

1. Check `ARCHITECTURE.md` for the complete new structure
2. Review the import examples above
3. Use backward compatible imports temporarily
4. File an issue on GitHub with your specific error

## Recommended: Gradual Migration

You don't have to migrate everything at once:

1. **Phase 1**: Keep using backward compatible imports
2. **Phase 2**: Update imports to new style in new code
3. **Phase 3**: Gradually refactor old code when convenient

The old import patterns will continue to work indefinitely through the backward compatibility wrappers.
