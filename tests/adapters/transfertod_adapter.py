"""
TransferTOD数据集适配器

将TransferTOD数据集格式转换为标准化的对话实例格式。

TransferTOD数据集特点:
- 中文任务型对话数据集
- 支持 clean 和 noise 两种数据类型
- 每个JSON文件包含多个对话实例
- 每个对话包含多个轮次，记录槽位的演变过程
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from .base_adapter import DatasetAdapter, DialogueInstance, DialogueTurn


class TransferTODAdapter(DatasetAdapter):
    """
    TransferTOD数据集适配器
    
    负责加载和转换TransferTOD格式的对话数据。
    """
    
    def __init__(self, data_root: str = "./data/TransferTOD"):
        """
        初始化TransferTOD适配器
        
        Args:
            data_root: TransferTOD数据集根目录路径
        """
        self.data_root = Path(data_root)
        self.raw_data_path = self.data_root / "data" / "raw_data"
        
        # 缓存
        self._dialogue_cache: Dict[str, DialogueInstance] = {}
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        self._all_dialogue_ids: Optional[List[str]] = None
        
    def load_dialogue(self, dialogue_id: str) -> DialogueInstance:
        """
        加载单个对话实例
        
        Args:
            dialogue_id: 格式为 "相对路径:实例ID"，例如 "clean/1-hotel/hotel_clean_4.json:1"
            
        Returns:
            标准化的对话实例
        """
        # 检查缓存
        if dialogue_id in self._dialogue_cache:
            return self._dialogue_cache[dialogue_id]
        
        # 解析 dialogue_id
        try:
            file_path_str, instance_id_str = dialogue_id.split(":")
            instance_id = int(instance_id_str)
        except ValueError:
            raise ValueError(f"Invalid dialogue_id format: {dialogue_id}. Expected 'file_path:instance_id'")
        
        # 构建完整文件路径
        file_path = self.raw_data_path / file_path_str
        
        if not file_path.exists():
            raise FileNotFoundError(f"Dialogue file not found: {file_path}")
        
        # 加载JSON文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 查找对应的对话实例
        raw_dialogue = None
        for item in data:
            if item.get("id") == instance_id:
                raw_dialogue = item
                break
        
        if raw_dialogue is None:
            raise ValueError(f"Dialogue instance with id {instance_id} not found in {file_path}")
        
        # 转换为标准格式
        dialogue_instance = self._convert_to_standard_format(raw_dialogue, dialogue_id)
        
        # 缓存
        self._dialogue_cache[dialogue_id] = dialogue_instance
        
        return dialogue_instance
    
    def _convert_to_standard_format(self, raw_dialogue: Dict, dialogue_id: str) -> DialogueInstance:
        """
        将TransferTOD原始格式转换为标准格式
        
        TransferTOD格式:
        {
            "id": 1,
            "task": "酒店",
            "extract_slot": 4,
            "content": [
                {
                    "Turn": 0,
                    "origin_slots": {"姓名": null, "入住日期": null, ...},
                    "conversations": [
                        {"from": "user", "value": ""},
                        {"from": "assistant", "value": "您的名字是什么？..."}
                    ],
                    "new_slots": {"姓名": null, "入住日期": null, ...}
                },
                ...
            ]
        }
        
        Args:
            raw_dialogue: 原始对话数据
            dialogue_id: 对话ID
            
        Returns:
            标准化的对话实例
        """
        domain = raw_dialogue.get("task", "未知")
        extract_slot = raw_dialogue.get("extract_slot", 0)
        description = f"{domain}场景对话 (extract_slot={extract_slot})"
        
        turns = []
        final_state = {}
        
        # 遍历每一轮对话
        for turn_data in raw_dialogue.get("content", []):
            turn_id = turn_data.get("Turn", 0)
            
            # 提取对话文本
            conversations = turn_data.get("conversations", [])
            user_utterance = ""
            assistant_utterance = ""
            
            for conv in conversations:
                if conv.get("from") == "user":
                    user_utterance = conv.get("value", "")
                elif conv.get("from") == "assistant":
                    assistant_utterance = conv.get("value", "")
            
            # 提取槽位变化
            origin_slots = turn_data.get("origin_slots", {})
            new_slots = turn_data.get("new_slots", {})
            expected_slots = self._extract_slot_changes(origin_slots, new_slots)
            
            # 创建DialogueTurn
            dialogue_turn = DialogueTurn(
                turn_id=turn_id,
                system_utterance=assistant_utterance,
                user_utterance=user_utterance,
                expected_slots=expected_slots
            )
            turns.append(dialogue_turn)
            
            # 更新final_state为最新的槽位状态
            final_state = new_slots.copy()
        
        # 创建DialogueInstance
        dialogue_instance = DialogueInstance(
            dialogue_id=dialogue_id,
            domain=domain,
            description=description,
            turns=turns,
            final_state=final_state,
            metadata={
                "extract_slot": extract_slot,
                "original_id": raw_dialogue.get("id")
            }
        )
        
        return dialogue_instance
    
    def _extract_slot_changes(self, origin_slots: Dict, new_slots: Dict) -> Dict:
        """
        提取本轮变化的槽位
        
        Args:
            origin_slots: 本轮开始时的槽位状态
            new_slots: 本轮结束后的槽位状态
        
        Returns:
            本轮新增或变化的槽位 (只包含非null的值)
        """
        changes = {}
        for key, new_value in new_slots.items():
            old_value = origin_slots.get(key)
            # 只记录有变化且新值非null的槽位
            if new_value != old_value and new_value is not None:
                changes[key] = new_value
        return changes
    
    def get_all_dialogue_ids(self) -> List[str]:
        """
        获取所有对话ID列表
        
        遍历 raw_data/clean/ 和 raw_data/noise/ 目录下的所有JSON文件，
        为每个对话实例生成唯一的 dialogue_id。
        
        Returns:
            所有对话ID列表，格式为 "相对路径:实例ID"
        """
        # 使用缓存
        if self._all_dialogue_ids is not None:
            return self._all_dialogue_ids
        
        dialogue_ids = []
        
        # 遍历 clean 和 noise 目录
        for data_type in ["clean", "noise"]:
            data_type_path = self.raw_data_path / data_type
            
            if not data_type_path.exists():
                continue
            
            # 遍历所有JSON文件
            for json_file in data_type_path.rglob("*.json"):
                # 计算相对路径
                relative_path = json_file.relative_to(self.raw_data_path)
                
                # 读取JSON文件
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 为每个对话实例生成ID
                    for item in data:
                        instance_id = item.get("id")
                        if instance_id is not None:
                            dialogue_id = f"{relative_path}:{instance_id}"
                            dialogue_ids.append(dialogue_id)
                except Exception as e:
                    print(f"Warning: Failed to load {json_file}: {e}")
                    continue
        
        # 缓存结果
        self._all_dialogue_ids = dialogue_ids
        
        return dialogue_ids
    
    def get_domain_schema(self, domain: str) -> Dict[str, Any]:
        """
        获取指定领域的槽位Schema
        
        从该领域的所有对话中自动提取槽位信息。
        收集所有轮次中出现的槽位，而不仅仅是final_state。
        
        Args:
            domain: 领域名称（如"酒店"、"餐厅"等）
            
        Returns:
            领域的Schema定义
        """
        # 检查缓存
        if domain in self._schema_cache:
            return self._schema_cache[domain]
        
        # 收集该领域的所有槽位
        slots = set()
        
        # 遍历所有对话
        for dialogue_id in self.get_all_dialogue_ids():
            try:
                dialogue = self.load_dialogue(dialogue_id)
                if dialogue.domain == domain:
                    # 从所有轮次的expected_slots收集槽位
                    for turn in dialogue.turns:
                        slots.update(turn.expected_slots.keys())
                    # 也从final_state收集槽位
                    slots.update(dialogue.final_state.keys())
            except Exception:
                continue
        
        # 构建Schema
        schema = {
            "domain": domain,
            "slots": {}
        }
        
        for slot_name in sorted(slots):
            schema["slots"][slot_name] = {
                "type": "string",
                "description": f"{slot_name}信息"
            }
        
        # 缓存
        self._schema_cache[domain] = schema
        
        return schema
    
    def get_dialogues_by_domain(self, domain: str = None, data_type: str = None) -> List[str]:
        """
        获取指定领域和数据类型的对话ID列表
        
        Args:
            domain: 领域名称，None表示所有领域
            data_type: 数据类型，"clean"、"noise" 或 None (所有类型)
            
        Returns:
            符合条件的对话ID列表
        """
        matching_ids = []
        
        for dialogue_id in self.get_all_dialogue_ids():
            # 检查数据类型
            if data_type is not None:
                if not dialogue_id.startswith(f"{data_type}/"):
                    continue
            
            # 检查领域
            if domain is not None:
                try:
                    dialogue = self.load_dialogue(dialogue_id)
                    if dialogue.domain == domain:
                        matching_ids.append(dialogue_id)
                except Exception:
                    continue
            else:
                # domain=None 表示所有领域
                matching_ids.append(dialogue_id)
        
        return matching_ids
