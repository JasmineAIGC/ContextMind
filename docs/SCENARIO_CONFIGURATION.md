# ContextMind 场景配置系统

## 概述

ContextMind v0.4.0 引入了完全可配置的场景系统，支持多种对话任务的灵活切换。

## 支持的场景

### 1. 闲聊场景 (Chat)

**特点：**
- 动态槽位提取
- 开放式意图识别
- 轻松自然的对话风格

**使用：**
```python
from scenarios import get_chat_scenario
config = get_chat_scenario()
```

### 2. 客服场景 (CallCenter)

**特点：**
- 问题追踪
- 工单管理
- 专业服务导向

**使用：**
```python
from scenarios import get_callcenter_scenario
config = get_callcenter_scenario()
```

### 3. 保险挽回场景 (Insurance)

**特点：**
- 双层意图体系（7个一级 + 34个二级）
- 18个预定义槽位
- 销售导向的对话策略

**使用：**
```python
from scenarios import get_insurance_scenario
config = get_insurance_scenario()
```

## 场景配置结构

每个场景配置包含：

```python
class ScenarioConfig:
    scenario_name: str          # 场景名称
    scenario_type: ScenarioType # 场景类型枚举
    description: str            # 场景描述
    
    # DST配置
    dst_intents: Dict           # 预定义意图
    dst_slots: Dict             # 预定义槽位
    dst_categorical_slots: Dict # 分类槽位
    
    # 提示词
    system_prompt: str          # 系统提示词
    
    # ContextMind配置
    enable_memory: bool         # 启用记忆
    enable_evolution: bool      # 启用进化
    
    # UI配置
    ui_title: str              # 界面标题
    ui_description: str        # 界面描述
```

## 如何添加新场景

### 步骤1：创建配置文件

在 `scenarios/` 目录下创建新文件，例如 `education_scenario.py`：

```python
from scenarios.config import ScenarioConfig, ScenarioType
from prompts import EDUCATION_SYSTEM_PROMPT

def get_education_scenario() -> ScenarioConfig:
    return ScenarioConfig(
        scenario_name="教育辅导",
        scenario_type=ScenarioType.EDUCATION,
        description="在线教育辅导场景",
        
        # 定义意图和槽位
        dst_intents={
            "学习咨询": ["科目选择", "难点询问", "方法指导"],
            "作业辅导": ["题目讲解", "思路提示", "答案验证"],
        },
        
        dst_slots={
            "subject": "学科",
            "grade": "年级",
            "difficulty": "难度",
        },
        
        dst_categorical_slots={
            "grade": ["小学", "初中", "高中"],
            "subject": ["数学", "物理", "化学", "英语"],
        },
        
        system_prompt=EDUCATION_SYSTEM_PROMPT,
        enable_memory=True,
        enable_evolution=True,
        
        ui_title="教育辅导 · 个性化学习",
        ui_description="智能学习助手"
    )
```

### 步骤2：添加到__init__.py

```python
# scenarios/__init__.py
from scenarios.education_scenario import get_education_scenario

__all__ = [
    'get_chat_scenario',
    'get_callcenter_scenario',
    'get_insurance_scenario',
    'get_education_scenario',  # 新增
]
```

### 步骤3：创建Demo文件

```bash
# 复制模板
cp insurance_interactive_demo.py education_interactive_demo.py
cp insurance_gradio_demo.py education_gradio_demo.py

# 修改场景配置调用
sed -i 's/get_insurance_scenario/get_education_scenario/g' education_*.py
```

### 步骤4：添加提示词

在 `prompts.py` 中添加：

```python
EDUCATION_SYSTEM_PROMPT = """
你是一位专业的在线教育辅导老师...
"""
```

## 使用示例

### 在Demo中使用

```python
from scenarios import get_insurance_scenario

# 获取配置
config = get_insurance_scenario()

# 在DST模式中使用
tracker = DialogueStateTracker(
    llm_client=llm,
    domain=config.scenario_name
)

# 配置预定义意图和槽位
for intent_category, sub_intents in config.dst_intents.items():
    # 使用预定义意图，不通过LLM提取
    pass
```

### 在Application中使用

```python
from scenarios import get_insurance_scenario
from contextmind import ContextEngine

config = get_insurance_scenario()

engine = ContextEngine(
    system_prompt=config.system_prompt,
    enable_memory=config.enable_memory,
    enable_evolution=config.enable_evolution
)
```

## 最佳实践

1. **预定义 vs 动态**
   - 对于规范化场景（如保险、客服），使用预定义意图和槽位
   - 对于开放场景（如闲聊），使用动态LLM提取

2. **分类槽位**
   - 为有限枚举值的槽位定义分类约束
   - 提高识别准确性和一致性

3. **双层意图**
   - 复杂场景使用一级+二级意图体系
   - 一级意图分大类，二级意图细化

4. **配置优先**
   - 将场景特定逻辑放在配置中
   - 保持框架代码的通用性

## 场景对比

| 特性 | 闲聊 | 客服 | 保险 |
|------|------|------|------|
| 意图提取 | LLM动态 | 预定义+LLM | 预定义 |
| 槽位数量 | 动态 | 12个 | 18个 |
| 分类槽位 | 无 | 4个 | 8个 |
| 意图层级 | 单层 | 单层 | 双层 |
| 记忆功能 | 是 | 是 | 是 |
| 进化功能 | 是 | 是 | 是 |

## 总结

场景配置系统提供了：
- ✅ 灵活的场景定义
- ✅ 统一的配置接口
- ✅ 易于扩展新场景
- ✅ 配置驱动的架构
- ✅ 代码复用最大化
