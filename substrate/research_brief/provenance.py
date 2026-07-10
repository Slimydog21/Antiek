"""Stable brief identity embedded in the local run-record seam."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .model import BudgetTuple, ResearchBrief


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported hash value: {type(value).__name__}")


def brief_content_hash(brief: ResearchBrief) -> str:
    """Hash editable content only, excluding lifecycle state and events."""
    budget = brief.budget
    assert isinstance(budget, BudgetTuple)
    payload = json.dumps(
        {
            "question": brief.question,
            "scope": brief.scope,
            "exclusions": brief.exclusions,
            "source_preferences": brief.source_preferences,
            "budget": asdict(budget),
            "price_ceiling": brief.price_ceiling,
            "unattended": brief.unattended,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
    ).encode()
    return sha256(payload).hexdigest()


@dataclass(frozen=True)
class BriefRunRecord:
    """Local additive record until SPR-01 exposes an importable run record."""

    run_id: str
    brief_id: str
    brief_hash: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def link_run(run_id: str, brief: ResearchBrief) -> BriefRunRecord:
    if not run_id.strip():
        raise ValueError("run_id is required")
    return BriefRunRecord(run_id, brief.brief_id, brief_content_hash(brief))
