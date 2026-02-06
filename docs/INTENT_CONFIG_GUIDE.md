# Intent Configuration System - 意图配置系统

## 概述

本系统实现了**配置驱动**的意图评测框架，将意图定义从硬编码迁移到JSON配置文件，实现了数据与代码的分离。

## 核心文件

### 1. 配置文件
- **路径**: `tests/configs/transfertod_intents.json`
- **作用**: 定义TransferTOD数据集的意图标签、映射关系、推断规则
- **格式**: JSON

### 2. 配置加载器
- **文件**: `tests/intent_config.py`
- **核心类**: `IntentConfig`, `IntentConfigLoader`
- **作用**: 加载、验证、查询意图配置

### 3. 意图评测器
- **文件**: `tests/intent_evaluator.py`
- **核心类**: `IntentEvaluator`
- **作用**: 使用配置进行意图推断和评测

## 配置文件结构

```json
{
  "dataset": "TransferTOD",
  "version": "1.0",
  "description": "数据集描述",
  
  "intents": {
    "task_related": [
      {
        "id": "provide_info",
        "name_en": "provide_info",
        "name_zh": "提供信息",
        "description": "用户主动提供槽位值",
        "inference_rule": "has_new_or_updated_slots",
        "priority": 4,
        "markers": ["标记词1", "标记词2"],
        "examples": ["示例1", "示例2"]
      }
    ],
    "task_independent": [...],
    "meta": [...]
  },
  
  "normalization_mapping": {
    "提供信息": "provide_info",
    "provide_info": "provide_info"
  },
  
  "task_relevance_mapping": {
    "provide_info": "task_related"
  },
  
  "aggregation_mapping": {
    "provide_info": "提供信息"
  }
}
```

## 使用方法

### 基础使用（自动加载默认配置）

```python
from tests.intent_evaluator import IntentEvaluator

# 自动加载 tests/configs/transfertod_intents.json
evaluator = IntentEvaluator()

# 进行意图推断
intent, relevance = evaluator.infer_intent_from_slots(
    turn_updates={'姓名': '张三'},
    previous_state={},
    user_utterance="我叫张三",
    turn_id=1
)
print(f"意图: {intent}, 相关性: {relevance}")
# 输出: 意图: provide_info, 相关性: task_related
```

### 使用自定义配置

```python
from tests.intent_config import load_intent_config
from tests.intent_evaluator import IntentEvaluator

# 加载自定义配置
config = load_intent_config("path/to/custom_intents.json")

# 使用自定义配置创建evaluator
evaluator = IntentEvaluator(intent_config=config)
```

### 查询配置信息

```python
from tests.intent_config import load_intent_config

config = load_intent_config()

# 1. 获取所有意图
all_intents = config.get_all_intents()
print(f"共有 {len(all_intents)} 个意图")

# 2. 获取特定意图详情
intent = config.get_intent_by_id("provide_info")
print(f"中文名: {intent['name_zh']}")
print(f"描述: {intent['description']}")
print(f"标记词: {intent['markers']}")

# 3. 标准化意图名称
normalized = config.normalize_intent("提供信息")
print(f"标准化: 提供信息 → {normalized}")  # provide_info

# 4. 获取显示名称
display_zh = config.get_intent_display_name("provide_info", "zh")
display_en = config.get_intent_display_name("provide_info", "en")
print(f"中文: {display_zh}, 英文: {display_en}")

# 5. 获取意图标记词
markers = config.get_intent_markers("request_info")
print(f"请求信息的标记词: {markers}")
```

## 添加新意图

### 步骤1：编辑JSON配置

在 `tests/configs/transfertod_intents.json` 中添加：

```json
{
  "intents": {
    "task_related": [
      {
        "id": "request_help",
        "name_en": "request_help",
        "name_zh": "请求帮助",
        "description": "用户请求帮助或支持",
        "inference_rule": "has_help_markers",
        "priority": 3,
        "markers": ["帮助", "支持", "help", "support"],
        "examples": ["需要帮助", "能帮我吗", "客服"]
      }
    ]
  }
}
```

### 步骤2：添加映射关系

```json
{
  "normalization_mapping": {
    "请求帮助": "request_help",
    "request_help": "request_help"
  },
  
  "task_relevance_mapping": {
    "request_help": "task_related"
  },
  
  "aggregation_mapping": {
    "request_help": "请求帮助"
  }
}
```

### 步骤3：无需修改代码！

配置会自动加载，新意图立即可用。

## 支持多数据集

### 创建新数据集配置

```bash
# 复制模板
cp tests/configs/transfertod_intents.json tests/configs/multiwoz_intents.json

# 编辑新配置
vim tests/configs/multiwoz_intents.json
```

### 使用新数据集

```python
config = load_intent_config("tests/configs/multiwoz_intents.json")
evaluator = IntentEvaluator(intent_config=config)
```

## 配置验证

### 必需字段

- `dataset`: 数据集名称
- `version`: 配置版本
- `intents`: 意图定义（至少包含`task_related`）
- `normalization_mapping`: 标准化映射

### 意图定义必需字段

- `id`: 唯一标识符
- `name_en`: 英文名称
- `name_zh`: 中文名称
- `description`: 描述
- `priority`: 优先级（0-5）

### 可选字段

- `inference_rule`: 推断规则描述
- `markers`: 检测标记词列表
- `examples`: 示例列表

## 最佳实践

### 1. 意图ID命名

- 使用小写字母和下划线
- 描述性命名：`provide_info` 而非 `pi`
- 保持一致性

### 2. 优先级设置

- 0: 最低优先级（unknown）
- 1: 任务无关意图（chitchat, greeting等）
- 2-3: 特殊任务意图（request, clarification）
- 4-5: 核心任务意图（provide_info, confirm_info）

### 3. 标记词选择

- 选择高区分度的词
- 包含中英文变体
- 避免过于通用的词

### 4. 映射完整性

确保所有意图在三个映射中都有定义：
- `normalization_mapping`: 中英文映射
- `task_relevance_mapping`: 任务相关性
- `aggregation_mapping`: 显示名称

## 迁移指南

### 从硬编码迁移到配置

**Before (硬编码):**
```python
class IntentType(Enum):
    PROVIDE_INFO = "provide_info"
    REQUEST_INFO = "request_info"
```

**After (配置驱动):**
```json
{
  "intents": {
    "task_related": [
      {"id": "provide_info", ...},
      {"id": "request_info", ...}
    ]
  }
}
```

### 检查清单

- [ ] 所有意图定义已移到JSON
- [ ] 映射关系已完整
- [ ] 标记词已配置
- [ ] 配置文件已验证
- [ ] 测试通过

## 故障排除

### 配置文件不存在

```python
FileNotFoundError: 意图配置文件不存在: ...
```

**解决**: 确保配置文件路径正确，或使用默认配置：
```python
evaluator = IntentEvaluator()  # 使用默认配置
```

### 缺少必需字段

```python
ValueError: 配置文件缺少必需字段: intents
```

**解决**: 检查JSON文件包含所有必需字段。

### 意图未找到

```python
intent = config.get_intent_by_id("unknown_intent")
# Returns None
```

**解决**: 检查意图ID拼写，或在配置中添加该意图。

## 参考

- 配置文件: `tests/configs/transfertod_intents.json`
- 加载器代码: `tests/intent_config.py`
- 评测器代码: `tests/intent_evaluator.py`
- 测试脚本: `tests/test_dst_transfertod.py`

## 版本历史

- **v1.0** (2026-02-06): 初始版本，支持TransferTOD数据集
  - 11个标准意图
  - 中英文映射
  - 标记词检测
  - 配置驱动架构
