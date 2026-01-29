"""
Tests for Template-based Context Optimization

Basic tests to verify the core functionality of the template system.
"""

import asyncio
try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False
    # Mock pytest.mark.asyncio decorator if pytest not available
    class MockPytest:
        class mark:
            @staticmethod
            def asyncio(func):
                return func
    pytest = MockPytest()

from contextmind.core.prompt_template import PromptTemplate, TemplateSlot, DEFAULT_CHAT_TEMPLATE
from contextmind.pipeline.intent_extractor import IntentExtractor, ExtractedIntent
from contextmind.pipeline.template_optimizer import TemplateBasedOptimization
from contextmind.core.data_models import Message, ContextItem, ProcessedContext
from contextmind.core.types import MessageRole, ContextSource


def test_prompt_template_creation():
    """Test creating a prompt template"""
    template = PromptTemplate(
        template_id="test",
        name="Test Template",
        template_text="Hello {name}, your intent is {intent}."
    )
    
    assert template.template_id == "test"
    assert template.name == "Test Template"
    assert len(template.slots) == 2
    assert "name" in template.get_slot_names()
    assert "intent" in template.get_slot_names()


def test_template_slot_filling():
    """Test filling template slots"""
    template = PromptTemplate(
        template_id="test",
        name="Test",
        template_text="Intent: {intent}, Topic: {topic}"
    )
    
    result = template.fill_slots({
        'intent': 'asking question',
        'topic': 'weather'
    })
    
    assert "Intent: asking question" in result
    assert "Topic: weather" in result


def test_template_with_defaults():
    """Test template with default values"""
    template = PromptTemplate(
        template_id="test",
        name="Test",
        template_text="Value: {value}",
        slots=[
            TemplateSlot(name="value", default_value="default")
        ]
    )
    
    # Without providing value
    result = template.fill_slots({})
    assert "Value: default" in result
    
    # With providing value
    result = template.fill_slots({'value': 'custom'})
    assert "Value: custom" in result


def test_default_chat_template():
    """Test the default chat template"""
    assert DEFAULT_CHAT_TEMPLATE is not None
    assert "intent" in DEFAULT_CHAT_TEMPLATE.get_slot_names()
    assert "topic" in DEFAULT_CHAT_TEMPLATE.get_slot_names()
    assert "context" in DEFAULT_CHAT_TEMPLATE.get_slot_names()


@pytest.mark.asyncio
async def test_intent_extractor_basic():
    """Test basic intent extraction"""
    extractor = IntentExtractor()
    
    messages = [
        Message(role=MessageRole.USER, content="你好"),
        Message(role=MessageRole.ASSISTANT, content="你好！"),
        Message(role=MessageRole.USER, content="今天天气怎么样？"),
    ]
    
    intent = await extractor.extract_intent(messages)
    
    assert intent is not None
    assert isinstance(intent, ExtractedIntent)
    assert intent.intent_type is not None
    assert intent.description is not None
    assert 0 <= intent.confidence <= 1


@pytest.mark.asyncio
async def test_intent_extractor_greeting():
    """Test greeting intent detection"""
    extractor = IntentExtractor()
    
    messages = [
        Message(role=MessageRole.USER, content="你好"),
    ]
    
    intent = await extractor.extract_intent(messages)
    assert intent.intent_type == "greeting"


@pytest.mark.asyncio
async def test_intent_extractor_question():
    """Test question intent detection"""
    extractor = IntentExtractor()
    
    messages = [
        Message(role=MessageRole.USER, content="什么是机器学习？"),
    ]
    
    intent = await extractor.extract_intent(messages)
    assert intent.intent_type == "question"


@pytest.mark.asyncio
async def test_topic_extraction():
    """Test topic extraction"""
    extractor = IntentExtractor()
    
    messages = [
        Message(role=MessageRole.USER, content="我想学习Python编程"),
    ]
    
    topic = await extractor.extract_topic(messages)
    assert topic is not None
    assert len(topic) > 0


@pytest.mark.asyncio
async def test_context_summary():
    """Test context summary extraction"""
    extractor = IntentExtractor()
    
    messages = [
        Message(role=MessageRole.USER, content="你好"),
        Message(role=MessageRole.ASSISTANT, content="你好！有什么可以帮助你的？"),
        Message(role=MessageRole.USER, content="我想了解Python"),
    ]
    
    summary = await extractor.extract_context_summary(messages)
    assert summary is not None
    assert len(summary) > 0


@pytest.mark.asyncio
async def test_template_optimization():
    """Test template-based optimization"""
    optimizer = TemplateBasedOptimization()
    
    # Create context with history items
    history_items = [
        ContextItem(
            content="user: 你好",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="assistant: 你好！",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="user: 今天天气怎么样？",
            source=ContextSource.HISTORY,
            score=1.0
        ),
    ]
    
    context = ProcessedContext(items=history_items)
    
    # Optimize
    result = await optimizer.optimize(context)
    
    assert result is not None
    assert len(result.items) > 0
    assert result.compressed is True
    assert result.metadata.get('optimization_method') == 'template_based'


@pytest.mark.asyncio
async def test_optimization_with_memory():
    """Test optimization with both history and memory"""
    optimizer = TemplateBasedOptimization()
    
    history_items = [
        ContextItem(
            content="user: 我喜欢Python",
            source=ContextSource.HISTORY,
            score=1.0
        ),
    ]
    
    memory_items = [
        ContextItem(
            content="用户对编程感兴趣",
            source=ContextSource.MEMORY,
            score=0.9
        ),
    ]
    
    context = ProcessedContext(items=history_items + memory_items)
    result = await optimizer.optimize(context)
    
    assert result is not None
    # Should have optimized template + some memory items
    assert len(result.items) >= 1


def test_template_validation():
    """Test template slot validation"""
    template = PromptTemplate(
        template_id="test",
        name="Test",
        template_text="{required_slot}",
        slots=[
            TemplateSlot(name="required_slot", required=True)
        ]
    )
    
    # Valid
    is_valid, errors = template.validate_slots({'required_slot': 'value'})
    assert is_valid is True
    assert len(errors) == 0
    
    # Invalid - missing required
    is_valid, errors = template.validate_slots({})
    assert is_valid is False
    assert len(errors) > 0


if __name__ == "__main__":
    # Run tests
    print("Running Template Optimization Tests...")
    
    # Sync tests
    test_prompt_template_creation()
    print("✓ Template creation test passed")
    
    test_template_slot_filling()
    print("✓ Slot filling test passed")
    
    test_template_with_defaults()
    print("✓ Default values test passed")
    
    test_default_chat_template()
    print("✓ Default template test passed")
    
    test_template_validation()
    print("✓ Template validation test passed")
    
    # Async tests
    async def run_async_tests():
        await test_intent_extractor_basic()
        print("✓ Basic intent extraction test passed")
        
        await test_intent_extractor_greeting()
        print("✓ Greeting detection test passed")
        
        await test_intent_extractor_question()
        print("✓ Question detection test passed")
        
        await test_topic_extraction()
        print("✓ Topic extraction test passed")
        
        await test_context_summary()
        print("✓ Context summary test passed")
        
        await test_template_optimization()
        print("✓ Template optimization test passed")
        
        await test_optimization_with_memory()
        print("✓ Optimization with memory test passed")
    
    asyncio.run(run_async_tests())
    
    print("\n✅ All tests passed!")
