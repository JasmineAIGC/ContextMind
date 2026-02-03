# ContextEngine → EvolutionEngine 重命名总结

## 概述

将 `ContextEngine` 重命名为 `EvolutionEngine`，并完成所有 `contextmind` 相关引用到 `evolution` 的彻底清理。

## 核心变更

### 1. 主要类重命名

| 旧名称 | 新名称 |
|--------|--------|
| `ContextEngine` | `EvolutionEngine` |
| `ContextMindLogger` | `EvolutionLogger` |
| `ContextMind` (framework) | `Evolution` |
| `ContextMindConfig` | `EvolutionConfig` |

### 2. 环境变量更新

| 旧名称 | 新名称 |
|--------|--------|
| `CONTEXTMIND_API_KEY` | `EVOLUTION_API_KEY` |
| `CONTEXTMIND_BASE_URL` | `EVOLUTION_BASE_URL` |
| `CONTEXTMIND_MODEL` | `EVOLUTION_MODEL` |
| `CONTEXTMIND_ACCESS_KEY` | `EVOLUTION_ACCESS_KEY` |

### 3. 文件变更

**核心模块**:
- `evolution/engine.py` - `EvolutionEngine` 类定义
- `evolution/__init__.py` - 导出 `EvolutionEngine`
- `evolution/core/framework_config.py` - `Evolution` 框架配置类

**工具模块**:
- `utils/logger.py` - `EvolutionLogger` 类定义
- `utils/__init__.py` - 导出 `EvolutionLogger`
- `utils/embedding.py` - 环境变量引用更新

**应用层**:
- `interactive_demo.py` - 使用 `EvolutionEngine`
- `gradio_demo.py` - 使用 `EvolutionEngine`
- `apps/chat_app.py` - 使用 `EvolutionEngine`
- `apps/callcenter_app.py` - 使用 `EvolutionEngine`
- `apps/insurance_app.py` - 使用 `EvolutionEngine`
- `apps/plugin_examples.py` - 使用 `EvolutionEngine`

**UI 组件**:
- `ui_components.py` - 界面文本和变量名更新

**内部模块**:
- `evolution/core/__init__.py` - 导入和导出更新
- `evolution/core/models.py` - Logger 引用更新
- `evolution/evolution/evolutionary_updater.py` - 导入更新
- `evolution/evolution/feedback_system.py` - 导入更新

**文档**:
- `README.md` - 使用示例更新
- `docs/ADK_FINAL_INTEGRATION.md` - 引用更新
- `docs/EVOLUTION_MODE_RENAME.md` - 引用更新
- `docs/architecture.md` - 架构文档更新
- `docs/migration.md` - 迁移指南更新
- `docs/modes.md` - 模式对比更新

## 使用示例

### 基本使用

```python
from evolution import EvolutionAgent, EvolutionEngine

# 创建 Agent
agent = EvolutionAgent()

# 创建 Engine
engine = EvolutionEngine(
    app_name="my_app",
    user_id="user_123",
    llm_client=agent
)

# 优化上下文
context_result = await engine.optimize("你好")

# 更新上下文
await engine.update(
    user_input="你好",
    assistant_response="你好，有什么可以帮助你的？"
)
```

### 日志使用

```python
from utils import EvolutionLogger, LogLevel

# 创建 Logger
logger = EvolutionLogger("MyModule", level=LogLevel.INFO)

# 记录日志
logger.info("这是信息日志")
logger.debug("这是调试日志")
```

### 框架配置

```python
from evolution.core import Evolution

# 使用框架配置
framework = Evolution()
result = await framework.process("用户输入")
```

## 验证

所有模块导入测试通过：

```python
✅ EvolutionAgent
✅ EvolutionEngine
✅ DSTAgent
✅ ChatApplication
✅ CallCenterApplication
✅ InsuranceApplication
✅ EvolutionLogger
✅ get_logger
```

## 命名约定

### Python 代码
- **类名**: `EvolutionEngine`, `EvolutionAgent`, `EvolutionLogger`
- **模块名**: `evolution`
- **变量名**: `evolution_settings`, `evolution_config`

### 环境变量
- **前缀**: `EVOLUTION_*`
- **示例**: `EVOLUTION_API_KEY`, `EVOLUTION_MODEL`

### UI 文本
- **中文**: "Evolution 模式", "进化模式"
- **英文**: "Evolution mode", "Evolution Framework"

## 迁移检查清单

如果你有自定义代码使用旧名称，请进行以下更新：

- [ ] 将 `ContextEngine` 改为 `EvolutionEngine`
- [ ] 将 `ContextMindLogger` 改为 `EvolutionLogger`
- [ ] 将 `from contextmind` 改为 `from evolution`
- [ ] 更新环境变量名 `CONTEXTMIND_*` → `EVOLUTION_*`
- [ ] 更新配置文件中的引用
- [ ] 更新文档和注释

## 向后兼容性

**注意**: 此版本 (v0.4.1) **不保留向后兼容性**。所有旧名称已被移除，必须使用新名称。

---

**版本**: v0.4.1  
**日期**: 2026-02-03  
**状态**: ✅ 重命名完成  
**影响**: 所有使用 ContextEngine 的代码都需要更新
