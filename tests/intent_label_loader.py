"""
Intent Label Loader for TransferTOD Dataset

Loads and provides access to intent labels from intent_labels_30_domains_Version2.json
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from contextmind.infra.logger import get_logger

logger = get_logger(__name__)


class IntentLabelLoader:
    """
    Loader for intent labels configuration from JSON file
    
    Provides access to domain-specific intent labels, descriptions, and keywords
    for use in DST prompting and evaluation.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the intent label loader
        
        Args:
            config_path: Path to the intent labels JSON file
        """
        if config_path is None:
            # Default path relative to this file
            config_path = Path(__file__).parent / "configs" / "intent_labels_30_domains_Version2.json"
        
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.domains = self.config.get("domains", {})
        self.metadata = self.config.get("metadata", {})
        
        logger.info(f"Loaded intent labels for {len(self.domains)} domains")
    
    def _load_config(self) -> Dict:
        """Load the intent labels configuration from JSON file"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.error(f"Intent labels file not found: {self.config_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse intent labels JSON: {e}")
            raise
    
    def get_domain_intents(self, domain: str) -> List[str]:
        """
        Get the list of intents for a specific domain
        
        Args:
            domain: Domain name (Chinese, e.g., "酒店", "景点")
            
        Returns:
            List of intent names for the domain
        """
        if domain not in self.domains:
            logger.warning(f"Domain '{domain}' not found in intent labels")
            return []
        
        return self.domains[domain].get("intents", [])
    
    def get_intent_description(self, domain: str, intent: str) -> Dict:
        """
        Get the description and metadata for a specific intent
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            Dictionary with description, keywords, etc.
        """
        if domain not in self.domains:
            return {}
        
        intent_descriptions = self.domains[domain].get("intent_descriptions", {})
        return intent_descriptions.get(intent, {})
    
    def get_intent_keywords(self, domain: str, intent: str) -> List[str]:
        """
        Get keywords for a specific intent
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            List of keywords for the intent
        """
        desc = self.get_intent_description(domain, intent)
        return desc.get("keywords", [])
    
    def is_fallback_intent(self, domain: str, intent: str) -> bool:
        """
        Check if an intent is a fallback intent (e.g., "其他")
        
        Args:
            domain: Domain name
            intent: Intent name
            
        Returns:
            True if this is a fallback intent
        """
        desc = self.get_intent_description(domain, intent)
        return desc.get("is_fallback", False)
    
    def get_fallback_intent_name(self) -> str:
        """
        Get the name of the fallback intent
        
        Returns:
            Fallback intent name (default: "其他")
        """
        return self.metadata.get("other_intent_name", "其他")
    
    def get_all_domains(self) -> List[str]:
        """
        Get list of all available domains
        
        Returns:
            List of domain names
        """
        return list(self.domains.keys())
    
    def get_prompt_intent_list(self, domain: str) -> str:
        """
        Generate formatted intent list for use in prompts
        
        Args:
            domain: Domain name
            
        Returns:
            Formatted string listing all intents with descriptions
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
        Get the domain code for a specific domain
        
        Args:
            domain: Domain name
            
        Returns:
            Domain code (e.g., "1-hotel") or None if not found
        """
        if domain not in self.domains:
            return None
        return self.domains[domain].get("domain_code")
    
    def get_domain_en(self, domain: str) -> Optional[str]:
        """
        Get the English name for a specific domain
        
        Args:
            domain: Domain name (Chinese)
            
        Returns:
            English domain name or None if not found
        """
        if domain not in self.domains:
            return None
        return self.domains[domain].get("domain_en")


# Singleton instance for easy access
_intent_label_loader = None


def get_intent_label_loader(config_path: Optional[str] = None) -> IntentLabelLoader:
    """
    Get the singleton IntentLabelLoader instance
    
    Args:
        config_path: Optional path to config file (only used on first call)
        
    Returns:
        IntentLabelLoader instance
    """
    global _intent_label_loader
    if _intent_label_loader is None:
        _intent_label_loader = IntentLabelLoader(config_path)
    return _intent_label_loader
