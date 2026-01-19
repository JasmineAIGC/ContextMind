"""
ContextMind Type Safety Tests

测试 ProcessedContext 和 ContextResult 之间的类型安全和边界。
这些测试确保不会出现属性访问错误。
"""

import pytest
from datetime import datetime

from contextmind.data_models import (
    Message, MessageRole, ContextItem, ContextSource,
    ContextResult, ProcessedContext
)
from contextmind.strategies.optimization import CompressionStrategy, RerankingStrategy


class TestProcessedContextBoundary:
    """测试 ProcessedContext 的边界和限制"""
    
    def test_processed_context_has_items(self):
        """ProcessedContext 应该有 items 属性"""
        ctx = ProcessedContext()
        assert hasattr(ctx, 'items')
        assert hasattr(ctx, 'metadata')
        assert isinstance(ctx.items, list)
        assert isinstance(ctx.metadata, dict)
    
    def test_processed_context_no_recent_history(self):
        """ProcessedContext 不应该有 recent_history 属性"""
        ctx = ProcessedContext()
        assert not hasattr(ctx, 'recent_history')
    
    def test_processed_context_no_long_term_memory(self):
        """ProcessedContext 不应该有 long_term_memory 属性"""
        ctx = ProcessedContext()
        assert not hasattr(ctx, 'long_term_memory')
    
    def test_processed_context_no_external_knowledge(self):
        """ProcessedContext 不应该有 external_knowledge 属性"""
        ctx = ProcessedContext()
        assert not hasattr(ctx, 'external_knowledge')
    
    def test_processed_context_get_by_source(self):
        """ProcessedContext 应该提供 get_by_source 方法"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(content="Session", source=ContextSource.SESSION))
        ctx.add_item(ContextItem(content="Memory", source=ContextSource.MEMORY))
        ctx.add_item(ContextItem(content="Session2", source=ContextSource.SESSION))
        
        session_items = ctx.get_by_source(ContextSource.SESSION)
        assert len(session_items) == 2
        
        memory_items = ctx.get_by_source(ContextSource.MEMORY)
        assert len(memory_items) == 1


class TestContextResultBoundary:
    """测试 ContextResult 的边界和限制"""
    
    def test_context_result_has_categorized_attributes(self):
        """ContextResult 应该有分类的属性"""
        result = ContextResult()
        assert hasattr(result, 'recent_history')
        assert hasattr(result, 'long_term_memory')
        assert hasattr(result, 'external_knowledge')
        assert hasattr(result, 'metadata')
    
    def test_context_result_no_items(self):
        """ContextResult 不应该有 items 属性"""
        result = ContextResult()
        assert not hasattr(result, 'items')
    
    def test_context_result_attributes_are_lists(self):
        """ContextResult 的属性应该是列表"""
        result = ContextResult()
        assert isinstance(result.recent_history, list)
        assert isinstance(result.long_term_memory, list)
        assert isinstance(result.external_knowledge, list)
        assert isinstance(result.metadata, dict)
    
    def test_context_result_get_all_items(self):
        """ContextResult 应该提供 get_all_items 方法"""
        result = ContextResult()
        result.recent_history.append(
            Message(role=MessageRole.USER, content="Hello")
        )
        result.long_term_memory.append(
            ContextItem(content="Memory", source=ContextSource.MEMORY)
        )
        
        all_items = result.get_all_items()
        assert len(all_items) == 2
        assert all(isinstance(item, ContextItem) for item in all_items)


class TestProcessedContextToContextResult:
    """测试 ProcessedContext → ContextResult 的转换"""
    
    def test_to_context_result_basic(self):
        """基本的转换测试"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="user: Hello",
            source=ContextSource.SESSION
        ))
        ctx.add_item(ContextItem(
            content="Memory item",
            source=ContextSource.MEMORY
        ))
        ctx.add_item(ContextItem(
            content="Knowledge item",
            source=ContextSource.KNOWLEDGE
        ))
        
        result = ctx.to_context_result()
        
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 1
        assert len(result.long_term_memory) == 1
        assert len(result.external_knowledge) == 1
    
    def test_to_context_result_session_parsing(self):
        """测试会话消息的解析"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="user: Hello there",
            source=ContextSource.SESSION
        ))
        ctx.add_item(ContextItem(
            content="assistant: Hi! How can I help?",
            source=ContextSource.SESSION
        ))
        
        result = ctx.to_context_result()
        
        assert len(result.recent_history) == 2
        assert result.recent_history[0].role == MessageRole.USER
        assert result.recent_history[0].content == "Hello there"
        assert result.recent_history[1].role == MessageRole.ASSISTANT
        assert result.recent_history[1].content == "Hi! How can I help?"
    
    def test_to_context_result_malformed_session(self):
        """测试格式错误的会话消息"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="Malformed message without role",
            source=ContextSource.SESSION
        ))
        
        result = ctx.to_context_result()
        
        # 应该创建为 SYSTEM 消息
        assert len(result.recent_history) == 1
        assert result.recent_history[0].role == MessageRole.SYSTEM
        assert result.recent_history[0].content == "Malformed message without role"
    
    def test_to_context_result_invalid_role(self):
        """测试无效的角色"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="invalidrole: Some content",
            source=ContextSource.SESSION
        ))
        
        result = ctx.to_context_result()
        
        # 应该创建为 SYSTEM 消息
        assert len(result.recent_history) == 1
        assert result.recent_history[0].role == MessageRole.SYSTEM
    
    def test_to_context_result_empty_role(self):
        """测试空角色字符串"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content=": Some content",
            source=ContextSource.SESSION
        ))
        
        result = ctx.to_context_result()
        
        # 应该创建为 SYSTEM 消息
        assert len(result.recent_history) == 1
        assert result.recent_history[0].role == MessageRole.SYSTEM
    
    def test_to_context_result_external_source(self):
        """测试 EXTERNAL 来源"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="External item",
            source=ContextSource.EXTERNAL
        ))
        
        result = ctx.to_context_result()
        
        assert len(result.external_knowledge) == 1
        assert result.external_knowledge[0].content == "External item"
    
    def test_to_context_result_metadata_preserved(self):
        """测试元数据是否被保留"""
        ctx = ProcessedContext()
        ctx.metadata['test_key'] = 'test_value'
        ctx.metadata['count'] = 42
        
        result = ctx.to_context_result()
        
        assert result.metadata['test_key'] == 'test_value'
        assert result.metadata['count'] == 42
    
    def test_to_context_result_item_metadata_preserved(self):
        """测试条目元数据是否被保留"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="user: Test",
            source=ContextSource.SESSION,
            metadata={'item_id': 123}
        ))
        
        result = ctx.to_context_result()
        
        assert result.recent_history[0].metadata['item_id'] == 123


class TestOptimizationStrategyReturnTypes:
    """测试优化策略的返回类型"""
    
    @pytest.mark.asyncio
    async def test_compression_strategy_returns_context_result(self):
        """CompressionStrategy 应该返回 ContextResult"""
        strategy = CompressionStrategy(max_items=5)
        ctx = ProcessedContext()
        
        for i in range(10):
            ctx.add_item(ContextItem(
                content=f"user: Item {i}",
                source=ContextSource.SESSION,
                score=1.0
            ))
        
        result = await strategy.optimize(ctx)
        
        # 应该返回 ContextResult，不是 ProcessedContext
        assert isinstance(result, ContextResult)
        assert not isinstance(result, ProcessedContext)
        
        # 应该有 recent_history 而不是 items
        assert hasattr(result, 'recent_history')
        assert not hasattr(result, 'items')
    
    @pytest.mark.asyncio
    async def test_reranking_strategy_returns_context_result(self):
        """RerankingStrategy 应该返回 ContextResult"""
        strategy = RerankingStrategy()
        ctx = ProcessedContext()
        
        for i in range(5):
            ctx.add_item(ContextItem(
                content=f"Memory {i}",
                source=ContextSource.MEMORY,
                score=0.5 + i * 0.1
            ))
        
        result = await strategy.optimize(ctx)
        
        # 应该返回 ContextResult
        assert isinstance(result, ContextResult)
        assert hasattr(result, 'long_term_memory')
        assert not hasattr(result, 'items')


class TestAttributeAccessSafety:
    """测试属性访问的安全性"""
    
    def test_accessing_recent_history_on_processed_context_raises_error(self):
        """尝试访问 ProcessedContext.recent_history 应该引发 AttributeError"""
        ctx = ProcessedContext()
        
        with pytest.raises(AttributeError):
            _ = ctx.recent_history
    
    def test_accessing_long_term_memory_on_processed_context_raises_error(self):
        """尝试访问 ProcessedContext.long_term_memory 应该引发 AttributeError"""
        ctx = ProcessedContext()
        
        with pytest.raises(AttributeError):
            _ = ctx.long_term_memory
    
    def test_accessing_external_knowledge_on_processed_context_raises_error(self):
        """尝试访问 ProcessedContext.external_knowledge 应该引发 AttributeError"""
        ctx = ProcessedContext()
        
        with pytest.raises(AttributeError):
            _ = ctx.external_knowledge
    
    def test_accessing_items_on_context_result_raises_error(self):
        """尝试访问 ContextResult.items 应该引发 AttributeError"""
        result = ContextResult()
        
        with pytest.raises(AttributeError):
            _ = result.items


class TestEdgeCases:
    """测试边界情况"""
    
    def test_empty_processed_context_to_context_result(self):
        """空的 ProcessedContext 转换"""
        ctx = ProcessedContext()
        result = ctx.to_context_result()
        
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 0
        assert len(result.long_term_memory) == 0
        assert len(result.external_knowledge) == 0
    
    def test_mixed_sources_conversion(self):
        """混合来源的转换"""
        ctx = ProcessedContext()
        
        # 添加各种来源的条目
        ctx.add_item(ContextItem(content="user: Q1", source=ContextSource.SESSION))
        ctx.add_item(ContextItem(content="assistant: A1", source=ContextSource.SESSION))
        ctx.add_item(ContextItem(content="Mem1", source=ContextSource.MEMORY))
        ctx.add_item(ContextItem(content="Mem2", source=ContextSource.MEMORY))
        ctx.add_item(ContextItem(content="Know1", source=ContextSource.KNOWLEDGE))
        ctx.add_item(ContextItem(content="Ext1", source=ContextSource.EXTERNAL))
        
        result = ctx.to_context_result()
        
        assert len(result.recent_history) == 2
        assert len(result.long_term_memory) == 2
        # KNOWLEDGE 和 EXTERNAL 都应该在 external_knowledge 中
        assert len(result.external_knowledge) == 2
    
    @pytest.mark.asyncio
    async def test_optimization_with_no_items(self):
        """优化空上下文"""
        strategy = CompressionStrategy()
        ctx = ProcessedContext()
        
        result = await strategy.optimize(ctx)
        
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 0
        assert len(result.long_term_memory) == 0
        assert len(result.external_knowledge) == 0


class TestDocumentationAndUsageGuidance:
    """测试文档字符串和使用指南"""
    
    def test_processed_context_has_usage_docs(self):
        """ProcessedContext 应该有使用指南"""
        doc = ProcessedContext.__doc__
        assert doc is not None
        assert 'ProcessedContext vs ContextResult' in doc or 'items' in doc
    
    def test_context_result_has_usage_docs(self):
        """ContextResult 应该有使用指南"""
        doc = ContextResult.__doc__
        assert doc is not None
        assert 'recent_history' in doc or 'long_term_memory' in doc
    
    def test_to_context_result_has_usage_docs(self):
        """to_context_result 方法应该有使用指南"""
        doc = ProcessedContext.to_context_result.__doc__
        assert doc is not None
        assert 'ContextResult' in doc
