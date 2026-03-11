"""
安逸花外呼 · 增量精准知识库 · 数据模型

本模块定义了从安逸花外呼对话中提取的结构化知识的数据模型。

设计原则：
    · 精准 (Precise)：每条知识都携带来源证据（session_id、原文区间）
    · 可解释 (Interpretable)：每条知识均有明确的槽位名称和自然语言描述
    · 支持增量更新 (Incremental)：ConflictEntry 记录历史冲突，不丢弃旧值
    · 可扩展 (Extensible)：CustomerRecord 支持任意 slot_name，Schema 不耦合业务

典型使用::

    from contextmind.scenarios.anyihua.knowledge_base.schema import (
        SlotEvidence, SlotFact, CustomerRecord, ConflictEntry, KBStats,
    )

    evidence = SlotEvidence(
        session_id="2025102811215858702023182",
        value="高先生",
        char_start=5,
        char_end=8,
        alignment_status="match_exact",
        confidence=1.0,
    )
    fact = SlotFact(name="customer_name", current_evidence=evidence)
    record = CustomerRecord(customer_id="高先生::六七八")
    record.facts["customer_name"] = fact
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


# --------------------------------------------------------------------------- #
# 槽位证据：一次提取结果的完整溯源信息
# --------------------------------------------------------------------------- #


@dataclass
class SlotEvidence:
    """
    槽位值提取的完整溯源信息。

    每次提取都保留原始证据，支持事后审计和可解释性分析。

    属性:
        session_id:        来源对话的唯一标识
        value:             提取到的槽位值（字符串形式）
        char_start:        在原始对话文本中的字符起始位置（含；None 表示对齐失败）
        char_end:          在原始对话文本中的字符结束位置（不含；None 表示对齐失败）
        alignment_status:  langextract 对齐状态（"match_exact" / "match_lesser" /
                           "match_fuzzy" / None）
        confidence:        提取置信度（0.0–1.0；由对齐质量自动推导或手动指定）
        extracted_at:      提取时间戳
        speaker:           发言角色（"SYSTEM" 或 "USER"；None 表示未知）
        extraction_text:   langextract 回溯定位所用的原始文本片段
    """

    session_id: str
    value: str
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    alignment_status: Optional[str] = None
    confidence: float = 0.5
    extracted_at: datetime = field(default_factory=datetime.now)
    speaker: Optional[str] = None
    extraction_text: Optional[str] = None

    def is_aligned(self) -> bool:
        """返回该提取结果是否有有效的原文定位。"""
        return self.char_start is not None and self.char_end is not None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的字典（datetime → ISO 字符串）。"""
        return {
            "session_id": self.session_id,
            "value": self.value,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "alignment_status": self.alignment_status,
            "confidence": self.confidence,
            "extracted_at": self.extracted_at.isoformat(),
            "speaker": self.speaker,
            "extraction_text": self.extraction_text,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlotEvidence":
        """从字典反序列化。"""
        extracted_at = data.get("extracted_at")
        if isinstance(extracted_at, str):
            extracted_at = datetime.fromisoformat(extracted_at)
        elif extracted_at is None:
            extracted_at = datetime.now()
        return cls(
            session_id=data["session_id"],
            value=data["value"],
            char_start=data.get("char_start"),
            char_end=data.get("char_end"),
            alignment_status=data.get("alignment_status"),
            confidence=float(data.get("confidence", 0.5)),
            extracted_at=extracted_at,
            speaker=data.get("speaker"),
            extraction_text=data.get("extraction_text"),
        )


# --------------------------------------------------------------------------- #
# 槽位事实：知识库中对某个槽位的当前认知及历史记录
# --------------------------------------------------------------------------- #


@dataclass
class SlotFact:
    """
    知识库中对特定槽位的当前认知。

    current_evidence 持有最新（置信度最高）的证据；
    history 按时间倒序存储所有历史证据，支持回滚和审计。

    属性:
        name:             槽位名称（与 SGD schema.json 中的 slot.name 对应）
        current_evidence: 当前采信的最佳证据
        history:          历史证据列表（最新在前）
    """

    name: str
    current_evidence: Optional[SlotEvidence] = None
    history: List[SlotEvidence] = field(default_factory=list)

    @property
    def current_value(self) -> Optional[str]:
        """返回当前槽位值，若无证据则返回 None。"""
        return self.current_evidence.value if self.current_evidence else None

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的字典。"""
        return {
            "name": self.name,
            "current_evidence": (
                self.current_evidence.to_dict() if self.current_evidence else None
            ),
            "history": [e.to_dict() for e in self.history],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SlotFact":
        """从字典反序列化。"""
        current_evidence = data.get("current_evidence")
        if current_evidence is not None:
            current_evidence = SlotEvidence.from_dict(current_evidence)
        history = [SlotEvidence.from_dict(e) for e in data.get("history", [])]
        return cls(
            name=data["name"],
            current_evidence=current_evidence,
            history=history,
        )


# --------------------------------------------------------------------------- #
# 冲突记录：当新证据与已有值不一致时的记录
# --------------------------------------------------------------------------- #


@dataclass
class ConflictEntry:
    """
    记录槽位值的冲突事件。

    当同一客户的同一槽位在不同会话中出现不同值时，
    ConflictEntry 会被写入 CustomerRecord.conflicts，
    以供人工审查或自动冲突消解策略使用。

    属性:
        slot_name:        冲突槽位名称
        existing_value:   被替换前的旧值
        new_value:        触发冲突的新值
        existing_session: 旧值来源的会话 ID
        new_session:      新值来源的会话 ID
        resolution:       冲突消解结果（"kept_existing" / "replaced_by_new" /
                          "manual" / None 表示未消解）
        detected_at:      冲突检测时间戳
    """

    slot_name: str
    existing_value: str
    new_value: str
    existing_session: str
    new_session: str
    resolution: Optional[str] = None
    detected_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的字典。"""
        return {
            "slot_name": self.slot_name,
            "existing_value": self.existing_value,
            "new_value": self.new_value,
            "existing_session": self.existing_session,
            "new_session": self.new_session,
            "resolution": self.resolution,
            "detected_at": self.detected_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConflictEntry":
        """从字典反序列化。"""
        detected_at = data.get("detected_at")
        if isinstance(detected_at, str):
            detected_at = datetime.fromisoformat(detected_at)
        elif detected_at is None:
            detected_at = datetime.now()
        return cls(
            slot_name=data["slot_name"],
            existing_value=data["existing_value"],
            new_value=data["new_value"],
            existing_session=data["existing_session"],
            new_session=data["new_session"],
            resolution=data.get("resolution"),
            detected_at=detected_at,
        )


# --------------------------------------------------------------------------- #
# 客户记录：单个客户的完整知识聚合
# --------------------------------------------------------------------------- #


@dataclass
class CustomerRecord:
    """
    单个客户在知识库中的完整记录。

    customer_id 由应用层按业务规则生成（如 "姓名::手机尾号"），
    知识库本身不约束其格式，保持可扩展性。

    属性:
        customer_id:   唯一客户标识（由调用方定义）
        facts:         槽位名称 → SlotFact 的字典，存放所有已知事实
        session_ids:   该客户出现过的所有会话 ID（按时间排序）
        conflicts:     检测到的所有冲突记录
        created_at:    记录首次创建时间
        updated_at:    记录最后更新时间
    """

    customer_id: str
    facts: Dict[str, SlotFact] = field(default_factory=dict)
    session_ids: List[str] = field(default_factory=list)
    conflicts: List[ConflictEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def get_slot_value(self, slot_name: str) -> Optional[str]:
        """返回指定槽位的当前值，不存在时返回 None。"""
        fact = self.facts.get(slot_name)
        return fact.current_value if fact else None

    def list_known_slots(self) -> List[str]:
        """返回所有已知槽位名称列表。"""
        return [name for name, fact in self.facts.items() if fact.current_value is not None]

    def to_dict(self) -> Dict[str, Any]:
        """序列化为可 JSON 化的字典。"""
        return {
            "customer_id": self.customer_id,
            "facts": {k: v.to_dict() for k, v in self.facts.items()},
            "session_ids": self.session_ids,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CustomerRecord":
        """从字典反序列化。"""
        created_at = data.get("created_at")
        updated_at = data.get("updated_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()
        facts = {k: SlotFact.from_dict(v) for k, v in data.get("facts", {}).items()}
        conflicts = [ConflictEntry.from_dict(c) for c in data.get("conflicts", [])]
        return cls(
            customer_id=data["customer_id"],
            facts=facts,
            session_ids=data.get("session_ids", []),
            conflicts=conflicts,
            created_at=created_at,
            updated_at=updated_at,
        )


# --------------------------------------------------------------------------- #
# 知识库统计信息
# --------------------------------------------------------------------------- #


@dataclass
class KBStats:
    """
    知识库整体统计信息快照。

    属性:
        total_customers:     客户记录总数
        total_sessions:      覆盖的会话总数
        total_facts:         所有客户的已知槽位事实总数（current_value 非 None）
        total_conflicts:     检测到的冲突总数
        conflict_rate:       冲突率（total_conflicts / total_facts，0 时为 0.0）
        aligned_facts:       有效原文定位的事实数（char_start 非 None）
        provenance_rate:     溯源完整率（aligned_facts / total_facts，0 时为 0.0）
    """

    total_customers: int = 0
    total_sessions: int = 0
    total_facts: int = 0
    total_conflicts: int = 0
    conflict_rate: float = 0.0
    aligned_facts: int = 0
    provenance_rate: float = 0.0

    def __str__(self) -> str:
        return (
            f"KBStats("
            f"customers={self.total_customers}, "
            f"sessions={self.total_sessions}, "
            f"facts={self.total_facts}, "
            f"conflicts={self.total_conflicts} ({self.conflict_rate:.1%}), "
            f"provenance={self.aligned_facts}/{self.total_facts} "
            f"({self.provenance_rate:.1%})"
            f")"
        )
