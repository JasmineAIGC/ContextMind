"""
Template-based Context Optimization Demo - 模板优化演示

演示如何使用提示词模板和意图提取来优化上下文。
"""

import asyncio
from contextmind.core.prompt_template import PromptTemplate, TemplateSlot, DEFAULT_CHAT_TEMPLATE
from contextmind.pipeline.intent_extractor import IntentExtractor
from contextmind.pipeline.template_optimizer import TemplateBasedOptimization
from contextmind.core.data_models import Message, ContextItem, ProcessedContext
from contextmind.core.types import MessageRole, ContextSource
from contextmind.utils.logger import get_logger

logger = get_logger(__name__)


async def demo_basic_template():
    """演示基础模板使用"""
    print("\n" + "=" * 80)
    print("演示 1: 基础模板使用")
    print("=" * 80 + "\n")
    
    # 创建一个简单的模板
    template = PromptTemplate(
        template_id="demo_template",
        name="演示模板",
        template_text="""你是一个智能助手。

用户意图: {intent}
对话主题: {topic}

请根据用户意图回复。"""
    )
    
    print(f"模板名称: {template.name}")
    print(f"槽位数量: {len(template.slots)}")
    print(f"槽位列表: {template.get_slot_names()}")
    print()
    
    # 填充槽位
    slot_values = {
        'intent': '用户想了解天气情况',
        'topic': '天气查询'
    }
    
    filled = template.fill_slots(slot_values)
    print("填充后的模板:")
    print("-" * 80)
    print(filled)
    print("-" * 80)


async def demo_intent_extraction():
    """演示意图提取"""
    print("\n" + "=" * 80)
    print("演示 2: 意图提取")
    print("=" * 80 + "\n")
    
    # 创建意图提取器
    extractor = IntentExtractor()
    
    # 模拟对话历史
    messages = [
        Message(role=MessageRole.USER, content="你好"),
        Message(role=MessageRole.ASSISTANT, content="你好！有什么可以帮助你的？"),
        Message(role=MessageRole.USER, content="今天天气怎么样？"),
    ]
    
    print("对话历史:")
    for i, msg in enumerate(messages, 1):
        print(f"  {i}. {msg.role.value}: {msg.content}")
    print()
    
    # 提取意图
    intent = await extractor.extract_intent(messages)
    print(f"提取的意图:")
    print(f"  类型: {intent.intent_type}")
    print(f"  描述: {intent.description}")
    print(f"  置信度: {intent.confidence:.2f}")
    print()
    
    # 提取主题
    topic = await extractor.extract_topic(messages)
    print(f"提取的主题: {topic}")
    print()
    
    # 提取上下文摘要
    context_summary = await extractor.extract_context_summary(messages)
    print(f"上下文摘要: {context_summary}")


async def demo_template_optimization():
    """演示完整的模板优化流程"""
    print("\n" + "=" * 80)
    print("演示 3: 模板优化流程")
    print("=" * 80 + "\n")
    
    # 创建模板优化器
    optimizer = TemplateBasedOptimization(template=DEFAULT_CHAT_TEMPLATE)
    
    # 模拟对话历史（转换为ContextItem）
    history_items = [
        ContextItem(
            content="user: 你好",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="assistant: 你好！有什么可以帮助你的？",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="user: 我想了解Python编程",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="assistant: Python是一门很棒的编程语言！你想学习哪方面？",
            source=ContextSource.HISTORY,
            score=1.0
        ),
        ContextItem(
            content="user: 如何使用装饰器？",
            source=ContextSource.HISTORY,
            score=1.0
        ),
    ]
    
    # 添加一些长期记忆
    memory_items = [
        ContextItem(
            content="用户对编程感兴趣",
            source=ContextSource.MEMORY,
            score=0.85
        ),
        ContextItem(
            content="用户正在学习Python",
            source=ContextSource.MEMORY,
            score=0.90
        ),
    ]
    
    # 构建上下文
    context = ProcessedContext(
        items=history_items + memory_items,
        metadata={'total_items': len(history_items) + len(memory_items)}
    )
    
    print(f"原始上下文: {len(context.items)} 项")
    print()
    
    # 执行优化
    result = await optimizer.optimize(context)
    
    print(f"\n优化结果:")
    print(f"  优化后项数: {len(result.items)}")
    print(f"  是否压缩: {result.compressed}")
    print(f"  优化方法: {result.metadata.get('optimization_method')}")
    print()
    
    # 显示优化后的内容
    if result.items:
        print("优化后的第一项内容:")
        print("-" * 80)
        print(result.items[0].content)
        print("-" * 80)
        print()
        
        # 显示元数据
        print("元数据:")
        for key, value in result.items[0].metadata.items():
            if key != 'slot_values':  # slot_values 单独显示
                print(f"  {key}: {value}")
        
        if 'slot_values' in result.items[0].metadata:
            print("\n  槽位值:")
            for slot, value in result.items[0].metadata['slot_values'].items():
                print(f"    {slot}: {value[:60]}..." if len(value) > 60 else f"    {slot}: {value}")


async def demo_custom_template():
    """演示自定义模板"""
    print("\n" + "=" * 80)
    print("演示 4: 自定义模板")
    print("=" * 80 + "\n")
    
    # 创建一个客服场景的模板
    customer_service_template = PromptTemplate(
        template_id="customer_service",
        name="客服模板",
        template_text="""你是一个专业的客服助手。

## 客户意图
{intent}

## 问题分类
{topic}

## 历史上下文
{context}

## 用户信息
{user_info}

请专业、礼貌地回复客户。如果需要转人工，请明确说明。""",
        slots=[
            TemplateSlot(name="intent", description="客户意图", required=True),
            TemplateSlot(name="topic", description="问题分类", required=True),
            TemplateSlot(name="context", description="历史上下文", default_value="首次咨询"),
            TemplateSlot(name="user_info", description="用户信息", default_value="普通用户"),
        ]
    )
    
    print(f"模板名称: {customer_service_template.name}")
    print(f"模板ID: {customer_service_template.template_id}")
    print(f"槽位数量: {len(customer_service_template.slots)}")
    print()
    
    # 填充槽位
    values = {
        'intent': '咨询退货政策',
        'topic': '售后服务',
        'context': '用户在3天前购买了商品，现在想退货',
        'user_info': 'VIP会员'
    }
    
    filled = customer_service_template.fill_slots(values)
    print("填充后的客服模板:")
    print("-" * 80)
    print(filled)
    print("-" * 80)


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("模板优化系统演示")
    print("=" * 80)
    
    # 运行所有演示
    await demo_basic_template()
    await demo_intent_extraction()
    await demo_template_optimization()
    await demo_custom_template()
    
    print("\n" + "=" * 80)
    print("演示完成！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
