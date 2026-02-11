#!/usr/bin/env python3
"""
演示脚本：展示NLU格式数据的DST信息提取

不需要LLM，只演示数据结构和信息提取。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from benchmark.datasets.risawoz.nlu_adapter import NLUFormatAdapter


def main():
    print("="*70)
    print("RiSAWOZ NLU格式 DST信息提取演示")
    print("="*70)
    
    # 加载适配器
    print("\n加载数据...")
    adapter = NLUFormatAdapter("resources/data/risawoz_test.json")
    
    # 显示统计信息
    print("\n" + "="*70)
    print("数据集统计")
    print("="*70)
    stats = adapter.get_statistics()
    print(f"总轮次数: {stats['total_turns']}")
    print(f"包含槽位的轮次: {stats['turns_with_slots']}")
    print(f"总槽位-值对: {stats['total_slot_value_pairs']}")
    print(f"平均每轮槽位数: {stats['avg_slots_per_turn']:.2f}")
    print(f"唯一意图数: {stats['unique_intents']}")
    print(f"唯一领域数: {stats['unique_domains']}")
    
    print(f"\n意图分布（Top 5）:")
    sorted_intents = sorted(stats['intent_distribution'].items(), 
                           key=lambda x: x[1], reverse=True)
    for intent, count in sorted_intents[:5]:
        print(f"  {intent}: {count}")
    
    print(f"\n领域分布（Top 5）:")
    sorted_domains = sorted(stats['domain_distribution'].items(), 
                           key=lambda x: x[1], reverse=True)
    for domain, count in sorted_domains[:5]:
        print(f"  {domain}: {count}")
    
    # 展示几个有槽位值的轮次
    print("\n" + "="*70)
    print("轮次示例（包含槽位值）")
    print("="*70)
    
    # 找到有槽位值的轮次
    all_turns = adapter.get_all_turns()
    turns_with_slots = [turn for turn in all_turns if turn.belief_state]
    
    for i, turn in enumerate(turns_with_slots[:5]):
        print(f"\n【轮次 {turn.turn_id}】")
        print(f"话语: {turn.utterance}")
        
        print(f"意图信息:")
        for intent in turn.intents:
            print(f"  - 意图:{intent['intent']}, 领域:{intent['domain']}, "
                  f"槽位:{intent['slot']}, 值:{intent['value']}")
        
        print(f"Belief State (状态):")
        for slot, value in turn.belief_state.items():
            print(f"  {slot} = {value}")
    
    # 按领域展示
    print("\n" + "="*70)
    print("按领域过滤示例")
    print("="*70)
    
    # 获取旅游景点领域的轮次
    scenic_turns = adapter.get_turns_by_domain("旅游景点")
    scenic_with_slots = [t for t in scenic_turns if t.belief_state]
    
    print(f"\n'旅游景点' 领域:")
    print(f"  总轮次: {len(scenic_turns)}")
    print(f"  包含槽位: {len(scenic_with_slots)}")
    
    if scenic_with_slots:
        sample = scenic_with_slots[0]
        print(f"\n  示例轮次:")
        print(f"    话语: {sample.utterance}")
        print(f"    Belief State: {sample.belief_state}")
    
    # 获取酒店领域的轮次
    hotel_turns = adapter.get_turns_by_domain("酒店")
    hotel_with_slots = [t for t in hotel_turns if t.belief_state]
    
    print(f"\n'酒店' 领域:")
    print(f"  总轮次: {len(hotel_turns)}")
    print(f"  包含槽位: {len(hotel_with_slots)}")
    
    if hotel_with_slots:
        sample = hotel_with_slots[0]
        print(f"\n  示例轮次:")
        print(f"    话语: {sample.utterance}")
        print(f"    Belief State: {sample.belief_state}")
    
    # 创建单轮对话
    print("\n" + "="*70)
    print("单轮对话创建示例")
    print("="*70)
    
    dialogues = adapter.create_single_turn_dialogues()
    print(f"\n创建了 {len(dialogues)} 个单轮对话")
    
    # 展示几个对话
    for i in range(3):
        if i < len(dialogues) and dialogues[i].final_state:
            dialogue = dialogues[i]
            print(f"\n对话 {i}:")
            print(f"  ID: {dialogue.dialogue_id}")
            print(f"  领域: {dialogue.domain}")
            print(f"  轮次数: {len(dialogue.turns)}")
            print(f"  话语: {dialogue.turns[0].utterance}")
            print(f"  最终状态: {dialogue.final_state}")
    
    print("\n" + "="*70)
    print("演示完成！")
    print("="*70)
    print("\n说明:")
    print("1. NLU格式数据包含丰富的DST信息（意图、槽位、值）")
    print("2. 每个轮次都可以提取完整的belief state")
    print("3. 支持按领域过滤和统计分析")
    print("4. 可以用于DST模型的评测")
    print("\n运行完整评测（需要LLM）:")
    print("  python benchmark/run_dst_risawoz_nlu.py --limit 10 --verbose")


if __name__ == "__main__":
    main()
