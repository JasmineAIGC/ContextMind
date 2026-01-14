"""
Context data structures for passing information between pipeline steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class ContextData:
    """
    Immutable data container for context information.
    
    This class represents a single piece of context data with metadata.
    """
    
    content: str
    source: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    score: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "content": self.content,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "score": self.score,
        }


class Context:
    """
    Central context object that flows through the pipeline.
    
    This object holds all state and data as it passes through each step.
    It provides a clean interface for steps to read and write data.
    """
    
    def __init__(self, user_input: str, **initial_data):
        """
        Initialize context with user input.
        
        Args:
            user_input: The user's input text
            **initial_data: Additional initial context data
        """
        self._data: Dict[str, Any] = {
            "user_input": user_input,
            "created_at": datetime.now(),
            **initial_data
        }
        self._history: List[Dict[str, Any]] = []
        self._metadata: Dict[str, Any] = {}
    
    def set(self, key: str, value: Any) -> None:
        """
        Set a value in the context.
        
        Args:
            key: The key to set
            value: The value to set
        """
        self._data[key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a value from the context.
        
        Args:
            key: The key to retrieve
            default: Default value if key doesn't exist
            
        Returns:
            The value associated with the key, or default
        """
        return self._data.get(key, default)
    
    def has(self, key: str) -> bool:
        """
        Check if a key exists in the context.
        
        Args:
            key: The key to check
            
        Returns:
            True if key exists, False otherwise
        """
        return key in self._data
    
    def update(self, data: Dict[str, Any]) -> None:
        """
        Update multiple values at once.
        
        Args:
            data: Dictionary of key-value pairs to update
        """
        self._data.update(data)
    
    def add_context_data(self, data: ContextData) -> None:
        """
        Add a ContextData object to the context.
        
        Args:
            data: The ContextData to add
        """
        key = f"context_data_{data.source}"
        if key not in self._data:
            self._data[key] = []
        self._data[key].append(data)
    
    def get_context_data(self, source: Optional[str] = None) -> List[ContextData]:
        """
        Get context data, optionally filtered by source.
        
        Args:
            source: Optional source filter
            
        Returns:
            List of ContextData objects
        """
        if source:
            return self._data.get(f"context_data_{source}", [])
        
        # Return all context data
        result = []
        for key, value in self._data.items():
            if key.startswith("context_data_") and isinstance(value, list):
                result.extend(value)
        return result
    
    def set_metadata(self, key: str, value: Any) -> None:
        """
        Set metadata (doesn't flow through pipeline).
        
        Args:
            key: Metadata key
            value: Metadata value
        """
        self._metadata[key] = value
    
    def get_metadata(self, key: str, default: Any = None) -> Any:
        """
        Get metadata value.
        
        Args:
            key: Metadata key
            default: Default value
            
        Returns:
            Metadata value or default
        """
        return self._metadata.get(key, default)
    
    def record_step(self, step_name: str, data: Dict[str, Any]) -> None:
        """
        Record step execution for debugging/monitoring.
        
        Args:
            step_name: Name of the step
            data: Data to record
        """
        self._history.append({
            "step": step_name,
            "timestamp": datetime.now(),
            "data": data
        })
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get execution history.
        
        Returns:
            List of historical step records
        """
        return self._history.copy()
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert context to dictionary.
        
        Returns:
            Dictionary representation of context
        """
        return {
            "data": self._data.copy(),
            "metadata": self._metadata.copy(),
            "history": self._history.copy()
        }
    
    @property
    def user_input(self) -> str:
        """Get the user input."""
        return self._data.get("user_input", "")
    
    @property
    def response(self) -> Optional[str]:
        """Get the generated response."""
        return self._data.get("response")
    
    def __repr__(self) -> str:
        """String representation."""
        return f"Context(keys={list(self._data.keys())})"
