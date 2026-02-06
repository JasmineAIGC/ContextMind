# Token 管理最佳实践指南

## 概述

本指南总结了 ContextMind 三种模式（DST, FnCTOD, Evolve）在 Token 管理方面的最佳实践，供开发者参考。

---

## 核心原则

### 1. 历史长度限制

**原则：始终限制保留的历史长度**

```python
# ✅ 推荐
max_history_turns: int = 10  # 默认保留 10 轮

# 使用切片限制
recent_history = self.dialogue_history[-self.max_history_turns:]

# ❌ 避免
all_history = self.dialogue_history  # 无限增长
```

### 2. 避免累积式存储

**原则：不要在实例变量中无限累积**

```python
# ❌ 错误示范（会指数增长）
class BadTracker:
    def __init__(self):
        self.messages = [system_msg]
    
    def process_turn(self, user_input):
        # 包含历史的提示
        full_prompt = f"{history}\n{user_input}"
        self.messages.append({"role": "user", "content": full_prompt})
        self.messages.append({"role": "assistant", "content": response})
        # → 历史重复累积！

# ✅ 正确示范 1: 每轮重置（DST 模式）
class GoodTracker1:
    def __init__(self):
        self.messages = [system_msg]
    
    def process_turn(self, user_input):
        # 重置为只有系统消息
        self.messages = [self.messages[0]]
        self.messages.append({"role": "user", "content": full_prompt})
        # 不累积 assistant 响应

# ✅ 正确示范 2: 使用局部变量（FnCTOD 模式）
class GoodTracker2:
    def process_turn(self, user_input):
        # 每次构建新的局部 messages
        messages = [system_msg]
        for turn in history[-10:]:  # 限制历史
            messages.append(...)
        # 函数结束，自动释放

# ✅ 正确示范 3: 使用专门管理器（Evolve 模式）
class GoodTracker3:
    def __init__(self):
        self.session_manager = SessionManager(max_recent_events=10)
    
    def process_turn(self, user_input):
        # 由 SessionManager 管理历史
        history = await self.session_manager.get_recent_history(limit=10)
        # 自然受限
```

### 3. 结构化历史管理

**原则：将历史和消息分离管理**

```python
# ✅ 推荐模式
class Tracker:
    def __init__(self):
        # 结构化历史（用于状态管理）
        self.dialogue_history: List[DialogueTurn] = []
        
        # 消息数组（用于 LLM 调用）
        # 方式 1: 局部变量
        # 方式 2: 实例变量但每轮重置
        # 方式 3: SessionManager
    
    def process_turn(self, user_input):
        # 1. 更新结构化历史
        turn = DialogueTurn(...)
        self.dialogue_history.append(turn)
        
        # 2. 从历史构建 messages（限制长度）
        messages = self._build_messages(
            self.dialogue_history[-self.max_history_turns:]
        )
        
        # 3. 调用 LLM
        response = await self.llm_client.chat(messages)
```

---

## 模式特定的最佳实践

### DST 模式

#### 核心做法：每轮重置 messages 数组

```python
class DialogueStateTracker:
    async def process_turn(self, user_utterance: str):
        # 1. 构建当前轮的提示（包含限制后的历史）
        full_prompt = self._build_prompt(user_utterance)
        
        # 2. 重置 messages 数组（关键！）
        self.messages = [self.messages[0]]  # 只保留系统消息
        
        # 3. 添加当前用户消息
        self.messages.append({"role": "user", "content": full_prompt})
        
        # 4. 调用 LLM
        response = await self.llm_client.chat_async(
            messages=self.messages,
            temperature=0.0
        )
        
        # 5. 更新结构化历史（独立维护）
        turn = DialogueTurn(
            user_utterance=user_utterance,
            extracted_slots=extracted_slots,
            intent=intent
        )
        self.dialogue_history.append(turn)
        
        # 6. 不要添加 assistant 响应到 messages
        # （历史已在 dialogue_history 中）
```

**关键点：**
- ✅ messages 数组每轮重置
- ✅ dialogue_history 独立管理
- ✅ 历史通过 `_build_prompt()` 包含在用户消息中
- ✅ Token 使用：~1,124 (turn 15)

### FnCTOD 模式

#### 核心做法：使用局部 messages 变量

```python
class FnCTODTracker:
    async def _call_function(
        self,
        user_utterance: str,
        domains: List[str]
    ) -> FunctionCall:
        # 1. 构建局部 messages（关键！）
        messages = [
            {"role": "system", "content": system_prompt}
        ]
        
        # 2. 添加限制后的历史
        for turn in self.dialogue_history[-self.max_history_turns:]:
            messages.append({
                "role": "user",
                "content": turn.user_utterance
            })
            if turn.function_call:
                messages.append({
                    "role": "assistant",
                    "content": str(turn.function_call)
                })
        
        # 3. 添加当前用户输入
        messages.append({
            "role": "user",
            "content": user_utterance
        })
        
        # 4. 调用 LLM
        response = await self.llm_client.chat_async(messages)
        
        # 5. 函数结束，messages 自动释放
        return function_call
```

**关键点：**
- ✅ messages 是局部变量，每次重建
- ✅ 使用切片限制历史 `[-self.max_history_turns:]`
- ✅ 函数结束自动释放内存
- ✅ Token 使用：~985 (turn 15)

### Evolve 模式

#### 核心做法：使用 SessionManager

```python
class EvolutionEngine:
    def __init__(self):
        self.session_manager = SessionManager(
            max_recent_events=10  # 限制保留的消息数
        )
        self.memory_bank = MemoryBank()
    
    async def optimize(
        self,
        user_input: str,
        context: Optional[str] = None
    ) -> str:
        # 1. 添加用户消息
        await self.session_manager.add_message(
            role=MessageRole.USER,
            content=user_input
        )
        
        # 2. 获取受限的近期历史
        recent_history = await self.session_manager.get_recent_history(
            limit=5  # 只获取最近 5 条
        )
        
        # 3. 获取受限的长期记忆
        long_term_memory = await self.memory_bank.retrieve(
            query=user_input,
            limit=10  # 只获取最相关的 10 条
        )
        
        # 4. 构建提示（已经受限）
        prompt = self._build_context_optimization_prompt(
            user_input,
            recent_history,
            long_term_memory
        )
        
        # 5. 调用 LLM（无需担心 token 累积）
        response = await self.llm_client.generate_async(prompt)
        
        return response
```

**关键点：**
- ✅ SessionManager 内部管理历史限制
- ✅ 获取历史时明确 limit 参数
- ✅ 记忆检索也有 limit
- ✅ 多层限制，自然受限
- ✅ Token 使用：~1,500

---

## 通用工具和技巧

### 1. Token 估算

```python
def estimate_tokens(text: str) -> int:
    """
    估算文本的 token 数量
    
    简单规则：
    - 中文：1 字符 ≈ 1 token
    - 英文：1 单词 ≈ 1.3 tokens
    - 加 10% buffer
    """
    chinese_chars = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    english_words = len([w for w in text.split() if w.isalpha()])
    
    estimated = chinese_chars + int(english_words * 1.3)
    return int(estimated * 1.1)  # 10% buffer

# 使用示例
def _check_token_limit(self, messages: list):
    total_tokens = sum(
        estimate_tokens(m.get("content", ""))
        for m in messages
    )
    
    if total_tokens > 30000:  # 警告阈值
        logger.warning(f"Token 使用较高: {total_tokens}")
    
    return total_tokens
```

### 2. 历史摘要

```python
def _summarize_old_history(
    self,
    old_turns: List[DialogueTurn]
) -> str:
    """
    摘要旧的对话历史
    
    模板摘要（快速，无 LLM 调用）
    """
    if not old_turns:
        return ""
    
    # 统计关键信息
    num_turns = len(old_turns)
    extracted_slots = {}
    for turn in old_turns:
        extracted_slots.update(turn.extracted_slots)
    
    # 生成摘要
    summary = f"之前 {num_turns} 轮对话中，"
    summary += f"用户提供了以下信息：{extracted_slots}"
    
    return summary
```

### 3. 监控和日志

```python
def process_turn(self, user_input):
    # 记录 token 使用
    token_before = self._estimate_current_tokens()
    
    # 处理逻辑
    response = await self._process(user_input)
    
    # 记录 token 变化
    token_after = self._estimate_current_tokens()
    logger.info(
        f"Turn {self.turn_count}: "
        f"Tokens {token_before} → {token_after} "
        f"(Δ{token_after - token_before})"
    )
```

---

## 配置建议

### 默认配置（适合大多数场景）

```python
# DST
DialogueStateTracker(
    max_history_turns=10,          # 保留 10 轮
    enable_history_summary=True,   # 启用摘要
    use_llm_summary=False          # 使用模板摘要（快）
)

# FnCTOD
FnCTODTracker(
    max_history_turns=10,          # 保留 10 轮
    use_two_stage=True             # 两阶段处理
)

# Evolve
SessionManager(
    max_recent_events=10           # 保留 10 条消息
)
```

### 长对话场景（token 敏感）

```python
# DST
DialogueStateTracker(
    max_history_turns=5,           # 减少到 5 轮
    enable_history_summary=True,
    use_llm_summary=False
)

# FnCTOD
FnCTODTracker(
    max_history_turns=5,
    use_two_stage=True
)

# Evolve
SessionManager(
    max_recent_events=5            # 减少到 5 条
)
```

### 详细上下文场景（token 充足）

```python
# DST
DialogueStateTracker(
    max_history_turns=20,          # 增加到 20 轮
    enable_history_summary=True,
    use_llm_summary=True           # 使用 LLM 摘要（质量更高）
)

# FnCTOD
FnCTODTracker(
    max_history_turns=15,
    use_two_stage=True
)

# Evolve
SessionManager(
    max_recent_events=20           # 增加到 20 条
)
```

---

## Token 预算估算

### 典型场景 Token 使用

| 组件 | 简洁配置 | 标准配置 | 详细配置 |
|------|---------|---------|---------|
| 系统指令 | 500 | 2,000 | 3,000 |
| 历史 (10轮) | 800 | 1,000 | 1,500 |
| 当前轮 | 100 | 100 | 100 |
| **总计** | **1,400** | **3,100** | **4,600** |

### 不同模型的上下文限制

| 模型 | 上下文限制 | 建议配置 |
|------|----------|---------|
| Qwen2.5-7B | 32,768 | 标准 (3k) |
| GPT-4 | 8,192 | 简洁 (1.4k) |
| DeepSeek | 32,768 | 标准 (3k) |
| GPT-4-32k | 32,768 | 详细 (4.6k) |

---

## 常见问题

### Q1: 为什么不统一使用 SessionManager？

**A:** 不同模式有不同需求：
- DST 需要 DialogueTurn（包含 extracted_slots）
- FnCTOD 需要 DialogueTurn（包含 function_call）
- Evolve 需要简单的 Message

强制统一会丢失特性。

### Q2: 如何判断 token 使用是否过高？

**A:** 使用 token 估算：
```python
tokens = estimate_tokens(all_messages_content)
if tokens > context_limit * 0.8:  # 超过 80%
    logger.warning("Token 使用接近上限")
```

### Q3: 历史摘要会丢失信息吗？

**A:** 会有信息损失，但：
- 使用模板摘要：保留关键槽位信息
- 使用 LLM 摘要：质量更高但需额外调用
- 最近的历史保持完整

权衡：信息完整性 vs Token 效率

### Q4: 如何调试 token 问题？

**A:** 添加详细日志：
```python
logger.info(f"系统指令: {estimate_tokens(system_prompt)} tokens")
logger.info(f"历史: {estimate_tokens(history)} tokens")
logger.info(f"当前输入: {estimate_tokens(user_input)} tokens")
logger.info(f"总计: {total_tokens} tokens")
```

---

## 总结

### 核心原则回顾

1. ✅ **限制历史长度** - 使用 max_history_turns
2. ✅ **避免累积** - 重置/局部变量/SessionManager
3. ✅ **结构化管理** - 分离历史和消息
4. ✅ **监控 token** - 日志和估算
5. ✅ **适当摘要** - 平衡信息和效率

### 三种模式的选择

| 模式 | 适用场景 | Token 管理方式 |
|------|---------|--------------|
| DST | 槽位填充 | 实例变量重置 |
| FnCTOD | 函数调用 | 局部变量重建 |
| Evolve | 上下文优化 | SessionManager |

**每种都已优化，无需统一！**

---

**文档版本**: 1.0  
**创建日期**: 2026-02-06  
**适用版本**: ContextMind v0.2+
