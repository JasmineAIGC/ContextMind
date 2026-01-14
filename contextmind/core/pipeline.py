"""
Pipeline system for orchestrating context optimization steps.
"""

from __future__ import annotations

from typing import List, Optional, Dict, Any, Callable
import time
import asyncio
from datetime import datetime

from .context import Context
from .exceptions import PipelineError, StepError
from .registry import get_step_registry


class Pipeline:
    """
    Main pipeline class that orchestrates step execution.
    
    A pipeline is a sequence of steps that process a context object.
    Each step can read from and write to the context.
    """
    
    def __init__(
        self,
        name: str = "default",
        steps: Optional[List[tuple[str, Any]]] = None,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize pipeline.
        
        Args:
            name: Pipeline name
            steps: List of (step_name, step_instance) tuples
            config: Global pipeline configuration
        """
        self.name = name
        self._steps: List[tuple[str, Any]] = steps or []
        self.config = config or {}
        self._hooks: Dict[str, List[Callable]] = {
            "before_pipeline": [],
            "after_pipeline": [],
            "before_step": [],
            "after_step": [],
            "on_error": []
        }
    
    def add_step(self, name: str, step: Any, position: Optional[int] = None) -> Pipeline:
        """
        Add a step to the pipeline.
        
        Args:
            name: Step identifier
            step: Step instance
            position: Optional position to insert at (default: append)
            
        Returns:
            Self for chaining
        """
        if position is None:
            self._steps.append((name, step))
        else:
            self._steps.insert(position, (name, step))
        return self
    
    def remove_step(self, name: str) -> Pipeline:
        """
        Remove a step by name.
        
        Args:
            name: Step identifier
            
        Returns:
            Self for chaining
        """
        self._steps = [(n, s) for n, s in self._steps if n != name]
        return self
    
    def replace_step(self, name: str, new_step: Any) -> Pipeline:
        """
        Replace a step with a new instance.
        
        Args:
            name: Step identifier to replace
            new_step: New step instance
            
        Returns:
            Self for chaining
        """
        for i, (n, s) in enumerate(self._steps):
            if n == name:
                self._steps[i] = (name, new_step)
                break
        return self
    
    def get_step(self, name: str) -> Optional[Any]:
        """
        Get a step by name.
        
        Args:
            name: Step identifier
            
        Returns:
            Step instance or None
        """
        for n, s in self._steps:
            if n == name:
                return s
        return None
    
    def list_steps(self) -> List[str]:
        """
        List all step names in order.
        
        Returns:
            List of step names
        """
        return [name for name, _ in self._steps]
    
    def add_hook(self, event: str, callback: Callable) -> Pipeline:
        """
        Add a hook for pipeline events.
        
        Args:
            event: Event name (before_pipeline, after_pipeline, before_step, after_step, on_error)
            callback: Callback function
            
        Returns:
            Self for chaining
        """
        if event in self._hooks:
            self._hooks[event].append(callback)
        return self
    
    async def execute(self, context: Context) -> Context:
        """
        Execute the pipeline.
        
        Args:
            context: Context object to process
            
        Returns:
            Processed context
            
        Raises:
            PipelineError: If pipeline execution fails
        """
        start_time = time.time()
        
        try:
            # Run before_pipeline hooks
            await self._run_hooks("before_pipeline", context)
            
            # Execute each step
            for step_name, step in self._steps:
                try:
                    # Run before_step hooks
                    await self._run_hooks("before_step", context, step_name, step)
                    
                    step_start = time.time()
                    
                    # Execute step
                    if asyncio.iscoroutinefunction(step.execute):
                        context = await step.execute(context)
                    else:
                        context = step.execute(context)
                    
                    step_duration = time.time() - step_start
                    
                    # Record step execution
                    context.record_step(step_name, {
                        "duration": step_duration,
                        "timestamp": datetime.now()
                    })
                    
                    # Run after_step hooks
                    await self._run_hooks("after_step", context, step_name, step)
                    
                except Exception as e:
                    # Run error hooks
                    await self._run_hooks("on_error", context, step_name, e)
                    
                    # Decide whether to continue or fail
                    if self.config.get("strict_mode", True):
                        raise StepError(
                            f"Step '{step_name}' failed: {str(e)}"
                        ) from e
                    else:
                        # Log and continue
                        context.set_metadata(f"error_{step_name}", str(e))
            
            # Run after_pipeline hooks
            await self._run_hooks("after_pipeline", context)
            
            # Set pipeline metadata
            total_duration = time.time() - start_time
            context.set_metadata("pipeline_duration", total_duration)
            context.set_metadata("pipeline_name", self.name)
            
            return context
            
        except Exception as e:
            if isinstance(e, (StepError, PipelineError)):
                raise
            raise PipelineError(f"Pipeline execution failed: {str(e)}") from e
    
    async def _run_hooks(self, event: str, context: Context, *args):
        """Run hooks for an event."""
        for hook in self._hooks.get(event, []):
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(context, *args)
                else:
                    hook(context, *args)
            except Exception as e:
                # Hooks shouldn't break the pipeline
                context.set_metadata(f"hook_error_{event}", str(e))
    
    def __repr__(self) -> str:
        """String representation."""
        steps = ", ".join(name for name, _ in self._steps)
        return f"Pipeline(name='{self.name}', steps=[{steps}])"


class PipelineBuilder:
    """
    Builder for constructing pipelines declaratively.
    
    This class provides a fluent interface for building pipelines
    with validation and configuration management.
    """
    
    def __init__(self, name: str = "default"):
        """
        Initialize builder.
        
        Args:
            name: Pipeline name
        """
        self._name = name
        self._steps: List[tuple[str, Any]] = []
        self._config: Dict[str, Any] = {}
        self._step_registry = get_step_registry()
    
    def add_step(
        self,
        step_type: str,
        name: Optional[str] = None,
        **step_config
    ) -> PipelineBuilder:
        """
        Add a step by type.
        
        Args:
            step_type: Registered step type
            name: Optional custom name (defaults to step_type)
            **step_config: Configuration for the step
            
        Returns:
            Self for chaining
        """
        step_name = name or step_type
        step = self._step_registry.create_step(step_type, **step_config)
        self._steps.append((step_name, step))
        return self
    
    def add_custom_step(self, name: str, step: Any) -> PipelineBuilder:
        """
        Add a custom step instance.
        
        Args:
            name: Step name
            step: Step instance
            
        Returns:
            Self for chaining
        """
        self._steps.append((name, step))
        return self
    
    def set_config(self, **config) -> PipelineBuilder:
        """
        Set pipeline configuration.
        
        Args:
            **config: Configuration key-value pairs
            
        Returns:
            Self for chaining
        """
        self._config.update(config)
        return self
    
    def build(self) -> Pipeline:
        """
        Build the pipeline.
        
        Returns:
            Constructed Pipeline instance
        """
        return Pipeline(
            name=self._name,
            steps=self._steps.copy(),
            config=self._config.copy()
        )
    
    @classmethod
    def from_config(cls, config: Dict[str, Any]) -> Pipeline:
        """
        Build pipeline from configuration dictionary.
        
        Args:
            config: Pipeline configuration
            
        Returns:
            Constructed Pipeline instance
            
        Example config:
            {
                "name": "my_pipeline",
                "config": {"strict_mode": False},
                "steps": [
                    {"type": "validation", "name": "input_val"},
                    {"type": "collection", "name": "collect", "max_items": 10}
                ]
            }
        """
        builder = cls(config.get("name", "default"))
        
        if "config" in config:
            builder.set_config(**config["config"])
        
        for step_conf in config.get("steps", []):
            step_type = step_conf["type"]
            step_name = step_conf.get("name")
            step_params = {k: v for k, v in step_conf.items() 
                          if k not in ["type", "name"]}
            builder.add_step(step_type, step_name, **step_params)
        
        return builder.build()
