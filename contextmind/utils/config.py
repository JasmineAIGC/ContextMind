"""
ConfigManager - 配置管理工具

提供配置验证、加载和管理功能。
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class EngineConfig:
    """引擎配置"""
    app_name: str
    user_id: str
    max_recent_events: int = 10
    enable_memory: bool = True
    enable_session: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'app_name': self.app_name,
            'user_id': self.user_id,
            'max_recent_events': self.max_recent_events,
            'enable_memory': self.enable_memory,
            'enable_session': self.enable_session,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'EngineConfig':
        """从字典创建"""
        return cls(**data)


class ConfigManager:
    """
    配置管理器
    
    支持配置的加载、验证和保存。
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self._config = {}
    
    def load(self, path: Optional[Path] = None) -> Dict[str, Any]:
        """
        加载配置文件
        
        Args:
            path: 配置文件路径
            
        Returns:
            配置字典
        """
        path = path or self.config_path
        if not path or not path.exists():
            return {}
        
        with open(path, 'r', encoding='utf-8') as f:
            self._config = json.load(f)
        
        return self._config
    
    def save(self, config: Dict[str, Any], path: Optional[Path] = None):
        """
        保存配置到文件
        
        Args:
            config: 配置字典
            path: 配置文件路径
        """
        path = path or self.config_path
        if not path:
            raise ValueError("No config path specified")
        
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        self._config = config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)
    
    def set(self, key: str, value: Any):
        """设置配置项"""
        self._config[key] = value
    
    def validate(self) -> bool:
        """验证配置"""
        return validate_config(self._config)


def validate_config(config: Dict[str, Any]) -> bool:
    """
    验证配置的有效性
    
    Args:
        config: 配置字典
        
    Returns:
        是否有效
    """
    required_fields = ['app_name', 'user_id']
    
    for field in required_fields:
        if field not in config:
            return False
    
    # 验证数值范围
    if 'max_recent_events' in config:
        if not isinstance(config['max_recent_events'], int) or config['max_recent_events'] < 1:
            return False
    
    return True
