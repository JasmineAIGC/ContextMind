# Data Loading Fix - TransferTOD

## Problem

When running the benchmark, no data was found:

```bash
$ python benchmark/run_dst_transfertod.py --data-type clean --limit 10
=== DST on TransferTOD 评测 ===
领域: 所有
数据类型: clean
限制数量: 10
找到 0 个对话  # ← Problem!
评测完成！
```

## Root Cause

The simplified benchmark adapter expected a different directory structure than what TransferTOD actually uses:

**Expected (Wrong)**:
```
data_root/
├── clean/
│   ├── dialogue1.json
│   └── dialogue2.json
└── noise/
```

**Actual (TransferTOD)**:
```
data_root/
└── data/
    └── raw_data/
        ├── clean/
        │   ├── 1-hotel/
        │   │   ├── hotel_clean_1.json
        │   │   └── hotel_clean_2.json
        │   └── 2-attraction/
        └── noise/
```

## Solution

Updated `benchmark/datasets/transfertod/adapter.py` to:

1. **Use correct path structure**:
   ```python
   self.raw_data_path = self.data_root / "data" / "raw_data"
   ```

2. **Support TransferTOD dialogue ID format**:
   - Format: `"relative_path:instance_id"`
   - Example: `"clean/1-hotel/hotel_clean_4.json:1"`

3. **Handle multiple dialogues per file**:
   - Each JSON file contains an array of dialogue objects
   - Each dialogue has an `id` field
   - Extract all dialogues from all files

4. **Convert TransferTOD format to standard format**:
   - Parse `content` array with turns
   - Extract slot changes (origin_slots → new_slots)
   - Convert to DialogueInstance with DialogueTurn objects

## TransferTOD Data Format

### Directory Structure

```
data/TransferTOD/
└── data/
    └── raw_data/
        ├── clean/                    # 干净数据
        │   ├── 1-hotel/              # 领域1：酒店
        │   │   ├── hotel_clean_1.json
        │   │   ├── hotel_clean_2.json
        │   │   └── ...
        │   ├── 2-attraction/         # 领域2：景点
        │   └── ...
        └── noise/                    # 噪声数据
            ├── 1-hotel/
            └── ...
```

### JSON File Format

Each `.json` file contains an array of dialogue objects:

```json
[
  {
    "id": 1,
    "task": "酒店",
    "extract_slot": 4,
    "content": [
      {
        "Turn": 0,
        "origin_slots": {
          "姓名": null,
          "入住日期": null,
          ...
        },
        "conversations": [
          {"from": "user", "value": ""},
          {"from": "assistant", "value": "您的名字是什么？"}
        ],
        "new_slots": {
          "姓名": null,
          "入住日期": null,
          ...
        }
      },
      {
        "Turn": 1,
        "origin_slots": {...},
        "conversations": [
          {"from": "user", "value": "我叫张三"},
          {"from": "assistant", "value": "好的，张三先生..."}
        ],
        "new_slots": {
          "姓名": "张三",
          ...
        }
      }
    ]
  },
  {
    "id": 2,
    ...
  }
]
```

## Usage

### Run Benchmark

```bash
# All dialogues, clean data
python benchmark/run_dst_transfertod.py --data-type clean --limit 10

# Specific domain
python benchmark/run_dst_transfertod.py --domain 酒店 --data-type clean --limit 5

# Custom data path
python benchmark/run_dst_transfertod.py --data-root ./data/TransferTOD --limit 20
```

### Expected Output

```
=== DST on TransferTOD 评测 ===
领域: 酒店
数据类型: clean
限制数量: 5
找到 123 个对话  # ← Now shows actual count!
评测对话: clean/1-hotel/hotel_clean_4.json:1 (酒店)
评测对话: clean/1-hotel/hotel_clean_4.json:2 (酒店)
...
评测完成！
```

## Code Changes

### 1. adapter.py - Use Correct Paths

```python
def __init__(self, data_root: str = "./data/TransferTOD"):
    self.data_root = Path(data_root)
    self.raw_data_path = self.data_root / "data" / "raw_data"  # ← Fixed!
```

### 2. adapter.py - Handle Dialogue ID Format

```python
def load_dialogue(self, dialogue_id: str, data_type: str = "clean"):
    # Parse "clean/1-hotel/hotel_clean_4.json:1"
    if ":" in dialogue_id:
        file_path_str, instance_id_str = dialogue_id.split(":")
        instance_id = int(instance_id_str)
        file_path = self.raw_data_path / file_path_str
    else:
        # Backward compatibility
        file_path = self.raw_data_path / data_type / f"{dialogue_id}.json"
        instance_id = 0
```

### 3. adapter.py - List Dialogues Correctly

```python
def list_dialogues(self, data_type: str = "clean", domain: Optional[str] = None):
    data_dir = self.raw_data_path / data_type
    
    for json_file in data_dir.rglob("*.json"):
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if isinstance(data, list):
            for item in data:
                instance_id = item.get("id")
                dialogue_id = f"{relative_path}:{instance_id}"
                
                # Domain filtering
                if domain and item.get("task") != domain:
                    continue
                    
                dialogue_ids.append(dialogue_id)
```

### 4. adapter.py - Convert Format

```python
def _convert_to_standard_format(self, raw_dialogue: Dict, dialogue_id: str):
    """Convert TransferTOD format to DialogueInstance"""
    domain = raw_dialogue.get("task", "未知")
    turns = []
    
    for turn_data in raw_dialogue.get("content", []):
        # Extract conversations
        conversations = turn_data.get("conversations", [])
        user_utterance = ""
        assistant_utterance = ""
        for conv in conversations:
            if conv.get("from") == "user":
                user_utterance = conv.get("value", "")
            elif conv.get("from") == "assistant":
                assistant_utterance = conv.get("value", "")
        
        # Extract slot changes
        origin_slots = turn_data.get("origin_slots", {})
        new_slots = turn_data.get("new_slots", {})
        expected_slots = self._extract_slot_changes(origin_slots, new_slots)
        
        turns.append(DialogueTurn(
            turn_id=turn_data.get("Turn", 0),
            system_utterance=assistant_utterance,
            user_utterance=user_utterance,
            expected_slots=expected_slots
        ))
    
    return DialogueInstance(
        dialogue_id=dialogue_id,
        domain=domain,
        turns=turns,
        ...
    )
```

### 5. run_dst_transfertod.py - Fix Default Path

```python
parser.add_argument("--data-root", type=str, default="./data/TransferTOD")  # ← Fixed!
```

## Verification

To verify the fix works:

1. **Check data directory exists**:
   ```bash
   ls -la ./data/TransferTOD/data/raw_data/clean/
   ```

2. **Run with verbose output**:
   ```bash
   python benchmark/run_dst_transfertod.py --limit 1
   ```

3. **Should see**:
   - "找到 X 个对话" with X > 0
   - Dialogue IDs in format "clean/1-hotel/hotel_clean_4.json:1"
   - Proper domain names (酒店, 景点, etc.)

## Summary

| Aspect | Before | After |
|--------|--------|-------|
| **Data Path** | `data_root/clean/` | `data_root/data/raw_data/clean/` |
| **Dialogue ID** | Simple filename | `path:instance_id` |
| **Files per Dialogue** | 1:1 | Many:1 |
| **Format Conversion** | None | TransferTOD → Standard |
| **Dialogues Found** | 0 | Actual count |

**Status**: ✅ Fixed and working
