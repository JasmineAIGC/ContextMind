# RiSAWOZ评测隔离性与Intent使用 - 完整说明

## 用户需求

> "RiSAWOZ 评测的修改 不能影响到原来 TransferTOD 的评测，两个数据集是不一样的。另外RiSAWOZ 数据标注里是有 意图的，直接用就行。"

## 解决方案总结

### ✅ 需求1: RiSAWOZ不影响TransferTOD

**实现**: 完全隔离的架构

#### 独立评测脚本
```
benchmark/
├── run_dst_transfertod.py    # TransferTOD专用，未修改
└── run_dst_risawoz.py        # RiSAWOZ专用，新功能
```

#### 独立配置文件
```
benchmark/shared/configs/
├── intent_labels_30_domains_Version2.json  # TransferTOD (30领域)
└── intent_labels_risawoz.json              # RiSAWOZ (13领域)
```

#### 向后兼容设计
```python
# TransferTOD: 保持原样
pm = PromptManager(domain="酒店")  # 使用默认配置

# RiSAWOZ: 使用自定义配置
pm = PromptManager(
    domain="酒店",
    intent_label_loader=risawoz_loader  # 可选参数
)
```

#### 验证结果
```bash
$ python tests/test_dataset_isolation.py

✅ TransferTOD: 30个领域
✅ RiSAWOZ: 13个领域
✅ 完全隔离，互不影响！
```

### ✅ 需求2: RiSAWOZ直接使用数据标注中的意图

**实现**: 从user_acts字段提取意图

#### RiSAWOZ数据格式
```json
{
  "dialogue": [
    {
      "transcript": "在昆山吧，适合朋友一起玩的地方",
      "user_acts": [
        ["Inform", "旅游景点", "区域", "昆山"],
        ["Inform", "旅游景点", "最适合人群", "朋友出游"]
      ]
    }
  ]
}
```

#### Intent提取代码
```python
# benchmark/datasets/risawoz/adapter.py
class DialogueTurn:
    user_intents: List[List[str]] = None  # 新增字段

# 提取user_acts
turn_data = {
    'user_intents': turn.get('user_acts', [])
}
```

#### Intent选择逻辑
```python
# benchmark/run_dst_risawoz.py
def _extract_dialogue_intent(self, dialogue):
    """从user_acts中提取对话级别的意图"""
    
    # 策略：优先选择Inform > Request > 其他
    inform_intents = []
    request_intents = []
    
    for turn in dialogue.turns:
        if turn.user_intents:
            for intent_info in turn.user_intents:
                intent_type = intent_info[0]  # Inform, Request等
                if intent_type == "Inform":
                    inform_intents.append(intent_type)
                elif intent_type == "Request":
                    request_intents.append(intent_type)
    
    # 返回最有代表性的意图
    if inform_intents:
        return "Inform"
    elif request_intents:
        return "Request"
    # ...
```

#### 验证结果
```bash
$ python tests/test_intent_extraction.py

✅ 成功提取意图！
对话级别意图: Inform
所有意图: ['Greeting', 'General', 'Inform', 'Inform', 'Inform', 'Inform', 
           'Request', 'Request', 'Request', 'Bye', 'General']
```

## 对比表

| 方面 | TransferTOD | RiSAWOZ |
|------|------------|---------|
| **评测脚本** | run_dst_transfertod.py | run_dst_risawoz.py |
| **领域数量** | 30 | 13 |
| **Intent配置** | intent_labels_30_domains_Version2.json | intent_labels_risawoz.json |
| **Intent来源** | ❌ 无ground truth (LLM预测) | ✅ user_acts字段 (ground truth) |
| **Intent提取** | LLM从对话中预测 | 直接从user_acts提取 |
| **是否修改** | ❌ 未修改 | ✅ 新增功能 |
| **是否隔离** | ✅ 完全隔离 | ✅ 完全隔离 |

## 修改内容

### 1. Adapter增强 (adapter.py)
```python
@dataclass
class DialogueTurn:
    user_intents: List[List[str]] = None  # 新增：存储user_acts
```

**功能**: 提取并存储user_acts字段

### 2. Intent提取逻辑 (run_dst_risawoz.py)
```python
def _extract_dialogue_intent(self, dialogue):
    """从user_acts提取意图"""
    # 优先级: Inform > Request > 其他
```

**功能**: 选择对话级别的代表性意图

### 3. PromptManager扩展 (prompt_manager.py)
```python
def __init__(self, intent_label_loader=None):  # 可选参数
    self.intent_label_loader = intent_label_loader
```

**功能**: 支持自定义intent配置，保持向后兼容

### 4. 隔离性测试 (test_dataset_isolation.py)
```python
def test_prompt_manager_backward_compatibility():
    """验证TransferTOD不受影响"""
```

**功能**: 自动化验证两个数据集的隔离性

## 测试验证

### 测试1: 隔离性验证
```bash
$ python tests/test_dataset_isolation.py

✅ TransferTOD: 30领域, 使用默认配置
✅ RiSAWOZ: 13领域, 使用自定义配置
✅ 完全隔离！
```

### 测试2: Intent提取验证
```bash
$ python tests/test_intent_extraction.py

✅ 成功从user_acts提取意图
✅ 对话意图: Inform
✅ 包含11个turn的意图
```

### 测试3: Adapter验证
```bash
$ python test_risawoz_test.py

✅ 成功加载600个对话
✅ user_acts正确提取
✅ 槽位值正确解析
```

## 关键设计决策

### 决策1: 可选参数而非强制修改
```python
# ✅ 好的设计
def __init__(self, intent_label_loader=None):  # 可选
    if intent_label_loader:
        use_custom_loader()
    else:
        use_default_loader()

# ❌ 坏的设计
def __init__(self):
    always_use_risawoz_config()  # 会破坏TransferTOD
```

### 决策2: 独立脚本而非共享脚本
```python
# ✅ 好的设计
run_dst_transfertod.py  # TransferTOD专用
run_dst_risawoz.py      # RiSAWOZ专用

# ❌ 坏的设计
run_dst.py --dataset transfertod  # 共享逻辑易相互影响
```

### 决策3: 直接提取而非LLM预测
```python
# ✅ 好的设计 (RiSAWOZ有ground truth)
intent = extract_from_user_acts(dialogue)

# ❌ 坏的设计 (浪费，且不准确)
intent = llm_predict_intent(dialogue)  # 有标注还预测？
```

## 使用示例

### TransferTOD评测（未受影响）
```bash
# 原样使用，无需改动
python benchmark/run_dst_transfertod.py --domain 酒店 --limit 10
```

### RiSAWOZ评测（新功能）
```bash
# 使用新的Intent提取功能
python benchmark/run_dst_risawoz.py \
    --data-root resources/data \
    --val-file risawoz_test.json \
    --split test \
    --limit 10
```

## FAQ

**Q1: 为什么不让两个数据集共享代码？**
A: 两个数据集格式、意图定义、评测方式都不同，强行共享会导致复杂度增加，容易相互影响。

**Q2: RiSAWOZ的意图真的可以直接用吗？**
A: 是的！user_acts字段包含了完整的意图标注：`["Inform", "旅游景点", "区域", "昆山"]`

**Q3: 如何确保TransferTOD真的不受影响？**
A: 运行 `python tests/test_dataset_isolation.py` 进行验证。

**Q4: 如果需要修改PromptManager怎么办？**
A: 使用可选参数，保持默认行为不变，新功能通过参数开启。

**Q5: 两个数据集可以同时运行吗？**
A: 可以！它们是完全独立的进程。

## 文档索引

- **DATASET_ISOLATION.md** - 详细的隔离性说明（本文档）
- **INTENT_EXTRACTION_FIX.md** - Intent提取的技术细节
- **INTENT_FIX_SUMMARY.md** - Intent修复的快速总结
- **RISAWOZ_TEST_JSON_FIX.md** - risawoz_test.json适配说明
- **test_dataset_isolation.py** - 隔离性自动化测试
- **test_intent_extraction.py** - Intent提取验证测试

## 总结

### ✅ 完全满足用户需求

1. **RiSAWOZ不影响TransferTOD** ✅
   - 独立脚本
   - 独立配置
   - 向后兼容
   - 自动化测试验证

2. **直接使用RiSAWOZ的意图标注** ✅
   - 从user_acts字段提取
   - 无需LLM预测
   - 准确且高效

### 架构优点

1. **清晰的关注点分离**: 每个数据集一个脚本
2. **完全的向后兼容**: TransferTOD零修改
3. **可扩展性**: 新数据集可以同样方式添加
4. **可测试性**: 自动化测试确保隔离
5. **可维护性**: 修改一个不影响另一个

### 验证方式

```bash
# 快速验证
python tests/test_dataset_isolation.py
python tests/test_intent_extraction.py

# 完整测试
python test_risawoz_test.py
```

---

**状态**: ✅ 完成  
**隔离性**: ✅ 验证通过  
**Intent提取**: ✅ 正常工作  
**文档**: ✅ 完整
