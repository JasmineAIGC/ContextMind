# 知识存储格式设计文档

## 设计目标

设计一个优化的知识存储格式，满足以下核心需求：

1. **检索优化** - 支持快速、准确的知识检索
2. **便于更新** - 支持知识的动态更新和演化
3. **多模态支持** - 支持多种embedding算法和模型
4. **版本追踪** - 记录知识的完整演化历史
5. **智能评分** - 算法驱动的重要性和相关性评分
6. **淡化机制** - 基于时间和访问频率的记忆淡化

## 存储格式设计

### 完整JSON Schema

```json
{
  // ========== 核心标识 ==========
  "memory_id": "uuid-v4-string",                    // 唯一标识符
  "user_id": "user-123",                            // 所属用户
  "session_id": "session-456",                      // 所属会话（可选）
  
  // ========== 知识内容 ==========
  "type": "preference",                             // 类型: preference/fact/event/goal/entity/relationship
  "content": "用户喜欢辣食，不吃香菜",              // 核心文本内容
  "summary": "食物偏好：喜辣避香菜",               // 简短摘要（用于快速浏览）
  
  // ========== 多模态Embedding ==========
  "embeddings": {
    "primary": {
      "model": "text-embedding-3-large",            // 主要embedding模型
      "vector": [0.123, -0.456, ...],               // 向量（1536维）
      "dimension": 1536,
      "created_at": "2026-01-20T10:30:00Z"
    },
    "secondary": {
      "model": "bge-large-zh-v1.5",                 // 备用embedding（跨模型检索）
      "vector": [0.789, -0.234, ...],               // 向量（1024维）
      "dimension": 1024,
      "created_at": "2026-01-20T10:30:00Z"
    }
  },
  
  // ========== 元数据 ==========
  "metadata": {
    // --- 来源追溯 ---
    "source_type": "conversation",                  // 来源类型: conversation/import/manual
    "source_dialog_ids": [                          // 源对话ID列表（完整追溯）
      "dialog-001",
      "dialog-002"
    ],
    "extraction_method": "llm",                     // 提取方法: rule/llm/hybrid
    "extractor_version": "v7.2.0",                  // 提取器版本
    
    // --- 时间信息 ---
    "created_at": "2026-01-20T10:30:00Z",          // 创建时间
    "updated_at": "2026-01-20T15:45:00Z",          // 最后更新时间
    "last_accessed": "2026-01-21T08:20:00Z",       // 最后访问时间
    "expires_at": null,                             // 过期时间（null表示永不过期）
    
    // --- 访问统计 ---
    "access_count": 15,                             // 总访问次数
    "access_frequency": {                           // 访问频率统计
      "last_7_days": 5,
      "last_30_days": 12,
      "last_90_days": 15
    },
    
    // --- 评分系统 ---
    "scores": {
      "importance": 0.95,                           // 重要性分数（算法计算）
      "confidence": 0.88,                           // 置信度分数
      "relevance": 0.92,                            // 相关性分数（基于最近使用）
      "quality": 0.90                               // 质量分数（基于来源和验证）
    },
    
    // --- 语义增强 ---
    "category": "food_preference",                  // 细分类别
    "tags": ["食物", "偏好", "饮食习惯"],           // 标签（用于筛选）
    "keywords": ["辣", "香菜", "喜欢", "不吃"],     // 关键词（用于关键词检索）
    "entities": [                                   // 实体列表（NER结果）
      {
        "text": "辣食",
        "type": "food",
        "sentiment": "positive"
      },
      {
        "text": "香菜",
        "type": "food",
        "sentiment": "negative"
      }
    ],
    
    // --- 关系图谱 ---
    "relationships": [                              // 知识图谱关系
      {
        "relation_type": "preference_for",
        "target": "spicy_food",
        "strength": 0.9
      },
      {
        "relation_type": "aversion_to",
        "target": "coriander",
        "strength": 0.95
      }
    ],
    
    // --- 上下文信息 ---
    "context": {
      "original_text": "我特别喜欢吃辣的，但是不能吃香菜",  // 原始文本
      "conversation_turn": 3,                       // 对话轮次
      "surrounding_context": "在讨论餐厅推荐时提到"  // 上下文描述
    },
    
    // --- 冲突处理 ---
    "conflicts": [                                  // 与其他知识的冲突
      {
        "conflicting_memory_id": "uuid-xxx",
        "conflict_type": "contradiction",
        "resolution_strategy": "keep_newer",
        "resolved_at": "2026-01-20T15:45:00Z"
      }
    ]
  },
  
  // ========== 版本历史 ==========
  "version_history": [
    {
      "version": 2,
      "content": "用户喜欢辣食，不吃香菜",
      "updated_at": "2026-01-20T15:45:00Z",
      "update_reason": "用户再次确认偏好",
      "confidence_delta": 0.05,                     // 置信度变化
      "updated_by": "llm_extractor"
    },
    {
      "version": 1,
      "content": "用户可能喜欢辣食",
      "updated_at": "2026-01-20T10:30:00Z",
      "update_reason": "初次提取",
      "confidence_delta": 0.0,
      "updated_by": "rule_extractor"
    }
  ],
  
  // ========== 状态标记 ==========
  "status": "active",                               // 状态: active/archived/deleted
  "flags": {
    "verified": true,                               // 是否已验证
    "requires_review": false,                       // 是否需要人工审核
    "is_sensitive": false,                          // 是否包含敏感信息
    "auto_generated": true                          // 是否自动生成
  }
}
```

## 设计原则说明

### 1. 多层次ID系统

```
memory_id (全局唯一)
  └── user_id (用户隔离)
      └── session_id (会话上下文，可选)
```

**优势:**
- 支持跨用户的知识管理
- 支持会话级知识隔离
- 便于数据迁移和备份

### 2. 多Embedding支持

**设计理由:**
- 不同模型各有优势（精度 vs 速度）
- 支持模型升级而不丢失历史数据
- 跨模型检索提升召回率

**使用策略:**
```python
# 主要检索：使用primary embedding
# 备用检索：当primary结果不足时使用secondary
# 混合检索：融合多个embedding的结果
```

### 3. 智能评分系统

**四维评分体系:**

1. **Importance Score (重要性)**
   - 基于访问频率
   - 基于知识类型（核心偏好 > 临时事件）
   - 基于与其他知识的关联度

2. **Confidence Score (置信度)**
   - 提取方法决定基础分数
   - 多次验证提升置信度
   - 冲突降低置信度

3. **Relevance Score (相关性)**
   - 基于时间衰减
   - 基于最近访问
   - 基于上下文匹配

4. **Quality Score (质量)**
   - 基于来源可靠性
   - 基于内容完整性
   - 基于验证状态

**动态调整算法:**
```python
# 每次访问
importance += 0.01
relevance = base_relevance * time_decay_factor

# 每次更新
confidence = (old_confidence + new_confidence) / 2
quality = verify_quality(content, metadata)

# 每天淡化
if days_since_access > 30:
    relevance *= 0.95
```

### 4. 版本历史追踪

**完整记录知识演化:**
- 每次更新创建新版本
- 保留所有历史版本（可配置保留策略）
- 记录更新原因和来源
- 支持回滚到历史版本

**版本压缩策略:**
```python
# 保留策略
- 最新10个版本: 全部保留
- 10-100个版本: 每10个保留1个
- 100+个版本: 每100个保留1个
```

### 5. 检索优化设计

**多层次索引:**

```python
# 1. 向量索引 - 语义检索
embeddings.primary.vector -> HNSW/IVF索引

# 2. 关键词索引 - 精确匹配
metadata.keywords -> 倒排索引

# 3. 标签索引 - 快速筛选
metadata.tags -> 哈希索引

# 4. 时间索引 - 时间范围查询
metadata.created_at, last_accessed -> B-Tree索引

# 5. 评分索引 - 排序优化
metadata.scores.* -> 复合索引
```

**检索流程:**
```
1. 粗筛（快速）：
   - 标签过滤
   - 时间范围
   - 用户隔离

2. 精筛（准确）：
   - 向量相似度（主要）
   - 关键词匹配（辅助）
   
3. 重排序（优化）：
   - 综合评分排序
   - 时间衰减应用
   - 多样性优化
```

### 6. 知识更新策略

**冲突检测:**
```python
def detect_conflict(new_knowledge, existing_knowledge):
    # 1. 内容矛盾检测
    if contradicts(new.content, existing.content):
        return "contradiction"
    
    # 2. 时间冲突检测
    if overlaps(new.time_range, existing.time_range):
        return "temporal_conflict"
    
    # 3. 语义重复检测
    if semantic_similarity(new, existing) > 0.9:
        return "duplication"
    
    return None
```

**冲突解决策略:**
```python
resolution_strategies = {
    "keep_newer": lambda old, new: new,           # 保留新的
    "keep_higher_confidence": lambda old, new: max(old, new, key=lambda x: x.confidence),
    "merge": lambda old, new: merge_knowledge(old, new),  # 合并
    "manual_review": lambda old, new: flag_for_review(old, new)
}
```

**更新触发条件:**
```python
should_update = (
    new.confidence > existing.confidence + 0.1 or  # 明显更可信
    is_complementary(new, existing) or              # 补充信息
    user_explicitly_corrected() or                  # 用户明确纠正
    existing.age_days > 90                          # 旧信息需要刷新
)
```

## Python实现示例

### Knowledge类增强

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
import uuid

@dataclass
class EmbeddingInfo:
    """Embedding信息"""
    model: str
    vector: List[float]
    dimension: int
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class EntityInfo:
    """实体信息"""
    text: str
    type: str
    sentiment: Optional[str] = None

@dataclass
class RelationshipInfo:
    """关系信息"""
    relation_type: str
    target: str
    strength: float = 1.0

@dataclass
class VersionRecord:
    """版本记录"""
    version: int
    content: str
    updated_at: datetime
    update_reason: str
    confidence_delta: float
    updated_by: str

@dataclass
class ScoreInfo:
    """评分信息"""
    importance: float = 0.5
    confidence: float = 0.5
    relevance: float = 0.5
    quality: float = 0.5

@dataclass
class Knowledge:
    """优化的知识存储模型"""
    
    # 核心标识
    memory_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    session_id: Optional[str] = None
    
    # 知识内容
    type: str = "fact"  # preference/fact/event/goal/entity/relationship
    content: str = ""
    summary: Optional[str] = None
    
    # 多Embedding支持
    embeddings: Dict[str, EmbeddingInfo] = field(default_factory=dict)
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 评分系统
    scores: ScoreInfo = field(default_factory=ScoreInfo)
    
    # 版本历史
    version_history: List[VersionRecord] = field(default_factory=list)
    
    # 时间戳
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    last_accessed: Optional[datetime] = None
    
    # 访问统计
    access_count: int = 0
    
    # 状态
    status: str = "active"  # active/archived/deleted
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为存储格式"""
        return {
            "memory_id": self.memory_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "type": self.type,
            "content": self.content,
            "summary": self.summary,
            "embeddings": {
                name: {
                    "model": emb.model,
                    "vector": emb.vector,
                    "dimension": emb.dimension,
                    "created_at": emb.created_at.isoformat()
                }
                for name, emb in self.embeddings.items()
            },
            "metadata": self.metadata,
            "scores": {
                "importance": self.scores.importance,
                "confidence": self.scores.confidence,
                "relevance": self.scores.relevance,
                "quality": self.scores.quality
            },
            "version_history": [
                {
                    "version": v.version,
                    "content": v.content,
                    "updated_at": v.updated_at.isoformat(),
                    "update_reason": v.update_reason,
                    "confidence_delta": v.confidence_delta,
                    "updated_by": v.updated_by
                }
                for v in self.version_history
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "access_count": self.access_count,
            "status": self.status
        }
```

### 检索接口设计

```python
class KnowledgeRetriever:
    """知识检索器"""
    
    def retrieve(
        self,
        query: str,
        user_id: str,
        top_k: int = 5,
        filters: Optional[Dict] = None,
        strategy: str = "hybrid"
    ) -> List[Knowledge]:
        """
        检索知识
        
        Args:
            query: 查询文本
            user_id: 用户ID
            top_k: 返回数量
            filters: 过滤条件
                - tags: 标签列表
                - type: 知识类型
                - time_range: 时间范围
                - min_score: 最小评分
            strategy: 检索策略
                - "vector": 纯向量检索
                - "keyword": 纯关键词检索
                - "hybrid": 混合检索（推荐）
        
        Returns:
            检索到的知识列表（按相关性排序）
        """
        # 1. 粗筛
        candidates = self._filter_by_conditions(user_id, filters)
        
        # 2. 精筛
        if strategy == "vector":
            results = self._vector_search(query, candidates, top_k * 2)
        elif strategy == "keyword":
            results = self._keyword_search(query, candidates, top_k * 2)
        else:  # hybrid
            vector_results = self._vector_search(query, candidates, top_k)
            keyword_results = self._keyword_search(query, candidates, top_k)
            results = self._merge_results(vector_results, keyword_results)
        
        # 3. 重排序
        reranked = self._rerank(results, query)
        
        # 4. 更新访问统计
        for knowledge in reranked[:top_k]:
            self._update_access_stats(knowledge)
        
        return reranked[:top_k]
```

### 知识更新接口

```python
class KnowledgeUpdater:
    """知识更新器"""
    
    def update_or_create(
        self,
        new_knowledge: Knowledge,
        conflict_strategy: str = "merge"
    ) -> Knowledge:
        """
        更新或创建知识
        
        Args:
            new_knowledge: 新知识
            conflict_strategy: 冲突处理策略
                - "keep_newer": 保留新的
                - "keep_higher_confidence": 保留置信度高的
                - "merge": 合并
                - "manual_review": 标记人工审核
        
        Returns:
            最终存储的知识
        """
        # 1. 查找潜在冲突
        conflicts = self._find_conflicts(new_knowledge)
        
        if not conflicts:
            # 无冲突，直接创建
            return self._create(new_knowledge)
        
        # 2. 处理冲突
        for existing in conflicts:
            conflict_type = self._detect_conflict_type(new_knowledge, existing)
            
            if conflict_type == "duplication":
                # 重复：更新现有知识
                return self._update_existing(existing, new_knowledge)
            
            elif conflict_type == "contradiction":
                # 矛盾：按策略处理
                return self._resolve_contradiction(
                    existing, new_knowledge, conflict_strategy
                )
            
            elif conflict_type == "complementary":
                # 补充：合并知识
                return self._merge_knowledge(existing, new_knowledge)
        
        # 3. 无法自动处理，标记审核
        new_knowledge.metadata["requires_review"] = True
        return self._create(new_knowledge)
```

## 使用示例

### 创建知识

```python
from demos.llm_client import SimpleLLMClient

# 提取知识
knowledge = Knowledge(
    user_id="user-123",
    type="preference",
    content="用户喜欢辣食，不吃香菜",
    summary="食物偏好：喜辣避香菜"
)

# 生成embedding
llm_client = SimpleLLMClient.from_env()
embedding_vector = llm_client.embed(knowledge.content)

knowledge.embeddings["primary"] = EmbeddingInfo(
    model="text-embedding-3-large",
    vector=embedding_vector,
    dimension=len(embedding_vector)
)

# 填充元数据
knowledge.metadata = {
    "category": "food_preference",
    "tags": ["食物", "偏好"],
    "keywords": ["辣", "香菜"],
    "entities": [
        {"text": "辣食", "type": "food", "sentiment": "positive"},
        {"text": "香菜", "type": "food", "sentiment": "negative"}
    ],
    "extraction_method": "llm",
    "source_dialog_ids": ["dialog-001"]
}

# 设置评分
knowledge.scores = ScoreInfo(
    importance=0.85,
    confidence=0.90,
    relevance=1.0,
    quality=0.88
)

# 存储
storage.save(knowledge)
```

### 检索知识

```python
# 检索用户的食物偏好
results = retriever.retrieve(
    query="推荐餐厅",
    user_id="user-123",
    top_k=5,
    filters={
        "tags": ["食物", "偏好"],
        "min_score": 0.7
    },
    strategy="hybrid"
)

for knowledge in results:
    print(f"内容: {knowledge.content}")
    print(f"重要性: {knowledge.scores.importance}")
    print(f"相关性: {knowledge.scores.relevance}")
    print(f"访问次数: {knowledge.access_count}")
```

### 更新知识

```python
# 用户再次确认偏好
new_knowledge = Knowledge(
    user_id="user-123",
    type="preference",
    content="用户喜欢辣食，不吃香菜",  # 内容相同
    summary="食物偏好：喜辣避香菜"
)

# 自动检测重复并更新
updated = updater.update_or_create(
    new_knowledge,
    conflict_strategy="merge"
)

# 置信度和重要性会自动提升
print(f"新置信度: {updated.scores.confidence}")  # 0.95 (from 0.90)
print(f"新重要性: {updated.scores.importance}")  # 0.90 (from 0.85)
```

## 最佳实践

### 1. Embedding策略

```python
# 推荐：双embedding策略
embeddings = {
    "primary": {
        "model": "text-embedding-3-large",  # 高质量，1536维
        "use_for": "主要检索"
    },
    "fast": {
        "model": "bge-small-zh-v1.5",      # 快速，512维
        "use_for": "实时筛选"
    }
}
```

### 2. 评分调整

```python
# 每次访问
knowledge.access_count += 1
knowledge.last_accessed = datetime.now()
knowledge.scores.importance = min(1.0, knowledge.scores.importance + 0.01)

# 每天淡化（定时任务）
days_since_access = (datetime.now() - knowledge.last_accessed).days
if days_since_access > 30:
    knowledge.scores.relevance *= 0.95 ** (days_since_access - 30)
```

### 3. 版本管理

```python
# 创建新版本
def create_version(knowledge, reason):
    version = VersionRecord(
        version=len(knowledge.version_history) + 1,
        content=knowledge.content,
        updated_at=datetime.now(),
        update_reason=reason,
        confidence_delta=0.05,
        updated_by="system"
    )
    knowledge.version_history.append(version)
    
    # 版本压缩
    if len(knowledge.version_history) > 100:
        knowledge.version_history = compress_versions(knowledge.version_history)
```

### 4. 存储优化

```python
# 分层存储策略
storage_strategy = {
    "hot": {  # 热数据：最近30天访问过
        "storage": "Redis/Memory",
        "condition": lambda k: (datetime.now() - k.last_accessed).days < 30
    },
    "warm": {  # 温数据：最近90天访问过
        "storage": "PostgreSQL/MongoDB",
        "condition": lambda k: (datetime.now() - k.last_accessed).days < 90
    },
    "cold": {  # 冷数据：90天以上未访问
        "storage": "S3/OSS",
        "condition": lambda k: (datetime.now() - k.last_accessed).days >= 90
    }
}
```

## 性能优化建议

### 1. 索引设计

```sql
-- PostgreSQL示例
CREATE INDEX idx_user_id ON knowledge(user_id);
CREATE INDEX idx_type_status ON knowledge(type, status);
CREATE INDEX idx_scores ON knowledge((metadata->'scores'->>'importance'));
CREATE INDEX idx_tags ON knowledge USING GIN ((metadata->'tags'));
CREATE INDEX idx_vector ON knowledge USING ivfflat (embedding vector_cosine_ops);
```

### 2. 缓存策略

```python
# 多级缓存
cache_strategy = {
    "L1": "进程内存缓存 - 最热的100条知识",
    "L2": "Redis缓存 - 最近访问的1000条知识",
    "L3": "数据库 - 全部知识"
}
```

### 3. 批量操作

```python
# 批量embedding生成
def batch_embed(knowledge_list, batch_size=100):
    for i in range(0, len(knowledge_list), batch_size):
        batch = knowledge_list[i:i+batch_size]
        texts = [k.content for k in batch]
        vectors = llm_client.embed_batch(texts)
        for k, v in zip(batch, vectors):
            k.embeddings["primary"] = EmbeddingInfo(
                model="text-embedding-3-large",
                vector=v,
                dimension=len(v)
            )
```

## 总结

这个存储格式设计实现了：

1. ✅ **高效检索** - 多层次索引，混合检索策略
2. ✅ **便于更新** - 冲突检测，智能合并，版本追踪
3. ✅ **多模态支持** - 灵活的embedding架构
4. ✅ **算法驱动** - 动态评分，自动淡化
5. ✅ **生产就绪** - 分层存储，性能优化

该设计在保持灵活性的同时，确保了高性能和可扩展性，适用于大规模知识库应用。
