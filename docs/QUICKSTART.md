# ContextMind Quick Start Guide

## Installation

```bash
pip install -r requirements.txt
```

## Basic Usage

### 1. Initialize the Context Engine

```python
from contextmind import ContextEngine
from contextmind.adapters import OpenAIAdapter
from contextmind.modules import MemoryBank

# Initialize LLM adapter
llm_adapter = OpenAIAdapter(api_key="your-api-key")

# Create context engine
engine = ContextEngine(
    llm_adapter=llm_adapter,
    memory_bank=MemoryBank()
)
```

### 2. Process Conversations

```python
# Optimize context for a conversation
result = await engine.optimize(
    query="User's current question",
    session_id="unique-session-id"
)

# Access optimized context
recent_history = result.recent_history        # Recent conversation turns
long_term_memory = result.long_term_memory    # Retrieved memories
external_knowledge = result.external_knowledge # Retrieved knowledge
```

### 3. Run Demo Applications

**Interactive CLI Demo:**
```bash
python interactive_demo.py
```

**Gradio Web UI Demo:**
```bash
python gradio_demo.py
```

## Configuration

Customize behavior via configuration:

```python
from contextmind.config import MemorySystemConfig, RetrievalConfig

config = MemorySystemConfig(
    retrieval=RetrievalConfig(
        relevance_threshold=0.5,      # Minimum relevance score
        enable_recency_boost=True,    # Boost recent memories
        recency_weight=0.3            # Recency boost strength
    )
)

# Use in memory bank
memory_bank = MemoryBank(retrieval_config=config.retrieval)
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│         Context Engine                   │
│  ┌─────────────────────────────────┐    │
│  │   1. Retrieval                  │    │
│  │   2. Integration                │    │
│  │   3. Reordering                 │    │
│  │   4. Compression                │    │
│  └─────────────────────────────────┘    │
│                 ↓                        │
│         ContextResult                    │
│  - recent_history                        │
│  - long_term_memory                      │
│  - external_knowledge                    │
└─────────────────────────────────────────┘
```

## Key Concepts

### ProcessedContext vs ContextResult

- **ProcessedContext**: Pipeline intermediate state
  - Has `items` list
  - Used in retrieval, integration, reordering steps
  
- **ContextResult**: Final optimized output
  - Has `recent_history`, `long_term_memory`, `external_knowledge`
  - Used in application layer

### Memory System

- **Extraction**: Automatically extracts knowledge from conversations
- **Storage**: Persistent memory bank with vector search
- **Retrieval**: Relevance filtering, deduplication, recency weighting
- **Summarization**: Condenses old conversation turns

### Strategies (Pluggable)

- **Extraction**: Rule-based, LLM-based
- **Reordering**: Score-based, recency-based
- **Compression**: Source-aware truncation
- **Integration**: Merge contexts from different sources

## Next Steps

- Read [ARCHITECTURE.md](ARCHITECTURE.md) for system design
- Read [API_REFERENCE.md](API_REFERENCE.md) for detailed API docs
- Check [examples/](../examples/) for more usage patterns
