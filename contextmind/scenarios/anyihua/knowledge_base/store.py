"""
安逸花外呼 · 增量精准知识库 · CRUD 存储层

本模块提供知识库的标准 CRUD 接口，以及从 SGD 格式对话直接摄入数据的能力。

设计原则：
    · 接口与存储介质解耦：默认使用纯内存字典，支持 JSON 文件持久化。
    · 扩展友好：摄入入口 ingest_sgd_dialogue 不依赖 anyihua 特定字段，
      可通过参数化扩展至其他数据源（transfertod、risawoz 等）。
    · 幂等摄入：重复摄入同一 session_id 不会产生重复记录，
      而是委托 IncrementalMerger 进行冲突检测和增量合并。

典型使用::

    from pathlib import Path
    from contextmind.scenarios.anyihua.knowledge_base.store import KnowledgeStore

    store = KnowledgeStore()
    # 从 SGD 格式对话批量摄入
    with open("resources/anyihua_sgd/dialogues_001.json") as f:
        dialogues = json.load(f)
    for dialogue in dialogues:
        store.ingest_sgd_dialogue(dialogue)

    # CRUD 查询
    record = store.get_customer("高先生::六七八")
    print(record.get_slot_value("available_credit"))  # "9999.99"

    # 持久化
    store.save_to_json(Path("data/anyihua_kb.json"))
    store2 = KnowledgeStore.load_from_json(Path("data/anyihua_kb.json"))
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from contextmind.infra.logger import get_logger

from .schema import (
    CustomerRecord,
    KBStats,
    SlotEvidence,
    SlotFact,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# 辅助：从 SGD 帧（frame）中提取置信度
# ---------------------------------------------------------------------------

# SGD 对话中对齐状态 → 置信度映射（与 pipeline.py 保持一致）
_ALIGNMENT_CONFIDENCE: Dict[Optional[str], float] = {
    "match_exact": 1.0,
    "match_lesser": 0.85,
    "match_fuzzy": 0.70,
    None: 0.50,
}


def _confidence_from_alignment(status: Optional[str]) -> float:
    """将 langextract 对齐状态映射为置信度数值。"""
    return _ALIGNMENT_CONFIDENCE.get(status, 0.50)


# ---------------------------------------------------------------------------
# KnowledgeStore — 核心 CRUD 接口
# ---------------------------------------------------------------------------


class KnowledgeStore:
    """
    安逸花外呼精准知识库的核心 CRUD 存储层。

    内部以纯内存字典（customer_id → CustomerRecord）组织数据，
    支持通过 save_to_json / load_from_json 进行 JSON 文件持久化。

    线程安全说明：当前实现不加锁，适合单线程/单进程使用。
    高并发场景请在外部使用 asyncio.Lock 或将存储层替换为数据库后端。
    """

    def __init__(self) -> None:
        # 主存储：customer_id → CustomerRecord
        self._records: Dict[str, CustomerRecord] = {}
        # 会话去重集合：已摄入的 session_id，防止重复处理
        self._ingested_sessions: set = set()

    # ------------------------------------------------------------------ #
    # 摄入接口（Write）
    # ------------------------------------------------------------------ #

    def ingest_sgd_dialogue(
        self,
        dialogue: Dict[str, Any],
        customer_id_fn: Optional[Any] = None,
    ) -> Optional[CustomerRecord]:
        """
        从单条 SGD 格式对话中摄入知识。

        幂等设计：同一 session_id 的对话只处理一次。
        若需要重新摄入，请先调用 remove_session(session_id)。

        参数:
            dialogue:        SGD 格式对话字典（须含 "dialogue_id" 和 "turns"）
            customer_id_fn:  可选的客户 ID 生成函数，签名为
                             (dialogue: dict) -> str。
                             默认使用 _default_customer_id_fn。

        返回:
            摄入后的 CustomerRecord，若跳过则返回 None。
        """
        session_id = str(dialogue.get("dialogue_id", "")).strip()
        if not session_id:
            logger.warning("[KnowledgeStore] 跳过：对话缺少 dialogue_id")
            return None

        if session_id in self._ingested_sessions:
            logger.debug(f"[KnowledgeStore] 幂等跳过已摄入会话: {session_id}")
            return self._records.get(
                self._find_customer_by_session(session_id)
            )

        # 确定客户 ID
        if customer_id_fn is None:
            customer_id_fn = _default_customer_id_fn
        customer_id = customer_id_fn(dialogue)
        if not customer_id:
            logger.warning(
                f"[KnowledgeStore] 无法确定 customer_id，跳过会话: {session_id}"
            )
            return None

        # 获取或创建客户记录
        record = self._records.setdefault(
            customer_id, CustomerRecord(customer_id=customer_id)
        )

        # 更新会话列表
        if session_id not in record.session_ids:
            record.session_ids.append(session_id)

        # 逐帧提取槽位证据并写入记录
        slot_evidences: Dict[str, List[SlotEvidence]] = {}
        for turn in dialogue.get("turns", []):
            speaker = turn.get("speaker", "UNKNOWN")
            utterance = turn.get("utterance", "")
            for frame in turn.get("frames", []):
                for slot_name, ev in _extract_slot_evidences_named(
                    frame, session_id, speaker, utterance
                ):
                    slot_evidences.setdefault(slot_name, []).append(ev)

        # 写入记录（选取每个槽位置信度最高的证据）
        for slot_name, evs in slot_evidences.items():
            best_ev = max(evs, key=lambda e: e.confidence)
            self._upsert_slot(record, slot_name, best_ev)

        record.updated_at = datetime.now()
        self._ingested_sessions.add(session_id)

        logger.debug(
            f"[KnowledgeStore] 摄入会话 {session_id} → 客户 {customer_id}, "
            f"槽位: {list(slot_evidences.keys())}"
        )
        return record

    def upsert_slot_evidence(
        self,
        customer_id: str,
        slot_name: str,
        evidence: SlotEvidence,
    ) -> CustomerRecord:
        """
        直接向指定客户的指定槽位写入证据。

        若客户记录不存在则自动创建；
        冲突检测和历史追加由内部 _upsert_slot 处理。

        参数:
            customer_id: 客户标识
            slot_name:   槽位名称
            evidence:    SlotEvidence 证据对象

        返回:
            更新后的 CustomerRecord
        """
        record = self._records.setdefault(
            customer_id, CustomerRecord(customer_id=customer_id)
        )
        self._upsert_slot(record, slot_name, evidence)
        record.updated_at = datetime.now()
        return record

    # ------------------------------------------------------------------ #
    # 查询接口（Read）
    # ------------------------------------------------------------------ #

    def get_customer(self, customer_id: str) -> Optional[CustomerRecord]:
        """
        获取指定客户的完整知识记录。

        参数:
            customer_id: 客户标识

        返回:
            CustomerRecord，不存在时返回 None
        """
        return self._records.get(customer_id)

    def get_slot_value(self, customer_id: str, slot_name: str) -> Optional[str]:
        """
        获取指定客户指定槽位的当前值。

        参数:
            customer_id: 客户标识
            slot_name:   槽位名称

        返回:
            槽位值字符串，不存在时返回 None
        """
        record = self._records.get(customer_id)
        if record is None:
            return None
        return record.get_slot_value(slot_name)

    def list_customers(self) -> List[str]:
        """返回所有已知客户 ID 列表。"""
        return list(self._records.keys())

    def query_by_slot(
        self,
        slot_name: str,
        value: str,
        exact: bool = True,
    ) -> List[CustomerRecord]:
        """
        查询具有指定槽位值的所有客户记录。

        参数:
            slot_name: 槽位名称
            value:     目标槽位值
            exact:     True 时进行精确匹配，False 时进行包含匹配（大小写不敏感）

        返回:
            匹配的 CustomerRecord 列表
        """
        results = []
        for record in self._records.values():
            current = record.get_slot_value(slot_name)
            if current is None:
                continue
            if exact:
                if current == value:
                    results.append(record)
            else:
                if value.lower() in current.lower():
                    results.append(record)
        return results

    def iter_customers(self) -> Iterator[CustomerRecord]:
        """迭代所有客户记录。"""
        yield from self._records.values()

    # ------------------------------------------------------------------ #
    # 更新接口（Update）
    # ------------------------------------------------------------------ #

    def update_slot(
        self,
        customer_id: str,
        slot_name: str,
        new_evidence: SlotEvidence,
        force: bool = False,
    ) -> bool:
        """
        更新客户的槽位值。

        参数:
            customer_id:  客户标识
            slot_name:    槽位名称
            new_evidence: 新的槽位证据
            force:        True 时跳过置信度比较，强制覆盖

        返回:
            True 表示槽位值被更新，False 表示保持原值
        """
        record = self._records.get(customer_id)
        if record is None:
            logger.warning(
                f"[KnowledgeStore] update_slot: 客户 {customer_id} 不存在"
            )
            return False
        return self._upsert_slot(record, slot_name, new_evidence, force=force)

    # ------------------------------------------------------------------ #
    # 删除接口（Delete）
    # ------------------------------------------------------------------ #

    def delete_customer(self, customer_id: str) -> bool:
        """
        删除指定客户的完整记录。

        参数:
            customer_id: 客户标识

        返回:
            True 表示删除成功，False 表示客户不存在
        """
        if customer_id not in self._records:
            return False
        record = self._records.pop(customer_id)
        # 同步清理会话去重集合
        for sid in record.session_ids:
            self._ingested_sessions.discard(sid)
        logger.debug(f"[KnowledgeStore] 删除客户记录: {customer_id}")
        return True

    def has_session(self, session_id: str) -> bool:
        """
        检查指定会话是否已被摄入。

        参数:
            session_id: 会话 ID

        返回:
            True 表示该会话已在知识库中，重复摄入会被幂等跳过
        """
        return session_id in self._ingested_sessions

    def remove_session(self, session_id: str) -> None:
        """
        从幂等保护集合中移除指定会话，使其可被重新摄入。

        注意：此操作不会删除已写入知识记录中的槽位数据。

        参数:
            session_id: 会话 ID
        """
        self._ingested_sessions.discard(session_id)

    def clear(self) -> None:
        """清空所有知识记录和会话记录。"""
        self._records.clear()
        self._ingested_sessions.clear()
        logger.info("[KnowledgeStore] 知识库已清空")

    # ------------------------------------------------------------------ #
    # 统计接口
    # ------------------------------------------------------------------ #

    def get_stats(self) -> KBStats:
        """计算并返回知识库当前统计信息。"""
        total_facts = 0
        total_conflicts = 0
        aligned_facts = 0

        for record in self._records.values():
            for fact in record.facts.values():
                if fact.current_value is not None:
                    total_facts += 1
                    if fact.current_evidence and fact.current_evidence.is_aligned():
                        aligned_facts += 1
            total_conflicts += len(record.conflicts)

        provenance_rate = aligned_facts / total_facts if total_facts else 0.0
        conflict_rate = total_conflicts / total_facts if total_facts else 0.0

        return KBStats(
            total_customers=len(self._records),
            total_sessions=len(self._ingested_sessions),
            total_facts=total_facts,
            total_conflicts=total_conflicts,
            conflict_rate=conflict_rate,
            aligned_facts=aligned_facts,
            provenance_rate=provenance_rate,
        )

    # ------------------------------------------------------------------ #
    # 持久化（JSON 序列化 / 反序列化）
    # ------------------------------------------------------------------ #

    def save_to_json(self, path: Path) -> None:
        """
        将知识库序列化为 JSON 文件。

        参数:
            path: 输出文件路径（父目录须已存在）
        """
        payload = {
            "records": {
                cid: record.to_dict() for cid, record in self._records.items()
            },
            "ingested_sessions": list(self._ingested_sessions),
            "saved_at": datetime.now().isoformat(),
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        logger.info(
            f"[KnowledgeStore] 已保存 {len(self._records)} 条记录 → {path}"
        )

    @classmethod
    def load_from_json(cls, path: Path) -> "KnowledgeStore":
        """
        从 JSON 文件反序列化知识库。

        参数:
            path: JSON 文件路径

        返回:
            加载完成的 KnowledgeStore 实例
        """
        payload = json.loads(path.read_text(encoding="utf-8"))
        store = cls()
        for cid, record_dict in payload.get("records", {}).items():
            store._records[cid] = CustomerRecord.from_dict(record_dict)
        store._ingested_sessions = set(payload.get("ingested_sessions", []))
        logger.info(
            f"[KnowledgeStore] 已加载 {len(store._records)} 条记录 ← {path}"
        )
        return store

    # ------------------------------------------------------------------ #
    # 内部辅助方法
    # ------------------------------------------------------------------ #

    def _upsert_slot(
        self,
        record: CustomerRecord,
        slot_name: str,
        new_evidence: SlotEvidence,
        force: bool = False,
    ) -> bool:
        """
        将新证据写入客户记录的指定槽位，执行冲突检测和历史追加。

        冲突策略（默认）：
          - 若新证据置信度 >= 现有置信度，则替换（并记录冲突）。
          - 若新证据置信度 < 现有置信度，保留现有值（但仍追加至历史）。
          - force=True 时，跳过置信度比较，无条件替换。

        参数:
            record:       目标客户记录
            slot_name:    槽位名称
            new_evidence: 新证据
            force:        是否强制替换

        返回:
            True 表示当前槽位值被更新
        """
        if slot_name not in record.facts:
            # 首次写入：直接创建 SlotFact
            record.facts[slot_name] = SlotFact(
                name=slot_name, current_evidence=new_evidence
            )
            return True

        fact = record.facts[slot_name]
        existing_ev = fact.current_evidence

        if existing_ev is None:
            fact.current_evidence = new_evidence
            return True

        # 值相同：无需替换，但追加历史以记录重复出现
        if existing_ev.value == new_evidence.value:
            fact.history.insert(0, new_evidence)
            return False

        # 值不同：记录冲突
        from .schema import ConflictEntry

        conflict = ConflictEntry(
            slot_name=slot_name,
            existing_value=existing_ev.value,
            new_value=new_evidence.value,
            existing_session=existing_ev.session_id,
            new_session=new_evidence.session_id,
        )

        # 决定是否替换
        should_replace = force or (new_evidence.confidence >= existing_ev.confidence)
        if should_replace:
            conflict.resolution = "replaced_by_new"
            fact.history.insert(0, existing_ev)
            fact.current_evidence = new_evidence
            updated = True
        else:
            conflict.resolution = "kept_existing"
            fact.history.insert(0, new_evidence)
            updated = False

        record.conflicts.append(conflict)
        logger.debug(
            f"[KnowledgeStore] 冲突 [{slot_name}]: "
            f"'{existing_ev.value}' vs '{new_evidence.value}' → {conflict.resolution}"
        )
        return updated

    def _find_customer_by_session(self, session_id: str) -> Optional[str]:
        """通过 session_id 反查 customer_id。"""
        for cid, record in self._records.items():
            if session_id in record.session_ids:
                return cid
        return None


# ---------------------------------------------------------------------------
# 辅助：带槽位名称的帧证据提取
# ---------------------------------------------------------------------------


def _extract_slot_evidences_named(
    frame: Dict[str, Any],
    session_id: str,
    speaker: str,
    utterance: str,
) -> Iterator[tuple]:
    """
    从单个 SGD 帧中提取 (slot_name, SlotEvidence) 对。

    同时处理三个证据来源：
    1. frame["slots"]                — 槽位-值对列表（槽位状态标注）
    2. frame["state"]["slot_values"] — 累积槽位状态（置信度略高）
    3. frame["service_results"]      — 服务调用返回的业务结果（可信度最高）

    Yields:
        (slot_name: str, evidence: SlotEvidence) 元组
    """

    def _make(name: str, value: Any, confidence: float) -> Optional[SlotEvidence]:
        str_value = str(value).strip() if value is not None else ""
        if not str_value:
            return None
        return SlotEvidence(
            session_id=session_id,
            value=str_value,
            char_start=None,
            char_end=None,
            alignment_status=None,
            confidence=confidence,
            speaker=speaker,
            extraction_text=utterance[:100] if utterance else None,
        )

    # ① frame["slots"]
    for slot_entry in frame.get("slots", []):
        name = slot_entry.get("slot", "")
        if not name:
            continue
        for val in slot_entry.get("value", []):
            ev = _make(name, val, 0.60)
            if ev:
                yield name, ev

    # ② frame["state"]["slot_values"]
    state = frame.get("state", {})
    for name, vals in state.get("slot_values", {}).items():
        for val in (vals if isinstance(vals, list) else [vals]):
            ev = _make(name, val, 0.65)
            if ev:
                yield name, ev

    # ③ frame["service_results"]（最高可信度）
    for result in frame.get("service_results", []):
        for name, val in result.items():
            ev = _make(name, val, 0.90)
            if ev:
                yield name, ev


# ---------------------------------------------------------------------------
# 默认客户 ID 生成函数
# ---------------------------------------------------------------------------


def _default_customer_id_fn(dialogue: Dict[str, Any]) -> str:
    """
    从 SGD 对话中生成默认客户 ID。

    策略：在所有帧的 service_results 中查找 customer_name 和 phone_suffix，
    以 "姓名::手机尾号" 格式组合；若缺失任一字段，则退化为 dialogue_id。

    参数:
        dialogue: SGD 格式对话字典

    返回:
        客户 ID 字符串
    """
    name: Optional[str] = None
    phone: Optional[str] = None

    for turn in dialogue.get("turns", []):
        for frame in turn.get("frames", []):
            for result in frame.get("service_results", []):
                if name is None:
                    name = result.get("customer_name") or result.get("name")
                if phone is None:
                    phone = result.get("phone_suffix") or result.get("phone")
            if name and phone:
                break
        if name and phone:
            break

    if name and phone:
        return f"{name}::{phone}"
    if name:
        return name
    return str(dialogue.get("dialogue_id", "unknown"))
