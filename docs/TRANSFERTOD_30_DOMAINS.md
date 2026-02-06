# TransferTOD 30域意图配置文档

## 概述

TransferTOD数据集包含30个不同的对话域，每个域都有其特定的意图集合。本配置文件提供了完整的30域意图定义，包括特殊的"其他"意图处理。

## 30个领域列表

| # | 中文 | 英文 | 意图数 | 包含"其他" |
|---|------|------|--------|-----------|
| 1 | 酒店 | hotel | 8 | ✅ |
| 2 | 餐厅 | restaurant | 8 | ✅ |
| 3 | 景点 | attraction | 7 | ✅ |
| 4 | 出租车 | taxi | 6 | ✅ |
| 5 | 地铁 | metro | 6 | ✅ |
| 6 | 火车 | train | 8 | ✅ |
| 7 | 医院 | hospital | 7 | ✅ |
| 8 | 电影 | movie | 7 | ✅ |
| 9 | 天气 | weather | 6 | ✅ |
| 10 | 音乐 | music | 7 | ✅ |
| 11 | 新闻 | news | 6 | ✅ |
| 12 | 电视 | tv | 6 | ✅ |
| 13 | 购物 | shopping | 8 | ✅ |
| 14 | 银行 | bank | 7 | ✅ |
| 15 | 快递 | express | 7 | ✅ |
| 16 | 翻译 | translation | 5 | ✅ |
| 17 | 提醒 | reminder | 5 | ✅ |
| 18 | 闹钟 | alarm | 5 | ✅ |
| 19 | 日历 | calendar | 6 | ✅ |
| 20 | 股票 | stock | 6 | ✅ |
| 21 | 外卖 | food_delivery | 7 | ✅ |
| 22 | 导航 | navigation | 5 | ✅ |
| 23 | 计算器 | calculator | 4 | ✅ |
| 24 | 笔记 | note | 5 | ✅ |
| 25 | 百科 | encyclopedia | 4 | ✅ |
| 26 | 运动 | sports | 5 | ✅ |
| 27 | 智能家居 | smart_home | 6 | ✅ |
| 28 | 图片 | image | 5 | ✅ |
| 29 | 视频 | video | 5 | ✅ |
| 30 | 公交 | bus | 6 | ✅ |

**总计**: 30个领域，~183个意图

## intent_descriptions 的作用

### 为什么保留 intent_descriptions？

`intent_descriptions` 字段不仅仅是文档，它具有重要的功能作用：

1. **关键词匹配**: `keywords` 字段用于自动意图推断
2. **兜底识别**: `is_fallback` 标记用于识别"其他"意图
3. **意图描述**: 提供人类可读的意图说明

### 结构说明

```json
"intent_descriptions": {
  "意图名称": {
    "description": "意图的文本描述",
    "keywords": ["关键词1", "关键词2"],  // 用于自动匹配
    "is_fallback": true  // 仅用于"其他"意图
  }
}
```

### 使用示例

```python
from tests.domain_intent_config import load_domain_intent_config

config = load_domain_intent_config()

# 获取意图关键词（用于推断）
keywords = config.get_intent_keywords("酒店", "预订酒店")
# 返回: ["预订", "订房", "住"]

# 推断意图（使用关键词匹配）
intent = config.infer_intent_from_context(
    domain="酒店",
    user_utterance="我想订个房间",
    slot_changes={"入住日期": "明天"}
)
# 返回: "预订酒店" (因为utterance包含"订"关键词)
```

## "其他"意图特殊设计

每个领域都包含"其他"作为兜底意图，具有特殊标记 `"is_fallback": true`。

### 特殊处理机制

1. **推断时自动跳过**: 在 `infer_intent_from_context()` 中，不会将"其他"作为候选
2. **自动兜底**: 当没有其他意图匹配时，自动返回"其他"
3. **评测特殊处理**: 在意图评测时，"其他"可能需要放宽匹配标准

### 示例

```python
# 无法匹配任何具体意图时，返回"其他"
intent = config.infer_intent_from_context(
    domain="酒店",
    user_utterance="天气真好",  # 与酒店无关
    slot_changes={}
)
# 返回: "其他"
```

## 意图测试独立性

意图评测与槽位值测试是完全独立的两个系统：

### 槽位测试
- 位置: `test_dst_transfertod.py` 行 189-250
- 指标: Slot Accuracy, Joint Accuracy, Precision, Recall, F1
- 不受意图评测影响

### 意图测试
- 位置: `test_dst_transfertod.py` 行 157-177
- 指标: Intent Accuracy, Confusion Matrix
- 使用独立的 `IntentEvaluator`
- 不影响槽位指标

### 验证

运行测试时，两个评测系统分别输出结果，互不干扰：

```bash
python tests/test_dst_transfertod.py --domain 酒店 --limit 10

# 输出包含：
# 1. 槽位测试结果（独立）
# 2. 意图评测结果（独立）
```

## 扩展指南

### 添加新意图

只需编辑 JSON 文件：

```json
{
  "域名": {
    "intents": ["新意图", "其他"],
    "intent_descriptions": {
      "新意图": {
        "description": "描述",
        "keywords": ["关键词"]
      }
    }
  }
}
```

### 修改关键词

更新 `keywords` 数组即可，会立即生效于意图推断。

## 注意事项

1. 每个域必须包含"其他"意图
2. "其他"意图必须标记 `"is_fallback": true`
3. 关键词应该是常见、明确的词汇
4. 避免不同意图的关键词重叠

## 技术规格

- **配置文件**: `tests/configs/transfertod_30domains_intents.json`
- **加载器**: `tests/domain_intent_config.py`
- **版本**: 3.0
- **总大小**: ~21KB
- **编码**: UTF-8
