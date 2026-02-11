#!/usr/bin/env python3
"""
Test script to verify intent extraction from user_acts
"""

import json
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

def test_intent_extraction():
    """Test that user_acts are correctly extracted"""
    
    # Load adapter
    adapter = RiSAWOZAdapter(
        data_root="resources/data",
        file_mapping={"test": "risawoz_test.json"}
    )
    
    # Load first dialogue
    dialogue = adapter.load_dialogue("0", split="test")
    
    print("=" * 70)
    print(f"对话 ID: {dialogue.dialogue_id}")
    print(f"领域: {dialogue.domain}")
    print(f"轮次数: {len(dialogue.turns)}")
    print("=" * 70)
    
    # Check each turn for user_intents
    all_intents = []
    for i, turn in enumerate(dialogue.turns):
        print(f"\n【轮次 {turn.turn_id}】")
        print(f"用户话语: {turn.user_utterance[:60]}...")
        print(f"用户意图 (user_intents): {turn.user_intents}")
        
        # Extract intent names
        for intent_info in turn.user_intents:
            if len(intent_info) >= 2:
                intent = intent_info[0]
                domain = intent_info[1]
                if intent:
                    all_intents.append(intent)
                    print(f"  - 意图: {intent}, 领域: {domain}")
    
    print("\n" + "=" * 70)
    print(f"所有意图: {all_intents}")
    
    # Test intent selection
    inform_intents = [i for i in all_intents if i == "Inform"]
    request_intents = [i for i in all_intents if i == "Request"]
    other_intents = [i for i in all_intents if i not in ["Inform", "Request", "General", "Greeting", "Bye"]]
    
    print(f"\nInform意图: {inform_intents}")
    print(f"Request意图: {request_intents}")
    print(f"其他意图: {other_intents}")
    
    # Select dialogue intent
    if inform_intents:
        dialogue_intent = inform_intents[-1]
    elif request_intents:
        dialogue_intent = request_intents[-1]
    elif other_intents:
        dialogue_intent = other_intents[-1]
    else:
        dialogue_intent = all_intents[-1] if all_intents else ""
    
    print(f"\n对话级别意图: {dialogue_intent}")
    print("=" * 70)
    
    # Verify it's not empty
    if dialogue_intent:
        print("\n✅ 成功提取意图！")
        return True
    else:
        print("\n❌ 未能提取意图")
        return False

if __name__ == "__main__":
    success = test_intent_extraction()
    exit(0 if success else 1)
