# ContextMind 快速参考指南

> 快速查阅上下文优化的核心概念和实现要点

## 11个核心步骤速查

| # | 步骤 | 主要操作 | 当前实现位置 |
|---|------|---------|-------------|
| 1 | 输入验证 | 非空检查、文本清洗 | `process_turn()` 开头 |
| 2 | 会话管理 | 创建/获取session | `_ensure_session()` |
| 3 | 上下文收集 | 历史、记忆、画像、规则 | `_collect_recent_history()`, `_retrieve_memory()` |
| 4 | 上下文整合 | 整合为IntegratedKnowledge | `integrate_context_to_knowledge()` |
| 5 | Prompt生成 | Agent/模板双模式 | `generate_prompt_from_knowledge()` |
| 6 | 响应生成 | LLM调用+重试 | `_generate_response_with_retry()` |
| 7 | 响应后处理 | 格式清洗 | `_extract_actual_response()` |
| 8 | 状态更新 | 记录对话历史 | `process_turn()` 中段 |
| 9 | 知识提取 | 提取并存储知识 | `_extract_knowledge_from_session()` |
| 10 | 定期总结 | 生成摘要 | `_periodic_summary()` |
| 11 | 结果封装 | 返回ContextTurnResult | `process_turn()` 结尾 |

## 关键数据结构

### IntegratedKnowledge
```python
@dataclass
class IntegratedKnowledge:
    user_input: str              # 用户输入
    history_text: str            # 对话历史
    memory_text: str             # 长期记忆
    preset_info: str             # 预置信息
    extended_context: str        # 扩展上下文
    base_system_prompt: str      # 基础prompt
    user_profile: dict           # 用户画像
    business_rules: dict         # 业务规则
    temporal_context: dict       # 时间上下文
```

### ContextTurnResult
```python
@dataclass
class ContextTurnResult:
    prompt: str                  # 生成的prompt
    reasoning: str               # 推理过程
    response: str                # 最终回复
    memory_hits: List[str]       # 命中的记忆
    history_count: int           # 历史数量
    profile_summary: str         # 画像摘要
    rules_count: int             # 规则数量
    memory_count: int            # 记忆数量
    turn_number: int             # 轮次编号
    processing_time: float       # 处理时间
```

## 关键算法

### 相关性评分公式
```
总分 = 关键词匹配分(40%) + 重要性标签分(30%) + 时间衰减分(30%)
```

**关键词匹配** (40%):
- 完全匹配: 0.4
- 部分匹配: 0.4 × (重叠词数 / 查询词数)

**重要性标签** (30%):
- [重要事实]: 0.3
- [关键事件]: 0.3
- [对话总结]: 0.25
- [情绪状态]: 0.2
- [用户偏好]: 0.2

**时间衰减** (30%):
- 1天内: 1.0 × 0.3 = 0.3
- 7天内: 0.8 × 0.3 = 0.24
- 30天内: 0.6 × 0.3 = 0.18
- 更久: 0.4 × 0.3 = 0.12

### 上下文权重计算

**基础权重**:
```python
weights = {
    'history': 0.5,    # 对话历史
    'memory': 0.3,     # 长期记忆
    'preset': 0.1,     # 预置信息
    'extended': 0.1    # 扩展上下文
}
```

**动态调整规则**:
1. 有长期记忆 → memory: 0.8, history: 0.6
2. 包含业务关键词 → preset: 0.7
3. 包含情绪关键词 → memory: 0.9

**业务关键词**: 额度、费用、利息、申请、还款、逾期、优逸花

**情绪关键词**: 骚扰、报警、拒绝、烦、不要、停止、投诉

## 配置参数

### ContextEngine初始化参数

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| app_name | str | 必填 | 应用名称 |
| user_id | str | 必填 | 用户ID |
| llm_client | Client | 必填 | LLM客户端 |
| session_service | BaseSessionService | InMemorySessionService | Session服务 |
| memory_service | BaseMemoryService | None | Memory服务 |
| session_id | str | None | 会话ID |
| max_recent_events | int | 6 | 保留的最近事件数 |
| base_system_prompt | str | "" | 基础系统提示词 |
| user_profile | dict | None | 用户画像 |
| business_rules | dict | None | 业务规则 |
| temporal_context | dict | None | 时间上下文 |
| use_preset_info | bool | True | 是否使用预置信息 |
| agent_timeout | float | 10.0 | Agent超时时间(秒) |

### 常量定义

```python
DEFAULT_AGENT_TIMEOUT = 10.0      # Agent超时
MIN_PROMPT_LENGTH = 50            # 有效prompt最小长度
MIN_FACT_LENGTH = 5               # 有效事实最小长度
SUMMARY_INTERVAL = 5              # 总结间隔(轮)
MAX_RETRIES = 3                   # LLM调用最大重试次数
```

## 性能优化技巧

### 1. 并发检索
```python
# 并发执行多个查询
search_tasks = [search_single_query(q) for q in queries[:5]]
results = await asyncio.gather(*search_tasks)
```

### 2. 批量操作
```python
# 批量添加事件
for event in events:
    await session_service.append_event(session, event)
```

### 3. 缓存策略
- 缓存LLM响应（相同prompt）
- 缓存检索结果（短时间内）
- 缓存用户画像（定期更新）

### 4. 超时控制
```python
# 使用asyncio.wait_for
result = await asyncio.wait_for(
    agent_call(),
    timeout=10.0
)
```

## 错误处理模式

### 1. Try-Except-Continue
```python
try:
    result = await risky_operation()
except Exception as e:
    logger.warning(f"操作失败: {e}")
    # 继续执行，使用默认值
    result = default_value
```

### 2. Retry机制
```python
for attempt in range(max_retries):
    try:
        return await operation()
    except Exception as e:
        if attempt < max_retries - 1:
            continue
        raise
```

### 3. 回退策略
```python
try:
    # 尝试高级方法
    result = await advanced_method()
except Exception:
    # 回退到简单方法
    result = fallback_method()
```

## 日志级别使用

```python
logger.debug()    # 详细执行信息
logger.info()     # 关键操作信息
logger.warning()  # 警告（不影响功能）
logger.error()    # 错误（可能影响功能）
```

**日志最佳实践**:
- ✅ 关键步骤开始/结束
- ✅ 异常情况和回退
- ✅ 性能指标（耗时、数量）
- ❌ 敏感信息（密码、Token）
- ❌ 过于频繁的循环日志

## 扩展点一览

### 可替换的策略

**检索策略**:
- 关键词检索（当前）
- 语义检索
- 向量检索
- 混合检索

**Prompt策略**:
- 模板Prompt（当前）
- Agent Prompt（当前）
- Chain-of-Thought
- Tree-of-Thought

**整合策略**:
- 模板整合（当前）
- 图整合
- 层次整合

**提取策略**:
- LLM提取（当前）
- 规则提取
- 混合提取

### 可添加的步骤

- **压缩步骤**: 上下文压缩（LongLLMLingua）
- **排序步骤**: 智能排序优化
- **过滤步骤**: 内容过滤和审查
- **增强步骤**: 外部知识增强

## 常见问题

### Q: 如何调整记忆检索的相关性？
A: 修改 `_calculate_relevance_score()` 中的权重比例。

### Q: 如何禁用Agent Prompt？
A: 设置 `agent_timeout=0` 或直接使用模板。

### Q: 如何增加历史保留数量？
A: 设置 `max_recent_events` 参数。

### Q: 如何自定义业务规则？
A: 传入 `business_rules` 字典参数。

### Q: 如何集成新的检索算法？
A: 参考 [集成指南](INTEGRATION_GUIDE.md)。

## 调试技巧

### 1. 启用详细日志
```python
from contextmind.logger import setup_logging, DEBUG
setup_logging(level=DEBUG)
```

### 2. 查看中间结果
```python
result = await engine.process_turn(user_input)
print(f"Prompt: {result.prompt[:200]}...")
print(f"Memory hits: {result.memory_count}")
```

### 3. 性能分析
```python
import time
start = time.time()
result = await engine.process_turn(user_input)
print(f"耗时: {time.time() - start:.2f}s")
```

### 4. 检查会话状态
```python
session = await engine.get_current_session()
print(f"Events: {len(session.events)}")
```

## 相关文档

- [上下文优化步骤总结](上下文优化步骤总结.md) - 完整步骤分析
- [框架设计文档](FRAMEWORK_DESIGN.md) - 架构设计
- [集成指南](INTEGRATION_GUIDE.md) - 集成新算法
- [实现路线图](ROADMAP.md) - 开发计划
