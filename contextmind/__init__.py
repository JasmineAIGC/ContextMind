"""
ContextMind - A Multi-Mode Conversational AI Framework

ContextMind provides three advanced modes for dialogue processing:
- DST (Dialogue State Tracking): State extraction and slot filling
- FnCTOD (Function Calling for Task-Oriented Dialogue): Function-based dialogue handling
- Evolve (Evolutionary Context Optimization): Advanced context management with memory evolution

Main components:
- core: Core framework components (config, common utilities)
- modes: Three dialogue processing modes
- scenarios: Scenario definitions and applications
"""

__version__ = "0.2.1"
__author__ = "ContextMind Team"

# Re-export main components for convenient access
from contextmind.config.registry import scenario_registry
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

__all__ = [
    "scenario_registry",
    "DialogueStateTracker",
    "FnCTODTracker",
    "EvolveEngine",
    "create_app_for_scenario",
]
