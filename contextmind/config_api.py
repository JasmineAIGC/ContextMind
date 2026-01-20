"""
ContextMind Configuration API - Simple framework configuration

Provides a simple, unified API for configuring the entire ContextMind framework.
Makes integration easy with sensible defaults and minimal boilerplate.

Example:
    ```python
    from contextmind import ContextMind
    
    # Simple setup with defaults
    cm = ContextMind(llm_client=your_llm)
    
    # Or customize
    cm = ContextMind(
        llm_client=your_llm,
        extractor='llm_entity',
        retriever='hybrid',
        enable_memory=True,
        enable_compression=True,
    )
    
    # Use it
    response = await cm.process(user_input, session_id="user123")
    ```
"""

from typing import Optional, Dict, Any
from .engine import ContextEngine
from .registry import registry
from .core import Message, MessageRole
from .utils import get_logger

logger = get_logger(__name__)


class ContextMind:
    """
    Unified, easy-to-use interface for ContextMind framework
    
    This class provides a simplified API that hides complexity while
    maintaining full configurability. Perfect for quick integration.
    
    Features:
    - Automatic plugin selection with sensible defaults
    - Simple process() method for common use cases
    - Built-in session management
    - Automatic memory extraction and storage
    - Easy plugin swapping
    
    Attributes:
        engine: The underlying ContextEngine instance
        session_id: Current session ID (if set)
    """
    
    def __init__(
        self,
        llm_client: Any,
        extractor: str = 'rule_based',
        retriever: str = 'semantic',
        updater: str = 'simple',
        enable_memory: bool = True,
        enable_compression: bool = True,
        enable_reordering: bool = True,
        enable_postprocessing: bool = True,
        enable_summarization: bool = False,
        **engine_kwargs
    ):
        """
        Initialize ContextMind with configuration
        
        Args:
            llm_client: LLM client for generating responses
            extractor: Extractor plugin name (default: 'rule_based')
            retriever: Retriever plugin name (default: 'semantic')
            updater: Updater plugin name (default: 'simple')
            enable_memory: Enable memory management (default: True)
            enable_compression: Enable context compression (default: True)
            enable_reordering: Enable context reordering (default: True)
            enable_postprocessing: Enable output post-processing (default: True)
            enable_summarization: Enable conversation summarization (default: False)
            **engine_kwargs: Additional arguments for ContextEngine
        """
        logger.info(f"[ContextMind] Initializing with extractor={extractor}, retriever={retriever}")
        
        # Create engine
        self.engine = ContextEngine(llm_client=llm_client, **engine_kwargs)
        
        # Configure plugins
        if enable_memory:
            # Set extractor
            extractor_plugin = registry.get_extractor(extractor)
            if extractor_plugin:
                from .pipeline.extractor import KnowledgeExtractor
                self.engine.extractor = KnowledgeExtractor(strategy=extractor_plugin)
            
            # Set retriever and updater for memory bank
            retriever_plugin = registry.get_retriever(retriever)
            updater_plugin = registry.get_updater(updater)
            if self.engine.memory and retriever_plugin and updater_plugin:
                self.engine.memory.set_retriever(retriever_plugin)
                self.engine.memory.set_updater(updater_plugin)
        
        # Configure pipeline components
        if not enable_compression and hasattr(self.engine, 'compressor'):
            self.engine.compressor = None
        
        if not enable_reordering and hasattr(self.engine, 'reorderer'):
            self.engine.reorderer = None
        
        if enable_postprocessing:
            from .pipeline.postprocessor import PostProcessor
            self.engine.postprocessor = PostProcessor()
        
        if enable_summarization:
            from .pipeline.summarizer import ConversationSummarizer
            self.engine.summarizer = ConversationSummarizer()
        
        self.session_id: Optional[str] = None
        logger.info("[ContextMind] ✓ Initialization complete")
    
    async def process(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        extract_knowledge: bool = True,
    ) -> str:
        """
        Process user input and return AI response
        
        This is a simplified, high-level method that handles the entire
        conversation flow including context optimization, LLM generation,
        and knowledge extraction.
        
        Args:
            user_input: User's message
            session_id: Session ID for conversation tracking
            system_prompt: Optional system prompt override
            extract_knowledge: Whether to extract knowledge from the conversation
            
        Returns:
            AI's response text
        """
        # Use provided session_id or stored one
        sid = session_id or self.session_id
        if sid:
            self.session_id = sid
        
        # Create user message
        user_msg = Message(role=MessageRole.USER, content=user_input)
        
        # Get conversation history
        messages = []
        if sid and self.engine.session:
            messages = await self.engine.session.get_messages(sid)
        
        # Add current message
        messages.append(user_msg)
        
        # Optimize context
        optimized = await self.engine.optimize_context(
            messages=messages,
            query=user_input,
            session_id=sid,
            system_prompt=system_prompt,
        )
        
        # Generate response using LLM client
        # Note: This is a simplified example. In production, you should:
        # 1. Build the complete prompt from optimized context
        # 2. Call your LLM client with the prompt
        # 3. Handle the response appropriately
        
        # Example LLM call (you'll need to adapt this to your LLM client):
        # response_text = await self.engine.llm_client.generate(optimized.context, user_input)
        
        # For now, return a placeholder that shows what was processed
        logger.warning(
            "[ContextMind] process() method uses placeholder response. "
            "Override this method or call engine.optimize_context() + your LLM directly."
        )
        response_text = (
            f"[ContextMind processed your input with {len(optimized.context)} context items. "
            f"Please implement actual LLM call in your application.]"
        )
        
        # Create assistant message
        assistant_msg = Message(role=MessageRole.ASSISTANT, content=response_text)
        
        # Save to session
        if sid and self.engine.session:
            await self.engine.session.add_message(sid, user_msg)
            await self.engine.session.add_message(sid, assistant_msg)
        
        # Extract knowledge if enabled
        if extract_knowledge and self.engine.extractor:
            knowledge = await self.engine.extractor.extract([user_msg, assistant_msg])
            if knowledge and self.engine.memory:
                for k in knowledge:
                    await self.engine.memory.add(k)
                logger.info(f"[ContextMind] Extracted and stored {len(knowledge)} knowledge items")
        
        return response_text
    
    def set_extractor(self, extractor_name: str):
        """Change the extractor plugin"""
        extractor = registry.get_extractor(extractor_name)
        if extractor:
            from .pipeline.extractor import KnowledgeExtractor
            self.engine.extractor = KnowledgeExtractor(strategy=extractor)
            logger.info(f"[ContextMind] Switched to extractor: {extractor_name}")
    
    def set_retriever(self, retriever_name: str):
        """Change the retriever plugin"""
        retriever = registry.get_retriever(retriever_name)
        if retriever and self.engine.memory:
            self.engine.memory.set_retriever(retriever)
            logger.info(f"[ContextMind] Switched to retriever: {retriever_name}")
    
    def set_updater(self, updater_name: str):
        """Change the updater plugin"""
        updater = registry.get_updater(updater_name)
        if updater and self.engine.memory:
            self.engine.memory.set_updater(updater)
            logger.info(f"[ContextMind] Switched to updater: {updater_name}")
    
    def list_available_plugins(self) -> Dict[str, list]:
        """List all available plugins"""
        return registry.get_all_plugins()
