# Prompt 优化与对话摘要设计方案

## 设计日期
2026-01-21

## 问题分析

### 当前问题
1. **Prompt 过长**: 每次都包含所有对话历史(20条)和所有记忆(6条)
2. **噪音日志**: HTTP连接、发送、接收的底层日志污染输出
3. **无选择策略**: 没有智能选择最相关的历史和记忆
4. **缺少摘要**: 长对话没有摘要机制，context越来越长
5. **摘要使用不明**: 即使有摘要也不知道如何使用

## 解决方案设计

### 1. Prompt 内容优化策略

#### 1.1 记忆选择策略
- **相关性过滤**: 只包含相关性分数 >= 0.3 的记忆
- **数量限制**: 最多5条最相关记忆
- **优先级排序**: 
  1. 高分记忆 (score >= 0.7) 优先
  2. 最近访问的记忆
  3. 用户明确提及的记忆

#### 1.2 对话历史选择策略
- **基础策略**: 最近N轮对话（N可配置，默认5-10轮）
- **智能策略**: 
  - 最近2轮：必须包含（保持连贯性）
  - 中间历史：基于相关性选择
  - 早期历史：仅在非常相关时包含

#### 1.3 Prompt 结构
```
[系统提示词]

[相关记忆] (最多5条，score >= 0.3)
- [TYPE] 记忆内容

[对话摘要] (如果对话轮次 > 15)
前10轮对话摘要: XXX

[最近对话] (最近5轮)
user: XXX
assistant: XXX
...

[当前输入]
user: XXX
```

### 2. 对话摘要设计

#### 2.1 触发条件
- **轮次触发**: 对话轮次达到15轮时，对前10轮生成摘要
- **增量摘要**: 每增加10轮，对之前未摘要的部分生成新摘要

#### 2.2 摘要策略
**方案A: 基于规则的摘要（快速）**
- 提取关键事实和偏好
- 识别话题转换
- 保留重要信息点

**方案B: LLM生成摘要（高质量）**
- 使用LLM理解和压缩对话
- 保留关键上下文
- 更自然的表达

**推荐**: 根据配置选择，默认规则摘要，可选LLM摘要

#### 2.3 摘要使用方式
1. **替代原始对话**: 摘要的对话不再详细包含
2. **元数据标记**: 标记哪些对话已被摘要
3. **检索增强**: 摘要也可被检索和引用
4. **分层存储**:
   - Level 1: 最近对话（完整保留）
   - Level 2: 中期对话（摘要）
   - Level 3: 早期对话（提取知识后归档）

#### 2.4 摘要示例
```
前10轮对话摘要:
用户自我介绍为"一二"，喜欢数学和雪花。表示更喜欢旅行和亲近大自然，但因是重庆人，
只在重庆转过，未去外地。用户喜欢火锅，尤其是麻辣锅底，喜欢的食材包括毛肚、鸭血和豆皮。
```

### 3. 日志优化

#### 3.1 移除噪音日志
- **禁用 HTTPX/HTTPCORE 日志**: 设置日志级别为WARNING或ERROR
- **过滤网络层日志**: connect_tcp, send_request, receive 等
- **保留业务日志**: LLM请求/响应、知识提取、上下文优化

#### 3.2 日志级别配置
```python
import logging

# 禁用HTTP库的debug日志
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.INFO)  # 只保留INFO级别
```

### 4. 实现优先级

#### Phase 1: 立即修复（Critical）
- [x] 禁用HTTP debug日志
- [x] 限制Prompt中的历史数量（5-10轮）
- [x] 限制记忆数量（最多5条）

#### Phase 2: 短期优化（High）
- [ ] 实现基于相关性的历史选择
- [ ] 基于规则的对话摘要
- [ ] 摘要存储和检索

#### Phase 3: 长期改进（Medium）
- [ ] LLM生成的对话摘要
- [ ] 多级对话缓存策略
- [ ] 个性化Prompt策略

## 实现细节

### Prompt 构建逻辑（新）

```python
def build_prompt_optimized(self, user_input: str, context: ContextResult) -> str:
    """优化后的 Prompt 构建"""
    prompt_parts = [self.system_prompt]
    
    # 1. 相关记忆（最多5条，分数>=0.3）
    memories = [item for item in context.items 
                if item.source == ContextSource.MEMORY and item.score >= 0.3]
    if memories:
        top_memories = sorted(memories, key=lambda x: x.score, reverse=True)[:5]
        memory_text = "\n".join(f"- {m.content}" for m in top_memories)
        prompt_parts.append(f"\n## 已知信息\n{memory_text}")
    
    # 2. 对话摘要（如果对话 > 15轮）
    history = [item for item in context.items if item.source == ContextSource.HISTORY]
    total_turns = len(history)
    
    if total_turns > 15:
        # 生成前N轮摘要
        summary_turns = total_turns - 5
        summary = self._summarize_history(history[:summary_turns])
        prompt_parts.append(f"\n## 早期对话摘要\n{summary}")
        recent_history = history[-5:]
    else:
        # 所有历史都包含
        recent_history = history[-10:]  # 最多10轮
    
    # 3. 最近对话（5-10轮）
    if recent_history:
        history_text = "\n".join(item.content for item in recent_history)
        prompt_parts.append(f"\n## 对话历史\n{history_text}")
    
    # 4. 当前输入
    prompt_parts.append(f"\n## 当前问题\nuser: {user_input}")
    
    return "\n".join(prompt_parts)

def _summarize_history(self, history_items: List[ContextItem]) -> str:
    """生成对话摘要"""
    # TODO: 实现摘要逻辑
    # 方案A: 基于规则提取关键信息
    # 方案B: 使用LLM生成摘要
    pass
```

## 配置参数

```python
class PromptConfig:
    """Prompt 优化配置"""
    
    # 记忆配置
    max_memories: int = 5  # 最多包含的记忆数
    memory_relevance_threshold: float = 0.3  # 记忆相关性阈值
    
    # 对话历史配置
    max_recent_turns: int = 10  # 最多包含的最近对话轮数
    summarize_threshold: int = 15  # 触发摘要的对话轮数阈值
    keep_recent_turns: int = 5  # 摘要后保留的最近对话轮数
    
    # 摘要配置
    enable_summarization: bool = True  # 是否启用对话摘要
    summarization_method: str = "rule"  # 摘要方式: 'rule' 或 'llm'
    
    # 日志配置
    disable_http_logs: bool = True  # 禁用HTTP日志
```

## 总结

通过以上设计，我们将实现：

1. **更短的Prompt**: 从包含所有历史到智能选择5-10轮
2. **更干净的日志**: 移除HTTP噪音，只保留业务日志
3. **智能选择策略**: 基于相关性和重要性选择内容
4. **对话摘要机制**: 自动压缩长对话历史
5. **灵活的配置**: 支持不同场景的配置需求

这将显著提升：
- Prompt 质量和相关性
- 系统性能（更短的prompt）
- 开发调试体验（清晰的日志）
- 长对话场景支持（通过摘要）
