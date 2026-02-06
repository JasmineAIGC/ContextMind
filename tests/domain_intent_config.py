"""
TransferTOD数据集的域特定意图配置

支持30个域，包含完整的意图分类体系。
对"其他"(Other)意图提供特殊处理，作为回退类别。
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class DomainIntentConfig:
    """
    域特定意图配置
    
    管理30个TransferTOD域的意图定义，并对"其他"(Other)意图提供特殊处理。
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        初始化域意图配置
        
        参数:
            config_data: 从JSON加载的配置字典
        """
        self.dataset = config_data.get("dataset", "TransferTOD")
        self.version = config_data.get("version", "3.0")
        self.description = config_data.get("description", "")
        self.total_domains = config_data.get("total_domains", 30)
        self.metadata = config_data.get("metadata", {})
        self.domains = config_data.get("domains", {})
        
        # 提取特殊"其他"意图处理信息
        self.other_intent_name = self.metadata.get("other_intent_name", "其他")
        self.other_intent_description = self.metadata.get("other_intent_description", "")
        self.other_intent_evaluation = self.metadata.get("other_intent_evaluation", "special_handling")
    
    def get_all_domains(self) -> List[str]:
        """
        获取所有域名列表
        
        返回:
            域名列表(中文)
        """
        return list(self.domains.keys())
    
    def get_domain_intents(self, domain: str) -> List[str]:
        """
        获取特定域的意图列表
        
        参数:
            domain: 域名(例如，"酒店"、"餐厅")
            
        返回:
            该域的意图名称列表
        """
        if domain not in self.domains:
            return []
        return self.domains[domain].get("intents", [])
    
    def get_intent_description(self, domain: str, intent: str) -> Dict[str, Any]:
        """
        获取特定意图的描述和元数据
        
        参数:
            domain: 域名
            intent: 意图名称
            
        返回:
            包含意图描述、关键词等的字典
        """
        if domain not in self.domains:
            return {}
        
        intent_descs = self.domains[domain].get("intent_descriptions", {})
        return intent_descs.get(intent, {})
    
    def is_fallback_intent(self, domain: str, intent: str) -> bool:
        """
        检查意图是否为回退意图(其他)
        
        参数:
            domain: 域名
            intent: 意图名称
            
        返回:
            如果是回退"其他"意图则返回True
        """
        if intent == self.other_intent_name:
            return True
        
        intent_desc = self.get_intent_description(domain, intent)
        return intent_desc.get("is_fallback", False)
    
    def get_intent_keywords(self, domain: str, intent: str) -> List[str]:
        """
        获取意图检测的关键词
        
        参数:
            domain: 域名
            intent: 意图名称
            
        返回:
            关键词列表
        """
        intent_desc = self.get_intent_description(domain, intent)
        return intent_desc.get("keywords", [])
    
    def infer_intent_from_context(
        self,
        domain: str,
        user_utterance: str = "",
        slot_changes: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        从对话上下文推断意图
        
        使用关键词匹配和槽值提示来确定最可能的意图。
        如果找不到清晰的匹配，则回退到"其他"。
        
        参数:
            domain: 域名
            user_utterance: 用户说话文本
            slot_changes: 本轮槽值变化字典
            
        返回:
            推断的意图名称
        """
        if domain not in self.domains:
            return self.other_intent_name
        
        if slot_changes is None:
            slot_changes = {}
        
        # 获取该域的所有意图
        intents = self.get_domain_intents(domain)
        
        # 对每个意图进行评分(暂时排除"其他")
        scores = {}
        for intent in intents:
            if self.is_fallback_intent(domain, intent):
                continue  # 跳过评分中的回退意图
            
            score = 0
            keywords = self.get_intent_keywords(domain, intent)
            
            # 基于关键词匹配的评分
            for keyword in keywords:
                if keyword and keyword in user_utterance:
                    score += 2
            
            # 基于槽值变化的额外评分(如果可用)
            # 这是一个简单的启发式方法，可以进一步改进
            if slot_changes:
                score += 1
            
            scores[intent] = score
        
        # 查找评分最高的意图
        if scores:
            best_intent = max(scores.items(), key=lambda x: x[1])
            if best_intent[1] > 0:
                return best_intent[0]
        
        # 如果没有清晰匹配，回退到"其他"
        return self.other_intent_name
    
    def get_domain_info(self, domain: str) -> Dict[str, Any]:
        """
        获取域的完整信息
        
        参数:
            domain: 域名
            
        返回:
            包含域信息的字典
        """
        return self.domains.get(domain, {})
    
    def get_total_intents_count(self, domain: Optional[str] = None) -> int:
        """
        获取意图总数
        
        参数:
            domain: 如果指定，则仅计算该域的意图数。
                   如果为None，则计算所有域中的总唯一意图数。
        
        返回:
            意图数量
        """
        if domain:
            return len(self.get_domain_intents(domain))
        else:
            # 计算所有域中的总数
            total = 0
            for d in self.domains.values():
                total += len(d.get("intents", []))
            return total


class DomainIntentConfigLoader:
    """
    域意图配置的单例加载器
    
    从JSON文件加载和缓存30域意图配置。
    """
    
    _instance: Optional['DomainIntentConfig'] = None
    _config_path: Optional[str] = None
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """
        加载域意图配置(单例模式)
        
        参数:
            config_path: 配置文件的路径。如果为None，则使用默认路径。
            
        返回:
            DomainIntentConfig实例
        """
        # 确定配置文件路径
        if config_path is None:
            # 默认使用30域配置
            config_path = str(Path(__file__).parent / "configs" / "transfertod_30domains_intents.json")
        
        # 如果路径相同，则返回缓存的实例
        if cls._instance is not None and cls._config_path == config_path:
            return cls._instance
        
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # 创建并缓存实例
        cls._instance = DomainIntentConfig(config_data)
        cls._config_path = config_path
        
        return cls._instance
    
    @classmethod
    def reload(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """
        强制重新加载配置
        
        参数:
            config_path: 配置文件的路径
            
        返回:
            新的DomainIntentConfig实例
        """
        cls._instance = None
        cls._config_path = None
        return cls.load(config_path)


def load_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """
    加载域意图配置的便利函数
    
    参数:
        config_path: 配置文件的路径。如果为None，则使用默认的30域配置。
        
    返回:
        DomainIntentConfig实例
    """
    return DomainIntentConfigLoader.load(config_path)


# 用于向后兼容性
def get_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """
    旧版函数名，用于向后兼容性
    
    参数:
        config_path: 配置文件的路径
        
    返回:
        DomainIntentConfig实例
    """
    return load_domain_intent_config(config_path)
