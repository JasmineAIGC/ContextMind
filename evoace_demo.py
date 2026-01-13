#!/usr/bin/env python3
"""
EvoACE Framework Integration Demo

演示如何使用集成到ContextMind中的EvoACE框架，包括：
1. 启用EvoACE的ContextEngine
2. ThetaEvolve评估器的使用
3. AlphaEvolve调度器的使用
4. 完整的强化学习反馈循环
"""

import asyncio
import sys
from pathlib import Path

# 将项目根目录添加到 Python 搜索路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
env_file = project_root / ".env"
if env_file.exists():
    load_dotenv(env_file)

from contextmind import (
    Client,
    ContextEngine,
    ThetaEvolveEvaluator,
    AlphaEvolveScheduler,
    EvoACETestingHooks,
    get_logger,
    setup_logging,
)

# 设置日志
setup_logging(level="INFO", log_to_console=True)
logger = get_logger(__name__)


async def demo_evoace_integration():
    """演示EvoACE框架集成"""
    
    logger.info("=" * 80)
    logger.info("EvoACE Framework Integration Demo")
    logger.info("=" * 80)
    
    # 1. 创建LLM客户端
    logger.info("\n📦 Step 1: Creating LLM Client...")
    client = Client()
    
    # 2. 创建启用EvoACE的ContextEngine
    logger.info("\n🔧 Step 2: Creating ContextEngine with EvoACE enabled...")
    
    def reward_callback(result):
        """奖励回调示例"""
        logger.info(f"  📊 Reward callback: reward={result.reward_signal:.3f}, "
                   f"turn={result.turn_number}")
    
    engine = ContextEngine(
        app_name="evoace-demo",
        user_id="demo-user",
        llm_client=client,
        base_system_prompt="你是一个智能助手，使用EvoACE框架进行持续学习。",
        enable_evoace=True,
        reward_callback=reward_callback,
        max_recent_events=10,
    )
    
    # 3. 创建ThetaEvolve评估器
    logger.info("\n⚙️  Step 3: Creating ThetaEvolve Evaluator...")
    
    def reward_hook(metrics):
        """奖励钩子示例"""
        logger.info(f"  🎯 Reward hook: normalized_reward={metrics.normalized_reward:.3f}, "
                   f"context_quality={metrics.context_quality:.3f}")
    
    evaluator = ThetaEvolveEvaluator(
        reward_process_type="RL-NORMALIZED",
        enable_monitoring=True,
        reward_hooks=[reward_hook],
    )
    
    # 4. 创建AlphaEvolve调度器
    logger.info("\n📅 Step 4: Creating AlphaEvolve Scheduler...")
    scheduler = AlphaEvolveScheduler(
        default_sampling_strategy="ADAPTIVE",
        dynamic_sampling_variance_filter={
            'threshold': 0.1,
            'window_size': 20,
            'adaptive_threshold': True,
        },
        enable_auto_tuning=True,
    )
    
    # 5. 创建实验
    logger.info("\n🔬 Step 5: Creating Experiment...")
    exp_config = scheduler.create_experiment("demo-experiment")
    scheduler.activate_experiment("demo-experiment")
    logger.info(f"  Experiment created: {exp_config.name}")
    
    # 6. 运行几轮对话，演示完整的反馈循环
    logger.info("\n🔄 Step 6: Running Feedback Loop Iterations...")
    
    test_inputs = [
        "你好，请介绍一下EvoACE框架。",
        "它有什么优势？",
        "如何使用强化学习优化？",
    ]
    
    for i, user_input in enumerate(test_inputs, 1):
        logger.info(f"\n--- Iteration {i} ---")
        logger.info(f"👤 User: {user_input}")
        
        # 6.1 处理上下文
        result = await engine.process_turn(user_input)
        logger.info(f"🤖 Assistant: {result.response}")
        logger.info(f"📈 Reward Signal: {result.reward_signal:.3f}")
        
        # 6.2 评估结果
        metrics = evaluator.evaluate_context_result(result)
        logger.info(f"📊 Normalized Reward: {metrics.normalized_reward:.3f}")
        logger.info(f"📊 Context Quality: {metrics.context_quality:.3f}")
        logger.info(f"📊 Response Quality: {metrics.response_quality:.3f}")
        
        # 6.3 生成RL输入
        rl_input = evaluator.generate_rl_optimizer_input(result)
        logger.info(f"🎮 RL Input Generated: reward={rl_input.reward:.3f}")
        
        # 6.4 调度迭代
        iteration_result = scheduler.schedule_iteration(engine, evaluator)
        logger.info(f"🔄 Iteration Scheduled: #{iteration_result['iteration']}")
        logger.info(f"📉 Variance: {iteration_result['variance']:.4f}")
    
    # 7. 显示监控统计
    logger.info("\n📊 Step 7: Monitoring Statistics...")
    stats = evaluator.get_monitoring_stats()
    logger.info(f"  Total Evaluations: {stats['total_evaluations']}")
    logger.info(f"  Average Reward: {stats['average_reward']:.3f}")
    logger.info(f"  Reward Variance: {stats['reward_variance']:.4f}")
    logger.info(f"  Context Quality Avg: {stats['context_quality_avg']:.3f}")
    
    # 8. 显示方差统计
    logger.info("\n📉 Step 8: Variance Statistics...")
    var_stats = scheduler.get_variance_stats()
    logger.info(f"  Current Variance: {var_stats['current_variance']:.4f}")
    logger.info(f"  Mean Variance: {var_stats['mean_variance']:.4f}")
    logger.info(f"  Variance Trend Length: {len(var_stats['variance_trend'])}")
    
    # 9. 测试模块化接口
    logger.info("\n🔌 Step 9: Testing Modular Interface...")
    modular_interface = engine.get_modular_prompt_interface()
    logger.info(f"  Available Components: {list(modular_interface.keys())}")
    
    # 10. 测试记忆上下文化
    logger.info("\n🧠 Step 10: Testing Memory Contextualization...")
    contextualized = await engine.contextualize_memory(
        "用户对EvoACE框架很感兴趣",
        context_type="cross_module"
    )
    logger.info(f"  Contextualized Keys: {list(contextualized.keys())}")
    
    # 11. 测试模板生成
    logger.info("\n📝 Step 11: Testing Template Generation...")
    memory_update = engine.generate_memory_update_from_template(
        'important_fact',
        fact="EvoACE框架集成成功"
    )
    logger.info(f"  Memory Update: {memory_update}")
    
    logger.info("\n✅ Demo completed successfully!")
    logger.info("=" * 80)


async def demo_integration_tests():
    """演示集成测试"""
    
    logger.info("\n" + "=" * 80)
    logger.info("Running EvoACE Integration Tests")
    logger.info("=" * 80)
    
    # 创建组件
    client = Client()
    engine = ContextEngine(
        app_name="test-app",
        user_id="test-user",
        llm_client=client,
        enable_evoace=True,
        max_recent_events=5,
    )
    evaluator = ThetaEvolveEvaluator(reward_process_type="RL-NORMALIZED")
    scheduler = AlphaEvolveScheduler()
    
    # 创建测试钩子
    testing_hooks = EvoACETestingHooks(engine, evaluator, scheduler)
    testing_hooks.enable_debug_mode()
    
    # 运行所有测试
    report = await testing_hooks.run_all_tests()
    
    # 显示摘要
    logger.info("\n📋 Test Summary:")
    logger.info(f"  Total: {report.total_tests}")
    logger.info(f"  Passed: {report.passed_tests} ✅")
    logger.info(f"  Failed: {report.failed_tests} ❌")
    logger.info(f"  Success Rate: {report.passed_tests / report.total_tests * 100:.1f}%")
    
    # 测试调试环境
    logger.info("\n🔧 Testing Debug Environment...")
    debug_env = await testing_hooks.init_run_post_debug_env("测试调试环境")
    logger.info(f"  Debug Env Keys: {list(debug_env.keys())}")
    logger.info(f"  Reward: {debug_env['evaluation_metrics']['normalized_reward']:.3f}")
    
    logger.info("\n✅ Integration tests completed!")
    logger.info("=" * 80)


async def main():
    """主函数"""
    
    print("\n" + "=" * 80)
    print("EvoACE Framework Integration - Interactive Demo")
    print("=" * 80)
    print("\n选择演示模式：")
    print("1. EvoACE集成演示 (推荐)")
    print("2. 集成测试演示")
    print("3. 两者都运行")
    
    choice = input("\n请输入选择 (1/2/3, 默认为1): ").strip() or "1"
    
    if choice == "1":
        await demo_evoace_integration()
    elif choice == "2":
        await demo_integration_tests()
    elif choice == "3":
        await demo_evoace_integration()
        await demo_integration_tests()
    else:
        print("无效选择，运行默认演示...")
        await demo_evoace_integration()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n程序被用户中断")
    except Exception as e:
        print(f"\n\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
