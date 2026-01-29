"""
槽位模板方式演示 (Slot Template Baseline Demo)

展示如何使用槽位模板方式进行上下文优化。
这是一个简单的 baseline 版本，用于与 ContextMind 框架进行对比。
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from slot_template import SlotTemplateEngine
from prompts import SLOT_TEMPLATE_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT


async def demo_basic_usage():
    """基础使用演示"""
    print("=" * 80)
    print("槽位模板方式 - 基础使用演示")
    print("=" * 80)
    print()
    
    # 1. 初始化引擎（使用规则提取，不需要 LLM）
    print("🔧 初始化槽位模板引擎...")
    engine = SlotTemplateEngine(
        llm_client=None,  # 不使用 LLM 进行意图提取
        use_llm_extraction=False  # 使用规则提取
    )
    print("✅ 引擎初始化完成")
    print()
    
    # 2. 模拟多轮对话
    print("💬 模拟多轮对话场景：")
    print("-" * 80)
    
    conversations = [
        ("你好", "您好！我是智能助手，有什么可以帮助您的吗？"),
        ("我叫张三", "很高兴认识你，张三！"),
        ("我喜欢打篮球", "不错的爱好！运动对身体很有好处。"),
        ("你还记得我叫什么吗？", None)  # 当前轮，需要生成回复
    ]
    
    # 添加历史对话
    for i, (user_msg, assistant_msg) in enumerate(conversations[:-1], 1):
        print(f"第 {i} 轮：")
        print(f"  用户: {user_msg}")
        print(f"  助手: {assistant_msg}")
        
        engine.add_message("user", user_msg)
        engine.add_message("assistant", assistant_msg)
    
    print()
    print("-" * 80)
    
    # 3. 处理当前输入
    current_input = conversations[-1][0]
    print(f"\n📝 当前用户输入: {current_input}")
    print()
    
    print("🔍 提取槽位信息...")
    result = await engine.process(
        user_input=current_input,
        system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
    )
    
    # 4. 显示槽位值
    print("\n📊 提取的槽位值：")
    print("-" * 80)
    for slot_name, value in result['slot_values'].items():
        print(f"  {slot_name}:")
        print(f"    {value}")
    print("-" * 80)
    
    # 5. 显示填充后的提示词
    print("\n📄 填充后的系统提示词：")
    print("-" * 80)
    print(result['filled_prompt'])
    print("-" * 80)
    
    # 6. 生成完整提示词
    print("\n📝 生成完整提示词（用于 LLM 调用）：")
    print("-" * 80)
    full_prompt = await engine.generate_prompt(
        user_input=current_input,
        system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
    )
    print(full_prompt)
    print("-" * 80)
    
    print("\n✅ 演示完成！")
    print()


async def demo_interactive():
    """交互式演示"""
    print("=" * 80)
    print("槽位模板方式 - 交互式演示")
    print("=" * 80)
    print()
    
    print("💡 使用说明：")
    print("  - 直接输入消息开始对话")
    print("  - 输入 'quit' 或 'exit' 退出")
    print("  - 输入 'reset' 重置对话")
    print("  - 输入 'slots' 查看当前槽位值")
    print()
    
    # 初始化引擎
    engine = SlotTemplateEngine(
        llm_client=None,
        use_llm_extraction=False
    )
    
    turn_count = 0
    
    while True:
        # 获取用户输入
        try:
            user_input = input("\n你: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！")
            break
        
        if not user_input:
            continue
        
        # 处理特殊命令
        if user_input.lower() in ['quit', 'exit', 'q']:
            print("\n👋 再见！")
            break
        
        if user_input.lower() == 'reset':
            engine.clear_history()
            turn_count = 0
            print("✅ 对话已重置")
            continue
        
        if user_input.lower() == 'slots':
            slots = engine.get_all_slots()
            print("\n📊 当前槽位值：")
            for slot_name, value in slots.items():
                print(f"  {slot_name}: {value}")
            continue
        
        # 处理对话
        turn_count += 1
        print(f"\n[第 {turn_count} 轮]")
        
        # 提取槽位信息
        result = await engine.process(
            user_input=user_input,
            system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
        )
        
        # 显示槽位值（简化版）
        print(f"  意图: {result['slot_values']['user_intent']}")
        
        # 生成模拟回复
        # 注意：实际应用中需要集成 LLM 客户端
        # 示例：response = await your_llm.chat(result['filled_prompt'])
        assistant_response = f"[模拟回复 - 需集成 LLM] 已理解您的意图"
        
        print(f"助手: {assistant_response}")
        print("  💡 提示: 此为模拟回复。实际使用时请集成 LLM 客户端。")
        
        # 添加到历史
        engine.add_message("user", user_input)
        engine.add_message("assistant", assistant_response)


async def demo_comparison():
    """对比演示：槽位模板 vs ContextMind"""
    print("=" * 80)
    print("对比演示：槽位模板方式 vs ContextMind 上下文工程")
    print("=" * 80)
    print()
    
    print("场景：用户在多轮对话中提到自己的名字和爱好，然后询问系统是否记得")
    print()
    
    # 准备对话历史
    conversations = [
        ("你好", "您好！"),
        ("我叫李明", "很高兴认识你，李明！"),
        ("我喜欢编程", "编程是个很棒的爱好！"),
        ("你还记得我叫什么吗？", None)
    ]
    
    print("=" * 80)
    print("方式 1: 槽位模板（Baseline）")
    print("=" * 80)
    
    # 槽位模板方式
    slot_engine = SlotTemplateEngine(llm_client=None, use_llm_extraction=False)
    
    for user_msg, assistant_msg in conversations[:-1]:
        slot_engine.add_message("user", user_msg)
        if assistant_msg:
            slot_engine.add_message("assistant", assistant_msg)
    
    current_input = conversations[-1][0]
    slot_result = await slot_engine.process(
        user_input=current_input,
        system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
    )
    
    print(f"\n提取的槽位信息：")
    print(f"  意图: {slot_result['slot_values']['user_intent']}")
    print(f"  上下文: {slot_result['slot_values']['conversation_context']}")
    print(f"  关键信息: {slot_result['slot_values']['key_info']}")
    
    print("\n特点：")
    print("  ✅ 简单直接，易于理解")
    print("  ✅ 无需外部依赖（向量数据库等）")
    print("  ❌ 信息提取能力有限（基于简单规则）")
    print("  ❌ 无长期记忆（仅限当前会话）")
    
    print()
    print("=" * 80)
    print("方式 2: ContextMind（上下文工程）")
    print("=" * 80)
    
    print("\nContextMind 的处理流程：")
    print("  1. 预处理：清理和规范化输入")
    print("  2. 检索：从记忆库召回相关知识（语义检索）")
    print("  3. 压缩：智能压缩上下文，减少 token 使用")
    print("  4. 重排序：优化上下文顺序，提升效果")
    print("  5. 响应处理：自动提取知识，更新长期记忆")
    
    print("\n特点：")
    print("  ✅ 功能完整，适合生产环境")
    print("  ✅ 长期记忆，跨会话记住信息")
    print("  ✅ 智能检索，基于语义相似度")
    print("  ✅ 上下文优化，压缩和重排序")
    print("  ❌ 复杂度较高，需要更多资源")
    print("  ❌ 需要向量数据库等外部依赖")
    
    print()
    print("=" * 80)
    print("总结")
    print("=" * 80)
    print()
    print("选择建议：")
    print("  - 简单对话、快速原型、baseline 实验 → 槽位模板")
    print("  - 生产环境、复杂应用、长期记忆需求 → ContextMind")
    print()


async def main():
    """主函数"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║          槽位模板上下文优化方案演示 (Slot Template Baseline)              ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # 选择演示模式
    print("请选择演示模式：")
    print("  1. 基础使用演示")
    print("  2. 交互式演示")
    print("  3. 对比演示（槽位模板 vs ContextMind）")
    print("  4. 运行所有演示")
    print()
    
    try:
        choice = input("请输入选项 (1-4, 默认 1): ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print("\n\n👋 再见！")
        return
    
    print()
    
    if choice == "1":
        await demo_basic_usage()
    elif choice == "2":
        await demo_interactive()
    elif choice == "3":
        await demo_comparison()
    elif choice == "4":
        await demo_basic_usage()
        print("\n" * 2)
        await demo_comparison()
        print("\n" * 2)
        print("交互式演示已跳过（需要手动运行）")
    else:
        print("❌ 无效选项，运行基础演示")
        await demo_basic_usage()
    
    print("\n✨ 演示结束！")
    print()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 程序错误: {str(e)}")
        import traceback
        traceback.print_exc()
