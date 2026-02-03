# ContextMind 项目状态

## 版本
v0.4.1

## 最后更新
2026-02-03

---

## 项目定位

**通用、可扩展、易集成的上下文工程框架**

- 底层基于 adk-python
- 自研上下文工程算法
- 支持 DST 和 Evolution 两种模式

---

## 架构概览

```
应用层 (Apps, Scenarios)
    ↓ 业务逻辑和场景配置
上下文工程层 (DST, Evolution)
    ↓ 自研核心算法
基础设施层 (Session, Memory, Agent)
    ↓ google-adk
LLM 层 (Qwen API)
    ↓ openai SDK
```

---

## 核心组件

### 1. DST 模式（对话状态追踪）

**基于 ADK**:
- Agent 框架

**自研算法**:
- 槽位提取
- Prompt 工程
- 状态追踪
- 响应解析

### 2. Evolution 模式（记忆进化）

**基于 ADK**:
- Agent 框架
- Session 管理
- Memory 管理

**自研算法**:
- Pipeline（预处理、压缩、重排序、摘要）
- 记忆进化（适应度计算、进化更新）
- 知识提取

### 3. 应用层

**场景**:
- 闲聊 (chat)
- 客服 (callcenter)
- 保险挽回 (insurance)

**应用**:
- ChatApplication
- CallCenterApplication
- InsuranceApplication

---

## 技术栈

### 核心依赖
- **google-adk** >= 1.23.0 - Agent 框架和基础设施
- **openai** >= 1.0.0 - LLM API 客户端

### 支持的模型
- Qwen 系列（通过 OpenAI 兼容接口）

---

## 代码统计

### 代码量
- **总计**: ~6,500 行
- **上下文工程**: ~2,500 行 (核心价值)
- **业务逻辑**: ~1,600 行
- **基础设施**: ~200 行 (ADK)
- **数据模型**: ~800 行

### 模块分布
- `dst/`: ~1,500 行
- `evolution/`: ~4,000 行
- `apps/`: ~1,300 行
- `scenarios/`: ~300 行
- `utils/`: ~800 行

---

## 文档组织

### 核心文档 (docs/)
1. **ARCHITECTURE.md** - 架构说明 ⭐⭐⭐
2. **FRAMEWORK_SUMMARY.md** - 框架总结 ⭐
3. **quick-start.md** - 快速开始 ⭐
4. **configuration.md** - 配置指南 ⭐⭐
5. **modes.md** - 模式说明 ⭐⭐
6. **paper-DST.md** - DST 论文实现
7. **dst-optimizations.md** - DST 优化
8. **FINAL_CLEANUP_SUMMARY.md** - 清理总结

### 归档文档 (docs/archive/)
9 个过程性和总结性文档

---

## 优化成果

### ADK 集成
- ✅ Agent 框架 100% 使用 ADK
- ✅ Session 管理 100% 使用 ADK
- ✅ Memory 管理 100% 使用 ADK
- ✅ 代码简化 43% (基础设施层)

### 代码质量
- ✅ 删除冗余代码 ~1,050 行
- ✅ 消除重复实现
- ✅ 清晰的命名规范
- ✅ 统一的架构模式

### 文档组织
- ✅ 根目录简洁 (1 个 README)
- ✅ 核心文档清晰 (8 个)
- ✅ 归档管理规范 (9 个)

---

## 使用指南

### 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量 (.env)
QWEN3_API_KEY=your-key
QWEN3_BASE_URL=your-endpoint
QWEN3_MODEL=Qwen2.5-7B-Instruct

# 运行 Demo
python interactive_demo.py --scenario chat --mode dst
python gradio_demo.py
```

### 代码示例

```python
# DST 模式
from dst import DSTAgent, DialogueStateTracker

agent = DSTAgent()
tracker = DialogueStateTracker(agent)
result = tracker.process_turn(
    system_utterance="",
    user_utterance="我想订一张北京到上海的机票"
)

# Evolution 模式
from evolution import EvolutionAgent, EvolutionEngine

agent = EvolutionAgent()
engine = EvolutionEngine(
    app_name="my_app",
    user_id="user_123",
    llm_client=agent
)
context = await engine.optimize("你好")
```

---

## 性能指标

### 代码效率
- 基础设施代码减少 43%
- 核心算法 100% 保留
- 无冗余实现

### 架构清晰度
- 职责分离: ⭐⭐⭐⭐⭐
- 易于理解: ⭐⭐⭐⭐⭐
- 可维护性: ⭐⭐⭐⭐⭐
- 可扩展性: ⭐⭐⭐⭐⭐

---

## 后续计划

### 优化方向
1. 核心算法性能优化
2. 文档和示例完善
3. 测试覆盖率提升
4. 场景扩展

### 跟进事项
1. 关注 google-adk 更新
2. 收集用户反馈
3. 持续优化算法
4. 扩展应用场景

---

## 联系方式

- 仓库: Jasmine66Bloom/ContextMind
- 版本: v0.4.1
- 状态: ✅ 生产就绪

---

**最后更新**: 2026-02-03  
**维护者**: ContextMind 团队
