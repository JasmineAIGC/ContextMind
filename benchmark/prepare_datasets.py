#!/usr/bin/env python3
"""
Benchmark 数据集解析与准备工具

ContextMind benchmark 支持三个数据集：

  risawoz    https://github.com/terryqj0107/RiSAWOZ
  sgd        https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
  transfertod https://github.com/KongLongGeFDU/TransferTOD

典型工作流程：
  1. 从上方 GitHub 链接下载（clone 或 ZIP 下载）到本地任意目录。
  2. 运行本脚本的 --parse 模式进行解析，将数据整理到 benchmark 期望的标准路径。
  3. 运行 benchmark/run_benchmark.py 直接使用。

用法示例：
  # 解析 RiSAWOZ（--source 指向 clone 目录或 ZIP 文件）
  python benchmark/prepare_datasets.py --dataset risawoz \\
      --source /path/to/RiSAWOZ --parse

  # 解析 SGD
  python benchmark/prepare_datasets.py --dataset sgd \\
      --source /path/to/dstc8-schema-guided-dialogue --parse

  # 解析 TransferTOD
  python benchmark/prepare_datasets.py --dataset transfertod \\
      --source /path/to/TransferTOD --parse

  # 验证已解析结果
  python benchmark/prepare_datasets.py --dataset all --verify

  # 打印各数据集格式说明
  python benchmark/prepare_datasets.py --dataset sgd --info
"""

import argparse
import json
import logging
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据集格式说明文档
# ---------------------------------------------------------------------------

SGD_README = """
SGD (Schema-Guided Dialogue) 数据集格式说明
============================================

官方仓库: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

下载方式（二选一）:
  git clone https://github.com/google-research-datasets/dstc8-schema-guided-dialogue.git
  wget https://github.com/google-research-datasets/dstc8-schema-guided-dialogue/archive/refs/heads/master.zip

解析命令（将原始 clone 目录解析到标准路径）:
  python benchmark/prepare_datasets.py --dataset sgd \\
      --source /path/to/dstc8-schema-guided-dialogue --parse

标准目标目录 (resources/dataset/SGD/):
  train/
    schema.json
    dialogues_001.json  …  dialogues_NNN.json
  dev/
    schema.json
    dialogues_001.json  …
  test/
    schema.json
    dialogues_001.json  …

对话文件格式 (dialogues_*.json):
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

schema.json 格式:
  [
    {
      "service_name": "Flights_4",
      "description": "Book domestic flights.",
      "slots": [{"name": "origin_city", "description": "...", "is_categorical": false}],
      "intents": [{"name": "SearchOneWayFlight", "description": "...", ...}]
    }
  ]
"""

TRANSFERTOD_README = """
TransferTOD 数据集格式说明
===========================

官方仓库: https://github.com/KongLongGeFDU/TransferTOD

下载方式:
  git clone https://github.com/KongLongGeFDU/TransferTOD.git
  # 或从 Releases / ZIP 下载

解析命令:
  python benchmark/prepare_datasets.py --dataset transfertod \\
      --source /path/to/TransferTOD --parse

标准目标目录 (resources/dataset/TransferTOD/):
  data/
    raw_data/
      clean/
        1-hotel/
          hotel_clean_1.json
          hotel_clean_2.json
          ...
        2-restaurant/
          restaurant_clean_1.json
          ...
        ...（共 24 个领域子目录）
      noise/
        1-hotel/
          hotel_noise_1.json
          ...
        ...

对话文件格式（每个 JSON 包含一个列表）:
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
          "origin_slots": {"姓名": null, ...},
          "new_slots":    {"姓名": "张三", ...},
          "conversations": [
            {"from": "user",      "value": "我叫张三"},
            {"from": "assistant", "value": "好的，请问入住日期？"}
          ]
        }
      ]
    }
  ]

槽位变化提取规则:
  每轮 expected_slots = new_slots 中比 origin_slots 新增或变化的非 null 槽位。
"""

RISAWOZ_README = """
RiSAWOZ 数据集格式说明
=======================

官方仓库: https://github.com/terryqj0107/RiSAWOZ

内置测试集（600 条）已在:
  resources/data/risawoz_test.json    ← 开箱即用，无需下载

下载完整数据集（训练集 10000 / 验证集 600 条）:
  git clone https://github.com/terryqj0107/RiSAWOZ.git

解析命令:
  python benchmark/prepare_datasets.py --dataset risawoz \\
      --source /path/to/RiSAWOZ --parse

解析后目标文件:
  resources/data/
    risawoz_train.json   （10000 条）
    risawoz_val.json     （600 条）
    risawoz_test.json    （600 条，已内置）

RiSAWOZ GitHub 仓库实际结构（git clone 后）:
  RiSAWOZ/
    RiSAWOZ-data/
      source-data.zip          ← 完整原始标注数据（推荐）
      task2-data-DST.zip       ← DST 专用格式
      dataset_split_ids_dict.json
      ...

解析器会自动提取 RiSAWOZ-data/ 内的嵌套 ZIP，无需手动解压。

RiSAWOZ 源数据支持两种格式，适配器自动识别：

格式 A (source-data，推荐):
  单条对话结构:
    {
      "dialogue_id": "attraction_goal_1###123",
      "domains": ["旅游景点"],
      "dialogue": [
        {
          "turn_id": 0,
          "user_utterance": "用户话语...",
          "system_utterance": "系统话语...",
          "belief_state": {
            "inform slot-values": {"旅游景点-景点类型": "水乡古镇"},
            "turn_inform":        {"旅游景点-景点类型": "水乡古镇"},
            "turn request":       []
          },
          "user_actions": [["Inform", "旅游景点", "景点类型", "水乡古镇"]]
        },
        ...
      ]
    }

格式 B (task2-data-DST):
  单条对话结构:
    {
      "dialogue_idx": "attraction_goal_1###123",
      "domains": ["旅游景点"],
      "dialogue": [
        {
          "turn_idx": 0,
          "transcript": "用户话语（空格分词）...",
          "system_transcript": "系统话语...",
          "belief_state": [
            {"slots": [["旅游景点-景点类型", "水乡 古镇"]], "act": "inform"}
          ],
          "turn_label": [["旅游景点-景点类型", "水乡 古镇"]],
          "user_acts": [["Inform", "旅游景点", "景点类型", "水乡 古镇"]]
        },
        ...
      ]
    }

适配器 (RiSAWOZAdapter) 自动处理两种格式，无需手动转换。
"""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _extract_zip_if_needed(source: Path, work_dir: Path) -> Path:
    """如果 source 是 ZIP 文件，解压到 work_dir 并返回解压后的根目录；否则直接返回 source。"""
    if source.suffix.lower() != ".zip":
        return source
    logger.info(f"解压 ZIP 文件: {source} → {work_dir}")
    work_dir.mkdir(parents=True, exist_ok=True)
    # Guard against zip slip: validate all member paths stay within work_dir
    with zipfile.ZipFile(source, "r") as zf:
        for member in zf.infolist():
            member_path = (work_dir / member.filename).resolve()
            if not str(member_path).startswith(str(work_dir.resolve())):
                raise ValueError(f"ZIP 包含不安全路径: {member.filename}")
        zf.extractall(work_dir)
    # GitHub 下载的 ZIP 通常有一个顶层包装目录，如 repo-master/
    children = [c for c in work_dir.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return work_dir


def _copy_tree(src: Path, dst: Path) -> None:
    """将 src 目录树拷贝到 dst（若 dst 已存在则覆盖）。"""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _copy_file(src: Path, dst: Path) -> None:
    """拷贝单个文件，自动创建目标目录。"""
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    logger.info(f"  {src.name} → {dst}")


# ---------------------------------------------------------------------------
# RiSAWOZ：解析与验证
# ---------------------------------------------------------------------------

# 已知的 source-data 子目录名及其 split → 文件名映射
_RISAWOZ_SUBDIR_MAPPINGS = [
    # (subdir_name, split_to_filename_dict)
    ("source-data", {
        "train": "all_train10000.json",
        "val":   "all_dev600.json",
        "test":  "all_test600_new.json",
    }),
    ("task2-data-DST", {
        "train": "dst_all_train10000.json",
        "val":   "dst_all_dev600.json",
        "test":  "dst_all_test600_new.json",
    }),
    ("task3-data-E2E-Context-to-text", {
        "train": "train.json",
        "val":   "val.json",
        "test":  "test.json",
    }),
    ("task5-data-Unified-generative-ellipsis-and-coreference-resolution", {
        "train": "all_train10000.json",
        "val":   "all_dev600.json",
        "test":  "all_test600_new.json",
    }),
]

# 输出文件命名约定
_RISAWOZ_OUTPUT_NAMES = {
    "train": "risawoz_train.json",
    "val":   "risawoz_val.json",
    "test":  "risawoz_test.json",
}


def _extract_risawoz_nested_zips(source: Path, tmp_dir: Path) -> Path:
    """
    RiSAWOZ GitHub 仓库将数据以 ZIP 形式存放在 RiSAWOZ-data/ 子目录中：
      RiSAWOZ-data/source-data.zip
      RiSAWOZ-data/task2-data-DST.zip
      等

    本函数检测 source/RiSAWOZ-data/ 是否存在嵌套 ZIP，若存在则提取到
    tmp_dir/risawoz_nested/ 并返回该目录路径，否则返回原始 source。
    """
    risawoz_data = source / "RiSAWOZ-data"
    if not risawoz_data.is_dir():
        return source

    # 按优先级提取已知 ZIP 文件（source-data 信息最完整，优先提取）
    zip_candidates = [
        "source-data.zip",
        "task2-data-DST.zip",
        "task3-data-E2E-Context-to-text.zip",
        "task5-data-Unified-generative-ellipsis-and-coreference-resolution.zip",
    ]

    extract_parent = tmp_dir / "risawoz_nested"
    extract_parent.mkdir(parents=True, exist_ok=True)

    extracted_any = False
    for zip_name in zip_candidates:
        zip_path = risawoz_data / zip_name
        if not zip_path.exists():
            continue
        logger.info(f"  发现嵌套 ZIP: {zip_name}，正在解压…")
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                for member in zf.infolist():
                    member_path = (extract_parent / member.filename).resolve()
                    if not str(member_path).startswith(str(extract_parent.resolve())):
                        raise ValueError(f"ZIP 包含不安全路径: {member.filename}")
                    zf.extract(member, extract_parent)
            logger.info(f"  已解压: {zip_name}")
            extracted_any = True
        except Exception as exc:
            logger.warning(f"  解压 {zip_name} 失败: {exc}")

    return extract_parent if extracted_any else source


def _find_risawoz_data_dir(root: Path):
    """
    在 root 下自动检测 RiSAWOZ 数据子目录。

    返回 (subdir_path, split_mapping) 或 (None, None)。
    优先选择包含 train/val/test 三个文件的子目录；
    其次选择只有部分文件的子目录；
    最后把 root 本身当作数据目录（文件直接在 root 下）。

    同时检查 root/RiSAWOZ-data/ 内是否有已解压的已知子目录（适配 GitHub
    仓库中嵌套 ZIP 已被手动解压的情形）。
    """
    # 搜索路径：先在 root 下，再在 root/RiSAWOZ-data/ 下（手动解压场景）
    search_roots = [root]
    if (root / "RiSAWOZ-data").is_dir():
        search_roots.append(root / "RiSAWOZ-data")

    for search_root in search_roots:
        for subdir_name, mapping in _RISAWOZ_SUBDIR_MAPPINGS:
            cand = search_root / subdir_name
            if cand.is_dir():
                found = {sp: fn for sp, fn in mapping.items() if (cand / fn).exists()}
                if found:
                    rel = cand.relative_to(root) if search_root != root else Path(subdir_name)
                    logger.info(f"  检测到子目录: {rel}  (含 {list(found.keys())})")
                    return cand, mapping

    # 未找到已知子目录时，检查 root 本身是否包含 JSON 文件
    json_files = list(root.glob("*.json"))
    if json_files:
        # 尝试识别已知文件名
        for _, mapping in _RISAWOZ_SUBDIR_MAPPINGS:
            found = {sp: fn for sp, fn in mapping.items() if (root / fn).exists()}
            if found:
                logger.info(f"  在根目录检测到 RiSAWOZ 文件 (含 {list(found.keys())})")
                return root, mapping

    return None, None


def parse_risawoz(source: Path, target_dir: Path) -> bool:
    """
    解析 RiSAWOZ 数据集，将 train/val/test 文件整理到 target_dir。

    source 可以是：
      - git clone 产生的目录（RiSAWOZ-data/ 下含嵌套 ZIP：source-data.zip 等）
      - 直接是数据子目录（包含 all_train10000.json 等文件）
      - ZIP 文件（外层 GitHub ZIP 或内层数据 ZIP）

    目标文件（写入 target_dir）:
      risawoz_train.json
      risawoz_val.json
      risawoz_test.json
    """
    with tempfile.TemporaryDirectory(prefix="risawoz_extract_") as tmp_str:
        tmp_dir = Path(tmp_str)
        source = _extract_zip_if_needed(source, tmp_dir)
        if not source.exists():
            logger.error(f"源路径不存在: {source}")
            return False

        # RiSAWOZ GitHub 仓库将数据打包为 RiSAWOZ-data/ 内的嵌套 ZIP
        # 先尝试提取这些嵌套 ZIP，再继续检索数据目录
        source = _extract_risawoz_nested_zips(source, tmp_dir)

        data_dir, mapping = _find_risawoz_data_dir(source)
        if data_dir is None:
            logger.error(
                f"在 {source} 下未找到 RiSAWOZ 数据文件。\n"
                f"请确认 source 目录为 RiSAWOZ repo 根目录，或其中某个数据子目录。\n"
                f"支持的子目录: {[n for n, _ in _RISAWOZ_SUBDIR_MAPPINGS]}"
            )
            return False

        target_dir.mkdir(parents=True, exist_ok=True)
        copied = []
        for split, src_name in mapping.items():
            src_file = data_dir / src_name
            if not src_file.exists():
                logger.warning(f"  {split} 文件不存在，跳过: {src_file}")
                continue
            dst_file = target_dir / _RISAWOZ_OUTPUT_NAMES[split]
            # 如果目标文件已存在且大小相同则跳过
            if dst_file.exists() and dst_file.stat().st_size == src_file.stat().st_size:
                logger.info(f"  {dst_file.name} 已存在，跳过")
                copied.append(split)
                continue
            _copy_file(src_file, dst_file)
            copied.append(split)

    if copied:
        logger.info(f"✅ RiSAWOZ 解析完成，已写入 {len(copied)} 个分片: {copied}")
        logger.info(f"   目标目录: {target_dir}")
        return True
    logger.error("未找到任何可用的 RiSAWOZ 数据文件。")
    return False


def verify_risawoz(data_root: Path) -> bool:
    """验证 RiSAWOZ 数据目录完整性。"""
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
            # 也接受 dialogue_id 代替 dialogue_idx
            if "dialogue_id" in first:
                missing.discard("dialogue_idx")
            if missing:
                print(f"❌ 对话条目缺少必需字段: {missing}")
                return False
        print(f"✅ risawoz_test.json: {len(data)} 条对话，格式验证通过")
        print(f"   文件: {test_file}")
        print(f"   样本: id={first.get('dialogue_idx', first.get('dialogue_id', '?'))!r}, "
              f"domains={first.get('domains', [])}, turns={len(first['dialogue'])}")

        # 检查 train/val（可选）
        for split, fname in [("train", "risawoz_train.json"), ("val", "risawoz_val.json")]:
            fp = data_root / fname
            if fp.exists():
                with open(fp, encoding="utf-8") as f:
                    d = json.load(f)
                print(f"✅ {fname}: {len(d)} 条对话")
            else:
                print(f"ℹ️  {fname} 不存在（可选；需要时运行 --parse 生成）")
        return True
    except json.JSONDecodeError as e:
        print(f"❌ JSON 解析错误: {e}")
        return False


# ---------------------------------------------------------------------------
# SGD：解析与验证
# ---------------------------------------------------------------------------

def _find_sgd_data_dir(root: Path) -> Optional[Path]:
    """
    在 root 下找到包含 train/dev/test 子目录的 SGD 数据根目录。

    处理以下情况：
      - root 本身就是数据根（直接有 train/ dev/ test/）
      - root/dstc8-schema-guided-dialogue/ 或 root/dstc8-schema-guided-dialogue-master/ 等
    """
    # 直接检查 root
    if (root / "train").is_dir() and (root / "test").is_dir():
        return root
    # 检查一层子目录
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "train").is_dir() and (child / "test").is_dir():
            return child
    return None


def parse_sgd(source: Path, target_dir: Path) -> bool:
    """
    解析 SGD 数据集，将 train/dev/test 目录整理到 target_dir。

    source 可以是：
      - git clone 目录（dstc8-schema-guided-dialogue/，包含 train/dev/test 子目录）
      - ZIP 文件
    """
    with tempfile.TemporaryDirectory(prefix="sgd_extract_") as tmp_str:
        tmp_dir = Path(tmp_str)
        source = _extract_zip_if_needed(source, tmp_dir)
        if not source.exists():
            logger.error(f"源路径不存在: {source}")
            return False

        data_dir = _find_sgd_data_dir(source)
        if data_dir is None:
            logger.error(
                f"在 {source} 下未找到 SGD train/dev/test 目录。\n"
                f"请确认 source 指向 dstc8-schema-guided-dialogue 目录。"
            )
            return False

        logger.info(f"  SGD 数据根目录: {data_dir}")

        # 复制 train/dev/test 子目录
        target_dir.mkdir(parents=True, exist_ok=True)
        for split_dir_name in ("train", "dev", "test"):
            src_split = data_dir / split_dir_name
            if not src_split.exists():
                logger.warning(f"  {split_dir_name}/ 不存在，跳过")
                continue
            dst_split = target_dir / split_dir_name
            logger.info(f"  复制 {split_dir_name}/ ...")
            _copy_tree(src_split, dst_split)
            schema_ok = (dst_split / "schema.json").exists()
            dialogue_files = list(dst_split.glob("dialogues_*.json"))
            logger.info(f"    schema.json: {'✓' if schema_ok else '✗'}, "
                        f"dialogue files: {len(dialogue_files)}")

    logger.info(f"✅ SGD 解析完成，目标目录: {target_dir}")
    return True


def verify_sgd(data_root: Path) -> bool:
    """验证 SGD 数据集目录结构。"""
    if not data_root.exists():
        print(f"❌ SGD 数据目录不存在: {data_root}")
        print("   请先运行: python benchmark/prepare_datasets.py --dataset sgd --source <path> --parse")
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


# ---------------------------------------------------------------------------
# TransferTOD：解析与验证
# ---------------------------------------------------------------------------

def _find_transfertod_raw_data(root: Path) -> Optional[Path]:
    """
    在 root 下找到 TransferTOD 的 raw_data 目录。

    处理以下情况：
      - root/data/raw_data/
      - root/raw_data/
      - root 本身就是 raw_data（包含 clean/ noise/ 子目录）
    """
    # root 本身包含 clean 或 noise
    if (root / "clean").is_dir() or (root / "noise").is_dir():
        return root
    # root/data/raw_data/
    cand = root / "data" / "raw_data"
    if cand.is_dir():
        return cand
    # root/raw_data/
    cand = root / "raw_data"
    if cand.is_dir():
        return cand
    # 在子目录中递归查找
    for child in sorted(root.iterdir()):
        if child.is_dir() and not child.name.startswith("."):
            cand = child / "data" / "raw_data"
            if cand.is_dir():
                return cand
            if (child / "clean").is_dir():
                return child
    return None


def parse_transfertod(source: Path, target_dir: Path) -> bool:
    """
    解析 TransferTOD 数据集，将 raw_data/clean|noise 整理到 target_dir。

    source 可以是：
      - git clone 目录（TransferTOD/，包含 data/raw_data/clean 等）
      - ZIP 文件
    """
    with tempfile.TemporaryDirectory(prefix="transfertod_extract_") as tmp_str:
        tmp_dir = Path(tmp_str)
        source = _extract_zip_if_needed(source, tmp_dir)
        if not source.exists():
            logger.error(f"源路径不存在: {source}")
            return False

        raw_data_dir = _find_transfertod_raw_data(source)
        if raw_data_dir is None:
            logger.error(
                f"在 {source} 下未找到 TransferTOD raw_data 目录。\n"
                f"请确认 source 指向 TransferTOD repo 根目录，或其 data/ 子目录。"
            )
            return False

        logger.info(f"  TransferTOD raw_data 目录: {raw_data_dir}")

        target_raw_data = target_dir / "data" / "raw_data"
        target_raw_data.mkdir(parents=True, exist_ok=True)

        ok = False
        for data_type in ("clean", "noise"):
            src_type_dir = raw_data_dir / data_type
            if not src_type_dir.exists():
                logger.warning(f"  {data_type}/ 不存在，跳过")
                continue
            dst_type_dir = target_raw_data / data_type
            logger.info(f"  复制 {data_type}/ ...")
            _copy_tree(src_type_dir, dst_type_dir)
            domain_dirs = [d for d in dst_type_dir.iterdir() if d.is_dir()]
            json_files = list(dst_type_dir.rglob("*.json"))
            logger.info(f"    域目录数: {len(domain_dirs)}, JSON 文件数: {len(json_files)}")
            ok = True

    if ok:
        logger.info(f"✅ TransferTOD 解析完成，目标目录: {target_dir}")
    else:
        logger.error("未找到任何 clean/noise 子目录。")
    return ok


def verify_transfertod(data_root: Path) -> bool:
    """验证 TransferTOD 数据集目录结构。"""
    raw_data_path = data_root / "data" / "raw_data"
    if not raw_data_path.exists():
        print(f"❌ TransferTOD 数据目录不存在: {raw_data_path}")
        print("   请先运行: python benchmark/prepare_datasets.py --dataset transfertod --source <path> --parse")
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
                # 验证 content 中的轮次格式
                first_turn = first["content"][0] if first.get("content") else {}
                turn_keys = set(first_turn.keys())
                expected_turn_keys = {"Turn", "origin_slots", "new_slots", "conversations"}
                missing_turn = expected_turn_keys - turn_keys
                if missing_turn:
                    print(f"⚠️  {json_files[0]}: 轮次条目缺少字段 {missing_turn}")
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
        description="ContextMind Benchmark 数据集解析与验证工具",
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
        "--parse",
        action="store_true",
        help=(
            "解析模式：读取 --source 指定的原始下载目录，"
            "自动检测结构并整理到标准目标路径。"
        ),
    )
    parser.add_argument(
        "--source", "-s",
        default=None,
        help=(
            "原始数据源路径（--parse 时必须提供）。"
            "可以是 git clone 目录或 ZIP 文件路径。"
        ),
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="验证已整理的数据集目录结构和文件格式。",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="打印数据集格式说明。",
    )
    parser.add_argument(
        "--output", "--data-root",
        default=None,
        dest="output",
        help=(
            "目标输出目录（不指定则使用默认路径）。"
            "risawoz 默认: resources/data/，"
            "sgd/transfertod 默认: resources/dataset/<DatasetName>/。"
        ),
    )
    args = parser.parse_args()

    # 默认目标路径
    default_targets = {
        "risawoz":     PROJECT_ROOT / "resources" / "data",
        "sgd":         PROJECT_ROOT / "resources" / "dataset" / "SGD",
        "transfertod": PROJECT_ROOT / "resources" / "dataset" / "TransferTOD",
    }

    # 如果既没有 --parse 也没有 --verify 也没有 --info，则默认执行 --verify
    if not args.parse and not args.verify and not args.info:
        args.verify = True

    datasets = ["risawoz", "sgd", "transfertod"] if args.dataset == "all" else [args.dataset]

    all_ok = True
    for ds in datasets:
        print(f"\n{'=' * 60}")
        print(f"  数据集: {ds.upper()}")
        print(f"{'=' * 60}")

        target = Path(args.output) if args.output else default_targets[ds]

        if args.info:
            if ds == "risawoz":
                print(RISAWOZ_README)
            elif ds == "sgd":
                print(SGD_README)
            elif ds == "transfertod":
                print(TRANSFERTOD_README)
            continue

        if args.parse:
            if not args.source:
                print("❌ --parse 模式必须通过 --source 指定原始数据路径。")
                all_ok = False
                continue
            source = Path(args.source)
            print(f"解析模式  source={source}  →  target={target}")
            if ds == "risawoz":
                ok = parse_risawoz(source, target)
            elif ds == "sgd":
                ok = parse_sgd(source, target)
            elif ds == "transfertod":
                ok = parse_transfertod(source, target)
            else:
                ok = False
            if not ok:
                all_ok = False
            # 解析完后自动验证
            print("\n--- 验证解析结果 ---")

        if args.verify or args.parse:
            if ds == "risawoz":
                ok = verify_risawoz(target)
            elif ds == "sgd":
                ok = verify_sgd(target)
            elif ds == "transfertod":
                ok = verify_transfertod(target)
            else:
                ok = False
            if not ok:
                all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
