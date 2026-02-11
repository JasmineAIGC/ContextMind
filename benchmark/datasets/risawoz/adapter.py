"""
RiSAWOZ数据集适配器

将RiSAWOZ数据集格式转换为标准化的对话实例格式。

RiSAWOZ数据集结构:
- train.json: 训练集
- val.json: 验证集
- test.json: 测试集
- 每个JSON文件包含对话实例列表
- 对话格式遵循MultiWOZ风格，包含belief state、对话历史等

参考: https://github.com/terryqj0107/RiSAWOZ
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Union
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class DialogueTurn:
    """单个对话轮次"""
    turn_id: int
    user_utterance: str
    system_utterance: str
    expected_slots: Dict[str, str]  # belief state for this turn
    

@dataclass  
class DialogueInstance:
    """完整对话实例"""
    dialogue_id: str
    domain: str
    turns: List[DialogueTurn]
    description: str = ""
    final_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


class RiSAWOZAdapter:
    """
    RiSAWOZ数据集适配器
    
    RiSAWOZ是一个面向任务型对话的中文数据集，包含12个领域。
    数据格式类似MultiWOZ，包含完整的belief state标注。
    """
    
    def __init__(self, data_root: str = "./data/RiSAWOZ", file_mapping: Dict[str, str] = None):
        """
        初始化RiSAWOZ适配器
        
        Args:
            data_root: RiSAWOZ数据集根目录路径
            file_mapping: 自定义文件名映射 (可选)
                默认: {"train": "train.json", "val": "val.json", "test": "test.json"}
                示例: {"train": "train_data.json", "val": "val_data.json", "test": "test_data.json_all"}
        """
        self.data_root = Path(data_root)
        self.dialogue_cache = {}
        self._all_dialogues_data = None
        self._dialogue_ids = None
        
        # 文件映射：默认值或自定义
        self.file_mapping = file_mapping or {
            "train": "train.json",
            "val": "val.json",
            "test": "test.json"
        }
        
        # RiSAWOZ的12个领域
        self.domains = [
            "景点", "酒店", "餐厅", "地铁",
            "出租", "火车", "电视剧", "天气",
            "航班", "医院", "电影", "音乐"
        ]
    
    def _load_data_file(self, split: str = "val") -> Dict:
        """
        加载数据文件
        
        Args:
            split: 数据集划分，可选 "train", "val", "test"
            
        Returns:
            JSON数据字典
        """
        # 使用file_mapping获取实际文件名
        filename = self.file_mapping.get(split, f"{split}.json")
        file_path = self.data_root / filename
        
        if not file_path.exists():
            raise FileNotFoundError(f"数据文件不存在: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证数据格式
        self._validate_data_format(data, file_path)
        
        return data
    
    def _validate_data_format(self, data: Any, file_path: Path):
        """
        验证数据格式是否适用于 DST 评测
        
        检测常见的错误格式并给出清晰的错误提示。
        """
        if not isinstance(data, (list, dict)):
            return
        
        # 检查是否为 NLU 标注数据格式
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            
            # NLU 格式: [[tokens], [labels], [intents], [parsed_intents], []]
            if isinstance(first_item, list) and len(first_item) >= 4:
                # 检查是否所有前4个元素都是列表（NLU格式的特征）
                if all(isinstance(x, list) for x in first_item[:4]):
                    raise ValueError(
                        f"\n{'='*70}\n"
                        f"❌ 错误：检测到 NLU 标注数据格式\n"
                        f"{'='*70}\n\n"
                        f"文件: {file_path}\n\n"
                        f"检测到的格式:\n"
                        f"  - 嵌套列表结构 [[tokens], [labels], [intents], ...]\n"
                        f"  - 这是 NLU 任务数据（意图识别、实体提取）\n\n"
                        f"此格式不适用于 DST（对话状态追踪）评测。\n\n"
                        f"DST 评测需要的数据格式（两种之一）:\n\n"
                        f"格式1 - 字典格式:\n"
                        f"  {{\n"
                        f"    \"dialogue_id\": \"xxx\",\n"
                        f"    \"dialogue\": [\n"
                        f"      {{\"user_utterance\": \"...\", \"belief_state\": [...]}}\n"
                        f"    ]\n"
                        f"  }}\n\n"
                        f"格式2 - 列表格式:\n"
                        f"  [\n"
                        f"    {{\"turn_id\": 0, \"user_utterance\": \"...\", \"belief_state\": [...]}},\n"
                        f"    {{\"turn_id\": 1, \"user_utterance\": \"...\", \"belief_state\": [...]}}\n"
                        f"  ]\n\n"
                        f"如何获取正确的数据:\n"
                        f"  1. 从 RiSAWOZ GitHub 下载: https://github.com/terryqj0107/RiSAWOZ\n"
                        f"  2. 使用标准的 train.json, val.json, test.json 文件\n"
                        f"  3. 不要使用 task1-data 目录下的 NLU 格式文件\n\n"
                        f"参考文档: benchmark/datasets/risawoz/DATASET_SETUP.md\n"
                        f"{'='*70}\n"
                    )
    
    def _parse_dialogue_data(self, dialogue_data: Dict, dialogue_id: str) -> DialogueInstance:
        """
        解析单个对话数据
        
        Args:
            dialogue_data: 原始对话数据（可以是字典或列表）
            dialogue_id: 对话ID
            
        Returns:
            标准化的对话实例
        """
        # RiSAWOZ数据格式支持两种：
        # 格式1 (标准字典格式):
        # {
        #   "dialogue_id": "xxx",
        #   "goal": {...},
        #   "dialogue": [...]
        # }
        # 格式2 (简化列表格式):
        # [
        #   {
        #     "turn_id": 0,
        #     "user_utterance": "...",
        #     "belief_state": [...]
        #   },
        #   ...
        # ]
        # 注意：task1-data 中的 NLU 格式数据（嵌套列表，包含 tokens, labels, intents）
        # 不适用于 DST 评测，会被验证拒绝。
        
        turns = []
        cumulative_state = {}  # 累积的belief state
        
        # 检测数据格式并规范化
        if isinstance(dialogue_data, list):
            # 格式2：直接是对话轮次列表
            # 处理可能的嵌套列表结构
            dialogue_turns = []
            for item in dialogue_data:
                if isinstance(item, dict):
                    dialogue_turns.append(item)
                elif isinstance(item, list):
                    # 嵌套列表，展开
                    dialogue_turns.extend([t for t in item if isinstance(t, dict)])
            goal_info = {}
        elif isinstance(dialogue_data, dict):
            # 格式1：标准字典格式
            dialogue_turns = dialogue_data.get("dialogue", [])
            goal_info = dialogue_data.get("goal", {})
        else:
            raise ValueError(f"不支持的对话数据格式: {type(dialogue_data)}")
        
        # 提取领域信息
        domains = set()
        for turn_data in dialogue_turns:
            if "belief_state" in turn_data:
                for belief in turn_data["belief_state"]:
                    if "domain" in belief:
                        domains.add(belief["domain"])
        
        # 使用第一个领域作为主领域（如果有多个领域则记录在metadata中）
        domain = list(domains)[0] if domains else "未知"
        
        # 解析对话轮次
        for turn_data in dialogue_turns:
            # 额外的安全检查：确保turn_data是字典
            if not isinstance(turn_data, dict):
                logger.warning(f"跳过非字典类型的turn_data: {type(turn_data)}")
                continue
            
            turn_id = turn_data.get("turn_id", len(turns))
            
            # 提取用户和系统话语
            user_utterance = turn_data.get("user_utterance", "")
            system_utterance = turn_data.get("system_utterance", "")
            
            # 解析belief state
            turn_belief_state = {}
            if "belief_state" in turn_data:
                for belief in turn_data["belief_state"]:
                    # RiSAWOZ格式: {"domain": "景点", "slot": "名称", "value": "故宫"}
                    slot_domain = belief.get("domain", "")
                    slot_name = belief.get("slot", "")
                    slot_value = belief.get("value", "")
                    
                    if slot_name and slot_value:
                        # 使用"领域-槽位"格式作为key
                        slot_key = f"{slot_domain}-{slot_name}" if slot_domain else slot_name
                        turn_belief_state[slot_key] = slot_value
            
            # 更新累积状态
            cumulative_state.update(turn_belief_state)
            
            # 创建对话轮次（使用累积状态作为expected_slots）
            turn = DialogueTurn(
                turn_id=turn_id,
                user_utterance=user_utterance,
                system_utterance=system_utterance,
                expected_slots=cumulative_state.copy()
            )
            turns.append(turn)
        
        # 创建对话实例
        dialogue = DialogueInstance(
            dialogue_id=dialogue_id,
            domain=domain,
            turns=turns,
            description=goal_info.get("description", "") if isinstance(goal_info, dict) else "",
            final_state=cumulative_state.copy(),
            metadata={
                "all_domains": list(domains),
                "goal": goal_info,
                "original_id": dialogue_data.get("dialogue_id", dialogue_id) if isinstance(dialogue_data, dict) else dialogue_id
            }
        )
        
        return dialogue
    
    def load_dialogue(self, dialogue_id: str, split: str = "val") -> DialogueInstance:
        """
        加载单个对话实例
        
        Args:
            dialogue_id: 对话ID或索引
            split: 数据集划分 ("train", "val", "test")
            
        Returns:
            标准化的对话实例
        """
        cache_key = f"{split}:{dialogue_id}"
        
        # 检查缓存
        if cache_key in self.dialogue_cache:
            return self.dialogue_cache[cache_key]
        
        # 加载数据文件
        data = self._load_data_file(split)
        
        # 查找对话
        dialogue_data = None
        if isinstance(data, list):
            # 数组格式
            if dialogue_id.isdigit():
                idx = int(dialogue_id)
                if 0 <= idx < len(data):
                    dialogue_data = data[idx]
            else:
                # 按dialogue_id查找
                for item in data:
                    if item.get("dialogue_id") == dialogue_id:
                        dialogue_data = item
                        break
        elif isinstance(data, dict):
            # 字典格式
            dialogue_data = data.get(dialogue_id)
        
        if dialogue_data is None:
            raise ValueError(f"对话不存在: {dialogue_id} in {split}")
        
        # 解析对话
        dialogue = self._parse_dialogue_data(dialogue_data, dialogue_id)
        
        # 缓存
        self.dialogue_cache[cache_key] = dialogue
        
        return dialogue
    
    def get_dialogues_by_domain(self, domain: str = None, split: str = "val") -> List[str]:
        """
        获取指定领域的所有对话ID
        
        Args:
            domain: 领域名称（如果为None则返回所有对话）
            split: 数据集划分
            
        Returns:
            对话ID列表
        """
        data = self._load_data_file(split)
        dialogue_ids = []
        
        if isinstance(data, list):
            for idx, dialogue_data in enumerate(data):
                # 检查领域
                if domain is None:
                    dialogue_ids.append(str(idx))
                else:
                    # 提取该对话的所有领域
                    dialogue_domains = set()
                    if "dialogue" in dialogue_data:
                        for turn_data in dialogue_data["dialogue"]:
                            if "belief_state" in turn_data:
                                for belief in turn_data["belief_state"]:
                                    if "domain" in belief:
                                        dialogue_domains.add(belief["domain"])
                    
                    if domain in dialogue_domains:
                        dialogue_ids.append(str(idx))
        elif isinstance(data, dict):
            for did in data.keys():
                dialogue_data = data[did]
                if domain is None:
                    dialogue_ids.append(did)
                else:
                    dialogue_domains = set()
                    if "dialogue" in dialogue_data:
                        for turn_data in dialogue_data["dialogue"]:
                            if "belief_state" in turn_data:
                                for belief in turn_data["belief_state"]:
                                    if "domain" in belief:
                                        dialogue_domains.add(belief["domain"])
                    
                    if domain in dialogue_domains:
                        dialogue_ids.append(did)
        
        return dialogue_ids
    
    def get_all_domains(self) -> List[str]:
        """
        获取数据集中所有可用的领域列表
        
        Returns:
            领域名称列表
        """
        return self.domains.copy()
    
    def get_domain_schema(self, domain: str) -> Dict[str, Any]:
        """
        获取指定领域的schema
        
        Args:
            domain: 领域名称
            
        Returns:
            领域schema（槽位定义等）
        """
        # RiSAWOZ的slot定义是动态的，从数据中提取
        # 这里返回一个基本结构，实际槽位在运行时从数据中获取
        return {
            "domain": domain,
            "description": f"{domain}领域的对话任务处理",
            "slots": {},  # 动态填充
            "metadata": {
                "source": "RiSAWOZ数据集",
                "domains": self.domains
            }
        }
