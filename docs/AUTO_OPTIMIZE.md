# Auto-Optimization Module

## 概述

ContextMind的自动优化模块提供了进化算法能力，用于自动调优策略、配置参数和提示词。该模块基于遗传算法和进化计算原理，可以自动搜索最优解决方案。

## 核心概念

### 1. 候选解决方案 (Candidate)
表示一个待优化的解决方案，包含：
- `genome`: 基因型（参数/配置的字典）
- `fitness`: 适应度分数
- `generation`: 所属代数
- `metadata`: 额外元数据

### 2. 适应度评估 (Fitness Evaluation)
评估候选解决方案的好坏程度。
- `FitnessScore`: 适应度分数（越高越好）
- `Evaluator`: 评估器接口

### 3. 进化操作
- **选择 (Selection)**: 选择优秀个体作为父代
- **交叉 (Crossover)**: 父代基因交换产生子代
- **变异 (Mutation)**: 随机改变基因引入多样性

### 4. 群体 (Population)
管理一组候选解决方案，提供：
- 添加/获取候选
- 适应度统计
- 多样性采样

## 模块结构

```
contextmind/auto_optimize/
├── __init__.py          # 导出接口
├── base.py              # 基础数据结构和协议
├── population.py        # 群体管理
├── operators.py         # 变异和交叉操作
├── selection.py         # 选择策略
├── evaluator.py         # 评估框架
└── evolver.py           # 主进化引擎
```

## 快速开始

### 基本使用

```python
import asyncio
from contextmind.auto_optimize import (
    Candidate,
    FitnessScore,
    EvolutionConfig,
    StrategyEvolver,
    BaseEvaluator,
)

# 1. 定义评估器
class MyEvaluator(BaseEvaluator):
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        # 计算适应度
        x = candidate.genome.get("param_x", 0)
        y = candidate.genome.get("param_y", 0)
        
        # 目标函数
        value = -(x - 5)**2 - (y - 3)**2  # 最大化这个值
        
        return FitnessScore(value=value)

# 2. 配置进化参数
config = EvolutionConfig(
    population_size=20,      # 群体大小
    num_generations=50,      # 进化代数
    mutation_rate=0.1,       # 变异概率
    crossover_rate=0.7,      # 交叉概率
    elite_size=2,            # 精英数量
)

# 3. 创建进化器
evolver = StrategyEvolver(
    config=config,
    evaluator=MyEvaluator(),
    initializer=lambda: {"param_x": random.uniform(-10, 10),
                         "param_y": random.uniform(-10, 10)}
)

# 4. 运行优化
async def optimize():
    best = await evolver.evolve()
    print(f"Best solution: {best.genome}")
    print(f"Best fitness: {best.fitness.value}")

asyncio.run(optimize())
```

## 核心组件详解

### 1. 进化配置 (EvolutionConfig)

```python
config = EvolutionConfig(
    population_size=20,              # 群体大小
    num_generations=50,              # 最大进化代数
    mutation_rate=0.1,               # 变异概率
    crossover_rate=0.7,              # 交叉概率
    elite_size=2,                    # 精英保留数量
    tournament_size=3,               # 锦标赛大小
    convergence_threshold=1e-6,      # 收敛阈值
    max_stagnant_generations=10,     # 最大停滞代数
)
```

### 2. 选择策略 (Selection Strategies)

#### 锦标赛选择 (Tournament Selection)
随机选择k个候选，取最优者。

```python
from contextmind.auto_optimize import TournamentSelection

selection = TournamentSelection(tournament_size=3)
```

#### 轮盘赌选择 (Roulette Selection)
概率正比于适应度。

```python
from contextmind.auto_optimize import RouletteSelection

selection = RouletteSelection()
```

#### 精英选择 (Elitist Selection)
直接选择最优个体。

```python
from contextmind.auto_optimize import ElitistSelection

selection = ElitistSelection()
```

#### 排名选择 (Rank Selection)
基于排名而非原始适应度。

```python
from contextmind.auto_optimize import RankSelection

selection = RankSelection()
```

### 3. 变异操作 (Mutation Operators)

#### 随机变异 (Random Mutation)
随机扰动参数值。

```python
from contextmind.auto_optimize import RandomMutation

mutation = RandomMutation(mutation_strength=0.1)
```

#### 高斯变异 (Gaussian Mutation)
使用高斯分布扰动数值参数。

```python
from contextmind.auto_optimize import GaussianMutation

mutation = GaussianMutation(sigma=0.1)
```

### 4. 交叉操作 (Crossover Operators)

#### 均匀交叉 (Uniform Crossover)
每个基因50%概率来自任一父代。

```python
from contextmind.auto_optimize import UniformCrossover

crossover = UniformCrossover(crossover_rate=0.5)
```

#### 单点交叉 (Single-Point Crossover)
在随机点切分并交换基因。

```python
from contextmind.auto_optimize import SinglePointCrossover

crossover = SinglePointCrossover()
```

### 5. 评估器 (Evaluators)

#### 基础评估器
自定义评估逻辑。

```python
class CustomEvaluator(BaseEvaluator):
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        # 自定义评估逻辑
        score = compute_fitness(candidate.genome)
        return FitnessScore(value=score)
```

#### 缓存评估器
避免重复评估。

```python
from contextmind.auto_optimize import CachedEvaluator

cached_eval = CachedEvaluator(base_evaluator)
```

#### 复合评估器
多目标优化。

```python
from contextmind.auto_optimize import CompositeEvaluator

evaluators = {
    "accuracy": AccuracyEvaluator(),
    "speed": SpeedEvaluator(),
}
weights = {"accuracy": 0.7, "speed": 0.3}

composite = CompositeEvaluator(evaluators, weights)
```

## 高级用法

### 自定义初始化器

```python
def custom_initializer():
    """创建特定范围的初始参数"""
    return {
        "learning_rate": random.uniform(0.001, 0.1),
        "batch_size": random.choice([16, 32, 64, 128]),
        "num_layers": random.randint(1, 5),
        "activation": random.choice(["relu", "tanh", "sigmoid"]),
    }

evolver = StrategyEvolver(
    config=config,
    evaluator=evaluator,
    initializer=custom_initializer
)
```

### 自定义操作符

```python
from contextmind.auto_optimize import MutationOperator, Candidate

class CustomMutation:
    def mutate(self, candidate: Candidate) -> Candidate:
        mutated = candidate.clone()
        # 自定义变异逻辑
        if "learning_rate" in mutated.genome:
            mutated.genome["learning_rate"] *= random.uniform(0.5, 2.0)
        return mutated

evolver = StrategyEvolver(
    config=config,
    evaluator=evaluator,
    mutation_operator=CustomMutation()
)
```

### 多目标优化

```python
# 定义多个目标
class AccuracyEvaluator(BaseEvaluator):
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        accuracy = compute_accuracy(candidate.genome)
        return FitnessScore(value=accuracy)

class SpeedEvaluator(BaseEvaluator):
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        speed = compute_speed(candidate.genome)
        return FitnessScore(value=speed)

# 组合评估器
composite_eval = CompositeEvaluator(
    evaluators={
        "accuracy": AccuracyEvaluator(),
        "speed": SpeedEvaluator(),
    },
    weights={
        "accuracy": 0.6,  # 更重视准确性
        "speed": 0.4,     # 次要考虑速度
    }
)
```

### 查看进化历史

```python
best = await evolver.evolve()

# 获取进化历史
history = evolver.get_history()

for gen_info in history:
    print(f"Generation {gen_info['generation']}:")
    print(f"  Best: {gen_info['best_fitness']}")
    print(f"  Avg:  {gen_info['stats']['avg']}")
    print(f"  Std:  {gen_info['stats']['std']}")
```

## 应用场景

### 1. 超参数调优

```python
class HyperparameterEvaluator(BaseEvaluator):
    def __init__(self, train_data, val_data):
        self.train_data = train_data
        self.val_data = val_data
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        # 使用候选参数训练模型
        model = train_model(
            self.train_data,
            learning_rate=candidate.genome["learning_rate"],
            batch_size=candidate.genome["batch_size"],
            num_layers=candidate.genome["num_layers"]
        )
        
        # 在验证集上评估
        accuracy = evaluate_model(model, self.val_data)
        
        return FitnessScore(value=accuracy)
```

### 2. 提示词优化

```python
class PromptEvaluator(BaseEvaluator):
    def __init__(self, llm_client, test_cases):
        self.llm = llm_client
        self.test_cases = test_cases
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        prompt = candidate.genome["prompt_template"]
        
        # 在测试用例上评估提示词
        total_score = 0
        for test_case in self.test_cases:
            response = await self.llm.generate(
                prompt.format(**test_case["input"])
            )
            score = compute_quality(response, test_case["expected"])
            total_score += score
        
        avg_score = total_score / len(self.test_cases)
        return FitnessScore(value=avg_score)
```

### 3. 策略配置优化

```python
class StrategyEvaluator(BaseEvaluator):
    def __init__(self, context_engine, benchmark_queries):
        self.engine = context_engine
        self.queries = benchmark_queries
    
    async def evaluate(self, candidate: Candidate) -> FitnessScore:
        # 应用候选配置
        self.engine.update_config(candidate.genome)
        
        # 在基准查询上测试
        total_quality = 0
        total_latency = 0
        
        for query in self.queries:
            result = await self.engine.optimize(query)
            total_quality += result.quality_score
            total_latency += result.latency
        
        # 综合评分
        avg_quality = total_quality / len(self.queries)
        avg_latency = total_latency / len(self.queries)
        
        # 质量优先，同时考虑延迟
        score = avg_quality - 0.1 * avg_latency
        
        return FitnessScore(
            value=score,
            objectives={
                "quality": avg_quality,
                "latency": -avg_latency
            }
        )
```

## 性能优化建议

### 1. 使用缓存评估器
```python
from contextmind.auto_optimize import CachedEvaluator

cached_evaluator = CachedEvaluator(your_evaluator)
```

### 2. 调整群体大小
- 小问题: 10-20个候选
- 中等问题: 20-50个候选
- 大问题: 50-100个候选

### 3. 早停策略
```python
config = EvolutionConfig(
    convergence_threshold=1e-4,      # 改进小于此值视为收敛
    max_stagnant_generations=10,     # 连续10代无改进则停止
)
```

### 4. 精英保留
```python
config = EvolutionConfig(
    elite_size=2,  # 保留最优的2个候选
)
```

## 设计原则

1. **模块化**: 每个组件可独立替换
2. **可扩展**: 易于添加新的操作符和评估器
3. **类型安全**: 使用Protocol和dataclass
4. **简洁**: 避免过度复杂的抽象
5. **实用**: 注重实际应用价值

## 参考资料

### 进化算法基础
- Eiben & Smith (2015): Introduction to Evolutionary Computing
- Goldberg (1989): Genetic Algorithms in Search, Optimization, and Machine Learning

### 应用于机器学习
- Bergstra & Bengio (2012): Random Search for Hyper-Parameter Optimization
- Hutter et al. (2011): Sequential Model-Based Optimization for General Algorithm Configuration

### AlphaEvolve/ThetaEvolve相关
- Lehman et al. (2022): Evolution through Large Models
- Real et al. (2020): AutoML-Zero: Evolving Code that Learns

## 未来扩展

可能的扩展方向：

1. **LLM驱动的变异**: 使用大语言模型生成代码/提示词变异
2. **自适应操作符**: 根据进化进度动态调整变异/交叉率
3. **并行评估**: 支持批量并行评估候选
4. **元学习**: 学习最优的进化参数
5. **多种群协同**: 多个群体并行进化并交换信息

## 常见问题

**Q: 如何选择合适的群体大小？**
A: 取决于问题复杂度。简单问题10-20个候选即可，复杂问题可能需要50-100个。

**Q: 变异率和交叉率如何设置？**
A: 常用值：变异率0.05-0.2，交叉率0.6-0.9。可以实验调优。

**Q: 如何避免早熟收敛？**
A: 增加群体大小、提高变异率、使用多样性维护机制。

**Q: 评估成本很高怎么办？**
A: 使用CachedEvaluator缓存、减少群体大小、设置早停条件。

**Q: 如何处理离散参数？**
A: 在初始化器中使用random.choice，在变异器中随机替换为其他允许值。
