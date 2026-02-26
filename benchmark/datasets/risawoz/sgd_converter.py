"""
RiSAWOZ → SGD 格式转换器

将中文 RiSAWOZ 数据集转换为 Google SGD（Schema-Guided Dialogue）格式，
以便使用 pyTOD 算法对该数据集进行训练和测试。

SGD 格式参考:
  https://github.com/google-research-datasets/dstc8-schema-guided-dialogue

RiSAWOZ 格式参考:
  https://github.com/terryqj0107/RiSAWOZ

----------------------------------------------------------------------
支持的 RiSAWOZ 源格式
----------------------------------------------------------------------

"source-data" 格式 (source-data.zip)
  对话的每一轮用两个独立的 dict 表示，一个 role="usr"，一个 role="sys":
    {
      "dialogue_id": "hotel_0001",
      "domains": ["酒店"],
      "dialogue": [
        {"turn_id": 0, "role": "usr", "utterance": "...",
         "dialogue_act": [{"act":"Inform","domain":"酒店","slot":"位置","value":"西城区"}],
         "belief_state": [{"domain":"酒店","slot":"位置","value":"西城区"}]},
        {"turn_id": 1, "role": "sys", "utterance": "...",
         "dialogue_act": [...], "belief_state": [...]},
        ...
      ]
    }

"task2-dst" 格式 (task2-data-DST.zip)
  每轮 dict 同时包含 user_utterance 和 system_utterance:
    {
      "dialogue": [
        {"turn_id": 0,
         "user_utterance": "...", "system_utterance": "...",
         "belief_state": [...], "user_acts": [...]},
        ...
      ]
    }

转换器会自动检测格式。也可通过 source_format 参数手动指定。

格式映射:
  RiSAWOZ dialogue → SGD dialogue
  RiSAWOZ domain   → SGD service_name (e.g. "景点_1")
  RiSAWOZ turn(s)  → 2 SGD turns (USER turn + SYSTEM turn)
  RiSAWOZ belief_state [{domain, slot, value}]
    → SGD state.slot_values {slot_name: [value]}
  RiSAWOZ user_acts / dialogue_act
    → SGD actions [{act, slot, values, canonical_values}]
"""

import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from benchmark.datasets.risawoz.adapter import RiSAWOZAdapter, RISAWOZ_FILE_MAPPINGS

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
# Source-format detection
# ------------------------------------------------------------------

#: Accepted values for the source_format parameter.
#: Includes all keys from RISAWOZ_FILE_MAPPINGS plus "auto".
SOURCE_FORMATS = ("auto", "source-data", "task2-dst", "task3-e2e", "task5-unified")


def _detect_format(dialogue_data: Dict) -> str:
    """
    Infer the RiSAWOZ source format from a single dialogue dict.

    Returns one of:
      "source-data" — turns have individual role="usr"/"sys" dicts with an
                      "utterance" field and optionally "dialogue_act"
      "task2-dst"   — turns are combined dicts with "user_utterance" /
                      "system_utterance" and optionally "user_acts"
    """
    turns = dialogue_data.get("dialogue", [])
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        if "role" in turn and "utterance" in turn:
            return "source-data"
        if "user_utterance" in turn or "system_utterance" in turn:
            return "task2-dst"
    # default – task2-dst handles both via fallback keys
    return "task2-dst"


# Role values recognized as user/system turns (case-insensitive, checked via .lower())
_USR_ROLES: frozenset = frozenset({
    "usr", "user",                    # English abbreviations
    "用户", "客户", "顾客", "client",  # Chinese/other user-side labels
})
_SYS_ROLES: frozenset = frozenset({
    "sys", "system",                  # English
    "系统", "客服", "服务员", "agent", # Chinese/other system-side labels
})


def _coerce_belief_list(bs: Any) -> List:
    """
    Normalise a belief_state value to a list regardless of how it was stored.

    Handles all known RiSAWOZ belief_state formats:
      - list  (standard)   → returned as-is
      - {}    (empty dict) → []
      - {"domain": {"slot": "value"}}
          Standard nested dict: first-level key is domain name,
          second-level key is plain slot name.
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - {"act_type": {"domain-slot": "value"}}
          Source-data act-type nested dict: first-level key is an act type
          (e.g. "inform slot-values", "turn_inform"), second-level keys are
          "domain-slot" format strings (contain "-").
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - {"domain-slot": "value"}
          Flat dict where key is "domain-slot" format string.
          → [{"domain":"domain","slot":"slot","value":"value"}]
      - None / other       → []
    """
    if isinstance(bs, list):
        return bs
    if isinstance(bs, dict):
        if not bs:
            return []
        result = []
        for k, v in bs.items():
            if isinstance(v, dict):
                # Distinguish two nested-dict formats by inspecting second-level keys:
                #   A. {"domain": {"slot": "value"}}        — slot keys have no "-"
                #   B. {"act_type": {"domain-slot": "value"}} — slot keys contain "-"
                if any("-" in str(sk) for sk in v.keys()):
                    # Format B: act-type key, second-level keys are "domain-slot"
                    for slot_key, value in v.items():
                        sk = str(slot_key)
                        if "-" in sk and value:
                            domain, slot = sk.split("-", 1)
                            result.append({"domain": domain, "slot": slot, "value": str(value)})
                else:
                    # Format A: standard domain → slot → value
                    for slot, value in v.items():
                        if value:
                            result.append({"domain": k, "slot": slot, "value": str(value)})
            elif isinstance(v, str) and v:
                # Flat dict: {"domain-slot": "value"}
                sk = str(k)
                if "-" in sk:
                    domain, slot = sk.split("-", 1)
                    result.append({"domain": domain, "slot": slot, "value": v})
        return result
    return []


def _infer_role_sets(raw_turns: List[Dict]) -> Tuple[frozenset, frozenset]:
    """
    Examine the actual role values in a list of raw turns and return
    ``(usr_roles, sys_roles)`` frozensets to use for pairing.

    Strategy (in order of preference):
    1. If all role values are already in the known sets → use known sets.
    2. If exactly 2 distinct role values exist → the one that appears *first*
       overall is treated as the user role, the other as the system role.
    3. Fallback: return empty frozensets so the caller uses position-based pairing.
    """
    seen_roles = []
    seen_set: set = set()
    for turn in raw_turns:
        if not isinstance(turn, dict):
            continue
        r = turn.get("role")
        if r is not None:
            rl = str(r).lower()
            if rl not in seen_set:
                seen_set.add(rl)
                seen_roles.append(rl)

    if not seen_roles:
        return frozenset(), frozenset()

    # Check if all seen roles are already covered by the known sets
    known = _USR_ROLES | _SYS_ROLES
    if all(r in known for r in seen_roles):
        return _USR_ROLES, _SYS_ROLES

    # Exactly 2 distinct roles → first-seen = user, second-seen = system
    if len(seen_roles) == 2:
        logger.info(
            f"[RiSAWOZ→SGD] 自动推断 role 映射: "
            f"'{seen_roles[0]}' → 用户(user), '{seen_roles[1]}' → 系统(system)"
        )
        return frozenset({seen_roles[0]}), frozenset({seen_roles[1]})

    # More than 2 distinct roles or 1 unknown role → fallback
    logger.warning(
        f"[RiSAWOZ→SGD] ⚠️  无法自动推断 role 映射，将使用位置法（偶数轮=用户，奇数轮=系统）\n"
        f"  发现的 role 值: {seen_roles}"
    )
    return frozenset(), frozenset()


def _get_utterance(turn: Dict) -> str:
    """Extract utterance text from a raw turn, trying all known field names."""
    return (
        turn.get("utterance")
        or turn.get("transcript")
        or turn.get("utt")
        or turn.get("text")
        or turn.get("content")
        or ""
    )


def _pair_turns_by_role(
    raw_turns: List[Dict], usr_roles: frozenset, sys_roles: frozenset
) -> List[Dict]:
    """
    Pair consecutive user/system turns into combined dicts.
    Returns a list of combined turn dicts with keys:
      user_utterance, system_utterance, belief_state, user_acts, _dialogue_act
    """
    combined: List[Dict] = []
    pending_usr: Optional[Dict] = None

    for turn in raw_turns:
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role", "")).lower()
        if role in usr_roles:
            pending_usr = turn
        elif role in sys_roles and pending_usr is not None:
            user_bs = _coerce_belief_list(pending_usr.get("belief_state", []))
            sys_bs = _coerce_belief_list(turn.get("belief_state", []))
            belief_state = sys_bs if sys_bs else user_bs
            d_acts = pending_usr.get("dialogue_act", [])
            combined.append({
                "user_utterance": _get_utterance(pending_usr),
                "system_utterance": _get_utterance(turn),
                "belief_state": belief_state,
                "user_acts": _dialogue_acts_to_user_acts(d_acts),
                "_dialogue_act": d_acts,
            })
            pending_usr = None

    return combined


def _pair_turns_by_position(raw_turns: List[Dict]) -> List[Dict]:
    """
    Pair turns by position when role values are unknown or missing.
    Even positions (0, 2, 4, …) are treated as user turns;
    odd positions  (1, 3, 5, …) are treated as system turns.
    """
    dicts = [t for t in raw_turns if isinstance(t, dict)]
    combined: List[Dict] = []
    for i in range(0, len(dicts) - 1, 2):
        usr_turn = dicts[i]
        sys_turn = dicts[i + 1]
        user_bs = _coerce_belief_list(usr_turn.get("belief_state", []))
        sys_bs = _coerce_belief_list(sys_turn.get("belief_state", []))
        belief_state = sys_bs if sys_bs else user_bs
        d_acts = usr_turn.get("dialogue_act", [])
        combined.append({
            "user_utterance": _get_utterance(usr_turn),
            "system_utterance": _get_utterance(sys_turn),
            "belief_state": belief_state,
            "user_acts": _dialogue_acts_to_user_acts(d_acts),
            "_dialogue_act": d_acts,
        })
    return combined


def _normalize_turns(dialogue_data: Dict, fmt: str) -> List[Dict]:
    """
    Normalise raw turns into a list of combined dicts, each representing
    one user-turn + one system-turn pair.  Returns dicts with keys:
      user_utterance, system_utterance, belief_state, user_acts
    so the rest of the converter can treat them uniformly.

    For "task2-dst" the dicts already have that shape; we return them as-is.
    For "source-data" / other formats:
      1. Try to pair turns by known role values (from _USR_ROLES / _SYS_ROLES).
      2. If that produces 0 turns, auto-infer role values from the dialogue.
      3. If still 0, fall back to position-based pairing (even=user, odd=system).
    """
    raw_turns = dialogue_data.get("dialogue", [])

    if fmt == "task2-dst":
        return [t for t in raw_turns if isinstance(t, dict)]

    # ── source-data and other role-based formats ──────────────────────
    # Step 1: try with the well-known role sets
    combined = _pair_turns_by_role(raw_turns, _USR_ROLES, _SYS_ROLES)
    if combined:
        return combined

    # Step 2: auto-infer role sets from actual data
    usr_roles, sys_roles = _infer_role_sets(raw_turns)
    if usr_roles or sys_roles:
        combined = _pair_turns_by_role(raw_turns, usr_roles, sys_roles)
    if combined:
        return combined

    # Step 3: position-based fallback (always produces output if there are turns)
    return _pair_turns_by_position(raw_turns)


def _dialogue_acts_to_user_acts(dialogue_acts: List) -> List:
    """
    Convert source-data's dialogue_act list into the user_acts list format
    expected by the rest of the converter.

    Handles two formats:
      dict  : [{"act": "Inform", "domain": "酒店", "slot": "位置", "value": "西城区"}, ...]
      list  : [["Inform", "酒店", "位置", "西城区"], ...]   ← list-of-lists (also common)

    Returns user_acts:
      [["Inform", "酒店", "位置", "西城区"], ...]
    """
    result = []
    for da in dialogue_acts:
        if isinstance(da, dict):
            result.append([
                da.get("act", ""),
                da.get("domain", ""),
                da.get("slot", ""),
                da.get("value", ""),
            ])
        elif isinstance(da, list) and len(da) >= 2:
            # list-of-lists format: [intent, domain, slot?, value?]
            result.append([
                da[0],
                da[1],
                da[2] if len(da) > 2 else "",
                da[3] if len(da) > 3 else "",
            ])
    return result


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
            # ── belief_state ─────────────────────────────────────────────
            # Supports three formats:
            #   A. list-of-dicts: [{"domain": "景点", "slot": "名称", "value": "故宫"}]
            #   B. list-of-dicts: [{"slots": [["景点-名称", "故宫"]], "act": "..."}]
            #   C. nested dict:   {"景点": {"名称": "故宫"}} (normalised via _coerce_belief_list)
            belief_state = _coerce_belief_list(turn.get("belief_state", []))
            for belief in belief_state:
                if not isinstance(belief, dict):
                    continue
                if "domain" in belief and "slot" in belief:
                    # Format A: {"domain": "景点", "slot": "名称", "value": "故宫"}
                    domain = belief["domain"]
                    slot = belief["slot"]
                    value = belief.get("value", "")
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]  # ensure key exists
                elif "slots" in belief:
                    # Format B: {"slots": [["景点-名称", "故宫"], ...], "act": "..."}
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

            # ── user_acts (task2-dst): [[intent, domain, slot, value], ...] ──
            for act in turn.get("user_acts", []):
                if isinstance(act, list) and len(act) >= 2:
                    intent, domain = act[0], act[1]
                    if domain:
                        self._intents[domain].add(intent)

            # ── dialogue_act (source-data) ────────────────────────────────
            # Supports two formats:
            #   dict : [{"act":..,"domain":..,"slot":..,"value":..}, ...]
            #   list : [["Inform", "景点", "名称", "故宫"], ...]  ← list-of-lists
            for da in turn.get("dialogue_act", []):
                if isinstance(da, dict):
                    intent = da.get("act", "")
                    domain = da.get("domain", "")
                    slot = da.get("slot", "")
                    value = da.get("value", "")
                    if domain and intent:
                        self._intents[domain].add(intent)
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]
                elif isinstance(da, list) and len(da) >= 2:
                    # list-of-lists: [intent, domain, slot?, value?]
                    intent, domain = da[0], da[1]
                    slot = da[2] if len(da) > 2 else ""
                    value = da[3] if len(da) > 3 else ""
                    if domain and intent:
                        self._intents[domain].add(intent)
                    if domain and slot:
                        if value:
                            self._slots[domain][slot].add(str(value))
                        else:
                            self._slots[domain][slot]

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

    Supported source formats
    ------------------------
    "auto" (default)
        Auto-detect from the first dialogue's turn structure.
    "source-data"
        From ``source-data.zip``.  Each turn is an individual dict with
        ``role="usr"`` or ``role="sys"`` and an ``utterance`` field.
        Recommended — contains the richest annotations (``dialogue_act``).
    "task2-dst"
        From ``task2-data-DST.zip``.  Each turn is a combined dict with
        ``user_utterance`` and ``system_utterance`` fields.
        Also fully supported.

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
        source_format: str = "auto",
    ) -> None:
        if source_format not in SOURCE_FORMATS:
            raise ValueError(
                f"source_format 必须是 {SOURCE_FORMATS} 之一，got {source_format!r}"
            )
        # If no explicit file_mapping provided and a known source_format is given,
        # auto-apply the correct filename mapping from RISAWOZ_FILE_MAPPINGS.
        if file_mapping is None and source_format in RISAWOZ_FILE_MAPPINGS:
            file_mapping = RISAWOZ_FILE_MAPPINGS[source_format]
            logger.debug(
                f"[RiSAWOZToSGDConverter] 自动应用文件映射 ({source_format}): {file_mapping}"
            )
        self.adapter = RiSAWOZAdapter(data_root, file_mapping=file_mapping)
        self.data_root = Path(data_root)
        self.source_format = source_format

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

        # Detect format from the first dialogue if mode is "auto"
        effective_format = self.source_format
        if effective_format == "auto" and dialogues_raw:
            first_dict = next(
                (d for d in dialogues_raw if isinstance(d, dict)), None
            )
            if first_dict is not None:
                effective_format = _detect_format(first_dict)
        if effective_format == "auto":
            effective_format = "task2-dst"
        logger.info(f"[RiSAWOZ→SGD] 检测到源格式: {effective_format}")

        # ── Pass 1: build schema ──────────────────────────────────────
        builder = _SchemaBuilder()
        for dialogue_data in dialogues_raw:
            if isinstance(dialogue_data, dict):
                builder.ingest_dialogue(dialogue_data)
        schema = builder.build_schema()

        # Diagnostic: warn when schema is empty (signals a data format mismatch)
        if not schema and dialogues_raw:
            sample = next((d for d in dialogues_raw if isinstance(d, dict)), None)
            if sample:
                sample_turn = sample.get("dialogue", [None])[0]
                logger.warning(
                    f"[RiSAWOZ→SGD] ⚠️  schema.json 为空（0 个服务），"
                    f"请检查数据格式是否匹配。\n"
                    f"  第一条对话的 keys: {list(sample.keys())}\n"
                    f"  第一个 turn 的 keys: {list(sample_turn.keys()) if isinstance(sample_turn, dict) else sample_turn!r}"
                )

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
                sgd_dialogue = self._convert_dialogue(dialogue_data, idx, effective_format)
                sgd_dialogues.append(sgd_dialogue)
                total_turns += len(sgd_dialogue["turns"])
            except Exception as exc:
                logger.warning(f"[RiSAWOZ→SGD] 跳过对话 {idx}: {exc}")

        # Diagnostic: warn when turns are all empty (signals a role/format mismatch)
        if sgd_dialogues and total_turns == 0:
            sample = next((d for d in dialogues_raw if isinstance(d, dict)), None)
            if sample:
                turns = sample.get("dialogue", [])
                sample_roles = [t.get("role") for t in turns if isinstance(t, dict)]
                logger.warning(
                    f"[RiSAWOZ→SGD] ⚠️  转换了 {len(sgd_dialogues)} 条对话但总轮次为 0。\n"
                    f"  检测到的源格式: {effective_format}\n"
                    f"  第一条对话的 role 值: {sample_roles[:6]}\n"
                    f"  期望的 role 值: {list(_USR_ROLES)} 或 {list(_SYS_ROLES)}\n"
                    f"  若 role 值不在上述列表中，请检查数据格式。"
                )

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
            "source_format": effective_format,
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

    def _convert_dialogue(self, dialogue_data: Dict, idx: int, fmt: str = "task2-dst") -> Dict:
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
            for belief in _coerce_belief_list(turn.get("belief_state", [])):
                domain = self._extract_domain_from_belief(belief)
                if domain:
                    services.add(f"{domain}_1")

        services_list = sorted(services) if services else ["通用_1"]

        # Normalise turns into combined user+system dicts
        combined_turns = _normalize_turns(dialogue_data, fmt)

        # Convert turns: one combined turn → USER turn + SYSTEM turn in SGD
        sgd_turns: List[Dict] = []
        cumulative_slots: Dict[str, Dict[str, List[str]]] = defaultdict(dict)
        # cumulative_slots[service_name][slot_name] = [value]

        for turn_data in combined_turns:
            # Support both combined-dict field names:
            #   "user_utterance"    (produced by _normalize_turns for source-data)
            #   "transcript"        (native task2-DST / risawoz field name)
            user_utt = (
                turn_data.get("user_utterance")
                or turn_data.get("transcript")
                or ""
            )
            sys_utt = (
                turn_data.get("system_utterance")
                or turn_data.get("system_transcript")
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
        """Return the domain string from a single belief_state entry (already normalised)."""
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
        self, belief_state: Any
    ) -> Dict[str, Dict[str, List[str]]]:
        """
        Parse a RiSAWOZ belief_state value into:
            {service_name: {slot_name: [value]}}

        Accepts all supported belief_state formats (normalised via _coerce_belief_list):
          A. [{"domain": "景点", "slot": "名称", "value": "故宫"}, ...]
          B. [{"slots": [["景点-名称", "故宫"], ...], "act": "..."}]
          C. {"景点": {"名称": "故宫"}}  (nested dict, converted by _coerce_belief_list)
        """
        result: Dict[str, Dict[str, List[str]]] = defaultdict(dict)

        for belief in _coerce_belief_list(belief_state):
            if not isinstance(belief, dict):
                continue

            if "domain" in belief and "slot" in belief:
                # Format A
                domain = belief["domain"]
                slot = belief["slot"]
                value = str(belief.get("value", "")) if belief.get("value") else ""
                if domain and slot and value:
                    svc = f"{domain}_1"
                    result[svc][slot] = [value]

            elif "slots" in belief:
                # Format B
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
