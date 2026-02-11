# risawoz_test.json 修复报告

## 问题描述

`resources/data/risawoz_test.json` 文件包含600个完整对话的DST数据，但原始的适配器和文档都不正确。

## 发现的问题

### 1. 文档错误
**问题**: `RISAWOZ_TEST_README.md` 错误地描述为NLU格式（9,286条单轮数据）
**实际**: 文件是DST格式（600个完整对话）

### 2. 适配器不兼容
**问题**: `adapter.py` 无法正确解析 risawoz_test.json 的格式
**原因**: 
- 字段名不匹配：`transcript` vs `user_utterance`
- belief_state格式不同：`{'slots': [[key, value]], 'act': 'act'}` vs `{'domain': 'X', 'slot': 'Y', 'value': 'Z'}`
- ID字段：`dialogue_idx` vs `dialogue_id`

### 3. 评测结果全0
**日志证据**:
```
平均槽位准确率 (Slot Accuracy): 0.00%
平均联合准确率-严格 (Joint Accuracy Strict): 0.00%
平均精确率 (Precision): 0.00%
```

## 实施的修复

### 1. 更新适配器 (adapter.py)

#### a) 支持多种字段名
```python
# 用户话语
user_utterance = turn_data.get("transcript") or turn_data.get("user_utterance", "")

# 系统话语  
system_utterance = turn_data.get("system_transcript") or turn_data.get("system_utterance", "")
```

#### b) 增强belief_state解析
```python
# 格式1: [{'slots': [[slot-key, value], ...], 'act': 'act'}, ...]  (新格式)
if isinstance(first_item, dict) and "slots" in first_item:
    for belief_item in belief_state_data:
        slots = belief_item.get("slots", [])
        for slot_pair in slots:
            if isinstance(slot_pair, list) and len(slot_pair) >= 2:
                slot_key = slot_pair[0]
                slot_value = slot_pair[1]
                turn_belief_state[slot_key] = slot_value

# 格式2: [{"domain": "X", "slot": "Y", "value": "Z"}, ...]  (旧格式)
elif isinstance(first_item, dict) and "domain" in first_item:
    for belief in belief_state_data:
        slot_domain = belief.get("domain", "")
        slot_name = belief.get("slot", "")
        slot_value = belief.get("value", "")
        if slot_name and slot_value:
            slot_key = f"{slot_domain}-{slot_name}" if slot_domain else slot_name
            turn_belief_state[slot_key] = slot_value
```

#### c) 从turn_label提取（后备方案）
```python
# 如果belief_state为空，从turn_label获取
if not turn_belief_state and "turn_label" in turn_data:
    turn_label = turn_data["turn_label"]
    if isinstance(turn_label, list):
        for label_pair in turn_label:
            if isinstance(label_pair, list) and len(label_pair) >= 2:
                slot_key = label_pair[0]
                slot_value = label_pair[1]
                turn_belief_state[slot_key] = slot_value
```

#### d) 改进领域提取
```python
# 优先级1: 对话级别的domains字段
if isinstance(dialogue_data, dict) and "domains" in dialogue_data:
    domains.update(dialogue_data.get("domains", []))

# 优先级2: 轮次级别的domain字段
for turn_data in dialogue_turns:
    if "domain" in turn_data and turn_data["domain"]:
        domains.add(turn_data["domain"])

# 优先级3: belief_state中的domain (兼容旧格式)
```

#### e) 支持dialogue_idx
```python
# 查找时同时支持dialogue_id和dialogue_idx
for item in data:
    if item.get("dialogue_id") == dialogue_id or item.get("dialogue_idx") == dialogue_id:
        dialogue_data = item
        break
```

### 2. 更新文档 (RISAWOZ_TEST_README.md)

**之前**: 描述为9,286条NLU格式数据
**现在**: 正确描述为600个DST格式对话

添加了：
- 完整的数据结构说明
- belief_state和user_acts格式
- 适配器使用示例
- DST评测命令

### 3. 创建测试脚本 (test_risawoz_test.py)

提供快速验证脚本：
```bash
python test_risawoz_test.py
```

输出：
```
✅ Successfully loaded adapter
Total dialogues: 600
✅ All tests passed!
```

## 验证结果

### 适配器测试
```python
adapter = RiSAWOZAdapter(
    data_root="resources/data",
    file_mapping={"test": "risawoz_test.json"}
)
dialogue = adapter.load_dialogue("0", split="test")

# ✅ Domain: 旅游景点
# ✅ Turns: 6
# ✅ Final slots: 4
# ✅ Slots correctly extracted:
#    旅游景点-区域: 昆山
#    旅游景点-最适合人群: 朋友 出游
#    旅游景点-消费: 偏贵
#    旅游景点-名称: 周庄 古镇
```

### 数据统计
- ✅ 总对话数: 600
- ✅ 每个对话包含多个轮次（平均6轮）
- ✅ 每个轮次包含：
  - user utterance (transcript)
  - system utterance (system_transcript)
  - belief_state (累积状态)
  - user_acts (意图标签)
  - turn_label (当前轮次的槽位)

## 使用方法

### 1. 直接使用适配器
```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

adapter = RiSAWOZAdapter(
    data_root="resources/data",
    file_mapping={"test": "risawoz_test.json"}
)

# 加载所有对话
dialogue_ids = adapter.get_dialogues_by_domain(None, split="test")  # 600个

# 加载单个对话
dialogue = adapter.load_dialogue("0", split="test")
```

### 2. 运行DST评测
```bash
python benchmark/run_dst_risawoz.py \
    --data-root resources/data \
    --val-file risawoz_test.json \
    --split test \
    --limit 10 \
    --verbose
```

### 3. 运行测试脚本
```bash
python test_risawoz_test.py
```

## 数据格式详解

### 对话结构
```json
{
  "dialogue_idx": "attraction_goal_1-13_v2###8382",
  "domains": ["旅游景点"],
  "dialogue": [...]
}
```

### 轮次结构
```json
{
  "turn_idx": 1,
  "domain": "旅游景点",
  "system_transcript": "你好 ！ 当然 没 问题 的 !",
  "transcript": "在 昆山 吧 ， 适合 朋友 一起 玩 的 地方",
  "user_acts": [
    ["Inform", "旅游景点", "区域", "昆山"],
    ["Inform", "旅游景点", "最适合人群", "朋友 出游"]
  ],
  "belief_state": [
    {"slots": [["旅游景点-区域", "昆山"]], "act": "inform"},
    {"slots": [["旅游景点-最适合人群", "朋友 出游"]], "act": "inform"}
  ],
  "turn_label": [
    ["旅游景点-区域", "昆山"],
    ["旅游景点-最适合人群", "朋友 出游"]
  ]
}
```

## 后续工作

1. ✅ 适配器已修复
2. ✅ 文档已更新
3. ✅ 测试脚本已创建
4. ⏳ 运行完整评测验证指标正确性
5. ⏳ 如需要，添加意图提取功能（从user_acts）

## 相关文件

- `benchmark/datasets/risawoz/adapter.py` - 适配器
- `resources/data/RISAWOZ_TEST_README.md` - 数据说明
- `resources/data/risawoz_test.json` - 测试数据
- `test_risawoz_test.py` - 测试脚本

## 更新日志

- 2026-02-11: 修复适配器支持risawoz_test.json格式
- 2026-02-11: 更新README，纠正NLU/DST格式混淆
- 2026-02-11: 添加测试脚本验证修复

---

**状态**: ✅ 已完成  
**测试**: ✅ 通过  
**文档**: ✅ 已更新
