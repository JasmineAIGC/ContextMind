"""
SGD (Schema-Guided Dialogue) 数据集适配器

Google SGD 是标准多领域任务型对话基准数据集，支持 16,000+ 个对话，涵盖 20 个领域。

数据集目录结构:
  sgd_root/
    train/
      schema.json           # 服务 Schema 定义（意图+槽位）
      dialogues_001.json    # 对话文件（可多个）
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

SGD dialogue JSON 格式:
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
              },
              "slots": [...],
              "actions": [...]
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
      "slots": [
        {
          "name": "origin_city",
          "description": "City of departure",
          "is_categorical": false,
          "possible_values": []
        }
      ],
      "intents": [
        {
          "name": "SearchOneWayFlight",
          "description": "Search for one way flights.",
          "is_transactional": false,
          "required_slots": ["origin_city", "destination_city"],
          "optional_slots": {...},
          "result_slots": [...]
        }
      ]
    }
  ]

参考: https://github.com/google-research-datasets/dstc8-schema-guided-dialogue
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field

from benchmark.datasets.base import BaseDatasetAdapter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# SGD split 名称 → 目录映射
# ------------------------------------------------------------------
SGD_SPLIT_DIRS: Dict[str, str] = {
    "train": "train",
    "dev": "dev",
    "val": "dev",      # 别名，与其他数据集保持一致
    "test": "test",
}


# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------

@dataclass
class SGDSlot:
    """SGD 槽位定义。"""
    name: str
    description: str
    is_categorical: bool = False
    possible_values: List[str] = field(default_factory=list)


@dataclass
class SGDIntent:
    """SGD 意图定义。"""
    name: str
    description: str
    is_transactional: bool = False
    required_slots: List[str] = field(default_factory=list)
    optional_slots: Dict[str, str] = field(default_factory=dict)
    result_slots: List[str] = field(default_factory=list)


@dataclass
class SGDServiceSchema:
    """SGD 服务 Schema（含意图和槽位）。"""
    service_name: str
    description: str
    slots: List[SGDSlot] = field(default_factory=list)
    intents: List[SGDIntent] = field(default_factory=list)

    def get_slot_dict(self) -> Dict[str, SGDSlot]:
        """返回 slot_name → SGDSlot 的映射字典。"""
        return {s.name: s for s in self.slots}


@dataclass
class SGDDialogueTurn:
    """SGD 单个对话轮次（USER + SYSTEM 配对后的合并表示）。"""
    turn_id: int
    user_utterance: str
    system_utterance: str
    # 对话状态标注：slot_name → 值列表（SGD 允许多值）
    expected_slots: Dict[str, List[str]] = field(default_factory=dict)
    # 当前轮活跃意图
    active_intent: str = ""
    # 用户请求的槽位（"what" 类型请求）
    requested_slots: List[str] = field(default_factory=list)
    # 当前服务名称
    service: str = ""

    @property
    def expected_slots_flat(self) -> Dict[str, str]:
        """将多值槽位展平为单值（取第一个值），方便与 DST 评测接口对齐。"""
        return {k: v[0] if v else "" for k, v in self.expected_slots.items()}


@dataclass
class SGDDialogueInstance:
    """SGD 完整对话实例。"""
    dialogue_id: str
    services: List[str]
    turns: List[SGDDialogueTurn]

    @property
    def domain(self) -> str:
        """主服务名称（取第一个服务，与其他适配器接口保持一致）。"""
        return self.services[0] if self.services else "unknown"

    @property
    def primary_service(self) -> str:
        """主服务名称（同 domain）。"""
        return self.domain


# ------------------------------------------------------------------
# 适配器实现
# ------------------------------------------------------------------

class SGDAdapter(BaseDatasetAdapter):
    """SGD 数据集适配器。

    将 SGD 格式数据转换为标准化对话实例，供评测 runner 统一驱动。

    用法::

        adapter = SGDAdapter(data_root="./data/SGD")
        ids = adapter.list_dialogue_ids(split="test", service="Flights_4")
        dialogue = adapter.load_dialogue(ids[0], split="test")
        schema = adapter.get_service_schema("Flights_4", split="test")
    """

    def __init__(self, data_root: str = "./data/SGD") -> None:
        """初始化适配器。

        Args:
            data_root: SGD 数据集根目录（包含 train/dev/test 子目录）。
        """
        self.data_root = Path(data_root)
        # 对话缓存：split → {dialogue_id: SGDDialogueInstance}
        self._dialogue_cache: Dict[str, Dict[str, SGDDialogueInstance]] = {}
        # Schema 缓存：split → {service_name: SGDServiceSchema}
        self._schema_cache: Dict[str, Dict[str, SGDServiceSchema]] = {}
        # 对话 ID 列表缓存：split → [dialogue_id, ...]
        self._id_cache: Dict[str, List[str]] = {}

    # ------------------------------------------------------------------ #
    # BaseDatasetAdapter 接口实现
    # ------------------------------------------------------------------ #

    def load_dialogue(self, dialogue_id: str, split: str = "test") -> SGDDialogueInstance:
        """按 ID 加载 SGD 对话实例。

        Args:
            dialogue_id: SGD 格式对话 ID（如 ``"1_00001"``）。
            split: 数据集划分（``"train"`` / ``"dev"`` / ``"val"`` / ``"test"``）。

        Returns:
            SGDDialogueInstance 实例。

        Raises:
            KeyError: 对话 ID 不存在。
        """
        self._ensure_loaded(split)
        cache = self._dialogue_cache.get(split, {})
        if dialogue_id not in cache:
            raise KeyError(f"对话 ID '{dialogue_id}' 在 split='{split}' 中不存在")
        return cache[dialogue_id]

    def list_dialogue_ids(
        self,
        split: str = "test",
        service: Optional[str] = None,
        **kwargs: Any,
    ) -> List[str]:
        """列出指定 split 中的所有对话 ID。

        Args:
            split:   数据集划分。
            service: 可选，只返回含该服务的对话（如 ``"Flights_4"``）。
            **kwargs: 预留，暂未使用。

        Returns:
            对话 ID 字符串列表。
        """
        self._ensure_loaded(split)
        cache = self._dialogue_cache.get(split, {})
        if service:
            return [
                did for did, dlg in cache.items()
                if service in dlg.services
            ]
        return list(cache.keys())

    def get_domain(self, dialogue_id: str, split: str = "test") -> str:
        """返回对话的主服务名称（即 SGD 的 services[0]）。"""
        dialogue = self.load_dialogue(dialogue_id, split=split)
        return dialogue.domain

    # ------------------------------------------------------------------ #
    # SGD 专属接口
    # ------------------------------------------------------------------ #

    def get_service_schema(
        self, service_name: str, split: str = "test"
    ) -> Optional[SGDServiceSchema]:
        """获取指定服务的 Schema 定义。

        Args:
            service_name: 服务名称（如 ``"Flights_4"``）。
            split: 数据集划分。

        Returns:
            SGDServiceSchema 或 None（服务不存在时）。
        """
        self._ensure_schema_loaded(split)
        return self._schema_cache.get(split, {}).get(service_name)

    def list_services(self, split: str = "test") -> List[str]:
        """列出 split 中所有服务名称。"""
        self._ensure_schema_loaded(split)
        return list(self._schema_cache.get(split, {}).keys())

    def get_domain_schema(self, service_name: str, split: str = "test") -> Dict[str, Any]:
        """获取服务 Schema 的字典格式（与 TransferTOD/RiSAWOZ 适配器接口保持兼容）。

        返回格式::

            {
                "name": "Flights_4",
                "description": "...",
                "slots": {
                    "origin_city": {"description": "...", "is_categorical": False}
                },
                "intents": [
                    {"name": "SearchOneWayFlight", "description": "...", ...}
                ]
            }
        """
        schema = self.get_service_schema(service_name, split=split)
        if schema is None:
            logger.warning(f"服务 '{service_name}' 的 Schema 不存在 (split={split})，返回空 Schema")
            return {"name": service_name, "description": "", "slots": {}, "intents": []}

        slots_dict = {
            s.name: {
                "description": s.description,
                "is_categorical": s.is_categorical,
                "possible_values": s.possible_values,
            }
            for s in schema.slots
        }
        intents_list = [
            {
                "name": i.name,
                "description": i.description,
                "is_transactional": i.is_transactional,
                "required_slots": i.required_slots,
                "optional_slots": i.optional_slots,
                "result_slots": i.result_slots,
            }
            for i in schema.intents
        ]
        return {
            "name": schema.service_name,
            "description": schema.description,
            "slots": slots_dict,
            "intents": intents_list,
        }

    # ------------------------------------------------------------------ #
    # 私有辅助方法
    # ------------------------------------------------------------------ #

    def _get_split_dir(self, split: str) -> Path:
        """将 split 名称映射到实际目录。"""
        dir_name = SGD_SPLIT_DIRS.get(split, split)
        return self.data_root / dir_name

    def _ensure_loaded(self, split: str) -> None:
        """按需懒加载对话数据和 Schema。"""
        if split not in self._dialogue_cache:
            self._load_split(split)

    def _ensure_schema_loaded(self, split: str) -> None:
        """按需懒加载 Schema。"""
        if split not in self._schema_cache:
            self._load_schema(split)

    def _load_split(self, split: str) -> None:
        """加载整个 split 的对话数据和 Schema。"""
        self._load_schema(split)
        self._load_dialogues(split)

    def _load_schema(self, split: str) -> None:
        """从 schema.json 加载服务 Schema。"""
        split_dir = self._get_split_dir(split)
        schema_file = split_dir / "schema.json"
        if not schema_file.exists():
            logger.warning(f"SGD schema 文件不存在: {schema_file}")
            self._schema_cache[split] = {}
            return

        with open(schema_file, encoding="utf-8") as f:
            raw_schemas = json.load(f)

        schemas: Dict[str, SGDServiceSchema] = {}
        for raw in raw_schemas:
            service_name = raw["service_name"]
            slots = [
                SGDSlot(
                    name=s["name"],
                    description=s.get("description", ""),
                    is_categorical=s.get("is_categorical", False),
                    possible_values=s.get("possible_values", []),
                )
                for s in raw.get("slots", [])
            ]
            intents = [
                SGDIntent(
                    name=i["name"],
                    description=i.get("description", ""),
                    is_transactional=i.get("is_transactional", False),
                    required_slots=i.get("required_slots", []),
                    optional_slots=i.get("optional_slots", {}),
                    result_slots=i.get("result_slots", []),
                )
                for i in raw.get("intents", [])
            ]
            schemas[service_name] = SGDServiceSchema(
                service_name=service_name,
                description=raw.get("description", ""),
                slots=slots,
                intents=intents,
            )

        self._schema_cache[split] = schemas
        logger.info(f"[SGD] 已加载 {len(schemas)} 个服务 Schema (split={split})")

    def _load_dialogues(self, split: str) -> None:
        """从 dialogues_*.json 文件批量加载对话。"""
        split_dir = self._get_split_dir(split)
        if not split_dir.exists():
            logger.warning(f"SGD split 目录不存在: {split_dir}")
            self._dialogue_cache[split] = {}
            return

        dialogue_files = sorted(split_dir.glob("dialogues_*.json"))
        if not dialogue_files:
            logger.warning(f"SGD split '{split}' 目录中没有找到 dialogues_*.json 文件")
            self._dialogue_cache[split] = {}
            return

        cache: Dict[str, SGDDialogueInstance] = {}
        total = 0
        for file in dialogue_files:
            with open(file, encoding="utf-8") as f:
                raw_dialogues = json.load(f)
            for raw_dlg in raw_dialogues:
                instance = self._parse_dialogue(raw_dlg)
                cache[instance.dialogue_id] = instance
                total += 1

        self._dialogue_cache[split] = cache
        logger.info(f"[SGD] 已加载 {total} 个对话 (split={split}，共 {len(dialogue_files)} 个文件)")

    def _parse_dialogue(self, raw: Dict[str, Any]) -> SGDDialogueInstance:
        """将原始 SGD JSON 对话转换为 SGDDialogueInstance。

        SGD 的轮次格式为交替的 USER / SYSTEM 话语，需要配对为 (user, system) 轮次。
        """
        dialogue_id = raw["dialogue_id"]
        services = raw.get("services", [])
        raw_turns = raw.get("turns", [])

        parsed_turns: List[SGDDialogueTurn] = []
        turn_id = 0

        # SGD 轮次严格交替：USER → SYSTEM → USER → ...
        # 将相邻 USER+SYSTEM 配对，合并为一个 SGDDialogueTurn
        i = 0
        while i < len(raw_turns):
            user_turn = raw_turns[i] if raw_turns[i]["speaker"] == "USER" else None
            sys_turn = raw_turns[i + 1] if (i + 1 < len(raw_turns) and raw_turns[i + 1]["speaker"] == "SYSTEM") else None

            if user_turn is None:
                i += 1
                continue

            user_utt = user_turn.get("utterance", "")
            sys_utt = sys_turn.get("utterance", "") if sys_turn else ""

            # 从 USER 帧中提取对话状态
            expected_slots: Dict[str, List[str]] = {}
            active_intent = ""
            requested_slots: List[str] = []
            service_name = services[0] if services else ""

            for frame in user_turn.get("frames", []):
                state = frame.get("state", {})
                if state:
                    active_intent = state.get("active_intent", "")
                    requested_slots = state.get("requested_slots", [])
                    slot_values = state.get("slot_values", {})
                    for slot_name, values in slot_values.items():
                        if isinstance(values, list):
                            expected_slots[slot_name] = values
                        else:
                            expected_slots[slot_name] = [str(values)]
                if "service" in frame:
                    service_name = frame["service"]
                break  # 取第一个 frame

            parsed_turns.append(SGDDialogueTurn(
                turn_id=turn_id,
                user_utterance=user_utt,
                system_utterance=sys_utt,
                expected_slots=expected_slots,
                active_intent=active_intent,
                requested_slots=requested_slots,
                service=service_name,
            ))
            turn_id += 1
            i += 2 if sys_turn else 1

        return SGDDialogueInstance(
            dialogue_id=dialogue_id,
            services=services,
            turns=parsed_turns,
        )
