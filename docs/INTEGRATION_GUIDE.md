# 集成新算法指南

本文档介绍如何在 ContextMind 框架中集成新的上下文优化算法和论文方案。

## 1. 集成流程概览

```
1. 理解算法原理
   ↓
2. 确定集成点（步骤/策略）
   ↓
3. 实现策略类
   ↓
4. 注册策略
   ↓
5. 配置使用
   ↓
6. 测试验证
```

## 2. 常见集成场景

### 2.1 集成新的检索算法

**适用场景**: RAG、DPR、ColBERT、向量检索等

**集成步骤**:

#### 步骤1: 创建检索策略类

```python
# contextmind/strategies/retrieval/dpr.py

from typing import List, Dict, Any
from contextmind.strategies.base import BaseStrategy

class DensePassageRetrievalStrategy(BaseStrategy):
    """
    Dense Passage Retrieval (DPR) 检索策略
    
    论文: https://arxiv.org/abs/2004.04906
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        # 初始化DPR模型
        self.encoder = self._load_encoder()
        self.index = self._load_index()
        
    def _load_encoder(self):
        """加载DPR编码器"""
        from transformers import DPRQuestionEncoder, DPRQuestionEncoderTokenizer
        
        model_name = self.config.get(
            'model_name', 
            'facebook/dpr-question_encoder-single-nq-base'
        )
        tokenizer = DPRQuestionEncoderTokenizer.from_pretrained(model_name)
        model = DPRQuestionEncoder.from_pretrained(model_name)
        
        return {'tokenizer': tokenizer, 'model': model}
    
    def _load_index(self):
        """加载或构建向量索引"""
        # FAISS或其他向量索引
        pass
        
    async def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        应用DPR检索
        
        Args:
            context: 包含 'query', 'app_name', 'user_id' 等信息
            
        Returns:
            包含 'memories', 'scores' 等结果
        """
        query = context['query']
        top_k = self.config.get('top_k', 5)
        
        # 1. 编码查询
        query_embedding = self._encode_query(query)
        
        # 2. 检索
        results = self._search(query_embedding, top_k)
        
        # 3. 格式化结果
        memories = self._format_results(results)
        
        return {
            'memories': memories,
            'scores': [r['score'] for r in results],
            'method': 'dpr'
        }
    
    def _encode_query(self, query: str):
        """编码查询文本"""
        import torch
        
        tokenizer = self.encoder['tokenizer']
        model = self.encoder['model']
        
        inputs = tokenizer(query, return_tensors='pt', truncation=True)
        with torch.no_grad():
            embeddings = model(**inputs).pooler_output
        
        return embeddings.numpy()
    
    def _search(self, query_embedding, top_k: int):
        """在索引中检索"""
        # 使用FAISS或其他向量数据库
        distances, indices = self.index.search(query_embedding, top_k)
        
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            results.append({
                'id': idx,
                'score': float(dist),
                'content': self._get_content(idx)
            })
        
        return results
    
    def _format_results(self, results):
        """格式化为框架期望的格式"""
        from google.genai.types import Content, Part
        
        memories = []
        for r in results:
            # 转换为ADK Memory格式
            memory = {
                'content': Content(role='system', parts=[Part(text=r['content'])]),
                'score': r['score'],
                'timestamp': None  # 可选
            }
            memories.append(memory)
        
        return memories
```

#### 步骤2: 注册策略

```python
# contextmind/strategies/retrieval/__init__.py

from .keyword import KeywordRetrievalStrategy
from .semantic import SemanticRetrievalStrategy
from .dpr import DensePassageRetrievalStrategy
from contextmind.core.registry import StrategyRegistry

# 注册所有检索策略
StrategyRegistry.register('retrieval', 'keyword', KeywordRetrievalStrategy)
StrategyRegistry.register('retrieval', 'semantic', SemanticRetrievalStrategy)
StrategyRegistry.register('retrieval', 'dpr', DensePassageRetrievalStrategy)
```

#### 步骤3: 使用新策略

```python
from contextmind.core.pipeline import ContextOptimizationPipeline
from contextmind.steps.collection import ContextCollectionStep
from contextmind.core.registry import StrategyRegistry

# 创建DPR检索策略
dpr_strategy = StrategyRegistry.create(
    'retrieval', 
    'dpr',
    model_name='facebook/dpr-question_encoder-single-nq-base',
    top_k=5
)

# 创建使用DPR的收集步骤
collection_step = ContextCollectionStep(
    retrieval_strategy=dpr_strategy
)

# 添加到Pipeline
pipeline = ContextOptimizationPipeline()
pipeline.add_step('collection', collection_step)
```

### 2.2 集成新的Prompt优化算法

**适用场景**: Chain-of-Thought、Tree-of-Thought、ReAct等

**集成步骤**:

#### 步骤1: 创建Prompt策略类

```python
# contextmind/strategies/prompt/cot.py

from typing import Dict, Any
from contextmind.strategies.base import BaseStrategy
from contextmind.core.context import IntegratedKnowledge

class ChainOfThoughtPromptStrategy(BaseStrategy):
    """
    Chain-of-Thought Prompt 策略
    
    论文: https://arxiv.org/abs/2201.11903
    """
    
    async def apply(self, context: Dict[str, Any]) -> str:
        """
        生成CoT风格的prompt
        
        Args:
            context: 包含 'knowledge' (IntegratedKnowledge对象) 等信息
            
        Returns:
            生成的prompt字符串
        """
        knowledge: IntegratedKnowledge = context['knowledge']
        
        # 构建CoT prompt
        prompt_parts = []
        
        # 1. 系统角色
        prompt_parts.append(knowledge.base_system_prompt)
        
        # 2. 上下文信息
        if knowledge.history_text:
            prompt_parts.append(f"\n【对话历史】\n{knowledge.history_text}")
        
        if knowledge.memory_text:
            prompt_parts.append(f"\n【相关记忆】\n{knowledge.memory_text}")
        
        # 3. 当前问题
        prompt_parts.append(f"\n【用户输入】\n{knowledge.user_input}")
        
        # 4. CoT引导
        cot_instruction = """
        
【思考步骤】
请按照以下步骤思考并回复：
1. 理解用户意图：用户想要什么？
2. 分析相关信息：历史记忆中有哪些相关信息？
3. 考虑业务规则：需要遵守哪些规则？
4. 制定回复策略：如何最好地回应用户？
5. 生成最终回复：简洁、专业地回复

请按照以上步骤进行思考，最后给出你的回复。
"""
        prompt_parts.append(cot_instruction)
        
        return "\n".join(prompt_parts)
```

#### 步骤2: 注册并使用

```python
# 注册
from contextmind.core.registry import StrategyRegistry
from contextmind.strategies.prompt.cot import ChainOfThoughtPromptStrategy

StrategyRegistry.register('prompt', 'cot', ChainOfThoughtPromptStrategy)

# 使用
from contextmind.steps.prompt import PromptGenerationStep

cot_strategy = StrategyRegistry.create('prompt', 'cot')
prompt_step = PromptGenerationStep(prompt_strategy=cot_strategy)

pipeline.add_step('prompt', prompt_step)
```

### 2.3 集成上下文压缩算法

**适用场景**: LongLLMLingua、Selective Context、RECOMP等

**集成步骤**:

#### 步骤1: 创建新的步骤类

```python
# contextmind/steps/compression.py

from contextmind.steps.base import BaseStep
from contextmind.core.context import PipelineContext

class ContextCompressionStep(BaseStep):
    """上下文压缩步骤"""
    
    def __init__(self, compression_strategy=None, **config):
        super().__init__(config)
        self.compression_strategy = compression_strategy
        
    async def execute(self, context: PipelineContext) -> PipelineContext:
        """
        压缩上下文信息
        
        在收集和整合之后，prompt生成之前执行
        """
        if not self.compression_strategy:
            return context
            
        # 压缩历史
        if context.history_text:
            compressed_history = await self.compression_strategy.compress(
                context.history_text,
                target_length=self.config.get('history_target_length', 500)
            )
            context.history_text = compressed_history
        
        # 压缩记忆
        if context.memory_text:
            compressed_memory = await self.compression_strategy.compress(
                context.memory_text,
                target_length=self.config.get('memory_target_length', 300)
            )
            context.memory_text = compressed_memory
        
        return context
```

#### 步骤2: 实现压缩策略

```python
# contextmind/strategies/compression/llmlingua.py

from contextmind.strategies.base import BaseStrategy

class LLMLinguaCompressionStrategy(BaseStrategy):
    """
    LLMLingua压缩策略
    
    论文: https://arxiv.org/abs/2310.05736
    """
    
    def __init__(self, config=None):
        super().__init__(config)
        self.compressor = self._load_compressor()
    
    def _load_compressor(self):
        """加载LLMLingua压缩器"""
        from llmlingua import PromptCompressor
        
        return PromptCompressor(
            model_name=self.config.get('model_name', 'microsoft/llmlingua-2-bert-base-multilingual-cased'),
            device_map=self.config.get('device', 'cpu')
        )
    
    async def compress(self, text: str, target_length: int) -> str:
        """压缩文本"""
        # 计算压缩比
        compression_ratio = target_length / len(text)
        
        # 调用LLMLingua
        result = self.compressor.compress_prompt(
            text,
            rate=compression_ratio,
            force_tokens=['\n', ':', '?', '!']  # 保留重要标点
        )
        
        return result['compressed_prompt']
```

#### 步骤3: 集成到Pipeline

```python
# 创建压缩策略
from contextmind.strategies.compression.llmlingua import LLMLinguaCompressionStrategy

compression_strategy = LLMLinguaCompressionStrategy(
    model_name='microsoft/llmlingua-2-bert-base-multilingual-cased'
)

# 创建压缩步骤
from contextmind.steps.compression import ContextCompressionStep

compression_step = ContextCompressionStep(
    compression_strategy=compression_strategy,
    history_target_length=500,
    memory_target_length=300
)

# 添加到Pipeline（在整合之后，prompt生成之前）
pipeline = ContextOptimizationPipeline()
pipeline.add_step('validation', InputValidationStep())
pipeline.add_step('session', SessionManagementStep())
pipeline.add_step('collection', ContextCollectionStep())
pipeline.add_step('integration', ContextIntegrationStep())
pipeline.add_step('compression', compression_step)  # 压缩步骤
pipeline.add_step('prompt', PromptGenerationStep())
pipeline.add_step('generation', ResponseGenerationStep())
```

### 2.4 集成知识图谱

**适用场景**: 使用知识图谱增强上下文

**集成步骤**:

#### 步骤1: 创建知识图谱收集器

```python
# contextmind/strategies/collection/knowledge_graph.py

from contextmind.strategies.base import BaseStrategy
from typing import Dict, Any, List

class KnowledgeGraphCollectionStrategy(BaseStrategy):
    """知识图谱收集策略"""
    
    def __init__(self, config=None):
        super().__init__(config)
        self.kg_client = self._init_kg_client()
    
    def _init_kg_client(self):
        """初始化知识图谱客户端（如Neo4j）"""
        from neo4j import GraphDatabase
        
        uri = self.config.get('uri', 'bolt://localhost:7687')
        user = self.config.get('user', 'neo4j')
        password = self.config.get('password', 'password')
        
        return GraphDatabase.driver(uri, auth=(user, password))
    
    async def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """从知识图谱收集相关信息"""
        query = context['query']
        
        # 1. 实体识别
        entities = await self._extract_entities(query)
        
        # 2. 图谱查询
        kg_results = []
        for entity in entities:
            relations = await self._query_kg(entity)
            kg_results.extend(relations)
        
        # 3. 格式化结果
        kg_context = self._format_kg_results(kg_results)
        
        return {
            'kg_context': kg_context,
            'entities': entities,
            'relations': kg_results
        }
    
    async def _extract_entities(self, text: str) -> List[str]:
        """实体识别"""
        # 使用NER模型或其他方法
        pass
    
    async def _query_kg(self, entity: str) -> List[Dict]:
        """查询知识图谱"""
        with self.kg_client.session() as session:
            result = session.run(
                """
                MATCH (e:Entity {name: $entity})-[r]->(related)
                RETURN e, type(r) as relation, related
                LIMIT 10
                """,
                entity=entity
            )
            return [record.data() for record in result]
    
    def _format_kg_results(self, results: List[Dict]) -> str:
        """格式化知识图谱结果"""
        lines = []
        for r in results:
            lines.append(f"{r['e']['name']} {r['relation']} {r['related']['name']}")
        return "\n".join(lines)
```

#### 步骤2: 扩展收集步骤

```python
# 修改 ContextCollectionStep 以支持知识图谱

class ContextCollectionStep(BaseStep):
    def __init__(self, retrieval_strategy=None, kg_strategy=None, **config):
        super().__init__(config)
        self.retrieval_strategy = retrieval_strategy
        self.kg_strategy = kg_strategy  # 新增
    
    async def execute(self, context: PipelineContext) -> PipelineContext:
        # 原有的收集逻辑
        # ...
        
        # 新增：收集知识图谱信息
        if self.kg_strategy:
            kg_result = await self.kg_strategy.apply({
                'query': context.user_input
            })
            context.set('kg_context', kg_result['kg_context'])
            context.set('entities', kg_result['entities'])
        
        return context
```

## 3. 测试新集成

### 3.1 单元测试

```python
# tests/strategies/retrieval/test_dpr.py

import pytest
from contextmind.strategies.retrieval.dpr import DensePassageRetrievalStrategy

@pytest.mark.asyncio
async def test_dpr_retrieval():
    """测试DPR检索"""
    strategy = DensePassageRetrievalStrategy({
        'model_name': 'facebook/dpr-question_encoder-single-nq-base',
        'top_k': 5
    })
    
    context = {
        'query': '用户对产品的态度如何？',
        'app_name': 'test-app',
        'user_id': 'test-user'
    }
    
    result = await strategy.apply(context)
    
    assert 'memories' in result
    assert 'scores' in result
    assert len(result['memories']) <= 5
    assert result['method'] == 'dpr'
```

### 3.2 集成测试

```python
# tests/integration/test_pipeline_with_dpr.py

import pytest
from contextmind.core.pipeline import ContextOptimizationPipeline
from contextmind.strategies.retrieval.dpr import DensePassageRetrievalStrategy

@pytest.mark.asyncio
async def test_pipeline_with_dpr():
    """测试使用DPR的完整Pipeline"""
    # 创建Pipeline
    pipeline = ContextOptimizationPipeline.create_default(
        app_name='test-app',
        user_id='test-user'
    )
    
    # 替换检索策略为DPR
    dpr_strategy = DensePassageRetrievalStrategy()
    collection_step = ContextCollectionStep(retrieval_strategy=dpr_strategy)
    pipeline.replace_step('collection', collection_step)
    
    # 执行
    result = await pipeline.execute('用户最近的情绪如何？')
    
    assert result.response
    assert result.metadata.get('retrieval_method') == 'dpr'
```

## 4. 最佳实践

### 4.1 配置管理

使用配置文件管理策略参数：

```python
# config/strategies.yaml

retrieval:
  dpr:
    model_name: "facebook/dpr-question_encoder-single-nq-base"
    top_k: 5
    device: "cuda:0"
    
prompt:
  cot:
    max_steps: 5
    include_examples: true
    
compression:
  llmlingua:
    model_name: "microsoft/llmlingua-2-bert-base-multilingual-cased"
    device: "cpu"
    compression_rate: 0.5
```

加载配置：

```python
import yaml

with open('config/strategies.yaml') as f:
    config = yaml.safe_load(f)

dpr_strategy = DensePassageRetrievalStrategy(config['retrieval']['dpr'])
```

### 4.2 性能优化

1. **批量处理**: 如果支持，使用批量编码提高效率
2. **缓存**: 缓存常见查询的结果
3. **异步操作**: 充分利用异步IO
4. **模型预加载**: 在初始化时加载模型，避免每次调用时加载

### 4.3 错误处理

```python
class RobustStrategy(BaseStrategy):
    async def apply(self, context: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return await self._apply_impl(context)
        except ModelNotLoadedError:
            # 模型未加载，使用备用策略
            return await self._fallback_strategy.apply(context)
        except Exception as e:
            # 记录错误
            logger.error(f"Strategy failed: {e}")
            # 返回默认结果
            return self._get_default_result()
```

## 5. 文档和示例

为新集成的算法编写文档：

```markdown
## DPR检索策略

### 简介
Dense Passage Retrieval (DPR) 使用密集向量表示进行高效的文本检索。

### 安装依赖
```bash
pip install transformers faiss-cpu
```

### 使用示例
```python
from contextmind.strategies.retrieval.dpr import DensePassageRetrievalStrategy

strategy = DensePassageRetrievalStrategy({
    'model_name': 'facebook/dpr-question_encoder-single-nq-base',
    'top_k': 5
})
```

### 配置参数
- `model_name`: DPR模型名称
- `top_k`: 返回结果数量
- `device`: 计算设备 (cpu/cuda)

### 性能
- 准确率: ...
- 延迟: ...
- 内存占用: ...
```

## 6. 总结

集成新算法的关键步骤：

1. ✅ 理解算法原理和接口
2. ✅ 选择合适的集成点（Step或Strategy）
3. ✅ 实现策略类，继承 `BaseStrategy`
4. ✅ 注册到 `StrategyRegistry`
5. ✅ 编写测试用例
6. ✅ 编写文档和示例
7. ✅ 性能测试和优化

通过遵循这些步骤，可以快速、规范地将新的论文算法集成到 ContextMind 框架中。
