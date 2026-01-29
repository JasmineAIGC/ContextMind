"""
对比实验脚本：槽位模板 vs ContextMind 上下文工程

用于对比两种上下文优化方式的效果差异
"""

import asyncio
import sys
import os
import time
from typing import List, Tuple, Dict, Any

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from baseline import SlotTemplateEngine
from contextmind import ContextEngine
from prompts import SLOT_TEMPLATE_SYSTEM_PROMPT, CHAT_SYSTEM_PROMPT


class ComparisonExperiment:
    """对比实验类"""
    
    def __init__(self):
        """初始化对比实验"""
        # 初始化两个引擎
        self.slot_engine = SlotTemplateEngine(
            llm_client=None,
            use_llm_extraction=False
        )
        
        self.context_engine = ContextEngine(
            app_name="comparison-demo",
            user_id="test-user",
        )
        
        # 测试对话场景
        self.test_conversations = [
            {
                "name": "简单问候场景",
                "turns": [
                    ("你好", "您好！有什么可以帮助您的吗？"),
                    ("今天天气不错", None)
                ]
            },
            {
                "name": "自我介绍场景",
                "turns": [
                    ("你好", "您好！"),
                    ("我叫张三", "很高兴认识你，张三！"),
                    ("我喜欢编程", "编程是个很棒的爱好！"),
                    ("你还记得我叫什么吗？", None)
                ]
            },
            {
                "name": "客服咨询场景",
                "turns": [
                    ("我想了解产品信息", "好的，请问您对哪类产品感兴趣？"),
                    ("价格是多少", "让我为您查询一下价格信息..."),
                    ("有优惠吗", None)
                ]
            },
            {
                "name": "多轮复杂对话",
                "turns": [
                    ("你好", "您好！"),
                    ("我在北京工作", "北京是个很不错的城市！"),
                    ("我是软件工程师", "很棒的职业！"),
                    ("工资大概2万", "不错的收入水平。"),
                    ("我想买房", "买房是个重要决定。"),
                    ("根据我的情况，你觉得我适合买什么价位的房子？", None)
                ]
            }
        ]
    
    async def run_baseline(
        self,
        conversation: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """运行槽位模板方式
        
        Args:
            conversation: 对话历史 [(user, assistant), ...]
        
        Returns:
            结果字典，包含槽位值、耗时等信息
        """
        # 重置引擎
        self.slot_engine.clear_history()
        
        # 添加历史对话
        for user_msg, assistant_msg in conversation[:-1]:
            self.slot_engine.add_message("user", user_msg)
            if assistant_msg:
                self.slot_engine.add_message("assistant", assistant_msg)
        
        # 处理当前输入
        current_input = conversation[-1][0]
        
        start_time = time.time()
        result = await self.slot_engine.process(
            user_input=current_input,
            system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
        )
        elapsed_time = time.time() - start_time
        
        return {
            "method": "baseline",
            "elapsed_time": elapsed_time,
            "slot_values": result['slot_values'],
            "prompt_preview": result.get('filled_prompt', '')[:200]
        }
    
    async def run_contextmind(
        self,
        conversation: List[Tuple[str, str]]
    ) -> Dict[str, Any]:
        """运行 ContextMind 方式
        
        Args:
            conversation: 对话历史 [(user, assistant), ...]
        
        Returns:
            结果字典，包含上下文信息、耗时等信息
        """
        # 重置引擎
        await self.context_engine.clear_session()
        
        # 添加历史对话
        from contextmind.core.types import MessageRole
        for user_msg, assistant_msg in conversation[:-1]:
            await self.context_engine.session_manager.add_message(
                role=MessageRole.USER,
                content=user_msg
            )
            if assistant_msg:
                await self.context_engine.session_manager.add_message(
                    role=MessageRole.ASSISTANT,
                    content=assistant_msg
                )
        
        # 优化上下文
        current_input = conversation[-1][0]
        
        start_time = time.time()
        context_result = await self.context_engine.optimize(
            user_input=current_input,
            include_session=True,
            include_memory=True
        )
        elapsed_time = time.time() - start_time
        
        return {
            "method": "contextmind",
            "elapsed_time": elapsed_time,
            "context_items": len(context_result.items),
            "compressed": context_result.compressed,
            "metadata": context_result.metadata
        }
    
    async def run_comparison(self, scenario_index: int = None):
        """运行对比实验
        
        Args:
            scenario_index: 场景索引，None 表示运行所有场景
        """
        print("=" * 100)
        print("对比实验：槽位模板 vs ContextMind 上下文工程")
        print("=" * 100)
        print()
        
        # 选择场景
        scenarios = (
            [self.test_conversations[scenario_index]]
            if scenario_index is not None
            else self.test_conversations
        )
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\n{'=' * 100}")
            print(f"场景 {i}: {scenario['name']}")
            print("=" * 100)
            
            # 显示对话历史
            print("\n对话历史：")
            for j, (user_msg, assistant_msg) in enumerate(scenario['turns'][:-1], 1):
                print(f"  轮次 {j}:")
                print(f"    用户: {user_msg}")
                print(f"    助手: {assistant_msg}")
            
            current_input = scenario['turns'][-1][0]
            print(f"\n当前用户输入: {current_input}")
            print()
            
            # 运行槽位模板
            print("-" * 100)
            print("方式 1: 槽位模板 (Baseline)")
            print("-" * 100)
            
            slot_result = await self.run_baseline(scenario['turns'])
            
            print(f"\n⏱️  耗时: {slot_result['elapsed_time']:.4f}s")
            print(f"\n📊 槽位信息:")
            for slot_name, value in slot_result['slot_values'].items():
                print(f"  {slot_name}:")
                print(f"    {value}")
            
            # 运行 ContextMind
            print()
            print("-" * 100)
            print("方式 2: ContextMind (上下文工程)")
            print("-" * 100)
            
            cm_result = await self.run_contextmind(scenario['turns'])
            
            print(f"\n⏱️  耗时: {cm_result['elapsed_time']:.4f}s")
            print(f"\n📊 上下文优化结果:")
            print(f"  上下文项数量: {cm_result['context_items']}")
            print(f"  是否压缩: {cm_result['compressed']}")
            print(f"  元数据: {cm_result['metadata']}")
            
            # 对比分析
            print()
            print("-" * 100)
            print("📈 对比分析")
            print("-" * 100)
            
            print(f"\n性能对比:")
            print(f"  槽位模板耗时: {slot_result['elapsed_time']:.4f}s")
            print(f"  ContextMind耗时: {cm_result['elapsed_time']:.4f}s")
            
            if slot_result['elapsed_time'] > 0.0001:  # 避免除零和极小值
                speed_ratio = cm_result['elapsed_time'] / slot_result['elapsed_time']
                print(f"  速度比: ContextMind 是槽位模板的 {speed_ratio:.2f}x")
            else:
                print(f"  速度比: 两者都非常快，差异可忽略")
            
            print(f"\n功能对比:")
            print(f"  槽位模板:")
            print(f"    ✅ 简单直接")
            print(f"    ✅ 速度快")
            print(f"    ❌ 功能有限")
            print(f"    ❌ 无长期记忆")
            
            print(f"  ContextMind:")
            print(f"    ✅ 功能完整")
            print(f"    ✅ 支持长期记忆")
            print(f"    ✅ 智能优化")
            print(f"    ⚠️  复杂度较高")
            
            print()
    
    async def run_interactive_comparison(self):
        """交互式对比"""
        print("=" * 100)
        print("交互式对比实验")
        print("=" * 100)
        print()
        
        print("💡 使用说明：")
        print("  - 输入对话内容，系统会同时使用两种方式处理")
        print("  - 输入 'quit' 退出")
        print("  - 输入 'reset' 重置对话")
        print()
        
        turn_count = 0
        
        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n\n👋 再见！")
                break
            
            if not user_input:
                continue
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n👋 再见！")
                break
            
            if user_input.lower() == 'reset':
                try:
                    self.slot_engine.clear_history()
                    await self.context_engine.clear_session()
                    turn_count = 0
                    print("✅ 对话已重置")
                except Exception as e:
                    print(f"⚠️  重置失败: {e}")
                continue
            
            turn_count += 1
            print(f"\n[第 {turn_count} 轮]")
            
            # 模拟助手回复
            assistant_response = "[模拟回复] 已收到您的消息"
            
            # 添加到两个引擎
            self.slot_engine.add_message("user", user_input)
            self.slot_engine.add_message("assistant", assistant_response)
            
            from contextmind.core.types import MessageRole
            await self.context_engine.session_manager.add_message(
                MessageRole.USER, user_input
            )
            await self.context_engine.session_manager.add_message(
                MessageRole.ASSISTANT, assistant_response
            )
            
            print(f"\n助手: {assistant_response}")
            
            # 显示两种方式的处理结果
            print("\n" + "-" * 100)
            print("槽位模板处理结果:")
            slot_result = await self.slot_engine.process(
                user_input=user_input,
                system_prompt_template=SLOT_TEMPLATE_SYSTEM_PROMPT
            )
            print(f"  意图: {slot_result['slot_values']['user_intent']}")
            
            print("\nContextMind处理结果:")
            cm_result = await self.context_engine.optimize(user_input)
            print(f"  上下文项: {len(cm_result.items)}")
            print(f"  压缩: {cm_result.compressed}")
            print("-" * 100)


async def main():
    """主函数"""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════════════════╗")
    print("║                   对比实验：槽位模板 vs ContextMind                       ║")
    print("╚════════════════════════════════════════════════════════════════════════════╝")
    print()
    
    experiment = ComparisonExperiment()
    
    print("请选择实验模式：")
    print("  1. 运行所有预设场景")
    print("  2. 运行单个场景")
    print("  3. 交互式对比")
    print()
    
    try:
        choice = input("请输入选项 (1-3, 默认 1): ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        print("\n\n👋 再见！")
        return
    
    print()
    
    if choice == "1":
        await experiment.run_comparison()
    elif choice == "2":
        print("可用场景：")
        for i, scenario in enumerate(experiment.test_conversations, 1):
            print(f"  {i}. {scenario['name']}")
        
        try:
            scenario_idx = int(input("\n请选择场景编号: ").strip()) - 1
            await experiment.run_comparison(scenario_idx)
        except (ValueError, IndexError):
            print("❌ 无效的场景编号")
    elif choice == "3":
        await experiment.run_interactive_comparison()
    else:
        print("❌ 无效选项")
    
    print("\n✨ 实验结束！")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 程序已中断")
    except Exception as e:
        print(f"\n❌ 程序错误: {str(e)}")
        import traceback
        traceback.print_exc()
