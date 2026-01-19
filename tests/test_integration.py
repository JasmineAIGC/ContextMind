"""
Integration test to verify the ProcessedContext → ContextResult pipeline flow.

This test simulates the entire pipeline to ensure type safety throughout.
"""

import pytest
from contextmind.data_models import (
    ProcessedContext, ContextResult, ContextItem, ContextSource,
    Message, MessageRole
)
from contextmind.strategies.optimization import CompressionStrategy, RerankingStrategy
from contextmind.modules.compressor import ContextCompressor


class TestPipelineIntegration:
    """测试完整的 pipeline 流程"""
    
    @pytest.mark.asyncio
    async def test_full_optimization_pipeline(self):
        """测试完整的优化 pipeline"""
        # 1. 创建 ProcessedContext（模拟 retriever 的输出）
        ctx = ProcessedContext()
        
        # 添加会话条目
        ctx.add_item(ContextItem(
            content="user: What's the weather?",
            source=ContextSource.SESSION,
            score=1.0
        ))
        ctx.add_item(ContextItem(
            content="assistant: I'll check for you.",
            source=ContextSource.SESSION,
            score=1.0
        ))
        
        # 添加记忆条目
        ctx.add_item(ContextItem(
            content="User lives in San Francisco",
            source=ContextSource.MEMORY,
            score=0.8
        ))
        ctx.add_item(ContextItem(
            content="User prefers Celsius",
            source=ContextSource.MEMORY,
            score=0.7
        ))
        
        # 添加知识条目
        ctx.add_item(ContextItem(
            content="Weather API documentation",
            source=ContextSource.KNOWLEDGE,
            score=0.6
        ))
        
        # 验证 ProcessedContext 不应该有这些属性
        assert not hasattr(ctx, 'recent_history')
        assert not hasattr(ctx, 'long_term_memory')
        assert not hasattr(ctx, 'external_knowledge')
        
        # 2. 通过压缩策略处理（应该返回 ContextResult）
        strategy = CompressionStrategy(max_items=10)
        result = await strategy.optimize(ctx)
        
        # 3. 验证返回类型
        assert isinstance(result, ContextResult)
        assert not isinstance(result, ProcessedContext)
        
        # 4. 验证 ContextResult 有正确的属性
        assert hasattr(result, 'recent_history')
        assert hasattr(result, 'long_term_memory')
        assert hasattr(result, 'external_knowledge')
        
        # 不应该有 items 属性
        assert not hasattr(result, 'items')
        
        # 5. 验证内容被正确分类
        assert len(result.recent_history) == 2
        assert len(result.long_term_memory) == 2
        assert len(result.external_knowledge) == 1
        
        # 6. 验证会话消息被正确解析
        assert result.recent_history[0].role == MessageRole.USER
        assert "weather" in result.recent_history[0].content.lower()
        assert result.recent_history[1].role == MessageRole.ASSISTANT
        
        # 7. 验证记忆条目内容
        memory_contents = [item.content for item in result.long_term_memory]
        assert "San Francisco" in memory_contents[0] or "San Francisco" in memory_contents[1]
        
    @pytest.mark.asyncio
    async def test_compressor_module_returns_context_result(self):
        """测试 ContextCompressor 模块返回 ContextResult"""
        compressor = ContextCompressor()
        
        ctx = ProcessedContext()
        for i in range(5):
            ctx.add_item(ContextItem(
                content=f"user: Message {i}",
                source=ContextSource.SESSION,
                score=1.0
            ))
        
        result = await compressor.compress(ctx)
        
        # 验证返回类型
        assert isinstance(result, ContextResult)
        assert hasattr(result, 'recent_history')
        assert not hasattr(result, 'items')
        
    @pytest.mark.asyncio
    async def test_reranking_then_compression(self):
        """测试重排序后压缩的 pipeline"""
        # 创建带有不同分数的上下文
        ctx = ProcessedContext()
        
        # 添加不同分数的条目
        for i in range(10):
            ctx.add_item(ContextItem(
                content=f"user: Memory item {i}",
                source=ContextSource.SESSION,
                score=0.5 + i * 0.05  # 分数从 0.5 到 0.95
            ))
        
        # 先重排序（中间步骤，返回 ProcessedContext）
        rerank_strategy = RerankingStrategy(keep_recent_at_end=False)
        reranked_ctx = await rerank_strategy.optimize(ctx)
        
        # 验证重排序返回 ProcessedContext
        assert isinstance(reranked_ctx, ProcessedContext)
        assert hasattr(reranked_ctx, 'items')
        assert not hasattr(reranked_ctx, 'recent_history')
        
        # 然后压缩（最终步骤，返回 ContextResult）
        compress_strategy = CompressionStrategy()
        final_result = await compress_strategy.optimize(reranked_ctx)
        
        # 验证压缩返回 ContextResult
        assert isinstance(final_result, ContextResult)
        assert hasattr(final_result, 'recent_history')
        assert len(final_result.recent_history) > 0
        
    @pytest.mark.asyncio
    async def test_mixed_sources_pipeline(self):
        """测试混合来源的 pipeline"""
        ctx = ProcessedContext()
        
        # 添加所有四种来源的条目
        ctx.add_item(ContextItem(
            content="user: Hello",
            source=ContextSource.SESSION
        ))
        ctx.add_item(ContextItem(
            content="User preference",
            source=ContextSource.MEMORY
        ))
        ctx.add_item(ContextItem(
            content="Domain knowledge",
            source=ContextSource.KNOWLEDGE
        ))
        ctx.add_item(ContextItem(
            content="External fact",
            source=ContextSource.EXTERNAL
        ))
        
        strategy = CompressionStrategy()
        result = await strategy.optimize(ctx)
        
        # 验证所有来源都被正确处理
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 1
        assert len(result.long_term_memory) == 1
        # KNOWLEDGE 和 EXTERNAL 都应该在 external_knowledge
        assert len(result.external_knowledge) == 2
        
    @pytest.mark.asyncio
    async def test_empty_context_pipeline(self):
        """测试空上下文的 pipeline"""
        ctx = ProcessedContext()
        
        strategy = CompressionStrategy()
        result = await strategy.optimize(ctx)
        
        # 验证空上下文也能正确处理
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 0
        assert len(result.long_term_memory) == 0
        assert len(result.external_knowledge) == 0
        
    def test_direct_conversion(self):
        """测试直接转换方法"""
        ctx = ProcessedContext()
        ctx.add_item(ContextItem(
            content="user: Test",
            source=ContextSource.SESSION
        ))
        ctx.metadata['test_key'] = 'test_value'
        
        # 直接调用 to_context_result
        result = ctx.to_context_result()
        
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) == 1
        assert result.metadata['test_key'] == 'test_value'
        
    @pytest.mark.asyncio
    async def test_large_context_truncation(self):
        """测试大上下文的截断"""
        ctx = ProcessedContext()
        
        # 添加大量条目
        for i in range(100):
            ctx.add_item(ContextItem(
                content=f"user: Long message number {i} " + "x" * 100,
                source=ContextSource.SESSION,
                score=1.0
            ))
        
        # 使用严格的限制
        strategy = CompressionStrategy(max_tokens=500, max_items=5)
        result = await strategy.optimize(ctx)
        
        # 验证被截断
        assert isinstance(result, ContextResult)
        assert len(result.recent_history) <= 5
        assert 'truncated' in result.metadata or len(result.recent_history) < 100
