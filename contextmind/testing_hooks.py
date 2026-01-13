"""
EvoACE Integration Testing Hooks

该模块提供跨仓库API测试钩子，用于测试EvoACE框架的完整反馈循环。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable

from .engine import ContextEngine
from .theta_evolve import ThetaEvolveEvaluator
from .alpha_evolve import AlphaEvolveScheduler
from .logger import get_logger

logger = get_logger(__name__)


@dataclass
class TestResult:
    """测试结果数据类"""
    test_name: str
    passed: bool
    message: str
    metrics: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class IntegrationTestReport:
    """集成测试报告数据类"""
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    test_results: List[TestResult] = field(default_factory=list)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    end_time: Optional[str] = None


class EvoACETestingHooks:
    """
    EvoACE测试钩子类
    
    提供用于测试EvoACE框架集成的API钩子和测试工具。
    """
    
    def __init__(
        self,
        context_engine: ContextEngine,
        theta_evaluator: ThetaEvolveEvaluator,
        alpha_scheduler: AlphaEvolveScheduler,
    ):
        """
        初始化测试钩子。
        
        Args:
            context_engine: ContextEngine实例
            theta_evaluator: ThetaEvolveEvaluator实例
            alpha_scheduler: AlphaEvolveScheduler实例
        """
        self.context_engine = context_engine
        self.theta_evaluator = theta_evaluator
        self.alpha_scheduler = alpha_scheduler
        
        self._test_report = IntegrationTestReport()
        self._debug_mode = False
        
        logger.info("EvoACE testing hooks initialized")

    def enable_debug_mode(self):
        """启用调试模式。"""
        self._debug_mode = True
        logger.info("Debug mode enabled")

    def disable_debug_mode(self):
        """禁用调试模式。"""
        self._debug_mode = False
        logger.info("Debug mode disabled")

    async def test_context_engine_evoace_support(self) -> TestResult:
        """测试ContextEngine的EvoACE支持。"""
        test_name = "ContextEngine EvoACE Support"
        
        try:
            # 检查EvoACE是否启用
            if not self.context_engine.enable_evoace:
                return TestResult(
                    test_name=test_name,
                    passed=False,
                    message="EvoACE not enabled in ContextEngine",
                )
            
            # 测试模块化接口
            modular_interface = self.context_engine.get_modular_prompt_interface()
            assert 'learning_features' in modular_interface
            assert 'memory_trajectory' in modular_interface
            
            # 测试记忆上下文化
            contextualized = await self.context_engine.contextualize_memory(
                "测试记忆内容",
                context_type="cross_module"
            )
            assert 'learning_features' in contextualized
            assert 'memory_trajectory' in contextualized
            
            # 测试模板生成
            memory_update = self.context_engine.generate_memory_update_from_template(
                'important_fact',
                fact="测试事实"
            )
            assert len(memory_update) > 0
            
            return TestResult(
                test_name=test_name,
                passed=True,
                message="All ContextEngine EvoACE features working",
                metrics={
                    'modular_interface_keys': list(modular_interface.keys()),
                    'contextualized_keys': list(contextualized.keys()),
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                message=f"Test failed with error: {str(e)}",
            )

    async def test_theta_evaluator_integration(self) -> TestResult:
        """测试ThetaEvolve评估器集成。"""
        test_name = "ThetaEvolve Evaluator Integration"
        
        try:
            # 模拟一个简单的上下文结果
            from .engine import ContextTurnResult
            
            mock_result = ContextTurnResult(
                prompt="测试prompt",
                reasoning="",
                response="测试响应",
                memory_hits=[],
                turn_number=1,
                processing_time=0.5,
                reward_signal=0.8,
                learning_trajectory=[{'type': 'test'}],
                feedback_metadata={'test': True},
            )
            
            # 测试评估
            metrics = self.theta_evaluator.evaluate_context_result(mock_result)
            assert metrics.reward > 0
            assert metrics.normalized_reward >= 0
            
            # 测试RL输入生成
            rl_input = self.theta_evaluator.generate_rl_optimizer_input(mock_result)
            assert rl_input.reward >= 0
            assert 'turn_number' in rl_input.state
            
            # 测试监控统计
            stats = self.theta_evaluator.get_monitoring_stats()
            assert stats['total_evaluations'] > 0
            
            return TestResult(
                test_name=test_name,
                passed=True,
                message="ThetaEvolve evaluator working correctly",
                metrics={
                    'normalized_reward': metrics.normalized_reward,
                    'total_evaluations': stats['total_evaluations'],
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                message=f"Test failed with error: {str(e)}",
            )

    async def test_alpha_scheduler_variance_filter(self) -> TestResult:
        """测试AlphaEvolve调度器的方差过滤。"""
        test_name = "AlphaEvolve Variance Filter"
        
        try:
            # 测试方差过滤
            test_samples = [0.1, 0.9, 0.2, 0.8, 0.3, 0.7, 0.4, 0.6]
            filtered = self.alpha_scheduler.apply_dynamic_sampling_variance_filter(test_samples)
            
            assert len(filtered) == len(test_samples)
            
            # 测试采样
            sampled = self.alpha_scheduler.sample_from_distribution(filtered)
            assert isinstance(sampled, float)
            
            # 测试方差统计
            variance_stats = self.alpha_scheduler.get_variance_stats()
            assert 'current_variance' in variance_stats
            
            return TestResult(
                test_name=test_name,
                passed=True,
                message="Variance filter working correctly",
                metrics={
                    'current_variance': variance_stats['current_variance'],
                    'sampled_value': sampled,
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                message=f"Test failed with error: {str(e)}",
            )

    async def test_end_to_end_feedback_loop(self, test_input: str = "你好") -> TestResult:
        """测试端到端的EvoACE反馈循环。"""
        test_name = "End-to-End Feedback Loop"
        
        try:
            # 1. 处理上下文
            context_result = await self.context_engine.process_turn(test_input)
            
            # 2. 评估结果
            metrics = self.theta_evaluator.evaluate_context_result(context_result)
            
            # 3. 生成RL输入
            rl_input = self.theta_evaluator.generate_rl_optimizer_input(context_result)
            
            # 4. 调度迭代
            iteration_result = self.alpha_scheduler.schedule_iteration(
                self.context_engine,
                self.theta_evaluator
            )
            
            # 验证所有组件都正常工作
            assert context_result.reward_signal >= 0
            assert metrics.normalized_reward >= 0
            assert rl_input.reward >= 0
            assert iteration_result['iteration'] > 0
            
            return TestResult(
                test_name=test_name,
                passed=True,
                message="End-to-end feedback loop working",
                metrics={
                    'context_reward': context_result.reward_signal,
                    'normalized_reward': metrics.normalized_reward,
                    'rl_reward': rl_input.reward,
                    'iteration': iteration_result['iteration'],
                }
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                message=f"Test failed with error: {str(e)}",
            )

    async def test_reward_hooks(self) -> TestResult:
        """测试奖励钩子功能。"""
        test_name = "Reward Hooks"
        
        hook_called = {'count': 0}
        
        def test_hook(metrics):
            hook_called['count'] += 1
        
        try:
            # 添加钩子
            self.theta_evaluator.add_reward_hook(test_hook)
            
            # 模拟评估
            from .engine import ContextTurnResult
            mock_result = ContextTurnResult(
                prompt="测试",
                reasoning="",
                response="测试",
                reward_signal=0.5,
            )
            
            self.theta_evaluator.evaluate_context_result(mock_result)
            
            # 验证钩子被调用
            assert hook_called['count'] > 0
            
            return TestResult(
                test_name=test_name,
                passed=True,
                message="Reward hooks working correctly",
                metrics={'hook_calls': hook_called['count']}
            )
            
        except Exception as e:
            return TestResult(
                test_name=test_name,
                passed=False,
                message=f"Test failed with error: {str(e)}",
            )

    async def run_all_tests(self) -> IntegrationTestReport:
        """运行所有集成测试。"""
        logger.info("Starting EvoACE integration tests...")
        
        self._test_report = IntegrationTestReport()
        
        # 运行所有测试
        tests = [
            self.test_context_engine_evoace_support(),
            self.test_theta_evaluator_integration(),
            self.test_alpha_scheduler_variance_filter(),
            self.test_end_to_end_feedback_loop(),
            self.test_reward_hooks(),
        ]
        
        results = await asyncio.gather(*tests, return_exceptions=True)
        
        # 处理结果
        for result in results:
            if isinstance(result, Exception):
                self._test_report.test_results.append(TestResult(
                    test_name="Unknown Test",
                    passed=False,
                    message=f"Test crashed: {str(result)}",
                ))
                self._test_report.failed_tests += 1
            else:
                self._test_report.test_results.append(result)
                if result.passed:
                    self._test_report.passed_tests += 1
                else:
                    self._test_report.failed_tests += 1
            
            self._test_report.total_tests += 1
        
        self._test_report.end_time = datetime.now().isoformat()
        
        # 打印报告
        self._print_test_report()
        
        return self._test_report

    def _print_test_report(self):
        """打印测试报告。"""
        report = self._test_report
        
        logger.info("=" * 80)
        logger.info("EvoACE Integration Test Report")
        logger.info("=" * 80)
        logger.info(f"Total Tests: {report.total_tests}")
        logger.info(f"Passed: {report.passed_tests}")
        logger.info(f"Failed: {report.failed_tests}")
        logger.info(f"Success Rate: {report.passed_tests / report.total_tests * 100:.1f}%")
        logger.info("=" * 80)
        
        for result in report.test_results:
            status = "✅ PASS" if result.passed else "❌ FAIL"
            logger.info(f"{status} - {result.test_name}")
            if self._debug_mode or not result.passed:
                logger.info(f"  Message: {result.message}")
                if result.metrics:
                    logger.info(f"  Metrics: {result.metrics}")
        
        logger.info("=" * 80)

    def get_test_report(self) -> IntegrationTestReport:
        """获取测试报告。"""
        return self._test_report

    async def init_run_post_debug_env(self, user_input: str = "测试输入") -> Dict[str, Any]:
        """
        初始化运行后调试环境，用于奖励测试。
        
        Args:
            user_input: 测试用户输入
            
        Returns:
            调试环境信息字典
        """
        logger.info("Initializing post-debug environment...")
        
        # 1. 处理上下文
        context_result = await self.context_engine.process_turn(user_input)
        
        # 2. 评估结果
        metrics = self.theta_evaluator.evaluate_context_result(context_result)
        
        # 3. 收集环境信息
        env_info = {
            'context_result': {
                'prompt_length': len(context_result.prompt),
                'response': context_result.response,
                'reward_signal': context_result.reward_signal,
                'turn_number': context_result.turn_number,
            },
            'evaluation_metrics': {
                'normalized_reward': metrics.normalized_reward,
                'context_quality': metrics.context_quality,
                'response_quality': metrics.response_quality,
                'learning_progress': metrics.learning_progress,
            },
            'scheduler_state': {
                'total_iterations': self.alpha_scheduler.get_scheduler_state().total_iterations,
                'variance': self.alpha_scheduler.get_variance_stats()['current_variance'],
            },
            'timestamp': datetime.now().isoformat(),
        }
        
        logger.info(f"Debug environment initialized with reward={metrics.normalized_reward:.3f}")
        
        return env_info
