# 目录结构说明

本文档详细说明 ContextMind 项目的目录结构和各文件的用途。

## 总体结构

```
ContextMind/
├── contextmind/          # 主包（核心代码）
├── examples/             # 示例程序
├── benchmark/            # 评测框架
├── docs/                 # 文档
├── resources/            # 静态资源
├── logs/                 # 日志文件（运行时生成）
├── setup.py              # 安装配置
├── requirements.txt      # Python依赖
├── .env                  # 环境变量（需创建）
├── .gitignore           # Git忽略配置
└── README.md            # 项目说明
```

---

## 主包结构 (contextmind/)

### 概览

```
contextmind/
├── __init__.py          # 包入口，导出主要接口
├── infra/               # 基础设施层
├── ui/                  # UI层
├── modes/               # 对话处理模式
└── scenarios/           # 场景配置与应用（含注册表和YAML配置）
```

### 1. 基础设施层 (infra/)

**用途**: 提供底层工具和服务

```
infra/
├── __init__.py
├── logger.py            # 日志工具
│   └── setup_logger()  # 配置日志
│   └── get_logger()    # 获取日志器
│
├── llm_client.py        # LLM客户端封装
│   └── SimpleLLMClient # 简单客户端实现
│
├── embedding.py         # 向量嵌入工具
│   └── calculate_embedding_similarity()
│
└── data_models.py       # 通用数据模型
    └── EmbeddingInfo   # 嵌入信息
```

**依赖**: 无其他内部依赖

### 2. UI层 (ui/)

**用途**: 用户界面组件

```
ui/
├── __init__.py
└── components.py        # Gradio UI组件
    └── create_gradio_ui()
    └── create_mode_selector()
```

**依赖**: infra

### 3. 对话处理模式 (modes/)

**用途**: 四种核心对话处理算法

```
modes/
├── __init__.py
├── base.py                  # BaseTracker 协议（所有追踪器的共享接口）
│
├── dst/                 # 对话状态追踪模式（3文件）
│   ├── __init__.py
│   ├── tracker.py                   # 主追踪器 + DialogueTurn/SpecialValue 数据模型
│   ├── prompts.py                   # 提示管理器
│   └── parser.py                    # DST响应解析器（DSTResponseParser）
│
├── fnctod/              # 函数调用模式（4文件）
│   ├── __init__.py
│   ├── tracker.py                   # 主追踪器
│   ├── function_manager.py          # 函数管理器 + 数据模型（FunctionCall、DomainSpec等）
│   ├── parser.py                    # FnCTOD响应解析器（FnCTODResponseParser）
│   ├── schemas.py                   # Schema定义（YAML驱动加载器）
│   └── schemas.yaml                 # 场景 schema 参数配置（YAML）
│
├── evolve/              # 演化式上下文模式
│   ├── __init__.py
│   ├── engine.py                    # 主引擎
│   ├── factory.py                   # create_app_for_scenario 工厂函数
│   │
│   ├── core/                        # 核心组件（4文件）
│   │   ├── config.py                # 类型定义（KnowledgeType等）+ 配置数据类（合并）
│   │   ├── data_models.py           # 数据模型（Message、ContextItem等）
│   │   ├── strategies.py            # 抽象策略基类
│   │   └── registry.py              # 插件注册表
│   │
│   ├── memory/                      # 记忆系统（6文件）
│   │   ├── bank.py                  # 记忆库
│   │   ├── extractor.py             # 知识提取器
│   │   ├── retriever.py             # 记忆检索器
│   │   ├── session.py               # 会话管理器
│   │   ├── updater.py               # 记忆更新器
│   │   └── fitness.py               # 适应度评估
│   │
│   ├── evolution/                   # 进化学习（2文件）
│   │   ├── updater.py               # 进化更新器
│   │   └── feedback.py              # 反馈系统
│   │
│   └── pipeline/                    # 上下文处理流水线（3文件）
│       ├── steps.py                 # InputPreprocessor + ContextRetriever + ContextCompressor + ContextReorderer（合并）
│       ├── summarizer.py            # LLMBasedSummarizer
│       └── response_handler.py      # 响应处理器
│
└── pytod/               # 可编程任务型对话模式（6文件）
    ├── __init__.py
    ├── tracker.py                   # 主追踪器（三步流程协调）
    ├── prompts.py                   # 动作解析器和对话管理器 prompt 构建
    ├── execution_engine.py          # 安全解析并执行程序语句
    ├── schemas.py                   # ServiceSchema / IntentDefinition / SlotDefinition
    ├── validator.py                 # 动作合法性校验
    └── registry.py                  # API注册表
```

**依赖**: infra

### 4. 场景配置与应用 (scenarios/)

**用途**: 定义各种对话场景的配置及对应的应用实现，并集中管理场景注册表和配置文件

```
scenarios/
├── __init__.py
├── base.py                  # 场景配置基类
│   └── ScenarioConfig      # 配置数据类
│   └── ScenarioType        # 场景类型枚举
│
├── prompts.py               # 所有场景系统提示词
│   └── CHAT_SYSTEM_PROMPT
│   └── CALLCENTER_SYSTEM_PROMPT
│   └── INSURANCE_SYSTEM_PROMPT
│
├── registry.py              # 场景注册表
│   └── ScenarioRegistry    # 注册表类
│   └── scenario_registry   # 全局实例
│
├── scenarios.yaml           # 场景配置文件（定义所有场景的元数据）
│
├── chat/                    # 闲聊场景包
│   ├── scenario.py          # get_chat_scenario()
│   └── app.py               # ChatApplication
│
├── callcenter/              # 客服场景包
│   ├── scenario.py          # get_callcenter_scenario()
│   └── app.py               # CallCenterApplication
│
├── insurance/               # 保险场景包
│   ├── scenario.py          # get_insurance_scenario()
│   └── app.py               # InsuranceApplication
│
```

**依赖**: infra, modes/evolve

---

## 示例程序 (examples/)

```
examples/
├── cli_demo.py                # 命令行交互示例
├── web_demo.py                # Web界面示例（Gradio）
├── batch_demo.py              # 批量测试示例
├── pytod_trace_demo.py        # PyTOD 追踪演示
└── anyihua_schema_induction_demo.py  # 安逸花 Schema 归纳演示
```

**用途**: 展示如何使用 ContextMind

**运行方式**:
```bash
python examples/cli_demo.py --scenario chat --mode dst
python examples/web_demo.py
```

---

## 文档 (docs/)

```
docs/
├── README.md                      # 文档索引
├── quick-start.md                 # 快速开始
├── examples.md                    # 示例代码
├── directory-structure.md         # 目录结构（本文档）
├── modes.md                       # 三种对话模式对比
├── configuration.md               # 配置指南
├── api-reference.md               # API参考
├── metrics-explanation.md         # 评测指标说明
├── extending-scenarios.md         # 扩展场景
├── troubleshooting.md             # 故障排查
├── changelog.md                   # 更新日志
├── CONTRIBUTING.md                # 贡献指南
├── algorithms/                    # 算法文档
│   ├── dst.md
│   ├── fnctod.md
│   ├── pytod.md
│   ├── intent-evaluation.md
│   └── context-engineering.md
└── datasets/                      # 数据集文档
    ├── sgd.md
    ├── transfertod.md
    ├── risawoz.md
    └── dialogue-count.md
```

---

## 静态资源 (resources/)

```
resources/
├── data/                # 数据文件
│   └── risawoz_test.json    # RiSAWOZ 测试数据
└── fonts/               # 字体文件
```

---

## 配置文件

### setup.py

```python
"""
包安装配置
- 定义包元数据
- 配置依赖关系
- 配置控制台脚本
"""
```

### requirements.txt

```
Python依赖列表:
- openai>=1.0.0
- PyYAML>=6.0.0
- gradio>=3.0.0
- python-dotenv>=1.0.0
等
```

### .env (需创建)

```bash
# LLM配置
QWEN3_API_KEY=your_key
QWEN3_BASE_URL=your_url
QWEN3_MODEL=qwen-plus

# 其他配置
DEBUG=False
```

---

## 文件命名规范

### Python文件

- **模块**: `snake_case.py` (如 `dialogue_state_tracker.py`)
- **类**: `PascalCase` (如 `DialogueStateTracker`)
- **函数**: `snake_case` (如 `process_turn`)
- **常量**: `UPPER_SNAKE_CASE` (如 `MAX_TURNS`)

### 配置文件

- YAML: `lowercase.yaml` (如 `scenarios.yaml`)
- Markdown: `kebab-case.md` (如 `quick-start.md`)

---

## 依赖关系图

```
层级结构（从底层到高层）:

1. infra/                    # 无依赖
   ↓
2. ui/ + modes/              # 依赖 infra
   ↓
3. scenarios/                # 依赖 infra, modes/evolve
   ↓
4. examples/                 # 依赖所有层
```

**原则**: 
- 上层可以依赖下层
- 同层之间可以互相依赖
- 下层不能依赖上层

---

## 扩展指南

### 添加新场景

1. 在 `contextmind/scenarios/` 创建 `xxx/` 子包，包含 `scenario.py` 和 `app.py`
2. 在 `contextmind/scenarios/scenarios.yaml` 注册
3. 编写测试

### 添加新模式

1. 在 `contextmind/modes/` 创建新目录
2. 实现核心类和辅助组件
3. 在 `contextmind/__init__.py` 导出接口
4. 编写文档和测试

### 添加新基础组件

1. 在 `contextmind/infra/` 创建新文件
2. 实现功能
3. 在 `contextmind/infra/__init__.py` 导出
4. 编写测试

---

## 相关文档

- [模式对比](modes.md)
- [扩展场景](extending-scenarios.md)
- [API参考](api-reference.md)
