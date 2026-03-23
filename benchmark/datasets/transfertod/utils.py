"""
TransferTOD数据集工具函数 - 包含域特定意图配置和其他辅助功能
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


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
                config_path = Path(__file__).parent.parent.parent / "shared" / "configs" / "intent_labels_30_domains_Version2.json"
            else:
                config_path = Path(config_path)
                
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            cls._config = DomainIntentConfig(config_data)
            
        return cls._config


def load_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """加载域意图配置的便利函数"""
    return DomainIntentConfigLoader.load(config_path)
