# ContextMind Architecture (v7.2+)

This document describes the optimized project structure based on the architecture design document in `docs/arch_by_me.md`.

## Overview

ContextMind follows a **6-Step Pipeline Architecture** for context optimization:

```
Raw User Input
    ↓
1. InputPreprocessor      (Input cleaning and normalization)
    ↓
2. ContextRetriever       (External retrieval)
   + MemoryBank          (Long-term memory management)
    ↓
3. ContextCompressor      (Context compression with ConversationSummarizer)
    ↓
4. ContextReorderer       (Context reordering)
    ↓
Build Final Prompt → LLM
    ↓ (During inference)
5. KVCacheManager         (Real-time KV cache management)
    ↓
LLM generates output
    ↓
6. PostProcessor          (Output post-processing)
    ↓
Final Response
```

## Project Structure

```
ContextMind/
├── contextmind/              # Core framework
│   ├── __init__.py          # Main exports
│   ├── config.py            # Easy integration API (ContextMind class)
│   ├── engine.py            # Main orchestration engine (ContextEngine)
│   ├── models.py            # Data models
│   ├── registry.py          # Component registry
│   │
│   │ # Pipeline Architecture - 6 Steps
│   ├── preprocessor.py      # Step 1: InputPreprocessor
│   ├── retriever.py         # Step 2: ContextRetriever (placeholder)
│   ├── compressor.py        # Step 3: ContextCompressor
│   ├── reorderer.py         # Step 4: ContextReorderer
│   ├── kvcache.py           # Step 5: KVCacheManager
│   ├── postprocessor.py     # Step 6: PostProcessor
│   │
│   ├── summarizer.py        # ConversationSummarizer (used by compressor)
│   │
│   │ # MemoryBank Module - 4 Sub-modules
│   ├── memory/
│   │   ├── __init__.py      # Exports all memory components
│   │   ├── bank.py          # Main MemoryBank class
│   │   ├── session.py       # SessionManager
│   │   ├── extractor.py     # Extract high-value information
│   │   ├── retriever.py     # Retrieve relevant memories
│   │   └── updater.py       # Memory updates (Add/Delete/Update)
│   │
│   ├── strategies/          # Strategy interfaces
│   │   ├── __init__.py      # Re-exports from memory
│   │   ├── base.py          # Base strategy interfaces
│   │   └── defaults.py      # Default implementations
│   │
│   ├── utils/
│   │   ├── __init__.py
│   │   └── embedding.py
│   │
│   │ # Backward Compatibility Wrappers
│   ├── pipeline.py          # Re-exports from modular components
│   └── memory.py            # Re-exports from memory/ submodule
│
├── examples/                # Examples and demos
│   ├── chat_app.py
│   ├── callcenter_app.py
│   ├── gradio_app.py
│   ├── interactive_app.py
│   ├── plugin_examples.py
│   └── llm_client.py
│
├── tests/                   # Unit and integration tests
├── docs/                    # Documentation
└── logs/                    # Log files
```

## Core Components

### 1. Pipeline Components (6 Steps)

#### Step 1: InputPreprocessor (`preprocessor.py`)
- **Purpose**: Input cleaning and normalization
- **Methods**: Text cleaning, validation, normalization
- **Common techniques**: Regex-based cleaning, dynamic prompt templates, semantic chunking

#### Step 2: Context Retrieval
- **ContextRetriever** (`retriever.py`): External knowledge retrieval (placeholder)
- **MemoryBank** (`memory/bank.py`): Long-term memory management
  - Uses 4 sub-modules: Extractor, Retriever, Updater, Bank

#### Step 3: ContextCompressor (`compressor.py`)
- **Purpose**: Context compression to reduce token usage
- **Uses**: ConversationSummarizer for recent dialogue summarization
- **Techniques**: Sliding window, summarization, intelligent filtering

#### Step 4: ContextReorderer (`reorderer.py`)
- **Purpose**: Reorder context to highlight key information
- **Techniques**: Timestamp sorting, source priority, relevance scoring
- **Mitigates**: "Lost-in-the-Middle" problem

#### Step 5: KVCacheManager (`kvcache.py`)
- **Purpose**: Real-time KV cache management during LLM inference
- **Strategies**: H2O, SnapKV, sliding window
- **Integration**: vLLM, sglang hooks (placeholder)

#### Step 6: PostProcessor (`postprocessor.py`)
- **Purpose**: Output refinement and consistency checks
- **Methods**: Format correction, self-refine, fact verification

### 2. MemoryBank Module (`memory/`)

The MemoryBank implements a 4-sub-module architecture:

#### 2.1 Extractor (`memory/extractor.py`)
- **Purpose**: Extract high-value information for long-term storage
- **Implementations**:
  - `RuleBasedExtractor`: Pattern matching (lightweight)
  - `LLMBasedExtractor`: LLM-assisted extraction (high-end)
  - `ImportancePredictorExtractor`: ML-based importance scoring

#### 2.2 Retriever (`memory/retriever.py`)
- **Purpose**: Retrieve relevant memories based on query
- **Implementations**:
  - `SemanticSearchRetriever`: Embedding-based similarity
  - `HybridRetriever`: Semantic + keyword matching
  - `LocatorMechanism`: Precise localization with context weighting

#### 2.3 Updater (`memory/updater.py`)
- **Purpose**: Intelligent memory updates (Add/Delete/Update)
- **Operations**:
  - **Add**: Insert new high-value memories
  - **Delete**: Remove outdated/low-value memories
  - **Update**: Handle conflicts and information evolution
- **Implementations**:
  - `SimpleUpdater`: Basic add/update/dedup logic
  - `ConflictResolver`: LLM-based conflict detection
  - `AdaptiveEviction`: Predictive pruning

#### 2.4 Bank (`memory/bank.py`)
- **Purpose**: Main MemoryBank class coordinating all sub-modules
- **Features**:
  - Persistent user/dialogue memory storage
  - Structured memory notes (preferences, facts, events)
  - Memory lifecycle management
  - Cross-session continuity

### 3. Supporting Components

#### SessionManager (`memory/session.py`)
- Manages conversation sessions
- Stores message history
- Provides recent history access

#### ConversationSummarizer (`summarizer.py`)
- Summarizes recent dialogue
- Used by ContextCompressor
- Reduces token usage while preserving context

#### ContextEngine (`engine.py`)
- Main orchestration engine
- Coordinates all pipeline components
- Provides high-level API: `optimize()`, `update()`, `extract_knowledge()`

#### ContextMind (`config.py`)
- Easy integration API
- Simplified configuration
- Plugin registry integration

## Import Patterns

### Recommended (New Code)

```python
# Pipeline components
from contextmind.preprocessor import InputPreprocessor
from contextmind.compressor import ContextCompressor
from contextmind.reorderer import ContextReorderer
from contextmind.postprocessor import PostProcessor
from contextmind.kvcache import KVCacheManager

# Memory components
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

# High-level API
from contextmind import ContextMind, ContextEngine
```

### Backward Compatible (Legacy Code)

```python
# Old pipeline imports still work
from contextmind.pipeline import (
    InputPreprocessor,
    ContextCompressor,
    ContextReorderer,
    PostProcessor,
)

# Old memory imports still work
from contextmind.memory import MemoryBank, SessionManager, KVCacheManager

# Old strategy imports redirected to memory
from contextmind.strategies import extractors, retrievers, updaters
```

## Migration Guide

### From v7.1 to v7.2+

1. **Pipeline imports**: Change from `contextmind.pipeline.X` to `contextmind.X`
   ```python
   # Old
   from contextmind.pipeline.compressor import ContextCompressor
   # New
   from contextmind.compressor import ContextCompressor
   ```

2. **Memory imports**: Use `contextmind.memory` submodule
   ```python
   # Old
   from contextmind.strategies.extractors import RuleBasedExtractor
   # New
   from contextmind.memory import RuleBasedExtractor
   ```

3. **Strategy imports**: Import from `strategies.defaults`
   ```python
   # Old
   from contextmind.strategies.optimization import CompressionStrategy
   # New
   from contextmind.strategies.defaults import CompressionStrategy
   ```

## Design Principles

1. **Modularity**: Each step in the pipeline is a separate module
2. **Plugin Architecture**: All components are pluggable and swappable
3. **Backward Compatibility**: Old imports still work via wrapper modules
4. **Clear Separation**: Pipeline, Memory, Strategies, and Utils are distinct
5. **Type Safety**: Strong typing with dataclasses
6. **Async-First**: All I/O operations use async/await

## Architecture Benefits

1. **Clear Structure**: Easy to understand the flow from input to output
2. **Easy Testing**: Each component can be tested independently
3. **Flexible**: Components can be swapped or extended
4. **Maintainable**: Related code is grouped together
5. **Scalable**: New components can be added without breaking existing code

## Next Steps

- Implement full ContextRetriever for external knowledge bases
- Add more Extractor/Retriever/Updater strategies
- Integrate with real inference frameworks (vLLM, sglang) for KVCache
- Enhance PostProcessor with advanced refinement strategies
