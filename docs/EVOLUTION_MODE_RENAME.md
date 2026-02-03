# Evolution 模式重命名总结

## 概述

将 `contextmind` 模式重命名为 `evolution` 模式，以更准确地反映其基于进化方法的特性。

## 完成的变更

### 1. 目录和模块重命名

**目录重命名**:
- `contextmind/` → `evolution/`

**模块更新**:
- `evolution/__init__.py` - 导出 EvolutionAgent, EvolutionConfig
- `evolution/agent.py` - Evolution 专用 ADK Agent
- `evolution/engine.py` - 保持 ContextEngine 类名不变
- `evolution/core/` - 所有核心模块
- `evolution/pipeline/` - 所有 Pipeline 算法
- `evolution/memory/` - 所有记忆管理模块
- `evolution/evolution/` - 进化系统模块

### 2. 代码更新

**主要文件**:
- `interactive_demo.py` - 使用 EvolutionAgent
- `gradio_demo.py` - 使用 EvolutionAgent  
- `apps/chat_app.py` - 导入 evolution 模块
- `apps/callcenter_app.py` - 导入 evolution 模块
- `apps/insurance_app.py` - 导入 evolution 模块
- `ui_components.py` - 更新引用
- `prompts.py` - 更新引用

**命名规则**:
- `contextmind` → `evolution`
- `ContextMind` → `Evolution`
- `ContextMindAgent` → `EvolutionAgent`
- `ContextMindConfig` → `EvolutionConfig`

### 3. 文档更新

**保留的文档** (12个):
- `ADK_FINAL_INTEGRATION.md` - ADK 集成总结
- `README.md` - 文档中心索引
- `architecture.md` - 架构说明
- `changelog.md` - 变更日志
- `configuration.md` - 配置指南
- `dst-implementation-analysis.md` - DST 实现分析
- `dst-multi-intent-analysis.md` - DST 多意图分析
- `dst-optimizations.md` - DST 优化文档
- `migration.md` - 迁移指南
- `modes.md` - 模式对比（已更新为 DST vs Evolution）
- `paper-DST.md` - DST 论文说明
- `quick-start.md` - 快速开始指南

**删除的文档** (4个):
- `ADK_OPTIMIZATION_COMPLETE.md` - 冗余
- `ADK_OPTIMIZATION_PLAN_V2.md` - 冗余
- `ADK_OPTIMIZATION_PROPOSAL.md` - 冗余
- `ADK_OPTIMIZATION_SUMMARY.md` - 冗余

### 4. LLM 配置

**配置来源**: 所有 LLM 配置从 `.env` 文件读取

**当前配置** (Qwen):
```ini
QWEN3_API_KEY=sk-xxx
QWEN3_BASE_URL=http://xxx/v1
QWEN3_MODEL=Qwen2.5-7B-Instruct
QWEN3_TOP_K=20
QWEN3_MAX_TOKENS=8192
```

**注意**: `.env` 文件内容未修改，保持原有 Qwen 配置。

## 两个独立模式

### DST 模式
- **目录**: `dst/`
- **Agent**: `DSTAgent`
- **特点**: 对话状态追踪，槽位提取
- **使用**: `python interactive_demo.py --mode dst`

### Evolution 模式
- **目录**: `evolution/`
- **Agent**: `EvolutionAgent`
- **特点**: 基于进化的上下文工程和记忆优化
- **使用**: `python interactive_demo.py --mode evolution`

## 使用示例

### 命令行

```bash
# Evolution 模式
python interactive_demo.py --scenario chat --mode evolution

# DST 模式
python interactive_demo.py --scenario chat --mode dst
```

### Python 代码

```python
from dst import DSTAgent, DialogueStateTracker
from evolution import EvolutionAgent, ContextEngine

# Evolution 模式
agent = EvolutionAgent()  # 从 .env 读取配置
engine = ContextEngine(
    app_name="my_app",
    user_id="user_123",
    llm_client=agent
)

# DST 模式
dst_agent = DSTAgent()  # 从 .env 读取配置
tracker = DialogueStateTracker(llm_client=dst_agent)
```

## 验证

所有导入测试通过:
- ✅ `from dst import DSTAgent`
- ✅ `from evolution import EvolutionAgent`
- ✅ `from evolution import ContextEngine`
- ✅ `from apps.chat_app import ChatApplication`
- ✅ `from apps.callcenter_app import CallCenterApplication`
- ✅ `from apps.insurance_app import InsuranceApplication`

---

**版本**: v0.4.1  
**日期**: 2026-02-03  
**状态**: ✅ 重命名完成
