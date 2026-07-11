"""NotDiamond shadow log — advisory only (§16 REJECT as production router).

Operator vision residual: when evaluating model routers, log what NotDiamond
*would* recommend beside the local selection, without ever dispatching through ND.

Rules:
* ``enabled`` kill switch defaults to False (shadow off).
* Records are advisory; ``authority`` is always ``"shadow"`` — never production.
* No network I/O in this module (inject recommendation strings from outside).
* Never returns a model id as the production choice — only a shadow comparison.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


class NotDiamondShadowError(ValueError):
    """Malformed shadow log request."""


@dataclass(frozen=True)
class ShadowRecord:
    enabled: bool
    authority: str
    task: str
    local_model_id: str
    nd_recommended_model_id: str | None
    agreement: bool | None
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "authority": self.authority,
            "task": self.task,
            "local_model_id": self.local_model_id,
            "nd_recommended_model_id": self.nd_recommended_model_id,
            "agreement": self.agreement,
            "notes": list(self.notes),
        }


def record_shadow_comparison(
    *,
    task: str,
    local_model_id: str,
    nd_recommended_model_id: str | None = None,
    enabled: bool = False,
    extra_notes: Sequence[str] | None = None,
) -> ShadowRecord:
    """Build an advisory shadow comparison record.

    When ``enabled`` is False, still returns a record with notes that shadow
    is off — never fabricates an ND recommendation.
    """
    t = (task or "").strip() or "general"
    local = (local_model_id or "").strip()
    if not local:
        raise NotDiamondShadowError("local_model_id must be non-empty")

    if enabled is not True:
        return ShadowRecord(
            enabled=False,
            authority="shadow",
            task=t,
            local_model_id=local,
            nd_recommended_model_id=None,
            agreement=None,
            notes=[
                "kill_switch=off — NotDiamond shadow disabled by default",
                "authority=shadow — never production dispatch",
                "no ND recommendation recorded while disabled",
            ],
        )

    nd = None if nd_recommended_model_id is None else str(nd_recommended_model_id).strip()
    if nd == "":
        nd = None

    agreement: bool | None
    if nd is None:
        agreement = None
        notes = [
            "kill_switch=on but nd_recommended_model_id missing — agreement unknown",
            "authority=shadow — never production dispatch",
        ]
    else:
        agreement = nd == local
        notes = [
            "kill_switch=on — shadow comparison recorded",
            "authority=shadow — never production dispatch",
            "agreement=true" if agreement else "agreement=false",
        ]

    if extra_notes:
        notes.extend(str(n) for n in extra_notes if str(n).strip())

    return ShadowRecord(
        enabled=True,
        authority="shadow",
        task=t,
        local_model_id=local,
        nd_recommended_model_id=nd,
        agreement=agreement,
        notes=notes,
    )


def assert_not_production_authority(record: ShadowRecord | Mapping[str, Any]) -> None:
    """Raise if a record claims production authority (fail closed)."""
    if isinstance(record, ShadowRecord):
        auth = record.authority
    else:
        auth = str(record.get("authority", ""))
    if auth != "shadow":
        raise NotDiamondShadowError(
            "NotDiamond shadow authority must be 'shadow', got " + repr(auth)
        )


__all__ = [
    "NotDiamondShadowError",
    "ShadowRecord",
    "assert_not_production_authority",
    "record_shadow_comparison",
]
