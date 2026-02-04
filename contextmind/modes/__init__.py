"""
Dialogue processing modes for ContextMind

Three modes available:
- dst: Dialogue State Tracking mode
- fnctod: Function Calling for Task-Oriented Dialogue mode
- evolve: Evolutionary Context Optimization mode
"""

# Import mode entry points
from contextmind.modes.dst import DialogueStateTracker
from contextmind.modes.fnctod import FnCTODTracker
from contextmind.modes.evolve import create_app_for_scenario, EvolveEngine

__all__ = [
    "DialogueStateTracker",
    "FnCTODTracker",
    "EvolveEngine",
    "create_app_for_scenario",
]
