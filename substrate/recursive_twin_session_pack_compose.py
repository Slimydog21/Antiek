"""Recursive twin session pack compose (pure, advisory).

Packs caller-supplied twin insights/questions for a session.
twin_store_mutated is always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RecursiveTwinSessionPackComposeError(ValueError):
    """Fail-closed validation for twin session pack compose."""


@dataclass(frozen=True)
class RecursiveTwinSessionPack:
    session_id: str
    asset_ids: tuple[str, ...]
    insight_count: int
    question_count: int
    bound_count: int
    unbound_count: int
    pack_ready: bool
    twin_store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "asset_ids": list(self.asset_ids),
            "insight_count": self.insight_count,
            "question_count": self.question_count,
            "bound_count": self.bound_count,
            "unbound_count": self.unbound_count,
            "pack_ready": self.pack_ready,
            "twin_store_mutated": False,
            "notes": list(self.notes),
            "authority": "recursive_twin_session_pack_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinSessionPackComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list):
        raise RecursiveTwinSessionPackComposeError(f"{field} must be an array")
    out: list[str] = []
    for i, s in enumerate(value):
        if not isinstance(s, str) or not s.strip():
            raise RecursiveTwinSessionPackComposeError(
                f"{field}[{i}] must be a non-empty string"
            )
        out.append(s.strip())
    return out


def compose_recursive_twin_session_pack(
    *,
    session_id: object,
    members: object,
) -> RecursiveTwinSessionPack:
    """Compose session twin pack. Never mutates twin store."""
    sid = _require_nonempty(session_id, field="session_id")
    if not isinstance(members, list) or len(members) == 0:
        raise RecursiveTwinSessionPackComposeError(
            "members must be a non-empty array"
        )

    notes: list[str] = [
        "twin_store_mutated=false — session pack intent only",
        "insights/questions are caller-supplied only (no invent content)",
    ]
    asset_ids: list[str] = []
    seen: set[str] = set()
    insight_count = 0
    question_count = 0
    bound_count = 0
    unbound_count = 0

    for i, m in enumerate(members):
        if not isinstance(m, dict):
            raise RecursiveTwinSessionPackComposeError(
                f"members[{i}] must be an object"
            )
        asset_id = _require_nonempty(
            m.get("asset_id"), field=f"members[{i}].asset_id"
        )
        if asset_id in seen:
            raise RecursiveTwinSessionPackComposeError(
                f"duplicate asset_id in members: {asset_id}"
            )
        seen.add(asset_id)
        asset_ids.append(asset_id)

        twin_bound = m.get("twin_bound")
        if not isinstance(twin_bound, bool):
            raise RecursiveTwinSessionPackComposeError(
                f"members[{i}].twin_bound must be an explicit boolean"
            )
        if twin_bound:
            bound_count += 1
        else:
            unbound_count += 1

        insights = _require_string_list(
            m.get("insights"), field=f"members[{i}].insights"
        )
        questions = _require_string_list(
            m.get("questions"), field=f"members[{i}].questions"
        )
        insight_count += len(insights)
        question_count += len(questions)

        search_hits = m.get("search_hits")
        if search_hits is not None:
            if (
                isinstance(search_hits, bool)
                or not isinstance(search_hits, int)
                or search_hits < 0
            ):
                raise RecursiveTwinSessionPackComposeError(
                    f"members[{i}].search_hits must be non-negative integer or null"
                )

    if insight_count == 0 and question_count == 0:
        notes.append(
            "no insights/questions supplied — pack scaffold only (no invent content)"
        )
    else:
        notes.append(
            f"insights={insight_count} questions={question_count} caller-supplied only"
        )

    pack_ready = bound_count >= 1 and (insight_count > 0 or question_count > 0)
    if not pack_ready:
        if bound_count < 1:
            notes.append("pack_ready=false — need ≥1 twin_bound member")
        else:
            notes.append(
                "pack_ready=false — bound twins present but no insights/questions"
            )
    else:
        notes.append(
            "pack_ready=true — substrate pack ready for merge/search intent"
        )
    notes.append("twin_store_mutated=false")

    return RecursiveTwinSessionPack(
        session_id=sid,
        asset_ids=tuple(asset_ids),
        insight_count=insight_count,
        question_count=question_count,
        bound_count=bound_count,
        unbound_count=unbound_count,
        pack_ready=pack_ready,
        twin_store_mutated=False,
        notes=tuple(notes),
        authority="recursive_twin_session_pack_compose_advisory",
    )


__all__ = [
    "RecursiveTwinSessionPack",
    "RecursiveTwinSessionPackComposeError",
    "compose_recursive_twin_session_pack",
]
