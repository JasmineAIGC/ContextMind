# LLM 客户端架构说明

## 当前架构

ContextMind v0.4.0 使用 **SimpleLLMClient** 作为统一的 LLM 客户端。

### SimpleLLMClient 特点

1. **兼容性**
   - 支持 OpenAI API 标准
   - 兼容所有 OpenAI-compatible API
   - 包括：Qwen（通义千问）、DeepSeek、本地模型等

2. **灵活性**
   - 支持自定义 base_url
   - 支持多种认证方式
   - 支持同步和异步调用

3. **统一性**
   - ContextMind 模式使用
   - Baseline DST 模式使用
   - 所有 demo 统一使用

## 关于 google-adk

### 为什么不迁移到 adk-python？

#### 1. 使用范围局限

**google-adk 主要用途：**
- Google AI Studio API
- Gemini 模型专用
- Google 生态系统

**SimpleLLMClient 支持：**
- OpenAI GPT 系列
- Anthropic Claude 系列
- Qwen（通义千问）
- 其他 OpenAI-compatible APIs
- 本地部署模型

#### 2. 架构复杂度

**google-adk：**
- 为 Google AI Studio 设计
- 包含许多特定功能
- 学习曲线较陡

**SimpleLLMClient：**
- 简单直观
- 易于理解和维护
- 符合标准 OpenAI API

#### 3. 依赖管理

**当前状态：**
- `google-adk` 在 requirements.txt 中
- 但代码中未实际使用
- 可能是早期测试遗留

**建议：**
- 如果不使用 Google AI Studio，可以移除
- 保持依赖最小化

### PromptManager 通用化方案

v0.4.0 通过 **PromptManager 通用化** 实现了对不同 LLM 的支持：

```python
from dst import PromptManager, Language, LLMFormat

# OpenAI 格式
pm_openai = PromptManager(
    language=Language.EN_US,
    llm_format=LLMFormat.OPENAI,
    template_style="structured"
)

# Google (Gemini) 格式
pm_google = PromptManager(
    language=Language.EN_US,
    llm_format=LLMFormat.GOOGLE,
    template_style="conversational"
)

# Qwen 格式
pm_qwen = PromptManager(
    language=Language.ZH_CN,
    llm_format=LLMFormat.QWEN,
    template_style="concise"
)
```

### 架构优势

#### 1. 统一接口

```python
# SimpleLLMClient 提供统一接口
llm = SimpleLLMClient()

# 同步调用
response = llm.chat(messages)

# 异步调用
response = await llm.chat_async(messages)
```

#### 2. 配置灵活

```python
# 通过 .env 配置不同的后端
# OpenAI
OPENAI_API_KEY=sk-xxx
OPENAI_BASE_URL=https://api.openai.com/v1

# Qwen
QWEN3_API_KEY=sk-xxx
QWEN3_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1

# 本地模型
LLM_BASE_URL=http://localhost:8000/v1
```

#### 3. 提示词适配

PromptManager 根据 LLM 格式自动调整：
- 上下文长度限制
- 提示词风格
- 输出格式要求

### 未来扩展

如果需要 Google AI Studio 的特定功能：

1. **保留 SimpleLLMClient** - 作为默认客户端
2. **添加 GoogleADKClient** - 作为可选客户端
3. **抽象接口** - 统一的 LLMClient 接口

```python
# 抽象接口（未来可选）
class LLMClient(ABC):
    @abstractmethod
    async def chat_async(self, messages: List[Dict]) -> str:
        pass

# 当前实现
class SimpleLLMClient(LLMClient):
    # OpenAI-compatible

# 可选实现
class GoogleADKClient(LLMClient):
    # Google AI Studio specific
```

## 建议

### 对于当前项目

1. **保持 SimpleLLMClient** - 简单、灵活、够用
2. **PromptManager 通用化** - 已实现，支持所有主流 LLM
3. **移除未使用的依赖** - 考虑从 requirements.txt 移除 google-adk

### 对于未来扩展

1. **按需添加** - 只在需要特定功能时添加新客户端
2. **保持兼容** - 新客户端应实现统一接口
3. **文档说明** - 清晰说明不同客户端的适用场景

## 总结

**ContextMind v0.4.0 的 LLM 架构：**

✅ **SimpleLLMClient** - 统一的 LLM 客户端  
✅ **PromptManager** - 通用的提示词管理（支持多LLM格式）  
✅ **灵活配置** - 通过 .env 切换不同后端  
✅ **简单维护** - 代码简洁，易于理解  

**不需要迁移到 adk-python，因为：**

❌ 使用范围受限（仅 Google）  
❌ 增加复杂度  
❌ 当前方案已足够灵活  

当前架构是最优选择！🎉
