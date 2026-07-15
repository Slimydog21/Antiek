"""Machine-checkable evidence required before a paid hard-ceiling route ships."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from .cost_projection import CostCatalogEntry

_REGISTRY_PATH = Path(__file__).with_name("provider_qualification.json")
_REQUIRED_DIMENSIONS = frozenset(
    {
        "pinned_pricing",
        "durable_idempotency",
        "hidden_retries_disabled",
        "authoritative_reconciliation",
        "stable_provider_evidence",
    }
)


class EvidenceStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNPROVEN = "unproven"


class QualificationVerdict(StrEnum):
    QUALIFIED = "qualified"
    REFUSED = "refused"


@dataclass(frozen=True)
class QualificationEvidence:
    status: EvidenceStatus
    source_url: str
    finding: str


@dataclass(frozen=True)
class ProviderQualification:
    provider: str
    model: str
    operation: str
    checked_at: str
    verdict: QualificationVerdict
    evidence: Mapping[str, QualificationEvidence]

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", MappingProxyType(dict(self.evidence)))

    @property
    def route_key(self) -> tuple[str, str, str]:
        return self.provider, self.model, self.operation

    @property
    def fully_qualified(self) -> bool:
        return (
            self.verdict is QualificationVerdict.QUALIFIED
            and set(self.evidence) == _REQUIRED_DIMENSIONS
            and all(item.status is EvidenceStatus.PASS for item in self.evidence.values())
        )


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"provider qualification {field} must be non-empty text")
    return value


def _parse_evidence(raw: object) -> dict[str, QualificationEvidence]:
    if not isinstance(raw, dict) or set(raw) != _REQUIRED_DIMENSIONS:
        raise ValueError("provider qualification must address exactly the five dimensions")
    parsed: dict[str, QualificationEvidence] = {}
    for dimension, item in raw.items():
        if not isinstance(item, dict) or set(item) != {"status", "source_url", "finding"}:
            raise ValueError(f"qualification evidence {dimension!r} has an invalid shape")
        source_url = _required_text(item["source_url"], "source_url")
        parsed_url = urlparse(source_url)
        if parsed_url.scheme != "https" or not parsed_url.netloc:
            raise ValueError("qualification evidence sources must be HTTPS URLs")
        parsed[dimension] = QualificationEvidence(
            status=EvidenceStatus(item["status"]),
            source_url=source_url,
            finding=_required_text(item["finding"], "finding"),
        )
    return parsed


def load_provider_qualifications(
    path: Path = _REGISTRY_PATH,
) -> tuple[ProviderQualification, ...]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or set(raw) != {"schema_version", "qualifications"}:
        raise ValueError("provider qualification registry has an invalid root shape")
    if raw["schema_version"] != 1 or not isinstance(raw["qualifications"], list):
        raise ValueError("unsupported provider qualification registry schema")

    qualifications: list[ProviderQualification] = []
    for item in raw["qualifications"]:
        if not isinstance(item, dict) or set(item) != {
            "provider",
            "model",
            "operation",
            "checked_at",
            "verdict",
            "evidence",
        }:
            raise ValueError("provider qualification entry has an invalid shape")
        qualification = ProviderQualification(
            provider=_required_text(item["provider"], "provider"),
            model=_required_text(item["model"], "model"),
            operation=_required_text(item["operation"], "operation"),
            checked_at=_required_text(item["checked_at"], "checked_at"),
            verdict=QualificationVerdict(item["verdict"]),
            evidence=_parse_evidence(item["evidence"]),
        )
        if qualification.verdict is QualificationVerdict.QUALIFIED and not all(
            evidence.status is EvidenceStatus.PASS for evidence in qualification.evidence.values()
        ):
            raise ValueError("qualified provider route has non-passing evidence")
        qualifications.append(qualification)

    keys = [item.route_key for item in qualifications]
    if len(keys) != len(set(keys)):
        raise ValueError("provider qualification registry contains duplicate routes")
    return tuple(qualifications)


def require_paid_catalog_qualifications(
    entries: tuple[CostCatalogEntry, ...],
    qualifications: tuple[ProviderQualification, ...] | None = None,
) -> None:
    """Reject checked-in paid eligibility without exact, fully passing evidence."""

    registry = load_provider_qualifications() if qualifications is None else qualifications
    qualified_routes = {item.route_key for item in registry if item.fully_qualified}
    for entry in entries:
        claims_hard_capabilities = (
            entry.paid_service
            and entry.durable_idempotency
            and entry.authoritative_reconciliation
            and entry.hidden_retries_disabled
        )
        route_key = (entry.provider, entry.model, entry.operation)
        if claims_hard_capabilities and route_key not in qualified_routes:
            raise ValueError(
                "paid catalog route claims hard-ceiling capabilities without "
                f"fully passing provider qualification: {route_key!r}"
            )
