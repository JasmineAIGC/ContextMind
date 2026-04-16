#!/usr/bin/env python3
"""
Benchmark 数据集下载与准备工具

ContextMind benchmark 支持三个数据集：

1. RiSAWOZ（内置，无需下载）
   - 测试集 600 条对话已内置于 resources/data/risawoz_test.json
   - 直接运行:
       python benchmark/run_benchmark.py --algorithm dst --dataset risawoz
   - 若需完整数据集（train 10000 条 / val 600 条），请从官方仓库下载（见下方说明）

2. SGD（Google Schema-Guided Dialogue）
   - 需要手动下载，下载后放置于 resources/dataset/SGD/
   - 运行:
       python benchmark/run_benchmark.py --algorithm dst --dataset sgd --split test

3. TransferTOD（中文多领域任务型对话）
   - 需要手动下载，下载后放置于 resources/dataset/TransferTOD/
   - 运行:
       python benchmark/run_benchmark.py --algorithm dst --dataset transfertod

用法:
    python benchmark/prepare_datasets.py --dataset sgd --verify
    python benchmark/prepare_datasets.py --dataset transfertod --verify
    python benchmark/prepare_datasets.py --dataset risawoz --verify
"""

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 各数据集预期目录结构和下载说明
# ---------------------------------------------------------------------------

SGD_README = """
SGD (Schema-Guided Dialogue) 数据集准备说明
============================================

官方仓库: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

下载步骤:
  1. 克隆或下载 ZIP 包：
       git clone https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.git
     或访问: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue/archive/refs/heads/master.zip

  2. 将数据集目录（含 train/ dev/ test/ 子目录）移动到:
       resources/dataset/SGD/

  3. 最终目录结构应为:
       resources/dataset/SGD/
         train/
           schema.json
           dialogues_001.json
           dialogues_002.json
           ...
         dev/
           schema.json
           dialogues_001.json
           ...
         test/
           schema.json
           dialogues_001.json
           ...

  4. 验证:
       python benchmark/prepare_datasets.py --dataset sgd --verify

SGD 对话文件格式 (dialogues_*.json):
  [
    {
      "dialogue_id": "1_00001",
      "services": ["Flights_4"],
      "turns": [
        {
          "speaker": "USER",
          "utterance": "I need to find a flight.",
          "frames": [
            {
              "service": "Flights_4",
              "state": {
                "active_intent": "SearchOneWayFlight",
                "requested_slots": [],
                "slot_values": {"origin_city": ["New York"]}
              }
            }
          ]
        },
        {
          "speaker": "SYSTEM",
          "utterance": "Where would you like to go?",
          "frames": [...]
        }
      ]
    }
  ]

SGD schema.json 格式:
  [
    {
      "service_name": "Flights_4",
      "description": "Book domestic flights.",
      "slots": [...],
      "intents": [...]
    }
  ]
"""

TRANSFERTOD_README = """
TransferTOD 数据集准备说明
===========================

TransferTOD 是中文多领域任务型对话数据集，覆盖 24 个领域。

请联系数据集作者或查阅对应论文获取数据访问权限。

下载完成后，将数据目录放置到:
  resources/dataset/TransferTOD/

数据集目录结构应为:
  resources/dataset/TransferTOD/
    data/
      raw_data/
        clean/
          1-hotel/
            hotel_clean_1.json
            hotel_clean_2.json
            ...
          2-restaurant/
            ...
          ...（共 24 个领域子目录）
        noise/
          1-hotel/
            hotel_noise_1.json
            ...
          ...

验证:
  python benchmark/prepare_datasets.py --dataset transfertod --verify

TransferTOD 对话文件格式（每个 JSON 文件包含一个列表）:
  [
    {
      "id": 1,
      "task": "酒店",
      "extract_slot": 4,
      "content": [
        {
          "Turn": 0,
          "origin_slots": {"姓名": null, "入住日期": null, "退房日期": null, "房型": null},
          "new_slots":    {"姓名": null, "入住日期": null, "退房日期": null, "房型": null},
          "conversations": [
            {"from": "user",      "value": ""},
            {"from": "assistant", "value": "您的名字是什么？"}
          ]
        },
        {
          "Turn": 1,
          "origin_slots": {"姓名": null, "入住日期": null, "退房日期": null, "房型": null},
          "new_slots":    {"姓名": "张三", "入住日期": null, "退房日期": null, "房型": null},
          "conversations": [
            {"from": "user",      "value": "我叫张三"},
            {"from": "assistant", "value": "好的张三，请问您计划哪天入住？"}
          ]
        }
      ]
    }
  ]

槽位变化提取规则:
  每轮 expected_slots = new_slots 中比 origin_slots 新增或更改的非空槽位。
"""

RISAWOZ_README = """
RiSAWOZ 数据集说明
==================

测试集（600 条）已内置于:
  resources/data/risawoz_test.json

内置文件格式:
  [
    {
      "dialogue_idx": "attraction_goal_1-13_v2###8382",
      "domains": ["旅游景点"],
      "dialogue": [
        {
          "turn_idx": 0,
          "domain": "旅游景点",
          "transcript": "你好 ! 我 是从 外地 来 苏州旅游 的 ，...",
          "system_transcript": "",
          "user_acts": [["Greeting", "旅游景点", "", ""], ...],
          "belief_state": [
            {"slots": [["旅游景点-区域", "昆山"]], "act": "inform"},
            ...
          ],
          "turn_label": [["旅游景点-区域", "昆山"], ...]
        },
        ...
      ]
    }
  ]

字段说明:
  - dialogue_idx:    对话唯一标识符
  - domains:         对话涉及的领域列表
  - transcript:      用户话语（空格分词）
  - system_transcript: 系统话语
  - belief_state:    累积对话状态（每个元素含 slots 列表和 act 类型）
                     slots 格式: [["领域-槽位名", "槽位值"], ...]
  - turn_label:      本轮新增/更新的槽位标注（格式同上）

完整数据集（含 train/val）下载:
  官方仓库: https://github.com/terryqj0107/RiSAWOZ
  - 下载 source-data.zip 后解压到指定目录
  - 使用 --data-root 参数指定到 source-data/ 子目录
  - 同时通过 RISAWOZ_FILE_MAPPING 或适配器 file_mapping 参数指定文件名映射：
      {"train": "all_train10000.json", "val": "all_dev600.json", "test": "all_test600_new.json"}
"""


# ---------------------------------------------------------------------------
# 验证函数
# ---------------------------------------------------------------------------

def verify_risawoz(data_root: Path) -> bool:
    """验证 RiSAWOZ 内置数据完整性。"""
    test_file = data_root / "risawoz_test.json"
    if not test_file.exists():
        print(f"❌ 内置测试文件不存在: {test_file}")
        return False
    try:
        with open(test_file, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list) or len(data) == 0:
            print(f"❌ {test_file} 格式错误：期望非空列表")
            return False
        first = data[0]
        required_keys = {"dialogue_idx", "domains", "dialogue"}
        missing = required_keys - set(first.keys())
        if missing:
            print(f"❌ 对话条目缺少必需字段: {missing}")
            return False
        print(f"✅ RiSAWOZ 内置测试集验证通过，共 {len(data)} 条对话")
        print(f"   文件: {test_file}")
        # 打印样本
        first_dialogue = first["dialogue"][0]
        print(f"   样本: dialogue_idx={first['dialogue_idx']!r}, "
              f"domains={first['domains']}, "
              f"turns={len(first['dialogue'])}")
        print(f"   第 1 轮字段: {list(first_dialogue.keys())}")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}")
        return False


def verify_sgd(data_root: Path) -> bool:
    """验证 SGD 数据集目录结构。"""
    if not data_root.exists():
        print(f"❌ SGD 数据目录不存在: {data_root}")
        print(f"   请参考下方说明下载数据集:")
        print(SGD_README)
        return False

    ok = True
    for split in ("train", "dev", "test"):
        split_dir = data_root / split
        if not split_dir.exists():
            print(f"❌ 缺少 {split}/ 子目录: {split_dir}")
            ok = False
            continue
        schema_file = split_dir / "schema.json"
        if not schema_file.exists():
            print(f"❌ 缺少 schema.json: {schema_file}")
            ok = False
        dialogue_files = list(split_dir.glob("dialogues_*.json"))
        if not dialogue_files:
            print(f"❌ {split}/ 下没有 dialogues_*.json 文件")
            ok = False
        else:
            # 验证第一个对话文件的格式
            with open(dialogue_files[0], encoding="utf-8") as f:
                sample = json.load(f)
            if not isinstance(sample, list) or not sample:
                print(f"❌ {dialogue_files[0]} 格式错误：期望非空列表")
                ok = False
            else:
                first = sample[0]
                if "dialogue_id" not in first or "turns" not in first:
                    print(f"❌ 对话条目缺少 dialogue_id 或 turns 字段")
                    ok = False
                else:
                    print(f"✅ {split}/: schema.json + {len(dialogue_files)} 个对话文件，"
                          f"样本 dialogue_id={first['dialogue_id']!r}")

    return ok


def verify_transfertod(data_root: Path) -> bool:
    """验证 TransferTOD 数据集目录结构。"""
    raw_data_path = data_root / "data" / "raw_data"
    if not raw_data_path.exists():
        print(f"❌ TransferTOD 数据目录不存在: {raw_data_path}")
        print(f"   期望结构: {data_root}/data/raw_data/clean/<domain>/*.json")
        print(f"   请参考下方说明下载数据集:")
        print(TRANSFERTOD_README)
        return False

    ok = True
    for data_type in ("clean", "noise"):
        type_dir = raw_data_path / data_type
        if not type_dir.exists():
            print(f"⚠️  {data_type}/ 子目录不存在: {type_dir}（可选）")
            continue
        json_files = list(type_dir.rglob("*.json"))
        if not json_files:
            print(f"❌ {type_dir}/ 下没有找到任何 JSON 文件")
            ok = False
            continue

        # 验证第一个文件格式
        with open(json_files[0], encoding="utf-8") as f:
            sample = json.load(f)
        if isinstance(sample, list) and sample:
            first = sample[0]
            required = {"id", "task", "content"}
            missing = required - set(first.keys())
            if missing:
                print(f"❌ {json_files[0]}: 条目缺少字段 {missing}")
                ok = False
            else:
                print(f"✅ {data_type}/: {len(json_files)} 个文件，"
                      f"样本 id={first['id']}, task={first['task']!r}")
        else:
            print(f"❌ {json_files[0]} 格式错误：期望非空列表")
            ok = False

    return ok


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ContextMind Benchmark 数据集下载与验证工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--dataset", "-d",
        choices=["risawoz", "sgd", "transfertod", "all"],
        default="all",
        help="要操作的数据集（默认: all）",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        default=True,
        help="验证数据集目录结构和文件格式（默认开启）",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="打印数据集下载说明",
    )
    parser.add_argument(
        "--data-root",
        default=None,
        help="数据集根目录（不指定则使用 resources/dataset/<DatasetName> 默认路径）",
    )
    args = parser.parse_args()

    datasets = ["risawoz", "sgd", "transfertod"] if args.dataset == "all" else [args.dataset]

    for ds in datasets:
        print(f"\n{'=' * 60}")
        print(f"  数据集: {ds.upper()}")
        print(f"{'=' * 60}")

        if args.info:
            if ds == "risawoz":
                print(RISAWOZ_README)
            elif ds == "sgd":
                print(SGD_README)
            elif ds == "transfertod":
                print(TRANSFERTOD_README)
            continue

        if ds == "risawoz":
            data_root = Path(args.data_root) if args.data_root else PROJECT_ROOT / "resources" / "data"
            verify_risawoz(data_root)
        elif ds == "sgd":
            data_root = Path(args.data_root) if args.data_root else PROJECT_ROOT / "resources" / "dataset" / "SGD"
            verify_sgd(data_root)
        elif ds == "transfertod":
            data_root = Path(args.data_root) if args.data_root else PROJECT_ROOT / "resources" / "dataset" / "TransferTOD"
            verify_transfertod(data_root)


if __name__ == "__main__":
    main()
