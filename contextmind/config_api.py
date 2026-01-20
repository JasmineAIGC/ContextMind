"""
ContextMind Configuration API - Simple framework configuration

Provides a simple, unified API for configuring the entire ContextMind framework.
Makes integration easy with sensible defaults and minimal boilerplate.

ContextMind focuses on context engineering (Steps 1-4 + Step 6):
- Steps 1-4: Build efficient prompt (context engineering core) - INSIDE ContextMind
- Step 5: LLM invocation (with KV cache) - EXTERNAL (user's LLM)
- Step 6: Output post-processing - INSIDE ContextMind

Example:
    ```python
    from contextmind import ContextMind
    
    # Setup
    cm = ContextMind()
    
    # Steps 1-4: ContextMind builds optimized context
    context = await cm.prepare_context("Hello", session_id="user123")
    
    # Step 5: User invokes EXTERNAL LLM (vLLM, OpenAI, etc.)
    llm_output = await your_llm.generate(
        system_prompt=context['system_prompt'],
        messages=context['optimized_context'],
        user_input=context['user_input']
    )
    
    # Step 6: ContextMind post-processes
    final_response = await cm.post_process(
        llm_output,
        session_id="user123"
    )
    ```
"""

from typing import Optional, Dict, Any
from .engine import ContextEngine
from .registry import registry
from .models import Message, MessageRole, get_logger

logger = get_logger(__name__)


class ContextMind:
    """
    Unified interface for ContextMind context engineering framework
    
    ContextMind focuses on context engineering (Steps 1-4 + Step 6):
    - Steps 1-4: Build efficient prompt (InputPreprocessor → Retriever → Compressor → Reorderer)
    - Step 5: LLM invocation is EXTERNAL (user calls their own LLM)
    - Step 6: Post-process LLM output (PostProcessor)
    
    This design keeps ContextMind universal - works with ANY LLM provider.
    
    Features:
    - Automatic plugin selection with sensible defaults
    - prepare_context() for Steps 1-4 (returns optimized context)
    - post_process() for Step 6 (processes LLM output)
    - Built-in session management
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
    
    async def prepare_context(
        self,
        user_input: str,
        session_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Steps 1-4: Build optimized context for LLM invocation
        
        This method runs the context engineering pipeline:
        1. InputPreprocessor - clean and normalize input
        2. ContextRetriever + MemoryBank - retrieve relevant context
        3. ContextCompressor - compress to fit context window
        4. ContextReorderer - reorder for optimal attention
        
        After this, user should invoke their LLM (Step 5) and then call
        post_process() on the LLM output (Step 6).
        
        Args:
            user_input: User's message
            session_id: Session ID for conversation tracking
            system_prompt: Optional system prompt override
            
        Returns:
            Dict containing:
                - 'optimized_context': List of context items ready for LLM
                - 'system_prompt': str - System instructions
                - 'user_input': str - Processed user input
                - 'messages': List - Full message history
                - 'metadata': Dict - Additional metadata
        
        Example:
            ```python
            cm = ContextMind()
            # Steps 1-4: ContextMind builds optimized context
            context = await cm.prepare_context("Hello", session_id="user123")
            
            # Step 5: User invokes EXTERNAL LLM
            llm_output = await your_llm.generate(
                system_prompt=context['system_prompt'],
                messages=context['optimized_context'],
                user_input=context['user_input']
            )
            
            # Step 6: ContextMind post-processes
            final = cm.post_process(llm_output, session_id="user123")
            ```
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
        
        # Steps 1-4: Optimize context (core context engineering)
        optimized = await self.engine.optimize_context(
            messages=messages,
            query=user_input,
            session_id=sid,
            system_prompt=system_prompt,
        )
        
        logger.info(
            f"[ContextMind] ✓ Context optimized: {len(optimized.context)} items ready for LLM"
        )
        
        # Return structured context for external LLM invocation
        return {
            'optimized_context': optimized.context,
            'system_prompt': system_prompt or "",
            'user_input': user_input,
            'messages': messages,
            'metadata': {
                'session_id': sid,
                'context_items': len(optimized.context),
                'compression_applied': hasattr(optimized, 'compression_ratio'),
            }
        }
    
    async def post_process(
        self,
        llm_output: str,
        session_id: Optional[str] = None,
        extract_knowledge: bool = True,
    ) -> str:
        """
        Step 6: Post-process LLM output and update memory
        
        Applies PostProcessor to ensure output quality:
        - Format validation and correction
        - Remove duplicates  
        - Citation generation (if applicable)
        - Consistency checks
        
        Also handles knowledge extraction and session updates.
        
        Args:
            llm_output: Raw output from LLM
            session_id: Session ID for conversation tracking
            extract_knowledge: Whether to extract knowledge from the conversation
            
        Returns:
            Final processed response ready for user
        
        Example:
            ```python
            # After calling LLM
            final_response = await cm.post_process(
                llm_output,
                session_id="user123",
                extract_knowledge=True
            )
            ```
        """
        logger.info(f"[ContextMind] Step 6: Post-processing LLM output ({len(llm_output)} chars)...")
        
        # Apply PostProcessor if available
        processed_output = llm_output
        if hasattr(self.engine, 'postprocessor') and self.engine.postprocessor:
            processed_output = self.engine.postprocessor.process(llm_output)
            logger.debug(f"[ContextMind] PostProcessor applied")
        
        # Use provided session_id or stored one
        sid = session_id or self.session_id
        
        # Create assistant message for session storage
        if sid and self.engine.session:
            assistant_msg = Message(role=MessageRole.ASSISTANT, content=processed_output)
            await self.engine.session.add_message(sid, assistant_msg)
            logger.debug(f"[ContextMind] Response saved to session: {sid}")
        
        # Extract knowledge if enabled
        if extract_knowledge and self.engine.extractor and self.engine.memory:
            # Get last user message from session
            if sid and self.engine.session:
                recent_messages = await self.engine.session.get_messages(sid, limit=2)
                if len(recent_messages) >= 2:
                    user_msg = recent_messages[-2]
                    assistant_msg = Message(role=MessageRole.ASSISTANT, content=processed_output)
                    
                    knowledge = await self.engine.extractor.extract([user_msg, assistant_msg])
                    if knowledge:
                        for k in knowledge:
                            await self.engine.memory.add(k)
                        logger.info(f"[ContextMind] ✓ Extracted and stored {len(knowledge)} knowledge items")
        
        logger.info(f"[ContextMind] ✓ Post-processing complete")
        return processed_output
    
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
