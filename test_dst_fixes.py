#!/usr/bin/env python3
"""
测试 DST 模式修复
验证 SimpleLLMClient 和 DialogueStateTracker 的集成
"""

import asyncio
import sys

def test_llm_client_methods():
    """测试 SimpleLLMClient 是否有必要的方法"""
    print("=" * 60)
    print("测试 1: SimpleLLMClient 方法检查")
    print("=" * 60)
    
    try:
        from utils.llm_client import SimpleLLMClient
        
        # 检查必需的方法
        required_methods = ['chat', 'chat_async', 'generate', 'generate_async']
        
        for method in required_methods:
            if hasattr(SimpleLLMClient, method):
                print(f"✅ SimpleLLMClient.{method} 存在")
            else:
                print(f"❌ SimpleLLMClient.{method} 缺失")
                return False
        
        print("\n✅ 所有必需方法都存在！")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def test_dst_tracker_integration():
    """测试 DialogueStateTracker 与 SimpleLLMClient 的集成"""
    print("\n" + "=" * 60)
    print("测试 2: DialogueStateTracker 集成检查")
    print("=" * 60)
    
    try:
        from baseline import DialogueStateTracker, PromptManager
        
        # 创建 PromptManager
        pm = PromptManager(domain="test")
        pm.add_slot("test_slot", "测试槽位")
        
        # 创建 DialogueStateTracker（不传 LLM 客户端也应该能工作）
        tracker = DialogueStateTracker(
            llm_client=None,
            prompt_manager=pm
        )
        
        print("✅ DialogueStateTracker 创建成功（无 LLM）")
        
        # 测试重置
        tracker.reset_dialogue()
        print("✅ DialogueStateTracker.reset_dialogue() 成功")
        
        # 测试获取状态
        state = tracker.get_current_state()
        print(f"✅ DialogueStateTracker.get_current_state() 成功: {state}")
        
        print("\n✅ DialogueStateTracker 集成测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_dst_process_turn():
    """测试 DialogueStateTracker 的 process_turn 方法"""
    print("\n" + "=" * 60)
    print("测试 3: DialogueStateTracker.process_turn 测试")
    print("=" * 60)
    
    try:
        from baseline import DialogueStateTracker, PromptManager
        
        # 创建 PromptManager
        pm = PromptManager(domain="test")
        pm.add_slot("intent", "用户意图")
        
        # 创建 DialogueStateTracker（不传 LLM，使用规则提取）
        tracker = DialogueStateTracker(
            llm_client=None,
            prompt_manager=pm
        )
        tracker.reset_dialogue()
        
        # 测试处理对话轮次（无 LLM）
        state = await tracker.process_turn(
            system_utterance="",
            user_utterance="我想预订一个房间"
        )
        
        print(f"✅ process_turn 成功，状态: {state}")
        
        print("\n✅ process_turn 测试通过！")
        return True
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("开始 DST 修复验证测试")
    print("=" * 60 + "\n")
    
    results = []
    
    # 测试 1: SimpleLLMClient 方法
    results.append(test_llm_client_methods())
    
    # 测试 2: DialogueStateTracker 集成
    results.append(test_dst_tracker_integration())
    
    # 测试 3: process_turn（异步）
    results.append(asyncio.run(test_dst_process_turn()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    total = len(results)
    passed = sum(results)
    
    print(f"总计: {total} 个测试")
    print(f"通过: {passed} 个")
    print(f"失败: {total - passed} 个")
    
    if all(results):
        print("\n✅ 所有测试通过！DST 修复成功！")
        return 0
    else:
        print("\n❌ 部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
