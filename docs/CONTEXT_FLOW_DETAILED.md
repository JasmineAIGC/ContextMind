# ContextMind 上下文处理流程详解

## 📋 目录
1. [上下文来源](#上下文来源)
2. [存储位置](#存储位置)
3. [处理流程](#处理流程)
4. [提取策略](#提取策略)
5. [检索机制](#检索机制)
6. [容量限制](#容量限制)

---

## 1. 上下文来源

ContextMind 从三个主要来源收集上下文：

### 1.1 会话历史 (Session History)
- **来源**: SessionService (Google ADK)
- **内容**: 用户和助手的对话记录
- **时效**: 短期（会话级别）
- **存储**: 内存中，程序重启后清空
- **用途**: 理解当前对话的上下文连贯性

### 1.2 长期记忆 (Long-term Memory)
- **来源**: MemoryService (Google ADK)
- **内容**: 提取的知识、用户偏好、重要信息
- **时效**: 长期（跨会话）
- **存储**: 持久化存储（具体取决于MemoryService实现）
- **用途**: 记住用户信息、业务知识

### 1.3 外部知识 (External Knowledge)
- **来源**: 外部知识库、向量数据库等
- **内容**: 领域知识、FAQ、文档等
- **时效**: 永久（知识库级别）
- **存储**: 外部系统
- **用途**: 提供专业知识支持

---

## 2. 存储位置

### 2.1 SessionService 存储
```
位置: 内存（InMemorySessionService）或数据库
内容: Event对象列表
    - Event.invocation_id: 唯一ID
    - Event.author: user/assistant/system
    - Event.content: Content对象（包含Parts）
    - Event.timestamp: 时间戳

结构:
Session
  └── events: List[Event]
        ├── Event(user, "你是谁", timestamp=xxx)
        ├── Event(assistant, "我是助手", timestamp=xxx)
        └── ...

容量限制: 
- 默认保留 max_recent_events=9999 条
- 实际限制取决于内存或数据库
```

### 2.2 MemoryService 存储
```
位置: 持久化存储（具体实现依赖）
内容: Memory对象列表
    - Memory.content: Content对象
    - Memory.timestamp: 时间戳
    - Memory.metadata: 元数据

结构:
MemoryStore
  └── memories: List[Memory]
        ├── Memory("[KNOWLEDGE] 产品名称：智能助手", timestamp=xxx)
        ├── Memory("[PREFERENCE] 用户喜欢简洁回答", timestamp=xxx)
        └── ...

容量限制:
- 由MemoryService实现决定
- InMemoryMemoryService: 内存限制
- 持久化实现: 数据库容量限制
```

---

## 3. 处理流程

### 3.1 完整流程图
```
用户输入
    ↓
[InputProcessor] 预处理和规范化
    ↓
[ContextCollector] 从各源收集上下文
    ├─→ SessionManager.get_recent_history() → 获取对话历史
    ├─→ MemoryManager.retrieve(query) → 检索相关记忆
    └─→ ExternalKB.search(query) → (未实现) 检索外部知识
    ↓
[ContextIntegrator] 整合所有上下文
    └─→ ProcessedContext (统一的上下文对象)
    ↓
[ContextOptimizer] 优化和提炼上下文
    ├─→ 去重
    ├─→ 智能提取 (entities, preferences, states, actions)
    ├─→ 按相关性排序
    └─→ 截断（如果需要）
    ↓
[ContextResult] 返回优化后的上下文
    ├─→ recent_history: List[Message]
    ├─→ long_term_memory: List[ContextItem]
    ├─→ external_knowledge: List[ContextItem]
    └─→ metadata: Dict (包含提取的关键信息)
```

### 3.2 详细步骤

#### Step 1: 收集 (Collect)
```python
# 在 ContextCollector.collect()
context = ProcessedContext()

# 1. 收集会话历史
if include_session:
    history = await session_manager.get_recent_history()
    # 转换为 ContextItem 并添加到 context.items
    
# 2. 收集长期记忆  
if include_memory:
    memories = await memory_manager.retrieve(user_input)
    # 添加到 context.items

# 3. 收集外部知识
if include_knowledge:
    # 预留接口，当前未实现
```

#### Step 2: 整合 (Integrate)
```python
# 在 ContextIntegrator.integrate()
# 1. 按来源分类
session_items = [item for item in items if item.source == SESSION]
memory_items = [item for item in items if item.source == MEMORY]

# 2. 去重（基于内容相似度）
unique_items = _deduplicate(items)

# 3. 返回整合后的上下文
```

#### Step 3: 优化 (Optimize)
```python
# 在 ContextOptimizer.optimize()
# 1. 智能提取关键信息
extracted_info = _extract_key_info(items)
# - entities: 地点、人名、物品
# - preferences: 用户偏好
# - states: 用户状态（情绪、忙碌等）
# - actions: 待办事项

# 2. 按相关性排序
sorted_items = sorted(items, key=lambda x: x.score, reverse=True)

# 3. 存储到metadata
context.metadata['extracted_info'] = extracted_info

# 4. 返回优化后的上下文
```

---

## 4. 提取策略

### 4.1 智能提取算法

ContextOptimizer 使用NLP技术提取关键信息：

#### 4.1.1 实体提取 (Entity Extraction)
```python
# 使用正则表达式匹配
patterns = {
    'location': r'(?:去|在|到)([^，。！？\s]{2,6})',
    'person': r'(?:叫|是)([^，。！？\s]{2,6})',
}

# 示例：
# "我想去重庆" → 提取: location="重庆"
# "我叫张三" → 提取: person="张三"
```

#### 4.1.2 偏好提取 (Preference Extraction)
```python
# 关键词匹配
keywords = ['喜欢', '不喜欢', '偏好', '想要', '不想']

# 示例：
# "我喜欢简洁的回答" → 提取: preference="简洁的回答"
# "不想去拥挤的地方" → 提取: preference="不拥挤的地方"
```

#### 4.1.3 状态提取 (State Extraction)
```python
# 状态关键词
keywords = ['累', '忙', '闲', '开心', '难过', '不想']

# 示例：
# "我最近很忙" → 提取: state="很忙"
# "心情不好" → 提取: state="心情不好"
```

#### 4.1.4 动作项提取 (Action Item Extraction)
```python
# 动作关键词
keywords = ['帮', '做', '写', '处理', '完成']

# 示例：
# "帮我写一首诗" → 提取: action="写诗"
# "处理这个问题" → 提取: action="处理问题"
```

### 4.2 提取结果存储

提取的信息存储在 `ProcessedContext.metadata['extracted_info']`:

```python
{
    'topics': {'重庆旅游', '美食推荐'},
    'entities': {'重庆', '火锅', '张三'},
    'user_preferences': [
        '喜欢简洁的回答',
        '不喜欢辣的食物'
    ],
    'user_states': ['很忙', '心情不错'],
    'action_items': ['写诗', '推荐餐厅'],
}
```

---

## 5. 检索机制

### 5.1 会话历史检索

```python
# SessionManager.get_recent_history(limit)
1. 连接到 SessionService
2. 获取当前会话
3. 读取最近 N 条事件 (N = limit 或 max_recent_events)
4. 转换为 Message 对象
5. 返回消息列表

注意：
- 返回顺序：按时间正序（最早的在前）
- 包含所有角色：user, assistant, system
- 自动过滤空内容
```

### 5.2 长期记忆检索

```python
# MemoryManager.retrieve(query, limit)
1. 如果 MemoryService 未配置，返回空列表
2. 调用 MemoryService.search_memory(query)
3. MemoryService 基于语义相似度搜索
4. 返回最相关的 N 条记忆 (N = limit)
5. 转换为 ContextItem 对象

注意：
- 使用语义搜索，不是关键词匹配
- 返回按相关性排序
- 每条记忆包含时间戳和元数据
```

### 5.3 检索性能

| 操作 | 时间复杂度 | 说明 |
|------|-----------|------|
| Session History | O(N) | N = num_recent_events |
| Memory Search | O(M log M) | M = 记忆总数，使用向量索引 |
| Knowledge Search | O(K log K) | K = 知识库大小 |

---

## 6. 容量限制

### 6.1 SessionService 容量

```python
# 配置参数
max_recent_events = 9999  # 默认值（实际不限制）

# 实际限制
- InMemorySessionService: 受内存限制
  - 估算: 每条消息 ~1KB，9999条 ≈ 10MB
- 数据库Session Service: 受数据库容量限制
  - 通常可存储数百万条消息
```

### 6.2 MemoryService 容量

```python
# 无显式配置参数

# 实际限制
- InMemoryMemoryService: 受内存限制
  - 建议: < 10,000 条记忆
- 持久化Memory Service: 受数据库容量限制
  - 可扩展到数十万条记忆
```

### 6.3 检索限制

```python
# 每次检索返回的最大条目数
session_limit = max_recent_events  # 默认 9999
memory_limit = 5  # 默认值
knowledge_limit = 5  # 默认值

# 实际影响
- 过多历史可能导致Prompt过长，超出LLM上下文窗口
- 建议根据LLM的token限制动态调整
```

---

## 7. 故障排查

### 7.1 长期记忆为0的常见原因

1. **MemoryService 未配置**
   ```python
   # 检查：
   engine = ContextEngine(..., memory_service=None)  # ❌ 未配置
   ```
   
2. **未启用记忆检索**
   ```python
   # 检查：
   context = await engine.optimize(input, include_memory=False)  # ❌ 未启用
   ```

3. **未植入种子数据**
   ```python
   # 检查：
   await engine.seed_memory(facts)  # 必须先植入
   ```

4. **查询词不匹配**
   ```python
   # MemoryService 使用语义搜索
   # 如果查询词与种子数据语义差异太大，可能检索不到
   ```

### 7.2 调试方法

```python
# 1. 启用调试日志
python interactive_demo.py --debug

# 2. 检查日志输出
[2026-01-15 15:40:12] INFO - Seeding 4 facts into long-term memory...
[2026-01-15 15:40:12] INFO - Successfully seeded 4 facts to memory
[2026-01-15 15:40:18] DEBUG - No memories found for query: 你是谁  # ← 检索失败

# 3. 验证MemoryService状态
# 查看是否真的存储成功
```

---

## 8. 最佳实践

### 8.1 会话历史

```python
# ✅ 推荐
- 启用会话历史: include_session=True
- 保留足够历史: max_recent_events=9999 (不限制)
- 定期清理: 在对话结束或用户请求时调用 clear()

# ❌ 避免
- 设置过小的限制 (如 max_recent_events=10)
- 频繁清空会话（会丢失上下文）
```

### 8.2 长期记忆

```python
# ✅ 推荐
- 植入高质量种子数据
- 使用清晰的标签 [KNOWLEDGE]、[PREFERENCE]
- 定期存储重要知识 (调用 store())

# ❌ 避免
- 存储大量低质量或重复信息
- 种子数据过于简短（< 5字符）
```

### 8.3 性能优化

```python
# ✅ 推荐
- 限制检索数量: memory_limit=5 (避免过多)
- 使用缓存: 相同查询可以缓存结果
- 异步操作: 充分利用 async/await

# ❌ 避免
- 每次都检索大量记忆 (memory_limit=100)
- 同步阻塞操作
```

---

## 9. 总结

### 核心要点
1. **三个来源**: Session (短期) + Memory (长期) + Knowledge (外部)
2. **五个步骤**: 输入 → 收集 → 整合 → 优化 → 输出
3. **智能提取**: 自动提取实体、偏好、状态、动作
4. **灵活配置**: 可选择性启用各个来源

### 架构优势
- ✅ **模块解耦**: 每个组件职责明确
- ✅ **易于扩展**: 可插拔的策略和服务
- ✅ **完整透明**: Debug模式显示所有处理步骤
- ✅ **生产就绪**: 异常处理、日志记录完善
