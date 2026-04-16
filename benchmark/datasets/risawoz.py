"""
RiSAWOZ 数据集综合模块

本模块合并了以下四个子模块:
  - label_parser: RiSAWOZ 标签解析器（解析"意图+领域+槽位+值"格式）
  - nlu_adapter: NLU 格式适配器（将 NLU 格式数据转换为 DST 评测格式）
  - adapter: RiSAWOZ 数据集适配器（将 RiSAWOZ 数据集格式转换为标准化对话实例）
  - sgd_converter: RiSAWOZ → SGD 格式转换器（将 RiSAWOZ 转换为 Google SGD 格式）
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass, field

# 获取logger
logger = logging.getLogger(__name__)


# ======================================================================
# Section: label_parser.py
# ======================================================================
# RiSAWOZ 标签解析器
#
# 用于解析 RiSAWOZ 数据集中的标签格式："意图+领域+槽位+值"


@dataclass
class RiSAWOZLabel:
    """
    RiSAWOZ 标签数据结构
    
    Attributes:
        intent: 意图类型（如 "Greeting", "Request", "Inform"）
        domain: 领域（如 "旅游景点", "酒店", "餐厅"）
        slot: 槽位名称（如 "名称", "区域", "价格"）
        value: 槽位值（如 "希尔顿", "苏州"）
    """
    intent: str
    domain: str
    slot: str
    value: str
    
    def has_slot(self) -> bool:
        """检查是否有槽位"""
        return bool(self.slot)
    
    def has_value(self) -> bool:
        """检查是否有值"""
        return bool(self.value)
    
    def to_dict(self) -> Dict[str, str]:
        """转换为字典"""
        return {
            "intent": self.intent,
            "domain": self.domain,
            "slot": self.slot,
            "value": self.value
        }
    
    def __str__(self) -> str:
        """格式化输出"""
        parts = [self.intent, self.domain]
        if self.has_slot():
            parts.append(f"槽位:{self.slot}")
        if self.has_value():
            parts.append(f"值:{self.value}")
        return " - ".join(parts)


class RiSAWOZLabelParser:
    """
    RiSAWOZ 标签解析器
    
    用于解析 "意图+领域+槽位+值" 格式的标签字符串
    
    示例:
        >>> parser = RiSAWOZLabelParser()
        >>> label = parser.parse_label("Inform+酒店+名称+希尔顿")
        >>> print(label.intent)  # "Inform"
        >>> print(label.domain)  # "酒店"
        >>> print(label.slot)    # "名称"
        >>> print(label.value)   # "希尔顿"
    """
    
    @staticmethod
    def parse_label(label_str: str) -> RiSAWOZLabel:
        """
        解析单个标签字符串
        
        Args:
            label_str: 标签字符串，格式为 "意图+领域+槽位+值"
            
        Returns:
            RiSAWOZLabel 对象
            
        Examples:
            >>> label = RiSAWOZLabelParser.parse_label("Greeting+旅游景点++")
            >>> print(label.intent)  # "Greeting"
            >>> print(label.domain)  # "旅游景点"
            >>> print(label.slot)    # ""
            >>> print(label.value)   # ""
            
            >>> label = RiSAWOZLabelParser.parse_label("Inform+酒店+名称+希尔顿")
            >>> print(label.intent)  # "Inform"
            >>> print(label.domain)  # "酒店"
            >>> print(label.slot)    # "名称"
            >>> print(label.value)   # "希尔顿"
        """
        # 使用 + 分隔标签字符串
        parts = label_str.split('+')
        
        # 确保至少有4个部分（不足的补空字符串）
        while len(parts) < 4:
            parts.append("")
        
        return RiSAWOZLabel(
            intent=parts[0],
            domain=parts[1],
            slot=parts[2],
            value=parts[3]
        )
    
    @staticmethod
    def parse_labels(label_strings: List[str]) -> List[RiSAWOZLabel]:
        """
        批量解析标签字符串列表
        
        Args:
            label_strings: 标签字符串列表
            
        Returns:
            RiSAWOZLabel 对象列表
            
        Examples:
            >>> labels = RiSAWOZLabelParser.parse_labels([
            ...     "Greeting+旅游景点++",
            ...     "Request+旅游景点+区域+"
            ... ])
            >>> print(len(labels))  # 2
            >>> print(labels[0].intent)  # "Greeting"
            >>> print(labels[1].slot)    # "区域"
        """
        return [RiSAWOZLabelParser.parse_label(label_str) for label_str in label_strings]
    
    @staticmethod
    def extract_slot_values(labels: List[RiSAWOZLabel]) -> Dict[str, str]:
        """
        从标签列表中提取槽位-值对
        
        Args:
            labels: RiSAWOZLabel 对象列表
            
        Returns:
            槽位-值字典，键为槽位名，值为槽位值
            
        Examples:
            >>> labels = RiSAWOZLabelParser.parse_labels([
            ...     "Request+旅游景点+区域+",
            ...     "Inform+酒店+名称+希尔顿",
            ...     "Inform+酒店+价格+500"
            ... ])
            >>> slots = RiSAWOZLabelParser.extract_slot_values(labels)
            >>> print(slots)  # {"区域": "", "名称": "希尔顿", "价格": "500"}
        """
        slot_values = {}
        for label in labels:
            if label.has_slot():
                slot_values[label.slot] = label.value
        return slot_values
    
    @staticmethod
    def validate_label(label_str: str) -> bool:
        """
        验证标签字符串格式是否正确
        
        Args:
            label_str: 标签字符串
            
        Returns:
            如果格式正确返回 True，否则返回 False
            
        Examples:
            >>> RiSAWOZLabelParser.validate_label("Greeting+旅游景点++")
            True
            >>> RiSAWOZLabelParser.validate_label("InvalidFormat")
            False
        """
        if not label_str:
            return False
        
        parts = label_str.split('+')
        
        # 至少要有意图和领域
        if len(parts) < 2:
            return False
        
        # 第一部分（意图）不能为空
        if not parts[0]:
            return False
        
        return True



# ======================================================================
# Section: nlu_adapter.py
# ======================================================================
# NLU Format Adapter for RiSAWOZ DST Evaluation
#
# Adapts NLU format data (with tokens, labels, intents, parsed_intents) 
# to work with DST evaluation pipeline.
#
# Format: [[tokens], [labels], [intents], [parsed_intents], [extra]]
# Where parsed_intents contains: [intent_type, domain, slot, value]


# RiSAWOZLabelParser is defined above in this file

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



# ======================================================================
# Section: adapter.py
# ======================================================================
# RiSAWOZ数据集适配器
#
# 将RiSAWOZ数据集格式转换为标准化的对话实例格式。
#
# RiSAWOZ数据集实际目录结构（解压后）:
#   RiSAWOZ-data/
#     source-data/                 # 完整原始标注数据（推荐）
#       all_train10000.json          # 训练集（10000条）
#       all_dev600.json              # 验证集（600条）
#       all_test600_new.json         # 测试集（全部600条）
#       multi_test230_new.json       # 多领域测试集（230条）
#       single_test370_new.json      # 单领域测试集（370条）
#       all_(11200)_new.json         # 完整数据集（11200条）
#     task2-data-DST/              # DST专用格式
#       dst_all_train10000.json
#       dst_all_dev600.json
#       dst_all_test600_new.json
#       dst_multi_test230_new.json
#       dst_single_test370_new.json
#     task3-data-E2E-Context-to-text/  # 端到端生成（标准命名）
#       train.json
#       val.json
#       test.json
#     task5-data-Unified-generative-ellipsis-and-coreference-resolution/
#       all_train10000.json          # 与 source-data 命名相同
#       all_dev600.json
#       all_test600_new.json
#       multi_test230_new.json
#       single_test370_new.json
#       all_(11200)_new.json
#     dataset_split_ids_dict.json
#     RiSAWOZ-Database-and-Ontology/  # 知识库和本体
#
# 使用 RISAWOZ_FILE_MAPPINGS 获取各格式的标准 split→filename 映射。
#
# 参考: https://github.com/terryqj0107/RiSAWOZ


# 获取logger
logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# 各 RiSAWOZ 数据源格式的文件名映射
# key: split 名称 ("train" / "val" / "test")
# value: 对应数据目录中的实际文件名
# ------------------------------------------------------------------
RISAWOZ_FILE_MAPPINGS: Dict[str, Dict[str, str]] = {
    # source-data/ 目录（推荐，信息最丰富）
    "source-data": {
        "train": "all_train10000.json",
        "val":   "all_dev600.json",
        "test":  "all_test600_new.json",
    },
    # task2-data-DST/ 目录（DST 专用格式）
    "task2-dst": {
        "train": "dst_all_train10000.json",
        "val":   "dst_all_dev600.json",
        "test":  "dst_all_test600_new.json",
    },
    # task3-data-E2E-Context-to-text/ 目录（标准命名，直接可用）
    "task3-e2e": {
        "train": "train.json",
        "val":   "val.json",
        "test":  "test.json",
    },
    # task5-data-Unified-generative-ellipsis-and-coreference-resolution/ 目录
    "task5-unified": {
        "train": "all_train10000.json",
        "val":   "all_dev600.json",
        "test":  "all_test600_new.json",
    },
}


@dataclass
class DialogueTurn:
    """单个对话轮次"""
    turn_id: int
    user_utterance: str
    system_utterance: str
    expected_slots: Dict[str, str]  # belief state for this turn
    user_intents: List[List[str]] = field(default_factory=list)  # user_acts: [[intent, domain, slot, value], ...]
    

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
    
    def __init__(self, data_root: str = "resources/dataset/RiSAWOZ", file_mapping: Dict[str, str] = None):
        """
        初始化RiSAWOZ适配器
        
        Args:
            data_root: RiSAWOZ数据目录路径（指向包含 JSON 文件的子目录，而非顶级目录）
                例如:
                  "./data/RiSAWOZ-data/source-data"      → source-data 格式
                  "./data/RiSAWOZ-data/task2-data-DST"   → task2-dst 格式
            file_mapping: split名称到文件名的映射 (可选)
                如不提供，请使用 RISAWOZ_FILE_MAPPINGS[格式名] 中的预设映射。
                例如:
                  RISAWOZ_FILE_MAPPINGS["source-data"]
                    = {"train": "all_train10000.json",
                       "val":   "all_dev600.json",
                       "test":  "all_test600_new.json"}
                  RISAWOZ_FILE_MAPPINGS["task2-dst"]
                    = {"train": "dst_all_train10000.json",
                       "val":   "dst_all_dev600.json",
                       "test":  "dst_all_test600_new.json"}
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
                        f"  - 这是 NLU 任务数据（意图识别、实体提取）\n"
                        f"  - 来自 task1-data 目录（NLU格式）\n\n"
                        f"⚠️  此格式不适用于 DST（对话状态追踪）评测。\n\n"
                        f"【原因】NLU格式缺少DST所需的关键信息:\n"
                        f"  - 无对话ID（无法分组对话）\n"
                        f"  - 无系统话语（只有用户话语）\n"
                        f"  - 无累积的belief_state\n"
                        f"  - 无对话结构（轮次顺序）\n\n"
                        f"【解决方案】\n"
                        f"1. 获取DST格式数据:\n"
                        f"   - 从 RiSAWOZ GitHub 下载: https://github.com/terryqj0107/RiSAWOZ\n"
                        f"   - 使用标准的 train.json, val.json, test.json 文件\n"
                        f"   - 不要使用 task1-data 目录下的文件\n\n"
                        f"2. 详细说明:\n"
                        f"   - 参考文档: benchmark/datasets/risawoz/DATASET_SETUP.md\n"
                        f"   - 格式对比: NLU_VS_DST_FORMAT.md\n\n"
                        f"DST 评测需要的数据格式:\n"
                        f"  {{\n"
                        f"    \"dialogue_id\": \"xxx\",\n"
                        f"    \"dialogue\": [\n"
                        f"      {{\"turn_id\": 0,\n"
                        f"        \"system_utterance\": \"...\",\n"
                        f"        \"user_utterance\": \"...\",\n"
                        f"        \"belief_state\": [...]}}\n"
                        f"    ]\n"
                        f"  }}\n\n"
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
        
        # 提取领域信息 - 支持多种方式
        domains = set()
        
        # 方式1: 从对话级别的domains字段获取
        if isinstance(dialogue_data, dict) and "domains" in dialogue_data:
            dialogue_domains = dialogue_data.get("domains", [])
            if isinstance(dialogue_domains, list):
                domains.update(dialogue_domains)
        
        # 方式2: 从每个turn的domain字段获取
        for turn_data in dialogue_turns:
            if "domain" in turn_data and turn_data["domain"]:
                domains.add(turn_data["domain"])
        
        # 方式3: 从belief_state中提取（旧格式兼容）
        for turn_data in dialogue_turns:
            if "belief_state" in turn_data:
                belief_state_data = turn_data["belief_state"]
                if isinstance(belief_state_data, list):
                    for belief in belief_state_data:
                        if isinstance(belief, dict) and "domain" in belief:
                            domains.add(belief["domain"])
                        # 也从slots中提取domain前缀
                        if isinstance(belief, dict) and "slots" in belief:
                            slots_data = belief.get("slots", [])
                            if isinstance(slots_data, list):
                                for slot_pair in slots_data:
                                    if isinstance(slot_pair, list) and len(slot_pair) >= 2:
                                        slot_key = slot_pair[0]
                                        if '-' in slot_key:
                                            slot_domain = slot_key.split('-')[0]
                                            # 只添加已知的RiSAWOZ领域
                                            known_domains = ['医院', '天气', '旅游景点', '汽车', '火车', '电影', 
                                                           '电脑', '电视剧', '辅导班', '酒店', '飞机', '餐厅']
                                            if slot_domain in known_domains:
                                                domains.add(slot_domain)
        
        # 移除"通用"如果有其他具体领域
        if len(domains) > 1 and "通用" in domains:
            domains.remove("通用")
        
        # 使用第一个领域作为主领域（如果有多个领域则记录在metadata中）
        # 如果没有找到领域，使用"通用"作为默认领域（RiSAWOZ有"通用"领域）
        domain = list(domains)[0] if domains else "通用"
        
        # 解析对话轮次
        for turn_data in dialogue_turns:
            # 额外的安全检查：确保turn_data是字典
            if not isinstance(turn_data, dict):
                logger.warning(f"跳过非字典类型的turn_data: {type(turn_data)}")
                continue
            
            turn_id = turn_data.get("turn_id", len(turns))
            
            # 提取用户和系统话语
            # 支持多种字段名：transcript/user_utterance, system_transcript/system_utterance
            user_utterance = turn_data.get("transcript") or turn_data.get("user_utterance", "")
            system_utterance = turn_data.get("system_transcript") or turn_data.get("system_utterance", "")
            
            # 解析belief state - 支持两种格式
            turn_belief_state = {}
            if "belief_state" in turn_data:
                belief_state_data = turn_data["belief_state"]
                
                if isinstance(belief_state_data, list) and len(belief_state_data) > 0:
                    # 检查第一个元素的格式
                    first_item = belief_state_data[0]
                    
                    if isinstance(first_item, dict) and "slots" in first_item:
                        # 格式1: [{'slots': [[slot-key, value], ...], 'act': 'act_type'}, ...]
                        # 这是 risawoz_test.json 的格式
                        for belief_item in belief_state_data:
                            slots = belief_item.get("slots", [])
                            for slot_pair in slots:
                                if isinstance(slot_pair, list) and len(slot_pair) >= 2:
                                    slot_key = slot_pair[0]  # 已经是 "领域-槽位" 格式
                                    slot_value = slot_pair[1]
                                    if slot_key and slot_value:
                                        turn_belief_state[slot_key] = slot_value
                    elif isinstance(first_item, dict) and "domain" in first_item:
                        # 格式2: [{"domain": "景点", "slot": "名称", "value": "故宫"}, ...]
                        # 这是旧的格式
                        for belief in belief_state_data:
                            slot_domain = belief.get("domain", "")
                            slot_name = belief.get("slot", "")
                            slot_value = belief.get("value", "")
                            
                            if slot_name and slot_value:
                                # 使用"领域-槽位"格式作为key
                                slot_key = f"{slot_domain}-{slot_name}" if slot_domain else slot_name
                                turn_belief_state[slot_key] = slot_value
            
            # 也可以从turn_label获取 (如果belief_state为空)
            if not turn_belief_state and "turn_label" in turn_data:
                turn_label = turn_data["turn_label"]
                if isinstance(turn_label, list):
                    for label_pair in turn_label:
                        if isinstance(label_pair, list) and len(label_pair) >= 2:
                            slot_key = label_pair[0]
                            slot_value = label_pair[1]
                            if slot_key and slot_value:
                                turn_belief_state[slot_key] = slot_value
            
            # 更新累积状态
            cumulative_state.update(turn_belief_state)
            
            # 提取用户意图 (user_acts)
            user_intents = []
            if "user_acts" in turn_data:
                user_acts_data = turn_data["user_acts"]
                if isinstance(user_acts_data, list):
                    for act in user_acts_data:
                        if isinstance(act, list) and len(act) >= 2:
                            # user_acts格式: [intent, domain, slot, value]
                            user_intents.append(act)
            
            # 创建对话轮次（使用累积状态作为expected_slots）
            turn = DialogueTurn(
                turn_id=turn_id,
                user_utterance=user_utterance,
                system_utterance=system_utterance,
                expected_slots=cumulative_state.copy(),
                user_intents=user_intents
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
                "original_id": (dialogue_data.get("dialogue_idx") or 
                               dialogue_data.get("dialogue_id") or 
                               dialogue_id) if isinstance(dialogue_data, dict) else dialogue_id
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
                # 按dialogue_id或dialogue_idx查找
                for item in data:
                    if item.get("dialogue_id") == dialogue_id or item.get("dialogue_idx") == dialogue_id:
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



# ======================================================================
# Section: sgd_converter.py
# ======================================================================
# RiSAWOZ → SGD 格式转换器
#
# 将中文 RiSAWOZ 数据集转换为 Google SGD（Schema-Guided Dialogue）格式，
# 以便使用 pyTOD 算法对该数据集进行训练和测试。
#
# SGD 格式参考:
#   https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
#
# RiSAWOZ 格式参考:
#   https://github.com/terryqj0107/RiSAWOZ
#
# ----------------------------------------------------------------------
# 支持的 RiSAWOZ 源格式
# ----------------------------------------------------------------------
#
# "source-data" 格式 (source-data.zip)
#   对话的每一轮用两个独立的 dict 表示，一个 role="usr"，一个 role="sys":
#     {
#       "dialogue_id": "hotel_0001",
#       "domains": ["酒店"],
#       "dialogue": [
#         {"turn_id": 0, "role": "usr", "utterance": "...",
#          "dialogue_act": [{"act":"Inform","domain":"酒店","slot":"位置","value":"西城区"}],
#          "belief_state": [{"domain":"酒店","slot":"位置","value":"西城区"}]},
#         {"turn_id": 1, "role": "sys", "utterance": "...",
#          "dialogue_act": [...], "belief_state": [...]},
#         ...
#       ]
#     }
#
# "task2-dst" 格式 (task2-data-DST.zip)
#   每轮 dict 同时包含 user_utterance 和 system_utterance:
#     {
#       "dialogue": [
#         {"turn_id": 0,
#          "user_utterance": "...", "system_utterance": "...",
#          "belief_state": [...], "user_acts": [...]},
#         ...
#       ]
#     }
#
# 转换器会自动检测格式。也可通过 source_format 参数手动指定。
#
# 格式映射:
#   RiSAWOZ dialogue → SGD dialogue
#   RiSAWOZ domain   → SGD service_name (e.g. "景点_1")
#   RiSAWOZ turn(s)  → 2 SGD turns (USER turn + SYSTEM turn)
#   RiSAWOZ belief_state [{domain, slot, value}]
#     → SGD state.slot_values {slot_name: [value]}
#   RiSAWOZ user_acts / dialogue_act
#     → SGD actions [{act, slot, values, canonical_values}]


logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# RiSAWOZ intent → SGD dialogue act mapping
# ------------------------------------------------------------------
_ACT_MAP: Dict[str, str] = {
    "Inform": "INFORM",
    "Request": "REQUEST",
    "Select": "SELECT",
    "Confirm": "CONFIRM",
    "NoOffer": "NOOFFER",
    "OfferBook": "OFFERBOOK",
    "OfferBooked": "OFFERBOOKED",
    "Recommend": "RECOMMEND",
    "Greeting": "INFORM",      # no direct SGD equivalent → INFORM
    "Bye": "INFORM",
    "Thank": "INFORM",
    "General": "INFORM",
    "GeneralAct": "INFORM",
}


def _map_act(risawoz_intent: str) -> str:
    """Map a RiSAWOZ intent string to the corresponding SGD act string."""
    return _ACT_MAP.get(risawoz_intent, risawoz_intent.upper())


# ------------------------------------------------------------------
# Source-format detection
# ------------------------------------------------------------------

#: Accepted values for the source_format parameter.
#: Includes all keys from RISAWOZ_FILE_MAPPINGS plus "auto".
SOURCE_FORMATS = ("auto", "source-data", "task2-dst", "task3-e2e", "task5-unified")


def _detect_format(dialogue_data: Dict) -> str:
    """
    Infer the RiSAWOZ source format from a single dialogue dict.

    Returns one of:
      "source-data" — turns have individual role="usr"/"sys" dicts with an
                      "utterance" field and optionally "dialogue_act"
      "task2-dst"   — turns are combined dicts with "user_utterance" /
                      "system_utterance" and optionally "user_acts"
    """
    turns = dialogue_data.get("dialogue", [])
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        if "role" in turn and "utterance" in turn:
            return "source-data"
        if "user_utterance" in turn or "system_utterance" in turn:
            return "task2-dst"
    # default – task2-dst handles both via fallback keys
    return "task2-dst"


# Role values recognized as user/system turns (case-insensitive, checked via .lower())
_USR_ROLES: frozenset = frozenset({
    "usr", "user",                    # English abbreviations
    "用户", "客户", "顾客", "client",  # Chinese/other user-side labels
})
_SYS_ROLES: frozenset = frozenset({
    "sys", "system",                  # English
    "系统", "客服", "服务员", "agent", # Chinese/other system-side labels
})


def _coerce_belief_list(bs: Any) -> List:
    """
    Normalise a belief_state value to a list regardless of how it was stored.

    Handles all known RiSAWOZ belief_state formats:
      - list  (standard)   → returned as-is
      - {}    (empty dict) → []
      - {"domain": {"slot": "value"}}
          Standard nested dict: first-level key is domain name,
          second-level key is plain slot name.
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - {"act_type": {"domain-slot": "value"}}
          Source-data act-type nested dict: first-level key is an act type
          (e.g. "inform slot-values", "turn_inform"), second-level keys are
          "domain-slot" format strings (contain "-").
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - {"domain-slot": "value"}
          Flat dict where key is "domain-slot" format string.
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - None / other       → []
    """
    if isinstance(bs, list):
        return bs
    if isinstance(bs, dict):
        if not bs:
            return []
        result = []
        for k, v in bs.items():
            if isinstance(v, dict):
                # Distinguish two nested-dict formats by inspecting second-level keys:
                #   A. {"domain": {"slot": "value"}}        — slot keys have no "-"
                #   B. {"act_type": {"domain-slot": "value"}} — slot keys contain "-"
                if any("-" in str(sk) for sk in v.keys()):
                    # Format B: act-type key, second-level keys are "domain-slot"
                    for slot_key, value in v.items():
                        sk = str(slot_key)
                        if "-" in sk and value:
                            domain, slot = sk.split("-", 1)
                            result.append({"domain": domain, "slot": slot, "value": str(value)})
                else:
                    # Format A: standard domain → slot → value
                    for slot, value in v.items():
                        if value:
                            result.append({"domain": k, "slot": slot, "value": str(value)})
            elif isinstance(v, str) and v:
                # Flat dict: {"domain-slot": "value"}
                sk = str(k)
                if "-" in sk:
                    domain, slot = sk.split("-", 1)
                    result.append({"domain": domain, "slot": slot, "value": v})
        return result
    return []


def _infer_role_sets(raw_turns: List[Dict]) -> Tuple[frozenset, frozenset]:
    """
    Examine the actual role values in a list of raw turns and return
    ``(usr_roles, sys_roles)`` frozensets to use for pairing.

    Strategy (in order of preference):
    1. If all role values are already in the known sets → use known sets.
    2. If exactly 2 distinct role values exist → the one that appears *first*
       overall is treated as the user role, the other as the system role.
    3. Fallback: return empty frozensets so the caller uses position-based pairing.
    """
    seen_roles = []
    seen_set: set = set()
    for turn in raw_turns:
        if not isinstance(turn, dict):
            continue
        r = turn.get("role")
        if r is not None:
            rl = str(r).lower()
            if rl not in seen_set:
                seen_set.add(rl)
                seen_roles.append(rl)

    if not seen_roles:
        return frozenset(), frozenset()

    # Check if all seen roles are already covered by the known sets
    known = _USR_ROLES | _SYS_ROLES
    if all(r in known for r in seen_roles):
        return _USR_ROLES, _SYS_ROLES

    # Exactly 2 distinct roles → first-seen = user, second-seen = system
    if len(seen_roles) == 2:
        logger.info(
            f"[RiSAWOZ→SGD] 自动推断 role 映射: "
            f"'{seen_roles[0]}' → 用户(user), '{seen_roles[1]}' → 系统(system)"
        )
        return frozenset({seen_roles[0]}), frozenset({seen_roles[1]})

    # More than 2 distinct roles or 1 unknown role → fallback
    logger.warning(
        f"[RiSAWOZ→SGD] ⚠️  无法自动推断 role 映射，将使用位置法（偶数轮=用户，奇数轮=系统）\n"
        f"  发现的 role 值: {seen_roles}"
    )
    return frozenset(), frozenset()


def _get_utterance(turn: Dict) -> str:
    """Extract utterance text from a raw turn, trying all known field names."""
    return (
        turn.get("utterance")
        or turn.get("transcript")
        or turn.get("utt")
        or turn.get("text")
        or turn.get("content")
        or ""
    )


def _pair_turns_by_role(
    raw_turns: List[Dict], usr_roles: frozenset, sys_roles: frozenset
) -> List[Dict]:
    """
    Pair consecutive user/system turns into combined dicts.
    Returns a list of combined turn dicts with keys:
      user_utterance, system_utterance, belief_state, user_acts, _dialogue_act
    """
    combined: List[Dict] = []
    pending_usr: Optional[Dict] = None

    for turn in raw_turns:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).lower()
        if role in usr_roles:
            pending_usr = turn
        elif role in sys_roles and pending_usr is not None:
            user_bs = _coerce_belief_list(pending_usr.get("belief_state", []))
            sys_bs = _coerce_belief_list(turn.get("belief_state", []))
            belief_state = sys_bs if sys_bs else user_bs
            d_acts = pending_usr.get("dialogue_act", [])
            combined.append({
                "user_utterance": _get_utterance(pending_usr),
                "system_utterance": _get_utterance(turn),
                "belief_state": belief_state,
                "user_acts": _dialogue_acts_to_user_acts(d_acts),
                "_dialogue_act": d_acts,
            })
            pending_usr = None

    return combined


def _pair_turns_by_position(raw_turns: List[Dict]) -> List[Dict]:
    """
    Pair turns by position when role values are unknown or missing.
    Even positions (0, 2, 4, …) are treated as user turns;
    odd positions  (1, 3, 5, …) are treated as system turns.
    """
    dicts = [t for t in raw_turns if isinstance(t, dict)]
    combined: List[Dict] = []
    for i in range(0, len(dicts) - 1, 2):
        usr_turn = dicts[i]
        sys_turn = dicts[i + 1]
        user_bs = _coerce_belief_list(usr_turn.get("belief_state", []))
        sys_bs = _coerce_belief_list(sys_turn.get("belief_state", []))
        belief_state = sys_bs if sys_bs else user_bs
        d_acts = usr_turn.get("dialogue_act", [])
        combined.append({
            "user_utterance": _get_utterance(usr_turn),
            "system_utterance": _get_utterance(sys_turn),
            "belief_state": belief_state,
            "user_acts": _dialogue_acts_to_user_acts(d_acts),
            "_dialogue_act": d_acts,
        })
    return combined


def _normalize_turns(dialogue_data: Dict, fmt: str) -> List[Dict]:
    """
    Normalise raw turns into a list of combined dicts, each representing
    one user-turn + one system-turn pair.  Returns dicts with keys:
      user_utterance, system_utterance, belief_state, user_acts
    so the rest of the converter can treat them uniformly.

    For "task2-dst" the dicts already have that shape; we return them as-is.
    For "source-data" / other formats:
      1. Try to pair turns by known role values (from _USR_ROLES / _SYS_ROLES).
      2. If that produces 0 turns, auto-infer role values from the dialogue.
      3. If still 0, fall back to position-based pairing (even=user, odd=system).
    """
    raw_turns = dialogue_data.get("dialogue", [])

    if fmt == "task2-dst":
        return [t for t in raw_turns if isinstance(t, dict)]

    # ── source-data and other role-based formats ──────────────────────
    # Step 1: try with the well-known role sets
    combined = _pair_turns_by_role(raw_turns, _USR_ROLES, _SYS_ROLES)
    if combined:
        return combined

    # Step 2: auto-infer role sets from actual data
    usr_roles, sys_roles = _infer_role_sets(raw_turns)
    if usr_roles or sys_roles:
        combined = _pair_turns_by_role(raw_turns, usr_roles, sys_roles)
    if combined:
        return combined

    # Step 3: position-based fallback (always produces output if there are turns)
    return _pair_turns_by_position(raw_turns)


def _dialogue_acts_to_user_acts(dialogue_acts: List) -> List:
    """
    Convert source-data's dialogue_act list into the user_acts list format
    expected by the rest of the converter.

    Handles two formats:
      dict  : [{"act": "Inform", "domain": "酒店", "slot": "位置", "value": "西城区"}, ...]
      list  : [["Inform", "酒店", "位置", "西城区"], ...]   ← list-of-lists (also common)

    Returns user_acts:
      [["Inform", "酒店", "位置", "西城区"], ...]
    """
    result = []
    for da in dialogue_acts:
        if isinstance(da, dict):
            result.append([
                da.get("act", ""),
                da.get("domain", ""),
                da.get("slot", ""),
                da.get("value", ""),
            ])
        elif isinstance(da, list) and len(da) >= 2:
            # list-of-lists format: [intent, domain, slot?, value?]
            result.append([
                da[0],
                da[1],
                da[2] if len(da) > 2 else "",
                da[3] if len(da) > 3 else "",
            ])
    return result


# ------------------------------------------------------------------
# Schema builder
# ------------------------------------------------------------------

class _SchemaBuilder:
    """Accumulates slot information per domain while scanning dialogues."""

    def __init__(self) -> None:
        # domain → slot_name → set of seen values
        self._slots: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        # domain → set of intents seen
        self._intents: Dict[str, Set[str]] = defaultdict(set)

    def ingest_dialogue(self, dialogue_data: Dict) -> None:
        """Extract slot/intent information from a single raw RiSAWOZ dialogue."""
        for turn in dialogue_data.get("dialogue", []):
            # ── belief_state ─────────────────────────────────────────────
            # Supports three formats:
            #   A. list-of-dicts: [{"domain": "景点", "slot": "名称", "value": "故宫"}]
            #   B. list-of-dicts: [{"slots": [["景点-名称", "故宫"]], "act": "..."}]
            #   C. nested dict:   {"景点": {"名称": "故宫"}} (normalised via _coerce_belief_list)
            belief_state = _coerce_belief_list(turn.get("belief_state", []))
            for belief in belief_state:
                if not isinstance(belief, dict):
                    continue
                if "domain" in belief and "slot" in belief:
                    # Format A: {"domain": "景点", "slot": "名称", "value": "故宫"}
                    domain = belief["domain"]
                    slot = belief["slot"]
                    value = belief.get("value", "")
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]  # ensure key exists
                elif "slots" in belief:
                    # Format B: {"slots": [["景点-名称", "故宫"], ...], "act": "..."}
                    for slot_pair in belief.get("slots", []):
                        if isinstance(slot_pair, list) and len(slot_pair) >= 2:
                            slot_key = slot_pair[0]  # "domain-slot"
                            value = str(slot_pair[1]) if slot_pair[1] else ""
                            if "-" in slot_key:
                                domain, slot = slot_key.split("-", 1)
                                if domain and slot:
                                    if value:
                                        self._slots[domain][slot].add(value)
                                    else:
                                        self._slots[domain][slot]

            # ── user_acts (task2-dst): [[intent, domain, slot, value], ...] ──
            for act in turn.get("user_acts", []):
                if isinstance(act, list) and len(act) >= 2:
                    intent, domain = act[0], act[1]
                    if domain:
                        self._intents[domain].add(intent)

            # ── dialogue_act (source-data) ────────────────────────────────
            # Supports two formats:
            #   dict : [{"act":..,"domain":..,"slot":..,"value":..}, ...]
            #   list : [["Inform", "景点", "名称", "故宫"], ...]  ← list-of-lists
            for da in turn.get("dialogue_act", []):
                if isinstance(da, dict):
                    intent = da.get("act", "")
                    domain = da.get("domain", "")
                    slot = da.get("slot", "")
                    value = da.get("value", "")
                    if domain and intent:
                        self._intents[domain].add(intent)
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]
                elif isinstance(da, list) and len(da) >= 2:
                    # list-of-lists: [intent, domain, slot?, value?]
                    intent, domain = da[0], da[1]
                    slot = da[2] if len(da) > 2 else ""
                    value = da[3] if len(da) > 3 else ""
                    if domain and intent:
                        self._intents[domain].add(intent)
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]

    def build_schema(self) -> List[Dict]:
        """Return a list of SGD-style service schema objects."""
        schemas: List[Dict] = []
        for domain in sorted(self._slots.keys()):
            service_name = f"{domain}_1"
            slots_info = self._slots[domain]

            sgd_slots = []
            for slot_name in sorted(slots_info.keys()):
                values = sorted(slots_info[slot_name])
                # Treat as categorical if the cardinality is small and values exist
                is_categorical = 0 < len(values) <= 20
                sgd_slots.append({
                    "name": slot_name,
                    "description": slot_name,
                    "is_categorical": is_categorical,
                    "possible_values": values if is_categorical else [],
                })

            # Build intents: one "查询" (query) intent per domain as a sensible default
            seen_intents = sorted(self._intents.get(domain, set()))
            # Always include a generic search intent so the schema is well-formed
            if not seen_intents:
                seen_intents = ["查询"]

            sgd_intents = []
            for intent in seen_intents:
                sgd_intents.append({
                    "name": intent,
                    "description": f"{domain}领域的{intent}意图",
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                })

            schemas.append({
                "service_name": service_name,
                "description": f"{domain}领域对话服务",
                "slots": sgd_slots,
                "intents": sgd_intents,
            })

        return schemas


# ------------------------------------------------------------------
# Main converter
# ------------------------------------------------------------------

class RiSAWOZToSGDConverter:
    """
    Converts a RiSAWOZ split (train / val / test) into SGD format.

    Supported source formats
    ------------------------
    "auto" (default)
        Auto-detect from the first dialogue's turn structure.
    "source-data"
        From ``source-data.zip``.  Each turn is an individual dict with
        ``role="usr"`` or ``role="sys"`` and an ``utterance`` field.
        Recommended — contains the richest annotations (``dialogue_act``).
    "task2-dst"
        From ``task2-data-DST.zip``.  Each turn is a combined dict with
        ``user_utterance`` and ``system_utterance`` fields.
        Also fully supported.

    Output directory layout (mirrors SGD):
        <output_dir>/
            schema.json          # all service schemas for this split
            dialogues_001.json   # dialogue files (≤1000 per file by default)
            dialogues_002.json
            ...

    Usage::

        converter = RiSAWOZToSGDConverter(data_root="./data/RiSAWOZ")
        converter.convert(split="train", output_dir="./data/RiSAWOZ_SGD/train")
    """

    DIALOGUES_PER_FILE = 1000

    def __init__(
        self,
        data_root: str = "./data/RiSAWOZ",
        file_mapping: Optional[Dict[str, str]] = None,
        source_format: str = "auto",
    ) -> None:
        if source_format not in SOURCE_FORMATS:
            raise ValueError(
                f"source_format 必须是 {SOURCE_FORMATS} 之一，got {source_format!r}"
            )
        # If no explicit file_mapping provided and a known source_format is given,
        # auto-apply the correct filename mapping from RISAWOZ_FILE_MAPPINGS.
        if file_mapping is None and source_format in RISAWOZ_FILE_MAPPINGS:
            file_mapping = RISAWOZ_FILE_MAPPINGS[source_format]
            logger.debug(
                f"[RiSAWOZToSGDConverter] 自动应用文件映射 ({source_format}): {file_mapping}"
            )
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.data_root = Path(data_root)
        self.source_format = source_format

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        split: str = "val",
        output_dir: Optional[str] = None,
        dialogues_per_file: int = DIALOGUES_PER_FILE,
    ) -> Dict[str, Any]:
        """
        Convert one split and write SGD files to *output_dir*.

        Args:
            split: "train", "val", or "test"
            output_dir: destination directory; defaults to
                        ``<data_root>_SGD/<split>``
            dialogues_per_file: max dialogues per ``dialogues_NNN.json``

        Returns:
            A summary dict with counts of converted dialogues and turns.
        """
        if output_dir is None:
            output_dir = str(self.data_root.parent / f"{self.data_root.name}_SGD" / split)

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[RiSAWOZ→SGD] 加载 {split} 数据集 ...")
        raw_data = self.adapter._load_data_file(split)
        dialogues_raw = raw_data if isinstance(raw_data, list) else list(raw_data.values())

        # Detect format from the first dialogue if mode is "auto"
        effective_format = self.source_format
        if effective_format == "auto" and dialogues_raw:
            first_dict = next(
                (d for d in dialogues_raw if isinstance(d, dict)), None
            )
            if first_dict is not None:
                effective_format = _detect_format(first_dict)
        if effective_format == "auto":
            effective_format = "task2-dst"
        logger.info(f"[RiSAWOZ→SGD] 检测到源格式: {effective_format}")

        # ── Pass 1: build schema ──────────────────────────────────────
        builder = _SchemaBuilder()
        for dialogue_data in dialogues_raw:
            if isinstance(dialogue_data, dict):
                builder.ingest_dialogue(dialogue_data)
        schema = builder.build_schema()

        # Diagnostic: warn when schema is empty (signals a data format mismatch)
        if not schema and dialogues_raw:
            sample = next((d for d in dialogues_raw if isinstance(d, dict)), None)
            if sample:
                sample_turn = sample.get("dialogue", [None])[0]
                logger.warning(
                    f"[RiSAWOZ→SGD] ⚠️  schema.json 为空（0 个服务），"
                    f"请检查数据格式是否匹配。\n"
                    f"  第一条对话的 keys: {list(sample.keys())}\n"
                    f"  第一个 turn 的 keys: {list(sample_turn.keys()) if isinstance(sample_turn, dict) else sample_turn!r}"
                )

        schema_path = out_path / "schema.json"
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"[RiSAWOZ→SGD] 写入 schema.json ({len(schema)} 个服务)")

        # ── Pass 2: convert dialogues ────────────────────────────────
        sgd_dialogues: List[Dict] = []
        total_turns = 0

        for idx, dialogue_data in enumerate(dialogues_raw):
            if not isinstance(dialogue_data, dict):
                continue
            try:
                sgd_dialogue = self._convert_dialogue(dialogue_data, idx, effective_format)
                sgd_dialogues.append(sgd_dialogue)
                total_turns += len(sgd_dialogue["turns"])
            except Exception as exc:
                logger.warning(f"[RiSAWOZ→SGD] 跳过对话 {idx}: {exc}")

        # Diagnostic: warn when turns are all empty (signals a role/format mismatch)
        if sgd_dialogues and total_turns == 0:
            sample = next((d for d in dialogues_raw if isinstance(d, dict)), None)
            if sample:
                turns = sample.get("dialogue", [])
                sample_roles = [t.get("role") for t in turns if isinstance(t, dict)]
                logger.warning(
                    f"[RiSAWOZ→SGD] ⚠️  转换了 {len(sgd_dialogues)} 条对话但总轮次为 0。\n"
                    f"  检测到的源格式: {effective_format}\n"
                    f"  第一条对话的 role 值: {sample_roles[:6]}\n"
                    f"  期望的 role 值: {list(_USR_ROLES)} 或 {list(_SYS_ROLES)}\n"
                    f"  若 role 值不在上述列表中，请检查数据格式。"
                )

        # ── Write dialogue files ─────────────────────────────────────
        file_count = 0
        for start in range(0, max(len(sgd_dialogues), 1), dialogues_per_file):
            chunk = sgd_dialogues[start : start + dialogues_per_file]
            file_count += 1
            file_name = f"dialogues_{file_count:03d}.json"
            (out_path / file_name).write_text(
                json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        summary = {
            "split": split,
            "output_dir": str(out_path),
            "source_format": effective_format,
            "dialogues": len(sgd_dialogues),
            "turns": total_turns,
            "services": len(schema),
            "dialogue_files": file_count,
        }
        logger.info(
            f"[RiSAWOZ→SGD] 完成 {split}: "
            f"{summary['dialogues']} 对话, {summary['turns']} 轮次, "
            f"{summary['services']} 服务, {summary['dialogue_files']} 文件"
        )
        return summary

    # ------------------------------------------------------------------
    # Internal conversion helpers
    # ------------------------------------------------------------------

    def _convert_dialogue(self, dialogue_data: Dict, idx: int, fmt: str = "task2-dst") -> Dict:
        """Convert one RiSAWOZ dialogue dict to SGD format."""
        # Dialogue ID
        dialogue_id = (
            dialogue_data.get("dialogue_id")
            or dialogue_data.get("dialogue_idx")
            or str(idx)
        )

        # Collect all services (domains) referenced in this dialogue
        services: Set[str] = set()
        for turn in dialogue_data.get("dialogue", []):
            for belief in _coerce_belief_list(turn.get("belief_state", [])):
                domain = self._extract_domain_from_belief(belief)
                if domain:
                    services.add(f"{domain}_1")

        services_list = sorted(services) if services else ["通用_1"]

        # Normalise turns into combined user+system dicts
        combined_turns = _normalize_turns(dialogue_data, fmt)

        # Convert turns: one combined turn → USER turn + SYSTEM turn in SGD
        sgd_turns: List[Dict] = []
        cumulative_slots: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
        # cumulative_slots[service_name][slot_name] = [value]

        for turn_data in combined_turns:
            # Support both combined-dict field names:
            #   "user_utterance"    (produced by _normalize_turns for source-data)
            #   "transcript"        (native task2-DST / risawoz field name)
            user_utt = (
                turn_data.get("user_utterance")
                or turn_data.get("transcript")
                or ""
            )
            sys_utt = (
                turn_data.get("system_utterance")
                or turn_data.get("system_transcript")
                or ""
            )

            # Parse this turn's belief_state increment
            turn_slot_delta = self._parse_belief_state(turn_data.get("belief_state", []))
            # Update cumulative state
            for svc, slots in turn_slot_delta.items():
                if svc not in cumulative_slots:
                    cumulative_slots[svc] = {}
                cumulative_slots[svc].update(slots)

            # Parse user actions
            user_actions = self._parse_user_acts(
                turn_data.get("user_acts", []), cumulative_slots
            )

            # Determine active intent from user_acts
            active_intent = self._get_active_intent(turn_data.get("user_acts", []))

            # Build frames for USER turn
            user_frames = self._build_user_frames(
                cumulative_slots, user_actions, active_intent, services_list
            )

            sgd_turns.append({
                "turn_id": str(len(sgd_turns)),
                "speaker": "USER",
                "utterance": user_utt,
                "frames": user_frames,
            })

            # Build frames for SYSTEM turn
            system_frames = self._build_system_frames(cumulative_slots, services_list)

            sgd_turns.append({
                "turn_id": str(len(sgd_turns)),
                "speaker": "SYSTEM",
                "utterance": sys_utt,
                "frames": system_frames,
            })

        return {
            "dialogue_id": str(dialogue_id),
            "services": services_list,
            "turns": sgd_turns,
        }

    # ------ belief_state parsing ------

    def _extract_domain_from_belief(self, belief: Any) -> Optional[str]:
        """Return the domain string from a single belief_state entry (already normalised)."""
        if not isinstance(belief, dict):
            return None
        if "domain" in belief:
            return belief["domain"]
        if "slots" in belief:
            for pair in belief["slots"]:
                if isinstance(pair, list) and len(pair) >= 1:
                    key = pair[0]
                    if isinstance(key, str) and "-" in key:
                        return key.split("-", 1)[0]
        return None

    def _parse_belief_state(
        self, belief_state: Any
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Parse a RiSAWOZ belief_state value into:
            {service_name: {slot_name: [value]}}

        Accepts all supported belief_state formats (normalised via _coerce_belief_list):
          A. [{"domain": "景点", "slot": "名称", "value": "故宫"}, ...]
          B. [{"slots": [["景点-名称", "故宫"], ...], "act": "..."}]
          C. {"景点": {"名称": "故宫"}}  (nested dict, converted by _coerce_belief_list)
        """
        result: Dict[str, Dict[str, List[str]]] = defaultdict(dict)

        for belief in _coerce_belief_list(belief_state):
            if not isinstance(belief, dict):
                continue

            if "domain" in belief and "slot" in belief:
                # Format A
                domain = belief["domain"]
                slot = belief["slot"]
                value = str(belief.get("value", "")) if belief.get("value") else ""
                if domain and slot and value:
                    svc = f"{domain}_1"
                    result[svc][slot] = [value]

            elif "slots" in belief:
                # Format B
                for pair in belief.get("slots", []):
                    if isinstance(pair, list) and len(pair) >= 2:
                        key = pair[0]
                        value = str(pair[1]) if pair[1] else ""
                        if isinstance(key, str) and "-" in key and value:
                            domain, slot = key.split("-", 1)
                            svc = f"{domain}_1"
                            result[svc][slot] = [value]

        return dict(result)

    # ------ user_acts parsing ------

    def _get_active_intent(self, user_acts: List) -> str:
        """Derive the active intent from the first user act with an intent."""
        for act in user_acts:
            if isinstance(act, list) and len(act) >= 1 and act[0]:
                return act[0]
        return "NONE"

    def _parse_user_acts(
        self,
        user_acts: List,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
    ) -> List[Dict]:
        """Convert RiSAWOZ user_acts to SGD actions list."""
        actions: List[Dict] = []
        for act in user_acts:
            if not isinstance(act, list) or len(act) < 2:
                continue
            intent = act[0] if len(act) > 0 else ""
            domain = act[1] if len(act) > 1 else ""
            slot = act[2] if len(act) > 2 else ""
            value = act[3] if len(act) > 3 else ""

            sgd_act = _map_act(intent) if intent else "INFORM"

            actions.append({
                "act": sgd_act,
                "slot": slot,
                "values": [value] if value else [],
                "canonical_values": [value] if value else [],
            })

        return actions

    # ------ frame builders ------

    def _build_user_frames(
        self,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
        user_actions: List[Dict],
        active_intent: str,
        services_list: List[str],
    ) -> List[Dict]:
        """Build SGD frames for a USER turn."""
        frames: List[Dict] = []

        # Determine which services are active (have slots or are in services_list)
        active_services = set(cumulative_slots.keys()) | set(services_list)

        for svc in sorted(active_services):
            slot_values = cumulative_slots.get(svc, {})
            # Filter actions to this service's domain
            svc_domain = svc.rsplit("_", 1)[0]
            svc_actions = [
                a for a in user_actions
                # include if no slot filter, or slot mentioned
                if True  # include all user actions in first service frame
            ] if svc == sorted(active_services)[0] else []

            frames.append({
                "service": svc,
                "state": {
                    "active_intent": active_intent,
                    "requested_slots": [],
                    "slot_values": slot_values,
                },
                "actions": svc_actions,
            })

        return frames

    def _build_system_frames(
        self,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
        services_list: List[str],
    ) -> List[Dict]:
        """Build SGD frames for a SYSTEM turn (no service_call / service_results)."""
        frames: List[Dict] = []

        active_services = set(cumulative_slots.keys()) | set(services_list)

        for svc in sorted(active_services):
            slot_values = cumulative_slots.get(svc, {})
            frames.append({
                "service": svc,
                "state": {
                    "active_intent": "NONE",
                    "requested_slots": [],
                    "slot_values": slot_values,
                },
                "actions": [],
                "service_call": None,
                "service_results": [],
            })

        return frames

