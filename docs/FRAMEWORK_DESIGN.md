# ContextMind 通用上下文优化框架设计

## 1. 设计目标

将 ContextMind 改造为一个**通用的、可扩展的上下文优化框架**，支持：

1. **灵活的Pipeline配置**: 可自由组合、替换各个处理步骤
2. **多策略支持**: 同一步骤支持多种实现策略（如检索策略、Prompt策略等）
3. **易于扩展**: 新的论文算法可以快速集成
4. **向后兼容**: 保持现有功能正常工作
5. **高性能**: 支持异步处理和并发优化

## 2. 核心架构

### 2.1 四层架构设计

```
┌─────────────────────────────────────────────────────────┐
│                    Application Layer                     │
│         (ContextEngine, Demos, Custom Applications)      │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                     Pipeline Layer                       │
│    (ContextOptimizationPipeline, StepRegistry, etc.)    │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      Step Layer                          │
│  (InputValidation, ContextCollection, PromptGen, etc.)  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                    Strategy Layer                        │
│   (RetrievalStrategy, PromptStrategy, IntegrationStrategy)│
└─────────────────────────────────────────────────────────┘
```

### 2.2 目录结构设计

```
contextmind/
├── __init__.py
├── client.py                    # LLM客户端（保持不变）
├── logger.py                    # 日志模块（保持不变）
│
├── core/                        # 核心框架代码
│   ├── __init__.py
│   ├── pipeline.py              # Pipeline核心实现
│   ├── context.py               # 上下文数据结构
│   ├── registry.py              # 注册表管理
│   └── exceptions.py            # 自定义异常
│
├── steps/                       # 步骤抽象层
│   ├── __init__.py
│   ├── base.py                  # BaseStep基类
│   ├── validation.py            # 输入验证步骤
│   ├── session.py               # 会话管理步骤
│   ├── collection.py            # 上下文收集步骤
│   ├── integration.py           # 上下文整合步骤
│   ├── prompt.py                # Prompt生成步骤
│   ├── generation.py            # 响应生成步骤
│   ├── postprocess.py           # 后处理步骤
│   ├── update.py                # 状态更新步骤
│   ├── extraction.py            # 知识提取步骤
│   ├── summarization.py         # 总结步骤
│   └── packaging.py             # 结果封装步骤
│
├── strategies/                  # 策略实现层
│   ├── __init__.py
│   ├── base.py                  # 策略基类
│   │
│   ├── retrieval/               # 检索策略
│   │   ├── __init__.py
│   │   ├── keyword.py           # 关键词检索
│   │   ├── semantic.py          # 语义检索
│   │   ├── vector.py            # 向量检索（新增）
│   │   └── hybrid.py            # 混合检索（新增）
│   │
│   ├── prompt/                  # Prompt策略
│   │   ├── __init__.py
│   │   ├── template.py          # 模板Prompt
│   │   ├── agent.py             # Agent Prompt
│   │   ├── cot.py               # Chain-of-Thought（新增）
│   │   └── tot.py               # Tree-of-Thought（新增）
│   │
│   ├── integration/             # 整合策略
│   │   ├── __init__.py
│   │   ├── template.py          # 模板整合
│   │   ├── graph.py             # 图整合（新增）
│   │   └── hierarchical.py      # 层次整合（新增）
│   │
│   └── extraction/              # 提取策略
│       ├── __init__.py
│       ├── llm.py               # LLM提取
│       ├── rule.py              # 规则提取
│       └── hybrid.py            # 混合提取
│
├── components/                  # 可复用组件
│   ├── __init__.py
│   ├── scorers.py               # 相关性评分器
│   ├── rankers.py               # 排序器
│   ├── filters.py               # 过滤器
│   └── validators.py            # 验证器
│
├── engine.py                    # 高层封装（向后兼容）
└── legacy/                      # 遗留代码（可选）
    └── old_engine.py            # 原始实现备份
```

## 3. 核心类设计

### 3.1 Pipeline上下文

```python
@dataclass
class PipelineContext:
    """Pipeline执行上下文，在各步骤间传递数据"""
    # 输入数据
    user_input: str
    
    # 会话相关
    session: Optional[Session] = None
    session_id: Optional[str] = None
    
    # 收集的上下文
    history_text: str = ""
    memory_text: str = ""
    memory_hits: List[str] = field(default_factory=list)
    
    # 整合的知识
    integrated_knowledge: Optional[IntegratedKnowledge] = None
    
    # 生成的prompt
    prompt: str = ""
    
    # 生成的响应
    response: str = ""
    
    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 配置
    config: Dict[str, Any] = field(default_factory=dict)
    
    def set(self, key: str, value: Any):
        """设置上下文值"""
        
    def get(self, key: str, default: Any = None) -> Any:
        """获取上下文值"""
```

### 3.2 Pipeline核心

```python
class ContextOptimizationPipeline:
    """上下文优化Pipeline核心类"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.steps: List[Tuple[str, BaseStep]] = []
        self.config = config or {}
        self._step_registry = StepRegistry()
        
    def add_step(
        self, 
        name: str, 
        step: BaseStep, 
        position: Optional[int] = None
    ) -> 'ContextOptimizationPipeline':
        """添加步骤到Pipeline"""
        
    def remove_step(self, name: str) -> 'ContextOptimizationPipeline':
        """移除步骤"""
        
    def replace_step(
        self, 
        name: str, 
        new_step: BaseStep
    ) -> 'ContextOptimizationPipeline':
        """替换步骤"""
        
    async def execute(
        self, 
        user_input: str, 
        **kwargs
    ) -> PipelineContext:
        """执行完整Pipeline"""
        context = PipelineContext(user_input=user_input, config=kwargs)
        
        for step_name, step in self.steps:
            try:
                context = await step.execute(context)
            except Exception as e:
                # 错误处理逻辑
                pass
                
        return context
        
    @classmethod
    def create_default(cls, **config) -> 'ContextOptimizationPipeline':
        """创建默认Pipeline配置"""
        pipeline = cls(config)
        # 添加默认步骤序列
        pipeline.add_step("validation", InputValidationStep())
        pipeline.add_step("session", SessionManagementStep())
        pipeline.add_step("collection", ContextCollectionStep())
        # ... 其他步骤
        return pipeline
```

### 3.3 步骤基类

```python
class BaseStep(ABC):
    """步骤基类"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.name = self.__class__.__name__
        
    @abstractmethod
    async def execute(self, context: PipelineContext) -> PipelineContext:
        """执行步骤，返回更新后的上下文"""
        pass
        
    def validate_input(self, context: PipelineContext) -> bool:
        """验证输入是否满足步骤要求"""
        return True
        
    def get_dependencies(self) -> List[str]:
        """返回依赖的步骤名称列表"""
        return []
        
    def should_execute(self, context: PipelineContext) -> bool:
        """判断是否应该执行此步骤"""
        return True
```

### 3.4 策略基类

```python
class BaseStrategy(ABC):
    """策略基类"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        
    @abstractmethod
    async def apply(self, context: Any) -> Any:
        """应用策略"""
        pass
        
    def get_config(self) -> Dict:
        """获取配置"""
        return self.config
        
    def set_config(self, config: Dict):
        """设置配置"""
        self.config.update(config)
```

### 3.5 注册表管理

```python
class StepRegistry:
    """步骤注册表"""
    _steps: Dict[str, Type[BaseStep]] = {}
    
    @classmethod
    def register(cls, name: str, step_class: Type[BaseStep]):
        """注册步骤"""
        cls._steps[name] = step_class
        
    @classmethod
    def get(cls, name: str) -> Type[BaseStep]:
        """获取步骤类"""
        return cls._steps.get(name)
        
    @classmethod
    def create(cls, name: str, **config) -> BaseStep:
        """创建步骤实例"""
        step_class = cls.get(name)
        if not step_class:
            raise ValueError(f"Step {name} not registered")
        return step_class(config=config)

class StrategyRegistry:
    """策略注册表"""
    _strategies: Dict[str, Dict[str, Type[BaseStrategy]]] = {}
    
    @classmethod
    def register(
        cls, 
        category: str, 
        name: str, 
        strategy_class: Type[BaseStrategy]
    ):
        """注册策略"""
        if category not in cls._strategies:
            cls._strategies[category] = {}
        cls._strategies[category][name] = strategy_class
        
    @classmethod
    def get(cls, category: str, name: str) -> Type[BaseStrategy]:
        """获取策略类"""
        return cls._strategies.get(category, {}).get(name)
        
    @classmethod
    def create(cls, category: str, name: str, **config) -> BaseStrategy:
        """创建策略实例"""
        strategy_class = cls.get(category, name)
        if not strategy_class:
            raise ValueError(f"Strategy {category}/{name} not registered")
        return strategy_class(config=config)
```

## 4. 使用示例

### 4.1 使用默认Pipeline

```python
from contextmind import Client
from contextmind.core.pipeline import ContextOptimizationPipeline

# 创建客户端
client = Client()

# 创建默认Pipeline
pipeline = ContextOptimizationPipeline.create_default(
    app_name="my-app",
    user_id="user-123",
    llm_client=client,
    max_recent_events=6
)

# 执行Pipeline
result = await pipeline.execute("你好，有什么可以帮助的？")
print(result.response)
```

### 4.2 自定义Pipeline

```python
from contextmind.core.pipeline import ContextOptimizationPipeline
from contextmind.steps import InputValidationStep, ContextCollectionStep
from contextmind.strategies.retrieval import VectorRetrievalStrategy
from contextmind.strategies.prompt import ChainOfThoughtPromptStrategy

# 创建自定义Pipeline
pipeline = ContextOptimizationPipeline()

# 添加步骤
pipeline.add_step("validation", InputValidationStep())

# 添加带自定义策略的步骤
collection_step = ContextCollectionStep(
    retrieval_strategy=VectorRetrievalStrategy(
        embedding_model="text-embedding-ada-002"
    )
)
pipeline.add_step("collection", collection_step)

# 使用Chain-of-Thought Prompt策略
prompt_step = PromptGenerationStep(
    prompt_strategy=ChainOfThoughtPromptStrategy()
)
pipeline.add_step("prompt", prompt_step)

# 执行
result = await pipeline.execute(user_input)
```

### 4.3 替换单个步骤

```python
from contextmind.strategies.prompt import TreeOfThoughtPromptStrategy

# 替换Prompt生成策略
new_prompt_step = PromptGenerationStep(
    prompt_strategy=TreeOfThoughtPromptStrategy()
)
pipeline.replace_step("prompt", new_prompt_step)
```

### 4.4 集成新的论文算法

```python
from contextmind.strategies.base import BaseStrategy

# 实现新的检索策略
class DensePassageRetrievalStrategy(BaseStrategy):
    """DPR检索策略"""
    
    async def apply(self, context: Dict) -> Dict:
        query = context['query']
        # DPR实现逻辑
        results = await self._dpr_retrieve(query)
        return {
            'memories': results,
            'scores': [r.score for r in results]
        }
        
    async def _dpr_retrieve(self, query: str):
        # 具体实现
        pass

# 注册策略
StrategyRegistry.register(
    "retrieval", 
    "dpr", 
    DensePassageRetrievalStrategy
)

# 使用新策略
dpr_strategy = StrategyRegistry.create(
    "retrieval", 
    "dpr", 
    model_name="facebook/dpr-ctx_encoder-single-nq-base"
)
collection_step = ContextCollectionStep(retrieval_strategy=dpr_strategy)
```

## 5. 向后兼容

为了保持向后兼容，原有的 `ContextEngine` 将作为 Pipeline 的高层封装：

```python
class ContextEngine:
    """高层封装，保持API兼容"""
    
    def __init__(self, **config):
        # 内部使用Pipeline
        self._pipeline = ContextOptimizationPipeline.create_default(**config)
        # 保留原有配置属性
        self.app_name = config.get('app_name')
        self.user_id = config.get('user_id')
        # ...
        
    async def process_turn(self, user_input: str) -> ContextTurnResult:
        """保持原有API"""
        context = await self._pipeline.execute(user_input)
        # 转换为原有的返回格式
        return ContextTurnResult(
            prompt=context.prompt,
            response=context.response,
            memory_hits=context.memory_hits,
            # ...
        )
```

## 6. 扩展指南

### 6.1 添加新步骤

1. 继承 `BaseStep`
2. 实现 `execute()` 方法
3. 可选：实现 `validate_input()`, `get_dependencies()`
4. 注册步骤（可选）

### 6.2 添加新策略

1. 继承 `BaseStrategy`
2. 实现 `apply()` 方法
3. 注册策略到 `StrategyRegistry`

### 6.3 自定义Pipeline

1. 创建 `ContextOptimizationPipeline` 实例
2. 通过 `add_step()` 添加步骤
3. 通过 `replace_step()` 替换步骤
4. 调用 `execute()` 运行

## 7. 性能优化

### 7.1 并发执行

支持在步骤内部使用 `asyncio.gather` 并发执行子任务：

```python
class ContextCollectionStep(BaseStep):
    async def execute(self, context: PipelineContext) -> PipelineContext:
        # 并发收集多个上下文源
        history, memory, profile = await asyncio.gather(
            self._collect_history(context),
            self._retrieve_memory(context),
            self._get_profile(context)
        )
        # ...
```

### 7.2 步骤级缓存

支持步骤级缓存以避免重复计算：

```python
class CachedStep(BaseStep):
    def __init__(self, **config):
        super().__init__(config)
        self._cache = {}
        
    async def execute(self, context: PipelineContext):
        cache_key = self._get_cache_key(context)
        if cache_key in self._cache:
            return self._cache[cache_key]
        result = await self._do_execute(context)
        self._cache[cache_key] = result
        return result
```

## 8. 总结

这个框架设计提供了：

1. **清晰的分层架构**: Pipeline → Step → Strategy
2. **高度的可扩展性**: 轻松添加新步骤和策略
3. **灵活的配置**: 支持多种组合方式
4. **向后兼容**: 保持现有API不变
5. **性能优化**: 异步支持和并发优化

通过这个框架，可以快速集成各种上下文优化的论文方案，打造一个通用的上下文优化平台。
