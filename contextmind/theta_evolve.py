"""
ThetaEvolve - RL优化评估器模块

该模块实现EvoACE框架的ThetaEvolve评估器，负责：
- 集成ContextMind生成的奖励信号
- 提供RL优化器输入和回调
- 监控来自ContextMind的模块化输入
- 支持RL-NORMALIZED奖励处理类型
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List, Optional, Any
from enum import Enum

from .logger import get_logger

logger = get_logger(__name__)


class RewardProcessType(Enum):
    """奖励处理类型枚举"""
    RAW = "RAW"
    NORMALIZED = "NORMALIZED"
    RL_NORMALIZED = "RL-NORMALIZED"
    ADAPTIVE = "ADAPTIVE"


@dataclass
class EvaluationMetrics:
    """评估指标数据类"""
    reward: float
    normalized_reward: float
    context_quality: float
    response_quality: float
    learning_progress: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RLOptimizerInput:
    """RL优化器输入数据类"""
    state: Dict[str, Any]
    action: str
    reward: float
    next_state: Dict[str, Any]
    done: bool
    info: Dict[str, Any] = field(default_factory=dict)


class ThetaEvolveEvaluator:
    """
    ThetaEvolve评估器类
    
    负责评估ContextMind生成的结果并提供RL优化器所需的输入。
    支持多种奖励处理类型和监控模块化输入。
    """
    
    def __init__(
        self,
        *,
        reward_process_type: str = "RL-NORMALIZED",
        enable_monitoring: bool = True,
        reward_hooks: Optional[List[Callable]] = None,
        normalization_params: Optional[Dict[str, float]] = None,
    ):
        """
        初始化ThetaEvolve评估器。
        
        Args:
            reward_process_type: 奖励处理类型 ("RAW", "NORMALIZED", "RL-NORMALIZED", "ADAPTIVE")
            enable_monitoring: 是否启用监控
            reward_hooks: 奖励钩子函数列表
            normalization_params: 归一化参数字典
        """
        self.reward_process_type = RewardProcessType[reward_process_type.replace("-", "_")]
        self.enable_monitoring = enable_monitoring
        self.reward_hooks = reward_hooks or []
        self.normalization_params = normalization_params or {
            'min_reward': 0.0,
            'max_reward': 1.0,
            'mean_reward': 0.5,
            'std_reward': 0.2,
        }
        
        # 评估历史
        self._evaluation_history: List[EvaluationMetrics] = []
        self._rl_inputs_buffer: List[RLOptimizerInput] = []
        
        # 监控统计
        self._monitoring_stats = {
            'total_evaluations': 0,
            'average_reward': 0.0,
            'reward_variance': 0.0,
            'context_quality_avg': 0.0,
        }
        
        logger.info(f"ThetaEvolve evaluator initialized with reward_process_type={self.reward_process_type.value}")

    def evaluate_context_result(self, context_result) -> EvaluationMetrics:
        """
        评估ContextMind的单次上下文结果。
        
        Args:
            context_result: ContextTurnResult对象
            
        Returns:
            评估指标对象
        """
        # 提取原始奖励
        raw_reward = context_result.reward_signal
        
        # 计算上下文质量
        context_quality = self._calculate_context_quality(context_result)
        
        # 计算响应质量
        response_quality = self._calculate_response_quality(context_result)
        
        # 计算学习进度
        learning_progress = self._calculate_learning_progress(context_result)
        
        # 处理奖励
        normalized_reward = self._process_reward(
            raw_reward, 
            context_quality, 
            response_quality, 
            learning_progress
        )
        
        # 创建评估指标
        metrics = EvaluationMetrics(
            reward=raw_reward,
            normalized_reward=normalized_reward,
            context_quality=context_quality,
            response_quality=response_quality,
            learning_progress=learning_progress,
            metadata={
                'turn_number': context_result.turn_number,
                'processing_time': context_result.processing_time,
                'memory_count': context_result.memory_count,
                'history_count': context_result.history_count,
            }
        )
        
        # 记录评估历史
        self._evaluation_history.append(metrics)
        
        # 更新监控统计
        if self.enable_monitoring:
            self._update_monitoring_stats(metrics)
        
        # 调用奖励钩子
        self._execute_reward_hooks(metrics)
        
        logger.debug(f"Evaluated context result: reward={normalized_reward:.3f}, "
                    f"context_quality={context_quality:.3f}, response_quality={response_quality:.3f}")
        
        return metrics

    def _process_reward(
        self, 
        raw_reward: float, 
        context_quality: float, 
        response_quality: float,
        learning_progress: float
    ) -> float:
        """根据处理类型处理奖励信号。"""
        if self.reward_process_type == RewardProcessType.RAW:
            return raw_reward
        
        elif self.reward_process_type == RewardProcessType.NORMALIZED:
            # 简单归一化到[0, 1]范围
            min_r = self.normalization_params['min_reward']
            max_r = self.normalization_params['max_reward']
            return (raw_reward - min_r) / (max_r - min_r) if max_r > min_r else raw_reward
        
        elif self.reward_process_type == RewardProcessType.RL_NORMALIZED:
            # RL归一化：结合上下文质量和响应质量
            weighted_reward = (
                0.4 * raw_reward +
                0.3 * context_quality +
                0.2 * response_quality +
                0.1 * learning_progress
            )
            # Z-score归一化
            mean = self.normalization_params['mean_reward']
            std = self.normalization_params['std_reward']
            normalized = (weighted_reward - mean) / std if std > 0 else weighted_reward
            # 裁剪到合理范围
            return max(0.0, min(1.0, normalized * 0.5 + 0.5))
        
        elif self.reward_process_type == RewardProcessType.ADAPTIVE:
            # 自适应：根据历史动态调整
            if len(self._evaluation_history) < 10:
                return raw_reward
            
            recent_rewards = [m.reward for m in self._evaluation_history[-10:]]
            adaptive_mean = sum(recent_rewards) / len(recent_rewards)
            adaptive_std = (sum((r - adaptive_mean) ** 2 for r in recent_rewards) / len(recent_rewards)) ** 0.5
            
            if adaptive_std > 0:
                return (raw_reward - adaptive_mean) / adaptive_std * 0.2 + 0.5
            return raw_reward
        
        return raw_reward

    def _calculate_context_quality(self, context_result) -> float:
        """计算上下文质量分数。"""
        quality = 0.0
        
        # 基于记忆使用
        if context_result.memory_count > 0:
            quality += 0.3
        
        # 基于历史使用
        if context_result.history_count > 2:
            quality += 0.3
        
        # 基于处理时间
        if context_result.processing_time < 3.0:
            quality += 0.2
        
        # 基于学习轨迹
        if hasattr(context_result, 'learning_trajectory') and context_result.learning_trajectory:
            quality += 0.2
        
        return min(quality, 1.0)

    def _calculate_response_quality(self, context_result) -> float:
        """计算响应质量分数。"""
        quality = 0.0
        
        # 基于响应长度
        response_len = len(context_result.response)
        if 20 < response_len < 200:
            quality += 0.4
        elif response_len >= 10:
            quality += 0.2
        
        # 基于prompt质量
        prompt_len = len(context_result.prompt)
        if prompt_len > 100:
            quality += 0.3
        
        # 基于记忆命中
        if context_result.memory_hits:
            quality += 0.3
        
        return min(quality, 1.0)

    def _calculate_learning_progress(self, context_result) -> float:
        """计算学习进度分数。"""
        if not hasattr(context_result, 'learning_trajectory'):
            return 0.0
        
        trajectory = context_result.learning_trajectory
        if not trajectory:
            return 0.0
        
        # 基于轨迹长度
        progress = min(len(trajectory) * 0.2, 0.6)
        
        # 基于轮次数
        if context_result.turn_number > 5:
            progress += 0.2
        
        # 基于反馈元数据
        if hasattr(context_result, 'feedback_metadata') and context_result.feedback_metadata:
            progress += 0.2
        
        return min(progress, 1.0)

    def _update_monitoring_stats(self, metrics: EvaluationMetrics):
        """更新监控统计信息。"""
        self._monitoring_stats['total_evaluations'] += 1
        n = self._monitoring_stats['total_evaluations']
        
        # 更新平均奖励
        prev_avg = self._monitoring_stats['average_reward']
        self._monitoring_stats['average_reward'] = (
            prev_avg * (n - 1) + metrics.normalized_reward
        ) / n
        
        # 更新奖励方差
        if n > 1:
            delta = metrics.normalized_reward - prev_avg
            self._monitoring_stats['reward_variance'] = (
                (self._monitoring_stats['reward_variance'] * (n - 2) + delta * 
                 (metrics.normalized_reward - self._monitoring_stats['average_reward'])) / (n - 1)
                if n > 1 else 0.0
            )
        
        # 更新上下文质量平均
        prev_cq_avg = self._monitoring_stats['context_quality_avg']
        self._monitoring_stats['context_quality_avg'] = (
            prev_cq_avg * (n - 1) + metrics.context_quality
        ) / n

    def _execute_reward_hooks(self, metrics: EvaluationMetrics):
        """执行所有奖励钩子函数。"""
        for hook in self.reward_hooks:
            try:
                hook(metrics)
            except Exception as e:
                logger.warning(f"Reward hook execution failed: {e}")

    def generate_rl_optimizer_input(
        self, 
        context_result, 
        state_extractor: Optional[Callable] = None
    ) -> RLOptimizerInput:
        """
        生成RL优化器输入。
        
        Args:
            context_result: ContextTurnResult对象
            state_extractor: 状态提取函数（可选）
            
        Returns:
            RL优化器输入对象
        """
        # 评估上下文结果
        metrics = self.evaluate_context_result(context_result)
        
        # 提取状态
        if state_extractor:
            state = state_extractor(context_result)
            next_state = state.copy()  # 简化处理
        else:
            state = self._default_state_extractor(context_result)
            next_state = state.copy()
        
        # 提取动作（这里使用响应作为动作）
        action = context_result.response
        
        # 判断是否完成（这里简化处理）
        done = False
        
        # 创建RL输入
        rl_input = RLOptimizerInput(
            state=state,
            action=action,
            reward=metrics.normalized_reward,
            next_state=next_state,
            done=done,
            info={
                'metrics': metrics,
                'turn_number': context_result.turn_number,
                'processing_time': context_result.processing_time,
            }
        )
        
        # 添加到缓冲区
        self._rl_inputs_buffer.append(rl_input)
        
        logger.debug(f"Generated RL optimizer input with reward={metrics.normalized_reward:.3f}")
        
        return rl_input

    def _default_state_extractor(self, context_result) -> Dict[str, Any]:
        """默认状态提取器。"""
        state = {
            'turn_number': context_result.turn_number,
            'history_count': context_result.history_count,
            'memory_count': context_result.memory_count,
            'processing_time': context_result.processing_time,
        }
        
        # 添加学习特征
        if hasattr(context_result, 'feedback_metadata') and context_result.feedback_metadata:
            state.update(context_result.feedback_metadata)
        
        return state

    def add_reward_hook(self, hook: Callable[[EvaluationMetrics], None]):
        """添加奖励钩子函数。"""
        self.reward_hooks.append(hook)
        logger.info(f"Added reward hook: {hook.__name__ if hasattr(hook, '__name__') else 'anonymous'}")

    def get_monitoring_stats(self) -> Dict[str, Any]:
        """获取监控统计信息。"""
        return self._monitoring_stats.copy()

    def get_evaluation_history(self, last_n: Optional[int] = None) -> List[EvaluationMetrics]:
        """
        获取评估历史。
        
        Args:
            last_n: 返回最近的N条记录（None表示全部）
            
        Returns:
            评估指标列表
        """
        if last_n is None:
            return self._evaluation_history.copy()
        return self._evaluation_history[-last_n:]

    def get_rl_inputs_buffer(self, clear: bool = False) -> List[RLOptimizerInput]:
        """
        获取RL输入缓冲区。
        
        Args:
            clear: 是否清空缓冲区
            
        Returns:
            RL输入列表
        """
        buffer = self._rl_inputs_buffer.copy()
        if clear:
            self._rl_inputs_buffer.clear()
        return buffer

    def reset(self):
        """重置评估器状态。"""
        self._evaluation_history.clear()
        self._rl_inputs_buffer.clear()
        self._monitoring_stats = {
            'total_evaluations': 0,
            'average_reward': 0.0,
            'reward_variance': 0.0,
            'context_quality_avg': 0.0,
        }
        logger.info("ThetaEvolve evaluator reset")
