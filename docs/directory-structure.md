# 目录结构说明

本文档详细说明 ContextMind 项目的目录结构和各文件的用途。

## 总体结构

```
ContextMind/
├── contextmind/          # 主包（核心代码）
├── examples/             # 示例程序
├── tests/                # 测试代码
├── docs/                 # 文档
├── resources/            # 静态资源
├── logs/                 # 日志文件（运行时生成）
├── setup.py              # 安装配置
├── requirements.txt      # Python依赖
├── .env                  # 环境变量（需创建）
├── .gitignore           # Git忽略配置
├── README.md            # 项目说明
├── ARCHITECTURE.md      # 架构文档
└── CONTRIBUTING.md      # 贡献指南
```

---

## 主包结构 (contextmind/)

### 概览

```
contextmind/
├── __init__.py          # 包入口，导出主要接口
├── infra/               # 基础设施层
├── config/              # 配置层
├── ui/                  # UI层
├── modes/               # 对话处理模式
├── scenarios/           # 场景配置
└── apps/                # 应用实现
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

### 2. 配置层 (config/)

**用途**: 管理系统配置和场景注册

```
config/
├── __init__.py
├── registry.py          # 场景注册表
│   └── ScenarioRegistry    # 注册表类
│   └── scenario_registry   # 全局实例
│
├── scenarios.yaml       # 场景配置文件
│   └── 定义所有场景的元数据
│
└── prompts.py           # 系统提示词
    └── CHAT_SYSTEM_PROMPT
    └── CALLCENTER_SYSTEM_PROMPT
    └── INSURANCE_SYSTEM_PROMPT
```

**依赖**: infra

### 3. UI层 (ui/)

**用途**: 用户界面组件

```
ui/
├── __init__.py
└── components.py        # Gradio UI组件
    └── create_gradio_ui()
    └── create_mode_selector()
```

**依赖**: infra, config

### 4. 对话处理模式 (modes/)

**用途**: 三种核心对话处理算法

```
modes/
├── __init__.py
│
├── dst/                 # 对话状态追踪模式
│   ├── __init__.py
│   ├── dialogue_state_tracker.py    # 主追踪器
│   ├── prompt_manager.py            # 提示管理器
│   ├── response_parser.py           # 响应解析器
│   └── data_models.py               # 数据模型
│
├── fnctod/              # 函数调用模式
│   ├── __init__.py
│   ├── fnctod_tracker.py            # 主追踪器
│   ├── function_manager.py          # 函数管理器
│   ├── response_parser.py           # 响应解析器
│   ├── schemas.py                   # Schema定义
│   ├── data_models.py               # 数据模型
│   └── fnctod_prompts.yaml          # 提示词配置
│
└── evolve/              # 演化式上下文模式
    ├── __init__.py
    ├── engine.py                    # 主引擎
    │
    ├── core/                        # 核心组件
    │   ├── configs.py               # 配置
    │   ├── data_models.py           # 数据模型
    │   ├── framework_config.py      # 框架配置
    │   ├── models.py                # 模型定义
    │   ├── registry.py              # 组件注册
    │   ├── strategies.py            # 策略模式
    │   └── types.py                 # 类型定义
    │
    ├── memory/                      # 记忆系统
    │   ├── bank.py                  # 记忆库
    │   ├── extractor.py             # 知识提取器
    │   ├── retriever.py             # 记忆检索器
    │   ├── session.py               # 会话管理器
    │   ├── updater.py               # 记忆更新器
    │   └── memory_fitness.py        # 适应度评估
    │
    ├── evolution/                   # 进化学习
    │   ├── evolutionary_updater.py  # 进化更新器
    │   └── feedback_system.py       # 反馈系统
    │
    └── pipeline/                    # 五步流水线
        ├── compressor.py            # 上下文压缩
        ├── context_retriever.py     # 上下文检索
        ├── preprocessor.py          # 预处理器
        ├── reorderer.py             # 重排序器
        ├── response_handler.py      # 响应处理器
        └── summarizer.py            # 摘要器
```

**依赖**: infra, config

### 5. 场景配置 (scenarios/)

**用途**: 定义各种对话场景的配置

```
scenarios/
├── __init__.py
├── config.py                # 场景配置基类
│   └── ScenarioConfig      # 配置数据类
│
├── chat_scenario.py         # 闲聊场景
│   └── get_chat_scenario()
│
├── callcenter_scenario.py   # 客服场景
│   └── get_callcenter_scenario()
│
└── insurance_scenario.py    # 保险场景
    └── get_insurance_scenario()
```

**依赖**: config

### 6. 应用实现 (apps/)

**用途**: Evolve 模式的场景特定应用

```
apps/
├── __init__.py
├── chat_app.py              # 闲聊应用
│   └── ChatApplication
│
├── callcenter_app.py        # 客服应用
│   └── CallCenterApplication
│
├── insurance_app.py         # 保险应用
│   └── InsuranceApplication
│
└── plugin_examples.py       # 插件示例
    └── PluginExamples
```

**依赖**: modes/evolve, scenarios

---

## 示例程序 (examples/)

```
examples/
├── cli_demo.py          # 命令行交互示例
├── web_demo.py          # Web界面示例（Gradio）
└── batch_demo.py        # 批量测试示例
```

**用途**: 展示如何使用 ContextMind

**运行方式**:
```bash
python examples/cli_demo.py --scenario chat --mode dst
python examples/web_demo.py
```

---

## 测试代码 (tests/)

```
tests/
├── __init__.py
├── test_dst_mode.py     # DST模式测试
├── test_evolve_mode.py  # Evolve模式测试
└── fixtures/            # 测试数据（如果有）
```

**用途**: 单元测试和集成测试

**运行方式**:
```bash
python -m pytest tests/
```

---

## 文档 (docs/)

```
docs/
├── README.md                 # 文档索引
├── architecture.md           # 架构说明
├── api-reference.md          # API参考
├── quick-start.md            # 快速开始
├── modes.md                  # 模式对比
├── configuration.md          # 配置指南
├── extending-scenarios.md    # 扩展场景
├── naming-standards.md       # 命名规范
├── directory-structure.md    # 目录结构（本文档）
├── examples.md               # 示例代码
├── troubleshooting.md        # 故障排查
├── migration.md              # 迁移指南
└── changelog.md              # 更新日志
```

---

## 静态资源 (resources/)

```
resources/
└── data/                # 数据文件
    ├── FnCTOD.md       # FnCTOD技术文档
    ├── dialogue.md     # 对话示例
    └── script.md       # 脚本模板
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
2. config/                   # 依赖 infra
   ↓
3. ui/ + modes/              # 依赖 infra, config
   ↓
4. scenarios/                # 依赖 config
   ↓
5. apps/                     # 依赖 modes/evolve, scenarios
   ↓
6. examples/                 # 依赖所有层
```

**原则**: 
- 上层可以依赖下层
- 同层之间可以互相依赖
- 下层不能依赖上层

---

## 扩展指南

### 添加新场景

1. 在 `contextmind/scenarios/` 创建 `xxx_scenario.py`
2. 在 `contextmind/apps/` 创建 `xxx_app.py` （如果使用Evolve）
3. 在 `contextmind/config/scenarios.yaml` 注册
4. 编写测试

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

- [架构说明](architecture.md)
- [命名规范](naming-standards.md)
- [扩展场景](extending-scenarios.md)
- [API参考](api-reference.md)
