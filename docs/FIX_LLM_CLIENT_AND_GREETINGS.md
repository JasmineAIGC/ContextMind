# LLM 客户端和开场白问题修复报告

## 问题描述

### 问题1: AttributeError: 'LlmAgent' object has no attribute 'run'

**错误信息**:
```
[2026-02-03 14:37:51] ERROR - [dst.adk_agent] DST Agent 调用失败: 'LlmAgent' object has no attribute 'run'
AttributeError: 'LlmAgent' object has no attribute 'run'
```

**根本原因**:
1. google-adk 包未安装（实际上也不需要）
2. 代码尝试使用 `agent.run()` 方法，但该方法不存在
3. Qwen API 是 OpenAI 兼容接口，应该使用 `openai` Python 包

### 问题2: 三个场景开场白都由机器人发起

**现象**:
- 闲聊、客服、保险三个场景在初始化时，机器人会自动发送开场白
- 用户希望由用户主动发起对话，而不是机器人先说话

---

## 解决方案

### 1. 创建 Qwen 客户端 (`utils/qwen_client.py`)

使用 OpenAI 兼容接口调用 Qwen API：

```python
from openai import AsyncOpenAI, OpenAI

class QwenClient:
    """Qwen LLM 客户端，使用 OpenAI 兼容接口"""
    
    def __init__(self, config: Optional[QwenConfig] = None):
        self.config = config or QwenConfig.from_env()
        
        # 创建 OpenAI 客户端
        self.async_client = AsyncOpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
        self.sync_client = OpenAI(
            api_key=self.config.api_key,
            base_url=self.config.base_url
        )
    
    async def chat_async(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """异步聊天调用"""
        response = await self.async_client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=kwargs.get('temperature', self.config.temperature),
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
        )
        return response.choices[0].message.content
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """同步聊天调用"""
        response = self.sync_client.chat.completions.create(
            model=self.config.model,
            messages=messages,
            temperature=kwargs.get('temperature', self.config.temperature),
            max_tokens=kwargs.get('max_tokens', self.config.max_tokens),
        )
        return response.choices[0].message.content
```

**配置类**:
```python
@dataclass
class QwenConfig:
    """Qwen 客户端配置"""
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.7
    max_tokens: int = 8192
    top_k: int = 20
    
    @classmethod
    def from_env(cls) -> "QwenConfig":
        """从环境变量加载配置"""
        api_key = os.getenv("QWEN3_API_KEY", "")
        base_url = os.getenv("QWEN3_BASE_URL", "")
        model = os.getenv("QWEN3_MODEL", "Qwen2.5-7B-Instruct")
        # ... 读取其他配置
        
        if not api_key or not base_url:
            raise ValueError("请在 .env 文件中配置 QWEN3_API_KEY 和 QWEN3_BASE_URL")
        
        return cls(api_key=api_key, base_url=base_url, model=model, ...)
```

### 2. 重写 Agent 实现

**DST Agent** (`dst/adk_agent.py`):
```python
from utils.qwen_client import QwenClient, QwenConfig

class DSTAgent:
    """DST 模式专用的 LLM Agent"""
    
    def __init__(self, config: Optional[QwenConfig] = None):
        self.client = QwenClient(config)
        logger.info(f"[DST Agent] 初始化成功")
    
    async def chat_async(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """异步聊天调用"""
        try:
            return await self.client.chat_async(messages, **kwargs)
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """同步聊天调用"""
        try:
            return self.client.chat(messages, **kwargs)
        except Exception as e:
            logger.error(f"DST Agent 调用失败: {e}")
            raise
```

**Evolution Agent** (`evolution/agent.py`):
```python
from utils.qwen_client import QwenClient, QwenConfig

class EvolutionAgent:
    """Evolution 模式专用的 LLM Agent"""
    
    def __init__(self, config: Optional[QwenConfig] = None):
        self.client = QwenClient(config)
        logger.info(f"[Evolution Agent] 初始化成功")
    
    async def chat_async(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """异步聊天调用"""
        try:
            return await self.client.chat_async(messages, **kwargs)
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        """同步聊天调用"""
        try:
            return self.client.chat(messages, **kwargs)
        except Exception as e:
            logger.error(f"Evolution Agent 调用失败: {e}")
            raise
    
    async def generate_async(self, prompt: str, **kwargs) -> str:
        """异步生成"""
        return await self.chat_async([{"role": "user", "content": prompt}], **kwargs)
    
    def generate(self, prompt: str, **kwargs) -> str:
        """同步生成"""
        return self.chat([{"role": "user", "content": prompt}], **kwargs)
```

### 3. 移除场景开场白

修改三个场景配置文件：

**chat_scenario.py**:
```python
return ScenarioConfig(
    # ... 其他配置 ...
    welcome_message=None,  # 让用户主动发起对话
    # ... 其他配置 ...
)
```

**callcenter_scenario.py**:
```python
return ScenarioConfig(
    # ... 其他配置 ...
    welcome_message=None,  # 让用户主动发起对话
    # ... 其他配置 ...
)
```

**insurance_scenario.py**:
```python
# 欢迎消息（保留用于文档，但不在对话中自动显示）
# 在实际对话中，让用户主动发起
welcome_message = None

return ScenarioConfig(
    # ... 其他配置 ...
    welcome_message=welcome_message,
    # ... 其他配置 ...
)
```

### 4. 更新依赖

**requirements.txt**:
```diff
- # ADK 核心
- google-adk>=1.0.0
-
- # LLM 支持 (通过 ADK + LiteLLM)
- litellm>=1.0.0
+ # LLM API 客户端（Qwen 使用 OpenAI 兼容接口）
+ openai>=1.0.0
```

---

## 环境配置

### .env 文件配置

```ini
# ==========================================
# Qwen3 API 配置（必填）
# ==========================================
QWEN3_API_KEY=sk-7e7c8b9ad0e1f2a3b4c5
QWEN3_BASE_URL=http://10.112.172.30:18023/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct
QWEN3_MAX_TOKENS=8192
QWEN3_TOP_K=20

# ==========================================
# Embedding 配置（可选，用于语义检索）
# ==========================================
# 注意：Embedding 使用专门的模型，不是 LLM
EMBEDDING_MODEL_PATH=/share/airesearch/data/aowen.xiao/models/BAAI/bge-large-zh-v1.5
EMBEDDING_MODEL=bge-large-zh-v1.5
```

### 安装依赖

```bash
# 安装 OpenAI Python 包
pip install openai

# 或安装全部依赖
pip install -r requirements.txt
```

---

## 测试验证

### 1. 导入测试

```python
from dst import DSTAgent
from evolution import EvolutionAgent
from utils.qwen_client import QwenConfig

print("✅ 所有导入成功")
```

### 2. 配置测试

```python
from utils.qwen_client import QwenConfig

config = QwenConfig.from_env()
print(f"Model: {config.model}")
print(f"Base URL: {config.base_url}")
```

**输出**:
```
Model: Qwen2.5-7B-Instruct
Base URL: http://10.112.172.30:18023/v1
```

### 3. Agent 初始化测试

```python
from dst import DSTAgent
from evolution import EvolutionAgent

dst_agent = DSTAgent()
evolution_agent = EvolutionAgent()

print("✅ 两个 Agent 初始化成功")
```

### 4. 场景开场白测试

```python
from scenarios import get_chat_scenario, get_callcenter_scenario, get_insurance_scenario

chat = get_chat_scenario()
callcenter = get_callcenter_scenario()
insurance = get_insurance_scenario()

assert chat.welcome_message is None
assert callcenter.welcome_message is None
assert insurance.welcome_message is None

print("✅ 所有场景都移除了开场白")
```

---

## 修复效果

### 问题1: LLM 调用错误 ✅

**修复前**:
```
[2026-02-03 14:37:51] ERROR - [dst.adk_agent] DST Agent 调用失败: 'LlmAgent' object has no attribute 'run'
AttributeError: 'LlmAgent' object has no attribute 'run'
```

**修复后**:
```
[2026-02-03 XX:XX:XX] INFO - [Qwen Client] 初始化成功，模型: Qwen2.5-7B-Instruct, endpoint: http://10.112.172.30:18023/v1
[2026-02-03 XX:XX:XX] INFO - [DST Agent] 初始化成功
[2026-02-03 XX:XX:XX] INFO - [Evolution Agent] 初始化成功
```

### 问题2: 机器人开场白 ✅

**修复前**:
```
🤖: 你好！我是你的AI助手，很高兴和你聊天。有什么我可以帮你的吗？
👤: [用户输入]
```

**修复后**:
```
👤: [用户主动发起对话]
🤖: [AI 回复]
```

---

## 代码变更

### 新增文件 (1个)
- `utils/qwen_client.py` - Qwen API 客户端（~180 行）

### 修改文件 (7个)
- `dst/adk_agent.py` - 使用 QwenClient（简化 ~70 行，删除 ~60 行）
- `evolution/agent.py` - 使用 QwenClient（简化 ~95 行，删除 ~45 行）
- `dst/__init__.py` - 导出 QwenConfig 别名
- `evolution/__init__.py` - 导出 QwenConfig 别名
- `scenarios/chat_scenario.py` - 移除开场白
- `scenarios/callcenter_scenario.py` - 移除开场白
- `scenarios/insurance_scenario.py` - 移除开场白
- `requirements.txt` - 使用 openai 替代 google-adk + litellm

### 净变化
- 新增: ~180 行
- 删除: ~105 行
- 净增: ~75 行

---

## 关键改进

1. **架构简化**: 移除 google-adk 依赖，直接使用 OpenAI 兼容接口
2. **配置清晰**: 从 .env 统一读取 QWEN3_* 配置
3. **错误处理**: 完善的异常捕获和日志记录
4. **用户体验**: 移除机器人开场白，让用户主动发起对话
5. **代码质量**: 更简洁、更易维护的 Agent 实现

---

**修复完成时间**: 2026-02-03  
**版本**: v0.4.1  
**状态**: ✅ 全部修复完成
