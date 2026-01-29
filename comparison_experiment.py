"""
对比实验脚本 - Baseline Template vs ContextMind

运行此脚本可快速对比两种方式的性能和效果。
"""

import asyncio
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline_template import TemplateEngine, Message
from prompts import CHAT_SYSTEM_PROMPT


async def test_baseline(test_conversation):
    """测试 Baseline Template 方式"""
    print("\n" + "=" * 80)
    print("🔹 方式1: Baseline Template（槽位模板基线）")
    print("=" * 80)
    
    # 创建引擎
    engine = TemplateEngine(system_prompt=CHAT_SYSTEM_PROMPT)
    
    # 测量时间
    start_time = time.time()
    prompt = await engine.generate_prompt(test_conversation)
    elapsed_time = time.time() - start_time
    
    # 输出结果
    print(f"\n⏱️  耗时: {elapsed_time * 1000:.2f} ms")
    print(f"📏 提示词长度: {len(prompt)} 字符")
    print(f"🔍 包含槽位: {engine.template.get_slot_names()}")
    print(f"💾 使用记忆库: ❌ 否")
    
    print("\n📝 生成的提示词:")
    print("-" * 80)
    print(prompt)
    print("-" * 80)
    
    return {
        'method': 'Baseline Template',
        'time_ms': elapsed_time * 1000,
        'prompt_length': len(prompt),
        'uses_memory': False,
    }


async def test_contextmind_simulation(test_conversation):
    """模拟 ContextMind 方式（简化版）"""
    print("\n" + "=" * 80)
    print("🔹 方式2: ContextMind（上下文工程）")
    print("=" * 80)
    
    print("\n注意：这是一个简化的模拟，实际 ContextMind 包含更多功能")
    
    # 模拟检索记忆和优化的时间
    start_time = time.time()
    
    # 模拟记忆检索（耗时）
    await asyncio.sleep(0.05)  # 模拟50ms的检索时间
    
    # 构建更丰富的提示词（模拟）
    prompt_parts = [CHAT_SYSTEM_PROMPT]
    
    # 添加"记忆"内容（模拟）
    prompt_parts.append("\n## 长期记忆\n- 用户可能对技术话题感兴趣\n- 之前讨论过编程相关内容")
    
    # 添加对话历史
    prompt_parts.append("\n## 对话历史")
    for msg in test_conversation[-5:]:  # 最近5条
        prompt_parts.append(f"{msg.role}: {msg.content}")
    
    # 添加当前输入
    if test_conversation:
        prompt_parts.append(f"\n## 当前用户输入\n{test_conversation[-1].content}")
    
    prompt = "\n".join(prompt_parts)
    elapsed_time = time.time() - start_time
    
    # 输出结果
    print(f"\n⏱️  耗时: {elapsed_time * 1000:.2f} ms")
    print(f"📏 提示词长度: {len(prompt)} 字符")
    print(f"🔍 优化策略: 记忆检索 + 上下文优化")
    print(f"💾 使用记忆库: ✅ 是")
    
    print("\n📝 生成的提示词:")
    print("-" * 80)
    print(prompt)
    print("-" * 80)
    
    return {
        'method': 'ContextMind',
        'time_ms': elapsed_time * 1000,
        'prompt_length': len(prompt),
        'uses_memory': True,
    }


async def run_comparison():
    """运行完整的对比测试"""
    print("\n" + "=" * 100)
    print(" " * 35 + "对比实验")
    print("=" * 100)
    
    # 准备测试数据
    test_conversations = [
        {
            'name': '简单对话',
            'messages': [
                Message(role="user", content="你好"),
                Message(role="assistant", content="你好！有什么可以帮助你的？"),
                Message(role="user", content="今天天气怎么样？"),
            ]
        },
        {
            'name': '多轮技术讨论',
            'messages': [
                Message(role="user", content="我想学习Python"),
                Message(role="assistant", content="很好！Python是很棒的语言。"),
                Message(role="user", content="应该从哪里开始？"),
                Message(role="assistant", content="建议从基础语法开始。"),
                Message(role="user", content="有推荐的学习资源吗？"),
            ]
        },
    ]
    
    # 运行测试
    for i, test in enumerate(test_conversations, 1):
        print(f"\n{'=' * 100}")
        print(f"测试用例 {i}: {test['name']}")
        print(f"{'=' * 100}")
        
        print(f"\n📝 对话内容 ({len(test['messages'])} 轮):")
        for j, msg in enumerate(test['messages'], 1):
            print(f"   [{j}] {msg.role}: {msg.content}")
        
        # 测试 Baseline
        baseline_result = await test_baseline(test['messages'])
        
        # 测试 ContextMind（模拟）
        contextmind_result = await test_contextmind_simulation(test['messages'])
        
        # 对比总结
        print(f"\n{'=' * 100}")
        print(f"对比总结 - {test['name']}")
        print(f"{'=' * 100}")
        
        print(f"\n速度对比:")
        print(f"  Baseline:    {baseline_result['time_ms']:>8.2f} ms")
        print(f"  ContextMind: {contextmind_result['time_ms']:>8.2f} ms")
        print(f"  速度差异:    {contextmind_result['time_ms'] / baseline_result['time_ms']:.1f}x")
        
        print(f"\n提示词长度:")
        print(f"  Baseline:    {baseline_result['prompt_length']:>8} 字符")
        print(f"  ContextMind: {contextmind_result['prompt_length']:>8} 字符")
        
        print(f"\n功能对比:")
        print(f"  Baseline:    {'❌' if not baseline_result['uses_memory'] else '✅'} 记忆库")
        print(f"  ContextMind: {'✅' if contextmind_result['uses_memory'] else '❌'} 记忆库")
    
    # 总结
    print(f"\n{'=' * 100}")
    print("总体总结")
    print(f"{'=' * 100}")
    
    print("\n🔹 Baseline Template 的优势:")
    print("   ✅ 速度快（< 10ms）")
    print("   ✅ 实现简单")
    print("   ✅ 无外部依赖")
    print("   ✅ 适合简单场景")
    
    print("\n🔹 ContextMind 的优势:")
    print("   ✅ 使用记忆库")
    print("   ✅ 更好的上下文理解")
    print("   ✅ 支持长期记忆")
    print("   ✅ 适合复杂场景")
    
    print("\n💡 选择建议:")
    print("   - 简单问答、快速原型 → 使用 Baseline Template")
    print("   - 复杂对话、需要记忆 → 使用 ContextMind")
    print("   - 对比实验基准 → 使用 Baseline Template")
    
    print(f"\n{'=' * 100}")
    print("实验完成！")
    print(f"{'=' * 100}\n")
    
    print("📚 更多信息:")
    print("   - 查看 baseline_template/README.md 了解基线模块")
    print("   - 查看 docs/COMPARISON_GUIDE.md 了解详细对比指南")
    print("   - 查看 prompts.py 了解统一的系统提示词")
    print()


if __name__ == "__main__":
    asyncio.run(run_comparison())
