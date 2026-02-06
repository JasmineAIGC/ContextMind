#!/usr/bin/env python3
"""
意图配置加载器 (Intent Config Loader)

从JSON配置文件加载意图定义，替代硬编码的Enum。
实现数据驱动的意图评测框架。

版本: 1.0
"""

import json
import os
from typing import Dict, List, Any, Optional
from pathlib import Path


class IntentConfig:
    """
    意图配置类
    
    功能：
    - 加载JSON配置文件
    - 提供意图查询接口
    - 提供映射查询接口
    - 验证配置完整性
    """
    
    def __init__(self, config_path: str):
        """
        初始化意图配置
        
        Args:
            config_path: JSON配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        self._validate_config()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载JSON配置文件"""
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"意图配置文件不存在: {self.config_path}")
        
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _validate_config(self):
        """验证配置完整性"""
        required_keys = ['dataset', 'version', 'intents', 'normalization_mapping']
        for key in required_keys:
            if key not in self.config:
                raise ValueError(f"配置文件缺少必需字段: {key}")
        
        # 验证intents结构
        if 'task_related' not in self.config['intents']:
            raise ValueError("配置文件缺少 task_related 意图定义")
    
    def get_all_intents(self) -> List[Dict[str, Any]]:
        """
        获取所有意图定义
        
        Returns:
            意图定义列表
        """
        intents = []
        for category in ['task_related', 'task_independent', 'meta']:
            if category in self.config['intents']:
                intents.extend(self.config['intents'][category])
        return intents
    
    def get_intent_by_id(self, intent_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取意图定义
        
        Args:
            intent_id: 意图ID（如 'provide_info'）
            
        Returns:
            意图定义字典，如果不存在返回None
        """
        for intent in self.get_all_intents():
            if intent['id'] == intent_id:
                return intent
        return None
    
    def get_intents_by_category(self, category: str) -> List[Dict[str, Any]]:
        """
        获取指定类别的所有意图
        
        Args:
            category: 类别名称（task_related, task_independent, meta）
            
        Returns:
            意图定义列表
        """
        return self.config['intents'].get(category, [])
    
    def get_normalization_mapping(self) -> Dict[str, str]:
        """
        获取意图名称标准化映射
        
        Returns:
            映射字典 {原始名称: 标准名称}
        """
        return self.config.get('normalization_mapping', {})
    
    def get_task_relevance_mapping(self) -> Dict[str, str]:
        """
        获取意图到任务相关性的映射
        
        Returns:
            映射字典 {intent_id: task_relevance}
        """
        return self.config.get('task_relevance_mapping', {})
    
    def get_aggregation_mapping(self) -> Dict[str, str]:
        """
        获取意图聚合映射（用于混淆矩阵）
        
        Returns:
            映射字典 {intent_id: 中文类别名}
        """
        return self.config.get('aggregation_mapping', {})
    
    def normalize_intent(self, intent_name: str) -> str:
        """
        标准化意图名称
        
        Args:
            intent_name: 原始意图名称（可能是中文或英文）
            
        Returns:
            标准化后的意图ID
        """
        mapping = self.get_normalization_mapping()
        return mapping.get(intent_name.lower(), intent_name.lower())
    
    def get_intent_display_name(self, intent_id: str, lang: str = 'zh') -> str:
        """
        获取意图的显示名称
        
        Args:
            intent_id: 意图ID
            lang: 语言（'zh' 或 'en'）
            
        Returns:
            显示名称
        """
        intent = self.get_intent_by_id(intent_id)
        if intent is None:
            return intent_id
        
        if lang == 'zh':
            return intent.get('name_zh', intent_id)
        else:
            return intent.get('name_en', intent_id)
    
    def get_all_intent_ids(self) -> List[str]:
        """
        获取所有意图ID列表
        
        Returns:
            意图ID列表
        """
        return [intent['id'] for intent in self.get_all_intents()]
    
    def get_inference_priority(self, intent_id: str) -> int:
        """
        获取意图的推断优先级
        
        Args:
            intent_id: 意图ID
            
        Returns:
            优先级（数字越大优先级越高）
        """
        intent = self.get_intent_by_id(intent_id)
        if intent is None:
            return 0
        return intent.get('priority', 0)
    
    def get_intent_markers(self, intent_id: str) -> List[str]:
        """
        获取意图的特征标记词
        
        Args:
            intent_id: 意图ID
            
        Returns:
            标记词列表
        """
        intent = self.get_intent_by_id(intent_id)
        if intent is None:
            return []
        return intent.get('markers', [])
    
    @property
    def dataset(self) -> str:
        """数据集名称"""
        return self.config.get('dataset', 'Unknown')
    
    @property
    def version(self) -> str:
        """配置版本"""
        return self.config.get('version', '1.0')
    
    @property
    def description(self) -> str:
        """配置描述"""
        return self.config.get('description', '')


class IntentConfigLoader:
    """
    意图配置加载器（单例模式）
    """
    
    _instance: Optional[IntentConfig] = None
    _config_path: Optional[str] = None
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> IntentConfig:
        """
        加载意图配置（单例模式）
        
        Args:
            config_path: 配置文件路径，如果为None则使用默认路径
            
        Returns:
            IntentConfig实例
        """
        # 默认配置路径
        if config_path is None:
            # 获取当前文件所在目录
            current_dir = Path(__file__).parent
            config_path = current_dir / 'configs' / 'transfertod_intents.json'
            config_path = str(config_path)
        
        # 如果已加载且路径相同，返回缓存实例
        if cls._instance is not None and cls._config_path == config_path:
            return cls._instance
        
        # 加载新配置
        cls._instance = IntentConfig(config_path)
        cls._config_path = config_path
        return cls._instance
    
    @classmethod
    def reload(cls, config_path: Optional[str] = None) -> IntentConfig:
        """
        重新加载配置（强制刷新）
        
        Args:
            config_path: 配置文件路径
            
        Returns:
            IntentConfig实例
        """
        cls._instance = None
        cls._config_path = None
        return cls.load(config_path)


# 便捷函数
def load_intent_config(config_path: Optional[str] = None) -> IntentConfig:
    """
    加载意图配置（便捷函数）
    
    Args:
        config_path: 配置文件路径，如果为None则使用默认路径
        
    Returns:
        IntentConfig实例
    """
    return IntentConfigLoader.load(config_path)
