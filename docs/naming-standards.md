# 命名标准规范 (Naming Standards)

## 概述

本文档定义了 ContextMind 项目中所有三种模式（DST、FnCTOD、Evolve）的统一命名规范。

**版本**: v0.2.1  
**更新日期**: 2026-02-04

---

## 1. 模块命名规范

### 1.1 文件命名
所有 Python 文件使用 **snake_case** 命名：

```
✅ 正确:
  - dialogue_state_tracker.py
  - response_parser.py
  - data_models.py
  - fnctod_tracker.py

❌ 错误:
  - DialogueStateTracker.py
  - ResponseParser.py
  - dataModels.py
```

### 1.2 模块结构
每个模式遵循一致的模块结构：

```
<mode>/
  ├── __init__.py              # 模块导出和别名
  ├── data_models.py           # 数据模型
  ├── <purpose>_manager.py     # 管理器类
  ├── response_parser.py       # 响应解析器
  └── <mode>_tracker.py        # 主追踪器/引擎
```

**示例**:
```
dst/
  ├── __init__.py
  ├── data_models.py
  ├── prompt_manager.py
  ├── response_parser.py
  └── dialogue_state_tracker.py

fnctod/
  ├── __init__.py
  ├── data_models.py
  ├── function_manager.py
  ├── response_parser.py
  ├── fnctod_tracker.py
  └── schemas.py

evolve/
  ├── __init__.py
  ├── engine.py
  ├── core/
  ├── pipeline/
  └── memory/
```

---

## 2. 类命名规范

### 2.1 主追踪器/引擎类

统一模式：`<Mode>Tracker` 或 `<Mode>Engine`

| 模式 | 主类名 | 简短别名 | 说明 |
|------|--------|----------|------|
| DST | `DialogueStateTracker` | `DSTTracker` | 对话状态追踪器 |
| FnCTOD | `FnCTODTracker` | - | 函数调用追踪器 |
| Evolve | `EvolveEngine` | `EvolveTracker` | 进化引擎 |

**推荐用法**:
```python
# 推荐使用简短别名（新代码）
from dst import DSTTracker
from fnctod import FnCTODTracker  
from evolve import EvolveTracker

# 完整名称仍然可用（向后兼容）
from dst import DialogueStateTracker
from evolve import EvolveEngine
```

### 2.2 Manager 类

语义化命名：`<Purpose>Manager`

| 模式 | Manager类 | 用途 |
|------|-----------|------|
| DST | `PromptManager` | 管理提示词和槽位定义 |
| FnCTOD | `FunctionManager` | 管理函数定义和调用 |
| Evolve | `SessionManager` | 管理会话和上下文 |

### 2.3 Parser 类

统一命名：`ResponseParser`

| 模式 | 实际类名 | 别名 | 说明 |
|------|----------|------|------|
| DST | `ResponseParser` | - | 解析槽位提取响应 |
| FnCTOD | `FnCTODResponseParser` | `ResponseParser` | 解析函数调用响应 |
| Evolve | `ResponseHandler` | `ResponseParser` | 处理响应生成 |

**推荐用法**:
```python
# 使用统一别名（推荐）
from dst import ResponseParser as DSTParser
from fnctod import ResponseParser as FnCTODParser
from evolve import ResponseParser as EvolveParser

# 或在各自模块内直接使用
from dst import ResponseParser  # DST的ResponseParser
from fnctod import ResponseParser  # FnCTOD的ResponseParser
```

### 2.4 数据模型类

使用 **PascalCase** 和语义化命名：

| 类名 | 用途 | 使用模式 |
|------|------|----------|
| `DialogueTurn` | 对话轮次 | DST, FnCTOD |
| `FunctionCall` | 函数调用 | FnCTOD |
| `FunctionParameter` | 函数参数 | FnCTOD |
| `DomainSpec` | 域规格 | FnCTOD |
| `Message` | 消息 | Evolve |
| `ContextItem` | 上下文项 | Evolve |
| `MemoryNote` | 记忆笔记 | Evolve |

---

## 3. 方法命名规范

### 3.1 核心方法

所有主类必须实现以下方法（统一签名）：

| 方法名 | 用途 | 参数 | 返回值 |
|--------|------|------|--------|
| `from_scenario()` | 工厂方法 | `(llm_client, scenario_config, ...)` | tracker实例 |
| `process_turn()` | 处理对话轮次 | `(user_input, ...)` | 响应/结果 |
| `reset()` | 重置状态 | `()` | None |

**示例**:
```python
# DST
tracker = DialogueStateTracker.from_scenario(llm_client, config)
state = await tracker.process_turn(user_input)
tracker.reset()

# FnCTOD
tracker = FnCTODTracker.from_scenario(llm_client, config)
result = await tracker.process_turn(user_input)
tracker.reset()

# Evolve
app = create_app_for_scenario("chat", llm_client, config)
response = await app.process_turn(user_input)
```

### 3.2 方法命名模式

- 使用 **snake_case**
- 动词开头，语义清晰
- 避免缩写（除非是行业标准）

```
✅ 正确:
  - process_turn()
  - get_state()
  - reset()
  - from_scenario()
  - add_slot()
  - parse_response()

❌ 错误:
  - processTurn()  (camelCase)
  - getst()        (缩写不清晰)
  - rst()          (过度缩写)
```

---

## 4. 变量命名规范

### 4.1 实例变量

使用 **snake_case**：

```python
# 正确
self.current_state = {}
self.dialogue_history = []
self.llm_client = llm_client
self.function_manager = FunctionManager()

# 错误
self.currentState = {}
self.DialogueHistory = []
```

### 4.2 常量

使用 **UPPER_SNAKE_CASE**：

```python
# 正确
MAX_HISTORY_TURNS = 10
DEFAULT_TEMPERATURE = 0.7
SCHEMA_GETTERS = {...}

# 错误
maxHistoryTurns = 10
default_temperature = 0.7
```

### 4.3 私有变量/方法

使用单下划线前缀：

```python
class Tracker:
    def __init__(self):
        self._internal_state = {}  # 私有变量
    
    def _helper_method(self):      # 私有方法
        pass
```

---

## 5. 导入和导出规范

### 5.1 模块导出（__init__.py）

每个模块必须：
1. 导出主要类
2. 提供简短别名
3. 明确 `__all__` 列表

```python
# dst/__init__.py
from dst.dialogue_state_tracker import DialogueStateTracker
from dst.response_parser import ResponseParser

# 别名 - 统一命名风格
DSTTracker = DialogueStateTracker

__all__ = [
    'DialogueStateTracker',
    'DSTTracker',  # 推荐使用的简短别名
    'ResponseParser',
    # ...
]
```

### 5.2 导入顺序

遵循 PEP8 标准：

```python
# 1. 标准库
import os
import sys
from typing import Dict, List

# 2. 第三方库
import numpy as np

# 3. 本地模块
from dst import DialogueStateTracker
from utils import get_logger
```

---

## 6. 命名对照表

### 6.1 三种模式命名对照

| 概念 | DST | FnCTOD | Evolve |
|------|-----|--------|--------|
| 主类 | `DialogueStateTracker` | `FnCTODTracker` | `EvolveEngine` |
| 简称 | `DSTTracker` | - | `EvolveTracker` |
| Manager | `PromptManager` | `FunctionManager` | `SessionManager` |
| Parser | `ResponseParser` | `FnCTODResponseParser` → `ResponseParser` | `ResponseHandler` → `ResponseParser` |
| 数据 | `DialogueTurn` | `DialogueTurn`, `FunctionCall` | `Message`, `ContextItem` |
| 重置 | `reset()` / `reset_dialogue()` | `reset()` | - |
| 处理 | `process_turn()` | `process_turn()` | `process_turn()` |
| 工厂 | `from_scenario()` | `from_scenario()` | `create_app_for_scenario()` |

### 6.2 推荐使用模式

```python
# 推荐的统一导入方式
from dst import DSTTracker, ResponseParser as DSTParser
from fnctod import FnCTODTracker, ResponseParser as FnCTODParser
from evolve import EvolveTracker, create_app_for_scenario

# 创建实例
dst_tracker = DSTTracker.from_scenario(llm, config)
fnctod_tracker = FnCTODTracker.from_scenario(llm, config)
evolve_app = create_app_for_scenario("chat", llm, config)

# 统一方法调用
await dst_tracker.process_turn(user_input)
await fnctod_tracker.process_turn(user_input)
await evolve_app.process_turn(user_input)

# 统一重置
dst_tracker.reset()
fnctod_tracker.reset()
# evolve_app 无需reset（由SessionManager管理）
```

---

## 7. 版本兼容性

### 7.1 向后兼容

所有别名都是**附加的**，不破坏现有代码：

```python
# 旧代码仍然工作
from dst import DialogueStateTracker
tracker = DialogueStateTracker(...)
tracker.reset_dialogue()  # 仍然可用

# 新代码推荐使用
from dst import DSTTracker
tracker = DSTTracker.from_scenario(...)
tracker.reset()  # 统一接口
```

### 7.2 弃用策略

- 不删除旧名称
- 添加别名以提供新接口
- 在文档中推荐新名称
- 可在未来版本中添加弃用警告

---

## 8. 文档规范

### 8.1 类文档字符串

```python
class DSTTracker:
    """
    对话状态追踪器（DST模式）
    
    基于 ACL 2023 论文的零样本对话状态追踪实现。
    
    主要功能：
    - 从用户输入中提取槽位-值对
    - 维护累积对话状态
    - 支持多轮对话历史管理
    
    使用示例：
        >>> tracker = DSTTracker.from_scenario(llm_client, config)
        >>> state = await tracker.process_turn("我要订酒店")
        >>> print(state)
    
    参数：
        llm_client: LLM客户端实例
        prompt_manager: 提示词管理器
        ...
    """
```

### 8.2 方法文档字符串

```python
def process_turn(self, user_input: str) -> Dict[str, Any]:
    """
    处理一轮对话，提取状态更新
    
    Args:
        user_input: 用户输入文本
        
    Returns:
        包含提取的状态信息的字典
        
    Raises:
        ValueError: 如果输入为空
        
    Example:
        >>> result = await tracker.process_turn("我要订北京的酒店")
        >>> print(result['destination'])  # "北京"
    """
```

---

## 9. 总结

### 9.1 核心原则

1. **一致性**: 三种模式使用相同的命名模式
2. **可读性**: 名称清晰表达意图
3. **可扩展性**: 为未来新模式预留空间
4. **兼容性**: 不破坏现有代码

### 9.2 快速参考

```python
# 统一的导入方式
from dst import DSTTracker
from fnctod import FnCTODTracker  
from evolve import EvolveTracker, create_app_for_scenario

# 统一的创建方式
tracker = <Mode>Tracker.from_scenario(llm_client, config)

# 统一的方法调用
result = await tracker.process_turn(user_input)
tracker.reset()

# 统一的Parser别名
from <mode> import ResponseParser
```

### 9.3 检查清单

在添加新模式或修改现有代码时，检查：

- [ ] 文件名使用 snake_case
- [ ] 类名使用 PascalCase
- [ ] 方法名使用 snake_case
- [ ] 提供 `from_scenario()` 工厂方法
- [ ] 实现 `process_turn()` 方法
- [ ] 实现 `reset()` 方法
- [ ] 在 `__init__.py` 导出主要类
- [ ] 提供简短别名
- [ ] 添加完整文档字符串
- [ ] 更新本文档

---

**维护者**: ContextMind Team  
**最后更新**: 2026-02-04  
**版本**: 1.0
