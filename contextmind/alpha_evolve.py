"""
AlphaEvolve - 动态调度器模块

该模块实现EvoACE框架的AlphaEvolve调度器，负责：
- 管理动态实验配置
- 实现dynamic_sampling_variance_filter参数化
- 协调ThetaEvolve和ContextMind之间的交互
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from enum import Enum

from .logger import get_logger

logger = get_logger(__name__)


class SamplingStrategy(Enum):
    """采样策略枚举"""
    UNIFORM = "UNIFORM"
    WEIGHTED = "WEIGHTED"
    ADAPTIVE = "ADAPTIVE"
    VARIANCE_BASED = "VARIANCE_BASED"


@dataclass
class ExperimentConfig:
    """实验配置数据类"""
    name: str
    sampling_strategy: str = "ADAPTIVE"
    variance_threshold: float = 0.1
    min_samples: int = 10
    max_samples: int = 1000
    learning_rate: float = 0.01
    exploration_rate: float = 0.1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SchedulerState:
    """调度器状态数据类"""
    current_experiment: Optional[str] = None
    total_iterations: int = 0
    active_experiments: List[str] = field(default_factory=list)
    variance_filter_active: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class AlphaEvolveScheduler:
    """
    AlphaEvolve动态调度器类
    
    负责管理动态实验、采样策略和方差过滤。
    """
    
    def __init__(
        self,
        *,
        default_sampling_strategy: str = "ADAPTIVE",
        dynamic_sampling_variance_filter: Optional[Dict[str, float]] = None,
        enable_auto_tuning: bool = True,
    ):
        """
        初始化AlphaEvolve调度器。
        
        Args:
            default_sampling_strategy: 默认采样策略
            dynamic_sampling_variance_filter: 动态采样方差过滤器配置
            enable_auto_tuning: 是否启用自动调优
        """
        self.default_sampling_strategy = SamplingStrategy[default_sampling_strategy]
        self.enable_auto_tuning = enable_auto_tuning
        
        # 方差过滤器配置
        self.variance_filter_config = dynamic_sampling_variance_filter or {
            'threshold': 0.1,
            'window_size': 20,
            'min_variance': 0.01,
            'max_variance': 0.5,
            'adaptive_threshold': True,
        }
        
        # 实验管理
        self._experiments: Dict[str, ExperimentConfig] = {}
        self._scheduler_state = SchedulerState()
        
        # 采样历史
        self._sampling_history: List[Dict[str, Any]] = []
        
        # 方差统计
        self._variance_stats = {
            'current_variance': 0.0,
            'mean_variance': 0.0,
            'variance_trend': [],
        }
        
        logger.info(f"AlphaEvolve scheduler initialized with strategy={self.default_sampling_strategy.value}")

    def create_experiment(
        self, 
        name: str, 
        config: Optional[ExperimentConfig] = None
    ) -> ExperimentConfig:
        """
        创建新的动态实验。
        
        Args:
            name: 实验名称
            config: 实验配置（可选）
            
        Returns:
            实验配置对象
        """
        if config is None:
            config = ExperimentConfig(
                name=name,
                sampling_strategy=self.default_sampling_strategy.value,
                variance_threshold=self.variance_filter_config['threshold'],
            )
        
        self._experiments[name] = config
        self._scheduler_state.active_experiments.append(name)
        
        logger.info(f"Created experiment: {name} with strategy={config.sampling_strategy}")
        
        return config

    def activate_experiment(self, name: str):
        """激活指定的实验。"""
        if name not in self._experiments:
            raise ValueError(f"Experiment '{name}' not found")
        
        self._scheduler_state.current_experiment = name
        logger.info(f"Activated experiment: {name}")

    def apply_dynamic_sampling_variance_filter(
        self, 
        samples: List[float],
        config_override: Optional[Dict[str, float]] = None
    ) -> List[float]:
        """
        应用动态采样方差过滤器。
        
        Args:
            samples: 样本列表
            config_override: 配置覆盖（可选）
            
        Returns:
            过滤后的样本列表
        """
        if not samples:
            return samples
        
        # 使用覆盖配置或默认配置
        config = config_override or self.variance_filter_config
        
        # 计算当前方差
        mean_val = sum(samples) / len(samples)
        variance = sum((x - mean_val) ** 2 for x in samples) / len(samples)
        
        # 更新方差统计
        self._variance_stats['current_variance'] = variance
        self._variance_stats['variance_trend'].append(variance)
        
        # 计算平均方差
        if self._variance_stats['variance_trend']:
            self._variance_stats['mean_variance'] = (
                sum(self._variance_stats['variance_trend']) / 
                len(self._variance_stats['variance_trend'])
            )
        
        # 确定阈值
        threshold = config.get('threshold', 0.1)
        if config.get('adaptive_threshold', False):
            # 自适应阈值：基于历史方差
            if self._variance_stats['mean_variance'] > 0:
                threshold = max(
                    config.get('min_variance', 0.01),
                    min(config.get('max_variance', 0.5), self._variance_stats['mean_variance'])
                )
        
        # 应用过滤
        if variance > threshold:
            # 方差过大，应用过滤
            self._scheduler_state.variance_filter_active = True
            
            # 使用滑动窗口平滑
            window_size = config.get('window_size', 20)
            filtered_samples = []
            
            for i in range(len(samples)):
                start_idx = max(0, i - window_size // 2)
                end_idx = min(len(samples), i + window_size // 2 + 1)
                window = samples[start_idx:end_idx]
                filtered_samples.append(sum(window) / len(window))
            
            logger.debug(f"Applied variance filter: variance={variance:.4f} > threshold={threshold:.4f}")
            return filtered_samples
        else:
            # 方差在可接受范围内，不过滤
            self._scheduler_state.variance_filter_active = False
            return samples

    def sample_from_distribution(
        self, 
        distribution: List[float],
        strategy: Optional[str] = None
    ) -> float:
        """
        根据策略从分布中采样。
        
        Args:
            distribution: 概率分布
            strategy: 采样策略（可选，默认使用配置的策略）
            
        Returns:
            采样值
        """
        import random
        
        if not distribution:
            return 0.0
        
        # 确定采样策略
        sampling_strategy = (
            SamplingStrategy[strategy] if strategy 
            else self.default_sampling_strategy
        )
        
        if sampling_strategy == SamplingStrategy.UNIFORM:
            # 均匀采样
            sampled_value = random.choice(distribution)
        
        elif sampling_strategy == SamplingStrategy.WEIGHTED:
            # 加权采样（基于值的大小）
            total = sum(distribution)
            if total > 0:
                normalized = [x / total for x in distribution]
                sampled_value = random.choices(distribution, weights=normalized)[0]
            else:
                sampled_value = random.choice(distribution)
        
        elif sampling_strategy == SamplingStrategy.ADAPTIVE:
            # 自适应采样（基于方差）
            variance = self._variance_stats['current_variance']
            if variance > self.variance_filter_config['threshold']:
                # 高方差：倾向于选择中位数附近的值
                sorted_dist = sorted(distribution)
                mid_idx = len(sorted_dist) // 2
                window = max(1, len(sorted_dist) // 4)
                start = max(0, mid_idx - window)
                end = min(len(sorted_dist), mid_idx + window)
                sampled_value = random.choice(sorted_dist[start:end])
            else:
                # 低方差：均匀采样
                sampled_value = random.choice(distribution)
        
        elif sampling_strategy == SamplingStrategy.VARIANCE_BASED:
            # 基于方差的采样
            mean = sum(distribution) / len(distribution)
            variance = sum((x - mean) ** 2 for x in distribution) / len(distribution)
            
            # 倾向于选择接近均值的样本
            if variance > 0:
                weights = [1.0 / (1.0 + abs(x - mean) / variance) for x in distribution]
                sampled_value = random.choices(distribution, weights=weights)[0]
            else:
                sampled_value = random.choice(distribution)
        
        else:
            sampled_value = random.choice(distribution)
        
        # 记录采样历史
        self._sampling_history.append({
            'value': sampled_value,
            'strategy': sampling_strategy.value,
            'variance': self._variance_stats['current_variance'],
            'timestamp': datetime.now().isoformat(),
        })
        
        return sampled_value

    def schedule_iteration(
        self,
        context_engine,
        theta_evaluator,
        iteration_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        调度一次迭代，协调ContextMind和ThetaEvolve。
        
        Args:
            context_engine: ContextEngine实例
            theta_evaluator: ThetaEvolveEvaluator实例
            iteration_callback: 迭代回调函数（可选）
            
        Returns:
            迭代结果字典
        """
        self._scheduler_state.total_iterations += 1
        
        # 获取当前实验配置
        current_exp_name = self._scheduler_state.current_experiment
        if current_exp_name and current_exp_name in self._experiments:
            exp_config = self._experiments[current_exp_name]
        else:
            exp_config = None
        
        # 收集上下文引擎的模块化接口
        modular_interface = context_engine.get_modular_prompt_interface()
        
        # 收集评估器的监控统计
        evaluator_stats = theta_evaluator.get_monitoring_stats()
        
        # 应用方差过滤
        if evaluator_stats['total_evaluations'] > 0:
            recent_rewards = [
                m.normalized_reward 
                for m in theta_evaluator.get_evaluation_history(last_n=50)
            ]
            if recent_rewards:
                filtered_rewards = self.apply_dynamic_sampling_variance_filter(recent_rewards)
                # 更新采样分布
                if filtered_rewards:
                    sampled_reward = self.sample_from_distribution(filtered_rewards)
                else:
                    sampled_reward = 0.0
            else:
                sampled_reward = 0.0
        else:
            sampled_reward = 0.0
        
        # 构建迭代结果
        result = {
            'iteration': self._scheduler_state.total_iterations,
            'experiment': current_exp_name,
            'sampled_reward': sampled_reward,
            'variance': self._variance_stats['current_variance'],
            'variance_filter_active': self._scheduler_state.variance_filter_active,
            'modular_interface': modular_interface,
            'evaluator_stats': evaluator_stats,
            'timestamp': datetime.now().isoformat(),
        }
        
        # 调用迭代回调
        if iteration_callback:
            try:
                iteration_callback(result)
            except Exception as e:
                logger.warning(f"Iteration callback failed: {e}")
        
        logger.debug(f"Scheduled iteration {self._scheduler_state.total_iterations}: "
                    f"sampled_reward={sampled_reward:.3f}, variance={self._variance_stats['current_variance']:.4f}")
        
        return result

    def update_variance_filter_config(self, config: Dict[str, float]):
        """更新方差过滤器配置。"""
        self.variance_filter_config.update(config)
        logger.info(f"Updated variance filter config: {config}")

    def get_experiment_config(self, name: str) -> Optional[ExperimentConfig]:
        """获取实验配置。"""
        return self._experiments.get(name)

    def get_all_experiments(self) -> Dict[str, ExperimentConfig]:
        """获取所有实验配置。"""
        return self._experiments.copy()

    def get_scheduler_state(self) -> SchedulerState:
        """获取调度器状态。"""
        return self._scheduler_state

    def get_variance_stats(self) -> Dict[str, Any]:
        """获取方差统计信息。"""
        return self._variance_stats.copy()

    def get_sampling_history(self, last_n: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        获取采样历史。
        
        Args:
            last_n: 返回最近的N条记录（None表示全部）
            
        Returns:
            采样历史列表
        """
        if last_n is None:
            return self._sampling_history.copy()
        return self._sampling_history[-last_n:]

    def reset(self):
        """重置调度器状态。"""
        self._scheduler_state = SchedulerState()
        self._sampling_history.clear()
        self._variance_stats = {
            'current_variance': 0.0,
            'mean_variance': 0.0,
            'variance_trend': [],
        }
        logger.info("AlphaEvolve scheduler reset")
