"""Stable brief identity embedded in the local run-record seam."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Any

from .model import ResearchBrief


def _json_default(value: object) -> str:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"unsupported hash value: {type(value).__name__}")


def brief_content_hash(brief: ResearchBrief) -> str:
    """Hash all content and lifecycle fields using canonical JSON."""
    payload = json.dumps(
        asdict(brief), sort_keys=True, separators=(",", ":"), default=_json_default
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

