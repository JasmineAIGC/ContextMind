"""
Common utilities and components for ContextMind

This module contains:
- prompts: System prompts for different scenarios
- ui_components: Gradio UI components and styling
- utils: General-purpose utilities (logger, LLM client, embeddings, data models)
"""

# Import submodules lazily to avoid circular imports and missing dependencies
__all__ = ["prompts", "ui_components", "utils"]
