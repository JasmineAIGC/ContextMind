# RiSAWOZ Intent Labels Fix - 修复报告

## 问题描述

根据 `logs/temp.log` 的分析，发现以下问题：

1. **错误的意图来源**: RiSAWOZ数据集评测使用了TransferTOD的意图标签配置文件
2. **大量"领域未找到"警告**: 日志中出现多次 `领域 '未知' 在意图标签中未找到`

## 问题根源

### 问题1：意图来源错误

**现象**:
```
[2026-02-11 16:10:05] INFO - [benchmark.shared.intent_label_loader] 已加载 30 个领域的意图标签
```

**原因**:
- RiSAWOZ评测代码中的`IntentEvaluator`使用默认配置
- 默认配置指向 `intent_labels_30_domains_Version2.json` (TransferTOD的30个领域)
- 应该使用 `intent_labels_risawoz.json` (RiSAWOZ的13个领域)

**影响**:
- TransferTOD领域与RiSAWOZ领域不匹配
- 意图评测不准确

### 问题2：领域"未知"警告

**现象**:
```
[2026-02-11 16:10:05] WARNING - [benchmark.shared.intent_label_loader] 领域 '未知' 在意图标签中未找到
[2026-02-11 16:10:05] WARNING - [contextmind.modes.dst.prompt_manager] No intents found for domain: 未知
```

**原因**:
- `adapter.py` 中的领域提取逻辑：当对话中没有belief_state或者belief_state为空时，默认返回"未知"
- "未知"不在意图标签配置中，导致警告

**代码位置** (`benchmark/datasets/risawoz/adapter.py:223`):
```python
domain = list(domains)[0] if domains else "未知"  # ❌ 问题所在
```

## 修复方案

### 修复1：使用RiSAWOZ专用意图配置

**修改文件**: `benchmark/run_dst_risawoz.py`

**Before**:
```python
self.intent_evaluator = IntentEvaluator()  # 使用默认配置
```

**After**:
```python
# 使用RiSAWOZ专用的意图标签配置
risawoz_intent_config = Path(__file__).parent / "shared" / "configs" / "intent_labels_risawoz.json"
self.intent_label_loader = IntentLabelLoader(str(risawoz_intent_config))
self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)
```

### 修复2：PromptManager使用自定义意图加载器

**修改文件**: `contextmind/modes/dst/prompt_manager.py`

**添加参数**:
```python
def __init__(self, 
             ...
             intent_label_loader = None):  # 新增参数
```

**使用自定义加载器**:
```python
# 优先使用自定义的intent_label_loader
loader = self.intent_label_loader if self.intent_label_loader is not None else _get_intent_label_loader()
```

### 修复3：修改默认领域为"通用"

**修改文件**: `benchmark/datasets/risawoz/adapter.py`

**Before**:
```python
domain = list(domains)[0] if domains else "未知"
```

**After**:
```python
# 如果没有找到领域，使用"通用"作为默认领域（RiSAWOZ有"通用"领域）
domain = list(domains)[0] if domains else "通用"
```

**原因**: RiSAWOZ数据集中有"通用"领域，使用它作为默认值可以避免警告。

### 修复4：更新RiSAWOZ意图配置格式

**修改文件**: `benchmark/shared/configs/intent_labels_risawoz.json`

**Before** (简化格式):
```json
{
  "医院": ["Bye", "General", "Inform", ...],
  "天气": ["Bye", "General", "Greeting", ...],
  ...
}
```

**After** (标准格式):
```json
{
  "dataset": "RiSAWOZ",
  "version": "1.0",
  "metadata": {
    "other_intent_name": "General",
    ...
  },
  "domains": {
    "医院": {
      "intents": ["Bye", "General", "Inform", ...]
    },
    ...
  }
}
```

## 修复效果

### Before (修复前)
```
[INFO] 已加载 30 个领域的意图标签  ← TransferTOD配置
[WARNING] 领域 '未知' 在意图标签中未找到  ← 多次警告
[WARNING] No intents found for domain: 未知
```

### After (修复后)
```
[INFO] 已加载 13 个领域的意图标签  ← RiSAWOZ配置
[INFO] Loaded X intents for domain: 通用  ← 正确加载意图
```

## RiSAWOZ vs TransferTOD 对比

| 特性 | TransferTOD | RiSAWOZ |
|------|-------------|---------|
| 领域数量 | 30个 | 13个 |
| 配置文件 | intent_labels_30_domains_Version2.json | intent_labels_risawoz.json |
| 语言 | 中文 | 中文 |
| 领域示例 | 酒店, 景点, 餐厅, 外卖, 火车票... | 医院, 天气, 旅游景点, 汽车, 火车... |
| 意图示例 | 查询, 预订, 告知, 确认, 请求... | Bye, General, Greeting, Inform, Recommend, Request... |

## RiSAWOZ 13个领域

```
医院、天气、旅游景点、汽车、火车、电影、电脑、
电视剧、辅导班、通用、酒店、飞机、餐厅
```

## RiSAWOZ 意图类型

常见意图：
- **Inform**: 用户提供信息
- **Request**: 用户请求信息
- **Recommend**: 系统推荐
- **General**: 通用对话
- **Greeting**: 问候
- **Bye**: 告别
- **No-offer**: 无法提供服务

## 验证方法

```bash
# 运行RiSAWOZ评测
python benchmark/run_dst_risawoz.py --val-file <path> --limit 10

# 应该看到：
# [INFO] 已加载 13 个领域的意图标签
# [INFO] Loaded X intents for domain: XXX

# 不应该看到：
# [WARNING] 领域 '未知' 在意图标签中未找到
```

## 相关文件

- `benchmark/run_dst_risawoz.py` - 评测脚本
- `benchmark/datasets/risawoz/adapter.py` - 数据适配器
- `benchmark/shared/configs/intent_labels_risawoz.json` - RiSAWOZ意图配置
- `benchmark/shared/intent_label_loader.py` - 意图标签加载器
- `contextmind/modes/dst/prompt_manager.py` - 提示词管理器

## 总结

✅ **问题1已修复**: RiSAWOZ评测现在使用正确的意图配置  
✅ **问题2已修复**: 默认领域改为"通用"，不再出现警告  
✅ **配置格式已统一**: RiSAWOZ配置符合IntentLabelLoader期望的格式  

---

**修复日期**: 2026-02-11  
**提交**: db8aaff
