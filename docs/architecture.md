# ContextMind 架构文档

## 项目结构

```
ContextMind/
├── contextmind/              # 主包（可通过pip安装）
│   ├── core/                 # 核心框架层
│   │   ├── config/           # 配置管理
│   │   │   ├── registry.py   # 场景注册表
│   │   │   └── scenarios.yaml # 场景配置
│   │   └── common/           # 通用组件
│   │       ├── prompts.py    # 系统提示词
│   │       ├── ui_components.py # UI组件
│   │       └── utils/        # 工具库
│   ├── modes/                # 对话处理模式
│   │   ├── dst/              # 对话状态追踪
│   │   ├── fnctod/           # 函数调用模式
│   │   └── evolve/           # 演化式上下文
│   └── scenarios/            # 场景定义
│       ├── config/           # 场景配置
│       └── apps/             # 应用实现
├── examples/                 # 示例程序
├── tests/                    # 测试
├── docs/                     # 文档
├── resources/                # 静态资源
└── setup.py                  # 安装配置
```

## 架构层次

### 1. Core Layer（核心层）
- **config**: 配置管理和场景注册
- **common**: 通用组件和工具库

### 2. Modes Layer（模式层）
- **dst**: 对话状态追踪模式
- **fnctod**: 函数调用模式
- **evolve**: 演化式上下文优化模式

### 3. Scenarios Layer（场景层）
- **config**: 场景配置定义
- **apps**: 场景应用实现

### 4. Examples Layer（示例层）
- **cli_demo**: 命令行示例
- **web_demo**: Web界面示例
- **batch_demo**: 批量测试示例

## 使用方式

### 作为包导入

```python
# 方式1: 从主包导入
from contextmind import (
    DialogueStateTracker,
    FnCTODTracker,
    EvolveEngine,
    scenario_registry,
)

# 方式2: 从子模块导入
from contextmind.modes.dst import DialogueStateTracker
from contextmind.core.config.registry import scenario_registry
from contextmind.scenarios.config import get_chat_scenario
```

### 安装使用

```bash
# 开发模式安装
pip install -e .

# 使用
import contextmind
tracker = contextmind.DialogueStateTracker.from_scenario(...)
```

## 设计原则

1. **模块化**: 每层职责清晰，可独立使用
2. **可扩展**: 易于添加新模式、新场景
3. **专业性**: 符合Python包开发标准
4. **清晰性**: 命名准确，结构清晰
