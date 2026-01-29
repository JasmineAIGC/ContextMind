# 对比实验指南 - Baseline Template vs ContextMind

## 概述

本指南说明如何进行槽位模板基线方式与上下文工程方式的对比实验。

## 两种方式的核心差异

### Baseline Template（槽位模板基线）

**位置**：`baseline_template/` 模块

**核心特点**：
- ✅ 完全独立的模块
- ❌ **不使用记忆库**
- ❌ **不使用向量检索**
- ✅ 只基于对话历史
- ✅ 规则提取 + 模板填充

**工作流程**：
```
对话历史
    ↓
规则意图提取 (< 5ms)
    ↓
模板填充 (< 1ms)
    ↓
生成提示词
```

**适用场景**：
- 作为对比基准
- 简单对话场景
- 不需要长期记忆
- 追求极致速度

### ContextMind（上下文工程）

**位置**：`contextmind/` 模块

**核心特点**：
- ✅ 完整的上下文工程框架
- ✅ **使用记忆库**
- ✅ **使用向量检索**
- ✅ 基于对话历史 + 长期记忆
- ✅ 多策略优化

**工作流程**：
```
对话历史 + 记忆库
    ↓
向量检索相关记忆
    ↓
上下文优化策略
    ↓
上下文压缩/重排
    ↓
生成提示词
```

**适用场景**：
- 复杂对话场景
- 需要长期记忆
- 需要个性化
- 追求对话质量

## 实验设置

### 1. 统一系统提示词

**重要**：使用 `prompts.py` 中的统一提示词确保公平性。

```python
# 两种方式都使用相同的系统提示词
from prompts import CHAT_SYSTEM_PROMPT  # 或 CALLCENTER_SYSTEM_PROMPT

# Baseline 方式
baseline_engine = TemplateEngine(system_prompt=CHAT_SYSTEM_PROMPT)

# ContextMind 方式
context_engine = ContextEngine(...)
app = ChatApplication(
    context_engine=context_engine,
    system_prompt=CHAT_SYSTEM_PROMPT  # 使用相同的提示词
)
```

### 2. 准备测试数据集

创建标准的对话历史数据集：

```python
# test_conversations.py

TEST_CONVERSATIONS = [
    {
        "id": 1,
        "name": "简单问候",
        "messages": [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！有什么可以帮助你的？"},
            {"role": "user", "content": "今天天气怎么样？"},
        ]
    },
    {
        "id": 2,
        "name": "多轮对话",
        "messages": [
            {"role": "user", "content": "我想学习编程"},
            {"role": "assistant", "content": "很好！建议从Python开始。"},
            {"role": "user", "content": "为什么选Python？"},
            {"role": "assistant", "content": "Python语法简单，适合初学者。"},
            {"role": "user", "content": "需要什么准备？"},
        ]
    },
    {
        "id": 3,
        "name": "需要记忆的对话",
        "messages": [
            {"role": "user", "content": "我叫张三，喜欢打篮球"},
            {"role": "assistant", "content": "很高兴认识你张三！篮球是很棒的运动。"},
            # ... 中间10轮其他对话 ...
            {"role": "user", "content": "你还记得我喜欢什么运动吗？"},
        ]
    },
]
```

### 3. 实验代码示例

```python
import asyncio
from baseline_template import TemplateEngine, Message
from contextmind import ContextEngine
from examples.chat_app import ChatApplication
from prompts import CHAT_SYSTEM_PROMPT

async def run_comparison_experiment():
    """运行对比实验"""
    
    # 1. 准备测试数据
    test_conversation = [
        Message(role="user", content="你好"),
        Message(role="assistant", content="你好！"),
        Message(role="user", content="今天天气怎么样？"),
    ]
    
    # 2. Baseline 方式
    print("=" * 80)
    print("方式1: Baseline Template")
    print("=" * 80)
    
    import time
    baseline_engine = TemplateEngine(system_prompt=CHAT_SYSTEM_PROMPT)
    
    start_time = time.time()
    baseline_prompt = await baseline_engine.generate_prompt(test_conversation)
    baseline_time = time.time() - start_time
    
    print(f"⏱️  耗时: {baseline_time*1000:.2f}ms")
    print(f"📏 提示词长度: {len(baseline_prompt)} 字符")
    print(f"📝 提示词预览:\n{baseline_prompt[:200]}...\n")
    
    # 3. ContextMind 方式
    print("=" * 80)
    print("方式2: ContextMind")
    print("=" * 80)
    
    context_engine = ContextEngine(app_name="test", user_id="test_user")
    app = ChatApplication(
        context_engine=context_engine,
        system_prompt=CHAT_SYSTEM_PROMPT
    )
    
    # 添加对话历史到会话
    for msg in test_conversation[:-1]:  # 除了最后一条
        await context_engine.session_manager.add_message(
            role=msg.role,
            content=msg.content
        )
    
    start_time = time.time()
    context_result = await context_engine.optimize(
        user_input=test_conversation[-1].content
    )
    contextmind_prompt = app.build_prompt(
        test_conversation[-1].content,
        context_result
    )
    contextmind_time = time.time() - start_time
    
    print(f"⏱️  耗时: {contextmind_time*1000:.2f}ms")
    print(f"📏 提示词长度: {len(contextmind_prompt)} 字符")
    print(f"📝 提示词预览:\n{contextmind_prompt[:200]}...\n")
    
    # 4. 对比总结
    print("=" * 80)
    print("对比总结")
    print("=" * 80)
    print(f"速度对比: Baseline {baseline_time*1000:.2f}ms vs ContextMind {contextmind_time*1000:.2f}ms")
    print(f"速度提升: {contextmind_time/baseline_time:.1f}x")
    print(f"长度对比: Baseline {len(baseline_prompt)} vs ContextMind {len(contextmind_prompt)}")
    print()

if __name__ == "__main__":
    asyncio.run(run_comparison_experiment())
```

## 评估指标

### 1. 定量指标

| 指标 | 测量方法 | Baseline | ContextMind |
|-----|---------|----------|-------------|
| **响应速度** | 从输入到生成提示词的时间 | < 10ms | 视情况而定 |
| **提示词长度** | 字符数 | 相对较短 | 可能更长 |
| **上下文项数量** | 包含的历史/记忆项 | 仅历史 | 历史+记忆 |
| **内存使用** | 峰值内存 | 极低 | 较高 |

### 2. 定性指标

| 指标 | 评估方法 | 说明 |
|-----|---------|------|
| **对话连贯性** | 人工评分 1-5 | 多轮对话的逻辑连贯性 |
| **记忆效果** | 特定测试用例 | 能否记住用户信息 |
| **响应相关性** | 人工评分 1-5 | 回复是否切题 |
| **个性化程度** | 人工评分 1-5 | 是否体现个性化 |

### 3. 测试用例设计

**用例1：短对话（1-3轮）**
- 预期：两种方式差异不大
- 关注：速度、简洁性

**用例2：中等对话（5-10轮）**
- 预期：开始出现差异
- 关注：上下文理解

**用例3：长对话（15+轮）**
- 预期：差异明显
- 关注：记忆效果、连贯性

**用例4：需要长期记忆**
- 示例：用户分享个人信息，稍后询问
- 预期：ContextMind 有明显优势
- 关注：记忆检索能力

## 实验记录模板

```markdown
### 实验记录

**日期**: 2026-01-29
**测试者**: 张三
**测试用例**: 需要长期记忆的对话

#### 测试设置
- 系统提示词: CHAT_SYSTEM_PROMPT
- 对话轮数: 15轮
- 包含个人信息: 姓名、爱好、工作

#### 结果

| 指标 | Baseline | ContextMind | 备注 |
|-----|----------|-------------|------|
| 响应时间 | 8ms | 150ms | - |
| 提示词长度 | 500字符 | 800字符 | - |
| 连贯性评分 | 3/5 | 5/5 | - |
| 记忆效果 | ❌ 未记住 | ✅ 准确记住 | - |
| 个性化 | 2/5 | 5/5 | - |

#### 观察
- Baseline 方式速度快但无法记住早期对话中的个人信息
- ContextMind 成功检索到相关记忆并体现在回复中
- 速度差异可接受，质量提升明显

#### 结论
对于需要长期记忆的场景，ContextMind 有显著优势。
```

## 预期实验结果

### 场景1：简单对话

**预期**：
- Baseline 和 ContextMind 差异不大
- Baseline 速度优势明显
- 两者回复质量相近

**建议**：
- 简单场景可使用 Baseline
- 追求速度时优先 Baseline

### 场景2：复杂对话

**预期**：
- ContextMind 在连贯性上更好
- ContextMind 能利用早期对话信息
- Baseline 可能"忘记"早期内容

**建议**：
- 复杂场景使用 ContextMind
- 需要记忆时必须用 ContextMind

### 场景3：个性化服务

**预期**：
- ContextMind 能记住用户偏好
- Baseline 每次都是"新用户"
- 长期使用效果差异巨大

**建议**：
- 个性化场景只能用 ContextMind
- Baseline 不适合此类场景

## 优化建议

### Baseline Template 优化

1. **扩展意图识别规则**
   - 添加更多关键词
   - 改进分类逻辑

2. **丰富模板**
   - 针对不同场景设计专门模板
   - 添加更多槽位

3. **提升提取准确度**
   - 改进主题提取算法
   - 优化上下文摘要

### ContextMind 优化

1. **记忆库调优**
   - 调整检索阈值
   - 优化向量模型

2. **策略优化**
   - 尝试不同优化策略
   - 平衡速度和质量

3. **提示词工程**
   - 优化系统提示词
   - 改进上下文组织

## 总结

### Baseline Template 的价值

- ✅ 作为性能基准
- ✅ 简单场景的实用选择
- ✅ 帮助理解核心原理
- ✅ 快速原型开发

### ContextMind 的价值

- ✅ 复杂场景的最佳选择
- ✅ 长期记忆和个性化
- ✅ 工业级对话系统
- ✅ 可扩展的架构

### 选择建议

| 场景 | 推荐方式 | 原因 |
|-----|---------|------|
| 简单问答 | Baseline | 速度快，够用 |
| 客服系统 | ContextMind | 需要记忆客户信息 |
| 闲聊机器人 | ContextMind | 需要个性化和连贯性 |
| 快速原型 | Baseline | 开发简单 |
| 生产系统 | ContextMind | 功能完整 |

---

**文档版本**: v1.0  
**最后更新**: 2026-01-29
