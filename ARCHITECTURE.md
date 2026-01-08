# ContextMind 架构设计文档

## 🏛️ 整体架构

### 1. 分层架构

```
┌─────────────────────────────────────────────────┐
│           应用层 (Application Layer)             │
│  ┌──────────────────┐  ┌──────────────────┐    │
│  │  gradio_demo.py  │  │interactive_demo.py│    │
│  │   (Web UI)       │  │    (CLI)          │    │
│  └──────────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│          框架层 (Framework Layer)                │
│            contextmind/                          │
│  ┌──────────────────────────────────────────┐  │
│  │        engine.py                         │  │
│  │    (ContextEngine - 核心引擎)           │  │
│  │  ┌────────────┐  ┌───────────────┐      │  │
│  │  │ Session    │  │ Memory        │      │  │
│  │  │ 短期记忆   │  │ 长期记忆      │      │  │
│  │  └────────────┘  └───────────────┘      │  │
│  └──────────────────────────────────────────┘  │
│  ┌──────────────┐  ┌──────────────┐           │
│  │  client.py   │  │  logger.py   │           │
│  │ (LLM Client) │  │ (日志系统)   │           │
│  └──────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────┐
│          基础设施层 (Infrastructure)              │
│  ┌──────────────┐  ┌──────────────┐            │
│  │  Google ADK  │  │  OpenAI SDK  │            │
│  └──────────────┘  └──────────────┘            │
│  ┌──────────────┐  ┌──────────────┐            │
│  │ Session Svc  │  │  Memory Svc  │            │
│  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────┘
```

### 2. 核心组件交互图

```
┌──────────┐
│   User   │
└────┬─────┘
     │ 用户输入
     ▼
┌─────────────────────────────────────┐
│      ContextEngine                  │
│                                     │
│  ┌──────────────────────────────┐  │
│  │ 1. 验证输入                  │  │
│  └──────────────────────────────┘  │
│           ▼                         │
│  ┌──────────────────────────────┐  │
│  │ 2. 确保 Session 存在         │◄─┼─┐
│  └──────────────────────────────┘  │ │
│           ▼                         │ │
│  ┌──────────────────────────────┐  │ │  Session
│  │ 3. 收集上下文                │  │ │  Service
│  │  - 最近历史 (Session)        │──┼─┤
│  │  - 长期记忆 (Memory)         │──┼─┼─┐
│  └──────────────────────────────┘  │ │ │
│           ▼                         │ │ │ Memory
│  ┌──────────────────────────────┐  │ │ │ Service
│  │ 4. 整合知识                  │  │ │ │
│  │  - 用户画像                  │  │ │ │
│  │  - 业务规则                  │  │ │ │
│  │  - 时间上下文                │  │ │ │
│  └──────────────────────────────┘  │ │ │
│           ▼                         │ │ │
│  ┌──────────────────────────────┐  │ │ │
│  │ 5. 生成 Prompt               │  │ │ │
│  └──────────────────────────────┘  │ │ │
│           ▼                         │ │ │
│  ┌──────────────────────────────┐  │ │ │
│  │ 6. 调用 LLM                  │──┼─┼─┼──► LLM
│  └──────────────────────────────┘  │ │ │    Client
│           ▼                         │ │ │
│  ┌──────────────────────────────┐  │ │ │
│  │ 7. 保存回复到 Session        │──┼─┘ │
│  └──────────────────────────────┘  │   │
│           ▼                         │   │
│  ┌──────────────────────────────┐  │   │
│  │ 8. 持久化到 Memory           │──┼───┘
│  └──────────────────────────────┘  │
│           ▼                         │
│  ┌──────────────────────────────┐  │
│  │ 9. 定期总结                  │  │
│  └──────────────────────────────┘  │
└─────────────────────────────────────┘
           │
           ▼
     ┌──────────┐
     │ Response │
     └──────────┘
```

## 🧠 记忆系统架构

### 三层记忆模型

```
┌────────────────────────────────────────────────┐
│                即时上下文                       │
│              (Immediate Context)                │
│  ┌──────────────────────────────────────────┐  │
│  │  当前用户输入 + 系统提示词               │  │
│  │  生命周期: 单次请求                      │  │
│  │  存储: Prompt 拼接                       │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────┐
│                短期记忆                         │
│              (Short-term Memory)                │
│  ┌──────────────────────────────────────────┐  │
│  │  Session Events (最近 6-50 轮对话)      │  │
│  │  生命周期: 单次会话                      │  │
│  │  存储: InMemorySessionService            │  │
│  │  特点: FIFO 队列，自动清理旧事件         │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
                      ▼
┌────────────────────────────────────────────────┐
│                长期记忆                         │
│              (Long-term Memory)                 │
│  ┌──────────────────────────────────────────┐  │
│  │  Memory Service (关键事实和知识)        │  │
│  │  生命周期: 跨会话持久化                  │  │
│  │  存储: InMemoryMemoryService             │  │
│  │  特点: 语义检索，相关性评分             │  │
│  └──────────────────────────────────────────┘  │
└────────────────────────────────────────────────┘
```

### 记忆流转机制

```
用户输入
   │
   ▼
┌──────────────┐
│ 保存到 Session│
│ (短期记忆)    │
└───────┬──────┘
        │
        │ 每轮对话后
        ▼
┌──────────────────┐
│ 提取关键知识      │
│ (事实抽取)        │
└───────┬──────────┘
        │
        │ 定期 (每 5 轮)
        ▼
┌──────────────────┐
│ 持久化到 Memory   │
│ (长期记忆)        │
└──────────────────┘
        │
        │ 下次对话时
        ▼
┌──────────────────┐
│ 语义检索相关记忆  │
└──────────────────┘
        │
        ▼
    拼接到 Prompt
```

## 🔄 数据流设计

### 1. 单轮对话数据流

```
输入阶段:
  User Input (str)
       │
       ▼
  验证和清理
       │
       ▼
  Event (author="user")
       │
       ▼
  SessionService.append_event()

处理阶段:
  SessionService.get_recent_events()
       │
       ▼
  _render_events() → history_text (str)
       
  MemoryService.search(query)
       │
       ▼
  _render_memory_entries() → memory_text (str)
       
  user_profile (dict)
  business_rules (dict)
  temporal_context (dict)
       │
       ▼
  IntegratedKnowledge (dataclass)
       │
       ▼
  generate_prompt_from_knowledge() → prompt (str)

生成阶段:
  prompt (str)
       │
       ▼
  LLMClient.generate()
       │
       ▼
  response (str)
       │
       ▼
  _extract_actual_response() → cleaned_response (str)

输出阶段:
  Event (author="assistant")
       │
       ▼
  SessionService.append_event()
       │
       ▼
  ContextTurnResult (dataclass)
       │
       ▼
  返回给应用层
```

### 2. Prompt 构建流程

```
IntegratedKnowledge
  ├─ base_system_prompt      (基础提示词)
  ├─ user_profile            (用户画像)
  ├─ business_rules          (业务规则)
  ├─ temporal_context        (时间上下文)
  ├─ history_text            (对话历史)
  ├─ memory_text             (长期记忆)
  ├─ preset_info             (预设信息)
  └─ extended_context        (扩展上下文)
       │
       ▼
_calculate_context_weights()  (计算权重)
       │
       ▼
_organize_context_by_weight() (按权重组织)
       │
       ▼
_build_prompt()               (构建 Prompt)
       │
       ▼
Final Prompt (str)

结构:
┌────────────────────────────┐
│ System Prompt              │  权重: 0.3
├────────────────────────────┤
│ User Profile               │  权重: 0.1
├────────────────────────────┤
│ Business Rules             │  权重: 0.1
├────────────────────────────┤
│ Temporal Context           │  权重: 0.05
├────────────────────────────┤
│ Long-term Memory           │  权重: 0.25
├────────────────────────────┤
│ Recent History             │  权重: 0.25
├────────────────────────────┤
│ Current User Input         │  最高优先级
└────────────────────────────┘
```

## 🎨 设计模式应用

### 1. 策略模式 (Strategy Pattern)

**应用场景**: 不同类型的引擎配置

```python
# 基础策略
engine_basic = ContextEngine(
    max_recent_events=6,
    # 无 memory_service
)

# 短期记忆策略
engine_short = ContextEngine(
    max_recent_events=6,
    user_profile={...},
    business_rules={...},
)

# 长期记忆策略
engine_long = ContextEngine(
    max_recent_events=50,
    user_profile={...},
    business_rules={...},
    memory_service=InMemoryMemoryService(),
)
```

### 2. 模板方法模式 (Template Method)

**应用场景**: `process_turn()` 定义了处理流程模板

```python
async def process_turn(self, user_input: str):
    # 固定流程
    self._validate_input(user_input)
    await self._ensure_session()
    self._update_state()
    await self._save_user_input(user_input)
    
    # 可扩展的步骤
    history = await self._collect_recent_history()
    memory = await self._retrieve_memory(query=user_input)
    knowledge = await self.integrate_context_to_knowledge(...)
    
    # 固定流程继续
    prompt = await self.generate_prompt_from_knowledge(knowledge)
    response = await self._generate_response_with_retry(prompt)
    await self._save_assistant_response(response)
    ...
```

### 3. 工厂模式 (Factory Pattern)

**应用场景**: 创建不同类型的引擎

```python
def _create_engine(self, engine_type: str, client: Client):
    if engine_type == 'basic':
        return ContextEngine(...)
    elif engine_type == 'short_term':
        return ContextEngine(...)
    elif engine_type == 'long_term':
        return ContextEngine(...)
```

### 4. 单例模式 (Singleton)

**应用场景**: 日志管理器

```python
class ContextMindLogger:
    _initialized = False
    _log_file: Optional[Path] = None
    
    @classmethod
    def setup_logging(cls, ...):
        if not cls._initialized:
            # 初始化
            cls._initialized = True
```

### 5. 装饰器模式 (Decorator)

**应用场景**: 日志格式化

```python
class EngineFormatter(logging.Formatter):
    def format(self, record):
        # 装饰原始日志记录
        engine_type = getattr(record, 'engine_type', 'default')
        symbol = self.ENGINE_SYMBOLS.get(engine_type, ...)
        record.msg = f"{symbol} [{engine_type}] {record.msg}"
        return super().format(record)
```

## 🔌 可扩展性设计

### 1. 插件化的记忆服务

```python
# 当前: 内存存储
memory_service = InMemoryMemoryService()

# 可扩展: Redis 存储
# memory_service = RedisMemoryService()

# 可扩展: 向量数据库
# memory_service = VectorMemoryService(
#     backend="chromadb"
# )
```

### 2. 可配置的 LLM 客户端

```python
# 当前: OpenAI 兼容
client = Client(config=ClientConfig.from_env())

# 可扩展: 不同的 LLM
# client = ClaudeClient(...)
# client = LlamaClient(...)
```

### 3. 自定义上下文提供器

```python
# 当前: 固定的上下文收集
async def _collect_recent_history(self) -> str:
    # 固定逻辑

# 可扩展: 插件式上下文提供器
# context_providers = [
#     HistoryProvider(),
#     MemoryProvider(),
#     ExternalKnowledgeProvider(),
#     UserPreferenceProvider(),
# ]
```

## 🧪 测试架构建议

### 单元测试层次

```
tests/
├── unit/
│   ├── test_client.py          # LLM 客户端测试
│   ├── test_engine.py          # 引擎核心测试
│   ├── test_logger.py          # 日志系统测试
│   └── test_utils.py           # 工具函数测试
├── integration/
│   ├── test_session_flow.py   # 会话流程测试
│   ├── test_memory_flow.py    # 记忆流程测试
│   └── test_end_to_end.py     # 端到端测试
└── fixtures/
    ├── mock_llm.py            # Mock LLM 响应
    ├── sample_sessions.py     # 示例会话数据
    └── sample_memories.py     # 示例记忆数据
```

### 测试覆盖目标

- **单元测试**: 80%+ 代码覆盖率
- **集成测试**: 核心流程 100% 覆盖
- **端到端测试**: 主要使用场景覆盖

## 📊 性能优化建议

### 1. 缓存层设计

```
┌─────────────────┐
│  Request        │
└────────┬────────┘
         │
         ▼
    ┌─────────┐
    │ Cache?  │───Yes──► Return cached
    └────┬────┘
         │ No
         ▼
    ┌─────────┐
    │ Process │
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │ Cache   │
    └────┬────┘
         │
         ▼
    ┌─────────┐
    │ Return  │
    └─────────┘
```

### 2. 批处理优化

```python
# 当前: 单个查询
for query in queries:
    results = await memory_service.search(query)

# 优化: 批量查询
results = await memory_service.batch_search(queries)
```

### 3. 异步并发

```python
# 当前: 串行
history = await self._collect_recent_history()
memory = await self._retrieve_memory(query)

# 优化: 并行
history, memory = await asyncio.gather(
    self._collect_recent_history(),
    self._retrieve_memory(query)
)
```

## 🔐 安全架构

### 数据流安全检查点

```
User Input
    │
    ▼ [检查点 1: 输入验证]
    ├─ 长度检查
    ├─ 字符过滤
    └─ 编码验证
    │
    ▼ [检查点 2: Prompt 注入防护]
    ├─ 危险模式检测
    ├─ 系统指令过滤
    └─ 上下文隔离
    │
    ▼ [检查点 3: API 调用]
    ├─ API Key 保护
    ├─ 请求签名
    └─ 速率限制
    │
    ▼ [检查点 4: 响应验证]
    ├─ 内容审查
    ├─ 格式验证
    └─ 敏感信息过滤
    │
    ▼
Response
```

---

**文档版本**: v1.0  
**最后更新**: 2026-01-08  
**维护者**: ContextMind Team
