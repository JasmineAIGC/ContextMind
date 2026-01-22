# ContextMind v7.2 Logging System

## Overview

ContextMind v7.2 includes a unified, professional logging system designed for context engineering workflows. The system provides three logging levels to support different use cases:

- **BASIC**: Pipeline-level logging (inputs, outputs, major events)
- **DETAILED**: Step-level logging (individual steps within pipeline)
- **DEBUG**: Complete logging (all internal details)

## Features

✅ **Unified Interface**: Single ContextMindLogger class for all modules  
✅ **Three-Level System**: BASIC → DETAILED → DEBUG  
✅ **Consistent Formatting**: Standardized log messages across all modules  
✅ **Global Configuration**: Set logging level once for entire framework  
✅ **Module Scoping**: Each module has its own logger instance  

## Quick Start

### Basic Setup

```python
from contextmind import setup_logging, LogLevel

# Basic mode (default) - Pipeline-level logs only
setup_logging(LogLevel.BASIC)

# Detailed mode - Step-level logs
setup_logging(LogLevel.DETAILED)

# Debug mode - All logs including internal details
setup_logging(LogLevel.DEBUG)
```

### Running Demos

```bash
# Basic mode (default)
python interactive_demo.py

# Detailed mode
python interactive_demo.py --detailed

# Debug mode (maximum verbosity)
python interactive_demo.py --debug
```

## Logging Levels Explained

### BASIC Mode (Default)

**What you see:**
- Pipeline start/end events
- User inputs and final outputs
- Major processing milestones
- Important intermediate results

**Use when:**
- Running in production
- You want high-level overview
- Focus on inputs and outputs

**Example output:**
```
[2026-01-20 10:00:00] INFO - ====================================================================================================
[2026-01-20 10:00:00] INFO - [ContextEngine] ========== 开始上下文优化 ==========
[2026-01-20 10:00:00] INFO - ====================================================================================================
[2026-01-20 10:00:00] INFO - [ContextEngine] 用户输入: '你好，我想了解一下...'
[2026-01-20 10:00:00] INFO - [ContextEngine] 检索到 5 个相关上下文项
[2026-01-20 10:00:00] INFO - [ContextEngine] 上下文优化完成
[2026-01-20 10:00:00] INFO - ----------------------------------------------------------------------------------------------------
```

### DETAILED Mode

**What you see:**
- Everything from BASIC mode
- Individual step execution logs
- Step-level inputs and outputs
- Intermediate processing results

**Use when:**
- Debugging workflows
- Understanding the process
- Analyzing specific steps

**Example output:**
```
[2026-01-20 10:00:00] INFO - ====================================================================================================
[2026-01-20 10:00:00] INFO - [ContextEngine] ========== 开始上下文优化 ==========
[2026-01-20 10:00:00] INFO - [ContextEngine] 用户输入: '你好，我想了解一下...'
[2026-01-20 10:00:00] INFO - [ContextEngine] 步骤 1/4: 输入预处理
[2026-01-20 10:00:01] INFO - [InputPreprocessor] 预处理完成: '你好，我想了解一下...'
[2026-01-20 10:00:01] INFO - [ContextEngine] 步骤 2/4: 检索上下文
[2026-01-20 10:00:02] INFO - [MemoryBank] 检索到 5 个相关记忆
[2026-01-20 10:00:02] INFO - [ContextEngine] 步骤 3/4: 重排序上下文
[2026-01-20 10:00:03] INFO - [ContextReorderer] 重排序完成
[2026-01-20 10:00:03] INFO - [ContextEngine] 步骤 4/4: 压缩上下文
[2026-01-20 10:00:04] INFO - [ContextCompressor] 压缩完成，原始: 5000 tokens -> 优化后: 2000 tokens
[2026-01-20 10:00:04] INFO - ----------------------------------------------------------------------------------------------------
```

### DEBUG Mode

**What you see:**
- Everything from DETAILED mode
- Internal variable states
- Detailed algorithm execution
- Low-level processing details

**Use when:**
- Deep debugging
- Development and testing
- Investigating issues

**Example output:**
```
[2026-01-20 10:00:00] INFO - ====================================================================================================
[2026-01-20 10:00:00] INFO - [ContextEngine] ========== 开始上下文优化 ==========
[2026-01-20 10:00:00] INFO - [ContextEngine] 用户输入: '你好，我想了解一下...'
[2026-01-20 10:00:00] DEBUG - [ContextEngine] 配置: session_history=True, long_term_memory=True
[2026-01-20 10:00:00] INFO - [ContextEngine] 步骤 1/4: 输入预处理
[2026-01-20 10:00:00] DEBUG - [InputPreprocessor] 原始输入长度: 45 字符
[2026-01-20 10:00:01] DEBUG - [InputPreprocessor] 清洗后长度: 42 字符
[2026-01-20 10:00:01] INFO - [InputPreprocessor] 预处理完成: '你好，我想了解一下...'
[2026-01-20 10:00:01] INFO - [ContextEngine] 步骤 2/4: 检索上下文
[2026-01-20 10:00:01] DEBUG - [MemoryBank] 查询向量维度: 768
[2026-01-20 10:00:02] DEBUG - [MemoryBank] 相似度计算: 使用余弦相似度
[2026-01-20 10:00:02] DEBUG - [MemoryBank] 检索结果相似度: [0.95, 0.89, 0.87, 0.82, 0.75]
[2026-01-20 10:00:02] INFO - [MemoryBank] 检索到 5 个相关记忆
...
```

## Using in Your Code

### Creating a Logger

```python
from contextmind import get_logger, LogLevel

# Create logger for your module
logger = get_logger("MyModule", level=LogLevel.DETAILED)

# Or use global level (set by setup_logging)
logger = get_logger("MyModule")
```

### Logger Methods

```python
# Pipeline-level events (shown in BASIC, DETAILED, DEBUG)
logger.pipeline("Starting context optimization")
logger.pipeline(f"User input: '{user_input}'")

# Step-level events (shown in DETAILED, DEBUG)
logger.step("Step 1/4: Preprocessing input")
logger.step("Preprocessing complete")

# Internal details (shown in DEBUG only)
logger.detail(f"Input length: {len(input_text)} characters")
logger.detail(f"Vector dimension: {vector.shape}")

# Section markers
logger.section_start("Context Optimization")
# ... processing ...
logger.section_end("Context Optimization")

# Separators
logger.separator("=", 100)  # Full line of =
logger.separator("-", 100)  # Full line of -

# General purpose
logger.info("Information message")
logger.warning("Warning message")
logger.error("Error message")
```

## Best Practices

### 1. Choose Appropriate Level

```python
# Pipeline boundaries and major events
logger.pipeline("Context optimization started")
logger.pipeline(f"Optimization complete, tokens: {final_tokens}")

# Individual processing steps
logger.step("Step 1: Preprocessing")
logger.step("Step 2: Retrieval")

# Internal implementation details
logger.detail(f"Cache hit rate: {hit_rate:.2%}")
logger.detail(f"Processing time: {elapsed:.3f}s")
```

### 2. Structure Your Logs

```python
# Start section
logger.section_start("Knowledge Extraction")

# Pipeline event
logger.pipeline("Extracting knowledge from conversation")

# Step details
logger.step("Analyzing user preferences")
logger.step("Extracting facts")
logger.step("Identifying events")

# End section
logger.section_end("Knowledge Extraction")
```

### 3. Include Useful Information

```python
# Good: Specific and actionable
logger.pipeline(f"Retrieved {len(items)} context items with avg score {avg_score:.3f}")

# Bad: Vague
logger.pipeline("Retrieved some items")

# Good: Shows progress
logger.step(f"Processing item {i+1}/{total}")

# Bad: No context
logger.step("Processing item")
```

## Demo Integration

All demo files support the three logging levels:

```bash
# interactive_demo.py
python interactive_demo.py                    # BASIC mode
python interactive_demo.py --detailed         # DETAILED mode
python interactive_demo.py --debug            # DEBUG mode

# gradio_demo.py
python gradio_demo.py                         # BASIC mode
python gradio_demo.py --detailed              # DETAILED mode
python gradio_demo.py --debug                 # DEBUG mode

# chat_interactive_demo.py
python chat_interactive_demo.py               # BASIC mode
python chat_interactive_demo.py --detailed    # DETAILED mode
python chat_interactive_demo.py --debug       # DEBUG mode

# chat_gradio_demo.py
python chat_gradio_demo.py                    # BASIC mode
python chat_gradio_demo.py --detailed         # DETAILED mode
python chat_gradio_demo.py --debug            # DEBUG mode
```

## Configuration

### Global Level

```python
from contextmind import setup_logging, set_global_log_level, LogLevel

# Set at initialization
setup_logging(LogLevel.DETAILED)

# Or change dynamically
set_global_log_level(LogLevel.DEBUG)
```

### Per-Module Level

```python
from contextmind import get_logger, LogLevel

# Override global level for specific module
logger = get_logger("MyModule", level=LogLevel.DEBUG)

# Change level dynamically
logger.set_level(LogLevel.BASIC)
```

## Migration from Old Logging

### Old Code

```python
import logging
logger = logging.getLogger(__name__)

logger.info("Processing started")
logger.debug("Internal detail")
```

### New Code

```python
from contextmind import get_logger, LogLevel

logger = get_logger(__name__)

logger.pipeline("Processing started")  # Pipeline-level
logger.detail("Internal detail")       # Debug-level
```

## Summary

The v7.2 logging system provides:

- **BASIC**: See the forest (pipeline overview)
- **DETAILED**: See the trees (individual steps)
- **DEBUG**: See the roots (all internal details)

Choose the level that matches your needs, and enjoy consistent, professional logging across the entire ContextMind framework!
