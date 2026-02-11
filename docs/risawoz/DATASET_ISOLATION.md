# RiSAWOZ与TransferTOD评测隔离性说明

## 概述

本文档详细说明RiSAWOZ和TransferTOD两个数据集的评测是完全隔离的，对RiSAWOZ的修改不会影响TransferTOD的评测。

## 用户关切

> "RiSAWOZ 评测的修改 不能影响到原来 TransferTOD 的评测，两个数据集是不一样的。"

**回答**: ✅ 完全隔离，互不影响！

## 隔离机制

### 1. 独立的评测脚本

```
benchmark/
├── run_dst_transfertod.py    # TransferTOD专用评测脚本
└── run_dst_risawoz.py        # RiSAWOZ专用评测脚本
```

**特点**:
- 两个完全独立的Python文件
- 各自的命令行参数
- 独立的数据加载逻辑
- 不共享任何评测状态

### 2. 不同的Intent配置

**TransferTOD**:
```python
# 使用默认配置（30个领域）
self.intent_evaluator = IntentEvaluator()  
pm = PromptManager(domain=domain)  # 不传intent_label_loader
```
- 配置文件: `intent_labels_30_domains_Version2.json`
- 领域数: 30个
- 领域示例: 酒店、景点、餐厅、外卖、火车票、机票...
- 意图示例: 预订酒店、查询酒店信息、取消预订...

**RiSAWOZ**:
```python
# 使用RiSAWOZ专用配置（13个领域）
risawoz_config = "benchmark/shared/configs/intent_labels_risawoz.json"
self.intent_label_loader = IntentLabelLoader(risawoz_config)
self.intent_evaluator = IntentEvaluator(intent_label_loader=self.intent_label_loader)
pm = PromptManager(domain=domain, intent_label_loader=self.intent_label_loader)
```
- 配置文件: `intent_labels_risawoz.json`
- 领域数: 13个
- 领域示例: 医院、天气、旅游景点、汽车、火车、电影...
- 意图示例: Inform、Request、General、Greeting、Bye...

### 3. 向后兼容的PromptManager

**设计原则**:
```python
class PromptManager:
    def __init__(self, 
                 domain: str = "general",
                 intent_label_loader = None):  # 可选参数，默认None
        self.intent_label_loader = intent_label_loader
        # ...
```

**关键机制**:
```python
def _load_domain_intents(self):
    # 优先使用自定义loader（RiSAWOZ）
    loader = self.intent_label_loader if self.intent_label_loader is not None else _get_intent_label_loader()
    # 回退到默认loader（TransferTOD）
```

**结果**:
- TransferTOD: 传入`None`，使用默认加载器 → 30个领域配置
- RiSAWOZ: 传入自定义加载器 → 13个领域配置
- **完全隔离，互不影响**

## 数据集对比

### TransferTOD数据集

**数据格式**:
```json
{
  "dialogue_id": "...",
  "dialogue": [
    {
      "turn_idx": 0,
      "user_utterance": "我想订一个酒店",
      "system_utterance": "好的，请问您有什么要求？",
      "belief_state": [
        {"domain": "酒店", "slot": "预订意图", "value": "预订"}
      ]
    }
  ]
}
```

**意图来源**: LLM预测（无ground truth）

**评测方式**:
- DST槽位准确率
- Joint Accuracy（对话级）
- LLM预测的意图

### RiSAWOZ数据集

**数据格式**:
```json
{
  "dialogue_idx": 0,
  "domains": ["旅游景点"],
  "dialogue": [
    {
      "turn_idx": 0,
      "transcript": "你好",
      "system_transcript": "你好，有什么可以帮助您的",
      "belief_state": [
        {"slots": [["旅游景点-区域", "昆山"]], "act": "inform"}
      ],
      "user_acts": [
        ["Inform", "旅游景点", "区域", "昆山"]
      ]
    }
  ]
}
```

**意图来源**: `user_acts` 字段（ground truth）✅

**评测方式**:
- DST槽位准确率
- Joint Accuracy（对话级）
- **直接使用user_acts中的意图**（无需LLM预测）

## Intent提取对比

### TransferTOD: LLM预测

```python
# TransferTOD没有ground truth intent
# 依赖LLM从对话中预测
predicted_intent = llm_predict_intent(dialogue)
```

### RiSAWOZ: 直接提取

```python
# RiSAWOZ有ground truth intent
def _extract_dialogue_intent(self, dialogue):
    """从user_acts中提取意图"""
    for turn in dialogue.turns:
        if turn.user_intents:  # user_acts字段
            for intent_info in turn.user_intents:
                intent_type = intent_info[0]  # Inform, Request, etc.
                # 选择最有代表性的意图
    return selected_intent
```

**关键点**: RiSAWOZ直接使用数据标注中的意图，不需要LLM预测！

## 验证测试

运行隔离性测试:
```bash
python tests/test_dataset_isolation.py
```

**测试结果**:
```
✅ 测试1: PromptManager向后兼容性
   TransferTOD意图数: 8 (使用默认配置)
   RiSAWOZ意图数: 5 (使用自定义配置)

✅ 测试2: IntentLabelLoader隔离性
   TransferTOD: 30个领域
   RiSAWOZ: 13个领域

✅ 结论: 两个数据集完全隔离，互不影响！
```

## 关键差异总结

| 方面 | TransferTOD | RiSAWOZ |
|------|------------|---------|
| **评测脚本** | run_dst_transfertod.py | run_dst_risawoz.py |
| **领域数量** | 30 | 13 |
| **Intent配置** | intent_labels_30_domains_Version2.json | intent_labels_risawoz.json |
| **Intent来源** | LLM预测 | user_acts字段（ground truth）|
| **PromptManager参数** | `PromptManager(domain)` | `PromptManager(domain, intent_label_loader=...)` |
| **意图示例** | 预订酒店、查询信息 | Inform、Request、General |
| **字段名** | user_utterance, system_utterance | transcript, system_transcript |
| **belief_state格式** | `[{domain, slot, value}]` | `[{slots: [[k,v]], act}]` |

## 修改历史

### 为RiSAWOZ添加的功能

1. **Intent标签加载器** (commit: db8aaff)
   - 添加RiSAWOZ专用配置文件
   - PromptManager支持自定义intent_label_loader
   - **向后兼容**: 不影响TransferTOD

2. **Intent提取** (commit: 6f13233)
   - 从user_acts字段提取意图
   - 只在RiSAWOZ脚本中使用
   - **不修改TransferTOD脚本**

3. **适配器增强** (commit: 4bc4878)
   - 支持多种字段名
   - 支持多种belief_state格式
   - **向后兼容**: 旧格式仍然工作

### 对TransferTOD的影响

**答案: 零影响！**

- ✅ PromptManager的修改是可选参数，完全向后兼容
- ✅ TransferTOD脚本未做任何修改
- ✅ TransferTOD使用默认配置，行为完全不变
- ✅ 所有修改仅在RiSAWOZ脚本中生效

## 如何确保未来修改也保持隔离

### 1. 使用独立的脚本
```bash
# TransferTOD评测
python benchmark/run_dst_transfertod.py --domain 酒店

# RiSAWOZ评测  
python benchmark/run_dst_risawoz.py --val-file risawoz_test.json
```

### 2. 明确区分配置文件
```
benchmark/shared/configs/
├── intent_labels_30_domains_Version2.json  # TransferTOD专用
└── intent_labels_risawoz.json              # RiSAWOZ专用
```

### 3. 使用可选参数而非强制修改
```python
# ✅ 好的做法：添加可选参数
class PromptManager:
    def __init__(self, intent_label_loader=None):  # 可选
        pass

# ❌ 坏的做法：强制修改默认行为
class PromptManager:
    def __init__(self):
        self.loader = load_risawoz_config()  # 会影响TransferTOD
```

### 4. 运行隔离性测试
```bash
# 在每次修改后运行
python tests/test_dataset_isolation.py
```

## FAQ

**Q: RiSAWOZ的修改会影响TransferTOD吗？**
A: 不会。两个数据集使用独立的脚本和配置，完全隔离。

**Q: PromptManager的修改是否向后兼容？**
A: 是的。intent_label_loader是可选参数，TransferTOD不传此参数，使用默认行为。

**Q: RiSAWOZ的intent是从哪里来的？**
A: 直接从数据的user_acts字段提取，是ground truth标注，不需要LLM预测。

**Q: 两个数据集可以同时运行吗？**
A: 可以。它们是完全独立的进程，不会相互干扰。

**Q: 如何验证隔离性？**
A: 运行 `python tests/test_dataset_isolation.py` 查看验证结果。

## 结论

✅ **RiSAWOZ和TransferTOD的评测是完全隔离的**

1. 使用独立的评测脚本
2. 使用不同的intent配置文件（30 vs 13个领域）
3. 使用不同的intent来源（LLM预测 vs user_acts标注）
4. PromptManager完全向后兼容
5. 所有修改仅影响RiSAWOZ
6. TransferTOD行为完全不变

**验证**: 运行 `python tests/test_dataset_isolation.py` 确认隔离性！
