"""
Domain-specific Intent Configuration for TransferTOD Dataset

Supports 30 domains with comprehensive intent taxonomy.
Special handling for "其他" (Other) intent as a fallback category.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any


class DomainIntentConfig:
    """
    Domain-specific intent configuration
    
    Manages intent definitions for 30 TransferTOD domains with special handling
    for the "其他" (Other) intent.
    """
    
    def __init__(self, config_data: Dict[str, Any]):
        """
        Initialize domain intent configuration
        
        Args:
            config_data: Configuration dictionary loaded from JSON
        """
        self.dataset = config_data.get("dataset", "TransferTOD")
        self.version = config_data.get("version", "3.0")
        self.description = config_data.get("description", "")
        self.total_domains = config_data.get("total_domains", 30)
        self.metadata = config_data.get("metadata", {})
        self.domains = config_data.get("domains", {})
        
        # Extract special "其他" intent handling info
        self.other_intent_name = self.metadata.get("other_intent_name", "其他")
        self.other_intent_description = self.metadata.get("other_intent_description", "")
        self.other_intent_evaluation = self.metadata.get("other_intent_evaluation", "special_handling")
    
    def get_all_domains(self) -> List[str]:
        """
        Get list of all domain names
        
        Returns:
            List of domain names (Chinese)
        """
        return list(self.domains.keys())
    
    def get_domain_intents(self, domain: str) -> List[str]:
        """
        Get list of intents for a specific domain
        
        Args:
            domain: Domain name (e.g., "酒店", "餐厅")
            
        Returns:
            List of intent names for the domain
        """
        if domain not in self.domains:
            return []
        return self.domains[domain].get("intents", [])
    
    def get_intent_description(self, domain: str, intent: str) -> Dict[str, Any]:
        """
        Get description and metadata for a specific intent
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            Dictionary with intent description, keywords, etc.
        """
        if domain not in self.domains:
            return {}
        
        intent_descs = self.domains[domain].get("intent_descriptions", {})
        return intent_descs.get(intent, {})
    
    def is_fallback_intent(self, domain: str, intent: str) -> bool:
        """
        Check if an intent is a fallback intent (其他)
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            True if this is the fallback "其他" intent
        """
        if intent == self.other_intent_name:
            return True
        
        intent_desc = self.get_intent_description(domain, intent)
        return intent_desc.get("is_fallback", False)
    
    def get_intent_keywords(self, domain: str, intent: str) -> List[str]:
        """
        Get keywords for intent detection
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            List of keywords
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
        Infer intent from dialogue context
        
        Uses keyword matching and slot hints to determine the most likely intent.
        Falls back to "其他" if no clear match is found.
        
        Args:
            domain: Domain name
            user_utterance: User's utterance text
            slot_changes: Dictionary of slot changes in this turn
            
        Returns:
            Inferred intent name
        """
        if domain not in self.domains:
            return self.other_intent_name
        
        if slot_changes is None:
            slot_changes = {}
        
        # Get all intents for this domain
        intents = self.get_domain_intents(domain)
        
        # Score each intent (excluding "其他" for now)
        scores = {}
        for intent in intents:
            if self.is_fallback_intent(domain, intent):
                continue  # Skip fallback intent in scoring
            
            score = 0
            keywords = self.get_intent_keywords(domain, intent)
            
            # Score based on keyword matches
            for keyword in keywords:
                if keyword and keyword in user_utterance:
                    score += 2
            
            # Additional scoring based on slot changes (if available)
            # This is a simple heuristic and can be improved
            if slot_changes:
                score += 1
            
            scores[intent] = score
        
        # Find intent with highest score
        if scores:
            best_intent = max(scores.items(), key=lambda x: x[1])
            if best_intent[1] > 0:
                return best_intent[0]
        
        # Fall back to "其他" if no clear match
        return self.other_intent_name
    
    def get_domain_info(self, domain: str) -> Dict[str, Any]:
        """
        Get complete information about a domain
        
        Args:
            domain: Domain name
            
        Returns:
            Dictionary with domain information
        """
        return self.domains.get(domain, {})
    
    def get_total_intents_count(self, domain: Optional[str] = None) -> int:
        """
        Get total number of intents
        
        Args:
            domain: If specified, count intents for that domain only.
                   If None, count total unique intents across all domains.
        
        Returns:
            Number of intents
        """
        if domain:
            return len(self.get_domain_intents(domain))
        else:
            # Count total across all domains
            total = 0
            for d in self.domains.values():
                total += len(d.get("intents", []))
            return total


class DomainIntentConfigLoader:
    """
    Singleton loader for domain intent configuration
    
    Loads and caches the 30-domain intent configuration from JSON file.
    """
    
    _instance: Optional['DomainIntentConfig'] = None
    _config_path: Optional[str] = None
    
    @classmethod
    def load(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """
        Load domain intent configuration (singleton pattern)
        
        Args:
            config_path: Path to configuration file. If None, uses default.
            
        Returns:
            DomainIntentConfig instance
        """
        # Determine config path
        if config_path is None:
            # Default to 30-domain configuration
            config_path = str(Path(__file__).parent / "configs" / "transfertod_30domains_intents.json")
        
        # Return cached instance if same config path
        if cls._instance is not None and cls._config_path == config_path:
            return cls._instance
        
        # Load configuration
        with open(config_path, 'r', encoding='utf-8') as f:
            config_data = json.load(f)
        
        # Create and cache instance
        cls._instance = DomainIntentConfig(config_data)
        cls._config_path = config_path
        
        return cls._instance
    
    @classmethod
    def reload(cls, config_path: Optional[str] = None) -> DomainIntentConfig:
        """
        Force reload of configuration
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Fresh DomainIntentConfig instance
        """
        cls._instance = None
        cls._config_path = None
        return cls.load(config_path)


def load_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """
    Convenience function to load domain intent configuration
    
    Args:
        config_path: Path to configuration file. If None, uses default 30-domain config.
        
    Returns:
        DomainIntentConfig instance
    """
    return DomainIntentConfigLoader.load(config_path)


# For backward compatibility
def get_domain_intent_config(config_path: Optional[str] = None) -> DomainIntentConfig:
    """
    Legacy function name for backward compatibility
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        DomainIntentConfig instance
    """
    return load_domain_intent_config(config_path)
