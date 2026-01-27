# ContextMind Design Documentation

This document consolidates the essential design information for the ContextMind framework.

---

## Table of Contents

1. [Overview](#overview)
2. [6-Step Pipeline Architecture](#6-step-pipeline-architecture)
3. [MemoryBank Module](#memorybank-module)
4. [Knowledge Extraction](#knowledge-extraction)
5. [Logging System](#logging-system)
6. [Context Optimization Strategies](#context-optimization-strategies)

---

## Overview

ContextMind is a pure context engineering framework that focuses on **Steps 1-4** (context building) and **Step 6** (output post-processing), while **Step 5** (LLM inference) is handled externally by the user.

### Design Principles

1. **Modularity** - Each component has a single responsibility
2. **Extensibility** - Plugin architecture for easy customization
3. **Separation of Concerns** - Context engineering ≠ LLM inference
4. **Type Safety** - Strong typing with data models
5. **Async-First** - Native async/await support
6. **Code Reuse** - Composition over inheritance

---

## 6-Step Pipeline Architecture

The framework processes context through 6 distinct steps:

```
User Input
    ↓
[Step 1] InputPreprocessor
    ↓
[Step 2] ContextRetriever + MemoryBank
    ↓
[Step 3] ContextCompressor (with ConversationSummarizer)
    ↓
[Step 4] ContextReorderer
    ↓
Optimized Context → External LLM (Step 5, user-controlled)
    ↓
[Step 6] PostProcessor
    ↓
Final Response
```

### Step 1: Input Preprocessing

**Purpose**: Clean, normalize, and validate user input before processing.

**Common Techniques**:
- Regex-based text cleaning
- Dynamic prompt templates (Jinja2)
- Semantic chunking
- System instruction injection

### Step 2: Context Retrieval

**Components**:
- **ContextRetriever**: External knowledge retrieval (extensible placeholder)
- **MemoryBank**: Long-term memory management (core component)

**Retrieval Strategies**:
- Semantic search (dense retrieval)
- Hybrid search (BM25 + semantic)
- Locator-based retrieval

### Step 3: Context Compression

**Purpose**: Reduce token count while preserving critical information.

**Techniques**:
- Conversation summarization
- Token-level truncation
- Importance-based filtering
- LLM-assisted compression (optional)

### Step 4: Context Reordering

**Purpose**: Optimize context order to combat the "lost-in-the-middle" problem.

**Strategies**:
- Relevance-based ordering
- Recency-based ordering
- Importance scoring
- Mixed strategies

### Step 5: LLM Inference (External)

This step is **not** part of ContextMind. Users call their own LLM with the optimized context.

### Step 6: Post-Processing

**Purpose**: Ensure output quality and extract knowledge for memory.

**Operations**:
- Format validation and correction
- Duplicate removal
- Citation generation
- Knowledge extraction
- Memory update

---

## MemoryBank Module

The MemoryBank is the core memory management component, handling long-term information persistence across sessions.

### Architecture

```
MemoryBank
├── Extractor    - Extract high-value knowledge from conversations
├── Retriever    - Retrieve relevant memories via semantic search
├── Updater      - Add/update/delete memories with conflict resolution
└── Bank         - Main storage and orchestration
```

### Knowledge Types

```python
class KnowledgeType(Enum):
    PREFERENCE = "preference"  # User preferences (e.g., "likes spicy food")
    FACT = "fact"              # Factual information (e.g., "birthday: Oct 1")
    EVENT = "event"            # Events (e.g., "visited Paris in 2024")
    GOAL = "goal"              # Goals (e.g., "wants to learn Python")
    ENTITY = "entity"          # Named entities
```

### Memory Format

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

### Extraction Strategies

#### 1. Rule-Based Extractor (Default)
- Fast, deterministic pattern matching
- Template-based extraction
- Keyword frequency analysis
- No API costs

#### 2. LLM-Based Extractor
- Semantic understanding via LLM
- Entity and relationship extraction
- Adaptive to complex scenarios
- API costs apply

#### 3. Importance-Based Extractor
- Predicts "persistence value" score
- Combines time decay and explicitness
- Small model fine-tuning (BERT-style)

### Retrieval Strategies

#### 1. Semantic Retriever
- Dense vector search
- Cosine similarity
- Top-k results

#### 2. Hybrid Retriever
- Combines BM25 + semantic search
- Weighted score fusion
- Better recall and precision

#### 3. Locator Retriever
- Graph-based memory navigation
- Contextual memory chains
- Advanced memory linking

### Update Strategies

#### 1. Simple Updater
- Direct add/update/delete
- No conflict handling
- Fast and straightforward

#### 2. Conflict Resolver Updater
- Detects contradictions
- Keeps newer information
- Version tracking

#### 3. Adaptive Updater
- Learning-based updates
- Frequency and importance weighting
- Smart memory consolidation

---

## Knowledge Extraction

### Extraction Methods Comparison

| Feature | Rule-Based | LLM-Based |
|---------|-----------|-----------|
| Speed | Fast | Slower (API calls) |
| Accuracy | High (clear patterns) | High (semantic) |
| Flexibility | Low (predefined) | High (adaptive) |
| Cost | Free | API costs |
| Complex Scenarios | Limited | Powerful |
| Entity Relations | Not supported | Supported |

### Configuration

```python
from contextmind.core import ExtractionConfig

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

### Usage Example

```python
from contextmind import ContextMind

# With rule-based extraction (default)
cm = ContextMind(llm_client=None, extractor='rule_based')

# With LLM-based extraction
cm = ContextMind(llm_client=your_llm, extractor='llm_entity')

# Automatic extraction during post-processing
final = await cm.post_process(
    llm_output,
    session_id="user-123",
    extract_knowledge=True  # Enable extraction
)
```

---

## Logging System

ContextMind provides a three-level logging system optimized for context engineering workflows.

### Logging Levels

#### 1. BASIC (Default)
- Pipeline-level events only
- Inputs and outputs
- Major processing milestones
- Production-ready

**Use when**: Running in production, high-level overview needed

#### 2. DETAILED
- BASIC + step-level logs
- Individual step execution
- Step inputs/outputs
- Intermediate results

**Use when**: Debugging workflows, understanding flow

#### 3. DEBUG
- DETAILED + internal details
- Token counts
- Memory operations
- Full trace information

**Use when**: Deep debugging, performance analysis

### Configuration

```python
from contextmind import setup_logging, LogLevel

# Basic mode (default)
setup_logging(LogLevel.BASIC)

# Detailed mode
setup_logging(LogLevel.DETAILED)

# Debug mode
setup_logging(LogLevel.DEBUG)
```

### Module-Specific Logging

Each module has prefix identifiers:
- `[MemoryBank]` - Memory operations
- `[Retriever]` - Retrieval operations
- `[ContextEngine]` - Engine orchestration
- `[Extractor]` - Knowledge extraction
- `[Prompt]` - Prompt building

### Status Indicators

- ✓ Success
- ✗ Failure
- ━━━ Stage separators

---

## Context Optimization Strategies

### Compression Strategies

1. **Rule-Based Compression**
   - TF-IDF keyword selection
   - Sentence importance scoring
   - Fast, deterministic

2. **LLM-Assisted Compression**
   - LLMLingua2 / LongLLMLingua
   - AutoCompressor
   - Higher quality, slower

3. **Summarization-Based**
   - Conversation summarization
   - Progressive summarization
   - Memory-efficient

### Reordering Strategies

1. **Relevance-Based**
   - Query-context similarity
   - Semantic matching
   - Attention optimization

2. **Recency-Based**
   - Time decay weighting
   - Recent-first ordering
   - Simple and effective

3. **Importance-Based**
   - Importance scoring
   - Critical information first
   - PPR (Personalized PageRank)

### Integration Strategies

1. **Naive Integration**
   - Simple concatenation
   - No deduplication
   - Fast baseline

2. **Smart Integration**
   - Duplicate detection
   - Conflict resolution
   - Source prioritization

3. **Semantic Integration**
   - Semantic deduplication
   - Information fusion
   - Maximum information density

---

## Best Practices

### 1. Start Simple, Scale Smart
- Begin with rule-based extraction
- Enable LLM extraction when needed
- Monitor API costs vs. quality gains

### 2. Configure Memory Wisely
- Set appropriate `max_memory_items` (default: 1000)
- Adjust `similarity_threshold` based on use case (0.6-0.8)
- Use `retrieval_top_k` of 3-10 for most cases

### 3. Optimize Token Usage
- Enable compression for long conversations
- Use summarization for token reduction
- Monitor token counts in DEBUG mode

### 4. Plugin Selection
- **Simple apps**: rule_based + semantic + simple
- **Advanced apps**: llm_entity + hybrid + conflict_resolver
- **Production**: Start simple, profile, then upgrade

### 5. Testing and Monitoring
- Run tests before deployment
- Use DETAILED logging during development
- Switch to BASIC logging in production
- Monitor memory size and retrieval latency

---

## Architecture Evolution

### v7.0 - Pure Context Engineering
- Separated LLM inference from framework
- Introduced 6-step pipeline
- Pluggable strategy system

### v7.1 - Code Quality
- Eliminated code duplication
- Improved type safety
- Enhanced documentation

### v7.2 - Enhanced Observability
- Module-specific logging
- Complete memory lifecycle tracking
- Transparent context optimization

### v7.3 - Modular Structure (Current)
- Split models.py into types, data_models, configs
- Reorganized engine layer
- Improved import structure
- Framework-level configuration (framework_config.py)

---

## Future Directions

### Short-Term
- Advanced compression algorithms (LLMLingua3)
- Multi-modal memory support
- Distributed memory backends

### Long-Term
- Federated memory systems
- Cross-user knowledge graphs
- Automatic strategy selection

---

**For detailed architecture information, see [ARCHITECTURE.md](ARCHITECTURE.md)**

**For migration guides, see [MIGRATION.md](MIGRATION.md)**

**For original architecture reference, see [arch_by_me.md](arch_by_me.md)**
