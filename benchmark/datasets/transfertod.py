"""
TransferTOD 数据集综合模块

本模块合并了以下两个子模块:
  - utils: TransferTOD 数据集工具函数（DomainIntentConfig、DomainIntentConfigLoader 等）
  - adapter: TransferTOD 数据集适配器（将 TransferTOD 格式数据转换为标准化对话实例）
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# ======================================================================
# Section: utils.py
# ======================================================================
# TransferTOD数据集工具函数 - 包含域特定意图配置和其他辅助功能


class DomainIntentConfig:
    """域特定意图配置 - 管理30个TransferTOD域的意图定义"""
    
    def __init__(self, config_data: Dict[str, Any]):
        self.dataset = config_data.get("dataset", "TransferTOD")
        self.version = config_data.get("version", "3.0")
        self.domains = config_data.get("domains", {})
        self.metadata = config_data.get("metadata", {})
        self.other_intent_name = self.metadata.get("other_intent_name", "其他")
        
    def get_all_domains(self) -> List[str]:
        return list(self.domains.keys())
        
    def get_domain_intents(self, domain: str) -> List[str]:
        if domain not in self.domains:
            return []
        return self.domains[domain].get("intents", [])
        
    def get_intent_description(self, domain: str, intent: str) -> Optional[Dict[str, Any]]:
        if domain not in self.domains:
            return None
        intent_descs = self.domains[domain].get("intent_descriptions", {})
        return intent_descs.get(intent)
        
    def is_fallback_intent(self, domain: str, intent: str) -> bool:
        return intent == self.other_intent_name


class DomainIntentConfigLoader:
    """域意图配置加载器（单例模式）"""
    _instance = None
    _config = None
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        if cls._config is None or config_path:
            if config_path is None:
                # 使用benchmark/shared/configs/中的共享配置
                config_path = Path(__file__).parent.parent / "evaluators" / "configs" / "intent_labels_30_domains_Version2.json"
            else:
                config_path = Path(config_path)
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            cls._config = DomainIntentConfig(config_data)
            
        return cls._config


def load_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """加载域意图配置的便利函数"""
    return DomainIntentConfigLoader.load(config_path)



# ======================================================================
# Section: adapter.py
# ======================================================================
# TransferTOD数据集适配器
#
# 将TransferTOD数据集格式转换为标准化的对话实例格式。
#
# TransferTOD数据集结构:
# - data_root/data/raw_data/clean/  - 干净数据
# - data_root/data/raw_data/noise/  - 噪声数据
# - 每个JSON文件包含多个对话实例
# - dialogue_id格式: "相对路径:实例ID"，例如 "clean/1-hotel/hotel_clean_4.json:1"


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
    description: str = ""
    final_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    
class TransferTODAdapter:
    """TransferTOD数据集适配器 - 负责加载和转换TransferTOD格式的对话数据"""
    
    def __init__(self, data_root: str = "resources/dataset/TransferTOD", schemas_file: str = None):
        """
        初始化TransferTOD适配器
        
        Args:
            data_root: TransferTOD数据集根目录路径
            schemas_file: 可选的预加载schemas JSON文件路径
                         如果提供，将从文件加载schemas而不是扫描数据集
        """
        self.data_root = Path(data_root)
        self.raw_data_path = self.data_root / "data" / "raw_data"
        self.dialogue_cache = {}
        self._all_dialogue_ids = None
        self._schema_cache = {}  # 缓存领域schema
        self._available_domains = None  # 缓存可用的域列表
        
        # 如果提供了schemas文件，预加载所有schemas
        if schemas_file:
            self.load_schemas_from_file(schemas_file)
        
    def load_dialogue(self, dialogue_id: str, data_type: str = "clean") -> DialogueInstance:
        """
        加载单个对话实例
        
        Args:
            dialogue_id: 格式为 "相对路径:实例ID"，例如 "clean/1-hotel/hotel_clean_4.json:1"
                        或简单的文件路径格式（向后兼容）
            data_type: 数据类型，用于向后兼容（如果dialogue_id不包含路径信息）
            
        Returns:
            标准化的对话实例
        """
        # 检查缓存
        if dialogue_id in self.dialogue_cache:
            return self.dialogue_cache[dialogue_id]
        
        # 解析 dialogue_id
        if ":" in dialogue_id:
            # 新格式: "clean/1-hotel/hotel_clean_4.json:1"
            file_path_str, instance_id_str = dialogue_id.split(":")
            instance_id = int(instance_id_str)
            file_path = self.raw_data_path / file_path_str
        else:
            # 向后兼容：简单格式（假设在data_type目录下）
            file_path = self.raw_data_path / data_type / f"{dialogue_id}.json"
            instance_id = 0  # 默认加载第一个实例
        
        if not file_path.exists():
            raise FileNotFoundError(f"对话文件不存在: {file_path}")
        
        # 加载JSON文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 查找对应的对话实例
        raw_dialogue = None
        if isinstance(data, list):
            # 数组格式：查找指定ID的实例
            for item in data:
                if item.get("id") == instance_id:
                    raw_dialogue = item
                    break
            if raw_dialogue is None:
                raise ValueError(f"在文件 {file_path} 中找不到ID为 {instance_id} 的对话实例")
        else:
            # 单个对象格式
            raw_dialogue = data
        
        if raw_dialogue is None:
            raise ValueError(f"无法从文件 {file_path} 加载对话实例")
        
        # 转换为标准格式
        dialogue_instance = self._convert_to_standard_format(raw_dialogue, dialogue_id)
        
        # 缓存
        self.dialogue_cache[dialogue_id] = dialogue_instance
        
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
        
    def list_dialogues(self, data_type: str = "clean", domain: Optional[str] = None) -> List[str]:
        """
        列出所有对话ID
        
        Args:
            data_type: 数据类型 ("clean" 或 "noise")
            domain: 领域过滤，None表示所有领域
            
        Returns:
            对话ID列表，格式为 "相对路径:实例ID"
        """
        data_dir = self.raw_data_path / data_type
        if not data_dir.exists():
            return []
            
        dialogue_ids = []
        
        # 遍历所有JSON文件
        for json_file in data_dir.rglob("*.json"):
            # 计算相对路径
            relative_path = json_file.relative_to(self.raw_data_path)
            
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # 处理列表格式
                if isinstance(data, list):
                    for item in data:
                        instance_id = item.get("id")
                        if instance_id is not None:
                            # Use as_posix() to ensure consistent forward slashes on all platforms
                            dialogue_id = f"{relative_path.as_posix()}:{instance_id}"
                            
                            # 域过滤
                            if domain:
                                item_domain = item.get("task", "未知")
                                if item_domain != domain:
                                    continue
                            
                            dialogue_ids.append(dialogue_id)
                else:
                    # 单个对象格式
                    dialogue_id = str(relative_path)
                    
                    # 域过滤
                    if domain:
                        item_domain = data.get("task", "未知")
                        if item_domain != domain:
                            continue
                    
                    dialogue_ids.append(dialogue_id)
                    
            except Exception as e:
                print(f"Warning: 加载文件失败 {json_file}: {e}")
                continue
                
        return sorted(dialogue_ids)
    
    def get_all_dialogue_ids(self) -> List[str]:
        """
        获取所有对话ID列表（clean和noise）
        
        Returns:
            所有对话ID列表
        """
        if self._all_dialogue_ids is not None:
            return self._all_dialogue_ids
        
        dialogue_ids = []
        for data_type in ["clean", "noise"]:
            dialogue_ids.extend(self.list_dialogues(data_type=data_type))
        
        self._all_dialogue_ids = dialogue_ids
        return dialogue_ids
    
    def get_domain_schema(self, domain: str) -> Dict[str, Any]:
        """
        获取指定领域的槽位Schema
        
        从该领域的所有对话中自动提取槽位信息。
        收集所有轮次中出现的槽位，而不仅仅是final_state。
        
        这是从TransferTOD数据集获取域-槽位预定义信息的核心方法。
        
        Args:
            domain: 领域名称（如"酒店"、"餐厅"等）
            
        Returns:
            领域的Schema定义，包含：
            - domain: 领域名称
            - description: 领域描述
            - slots: 槽位定义字典
        """
        # 检查缓存
        if domain in self._schema_cache:
            return self._schema_cache[domain]
        
        # 收集该领域的所有槽位和示例值
        slots_info = {}  # {slot_name: {"values": set(), "count": int}}
        
        # 遍历所有对话
        dialogue_count = 0
        for dialogue_id in self.get_all_dialogue_ids():
            try:
                dialogue = self.load_dialogue(dialogue_id)
                if dialogue.domain == domain:
                    dialogue_count += 1
                    # 从所有轮次的expected_slots收集槽位
                    for turn in dialogue.turns:
                        for slot_name, slot_value in turn.expected_slots.items():
                            if slot_name not in slots_info:
                                slots_info[slot_name] = {"values": set(), "count": 0}
                            if slot_value:  # 只记录非空值
                                slots_info[slot_name]["values"].add(str(slot_value))
                                slots_info[slot_name]["count"] += 1
                    # 也从final_state收集槽位
                    for slot_name, slot_value in dialogue.final_state.items():
                        if slot_name not in slots_info:
                            slots_info[slot_name] = {"values": set(), "count": 0}
                        if slot_value:
                            slots_info[slot_name]["values"].add(str(slot_value))
            except Exception:
                continue
        
        # 构建Schema
        schema = {
            "domain": domain,
            "description": f"{domain}领域的对话任务处理",
            "slots": {},
            "metadata": {
                "dialogue_count": dialogue_count,
                "slot_count": len(slots_info),
                "source": "TransferTOD数据集自动提取"
            }
        }
        
        # 为每个槽位生成描述
        for slot_name in sorted(slots_info.keys()):
            info = slots_info[slot_name]
            # 创建更详细的描述
            description = f"{slot_name}"
            
            # 如果有示例值，添加到描述中
            example_values = list(info["values"])[:3]  # 最多3个示例
            if example_values:
                # 使用逗号分隔，更通用
                examples_str = ", ".join(example_values)
                description += f"（如：{examples_str}）"
            
            schema["slots"][slot_name] = {
                "type": "string",
                "description": description,
                "occurrence_count": info["count"],
                "example_values": example_values
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
                    if dialogue.domain != domain:
                        continue
                except Exception:
                    continue
            
            # Both filters passed (or were None), add to results
            matching_ids.append(dialogue_id)
        
        return matching_ids
    
    def get_all_domains(self, verbose: bool = False) -> List[str]:
        """
        获取数据集中所有可用的领域列表
        
        从实际对话数据中提取所有唯一的领域名称。
        
        Args:
            verbose: 是否显示详细的扫描信息
        
        Returns:
            领域名称列表（已排序）
        """
        if self._available_domains is not None:
            return self._available_domains
        
        domains = set()
        error_count = 0
        
        # 遍历所有对话，收集唯一的领域
        dialogue_ids = self.get_all_dialogue_ids()
        if verbose:
            print(f"扫描 {len(dialogue_ids)} 个对话以查找所有域...")
        
        for dialogue_id in dialogue_ids:
            try:
                dialogue = self.load_dialogue(dialogue_id)
                domains.add(dialogue.domain)
            except Exception as e:
                error_count += 1
                if verbose:
                    print(f"  警告: 无法加载对话 {dialogue_id}: {e}")
                continue
        
        if verbose and error_count > 0:
            print(f"  跳过了 {error_count} 个无法加载的对话")
        
        self._available_domains = sorted(list(domains))
        return self._available_domains
    
    def get_all_domain_schemas(self) -> Dict[str, Dict[str, Any]]:
        """
        获取所有领域的Schema定义
        
        遍历所有可用领域，为每个领域生成Schema。
        这是从TransferTOD数据集获取30个域的预定义函数信息的主要方法。
        
        Returns:
            字典，键为领域名称，值为该领域的Schema定义
        """
        all_schemas = {}
        
        for domain in self.get_all_domains():
            try:
                schema = self.get_domain_schema(domain)
                all_schemas[domain] = schema
            except Exception as e:
                print(f"警告: 无法获取领域 '{domain}' 的schema: {e}")
                continue
        
        return all_schemas
    
    @staticmethod
    @staticmethod
    def get_transfertod_domains() -> List[str]:
        """
        获取TransferTOD数据集的标准域列表
        
        注意：此列表基于实际数据集中存在的域。
        TransferTOD数据集包含24个任务型对话域。
        域名称使用中文，与TransferTOD数据集保持一致。
        
        以下6个域在原始定义中存在但数据集中不可用，已从列表中移除：
        - 打印、摄影、机票、理发店、音乐会、餐厅
        
        Returns:
            包含24个域名的列表
        """
        return [
            "保洁", "健身房", "医院", "博物馆", "培训班", "外卖", "家电维修", "度假村",
            "律师", "快递", "搬家", "景点", "洗衣", "火车票",
            "牙医", "电影", "电话卡", "租房", "租车", "美容院", "购物",
            "送水", "邮轮", "酒店"
        ]
    
    @staticmethod
    def get_transfertod_30_domains() -> List[str]:
        """
        获取TransferTOD项目的标准域列表（已弃用）
        
        已弃用：使用 get_transfertod_domains() 代替
        
        注意：TransferTOD数据集实际只有24个域，不是30个。
        此方法保留用于向后兼容，返回与 get_transfertod_domains() 相同的结果。
        
        Returns:
            包含24个域名的列表
        """
        return TransferTODAdapter.get_transfertod_domains()
    
    def load_schemas_from_file(self, schemas_file: str):
        """
        从JSON文件加载所有域的schemas
        
        这个方法允许使用预先生成的schemas文件，而不是每次都扫描数据集。
        这对于加速测试和使用一致的schema定义非常有用。
        
        Args:
            schemas_file: schemas JSON文件路径
                         文件格式应该是 extract_transfertod_schemas.py 生成的格式
        
        Raises:
            FileNotFoundError: 如果文件不存在
            json.JSONDecodeError: 如果JSON格式错误
            ValueError: 如果文件格式不正确
        
        Example:
            adapter = TransferTODAdapter("./data/TransferTOD", 
                                        schemas_file="transfertod_schemas.json")
            # 现在所有 get_domain_schema() 调用都会使用预加载的schemas
        """
        import json
        from pathlib import Path
        from contextmind.infra.logger import get_logger
        
        logger = get_logger(__name__)
        
        schemas_path = Path(schemas_file)
        if not schemas_path.exists():
            raise FileNotFoundError(f"Schemas文件不存在: {schemas_file}")
        
        with open(schemas_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # 验证文件格式
        if "domains" not in data:
            raise ValueError(f"Schemas文件格式错误: 缺少 'domains' 字段")
        
        # 加载所有domains的schemas到缓存
        domains_data = data["domains"]
        for domain_name, schema in domains_data.items():
            # 验证schema包含必要字段
            if "slots" not in schema:
                logger.warning(f"域 '{domain_name}' 的schema缺少 'slots' 字段，跳过")
                continue
            
            # 存入缓存
            self._schema_cache[domain_name] = schema
        
        logger.info(f"从文件加载了 {len(self._schema_cache)} 个域的schemas: {schemas_file}")
        print(f"✅ 从文件加载了 {len(self._schema_cache)} 个域的schemas: {schemas_file}")
        
        # 更新可用域列表
        self._available_domains = sorted(list(self._schema_cache.keys()))

