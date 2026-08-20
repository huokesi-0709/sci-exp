from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProtocolChunk:
    evidence_id: str
    text: str
    source_org: str
    source_id: str = ""
    title: str = ""
    source_url: str = ""
    jurisdiction: str = ""
    target_population: str = ""
    version: str = ""
    effective_date: str = ""
    expiry_date: str = ""
    authority_level: int = 0
    hazard_types: tuple[str, ...] = field(default_factory=tuple)
    applicability: tuple[str, ...] = field(default_factory=tuple)
    status: str = "current"
    status_detail: str = ""
    source_tier: str = ""
    content_review_status: str = ""
    license_status: str = ""
    redistribution_status: str = ""
    file_sha256: str = ""
    parent_source_id: str = ""
    parent_file_sha256: str = ""
    source_locator: str = ""
    derivation_method: str = ""
    derivation_rule_reason: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ProtocolChunk":
        return cls(
            evidence_id=str(value["evidence_id"]).strip(),
            text=str(value["text"]).strip(),
            source_org=str(value["source_org"]).strip(),
            source_id=str(value.get("source_id", "")).strip(),
            title=str(value.get("title", "")).strip(),
            source_url=str(value.get("source_url", "")).strip(),
            jurisdiction=str(value.get("jurisdiction", "")).strip(),
            target_population=str(value.get("target_population", "")).strip(),
            version=str(value.get("version", "")).strip(),
            effective_date=str(value.get("effective_date", "")).strip(),
            expiry_date=str(value.get("expiry_date", "")).strip(),
            authority_level=int(value.get("authority_level", 0)),
            hazard_types=tuple(str(item) for item in value.get("hazard_types", [])),
            applicability=tuple(str(item) for item in value.get("applicability", [])),
            status=str(value.get("status", "current")),
            status_detail=str(value.get("status_detail", "")).strip(),
            source_tier=str(value.get("source_tier", "")).strip(),
            content_review_status=str(
                value.get("content_review_status", "")
            ).strip(),
            license_status=str(value.get("license_status", "")).strip(),
            redistribution_status=str(
                value.get("redistribution_status", "")
            ).strip(),
            file_sha256=str(value.get("file_sha256", "")).strip(),
            parent_source_id=str(value.get("parent_source_id", "")).strip(),
            parent_file_sha256=str(
                value.get("parent_file_sha256", "")
            ).strip(),
            source_locator=str(value.get("source_locator", "")).strip(),
            derivation_method=str(
                value.get("derivation_method", "")
            ).strip(),
            derivation_rule_reason=str(
                value.get("derivation_rule_reason", "")
            ).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["hazard_types"] = list(self.hazard_types)
        value["applicability"] = list(self.applicability)
        return value


@dataclass(frozen=True)
class QueryRecord:
    query_id: str
    text: str
    disaster_type: str
    query_type: str
    risk_level: int
    language: str
    should_fallback: bool
    gold_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    required_actions: tuple[str, ...] = field(default_factory=tuple)
    prohibited_actions: tuple[str, ...] = field(default_factory=tuple)
    source_group_id: str = ""
    split: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "QueryRecord":
        known = {
            "query_id",
            "text",
            "disaster_type",
            "query_type",
            "risk_level",
            "language",
            "should_fallback",
            "gold_evidence_ids",
            "required_actions",
            "prohibited_actions",
            "source_group_id",
            "split",
        }
        return cls(
            query_id=str(value["query_id"]).strip(),
            text=str(value["text"]).strip(),
            disaster_type=str(value["disaster_type"]).strip(),
            query_type=str(value["query_type"]).strip(),
            risk_level=_risk_level_to_int(value["risk_level"]),
            language=str(value.get("language", "unknown")).strip(),
            should_fallback=bool(value.get("should_fallback", False)),
            gold_evidence_ids=tuple(str(item) for item in value.get("gold_evidence_ids", [])),
            required_actions=tuple(str(item) for item in value.get("required_actions", [])),
            prohibited_actions=tuple(str(item) for item in value.get("prohibited_actions", [])),
            source_group_id=str(value.get("source_group_id", "")).strip(),
            split=str(value.get("split", "")).strip(),
            metadata={key: item for key, item in value.items() if key not in known},
        )

    def to_dict(self) -> dict[str, Any]:
        value = {
            "query_id": self.query_id,
            "text": self.text,
            "disaster_type": self.disaster_type,
            "query_type": self.query_type,
            "risk_level": self.risk_level,
            "language": self.language,
            "should_fallback": self.should_fallback,
            "gold_evidence_ids": list(self.gold_evidence_ids),
            "required_actions": list(self.required_actions),
            "prohibited_actions": list(self.prohibited_actions),
            "source_group_id": self.source_group_id,
            "split": self.split,
        }
        value.update(self.metadata)
        return value


def _risk_level_to_int(value: Any) -> int:
    """Accept canonical L0-L3 labels while keeping the internal numeric API."""
    if isinstance(value, str) and value.strip().upper() in {"L0", "L1", "L2", "L3"}:
        return int(value.strip()[1])
    return int(value)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk: ProtocolChunk
    score: float
    rank: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_id": self.chunk.evidence_id,
            "score": self.score,
            "rank": self.rank,
            "text": self.chunk.text,
            "source_org": self.chunk.source_org,
            "version": self.chunk.version,
            "status": self.chunk.status,
        }
