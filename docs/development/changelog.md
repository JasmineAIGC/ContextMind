# 更新日志

所有显著变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.3.0] - 2026-03-30

### 新增
- **ContextPipeline**: 统一上下文工程流水线（`contextmind.pipeline`），将第一步知识库构建与第三步上下文提取整合为一个简洁 API，3 行代码完成端到端上下文工程
- **KnowledgeBaseBuilder**: 通用知识库构建器（`contextmind.knowledge`），支持 5 种对话输入格式，自动完成发现→合成→转换三阶段处理
- **AdkPyTODTracker**: 完整实现的 PyTOD 追踪器，支持 AP→EE→DM 三步流程；含 `from_scenario()` 混合注册（预定义 API + schema 存根）和模糊函数名匹配（`difflib`，cutoff=0.6）
- **第一步→第三步桥接方法**: `KnowledgeBaseBuilder.to_service_schema()` / `load_schema()` 直接将第一步输出连接到第三步追踪器
- **vLLM Qwen3 支持**: `AdkLLMClient` 自动识别思维模型并通过 `chat_template_kwargs.enable_thinking=False` 关闭思维模式，避免 3–10× 延迟
- **context_pipeline_demo.py**: 端到端 ContextPipeline 演示脚本
- **build_kb_demo.py**: 通用知识库构建演示，支持多文件合并、多种输入格式

### 变更
- **包名调整**: 知识库构建模块由 `contextmind.kb` 正式更名为 `contextmind.knowledge`
- **追踪器类名**: PyTOD 追踪器由 `PyTODTracker` 重命名为 `AdkPyTODTracker`，LLM 客户端由 `SimpleLLMClient` 重命名为 `AdkLLMClient`
- **`__init__.py`**: 更新主包导出列表，新增 `ContextPipeline`、`KnowledgeBaseBuilder`、`ServiceSchema`、`load_schema_from_dict`
- **文档全面更新**: 所有 docs/ 文档更新为 v0.3.0 API（修正类名、导入路径、代码示例）

### 修复
- 修复 `SayStatement` 处理中已绑定变量被覆盖的问题（`execution_engine.py`）
- 修复 `_sanitize_infer_yaml`（`discoverer.py`）对 LLM 返回的三种输出格式（YAML/bare list/已包装 JSON）的解析
- 修复 `_register_apis_from_schema` 存根签名仅包含 required+optional slots，避免 AP 函数签名过长

### 安全
- 通过 CodeQL 安全扫描，0 个安全问题

---

## [未发布]

### 新增
- **三步框架文档**: 全面更新所有 docs/ 文档，将框架从「两步」升级为「三步」：
  ① 任意数据集→知识库（`contextmind.knowledge`）、
  ② 知识库→算法专用 Schema 数据生成（`contextmind.schema_builder`）、
  ③ 算法执行（`contextmind.modes.*`）
- **算法步骤依赖矩阵**: 在 `README.md`、`docs/README.md`、`docs/benchmark.md` 中新增各算法对三步框架依赖情况的对比表格
- **SchemaDataBuilder 配置文档**: `docs/configuration.md` 新增第二步 `SchemaDataBuilder` 的参数说明
- **SlotBasedEvaluator**: 新增 `SlotBasedEvaluator` 基类和 `SlotMetrics` 数据类（`benchmark/algorithms/base.py`），
  消除 `DSTEvaluator` 与 `FnCTODEvaluator` 之间完全重复的槽位指标计算逻辑（~260 行）

### 变更
- **DSTEvaluator / FnCTODEvaluator**: 重构为继承 `SlotBasedEvaluator`，保持向后兼容接口
- **docs/README.md**: 修正仓库 URL（Jasmine66Bloom → JasmineAIGC）；更新算法表格，添加「所需步骤」列；新增三步框架概述与依赖矩阵
- **docs/quick-start.md**: 添加三步框架概述表格；更新「更多示例」章节，新增完整三步流程示例
- **docs/algorithms/pytod.md**: 新增三步框架依赖说明；扩展「快速使用」章节，提供完整三步示例
- **docs/algorithms/dst.md** / **fnctod.md** / **evolve.md**: 各自添加三步框架依赖说明（DST/FnCTOD 不需要第二步，Evolve 不需要前两步）
- **contextmind/schema_builder/plan.md**: 明确标注为「第二步」，补充与第一步和第三步的衔接说明

### 修复
- 移除 `infra/llm_client.py` `_estimate_tokens()` 内重复的 `import re`（顶层已有）
- 将 `evolution/updater.py`、`memory/retriever.py`、`scenarios/chat/app.py`、
  `modes/fnctod/tracker.py` 中的内联 `import` 移到模块顶层

### 安全
- 通过 CodeQL 安全扫描，0 个安全问题

---

## [0.2.1] - 2026-02-10

### 新增
- **FnCTOD 模式**: 新增基于函数调用的对话状态跟踪模式
- **TransferTOD 集成**: 支持从 TransferTOD 数据集提取 30 个域的预定义函数
- **Schema 管理**: 为三个场景（闲聊、客服、保险）提供预定义 Schema
- **评测工具**: 新增 extract_transfertod_schemas.py 工具
- **使用文档**: 新增 HOW_TO_USE_SCHEMAS.md 指南

### 变更
- **场景扩展方式**: 从代码注册改为配置文件驱动（scenarios.yaml）
- **文档结构**: 重组文档目录，添加多个子目录
- **配置灵活性**: 支持从 JSON 文件加载预定义 Schema

### 修复
- 修复 IntentEvaluator 调用错误（ground_truth_intent 参数）
- 修复槽位值类型不一致导致的评测问题
- 修复 DialogueTurn 中 belief_state 属性名错误
- 修复字典类型槽位值无法加入集合的问题
- 修复域前缀不匹配导致的槽位查找失败
- 修复 Matplotlib 调试日志过多的问题

### 安全
- 通过 CodeQL 安全扫描，0 个安全问题

---

## [0.2.0] - 2026-02-05

### 新增
- **DST 模式**: 对话状态跟踪模式
- **Evolve 模式**: 基于记忆进化的智能对话系统
- **场景系统**: 支持闲聊、客服、保险三种预定义场景
- **历史管理**: 支持历史摘要（模板和 LLM 两种方式）
- **记忆系统**: 长期记忆存储和检索
- **进化学习**: 从对话中持续学习和优化

### 变更
- 项目架构重构为模块化设计
- 统一的场景配置系统
- 改进的日志系统

---

## [0.1.0] - 2026-01-15

### 新增
- 项目初始版本
- 基础对话管理功能
- LLM 客户端封装
- 简单的提示词管理

---

## 版本说明

### 版本号规则

采用语义化版本 `MAJOR.MINOR.PATCH`：
- **MAJOR**: 不兼容的 API 变更
- **MINOR**: 向下兼容的功能新增
- **PATCH**: 向下兼容的问题修复

### 变更类型

- **新增** (Added): 新功能
- **变更** (Changed): 现有功能的变更
- **废弃** (Deprecated): 即将移除的功能
- **移除** (Removed): 已移除的功能
- **修复** (Fixed): Bug 修复
- **安全** (Security): 安全相关的修复

---

**最后更新**: 2026-02-10
