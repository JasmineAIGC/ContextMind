"""
ContextMind 核心功能测试

测试核心组件：ContextEngine、数据模型、Pipeline 处理器
"""

import pytest
import asyncio
from datetime import datetime

from contextmind.models import (
    Message, MessageRole, ContextItem, ContextSource,
    ContextResult, ProcessedContext, Knowledge, KnowledgeType,
    Chunk, ContextState
)

from contextmind.pipeline import (
    InputPreprocessor, ContextReorderer, ContextCompressor
)


class TestDataModels:
    """数据模型测试"""
    
    def test_message_creation(self):
        """Message 创建"""
        msg = Message(
            role=MessageRole.USER,
            content="Hello, world!"
        )
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello, world!"
        assert isinstance(msg.timestamp, datetime)
        assert msg.metadata == {}
    
    def test_message_to_dict(self):
        """Message 转字典"""
        msg = Message(
            role=MessageRole.ASSISTANT,
            content="Hi there!"
        )
        d = msg.to_dict()
        assert d['role'] == 'assistant'
        assert d['content'] == 'Hi there!'
        assert 'timestamp' in d
    
    def test_context_item_creation(self):
        """ContextItem 创建"""
        item = ContextItem(
            content="Test content",
            source=ContextSource.MEMORY,
            score=0.9
        )
        assert item.content == "Test content"
        assert item.source == ContextSource.MEMORY
        assert item.score == 0.9
    
    def test_processed_context(self):
        """ProcessedContext 操作"""
        ctx = ProcessedContext()
        
        item1 = ContextItem(content="Item 1", source=ContextSource.SESSION)
        item2 = ContextItem(content="Item 2", source=ContextSource.MEMORY)
        
        ctx.add_item(item1)
        ctx.add_item(item2)
        
        assert len(ctx.items) == 2
        
        session_items = ctx.get_by_source(ContextSource.SESSION)
        assert len(session_items) == 1
        assert session_items[0].content == "Item 1"
    
    def test_context_result(self):
        """ContextResult 操作"""
        result = ContextResult()
        
        result.recent_history.append(
            Message(role=MessageRole.USER, content="Hello")
        )
        result.long_term_memory.append(
            ContextItem(content="User info", source=ContextSource.MEMORY)
        )
        
        assert len(result.recent_history) == 1
        assert len(result.long_term_memory) == 1
        
        all_items = result.get_all_items()
        assert len(all_items) == 2
    
    def test_knowledge_creation(self):
        """Knowledge 创建"""
        k = Knowledge(
            content="User prefers short answers",
            type=KnowledgeType.PREFERENCE,
            confidence=0.85
        )
        assert k.content == "User prefers short answers"
        assert k.type == KnowledgeType.PREFERENCE
        assert k.confidence == 0.85
    
    def test_chunk_creation(self):
        """Chunk 创建"""
        chunk = Chunk(
            content="Test chunk",
            token_count=10,
            relevance_score=0.9,
            diversity_score=0.5,
            source=ContextSource.EXTERNAL
        )
        assert chunk.content == "Test chunk"
        assert chunk.token_count == 10
        assert chunk.relevance_score == 0.9
        
        # 转换为 ContextItem
        item = chunk.to_context_item()
        assert item.content == "Test chunk"
        assert item.score == 0.9
    
    def test_context_state(self):
        """ContextState 测试"""
        state = ContextState(
            query="Test query",
            budget_limit=4096
        )
        state.add_log("Processing started")
        state.update_token_count("input", 100)
        
        assert state.query == "Test query"
        assert len(state.logs) == 1
        assert state.token_counts["input"] == 100
        assert state.current_usage == 100
        assert state.remaining_budget() == 3996
        assert state.has_budget(1000)


class TestPipeline:
    """Pipeline 组件测试"""
    
    @pytest.mark.asyncio
    async def test_input_processor_basic(self):
        """InputProcessor 基本功能"""
        processor = InputProcessor()
        
        result = await processor.process("  Hello World  ")
        assert result == "Hello World"
    
    @pytest.mark.asyncio
    async def test_input_processor_validation(self):
        """InputProcessor 验证"""
        processor = InputProcessor(min_length=5)
        
        with pytest.raises(ValueError):
            await processor.process("Hi")
    
    @pytest.mark.asyncio
    async def test_context_integrator_deduplication(self):
        """ContextIntegrator 去重"""
        integrator = ContextIntegrator(deduplicate=True)
        
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(content="Same content", source=ContextSource.SESSION))
        ctx.add_item(ContextItem(content="Same content", source=ContextSource.MEMORY))
        ctx.add_item(ContextItem(content="Different content", source=ContextSource.SESSION))
        
        result = await integrator.integrate(ctx)
        
        assert len(result.items) == 2
    
    @pytest.mark.asyncio
    async def test_context_optimizer_truncation(self):
        """ContextOptimizer 截断"""
        optimizer = ContextOptimizer()
        
        ctx = ProcessedContext()
        for i in range(10):
            ctx.add_item(ContextItem(
                content=f"Item {i} with some content",
                source=ContextSource.SESSION,
                score=1.0 - i * 0.1
            ))
        
        result = await optimizer.optimize(ctx, max_items=5)
        
        assert len(result.items) == 5


class TestFoundation:
    """Foundation 服务测试"""
    
    def test_tokenizer_simple(self):
        """TokenizerService 简单模式"""
        tokenizer = TokenizerService(
            tokenizer_type=TokenizerType.SIMPLE
        )
        
        count = tokenizer.count_tokens("Hello world test")
        assert count == 3
    
    def test_tokenizer_estimate(self):
        """TokenizerService 估算"""
        tokenizer = TokenizerService()
        
        # 英文估算
        estimate = tokenizer.estimate_tokens("Hello world")
        assert estimate > 0
        
        # 中文估算
        estimate_cn = tokenizer.estimate_tokens("你好世界")
        assert estimate_cn > 0
    
    def test_cache_manager_basic(self):
        """CacheManager 基本操作"""
        cache = CacheManager(max_size=100)
        
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        
        assert cache.get("nonexistent") is None
        
        cache.delete("key1")
        assert cache.get("key1") is None
    
    def test_cache_manager_lru(self):
        """CacheManager LRU 驱逐"""
        cache = CacheManager(max_size=3)
        
        cache.set("a", 1)
        cache.set("b", 2)
        cache.set("c", 3)
        cache.set("d", 4)
        
        assert cache.get("a") is None
        assert cache.get("d") == 4
    
    def test_cache_manager_stats(self):
        """CacheManager 统计"""
        cache = CacheManager(max_size=100)
        
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1


class TestAgentMemorySystem:
    """Agent Memory System 测试"""
    
    def test_memory_note_creation(self):
        """MemoryNote 创建"""
        from contextmind.models import MemoryNote, MemoryType
        
        note = MemoryNote(
            id="test001",
            content="用户喜欢简洁的回答",
            memory_type=MemoryType.SEMANTIC,
            keywords=["用户", "喜欢", "简洁"],
            tags=["偏好"],
        )
        
        assert note.id == "test001"
        assert note.content == "用户喜欢简洁的回答"
        assert note.memory_type == MemoryType.SEMANTIC
        assert len(note.keywords) == 3
        assert note.importance_score == 0.5
        assert note.access_count == 0
    
    def test_memory_note_access(self):
        """MemoryNote 访问记录"""
        from contextmind.models import MemoryNote, MemoryType
        
        note = MemoryNote(id="test002", content="测试内容")
        
        assert note.access_count == 0
        assert note.last_accessed is None
        
        note.access()
        assert note.access_count == 1
        assert note.last_accessed is not None
        
        note.access()
        assert note.access_count == 2
    
    def test_memory_note_linking(self):
        """MemoryNote 关联"""
        from contextmind.models import MemoryNote, MemoryType
        
        note1 = MemoryNote(id="note1", content="内容1")
        note2 = MemoryNote(id="note2", content="内容2")
        
        note1.add_link("note2")
        assert "note2" in note1.linked_memories
        
        # 防止重复
        note1.add_link("note2")
        assert note1.linked_memories.count("note2") == 1
    
    def test_memory_note_importance_update(self):
        """MemoryNote 重要性更新"""
        from contextmind.models import MemoryNote, MemoryType
        
        note = MemoryNote(id="test003", content="测试", importance_score=0.8)
        
        # 多次访问
        for _ in range(5):
            note.access()
        
        note.update_importance(decay_factor=0.95)
        
        # 重要性基于访问热度变化
        assert note.importance_score != 0.8
    
    def test_memory_note_to_context_item(self):
        """MemoryNote 转 ContextItem"""
        from contextmind.models import MemoryNote, MemoryType, ContextSource
        
        note = MemoryNote(
            id="test004",
            content="测试内容",
            memory_type=MemoryType.EPISODIC,
            keywords=["测试"],
            importance_score=0.75,
        )
        
        item = note.to_context_item()
        
        assert item.content == "测试内容"
        assert item.source == ContextSource.MEMORY
        assert item.score == 0.75
        assert item.metadata["memory_id"] == "test004"
        assert item.metadata["memory_type"] == "episodic"
    
    def test_memory_type_enum(self):
        """MemoryType 枚举"""
        from contextmind.models import MemoryType
        
        assert MemoryType.WORKING.value == "working"
        assert MemoryType.SEMANTIC.value == "semantic"
        assert MemoryType.EPISODIC.value == "episodic"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
