# EvoACE Framework Integration

This document describes the integration of the EvoACE framework into the ContextMind repository, providing enhanced short-term and long-term memory structure with reinforcement learning capabilities.

## Overview

The EvoACE framework integration extends ContextMind with three main components:

1. **Enhanced ContextMind Engine** - Memory contextualization and modular prompt generation with cross-module feedback
2. **ThetaEvolve Evaluator** - RL optimizer integration with reward processing and monitoring
3. **AlphaEvolve Scheduler** - Dynamic experiment management with variance-based sampling

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     EvoACE Framework                         │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐    ┌──────────────────┐              │
│  │  ContextEngine   │───▶│ ThetaEvolve      │              │
│  │  (Enhanced)      │    │ Evaluator        │              │
│  │                  │    │                  │              │
│  │ • Memory         │    │ • Reward         │              │
│  │   Trajectory     │    │   Processing     │              │
│  │ • Learning       │    │ • RL Optimizer   │              │
│  │   Features       │    │   Input          │              │
│  │ • Modular        │    │ • Monitoring     │              │
│  │   Interface      │    │ • Hooks          │              │
│  └──────────────────┘    └──────────────────┘              │
│           │                       │                          │
│           └───────────┬───────────┘                          │
│                       ▼                                      │
│              ┌──────────────────┐                           │
│              │ AlphaEvolve      │                           │
│              │ Scheduler        │                           │
│              │                  │                           │
│              │ • Dynamic        │                           │
│              │   Sampling       │                           │
│              │ • Variance       │                           │
│              │   Filter         │                           │
│              │ • Experiment     │                           │
│              │   Config         │                           │
│              └──────────────────┘                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Key Features

### 1. Enhanced ContextMind Engine

#### Memory Contextualization
```python
# Add context to memories for cross-module feedback
contextualized = await engine.contextualize_memory(
    "User showed interest in EvoACE",
    context_type="cross_module"
)
# Returns: dict with learning_features and memory_trajectory
```

#### Modular Prompt Interface
```python
# Get modular components for flexible prompt generation
interface = engine.get_modular_prompt_interface()
# Returns: {
#   'base_prompt': str,
#   'user_profile': dict,
#   'business_rules': dict,
#   'temporal_context': dict,
#   'learning_features': dict,
#   'memory_trajectory': list,
# }
```

#### Template-Based Memory Updates
```python
# Generate memory updates using templates
memory_update = engine.generate_memory_update_from_template(
    'important_fact',
    fact="User prefers detailed explanations"
)
# Returns: "[重要事实] User prefers detailed explanations"
```

#### Enhanced Prompt Building
The `_build_prompt` method now supports:
- Learning features integration
- Memory trajectory tracking
- Dynamic context weighting based on learning signals

### 2. ThetaEvolve Evaluator

#### Reward Processing Types
```python
from contextmind import ThetaEvolveEvaluator, RewardProcessType

evaluator = ThetaEvolveEvaluator(
    reward_process_type="RL-NORMALIZED",  # or "RAW", "NORMALIZED", "ADAPTIVE"
    enable_monitoring=True,
    reward_hooks=[custom_reward_hook],
)
```

Available reward processing types:
- **RAW**: Original reward signal
- **NORMALIZED**: Simple [0,1] normalization
- **RL-NORMALIZED**: Combined context quality, response quality, and learning progress
- **ADAPTIVE**: Dynamic adjustment based on history

#### RL Optimizer Input Generation
```python
# Evaluate context result and generate RL input
metrics = evaluator.evaluate_context_result(context_result)
rl_input = evaluator.generate_rl_optimizer_input(context_result)

# Access RL input components
state = rl_input.state
action = rl_input.action
reward = rl_input.reward
next_state = rl_input.next_state
```

#### Reward Hooks
```python
def my_reward_hook(metrics):
    print(f"Reward: {metrics.normalized_reward}")
    print(f"Context Quality: {metrics.context_quality}")
    print(f"Response Quality: {metrics.response_quality}")

evaluator.add_reward_hook(my_reward_hook)
```

#### Monitoring
```python
# Get monitoring statistics
stats = evaluator.get_monitoring_stats()
# Returns: {
#   'total_evaluations': int,
#   'average_reward': float,
#   'reward_variance': float,
#   'context_quality_avg': float,
# }
```

### 3. AlphaEvolve Scheduler

#### Dynamic Sampling Variance Filter
```python
from contextmind import AlphaEvolveScheduler

scheduler = AlphaEvolveScheduler(
    default_sampling_strategy="ADAPTIVE",
    dynamic_sampling_variance_filter={
        'threshold': 0.1,
        'window_size': 20,
        'min_variance': 0.01,
        'max_variance': 0.5,
        'adaptive_threshold': True,
    },
)

# Apply variance filter to samples
filtered_samples = scheduler.apply_dynamic_sampling_variance_filter(samples)
```

#### Sampling Strategies
Available strategies:
- **UNIFORM**: Random uniform sampling
- **WEIGHTED**: Weighted by value magnitude
- **ADAPTIVE**: Variance-aware adaptive sampling
- **VARIANCE_BASED**: Sample near mean when high variance

```python
from contextmind import SamplingStrategy

# Sample from distribution
sampled_value = scheduler.sample_from_distribution(
    distribution,
    strategy="ADAPTIVE"
)
```

#### Experiment Management
```python
# Create and activate experiment
config = scheduler.create_experiment("my-experiment")
scheduler.activate_experiment("my-experiment")

# Schedule iteration
result = scheduler.schedule_iteration(
    context_engine,
    theta_evaluator,
    iteration_callback=my_callback
)
```

## Complete Usage Example

```python
import asyncio
from contextmind import (
    Client,
    ContextEngine,
    ThetaEvolveEvaluator,
    AlphaEvolveScheduler,
)

async def main():
    # 1. Create LLM client
    client = Client()
    
    # 2. Create ContextEngine with EvoACE enabled
    engine = ContextEngine(
        app_name="my-app",
        user_id="user-123",
        llm_client=client,
        enable_evoace=True,
        reward_callback=lambda r: print(f"Reward: {r.reward_signal}"),
    )
    
    # 3. Create ThetaEvolve evaluator
    evaluator = ThetaEvolveEvaluator(
        reward_process_type="RL-NORMALIZED",
        enable_monitoring=True,
    )
    
    # 4. Create AlphaEvolve scheduler
    scheduler = AlphaEvolveScheduler(
        default_sampling_strategy="ADAPTIVE",
        dynamic_sampling_variance_filter={'threshold': 0.1},
    )
    
    # 5. Create and activate experiment
    scheduler.create_experiment("test-exp")
    scheduler.activate_experiment("test-exp")
    
    # 6. Run feedback loop
    result = await engine.process_turn("Hello, world!")
    
    # 7. Evaluate and generate RL input
    metrics = evaluator.evaluate_context_result(result)
    rl_input = evaluator.generate_rl_optimizer_input(result)
    
    # 8. Schedule iteration
    iteration = scheduler.schedule_iteration(engine, evaluator)
    
    print(f"Reward: {metrics.normalized_reward:.3f}")
    print(f"Variance: {iteration['variance']:.4f}")

asyncio.run(main())
```

## Testing

### Integration Tests

Run the complete integration test suite:

```bash
python3 -c "
import asyncio
from contextmind import (
    Client, ContextEngine, ThetaEvolveEvaluator,
    AlphaEvolveScheduler, EvoACETestingHooks
)

async def test():
    client = Client()
    engine = ContextEngine(
        app_name='test', user_id='test', 
        llm_client=client, enable_evoace=True
    )
    evaluator = ThetaEvolveEvaluator(reward_process_type='RL-NORMALIZED')
    scheduler = AlphaEvolveScheduler()
    
    hooks = EvoACETestingHooks(engine, evaluator, scheduler)
    report = await hooks.run_all_tests()
    
    print(f'Tests: {report.total_tests}')
    print(f'Passed: {report.passed_tests}')
    print(f'Failed: {report.failed_tests}')

asyncio.run(test())
"
```

### Validation Tests

Run basic validation tests:

```bash
python3 validate_integration.py
```

### Demo

Run the interactive demo:

```bash
python3 evoace_demo.py
```

## API Reference

### ContextEngine (Enhanced)

New methods:
- `contextualize_memory(memory_content, context_type)` - Add context to memories
- `generate_memory_update_from_template(template_name, **kwargs)` - Generate memory updates
- `get_modular_prompt_interface()` - Get modular prompt components
- `_build_memory_trajectory(history_text, memory_text)` - Build memory trajectory
- `_extract_learning_features(user_input, history_text)` - Extract learning features
- `_calculate_reward_signal(result)` - Calculate reward signal

New parameters:
- `enable_evoace: bool` - Enable EvoACE framework support
- `reward_callback: callable` - Reward callback function

### ThetaEvolveEvaluator

Methods:
- `evaluate_context_result(context_result)` - Evaluate context result
- `generate_rl_optimizer_input(context_result, state_extractor)` - Generate RL input
- `add_reward_hook(hook)` - Add reward hook
- `get_monitoring_stats()` - Get monitoring statistics
- `get_evaluation_history(last_n)` - Get evaluation history
- `get_rl_inputs_buffer(clear)` - Get RL inputs buffer
- `reset()` - Reset evaluator state

### AlphaEvolveScheduler

Methods:
- `create_experiment(name, config)` - Create experiment
- `activate_experiment(name)` - Activate experiment
- `apply_dynamic_sampling_variance_filter(samples, config_override)` - Apply variance filter
- `sample_from_distribution(distribution, strategy)` - Sample from distribution
- `schedule_iteration(context_engine, theta_evaluator, iteration_callback)` - Schedule iteration
- `update_variance_filter_config(config)` - Update variance filter config
- `get_variance_stats()` - Get variance statistics
- `reset()` - Reset scheduler state

### EvoACETestingHooks

Methods:
- `run_all_tests()` - Run all integration tests
- `init_run_post_debug_env(user_input)` - Initialize debug environment
- `test_context_engine_evoace_support()` - Test ContextEngine EvoACE support
- `test_theta_evaluator_integration()` - Test ThetaEvolve integration
- `test_alpha_scheduler_variance_filter()` - Test AlphaEvolve variance filter
- `test_end_to_end_feedback_loop(test_input)` - Test complete feedback loop
- `test_reward_hooks()` - Test reward hooks

## Configuration

### Variance Filter Configuration

```python
variance_filter_config = {
    'threshold': 0.1,           # Variance threshold
    'window_size': 20,          # Smoothing window size
    'min_variance': 0.01,       # Minimum variance
    'max_variance': 0.5,        # Maximum variance
    'adaptive_threshold': True, # Enable adaptive threshold
}
```

### Reward Normalization Parameters

```python
normalization_params = {
    'min_reward': 0.0,
    'max_reward': 1.0,
    'mean_reward': 0.5,
    'std_reward': 0.2,
}
```

## Performance Considerations

1. **Memory Trajectory**: Limited to recent items to avoid memory bloat
2. **Variance Filter**: Window size affects smoothing vs. responsiveness
3. **Reward Hooks**: Lightweight hooks recommended to avoid blocking
4. **Monitoring**: Stats updated incrementally for efficiency

## Troubleshooting

### Common Issues

**Issue**: EvoACE features not working
- **Solution**: Ensure `enable_evoace=True` when creating ContextEngine

**Issue**: High variance in rewards
- **Solution**: Adjust `dynamic_sampling_variance_filter` threshold

**Issue**: Slow evaluation
- **Solution**: Reduce monitoring frequency or disable reward hooks

## Contributing

When extending the EvoACE integration:
1. Maintain backward compatibility
2. Add tests to `testing_hooks.py`
3. Update this documentation
4. Follow existing naming conventions

## License

Same as ContextMind repository.
