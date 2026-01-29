"""
Baseline Template Demo - 基线模板演示

展示如何使用基线模板模块进行简单的对话生成。
"""

import asyncio
import sys
import os

# 添加路径以便导入模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline_template import TemplateEngine, Message, SimpleTemplateEngine
from prompts import BASELINE_TEMPLATE_SYSTEM_PROMPT


async def demo_template_engine():
    """演示完整的模板引擎功能"""
    print("=" * 80)
    print("基线模板引擎演示")
    print("=" * 80)
    print()
    
    # 创建引擎
    engine = TemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)
    
    print("🔧 引擎统计信息:")
    stats = engine.get_statistics()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print()
    
    # 准备对话历史
    conversation_history = [
        Message(role="user", content="你好，我想了解一下天气"),
        Message(role="assistant", content="你好！我可以帮你查询天气信息。请问你想了解哪个城市的天气？"),
        Message(role="user", content="北京今天天气怎么样？"),
    ]
    
    print("📝 对话历史:")
    for i, msg in enumerate(conversation_history, 1):
        print(f"   [{i}] {msg.role}: {msg.content}")
    print()
    
    # 生成提示词
    prompt = await engine.generate_prompt(conversation_history)
    
    print("🎯 生成的提示词:")
    print("-" * 80)
    print(prompt)
    print("-" * 80)
    print()


def demo_simple_engine():
    """演示简化版引擎（同步接口）"""
    print("=" * 80)
    print("简化版模板引擎演示（同步接口）")
    print("=" * 80)
    print()
    
    # 创建简化版引擎
    engine = SimpleTemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)
    
    # 直接生成提示词
    user_message = "请帮我推荐一本好书"
    
    print(f"📝 用户输入: {user_message}")
    print()
    
    # 使用历史对话
    history = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！有什么可以帮助你的？"),
    ]
    
    prompt = engine.generate_prompt_sync(user_message, history)
    
    print("🎯 生成的提示词:")
    print("-" * 80)
    print(prompt)
    print("-" * 80)
    print()


async def demo_comparison():
    """演示对比实验的设置"""
    print("=" * 80)
    print("对比实验演示")
    print("=" * 80)
    print()
    
    # 准备相同的测试数据
    test_conversation = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
        Message(role="user", content="我想学习Python编程"),
        Message(role="assistant", content="很好的选择！Python是一门很适合初学者的语言。"),
        Message(role="user", content="从哪里开始学习比较好？"),
    ]
    
    print("📝 测试对话历史:")
    for i, msg in enumerate(test_conversation, 1):
        print(f"   [{i}] {msg.role}: {msg.content}")
    print()
    
    # 基线模板方式
    print("🔹 方式1: 基线模板（Baseline Template）")
    baseline_engine = TemplateEngine(system_prompt=BASELINE_TEMPLATE_SYSTEM_PROMPT)
    baseline_prompt = await baseline_engine.generate_prompt(test_conversation)
    print(f"   提示词长度: {len(baseline_prompt)} 字符")
    print(f"   包含槽位: {baseline_engine.template.get_slot_names()}")
    print()
    
    # 上下文工程方式（这里只是示意，实际需要ContextMind）
    print("🔹 方式2: 上下文工程（ContextMind）")
    print("   [需要完整的 ContextMind 框架]")
    print("   - 使用记忆库")
    print("   - 向量检索")
    print("   - 多策略优化")
    print()
    
    print("💡 对比要点:")
    print("   1. 使用相同的系统提示词（确保公平性）")
    print("   2. 使用相同的测试数据集")
    print("   3. 评估响应质量、速度、连贯性")
    print("   4. 记录差异和优劣势")
    print()


async def main():
    """主函数"""
    print("\n" + "=" * 80)
    print(" " * 25 + "基线模板模块演示")
    print("=" * 80 + "\n")
    
    # 演示1：完整引擎
    await demo_template_engine()
    
    # 演示2：简化版引擎
    demo_simple_engine()
    
    # 演示3：对比实验设置
    await demo_comparison()
    
    print("=" * 80)
    print("演示完成！")
    print("=" * 80)
    print()
    print("💡 提示:")
    print("   - 查看 baseline_template/README.md 了解更多信息")
    print("   - 查看 prompts.py 了解统一的系统提示词")
    print("   - 可以自定义模板和意图提取规则")
    print()


if __name__ == "__main__":
    asyncio.run(main())
