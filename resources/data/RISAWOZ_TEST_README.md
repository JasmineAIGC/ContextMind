# RiSAWOZ 测试数据说明

## 文件信息

- **文件名**: `risawoz_test.json`
- **大小**: 7.9 MB
- **记录数**: 600 个完整对话
- **用途**: 对话状态追踪（DST）任务的评测数据

## 数据格式

这个文件是一个 JSON 列表，每个元素代表一个完整的多轮对话。

### 数据结构

每个对话包含以下字段：

```python
{
    "dialogue_idx": str,      # 对话唯一标识符
    "domains": List[str],     # 对话涉及的领域列表
    "dialogue": List[Dict]    # 对话轮次列表
}
```

### 对话轮次结构

每个轮次（turn）包含：

```python
{
    "turn_idx": int,                    # 轮次索引（从0开始）
    "domain": str,                      # 当前轮次的领域
    "system_transcript": str,           # 系统话语
    "system_acts": List[List[str]],     # 系统动作
    "transcript": str,                  # 用户话语
    "delex_transcript": str,            # 去词汇化的用户话语
    "user_acts": List[List[str]],       # 用户动作 [意图, 领域, 槽位, 值]
    "belief_state": List[Dict],         # 累积的belief state
    "turn_label": List[List[str]]       # 当前轮次的槽位-值对
}
```

### belief_state 格式

```python
[
    {
        "slots": [
            ["领域-槽位", "值"],
            ["旅游景点-区域", "昆山"],
            ["旅游景点-消费", "偏贵"]
        ],
        "act": "inform"  # 或其他动作类型
    },
    ...
]
```

### user_acts 格式

```python
[
    ["意图", "领域", "槽位", "值"],
    ["Greeting", "旅游景点", "", ""],
    ["Inform", "旅游景点", "区域", "昆山"]
]
```

## 完整示例

```json
{
  "dialogue_idx": "attraction_goal_1-13_v2###8382",
  "domains": ["旅游景点"],
  "dialogue": [
    {
      "turn_idx": 0,
      "domain": "旅游景点",
      "system_transcript": "",
      "system_acts": [],
      "transcript": "你好 ! 我 是从 外地 来 苏州旅游 的 ， 能 推荐 个 好玩 的 地方 吗 ？",
      "delex_transcript": "你好 ! 我 是从 外地 来 苏州旅游 的 ， 能 推荐 个 好玩 的 地方 吗 ？",
      "user_acts": [["Greeting", "旅游景点", "", ""], ["General", "旅游景点", "", ""]],
      "belief_state": [],
      "turn_label": []
    },
    {
      "turn_idx": 1,
      "domain": "旅游景点",
      "system_transcript": "你好 ！ 当然 没 问题 的 ! 你 想 去 哪个 区域 的 景点 呢 ？",
      "system_acts": [["Greeting", "通用", "", ""], ["Request", "旅游景点", "区域", ""]],
      "transcript": "在 昆山 吧 ， 适合 朋友 一起 玩 的 地方 ， 消费 贵点 也 是 可以 的 。",
      "delex_transcript": "在 [旅游景点_区域] 吧 ， 适合 朋友 一起 玩 的 地方 ， 消费 贵点 也 是 可以 的 。",
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
  ]
}
```

## 使用场景

这个数据文件适用于以下任务：

### 1. 对话状态追踪（DST）
- 追踪对话过程中的belief state变化
- 评测DST模型的准确性
- 计算Joint Accuracy、Slot Accuracy等指标

### 2. 意图识别
- 从user_acts中提取用户意图
- 多意图分类和评测

### 3. 对话管理研究
- 研究多轮对话的状态转换
- 分析系统响应策略

## 数据统计

- **总对话数**: 600
- **总轮次数**: 约3,600轮（平均每个对话6轮）
- **涵盖领域**: 旅游景点、酒店、餐厅等
- **常见意图**: Greeting, General, Request, Inform, Recommend

## 读取示例

### Python 读取

```python
import json

# 读取数据
with open('resources/data/risawoz_test.json', 'r', encoding='utf-8') as f:
    dialogues = json.load(f)

# 访问第一个对话
first_dialogue = dialogues[0]
print(f"对话ID: {first_dialogue['dialogue_idx']}")
print(f"领域: {first_dialogue['domains']}")
print(f"轮次数: {len(first_dialogue['dialogue'])}")

# 遍历对话轮次
for turn in first_dialogue['dialogue']:
    print(f"轮次 {turn['turn_idx']}")
    print(f"  用户: {turn['transcript']}")
    print(f"  系统: {turn['system_transcript']}")
    print(f"  Belief state: {turn['belief_state']}")
```

### 使用适配器

```python
from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

# 创建适配器
adapter = RiSAWOZAdapter(
    data_root="resources/data",
    file_mapping={"test": "risawoz_test.json"}
)

# 加载对话
dialogue = adapter.load_dialogue("0", split="test")

# 访问标准化的对话数据
print(f"对话ID: {dialogue.dialogue_id}")
print(f"领域: {dialogue.domain}")
print(f"轮次数: {len(dialogue.turns)}")

# 访问轮次
for turn in dialogue.turns:
    print(f"轮次 {turn.turn_id}")
    print(f"  用户: {turn.user_utterance}")
    print(f"  系统: {turn.system_utterance}")
    print(f"  期望槽位: {turn.expected_slots}")
```

## DST 评测

### 运行评测

```bash
# 使用 risawoz_test.json 进行 DST 评测
python benchmark/run_dst_risawoz.py \
    --data-root resources/data \
    --val-file risawoz_test.json \
    --split test \
    --limit 10 \
    --verbose
```

### 评测指标

- **Slot Accuracy**: 槽位级别的准确率
- **Joint Accuracy**: 对话级别的联合准确率
- **Precision/Recall/F1**: 槽位预测的精确率、召回率和F1分数

## 相关资源

- RiSAWOZ 数据集: https://github.com/terryqj0107/RiSAWOZ
- RiSAWOZ 论文: [链接到论文]
- DST 适配器文档: `benchmark/datasets/risawoz/adapter.py`

## 注意事项

1. **文件较大**: 7.9 MB，包含完整的600个对话
2. **编码格式**: UTF-8，包含中文字符
3. **DST 格式**: 这是标准的DST数据格式，包含完整的belief state
4. **累积状态**: belief_state是累积的，包含从对话开始到当前轮次的所有槽位

## 更新日志

- 2026-02-11: 更新文档，说明实际是DST格式而非NLU格式
- 2026-02-11: 添加适配器使用示例和评测命令
