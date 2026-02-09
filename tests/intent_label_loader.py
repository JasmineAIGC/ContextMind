"""
TransferTOD数据集的意图标签加载器

从intent_labels_30_domains_Version2.json加载并提供意图标签访问接口
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class IntentLabelLoader:
    """
    从JSON文件加载意图标签配置
    
    提供访问领域专属意图标签、描述和关键词的接口，
    用于DST提示词生成和评测。
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        初始化意图标签加载器
        
        Args:
            config_path: 意图标签JSON文件路径
        """
        if config_path is None:
            # 使用benchmark中的共享配置
            config_path = Path(__file__).parent.parent / "benchmark" / "shared" / "configs" / "intent_labels_30_domains_Version2.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.domains = self.config.get("domains", {})
        self.metadata = self.config.get("metadata", {})
        
        logger.info(f"已加载 {len(self.domains)} 个领域的意图标签")
    
    def _load_config(self) -> Dict:
        """从JSON文件加载意图标签配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"意图标签文件未找到: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"意图标签JSON解析失败: {e}")
            raise
    
    def get_domain_intents(self, domain: str) -> List[str]:
        """
        获取指定领域的意图列表
        
        Args:
            domain: 领域名称（中文，如"酒店"、"景点"）
            
        Returns:
            该领域的意图名称列表
        """
        if domain not in self.domains:
            logger.warning(f"领域 '{domain}' 在意图标签中未找到")
            return []
        
        return self.domains[domain].get("intents", [])
    
    def get_intent_description(self, domain: str, intent: str) -> Dict:
        """
        获取特定意图的描述和元数据
        
        Args:
            domain: 领域名称
            intent: 意图名称
            
        Returns:
            包含描述、关键词等的字典
        """
        if domain not in self.domains:
            return {}
        
        intent_descriptions = self.domains[domain].get("intent_descriptions", {})
        return intent_descriptions.get(intent, {})
    
    def get_intent_keywords(self, domain: str, intent: str) -> List[str]:
        """
        获取特定意图的关键词
        
        Args:
            domain: 领域名称
            intent: 意图名称
            
        Returns:
            该意图的关键词列表
        """
        desc = self.get_intent_description(domain, intent)
        return desc.get("keywords", [])
    
    def is_fallback_intent(self, domain: str, intent: str) -> bool:
        """
        检查是否为兜底意图（如"其他"）
        
        Args:
            domain: 领域名称
            intent: 意图名称
            
        Returns:
            如果是兜底意图返回True
        """
        desc = self.get_intent_description(domain, intent)
        return desc.get("is_fallback", False)
    
    def get_fallback_intent_name(self) -> str:
        """
        获取兜底意图的名称
        
        Returns:
            兜底意图名称（默认："其他"）
        """
        return self.metadata.get("other_intent_name", "其他")
    
    def get_all_domains(self) -> List[str]:
        """
        获取所有可用领域的列表
        
        Returns:
            领域名称列表
        """
        return list(self.domains.keys())
    
    def get_prompt_intent_list(self, domain: str) -> str:
        """
        生成格式化的意图列表用于提示词
        
        Args:
            domain: 领域名称
            
        Returns:
            格式化的字符串，列出所有意图及其描述
        """
        intents = self.get_domain_intents(domain)
        intent_descriptions = self.domains.get(domain, {}).get("intent_descriptions", {})
        
        lines = []
        for intent in intents:
            desc_info = intent_descriptions.get(intent, {})
            description = desc_info.get("description", "")
            keywords = desc_info.get("keywords", [])
            
            if description:
                line = f"  - {intent}: {description}"
            else:
                line = f"  - {intent}"
            
            if keywords:
                line += f" (关键词: {', '.join(keywords[:3])}...)" if len(keywords) > 3 else f" (关键词: {', '.join(keywords)})"
            
            lines.append(line)
        
        return "\n".join(lines)
    
    def get_domain_code(self, domain: str) -> Optional[str]:
        """
        获取指定领域的领域代码
        
        Args:
            domain: 领域名称
            
        Returns:
            领域代码（如"1-hotel"）或None（未找到时）
        """
        if domain not in self.domains:
            return None
        return self.domains[domain].get("domain_code")
    
    def get_domain_en(self, domain: str) -> Optional[str]:
        """
        获取指定领域的英文名称
        
        Args:
            domain: 领域名称（中文）
            
        Returns:
            英文领域名称或None（未找到时）
        """
        if domain not in self.domains:
            return None
        return self.domains[domain].get("domain_en")


# 单例实例，便于访问
_intent_label_loader = None


def get_intent_label_loader(config_path: Optional[str] = None) -> IntentLabelLoader:
    """
    获取单例IntentLabelLoader实例
    
    Args:
        config_path: 可选的配置文件路径（仅首次调用时使用）
        
    Returns:
        IntentLabelLoader实例
    """
    global _intent_label_loader
    if _intent_label_loader is None:
        _intent_label_loader = IntentLabelLoader(config_path)
    return _intent_label_loader
