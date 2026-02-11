"""
NLU Format Adapter for RiSAWOZ DST Evaluation

Adapts NLU format data (with tokens, labels, intents, parsed_intents) 
to work with DST evaluation pipeline.

Format: [[tokens], [labels], [intents], [parsed_intents], [extra]]
Where parsed_intents contains: [intent_type, domain, slot, value]
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

from benchmark.datasets.risawoz.label_parser import RiSAWOZLabelParser


@dataclass
class NLUTurn:
    """Single turn extracted from NLU format"""
    turn_id: int
    utterance: str
    tokens: List[str]
    ner_labels: List[str]
    intents: List[Dict[str, str]]  # List of {intent, domain, slot, value}
    belief_state: Dict[str, str]  # Accumulated slot-value pairs
    

@dataclass
class NLUDialogue:
    """Dialogue constructed from NLU format turns"""
    dialogue_id: str
    domain: str
    turns: List[NLUTurn]
    final_state: Dict[str, str]


class NLUFormatAdapter:
    """
    Adapter for NLU format RiSAWOZ data
    
    Converts NLU format (task1-data) with intent annotations
    to be compatible with DST evaluation.
    """
    
    def __init__(self, data_path: str):
        """
        Initialize adapter
        
        Args:
            data_path: Path to NLU format JSON file
        """
        self.data_path = Path(data_path)
        self.data = None
        self._load_data()
    
    def _load_data(self):
        """Load NLU format data from file"""
        with open(self.data_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
    
    def _extract_turn_info(self, record: List, turn_id: int) -> NLUTurn:
        """
        Extract turn information from NLU format record
        
        Args:
            record: [tokens, labels, intent_strings, parsed_intents, extra]
            turn_id: Turn index
            
        Returns:
            NLUTurn object with extracted information
        """
        tokens = record[0]
        ner_labels = record[1]
        intent_strings = record[2]
        parsed_intents = record[3]
        
        # Reconstruct utterance from tokens
        utterance = ''.join(tokens)
        
        # Extract intents with full information
        intents = []
        belief_state = {}
        
        for intent_info in parsed_intents:
            intent_type = intent_info[0] if len(intent_info) > 0 else ""
            domain = intent_info[1] if len(intent_info) > 1 else ""
            slot = intent_info[2] if len(intent_info) > 2 else ""
            value = intent_info[3] if len(intent_info) > 3 else ""
            
            intents.append({
                'intent': intent_type,
                'domain': domain,
                'slot': slot,
                'value': value
            })
            
            # Build belief state from slot-value pairs
            if slot and value:
                # Use domain-slot format for key
                slot_key = f"{domain}-{slot}" if domain else slot
                belief_state[slot_key] = value
        
        return NLUTurn(
            turn_id=turn_id,
            utterance=utterance,
            tokens=tokens,
            ner_labels=ner_labels,
            intents=intents,
            belief_state=belief_state
        )
    
    def get_turn(self, index: int) -> NLUTurn:
        """
        Get a single turn by index
        
        Args:
            index: Record index
            
        Returns:
            NLUTurn object
        """
        if index < 0 or index >= len(self.data):
            raise IndexError(f"Index {index} out of range (0-{len(self.data)-1})")
        
        return self._extract_turn_info(self.data[index], index)
    
    def get_all_turns(self) -> List[NLUTurn]:
        """
        Get all turns from the dataset
        
        Returns:
            List of NLUTurn objects
        """
        return [self._extract_turn_info(record, i) 
                for i, record in enumerate(self.data)]
    
    def get_turns_by_domain(self, domain: str) -> List[NLUTurn]:
        """
        Get turns filtered by domain
        
        Args:
            domain: Domain name to filter by
            
        Returns:
            List of NLUTurn objects for the specified domain
        """
        all_turns = self.get_all_turns()
        return [turn for turn in all_turns 
                if any(intent['domain'] == domain for intent in turn.intents)]
    
    def get_domains(self) -> List[str]:
        """
        Get all unique domains in the dataset
        
        Returns:
            List of domain names
        """
        domains = set()
        for record in self.data:
            parsed_intents = record[3]
            for intent_info in parsed_intents:
                if len(intent_info) > 1:
                    domains.add(intent_info[1])
        return sorted(list(domains))
    
    def get_intents(self) -> List[str]:
        """
        Get all unique intent types in the dataset
        
        Returns:
            List of intent types
        """
        intents = set()
        for record in self.data:
            parsed_intents = record[3]
            for intent_info in parsed_intents:
                if len(intent_info) > 0:
                    intents.add(intent_info[0])
        return sorted(list(intents))
    
    def create_single_turn_dialogues(self) -> List[NLUDialogue]:
        """
        Create single-turn dialogues from NLU data
        
        Each turn becomes its own dialogue for evaluation purposes.
        
        Returns:
            List of NLUDialogue objects
        """
        dialogues = []
        
        for i, record in enumerate(self.data):
            turn = self._extract_turn_info(record, 0)
            
            # Determine primary domain
            domain = "unknown"
            if turn.intents:
                domain = turn.intents[0]['domain']
            
            dialogue = NLUDialogue(
                dialogue_id=f"nlu_turn_{i}",
                domain=domain,
                turns=[turn],
                final_state=turn.belief_state.copy()
            )
            
            dialogues.append(dialogue)
        
        return dialogues
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get dataset statistics
        
        Returns:
            Dictionary with statistics
        """
        turns = self.get_all_turns()
        
        total_turns = len(turns)
        turns_with_slots = sum(1 for turn in turns if turn.belief_state)
        total_slots = sum(len(turn.belief_state) for turn in turns)
        
        intent_counts = {}
        for turn in turns:
            for intent in turn.intents:
                intent_type = intent['intent']
                intent_counts[intent_type] = intent_counts.get(intent_type, 0) + 1
        
        domain_counts = {}
        for turn in turns:
            for intent in turn.intents:
                domain = intent['domain']
                domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        return {
            'total_turns': total_turns,
            'turns_with_slots': turns_with_slots,
            'total_slot_value_pairs': total_slots,
            'avg_slots_per_turn': total_slots / total_turns if total_turns > 0 else 0,
            'unique_intents': len(intent_counts),
            'unique_domains': len(domain_counts),
            'intent_distribution': intent_counts,
            'domain_distribution': domain_counts
        }
