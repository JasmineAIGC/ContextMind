# ContextMind 框架实现路线图

> 本文档提供从当前实现到通用框架的渐进式改造路线图

## 改造原则

1. **渐进式改造**: 分阶段实施，每个阶段都保持可用性
2. **向后兼容**: 保持现有API不变
3. **测试驱动**: 每个改造步骤都有相应测试
4. **文档先行**: 先完善文档，再开始实现

## 阶段划分

### 第一阶段: 准备工作（已完成✅）

**目标**: 深入理解现有系统，完成架构设计

**任务**:
- [x] 分析现有代码结构
- [x] 识别11个核心步骤
- [x] 梳理60+个操作
- [x] 设计通用框架架构
- [x] 编写设计文档
- [x] 编写集成指南

**产出**:
- 上下文优化步骤总结文档
- 框架设计文档
- 集成指南
- 技术分析文档

---

### 第二阶段: 核心抽象层

**目标**: 建立框架的核心抽象，不影响现有功能

**估计时间**: 1-2周

#### 2.1 创建核心数据结构

**文件**: `contextmind/core/context.py`

```python
@dataclass
class PipelineContext:
    """Pipeline执行上下文"""
    user_input: str
    session: Optional[Session] = None
    session_id: Optional[str] = None
    history_text: str = ""
    memory_text: str = ""
    memory_hits: List[str] = field(default_factory=list)
    integrated_knowledge: Optional[IntegratedKnowledge] = None
    prompt: str = ""
    response: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
```

**测试**: 测试数据结构的创建和访问

#### 2.2 创建基类

**文件**: `contextmind/steps/base.py`

```python
class BaseStep(ABC):
    """步骤基类"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.name = self.__class__.__name__
        
    @abstractmethod
    async def execute(self, context: PipelineContext) -> PipelineContext:
        pass
```

**文件**: `contextmind/strategies/base.py`

```python
class BaseStrategy(ABC):
    """策略基类"""
    
    @abstractmethod
    async def apply(self, context: Any) -> Any:
        pass
```

**测试**: 测试基类的继承和方法调用

#### 2.3 创建注册表

**文件**: `contextmind/core/registry.py`

```python
class StepRegistry:
    """步骤注册表"""
    _steps: Dict[str, Type[BaseStep]] = {}
    
    @classmethod
    def register(cls, name: str, step_class: Type[BaseStep]):
        cls._steps[name] = step_class
    
    @classmethod
    def create(cls, name: str, **config) -> BaseStep:
        step_class = cls._steps.get(name)
        if not step_class:
            raise ValueError(f"Step {name} not registered")
        return step_class(config=config)

class StrategyRegistry:
    """策略注册表"""
    # 类似实现
```

**测试**: 测试注册和创建功能

---

### 第三阶段: Pipeline实现

**目标**: 实现Pipeline管理器，建立步骤编排能力

**估计时间**: 1-2周

#### 3.1 实现Pipeline核心

**文件**: `contextmind/core/pipeline.py`

```python
class ContextOptimizationPipeline:
    """上下文优化Pipeline"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.steps: List[Tuple[str, BaseStep]] = []
        self.config = config or {}
        
    def add_step(
        self, 
        name: str, 
        step: BaseStep, 
        position: Optional[int] = None
    ) -> 'ContextOptimizationPipeline':
        if position is None:
            self.steps.append((name, step))
        else:
            self.steps.insert(position, (name, step))
        return self
        
    def remove_step(self, name: str) -> 'ContextOptimizationPipeline':
        self.steps = [(n, s) for n, s in self.steps if n != name]
        return self
        
    def replace_step(
        self, 
        name: str, 
        new_step: BaseStep
    ) -> 'ContextOptimizationPipeline':
        for i, (n, s) in enumerate(self.steps):
            if n == name:
                self.steps[i] = (name, new_step)
                break
        return self
        
    async def execute(
        self, 
        user_input: str, 
        **kwargs
    ) -> PipelineContext:
        context = PipelineContext(user_input=user_input, config=kwargs)
        
        for step_name, step in self.steps:
            try:
                logger.debug(f"执行步骤: {step_name}")
                context = await step.execute(context)
            except Exception as e:
                logger.error(f"步骤 {step_name} 执行失败: {e}")
                if kwargs.get('strict_mode', False):
                    raise
                # 非严格模式下继续执行
                
        return context
```

**测试**: 
- 测试步骤添加、删除、替换
- 测试Pipeline执行流程
- 测试错误处理

#### 3.2 创建默认Pipeline

```python
@classmethod
def create_default(cls, **config) -> 'ContextOptimizationPipeline':
    """创建默认Pipeline配置"""
    pipeline = cls(config)
    
    # 添加11个默认步骤
    pipeline.add_step("validation", InputValidationStep())
    pipeline.add_step("session", SessionManagementStep())
    pipeline.add_step("collection", ContextCollectionStep())
    pipeline.add_step("integration", ContextIntegrationStep())
    pipeline.add_step("prompt", PromptGenerationStep())
    pipeline.add_step("generation", ResponseGenerationStep())
    pipeline.add_step("postprocess", PostProcessingStep())
    pipeline.add_step("update", StateUpdateStep())
    pipeline.add_step("extraction", KnowledgeExtractionStep())
    pipeline.add_step("summarization", SummarizationStep())
    pipeline.add_step("packaging", ResultPackagingStep())
    
    return pipeline
```

---

### 第四阶段: 步骤实现

**目标**: 将现有engine.py的逻辑分解为11个独立步骤

**估计时间**: 2-3周

#### 4.1 步骤1: InputValidationStep

**文件**: `contextmind/steps/validation.py`

```python
class InputValidationStep(BaseStep):
    """输入验证与预处理步骤"""
    
    async def execute(self, context: PipelineContext) -> PipelineContext:
        # 从 engine.py 的 process_turn 开头提取验证逻辑
        user_input = context.user_input.strip()
        
        if not user_input:
            raise ValueError("User input must be non-empty.")
        
        # 可选：长度检查
        max_length = self.config.get('max_length', 10000)
        if len(user_input) > max_length:
            user_input = user_input[:max_length]
        
        context.user_input = user_input
        return context
```

#### 4.2 步骤2: SessionManagementStep

**文件**: `contextmind/steps/session.py`

```python
class SessionManagementStep(BaseStep):
    """会话管理步骤"""
    
    async def execute(self, context: PipelineContext) -> PipelineContext:
        # 从 engine.py 的 _ensure_session 提取逻辑
        session_service = context.config.get('session_service')
        session_id = context.session_id
        
        if session_id:
            try:
                session = await session_service.get_session(...)
                if session:
                    context.session = session
                    return context
            except Exception:
                pass
        
        # 创建新session
        session = await session_service.create_session(...)
        context.session = session
        context.session_id = session.id
        
        return context
```

#### 4.3 步骤3-11: 类似方式实现其他步骤

每个步骤都从 `engine.py` 提取相应逻辑，独立实现。

**测试策略**:
- 每个步骤单独测试
- 测试步骤间的数据传递
- 测试步骤的错误处理

---

### 第五阶段: 策略实现

**目标**: 将关键功能抽象为可替换的策略

**估计时间**: 2-3周

#### 5.1 检索策略

**文件**: `contextmind/strategies/retrieval/`

- `keyword.py` - 关键词检索（当前实现）
- `semantic.py` - 语义检索
- `vector.py` - 向量检索（新增）
- `hybrid.py` - 混合检索（新增）

#### 5.2 Prompt策略

**文件**: `contextmind/strategies/prompt/`

- `template.py` - 模板Prompt（当前实现）
- `agent.py` - Agent Prompt（当前实现）
- `cot.py` - Chain-of-Thought（新增）
- `tot.py` - Tree-of-Thought（新增）

#### 5.3 其他策略

按需实现整合策略、提取策略等

---

### 第六阶段: 重构ContextEngine

**目标**: 将ContextEngine改造为Pipeline的高层封装

**估计时间**: 1周

```python
# contextmind/engine.py

class ContextEngine:
    """
    上下文引擎 - Pipeline的高层封装
    保持API向后兼容
    """
    
    def __init__(self, **config):
        # 内部使用Pipeline
        self._pipeline = ContextOptimizationPipeline.create_default(**config)
        
        # 保留原有属性（向后兼容）
        self.app_name = config.get('app_name')
        self.user_id = config.get('user_id')
        self._llm_client = config.get('llm_client')
        # ...
        
    async def process_turn(self, user_input: str) -> ContextTurnResult:
        """保持原有API不变"""
        # 执行Pipeline
        context = await self._pipeline.execute(
            user_input,
            app_name=self.app_name,
            user_id=self.user_id,
            llm_client=self._llm_client,
            # ... 传递所有必要配置
        )
        
        # 转换为原有返回格式
        return ContextTurnResult(
            prompt=context.prompt,
            response=context.response,
            memory_hits=context.memory_hits,
            history_count=context.metadata.get('history_count', 0),
            # ...
        )
    
    # 保留所有原有的公共方法
    async def seed_memory(self, facts: List[str]):
        """向后兼容的方法"""
        # 可以调用Pipeline中的相应步骤
        pass
```

**测试**:
- 运行所有原有测试，确保API兼容
- 运行demo验证功能正常

---

### 第七阶段: 组件库

**目标**: 提取可复用的组件

**估计时间**: 1周

**文件**: `contextmind/components/`

- `scorers.py` - 相关性评分器
- `rankers.py` - 排序器
- `filters.py` - 过滤器
- `validators.py` - 验证器

这些组件可以被多个步骤和策略复用。

---

### 第八阶段: 示例和集成

**目标**: 提供示例实现，验证可扩展性

**估计时间**: 1-2周

#### 8.1 实现DPR检索示例

按照集成指南实现DPR检索策略

#### 8.2 实现Chain-of-Thought示例

实现CoT Prompt策略

#### 8.3 更新Demo

更新demo以展示新特性：
- 演示策略替换
- 演示自定义Pipeline

---

### 第九阶段: 文档和测试

**目标**: 完善文档和测试覆盖

**估计时间**: 1周

- 更新API文档
- 编写教程
- 提高测试覆盖率到80%+
- 性能测试和优化

---

### 第十阶段: 发布

**目标**: 正式发布通用框架版本

- 版本号: v2.0.0
- 发布PyPI包
- 发布文档网站
- 撰写博客文章

---

## 优先级建议

### P0 (必须完成)
- 第一阶段（已完成✅）
- 第二阶段：核心抽象
- 第三阶段：Pipeline实现
- 第四阶段：步骤实现
- 第六阶段：重构ContextEngine

### P1 (重要)
- 第五阶段：策略实现
- 第九阶段：文档和测试

### P2 (可选)
- 第七阶段：组件库
- 第八阶段：示例集成

---

## 风险和缓解

### 风险1: 破坏现有功能

**缓解**: 
- 渐进式改造
- 保持API向后兼容
- 每个阶段都进行回归测试

### 风险2: 性能下降

**缓解**:
- 每个阶段进行性能测试
- 保持异步设计
- 使用性能分析工具

### 风险3: 过度设计

**缓解**:
- 遵循YAGNI原则（You Aren't Gonna Need It）
- 优先实现核心功能
- 根据实际需求迭代

---

## 成功标准

### 技术指标
- ✅ 所有原有功能正常工作
- ✅ 测试覆盖率 > 80%
- ✅ 性能不低于原实现
- ✅ 可以在5分钟内集成新策略

### 文档指标
- ✅ 完整的API文档
- ✅ 至少3个集成示例
- ✅ 详细的架构设计文档

### 可用性指标
- ✅ 清晰的错误信息
- ✅ 友好的API设计
- ✅ 丰富的示例代码

---

## 下一步行动

1. **Review设计文档**: 与团队review设计，收集反馈
2. **创建GitHub Issues**: 为每个阶段创建对应的issue
3. **设置Milestone**: 为关键阶段设置里程碑
4. **开始实现**: 从第二阶段开始实施

---

## 参考资料

- [上下文优化步骤总结](上下文优化步骤总结.md)
- [框架设计文档](FRAMEWORK_DESIGN.md)
- [集成指南](INTEGRATION_GUIDE.md)
- [技术分析](CONTEXT_OPTIMIZATION_ANALYSIS.md)
