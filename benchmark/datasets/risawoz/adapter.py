"""
RiSAWOZ数据集适配器（待实现）

RiSAWOZ是另一个中文任务型对话数据集。
"""

from typing import Dict, List, Any, Optional


class RiSAWOZAdapter:
    """RiSAWOZ数据集适配器（占位符）"""
    
    def __init__(self, data_root: str = "./data/RiSAWOZ"):
        self.data_root = data_root
        raise NotImplementedError("RiSAWOZ适配器尚未实现")
        
    def load_dialogue(self, dialogue_id: str):
        raise NotImplementedError("待实现")
        
    def list_dialogues(self):
        raise NotImplementedError("待实现")
