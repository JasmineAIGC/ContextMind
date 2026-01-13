#!/usr/bin/env python3
"""
Simple validation test for EvoACE integration

This test validates that all components can be imported and initialized correctly.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_imports():
    """Test that all modules can be imported"""
    print("Testing imports...")
    
    try:
        from contextmind import (
            ContextEngine,
            ThetaEvolveEvaluator,
            AlphaEvolveScheduler,
            EvoACETestingHooks,
            RewardProcessType,
            SamplingStrategy,
        )
        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def test_dataclass_creation():
    """Test that dataclasses can be created"""
    print("\nTesting dataclass creation...")
    
    try:
        from contextmind import ContextTurnResult, IntegratedKnowledge
        
        # Test ContextTurnResult with EvoACE fields
        result = ContextTurnResult(
            prompt="test",
            reasoning="",
            response="test response",
            reward_signal=0.8,
            learning_trajectory=[],
            feedback_metadata={},
        )
        
        assert hasattr(result, 'reward_signal')
        assert hasattr(result, 'learning_trajectory')
        assert hasattr(result, 'feedback_metadata')
        
        # Test IntegratedKnowledge with EvoACE fields
        knowledge = IntegratedKnowledge(
            user_input="test",
            history_text="",
            memory_text="",
            preset_info="",
            extended_context="",
            base_system_prompt="",
            user_profile={},
            business_rules={},
            temporal_context={},
            memory_trajectory=[],
            learning_features={},
        )
        
        assert hasattr(knowledge, 'memory_trajectory')
        assert hasattr(knowledge, 'learning_features')
        
        print("✅ Dataclass creation successful")
        return True
    except Exception as e:
        print(f"❌ Dataclass creation failed: {e}")
        return False

def test_enum_creation():
    """Test that enums can be created"""
    print("\nTesting enum creation...")
    
    try:
        from contextmind import RewardProcessType, SamplingStrategy
        
        # Test RewardProcessType
        assert hasattr(RewardProcessType, 'RL_NORMALIZED')
        assert RewardProcessType.RL_NORMALIZED.value == "RL-NORMALIZED"
        
        # Test SamplingStrategy
        assert hasattr(SamplingStrategy, 'ADAPTIVE')
        assert SamplingStrategy.ADAPTIVE.value == "ADAPTIVE"
        
        print("✅ Enum creation successful")
        return True
    except Exception as e:
        print(f"❌ Enum creation failed: {e}")
        return False

def test_module_structure():
    """Test that modules have expected structure"""
    print("\nTesting module structure...")
    
    try:
        # Import without initializing
        import contextmind.engine as engine_module
        import contextmind.theta_evolve as theta_module
        import contextmind.alpha_evolve as alpha_module
        import contextmind.testing_hooks as testing_module
        
        # Check ContextEngine has EvoACE methods
        assert hasattr(engine_module.ContextEngine, 'contextualize_memory')
        assert hasattr(engine_module.ContextEngine, 'generate_memory_update_from_template')
        assert hasattr(engine_module.ContextEngine, 'get_modular_prompt_interface')
        
        # Check ThetaEvolveEvaluator has expected methods
        assert hasattr(theta_module.ThetaEvolveEvaluator, 'evaluate_context_result')
        assert hasattr(theta_module.ThetaEvolveEvaluator, 'generate_rl_optimizer_input')
        assert hasattr(theta_module.ThetaEvolveEvaluator, 'add_reward_hook')
        
        # Check AlphaEvolveScheduler has expected methods
        assert hasattr(alpha_module.AlphaEvolveScheduler, 'apply_dynamic_sampling_variance_filter')
        assert hasattr(alpha_module.AlphaEvolveScheduler, 'schedule_iteration')
        
        # Check EvoACETestingHooks has expected methods
        assert hasattr(testing_module.EvoACETestingHooks, 'run_all_tests')
        assert hasattr(testing_module.EvoACETestingHooks, 'init_run_post_debug_env')
        
        print("✅ Module structure validation successful")
        return True
    except Exception as e:
        print(f"❌ Module structure validation failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all validation tests"""
    print("=" * 80)
    print("EvoACE Integration Validation Tests")
    print("=" * 80)
    
    results = []
    
    results.append(test_imports())
    results.append(test_dataclass_creation())
    results.append(test_enum_creation())
    results.append(test_module_structure())
    
    print("\n" + "=" * 80)
    print("Validation Summary")
    print("=" * 80)
    
    total = len(results)
    passed = sum(results)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {passed / total * 100:.1f}%")
    
    if all(results):
        print("\n✅ All validation tests passed!")
        return 0
    else:
        print("\n❌ Some validation tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
