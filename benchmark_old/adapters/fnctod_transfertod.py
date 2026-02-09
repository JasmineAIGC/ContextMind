"""
FnCTOD-TransferTOD 适配器

连接 FnCTOD 算法和 TransferTOD 数据集，处理格式转换和特殊处理
"""

from typing import Dict, List, Any, Optional
from benchmark.datasets.transfertod.adapters.transfertod_adapter import TransferTODAdapter
from benchmark.adapters.base_adapter import DatasetAdapter


class FnCTODTransferTODAdapter(DatasetAdapter):
    """
    FnCTOD算法在TransferTOD数据集上的适配器
    
    负责：
    1. 数据格式转换
    2. 函数调用映射
    3. 槽位映射
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
    
    def convert_to_fnctod_format(self, dialogue_data: Any) -> Dict[str, Any]:
        """
        将TransferTOD数据转换为FnCTOD算法期望的格式
        
        Args:
            dialogue_data: TransferTOD对话数据
            
        Returns:
            FnCTOD格式的对话数据
        """
        # 添加FnCTOD特定的格式转换
        return dialogue_data
    
    def convert_from_fnctod_format(self, fnctod_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        将FnCTOD输出转换回TransferTOD评估格式
        
        Args:
            fnctod_output: FnCTOD算法输出
            
        Returns:
            TransferTOD评估格式的数据
        """
        return fnctod_output
    
    def get_available_functions(self, domain: str) -> List[Dict[str, Any]]:
        """
        获取领域可用的函数列表
        
        Args:
            domain: 领域名称
            
        Returns:
            函数定义列表
        """
        # 根据TransferTOD数据集定义函数
        # 这里返回空列表，需要根据实际需求实现
        return []
    
    def map_slot_to_function_parameter(self, slot_name: str, domain: str) -> str:
        """
        将槽位名称映射到函数参数名称
        
        Args:
            slot_name: 槽位名称
            domain: 领域
            
        Returns:
            函数参数名称
        """
        # 添加槽位到函数参数的映射逻辑
        return slot_name
