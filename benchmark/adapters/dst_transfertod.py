"""
DST-TransferTOD 适配器

连接 DST 算法和 TransferTOD 数据集，处理格式转换和特殊处理
"""

from typing import Dict, List, Any, Optional
from benchmark.datasets.transfertod.adapters.transfertod_adapter import TransferTODAdapter
from benchmark.adapters.base_adapter import BaseAdapter


class DSTTransferTODAdapter(BaseAdapter):
    """
    DST算法在TransferTOD数据集上的适配器
    
    负责：
    1. 数据格式转换
    2. 槽位映射
    3. 领域映射
    4. 特殊处理逻辑
    """
    
    def __init__(self, data_root: str = ".data/TransferTOD/", data_type: str = "clean"):
        """
        初始化适配器
        
        Args:
            data_root: TransferTOD数据集根目录
            data_type: 数据类型（clean/noisy）
        """
        self.transfertod_adapter = TransferTODAdapter(data_root=data_root, data_type=data_type)
        
    def load_dialogue(self, dialogue_id: str):
        """加载对话数据"""
        return self.transfertod_adapter.load_dialogue(dialogue_id)
    
    def get_all_dialogue_ids(self, domain: Optional[str] = None) -> List[str]:
        """获取所有对话ID"""
        return self.transfertod_adapter.get_all_dialogue_ids(domain)
    
    def convert_to_dst_format(self, dialogue_data: Any) -> Dict[str, Any]:
        """
        将TransferTOD数据转换为DST算法期望的格式
        
        Args:
            dialogue_data: TransferTOD对话数据
            
        Returns:
            DST格式的对话数据
        """
        # TransferTOD数据已经是DST兼容的格式
        # 这里可以添加额外的转换逻辑
        return dialogue_data
    
    def convert_from_dst_format(self, dst_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        将DST输出转换回TransferTOD评估格式
        
        Args:
            dst_output: DST算法输出
            
        Returns:
            TransferTOD评估格式的数据
        """
        return dst_output
    
    def get_predefined_slots(self, domain: str) -> List[str]:
        """获取领域的预定义槽位列表"""
        return self.transfertod_adapter.get_predefined_slots(domain)
    
    def normalize_slot_name(self, slot_name: str, domain: str) -> str:
        """
        标准化槽位名称
        
        Args:
            slot_name: 原始槽位名称
            domain: 领域
            
        Returns:
            标准化后的槽位名称
        """
        # 添加DST特定的槽位名称标准化逻辑
        return slot_name
    
    def normalize_slot_value(self, slot_value: str, slot_name: str) -> str:
        """
        标准化槽位值
        
        Args:
            slot_value: 原始槽位值
            slot_name: 槽位名称
            
        Returns:
            标准化后的槽位值
        """
        # 添加DST特定的槽位值标准化逻辑
        # 例如：日期格式统一、数字格式统一等
        return slot_value
