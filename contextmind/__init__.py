"""
ContextMind - 基于 ADK 的上下文工程框架

提供多轮对话的短期记忆（Session）和长期记忆（Memory）管理。
集成EvoACE框架，支持强化学习优化。
"""

from .client import Client, ClientConfig
from .engine import ContextEngine, ContextTurnResult, IntegratedKnowledge
from .logger import get_logger, setup_logging, ContextMindLogger
from .theta_evolve import ThetaEvolveEvaluator, EvaluationMetrics, RLOptimizerInput, RewardProcessType
from .alpha_evolve import AlphaEvolveScheduler, ExperimentConfig, SchedulerState, SamplingStrategy
from .testing_hooks import EvoACETestingHooks, TestResult, IntegrationTestReport

__all__ = [
    "Client",
    "ClientConfig",
    "ContextEngine",
    "ContextTurnResult",
    "IntegratedKnowledge",
    "get_logger",
    "setup_logging",
    "ContextMindLogger",
    "ThetaEvolveEvaluator",
    "EvaluationMetrics",
    "RLOptimizerInput",
    "RewardProcessType",
    "AlphaEvolveScheduler",
    "ExperimentConfig",
    "SchedulerState",
    "SamplingStrategy",
    "EvoACETestingHooks",
    "TestResult",
    "IntegrationTestReport",
]
