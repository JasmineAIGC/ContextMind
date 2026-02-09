"""
TransferTOD数据集适配器

将TransferTOD数据集格式转换为标准化的对话实例格式。
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class DialogueTurn:
    """单个对话轮次"""
    turn_id: int
    user_utterance: str
    system_utterance: str
    expected_slots: Dict[str, str]
    

@dataclass  
class DialogueInstance:
    """完整对话实例"""
    dialogue_id: str
    domain: str
    turns: List[DialogueTurn]
    
    
class TransferTODAdapter:
    """TransferTOD数据集适配器 - 负责加载和转换TransferTOD格式的对话数据"""
    
    def __init__(self, data_root: str = "./data/TransferTOD"):
        self.data_root = Path(data_root)
        self.dialogue_cache = {}
        
    def load_dialogue(self, dialogue_id: str, data_type: str = "clean") -> DialogueInstance:
        """加载单个对话"""
        cache_key = f"{data_type}_{dialogue_id}"
        if cache_key in self.dialogue_cache:
            return self.dialogue_cache[cache_key]
            
        file_path = self.data_root / data_type / f"{dialogue_id}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"对话文件不存在: {file_path}")
            
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        turns = []
        for turn_data in data.get("turns", []):
            turn = DialogueTurn(
                turn_id=turn_data["turn_id"],
                user_utterance=turn_data["user"],
                system_utterance=turn_data.get("system", ""),
                expected_slots=turn_data.get("slots", {})
            )
            turns.append(turn)
            
        dialogue = DialogueInstance(
            dialogue_id=dialogue_id,
            domain=data.get("domain", "未知"),
            turns=turns
        )
        
        self.dialogue_cache[cache_key] = dialogue
        return dialogue
        
    def list_dialogues(self, data_type: str = "clean", domain: Optional[str] = None) -> List[str]:
        """列出所有对话ID"""
        data_dir = self.data_root / data_type
        if not data_dir.exists():
            return []
            
        dialogue_ids = []
        for file_path in data_dir.glob("*.json"):
            dialogue_id = file_path.stem
            if domain:
                try:
                    dialogue = self.load_dialogue(dialogue_id, data_type)
                    if dialogue.domain == domain:
                        dialogue_ids.append(dialogue_id)
                except:
                    continue
            else:
                dialogue_ids.append(dialogue_id)
                
        return sorted(dialogue_ids)
