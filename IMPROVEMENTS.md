# ContextMind 改进建议

## 📋 改进建议列表

基于项目分析，以下是按优先级排序的改进建议。

---

## 🔴 高优先级 (必须修复)

### 1. 修复记忆服务 API 调用错误

**问题**: 
```python
ERROR - contextmind.engine - ❌ Failed to seed memory: 'InMemoryMemoryService' object has no attribute 'persist_session'
```

**位置**: `contextmind/engine.py` line 337

**当前代码**:
```python
await self.memory_service.persist_session(
    session_id=uuid.uuid4().hex,
    author="system",
    content=Content(role="system", parts=[Part(text=fact)]),
)
```

**问题分析**:
- `InMemoryMemoryService` 没有 `persist_session` 方法
- 需要查阅 Google ADK 文档确认正确的 API

**建议修复**:
```python
# 方案 1: 使用正确的 API
await self.memory_service.add_memory(
    content=Content(role="system", parts=[Part(text=fact)]),
    metadata={"author": "system", "type": "seed"}
)

# 方案 2: 创建 Event 后添加
from google.adk.events.event import Event
event = Event(
    invocation_id=uuid.uuid4().hex,
    author="system",
    content=Content(role="system", parts=[Part(text=fact)]),
)
await self.memory_service.add_event(event)
```

**影响**: 
- 长期记忆功能无法正常工作
- 影响对话质量和用户体验

**优先级**: 🔴 最高

---

### 2. 添加依赖版本锁定

**问题**:
```txt
# requirements.txt
google-adk        # ❌ 没有版本号
openai            # ❌ 没有版本号
python-dotenv     # ❌ 没有版本号
```

**风险**:
- 依赖升级可能导致兼容性问题
- 团队成员可能使用不同版本
- 无法精确复现问题

**建议**:
```txt
# requirements.txt
google-adk==0.1.0          # 使用实际测试过的版本
openai==1.10.0
python-dotenv==1.0.0
gradio>=4.0.0,<5.0.0
aiofiles>=23.0.0,<24.0.0
```

**实施步骤**:
1. 在当前环境运行 `pip freeze > requirements-lock.txt`
2. 查看所有依赖的实际版本
3. 更新 `requirements.txt` 添加版本号
4. 测试安装是否成功

**优先级**: 🔴 高

---

### 3. 完善 .gitignore 文件

**问题**: 可能包含敏感文件或临时文件

**建议添加**:
```gitignore
# Environment
.env
.env.local
*.env

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Logs
*.log
logs/
*.log.*

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db

# Gradio
flagged/
gradio_cached_examples/

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/

# Temporary files
tmp/
temp/
*.tmp
```

**优先级**: 🔴 高

---

## 🟡 中优先级 (重要改进)

### 4. 添加单元测试

**当前状态**: 无测试文件

**建议创建测试结构**:
```
tests/
├── __init__.py
├── conftest.py                 # pytest 配置和 fixtures
├── unit/
│   ├── __init__.py
│   ├── test_client.py         # 测试 LLM 客户端
│   ├── test_engine.py         # 测试核心引擎
│   ├── test_logger.py         # 测试日志系统
│   └── test_utils.py          # 测试工具函数
├── integration/
│   ├── __init__.py
│   ├── test_session_flow.py  # 测试会话流程
│   └── test_memory_flow.py   # 测试记忆流程
└── fixtures/
    ├── __init__.py
    ├── mock_llm.py            # Mock LLM 响应
    └── sample_data.py         # 示例数据
```

**示例测试代码**:
```python
# tests/unit/test_engine.py
import pytest
from contextmind import ContextEngine, Client, ClientConfig

@pytest.fixture
def mock_client(monkeypatch):
    """Mock LLM 客户端"""
    class MockClient:
        async def generate(self, prompt, **kwargs):
            return "这是一个测试回复"
    return MockClient()

@pytest.mark.asyncio
async def test_process_turn_basic(mock_client):
    """测试基本对话处理"""
    engine = ContextEngine(
        app_name="test",
        user_id="test-user",
        llm_client=mock_client,
    )
    
    result = await engine.process_turn("你好")
    
    assert result.response == "这是一个测试回复"
    assert engine.get_interaction_count() == 1

@pytest.mark.asyncio
async def test_memory_persistence(mock_client):
    """测试记忆持久化"""
    from google.adk.memory import InMemoryMemoryService
    
    memory_service = InMemoryMemoryService()
    engine = ContextEngine(
        app_name="test",
        user_id="test-user",
        llm_client=mock_client,
        memory_service=memory_service
    )
    
    # 植入记忆
    await engine.seed_memory(["测试记忆1", "测试记忆2"])
    
    # 验证记忆已保存
    # TODO: 添加验证逻辑
```

**测试覆盖目标**:
- 单元测试覆盖率 >= 80%
- 核心功能 100% 覆盖

**优先级**: 🟡 中高

---

### 5. 配置文件化

**问题**: 业务逻辑硬编码在代码中

**建议**: 创建配置文件系统

**示例配置文件 `config/scenarios/customer_service.yaml`**:
```yaml
# 客服场景配置
scenario:
  name: "优逸花客服"
  description: "电话推销预留额度"

system_prompt: |
  你是优逸花客服，正在给用户打电话提醒申请预留额度。
  你的回复必须专业、简洁、直接，严格遵守客服话术规范。

user_profile:
  姓名: "胡女士"
  年龄: "35-45岁"
  性别: "女"
  历史行为: "多次拒绝推销，对电话推销比较敏感"
  风险等级: "高"

business_rules:
  core_duties:
    专业介绍: "专业、礼貌地介绍优逸花预留额度服务"
    策略调整: "根据用户反馈调整沟通策略"
    合规要求: "遵守合规要求，不误导用户"
  
  communication_strategy:
    开场策略: "开场确认身份，简明说明来意"
    产品定位: "强调'预留额度'而非'借款'"
    优势突出: "突出'方便后续资金周转'的优势"
    拒绝处理: "遇到拒绝时礼貌结束对话"
  
  reply_requirements:
    格式要求: "严格按照客服身份直接回复，不要使用任何格式标记"
    内容要求: "不要使用引号、JSON、markdown等格式，直接输出纯文本"
    禁止事项: "禁止输出分析过程、思考过程、推理过程"

engine_config:
  max_recent_events: 6
  summary_interval: 5
  use_memory: true

memory_seeds:
  - "用户多次要求停止推销并威胁报警。"
  - "用户对重复来电极度反感，情绪长期处于愤怒状态。"
  - "所有客服在再次联系该用户时必须立即道歉并承诺不再打扰。"
  - "若用户强调'别烦我'或提及报警，需第一时间结束对话并致歉。"
```

**实现代码**:
```python
# contextmind/config.py
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional

@dataclass
class ScenarioConfig:
    """场景配置"""
    name: str
    description: str
    system_prompt: str
    user_profile: Dict
    business_rules: Dict
    engine_config: Dict
    memory_seeds: List[str]
    
    @classmethod
    def from_yaml(cls, path: str) -> "ScenarioConfig":
        """从 YAML 文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        scenario = data['scenario']
        return cls(
            name=scenario['name'],
            description=scenario['description'],
            system_prompt=data['system_prompt'],
            user_profile=data['user_profile'],
            business_rules=data['business_rules'],
            engine_config=data['engine_config'],
            memory_seeds=data['memory_seeds']
        )

# 使用示例
config = ScenarioConfig.from_yaml('config/scenarios/customer_service.yaml')
engine = ContextEngine(
    app_name=config.name,
    user_id="user-001",
    llm_client=client,
    base_system_prompt=config.system_prompt,
    user_profile=config.user_profile,
    business_rules=config.business_rules,
    max_recent_events=config.engine_config['max_recent_events']
)
```

**优先级**: 🟡 中

---

### 6. 添加输入验证和安全检查

**问题**: 输入验证不够严格

**建议添加验证层**:

```python
# contextmind/validators.py
import re
from typing import Optional

class InputValidator:
    """输入验证器"""
    
    # 危险模式
    DANGEROUS_PATTERNS = [
        r"ignore\s+previous",
        r"ignore\s+all",
        r"system\s*:",
        r"assistant\s*:",
        r"<\|.*?\|>",  # 特殊标记
        r"\{.*?system.*?\}",  # JSON 注入
    ]
    
    MAX_INPUT_LENGTH = 2000
    MIN_INPUT_LENGTH = 1
    
    @classmethod
    def validate(cls, user_input: str) -> tuple[bool, Optional[str]]:
        """
        验证用户输入
        
        Returns:
            (is_valid, error_message)
        """
        # 长度检查
        if len(user_input) < cls.MIN_INPUT_LENGTH:
            return False, "输入不能为空"
        
        if len(user_input) > cls.MAX_INPUT_LENGTH:
            return False, f"输入过长（最大 {cls.MAX_INPUT_LENGTH} 字符）"
        
        # Prompt 注入检查
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, user_input, re.IGNORECASE):
                return False, "输入包含不允许的内容"
        
        # 字符检查
        if not cls._is_valid_encoding(user_input):
            return False, "输入包含无效字符"
        
        return True, None
    
    @staticmethod
    def _is_valid_encoding(text: str) -> bool:
        """检查字符编码"""
        try:
            text.encode('utf-8')
            return True
        except UnicodeEncodeError:
            return False
    
    @classmethod
    def sanitize(cls, user_input: str) -> str:
        """清理用户输入"""
        # 移除首尾空白
        text = user_input.strip()
        
        # 移除控制字符
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')
        
        # 规范化空白
        text = re.sub(r'\s+', ' ', text)
        
        return text

# 在 engine.py 中使用
from .validators import InputValidator

async def process_turn(self, user_input: str) -> ContextTurnResult:
    # 验证输入
    is_valid, error_msg = InputValidator.validate(user_input)
    if not is_valid:
        raise ValueError(f"无效输入: {error_msg}")
    
    # 清理输入
    user_input = InputValidator.sanitize(user_input)
    
    # ... 继续处理
```

**优先级**: 🟡 中

---

### 7. 优化记忆检索性能

**问题**: 线性搜索所有记忆，性能较差

**建议**: 使用向量数据库

**方案 1: 集成 ChromaDB**:
```python
# contextmind/memory/chroma_service.py
import chromadb
from chromadb.config import Settings
from typing import List
from google.adk.memory.base_memory_service import BaseMemoryService

class ChromaMemoryService(BaseMemoryService):
    """基于 ChromaDB 的记忆服务"""
    
    def __init__(self, collection_name: str = "contextmind"):
        self.client = chromadb.Client(Settings(
            chroma_db_impl="duckdb+parquet",
            persist_directory="./chroma_db"
        ))
        self.collection = self.client.get_or_create_collection(
            name=collection_name
        )
    
    async def add_memory(self, text: str, metadata: dict = None):
        """添加记忆"""
        self.collection.add(
            documents=[text],
            metadatas=[metadata or {}],
            ids=[str(uuid.uuid4())]
        )
    
    async def search(self, query: str, top_k: int = 5):
        """检索记忆"""
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k
        )
        return results['documents'][0]
```

**方案 2: 集成 FAISS**:
```python
# requirements.txt 添加
faiss-cpu==1.7.4
sentence-transformers==2.2.2
```

**优先级**: 🟡 中低

---

## 🟢 低优先级 (长期优化)

### 8. 添加 CI/CD 流程

**建议**: 使用 GitHub Actions

**.github/workflows/test.yml**:
```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.8, 3.9, '3.10', 3.11]
    
    steps:
    - uses: actions/checkout@v3
    
    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v4
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install -r requirements.txt
        pip install pytest pytest-asyncio pytest-cov
    
    - name: Run tests
      run: |
        pytest tests/ --cov=contextmind --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./coverage.xml
```

**优先级**: 🟢 低

---

### 9. 添加性能监控

**建议**: 添加性能指标收集

```python
# contextmind/metrics.py
import time
from functools import wraps
from contextlib import contextmanager

class PerformanceMetrics:
    """性能指标收集器"""
    
    def __init__(self):
        self.metrics = {
            'llm_calls': 0,
            'llm_total_time': 0.0,
            'memory_searches': 0,
            'memory_total_time': 0.0,
        }
    
    @contextmanager
    def measure(self, metric_name: str):
        """测量执行时间"""
        start = time.time()
        yield
        elapsed = time.time() - start
        
        self.metrics[f'{metric_name}_calls'] += 1
        self.metrics[f'{metric_name}_total_time'] += elapsed
    
    def get_stats(self):
        """获取统计信息"""
        stats = {}
        for key, value in self.metrics.items():
            if key.endswith('_calls') and value > 0:
                metric_name = key.replace('_calls', '')
                total_time = self.metrics.get(f'{metric_name}_total_time', 0)
                stats[metric_name] = {
                    'calls': value,
                    'total_time': total_time,
                    'avg_time': total_time / value
                }
        return stats

# 使用示例
metrics = PerformanceMetrics()

async def _generate_response_with_retry(self, prompt: str) -> str:
    with self.metrics.measure('llm'):
        # ... LLM 调用
        pass
```

**优先级**: 🟢 低

---

### 10. Docker 化部署

**建议**: 提供 Docker 镜像

**Dockerfile**:
```dockerfile
FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860

CMD ["python", "gradio_demo.py"]
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  contextmind:
    build: .
    ports:
      - "7860:7860"
    env_file:
      - .env
    volumes:
      - ./logs:/app/logs
      - ./data:/app/data
```

**优先级**: 🟢 低

---

## 📊 总结

### 立即行动 (本周内)
1. ✅ 修复记忆服务 API 错误
2. ✅ 锁定依赖版本
3. ✅ 完善 .gitignore

### 短期计划 (2周内)
4. ✅ 添加单元测试框架
5. ✅ 实现配置文件化
6. ✅ 添加输入验证

### 中期计划 (1个月内)
7. ✅ 优化记忆检索性能
8. ✅ 添加 CI/CD 流程

### 长期计划 (3个月内)
9. ✅ 添加性能监控
10. ✅ Docker 化部署
11. ✅ 完善 API 文档
12. ✅ 多语言支持

---

**文档版本**: v1.0  
**创建日期**: 2026-01-08  
**维护者**: ContextMind Team
