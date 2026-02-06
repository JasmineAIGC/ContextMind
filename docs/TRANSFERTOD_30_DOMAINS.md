# TransferTOD 30域意图配置文档

## 概述

本文档描述了TransferTOD数据集的30个领域意图配置系统，包含完整的意图分类和特殊"其他"意图处理机制。

## 配置文件

**主配置文件**: `tests/configs/transfertod_30domains_intents.json`

**配置加载器**: `tests/domain_intent_config.py`

## 30个领域列表

| # | 领域 | 英文名 | 意图数 | 总字符数 |
|---|------|--------|--------|----------|
| 1 | 酒店 | hotel | 8 | 含"其他" |
| 2 | 餐厅 | restaurant | 8 | 含"其他" |
| 3 | 景点 | attraction | 7 | 含"其他" |
| 4 | 出租车 | taxi | 6 | 含"其他" |
| 5 | 地铁 | metro | 6 | 含"其他" |
| 6 | 火车 | train | 8 | 含"其他" |
| 7 | 医院 | hospital | 7 | 含"其他" |
| 8 | 电影 | movie | 7 | 含"其他" |
| 9 | 天气 | weather | 6 | 含"其他" |
| 10 | 音乐 | music | 7 | 含"其他" |
| 11 | 新闻 | news | 6 | 含"其他" |
| 12 | 电视 | tv | 6 | 含"其他" |
| 13 | 购物 | shopping | 8 | 含"其他" |
| 14 | 银行 | bank | 7 | 含"其他" |
| 15 | 快递 | express | 7 | 含"其他" |
| 16 | 翻译 | translation | 5 | 含"其他" |
| 17 | 提醒 | reminder | 5 | 含"其他" |
| 18 | 闹钟 | alarm | 5 | 含"其他" |
| 19 | 日历 | calendar | 6 | 含"其他" |
| 20 | 股票 | stock | 6 | 含"其他" |
| 21 | 外卖 | food_delivery | 7 | 含"其他" |
| 22 | 导航 | navigation | 5 | 含"其他" |
| 23 | 计算器 | calculator | 4 | 含"其他" |
| 24 | 笔记 | note | 5 | 含"其他" |
| 25 | 百科 | encyclopedia | 4 | 含"其他" |
| 26 | 运动 | sports | 5 | 含"其他" |
| 27 | 智能家居 | smart_home | 6 | 含"其他" |
| 28 | 图片 | image | 5 | 含"其他" |
| 29 | 视频 | video | 5 | 含"其他" |
| 30 | (预留) | - | - | 可扩展 |

**总计**: 29个已配置领域，~177个意图

## "其他"意图特殊设计

### 1. 配置层面

每个领域都包含"其他"作为兜底意图，配置示例：

```json
"其他": {
  "description": "其他未分类的意图",
  "keywords": [],
  "is_fallback": true
}
```

### 2. 元数据定义

```json
"metadata": {
  "other_intent_name": "其他",
  "other_intent_description": "catch-all intent for utterances that don't fit other intent categories",
  "other_intent_evaluation": "special_handling"
}
```

### 3. 代码层面

**判断方法**:
```python
def is_fallback_intent(domain: str, intent: str) -> bool:
    """检查是否是"其他"兜底意图"""
    return intent == "其他" or intent_desc.get("is_fallback", False)
```

**自动推断**:
```python
def infer_intent_from_context(domain, utterance, slots):
    """
    推断意图，优先匹配具体意图
    无匹配时自动返回"其他"
    """
    # 对所有非"其他"意图打分
    # 找到最佳匹配
    # 无匹配时返回"其他"
    return best_intent or "其他"
```

## 使用示例

### 加载配置

```python
from tests.domain_intent_config import load_domain_intent_config

# 加载配置（自动使用30域配置）
config = load_domain_intent_config()
```

### 查询领域

```python
# 获取所有领域
domains = config.get_all_domains()
print(f"共有{len(domains)}个领域")

# 获取特定领域的意图
hotel_intents = config.get_domain_intents("酒店")
print(f"酒店领域意图: {hotel_intents}")
```

### 意图推断

```python
# 自动推断意图
intent = config.infer_intent_from_context(
    domain="酒店",
    user_utterance="我想订个房间",
    slot_changes={"入住日期": "明天"}
)
# 返回: "预订酒店"

# 无法匹配时返回"其他"
intent = config.infer_intent_from_context(
    domain="酒店",
    user_utterance="今天天气真好",
    slot_changes={}
)
# 返回: "其他"
```

### 检查兜底意图

```python
# 检查是否是兜底意图
is_fallback = config.is_fallback_intent("酒店", "其他")
# 返回: True

is_fallback = config.is_fallback_intent("酒店", "预订酒店")
# 返回: False
```

## 评测建议

### 策略1: 分类统计

```python
# 分别统计"其他"和非"其他"意图的准确率
other_correct = 0
other_total = 0
non_other_correct = 0
non_other_total = 0

for predicted, ground_truth in predictions:
    if ground_truth == "其他":
        other_total += 1
        if predicted == ground_truth:
            other_correct += 1
    else:
        non_other_total += 1
        if predicted == ground_truth:
            non_other_correct += 1

other_accuracy = other_correct / other_total
non_other_accuracy = non_other_correct / non_other_total
```

### 策略2: 放宽匹配

```python
# 对"其他"意图放宽匹配标准
def is_correct(predicted, ground_truth, explicit_intents):
    if ground_truth == "其他":
        # "其他"与任何非明确意图都算正确
        return predicted == "其他" or predicted not in explicit_intents
    else:
        # 正常匹配
        return predicted == ground_truth
```

### 策略3: 加权计算

```python
# 给"其他"意图较低权重
weights = {
    "其他": 0.5,
    "其他_default": 1.0
}

weighted_accuracy = sum(
    weights.get(intent, 1.0) * is_correct
    for intent, is_correct in results
) / sum(weights.get(intent, 1.0) for intent in all_intents)
```

## 扩展指南

### 添加新领域

编辑 `transfertod_30domains_intents.json`:

```json
{
  "domains": {
    "新领域": {
      "domain_en": "new_domain",
      "intents": [
        "意图1",
        "意图2",
        "其他"
      ],
      "intent_descriptions": {
        "意图1": {
          "description": "...",
          "keywords": [...]
        },
        "其他": {
          "description": "其他未分类的意图",
          "keywords": [],
          "is_fallback": true
        }
      }
    }
  }
}
```

### 添加新意图

在现有领域中添加新意图（确保保留"其他"）:

```json
{
  "domains": {
    "酒店": {
      "intents": [
        "预订酒店",
        "新意图名称",  // 新增
        "其他"  // 保持在最后
      ],
      "intent_descriptions": {
        "新意图名称": {
          "description": "描述",
          "keywords": ["关键词1", "关键词2"]
        }
      }
    }
  }
}
```

## 注意事项

1. **"其他"必须存在**: 每个领域必须包含"其他"作为兜底意图
2. **is_fallback标记**: "其他"意图必须有 `"is_fallback": true` 标记
3. **推断优先级**: 意图推断时会自动跳过"其他"，优先匹配具体意图
4. **评测特殊处理**: 建议对"其他"意图采用特殊评测策略

## 技术规格

- **配置格式**: JSON
- **编码**: UTF-8
- **领域数**: 29个已配置 + 1个预留
- **总意图数**: ~177个
- **平均每域意图数**: ~6个
- **文件大小**: ~20KB

## 更新日志

### v3.0 (当前版本)
- ✅ 完整的30域配置
- ✅ "其他"意图特殊处理
- ✅ 自动意图推断
- ✅ 兜底机制

### v2.0 (已废弃)
- 6域配置
- 基础意图定义

### v1.0 (已废弃)
- 通用对话行为意图
- 非领域特定

## 相关文件

- `tests/configs/transfertod_30domains_intents.json` - 配置文件
- `tests/domain_intent_config.py` - 加载器
- `docs/INTENT_CONFIG_GUIDE.md` - 详细使用指南

## 参考

- TransferTOD GitHub: https://github.com/KongLongGeFDU/TransferTOD
- 中文任务型对话数据集标准

---

**维护者**: ContextMind Team  
**最后更新**: 2026-02-06
