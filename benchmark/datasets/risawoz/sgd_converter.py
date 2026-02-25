"""
RiSAWOZ → SGD 格式转换器

将中文 RiSAWOZ 数据集转换为 Google SGD（Schema-Guided Dialogue）格式，
以便使用 pyTOD 算法对该数据集进行训练和测试。

SGD 格式参考:
  https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

RiSAWOZ 格式参考:
  https://github.com/terryqj0107/RiSAWOZ

格式映射:
  RiSAWOZ dialogue → SGD dialogue
  RiSAWOZ domain   → SGD service_name (e.g. "景点_1")
  RiSAWOZ turn     → 2 SGD turns (USER turn + SYSTEM turn)
  RiSAWOZ belief_state [{domain, slot, value}]
    → SGD state.slot_values {slot_name: [value]}
  RiSAWOZ user_acts [[intent, domain, slot, value]]
    → SGD actions [{act, slot, values, canonical_values}]
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# RiSAWOZ intent → SGD dialogue act mapping
# ------------------------------------------------------------------
_ACT_MAP: Dict[str, str] = {
    "Inform": "INFORM",
    "Request": "REQUEST",
    "Select": "SELECT",
    "Confirm": "CONFIRM",
    "NoOffer": "NOOFFER",
    "OfferBook": "OFFERBOOK",
    "OfferBooked": "OFFERBOOKED",
    "Recommend": "RECOMMEND",
    "Greeting": "INFORM",      # no direct SGD equivalent → INFORM
    "Bye": "INFORM",
    "Thank": "INFORM",
    "General": "INFORM",
    "GeneralAct": "INFORM",
}


def _map_act(risawoz_intent: str) -> str:
    """Map a RiSAWOZ intent string to the corresponding SGD act string."""
    return _ACT_MAP.get(risawoz_intent, risawoz_intent.upper())


# ------------------------------------------------------------------
# Schema builder
# ------------------------------------------------------------------

class _SchemaBuilder:
    """Accumulates slot information per domain while scanning dialogues."""

    def __init__(self) -> None:
        # domain → slot_name → set of seen values
        self._slots: Dict[str, Dict[str, Set[str]]] = defaultdict(lambda: defaultdict(set))
        # domain → set of intents seen
        self._intents: Dict[str, Set[str]] = defaultdict(set)

    def ingest_dialogue(self, dialogue_data: Dict) -> None:
        """Extract slot/intent information from a single raw RiSAWOZ dialogue."""
        for turn in dialogue_data.get("dialogue", []):
            # belief_state can be in two formats (see adapter.py for details)
            belief_state = turn.get("belief_state", [])
            for belief in belief_state:
                if not isinstance(belief, dict):
                    continue
                if "domain" in belief and "slot" in belief:
                    # Format: {"domain": "景点", "slot": "名称", "value": "故宫"}
                    domain = belief["domain"]
                    slot = belief["slot"]
                    value = belief.get("value", "")
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]  # ensure key exists
                elif "slots" in belief:
                    # Format: {"slots": [["景点-名称", "故宫"], ...], "act": "..."}
                    for slot_pair in belief.get("slots", []):
                        if isinstance(slot_pair, list) and len(slot_pair) >= 2:
                            slot_key = slot_pair[0]  # "domain-slot"
                            value = str(slot_pair[1]) if slot_pair[1] else ""
                            if "-" in slot_key:
                                domain, slot = slot_key.split("-", 1)
                                if domain and slot:
                                    if value:
                                        self._slots[domain][slot].add(value)
                                    else:
                                        self._slots[domain][slot]

            # user_acts: [[intent, domain, slot, value], ...]
            for act in turn.get("user_acts", []):
                if isinstance(act, list) and len(act) >= 2:
                    intent, domain = act[0], act[1]
                    if domain:
                        self._intents[domain].add(intent)

    def build_schema(self) -> List[Dict]:
        """Return a list of SGD-style service schema objects."""
        schemas: List[Dict] = []
        for domain in sorted(self._slots.keys()):
            service_name = f"{domain}_1"
            slots_info = self._slots[domain]

            sgd_slots = []
            for slot_name in sorted(slots_info.keys()):
                values = sorted(slots_info[slot_name])
                # Treat as categorical if the cardinality is small and values exist
                is_categorical = 0 < len(values) <= 20
                sgd_slots.append({
                    "name": slot_name,
                    "description": slot_name,
                    "is_categorical": is_categorical,
                    "possible_values": values if is_categorical else [],
                })

            # Build intents: one "查询" (query) intent per domain as a sensible default
            seen_intents = sorted(self._intents.get(domain, set()))
            # Always include a generic search intent so the schema is well-formed
            if not seen_intents:
                seen_intents = ["查询"]

            sgd_intents = []
            for intent in seen_intents:
                sgd_intents.append({
                    "name": intent,
                    "description": f"{domain}领域的{intent}意图",
                    "required_slots": [],
                    "optional_slots": {},
                    "result_slots": [],
                })

            schemas.append({
                "service_name": service_name,
                "description": f"{domain}领域对话服务",
                "slots": sgd_slots,
                "intents": sgd_intents,
            })

        return schemas


# ------------------------------------------------------------------
# Main converter
# ------------------------------------------------------------------

class RiSAWOZToSGDConverter:
    """
    Converts a RiSAWOZ split (train / val / test) into SGD format.

    Output directory layout (mirrors SGD):
        <output_dir>/
            schema.json          # all service schemas for this split
            dialogues_001.json   # dialogue files (≤1000 per file by default)
            dialogues_002.json
            ...

    Usage::

        converter = RiSAWOZToSGDConverter(data_root="./data/RiSAWOZ")
        converter.convert(split="train", output_dir="./data/RiSAWOZ_SGD/train")
    """

    DIALOGUES_PER_FILE = 1000

    def __init__(
        self,
        data_root: str = "./data/RiSAWOZ",
        file_mapping: Optional[Dict[str, str]] = None,
    ) -> None:
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.data_root = Path(data_root)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def convert(
        self,
        split: str = "val",
        output_dir: Optional[str] = None,
        dialogues_per_file: int = DIALOGUES_PER_FILE,
    ) -> Dict[str, Any]:
        """
        Convert one split and write SGD files to *output_dir*.

        Args:
            split: "train", "val", or "test"
            output_dir: destination directory; defaults to
                        ``<data_root>_SGD/<split>``
            dialogues_per_file: max dialogues per ``dialogues_NNN.json``

        Returns:
            A summary dict with counts of converted dialogues and turns.
        """
        if output_dir is None:
            output_dir = str(self.data_root.parent / f"{self.data_root.name}_SGD" / split)

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        logger.info(f"[RiSAWOZ→SGD] 加载 {split} 数据集 ...")
        raw_data = self.adapter._load_data_file(split)
        dialogues_raw = raw_data if isinstance(raw_data, list) else list(raw_data.values())

        # ── Pass 1: build schema ──────────────────────────────────────
        builder = _SchemaBuilder()
        for dialogue_data in dialogues_raw:
            if isinstance(dialogue_data, dict):
                builder.ingest_dialogue(dialogue_data)
        schema = builder.build_schema()

        schema_path = out_path / "schema.json"
        schema_path.write_text(
            json.dumps(schema, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(f"[RiSAWOZ→SGD] 写入 schema.json ({len(schema)} 个服务)")

        # ── Pass 2: convert dialogues ────────────────────────────────
        sgd_dialogues: List[Dict] = []
        total_turns = 0

        for idx, dialogue_data in enumerate(dialogues_raw):
            if not isinstance(dialogue_data, dict):
                continue
            try:
                sgd_dialogue = self._convert_dialogue(dialogue_data, idx)
                sgd_dialogues.append(sgd_dialogue)
                total_turns += len(sgd_dialogue["turns"])
            except Exception as exc:
                logger.warning(f"[RiSAWOZ→SGD] 跳过对话 {idx}: {exc}")

        # ── Write dialogue files ─────────────────────────────────────
        file_count = 0
        for start in range(0, max(len(sgd_dialogues), 1), dialogues_per_file):
            chunk = sgd_dialogues[start : start + dialogues_per_file]
            file_count += 1
            file_name = f"dialogues_{file_count:03d}.json"
            (out_path / file_name).write_text(
                json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        summary = {
            "split": split,
            "output_dir": str(out_path),
            "dialogues": len(sgd_dialogues),
            "turns": total_turns,
            "services": len(schema),
            "dialogue_files": file_count,
        }
        logger.info(
            f"[RiSAWOZ→SGD] 完成 {split}: "
            f"{summary['dialogues']} 对话, {summary['turns']} 轮次, "
            f"{summary['services']} 服务, {summary['dialogue_files']} 文件"
        )
        return summary

    # ------------------------------------------------------------------
    # Internal conversion helpers
    # ------------------------------------------------------------------

    def _convert_dialogue(self, dialogue_data: Dict, idx: int) -> Dict:
        """Convert one RiSAWOZ dialogue dict to SGD format."""
        # Dialogue ID
        dialogue_id = (
            dialogue_data.get("dialogue_id")
            or dialogue_data.get("dialogue_idx")
            or str(idx)
        )

        # Collect all services (domains) referenced in this dialogue
        services: Set[str] = set()
        for turn in dialogue_data.get("dialogue", []):
            for belief in turn.get("belief_state", []):
                domain = self._extract_domain_from_belief(belief)
                if domain:
                    services.add(f"{domain}_1")

        services_list = sorted(services) if services else ["通用_1"]

        # Convert turns: one RiSAWOZ turn → USER turn + SYSTEM turn
        sgd_turns: List[Dict] = []
        cumulative_slots: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
        # cumulative_slots[service_name][slot_name] = [value]

        for turn_data in dialogue_data.get("dialogue", []):
            if not isinstance(turn_data, dict):
                continue

            user_utt = (
                turn_data.get("transcript")
                or turn_data.get("user_utterance")
                or ""
            )
            sys_utt = (
                turn_data.get("system_transcript")
                or turn_data.get("system_utterance")
                or ""
            )

            # Parse this turn's belief_state increment
            turn_slot_delta = self._parse_belief_state(turn_data.get("belief_state", []))
            # Update cumulative state
            for svc, slots in turn_slot_delta.items():
                if svc not in cumulative_slots:
                    cumulative_slots[svc] = {}
                cumulative_slots[svc].update(slots)

            # Parse user actions
            user_actions = self._parse_user_acts(
                turn_data.get("user_acts", []), cumulative_slots
            )

            # Determine active intent from user_acts
            active_intent = self._get_active_intent(turn_data.get("user_acts", []))

            # Build frames for USER turn
            user_frames = self._build_user_frames(
                cumulative_slots, user_actions, active_intent, services_list
            )

            sgd_turns.append({
                "turn_id": str(len(sgd_turns)),
                "speaker": "USER",
                "utterance": user_utt,
                "frames": user_frames,
            })

            # Build frames for SYSTEM turn
            system_frames = self._build_system_frames(cumulative_slots, services_list)

            sgd_turns.append({
                "turn_id": str(len(sgd_turns)),
                "speaker": "SYSTEM",
                "utterance": sys_utt,
                "frames": system_frames,
            })

        return {
            "dialogue_id": str(dialogue_id),
            "services": services_list,
            "turns": sgd_turns,
        }

    # ------ belief_state parsing ------

    def _extract_domain_from_belief(self, belief: Any) -> Optional[str]:
        """Return the domain string from a single belief_state entry."""
        if not isinstance(belief, dict):
            return None
        if "domain" in belief:
            return belief["domain"]
        if "slots" in belief:
            for pair in belief["slots"]:
                if isinstance(pair, list) and len(pair) >= 1:
                    key = pair[0]
                    if isinstance(key, str) and "-" in key:
                        return key.split("-", 1)[0]
        return None

    def _parse_belief_state(
        self, belief_state: List
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Parse a RiSAWOZ belief_state list into:
            {service_name: {slot_name: [value]}}
        """
        result: Dict[str, Dict[str, List[str]]] = defaultdict(dict)

        for belief in belief_state:
            if not isinstance(belief, dict):
                continue

            if "domain" in belief and "slot" in belief:
                # Format: {"domain": "景点", "slot": "名称", "value": "故宫"}
                domain = belief["domain"]
                slot = belief["slot"]
                value = str(belief.get("value", "")) if belief.get("value") else ""
                if domain and slot and value:
                    svc = f"{domain}_1"
                    result[svc][slot] = [value]

            elif "slots" in belief:
                # Format: {"slots": [["景点-名称", "故宫"], ...], "act": "..."}
                for pair in belief.get("slots", []):
                    if isinstance(pair, list) and len(pair) >= 2:
                        key = pair[0]
                        value = str(pair[1]) if pair[1] else ""
                        if isinstance(key, str) and "-" in key and value:
                            domain, slot = key.split("-", 1)
                            svc = f"{domain}_1"
                            result[svc][slot] = [value]

        return dict(result)

    # ------ user_acts parsing ------

    def _get_active_intent(self, user_acts: List) -> str:
        """Derive the active intent from the first user act with an intent."""
        for act in user_acts:
            if isinstance(act, list) and len(act) >= 1 and act[0]:
                return act[0]
        return "NONE"

    def _parse_user_acts(
        self,
        user_acts: List,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
    ) -> List[Dict]:
        """Convert RiSAWOZ user_acts to SGD actions list."""
        actions: List[Dict] = []
        for act in user_acts:
            if not isinstance(act, list) or len(act) < 2:
                continue
            intent = act[0] if len(act) > 0 else ""
            domain = act[1] if len(act) > 1 else ""
            slot = act[2] if len(act) > 2 else ""
            value = act[3] if len(act) > 3 else ""

            sgd_act = _map_act(intent) if intent else "INFORM"

            actions.append({
                "act": sgd_act,
                "slot": slot,
                "values": [value] if value else [],
                "canonical_values": [value] if value else [],
            })

        return actions

    # ------ frame builders ------

    def _build_user_frames(
        self,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
        user_actions: List[Dict],
        active_intent: str,
        services_list: List[str],
    ) -> List[Dict]:
        """Build SGD frames for a USER turn."""
        frames: List[Dict] = []

        # Determine which services are active (have slots or are in services_list)
        active_services = set(cumulative_slots.keys()) | set(services_list)

        for svc in sorted(active_services):
            slot_values = cumulative_slots.get(svc, {})
            # Filter actions to this service's domain
            svc_domain = svc.rsplit("_", 1)[0]
            svc_actions = [
                a for a in user_actions
                # include if no slot filter, or slot mentioned
                if True  # include all user actions in first service frame
            ] if svc == sorted(active_services)[0] else []

            frames.append({
                "service": svc,
                "state": {
                    "active_intent": active_intent,
                    "requested_slots": [],
                    "slot_values": slot_values,
                },
                "actions": svc_actions,
            })

        return frames

    def _build_system_frames(
        self,
        cumulative_slots: Dict[str, Dict[str, List[str]]],
        services_list: List[str],
    ) -> List[Dict]:
        """Build SGD frames for a SYSTEM turn (no service_call / service_results)."""
        frames: List[Dict] = []

        active_services = set(cumulative_slots.keys()) | set(services_list)

        for svc in sorted(active_services):
            slot_values = cumulative_slots.get(svc, {})
            frames.append({
                "service": svc,
                "state": {
                    "active_intent": "NONE",
                    "requested_slots": [],
                    "slot_values": slot_values,
                },
                "actions": [],
                "service_call": None,
                "service_results": [],
            })

        return frames
