"""
Domain-specific intent configuration loader for TransferTOD dataset.

This module provides functionality to load and query domain-specific intent configurations.
Unlike the general intent configuration, this one groups intents by domain (酒店, 餐厅, etc.)
and provides domain-specific intent labels.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class DomainIntentConfig:
    """
    Domain-specific intent configuration.
    
    Provides methods to query intents by domain, infer intents from dialogue context,
    and manage domain-specific intent taxonomies.
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        Initialize with parsed configuration data.
        
        Args:
            config_data: Parsed JSON configuration
        """
        self.config_data = config_data
        self.dataset = config_data.get("dataset", "Unknown")
        self.version = config_data.get("version", "1.0")
        self.description = config_data.get("description", "")
        self.domains = config_data.get("domains", {})
        self.default_intent = config_data.get("default_intent", "其他")
        
    def get_all_domains(self) -> List[str]:
        """Get list of all domain names."""
        return list(self.domains.keys())
    
    def get_domain_intents(self, domain: str) -> List[str]:
        """
        Get list of intents for a specific domain.
        
        Args:
            domain: Domain name (e.g., "酒店", "餐厅")
            
        Returns:
            List of intent names for the domain
        """
        if domain not in self.domains:
            return [self.default_intent]
        return self.domains[domain].get("intents", [])
    
    def get_intent_description(self, domain: str, intent: str) -> Dict[str, Any]:
        """
        Get detailed description of an intent.
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            Dictionary with intent description, slot_hints, and keywords
        """
        if domain not in self.domains:
            return {}
        
        intent_descriptions = self.domains[domain].get("intent_descriptions", {})
        return intent_descriptions.get(intent, {})
    
    def get_intent_keywords(self, domain: str, intent: str) -> List[str]:
        """Get keywords associated with an intent."""
        desc = self.get_intent_description(domain, intent)
        return desc.get("keywords", [])
    
    def get_intent_slot_hints(self, domain: str, intent: str) -> List[str]:
        """Get slot hints that suggest this intent."""
        desc = self.get_intent_description(domain, intent)
        return desc.get("slot_hints", [])
    
    def infer_intent_from_context(
        self, 
        domain: str, 
        user_utterance: str = "", 
        slot_changes: Dict[str, Any] = None
    ) -> str:
        """
        Infer intent from dialogue context.
        
        Args:
            domain: Domain name
            user_utterance: User's utterance text
            slot_changes: Dictionary of slots that changed in this turn
            
        Returns:
            Inferred intent name
        """
        if domain not in self.domains:
            return self.default_intent
        
        slot_changes = slot_changes or {}
        intents = self.get_domain_intents(domain)
        
        # Score each intent based on keywords and slot hints
        scores = {}
        for intent in intents:
            score = 0
            
            # Check keywords in user utterance
            keywords = self.get_intent_keywords(domain, intent)
            for keyword in keywords:
                if keyword in user_utterance:
                    score += 2
            
            # Check slot hints
            slot_hints = self.get_intent_slot_hints(domain, intent)
            for slot in slot_changes.keys():
                if slot in slot_hints:
                    score += 1
            
            scores[intent] = score
        
        # Return intent with highest score, or default if all scores are 0
        if not scores or max(scores.values()) == 0:
            return self.default_intent
        
        return max(scores.items(), key=lambda x: x[1])[0]
    
    def get_domain_name_en(self, domain: str) -> str:
        """Get English name of domain."""
        if domain not in self.domains:
            return ""
        return self.domains[domain].get("domain_name_en", "")


class DomainIntentConfigLoader:
    """
    Singleton loader for domain-specific intent configurations.
    """
    
    _instance: Optional[DomainIntentConfig] = None
    _config_path: Optional[str] = None
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """
        Load domain intent configuration.
        
        Args:
            config_path: Path to configuration JSON file.
                        If None, uses default path.
        
        Returns:
            DomainIntentConfig instance
        """
        # Determine config path
        if config_path is None:
            # Default to transfertod_domain_intents.json in configs directory
            current_dir = Path(__file__).parent
            config_path = current_dir / "configs" / "transfertod_domain_intents.json"
        else:
            config_path = Path(config_path)
        
        # Load configuration if not cached or path changed
        if cls._instance is None or cls._config_path != str(config_path):
            if not config_path.exists():
                raise FileNotFoundError(f"Configuration file not found: {config_path}")
            
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
            
            cls._instance = DomainIntentConfig(config_data)
            cls._config_path = str(config_path)
        
        return cls._instance
    
    @classmethod
    def reload(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """Force reload configuration."""
        cls._instance = None
        cls._config_path = None
        return cls.load(config_path)


def load_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """
    Convenience function to load domain intent configuration.
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        DomainIntentConfig instance
    """
    return DomainIntentConfigLoader.load(config_path)


# Example usage
if __name__ == "__main__":
    # Load configuration
    config = load_domain_intent_config()
    
    print(f"Dataset: {config.dataset}")
    print(f"Version: {config.version}")
    print(f"\nDomains: {', '.join(config.get_all_domains())}")
    
    # Get intents for a domain
    hotel_intents = config.get_domain_intents("酒店")
    print(f"\n酒店 intents ({len(hotel_intents)}): {', '.join(hotel_intents)}")
    
    # Infer intent from context
    intent = config.infer_intent_from_context(
        domain="酒店",
        user_utterance="我想预订一个房间",
        slot_changes={"姓名": "张三", "入住日期": "2024-01-01"}
    )
    print(f"\nInferred intent: {intent}")
