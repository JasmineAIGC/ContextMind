"""
基础 DST 演示 (Basic Dialogue State Tracking Demo)

基于 ACL 2023 论文的 Zero-shot DST 实现演示
展示如何使用 DialogueStateTracker 进行对话状态追踪
"""

import asyncio
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline import DialogueStateTracker, PromptManager
import json


async def demo_basic_dst():
    """基础对话状态追踪演示"""
    print("=" * 80)
    print("对话状态追踪演示 - 基础用法")
    print("=" * 80)
    print()
    
    # 1. 初始化提示词管理器（可以添加自定义槽位）
    print("🔧 初始化提示词管理器...")
    prompt_manager = PromptManager(domain="general")
    
    # 添加一些自定义槽位
    prompt_manager.add_slot(
        "product_name",
        "用户感兴趣的产品名称",
        None
    )
    prompt_manager.add_slot(
        "budget",
        "用户的预算范围",
        ["低", "中", "高"]
    )
    
    print(f"✅ 已定义 {len(prompt_manager.ontology_slots)} 个槽位")
    print()
    
    # 2. 初始化对话状态追踪器（不使用 LLM 客户端，使用规则提取）
    print("🔧 初始化对话状态追踪器...")
    tracker = DialogueStateTracker(
        llm_client=None,  # 不使用 LLM，演示规则提取
        prompt_manager=prompt_manager
    )
    print("✅ 追踪器初始化完成")
    print()
    
    # 3. 开始对话
    print("💬 模拟对话场景：")
    print("-" * 80)
    
    # 重置对话
    tracker.reset_dialogue()
    
    # 对话轮次 1
    print("\n【轮次 1】")
    system_utt_1 = "您好，有什么可以帮助您的吗？"
    user_utt_1 = "我想要订一个酒店"
    print(f"系统: {system_utt_1}")
    print(f"用户: {user_utt_1}")
    
    state_1 = await tracker.process_turn(system_utt_1, user_utt_1)
    print(f"状态更新: {json.dumps(state_1, ensure_ascii=False, indent=2)}")
    
    # 对话轮次 2
    print("\n【轮次 2】")
    system_utt_2 = "好的，请问您想去哪个城市呢？"
    user_utt_2 = "我想去北京"
    print(f"系统: {system_utt_2}")
    print(f"用户: {user_utt_2}")
    
    state_2 = await tracker.process_turn(system_utt_2, user_utt_2)
    print(f"状态更新: {json.dumps(state_2, ensure_ascii=False, indent=2)}")
    
    # 对话轮次 3
    print("\n【轮次 3】")
    system_utt_3 = "北京有很多酒店，您有什么偏好吗？"
    user_utt_3 = "我想要一个不贵的，在市中心的"
    print(f"系统: {system_utt_3}")
    print(f"用户: {user_utt_3}")
    
    state_3 = await tracker.process_turn(system_utt_3, user_utt_3)
    print(f"状态更新: {json.dumps(state_3, ensure_ascii=False, indent=2)}")
    
    print()
    print("-" * 80)
    print("\n📊 最终对话状态：")
    final_state = tracker.get_current_state()
    print(json.dumps(final_state, ensure_ascii=False, indent=2))
    
    print()
    print("✅ 演示完成！")
    print()


async def demo_dst_with_prompt():
    """展示 Prompt 设计"""
    print("=" * 80)
    print("对话状态追踪 - Prompt 设计展示")
    print("=" * 80)
    print()
    
    # 创建提示词管理器
    prompt_manager = PromptManager(domain="restaurant")
    
    # 添加餐厅相关槽位
    prompt_manager.add_slot("restaurant_name", "餐厅名称")
    prompt_manager.add_slot("food_type", "菜系类型", ["中餐", "西餐", "日料", "韩餐", "其他"])
    prompt_manager.add_slot("party_size", "用餐人数")
    prompt_manager.add_slot("booking_time", "预订时间")
    
    # 显示系统指令
    print("📝 生成的系统指令 Prompt：")
    print("=" * 80)
    instruction = prompt_manager.get_system_instruction()
    print(instruction)
    print("=" * 80)
    print()
    
    print("💡 说明：")
    print("1. 这个 Prompt 遵循 ACL 2023 论文 Figure 2 的设计")
    print("2. 包含完整的槽位定义（ontology_slots）")
    print("3. 包含分类约束（categorical_constraints）")
    print("4. 指导 ChatGPT 如何提取和返回槽位更新")
    print()


async def demo_response_parsing():
    """展示响应解析功能"""
    print("=" * 80)
    print("对话状态追踪 - 响应解析演示")
    print("=" * 80)
    print()
    
    from baseline import ResponseParser
    
    # 创建解析器
    prompt_manager = PromptManager()
    parser = ResponseParser(prompt_manager)
    
    # 测试不同格式的响应
    test_responses = [
        # 标准 JSON
        '''{"intent": "预订", "location": "北京"}''',
        
        # 带文本的 JSON
        '''根据对话，用户更新了以下槽位：
        {"intent": "询问", "topic": "价格"}
        以上是提取的槽位信息。''',
        
        # 不完整的 JSON
        '''{
            "destination": "上海",
            "time": "明天"
        }''',
        
        # 列表格式
        '''[{"intent": "预订"}, {"location": "广州"}]''',
    ]
    
    print("🔍 测试不同格式的响应解析：")
    print()
    
    for i, response in enumerate(test_responses, 1):
        print(f"【测试 {i}】")
        print(f"原始响应:")
        print(f"  {response[:60]}{'...' if len(response) > 60 else ''}")
        
        extracted = parser.extract_json(response)
        print(f"提取结果:")
        print(f"  {json.dumps(extracted, ensure_ascii=False)}")
        
        filtered = parser.filter_hallucinations(extracted)
        print(f"过滤后 (仅保留有效槽位):")
        print(f"  {json.dumps(filtered, ensure_ascii=False)}")
        print()
    
    print("✅ 响应解析测试完成！")
    print()


async def demo_comparison():
    """对比展示：槽位模板 vs DST"""
    print("=" * 80)
    print("对比演示：基础槽位模板 vs 对话状态追踪")
    print("=" * 80)
    print()
    
    print("场景：用户预订酒店的多轮对话")
    print()
    
    # 对话示例
    dialogue = [
        ("您好，有什么可以帮您？", "我想订酒店"),
        ("好的，去哪个城市？", "北京"),
        ("您对价格有要求吗？", "不要太贵就行"),
        ("明白了，几号入住？", "下周五"),
    ]
    
    print("=" * 80)
    print("方式 1: 对话状态追踪（DST）")
    print("=" * 80)
    print()
    
    # DST 方式
    tracker = DialogueStateTracker(llm_client=None)
    tracker.reset_dialogue()
    
    print("特点：")
    print("  ✅ 累积式状态更新")
    print("  ✅ 完整的对话历史管理")
    print("  ✅ 结构化状态表示")
    print("  ✅ 支持共指消解（通过上下文）")
    print()
    
    for i, (sys_utt, user_utt) in enumerate(dialogue, 1):
        print(f"轮次 {i}:")
        print(f"  系统: {sys_utt}")
        print(f"  用户: {user_utt}")
        state = await tracker.process_turn(sys_utt, user_utt)
        print(f"  状态: {json.dumps(state, ensure_ascii=False)}")
        print()
    
    print("-" * 80)
    print(f"最终状态: {json.dumps(tracker.get_current_state(), ensure_ascii=False)}")
    print()
    
    print("=" * 80)
    print("方式 2: 基础槽位模板")
    print("=" * 80)
    print()
    
    print("特点：")
    print("  ✅ 简单直接")
    print("  ✅ 快速实现")
    print("  ❌ 无状态累积")
    print("  ❌ 槽位定义不够丰富")
    print()
    
    print("=" * 80)
    print("总结")
    print("=" * 80)
    print()
    print("选择建议：")
    print("  - 需要精确的状态追踪、多轮对话 → DST")
    print("  - 简单的意图识别、单轮对话 → 基础槽位模板")
    print()


async def main():
    """主函数"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║          对话状态追踪演示 (Dialogue State Tracking Demo)                  ║")
    print("║          基于 ACL 2023 论文的 Zero-shot 实现                              ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    # 选择演示模式
    print("请选择演示模式：")
    print("  1. 基础对话状态追踪演示")
    print("  2. Prompt 设计展示")
    print("  3. 响应解析演示")
    print("  4. 对比演示（槽位模板 vs DST）")
    print("  5. 运行所有演示")
    print()
    
    try:
        choice = input("请输入选项 (1-5, 默认 1): ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print("\n\n👋 再见！")
        return
    
    print()
    
    if choice == "1":
        await demo_basic_dst()
    elif choice == "2":
        await demo_dst_with_prompt()
    elif choice == "3":
        await demo_response_parsing()
    elif choice == "4":
        await demo_comparison()
    elif choice == "5":
        await demo_basic_dst()
        print("\n" * 2)
        await demo_dst_with_prompt()
        print("\n" * 2)
        await demo_response_parsing()
        print("\n" * 2)
        await demo_comparison()
    else:
        print("❌ 无效选项，运行基础演示")
        await demo_basic_dst()
    
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
