"""
Integration Example: Using Template-based Optimization with ContextEngine

This example demonstrates how to integrate the template-based optimization
into a real conversation scenario.
"""

import asyncio
from contextmind import ContextEngine
from contextmind.pipeline import TemplateBasedOptimization
from contextmind.core import PromptTemplate, TemplateSlot
from contextmind.core.data_models import ProcessedContext
from contextmind.utils.logger import get_logger

logger = get_logger(__name__)


async def simple_chat_example():
    """
    简单的对话示例，演示如何使用模板优化
    """
    print("\n" + "=" * 80)
    print("示例 1: 简单对话场景")
    print("=" * 80 + "\n")
    
    # 1. 初始化 ContextEngine
    engine = ContextEngine(
        app_name="template-demo",
        user_id="user-001"
    )
    
    # 2. 创建模板优化器
    optimizer = TemplateBasedOptimization()
    
    # 模拟几轮对话
    conversations = [
        ("你好", "你好！有什么可以帮助你的？"),
        ("我想学习Python编程", "很好的选择！Python是一门很受欢迎的编程语言。你想从哪里开始学习？"),
        ("如何定义函数？", None),  # 这一轮我们要生成回复
    ]
    
    # 添加前几轮对话
    for user_msg, assistant_msg in conversations[:-1]:
        await engine.update(user_msg, assistant_msg)
        print(f"用户: {user_msg}")
        print(f"助手: {assistant_msg}")
        print()
    
    # 处理最后一轮
    user_input = conversations[-1][0]
    print(f"用户: {user_input}")
    print()
    
    # 3. 优化上下文
    print("🔄 正在优化上下文...")
    context = await engine.optimize(user_input)
    
    # 4. 使用模板优化器进一步处理
    processed = ProcessedContext(items=context.items)
    optimized = await optimizer.optimize(processed)
    
    # 5. 查看优化后的提示词
    print("\n📋 优化后的提示词:")
    print("-" * 80)
    if optimized.items:
        print(optimized.items[0].content)
    print("-" * 80)
    print()
    
    # 显示优化信息
    print("📊 优化统计:")
    print(f"  - 原始上下文项: {len(context.items)}")
    print(f"  - 优化后项数: {len(optimized.items)}")
    print(f"  - 优化方法: {optimized.metadata.get('optimization_method')}")
    print(f"  - 意图置信度: {optimized.metadata.get('intent_confidence', 0):.2f}")
    print()


async def customer_service_example():
    """
    客服场景示例，使用自定义模板
    """
    print("\n" + "=" * 80)
    print("示例 2: 客服场景（自定义模板）")
    print("=" * 80 + "\n")
    
    # 创建客服专用模板
    cs_template = PromptTemplate(
        template_id="customer_service",
        name="客服模板",
        template_text="""你是一个专业、友好的客服助手。

## 客户意图
{intent}

## 问题分类
{topic}

## 对话历史
{context}

## 处理原则
1. 保持专业和礼貌
2. 快速理解客户需求
3. 提供清晰的解决方案
4. 必要时转人工客服

请根据以上信息专业地回复客户。""",
        slots=[
            TemplateSlot(name="intent", description="客户意图", required=True),
            TemplateSlot(name="topic", description="问题分类", required=True),
            TemplateSlot(name="context", description="对话历史", default_value="首次咨询"),
        ]
    )
    
    # 初始化引擎和优化器
    engine = ContextEngine(
        app_name="customer-service",
        user_id="customer-001"
    )
    
    optimizer = TemplateBasedOptimization(template=cs_template)
    
    # 模拟客服对话
    conversations = [
        ("你好，我的订单还没收到", "您好！很抱歉给您带来不便。请问您的订单号是多少？"),
        ("订单号是 12345", "感谢您提供订单号。让我帮您查询一下。"),
        ("什么时候能到？", None),
    ]
    
    # 添加对话历史
    for user_msg, assistant_msg in conversations[:-1]:
        await engine.update(user_msg, assistant_msg)
        print(f"客户: {user_msg}")
        print(f"客服: {assistant_msg}")
        print()
    
    user_input = conversations[-1][0]
    print(f"客户: {user_input}")
    print()
    
    # 优化上下文
    print("🔄 正在优化客服回复...")
    context = await engine.optimize(user_input)
    processed = ProcessedContext(items=context.items)
    optimized = await optimizer.optimize(processed)
    
    # 查看优化结果
    print("\n📋 客服提示词:")
    print("-" * 80)
    if optimized.items:
        print(optimized.items[0].content)
    print("-" * 80)
    print()


async def multi_turn_example():
    """
    多轮对话示例，展示意图如何随对话演变
    """
    print("\n" + "=" * 80)
    print("示例 3: 多轮对话意图演变")
    print("=" * 80 + "\n")
    
    engine = ContextEngine(
        app_name="multi-turn-demo",
        user_id="user-002"
    )
    
    optimizer = TemplateBasedOptimization()
    
    # 一系列对话，展示意图变化
    turns = [
        "你好",
        "今天天气怎么样？",
        "那我可以去公园吗？",
        "需要带伞吗？",
    ]
    
    for i, user_input in enumerate(turns, 1):
        print(f"\n--- 第 {i} 轮对话 ---")
        print(f"用户: {user_input}")
        
        # 优化上下文
        context = await engine.optimize(user_input)
        processed = ProcessedContext(items=context.items)
        optimized = await optimizer.optimize(processed)
        
        # 显示提取的意图和主题
        if optimized.items and optimized.items[0].metadata:
            metadata = optimized.items[0].metadata
            print(f"  意图: {metadata.get('intent_description', 'N/A')}")
            print(f"  主题: {metadata.get('topic', 'N/A')}")
        
        # 模拟助手回复（简化）
        mock_response = f"[回复第{i}轮]"
        await engine.update(user_input, mock_response)


async def template_comparison_example():
    """
    模板对比示例，展示不同模板的效果
    """
    print("\n" + "=" * 80)
    print("示例 4: 不同模板对比")
    print("=" * 80 + "\n")
    
    # 准备对话历史
    engine = ContextEngine(
        app_name="template-comparison",
        user_id="user-003"
    )
    
    await engine.update(
        "我想学习机器学习",
        "很好！机器学习是一个很有前景的领域。"
    )
    await engine.update(
        "需要什么基础？",
        "建议先掌握Python编程和基础数学知识。"
    )
    
    user_input = "推荐一些学习资源"
    context = await engine.optimize(user_input)
    processed = ProcessedContext(items=context.items)
    
    # 模板1: 默认模板
    print("📋 模板 1: 默认对话模板")
    print("-" * 80)
    optimizer1 = TemplateBasedOptimization()
    result1 = await optimizer1.optimize(processed)
    if result1.items:
        print(result1.items[0].content[:300] + "...")
    print()
    
    # 模板2: 简化模板
    print("\n📋 模板 2: 简化模板")
    print("-" * 80)
    simple_template = PromptTemplate(
        template_id="simple",
        name="简化模板",
        template_text="用户想: {intent}\n请简洁回复。"
    )
    optimizer2 = TemplateBasedOptimization(template=simple_template)
    result2 = await optimizer2.optimize(processed)
    if result2.items:
        print(result2.items[0].content)
    print()
    
    # 模板3: 详细教学模板
    print("\n📋 模板 3: 教学模板")
    print("-" * 80)
    teaching_template = PromptTemplate(
        template_id="teaching",
        name="教学模板",
        template_text="""你是一个耐心的老师。

学生意图: {intent}
学习主题: {topic}
学习进度: {context}

教学要求:
1. 用简单的语言解释
2. 提供具体例子
3. 鼓励学生提问
4. 检查理解程度

请提供详细的教学回复。"""
    )
    optimizer3 = TemplateBasedOptimization(template=teaching_template)
    result3 = await optimizer3.optimize(processed)
    if result3.items:
        print(result3.items[0].content[:400] + "...")
    print()


async def main():
    """运行所有示例"""
    print("\n" + "=" * 80)
    print("模板优化集成示例")
    print("=" * 80)
    
    try:
        await simple_chat_example()
        await customer_service_example()
        await multi_turn_example()
        await template_comparison_example()
        
        print("\n" + "=" * 80)
        print("✅ 所有示例运行完成！")
        print("=" * 80 + "\n")
        
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
