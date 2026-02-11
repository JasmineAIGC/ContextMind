#!/usr/bin/env python3
"""
Quick test script for risawoz_test.json evaluation
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

def main():
    print("="*70)
    print("Testing risawoz_test.json with RiSAWOZ Adapter")
    print("="*70)
    
    # Create adapter
    adapter = RiSAWOZAdapter(
        data_root="resources/data",
        file_mapping={"test": "risawoz_test.json"}
    )
    
    # Get all dialogues
    dialogue_ids = adapter.get_dialogues_by_domain(None, split="test")
    print(f"\n✅ Successfully loaded adapter")
    print(f"Total dialogues: {len(dialogue_ids)}")
    
    # Test loading first 5 dialogues
    print(f"\n{'='*70}")
    print("Testing first 5 dialogues:")
    print(f"{'='*70}")
    
    for i in range(min(5, len(dialogue_ids))):
        dialogue = adapter.load_dialogue(dialogue_ids[i], split="test")
        
        print(f"\n📖 Dialogue {i}:")
        print(f"  ID: {dialogue.dialogue_id}")
        print(f"  Original ID: {dialogue.metadata.get('original_id', 'N/A')}")
        print(f"  Domain: {dialogue.domain}")
        print(f"  All domains: {dialogue.metadata.get('all_domains', [])}")
        print(f"  Turns: {len(dialogue.turns)}")
        print(f"  Final state slots: {len(dialogue.final_state)}")
        
        # Show final state
        if dialogue.final_state:
            print(f"  Final slots:")
            for slot, value in list(dialogue.final_state.items())[:3]:
                print(f"    {slot}: {value}")
        
        # Check first turn with slots
        for turn in dialogue.turns:
            if turn.expected_slots:
                print(f"  First turn with slots (turn {turn.turn_id}):")
                print(f"    User: {turn.user_utterance[:60]}...")
                print(f"    Slots: {turn.expected_slots}")
                break
    
    print(f"\n{'='*70}")
    print("✅ All tests passed!")
    print("="*70)

if __name__ == "__main__":
    main()
