# ContextMind 重构文档

> 版本：v0.3.0  
> 状态：进行中

---

## 一、重构目标

1. **算法模式统一**：4 种模式（DST / FnCTOD / PyTOD / Evolve）使用统一的命名规范、初始化接口、执行接口和后处理步骤。
2. **场景架构清晰**：消除 `scenarios/` 目录中的冗余文件，统一场景描述结构。
3. **UI 代码分层**：分离 CSS 样式、布局构建和事件绑定，提高可维护性。
4. **Infra 层清理**：去掉与 Evolve 模式强绑定的命名，统一使用 ContextMind 品牌。

---

## 二、已识别问题清单

### 2.1 infra/

| 文件 | 问题 | 方案 |
|------|------|------|
| `logger.py` | `EvolveLogger` 类名绑定到 Evolve 模式，作为全局基础设施却带模式名 | 重命名为 `Logger`；保留 `EvolveLogger` 作为向后兼容别名 |
| `logger.py` | 日志文件命名为 `evolve_*.log` | 改为 `contextmind_*.log` |
| `llm_client.py` | 文档注释提到"Google ADK"而非通用描述 | 更新注释，使描述更通用 |

### 2.2 modes/ 算法模式

#### 统一接口问题

所有模式主类应遵循 `BaseTracker` 协议：

```python
@classmethod
def from_scenario(cls, llm_client, scenario_config, **kwargs) -> "BaseTracker": ...

async def process_turn(self, user_utterance: str, **kwargs) -> Dict[str, Any]: ...

def get_current_state(self) -> Dict[str, Any]: ...

def reset(self) -> None: ...
```

#### 各模式具体问题

| 模式 | 主类名 | 问题 | 方案 |
|------|--------|------|------|
| DST | `DialogueStateTracker` | `process_turn(system_utterance, user_utterance)` 参数顺序不标准（user 应在前） | 改为 `process_turn(user_utterance, system_utterance="", **kwargs)` |
| FnCTOD | `FnCTODAgent` | 命名用 "Agent" 而非 "Tracker"；`from_scenario` 不接受 `llm_client` 参数 | 重命名为 `FnCTODTracker`，标准化 `from_scenario(cls, llm_client, scenario_config, **kwargs)` |
| PyTOD | `PyTODAgent` | 命名用 "Agent" 而非 "Tracker"；`from_scenario` 不接受 `llm_client` 参数；`_build_instruction()` 是模块级函数 | 重命名为 `PyTODTracker`，标准化 `from_scenario`，将 `_build_instruction` 移入类 |
| Evolve | `EvolveApplication` | 缺少 `from_scenario()` 工厂方法；缺少 `get_current_state()` 方法；缺少 `reset()` 方法 | 添加三个方法使其满足 `BaseTracker` 协议 |

### 2.3 scenarios/

| 问题 | 方案 |
|------|------|
| `chat/app.py`、`callcenter/app.py`、`insurance/app.py` 各只有 1-2 行，仅做 re-export | 删除这三个冗余文件，在各场景 `__init__.py` 中直接导出 |
| `EvolveApplication` 放在 `scenarios/app.py`，但它属于 Evolve 模式逻辑 | 保留在 `scenarios/app.py`（向后兼容），但在 `modes/evolve/__init__.py` 中重新导出 |
| 各 scenario 的 `__init__.py` 导出内容不一致 | 统一每个场景只导出其 `get_xxx_scenario()` 函数和场景相关常量 |

### 2.4 ui/

| 问题 | 方案 |
|------|------|
| `components.py` 中 CSS、布局、事件绑定全部混在 `create_gradio_ui()` 一个函数中 | 将 CSS 提取到 `ui/styles.py`；将布局构建和事件绑定分为独立函数 |
| 版本号 `v0.2.1` 硬编码在 UI 字符串中 | 从包版本读取，或定义常量 |

---

## 三、重构实施细节

### 3.1 infra/logger.py

**变更**：

```python
# 旧
class EvolveLogger: ...

# 新
class Logger: ...
EvolveLogger = Logger  # 向后兼容别名

# 旧
log_filename = f"evolve_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# 新
log_filename = f"contextmind_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
```

### 3.2 modes/dst/tracker.py

**变更**：修正 `process_turn` 签名（user_utterance 在前），添加 `DSTTracker` 别名。

```python
# 旧
async def process_turn(self, system_utterance: str, user_utterance: str) -> Dict[str, str]:

# 新
async def process_turn(self, user_utterance: str, system_utterance: str = "", **kwargs) -> Dict[str, str]:

# 新增别名
DSTTracker = DialogueStateTracker
```

### 3.3 modes/fnctod/tracker.py

**变更**：

```python
# 旧
class FnCTODAgent:
    @classmethod
    def from_scenario(cls, scenario_config, **kwargs):

# 新
class FnCTODTracker:
    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        # llm_client 参数从 kwargs 提取或传入 config
        ...

FnCTODAgent = FnCTODTracker  # 向后兼容别名
```

### 3.4 modes/pytod/tracker.py

**变更**：

```python
# 旧（模块级函数）
def _build_instruction(scenario_context: str) -> str: ...

class PyTODAgent:
    @classmethod
    def from_scenario(cls, scenario_config, config=None, **kwargs):

# 新
class PyTODTracker:
    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs):
        ...

    @staticmethod
    def _build_instruction(scenario_context: str) -> str: ...

PyTODAgent = PyTODTracker  # 向后兼容别名
```

### 3.5 scenarios/app.py（EvolveApplication）

**变更**：添加三个方法使其满足 `BaseTracker` 协议。

```python
class EvolveApplication:
    # 已有
    async def process_turn(self, user_input, debug=False): ...

    # 新增
    @classmethod
    def from_scenario(cls, llm_client, scenario_config, **kwargs) -> "EvolveApplication":
        return cls.create_from_config(llm_client, scenario_config)

    def get_current_state(self) -> Dict[str, Any]:
        """返回 EvolveEngine 的 memory bank 缓存（近期记忆摘要）。"""
        ...

    def reset(self) -> None:
        """重置会话，创建新的 EvolveEngine session。"""
        ...
```

### 3.6 scenarios/ 目录清理

删除冗余文件：
- `scenarios/chat/app.py`（内容：1 行 re-export）
- `scenarios/callcenter/app.py`（内容：1 行 re-export）
- `scenarios/insurance/app.py`（内容：1 行 re-export）

更新各场景 `__init__.py`，直接从 `scenario.py` 导出配置函数。

### 3.7 ui/ 目录重构

新增 `ui/styles.py`，内容为提取自 `components.py` 的 CSS 常量。  
将 `create_gradio_ui()` 重构为：

```python
# ui/styles.py
CUSTOM_CSS = """..."""

# ui/components.py
def create_layout() -> tuple[gr.Blocks, dict]:
    """纯布局构建，不含事件绑定。"""
    ...

def bind_events(app: gr.Blocks, components: dict, demo_instance) -> None:
    """将事件处理器绑定到已创建的组件。"""
    ...

def create_gradio_ui(demo_instance=None) -> tuple[gr.Blocks, dict]:
    """向后兼容入口，组合 create_layout + bind_events。"""
    app, components = create_layout()
    if demo_instance:
        bind_events(app, components, demo_instance)
    return app, components
```

---

## 四、向后兼容策略

所有重命名均保留旧名称作为别名：

```python
# modes/fnctod/__init__.py 新增
FnCTODAgent = FnCTODTracker

# modes/pytod/__init__.py 新增
PyTODAgent = PyTODTracker

# modes/dst/__init__.py 新增
DSTTracker = DialogueStateTracker

# infra/logger.py 新增
EvolveLogger = Logger
```

---

## 五、实施顺序

1. `infra/logger.py` — 影响最小，改动最少
2. `modes/dst/tracker.py` — 标准化签名
3. `modes/fnctod/tracker.py` — 重命名 + 标准化
4. `modes/pytod/tracker.py` — 重命名 + 重组
5. `scenarios/app.py` — 添加协议方法
6. `scenarios/` — 删除冗余文件
7. `ui/` — 分离样式和布局
