"""Twin chase/analysis feed compose (pure).

Feeds caller-supplied chase findings into recursive twin note-taker scaffold.
twin_written, record_persisted, prompts_injected, live_dispatch_authorized
always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.recursive_twin_note_taker_compose import (
    RecursiveTwinNoteTakerCompose,
    RecursiveTwinNoteTakerComposeError,
    compose_recursive_twin_note_taker,
)

VALID_KINDS = frozenset(("insight", "question", "claim", "data"))


class TwinChaseAnalysisFeedComposeError(ValueError):
    """Fail-closed validation for twin chase analysis feed."""


@dataclass(frozen=True)
class TwinChaseAnalysisFeedCompose:
    session_id: str
    parent_asset_id: str
    finding_count: int
    insight_count: int
    question_count: int
    twin: RecursiveTwinNoteTakerCompose
    mark_for_prompt_context: bool
    feed_ready: bool
    twin_written: bool
    record_persisted: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "finding_count": self.finding_count,
            "insight_count": self.insight_count,
            "question_count": self.question_count,
            "twin": self.twin.to_dict(),
            "mark_for_prompt_context": self.mark_for_prompt_context,
            "feed_ready": self.feed_ready,
            "twin_written": False,
            "record_persisted": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "twin_chase_analysis_feed_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinChaseAnalysisFeedComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_twin_chase_analysis_feed(
    *,
    parent_asset_id: object,
    session_id: object,
    findings: object,
    operator_ack: object,
    analysis_excerpt: object | None = None,
    existing_twin_asset_id: object | None = None,
    mark_for_prompt_context: object | None = None,
) -> TwinChaseAnalysisFeedCompose:
    """Feed chase findings into twin note-taker scaffold. Never writes."""
    if not isinstance(operator_ack, bool):
        raise TwinChaseAnalysisFeedComposeError(
            "operator_ack must be an explicit boolean"
        )
    session = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    if not isinstance(findings, list) or len(findings) == 0:
        raise TwinChaseAnalysisFeedComposeError(
            "findings must be a non-empty array"
        )

    mark = False if mark_for_prompt_context is None else mark_for_prompt_context
    if not isinstance(mark, bool):
        raise TwinChaseAnalysisFeedComposeError(
            "mark_for_prompt_context must be boolean when set"
        )

    notes: list[str] = [
        "twin_written=false — twin document not mutated",
        "record_persisted=false — session records not written",
        "prompts_injected=false — no live prompt mutation",
        "live_dispatch_authorized=false — no twin agent dispatch",
    ]

    focus_questions: list[str] = []
    insight_bodies: list[str] = []
    insight_count = 0
    question_count = 0
    seen: set[str] = set()

    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            raise TwinChaseAnalysisFeedComposeError(
                f"findings[{i}] must be an object"
            )
        source_id = _require_nonempty(
            f.get("source_id"), field=f"findings[{i}].source_id"
        )
        if source_id in seen:
            raise TwinChaseAnalysisFeedComposeError(
                f"duplicate findings source_id: {source_id}"
            )
        seen.add(source_id)
        body = _require_nonempty(f.get("body"), field=f"findings[{i}].body")
        kind = f.get("kind") or "insight"
        if kind not in VALID_KINDS:
            raise TwinChaseAnalysisFeedComposeError(
                f"findings[{i}].kind must be insight|question|claim|data"
            )
        if kind == "question":
            focus_questions.append(body)
            question_count += 1
        else:
            insight_bodies.append(f"[{kind}/{source_id}] {body}")
            insight_count += 1

    analysis: str | None = None
    if analysis_excerpt is not None:
        analysis = _require_nonempty(
            analysis_excerpt, field="analysis_excerpt"
        )

    excerpt_parts: list[str] = []
    if analysis is not None:
        excerpt_parts.append(f"analysis: {analysis}")
    excerpt_parts.extend(insight_bodies)
    if not excerpt_parts and not focus_questions:
        raise TwinChaseAnalysisFeedComposeError(
            "no feedable content after normalization"
        )
    source_excerpt = (
        "\n".join(excerpt_parts)
        if excerpt_parts
        else "\n".join(focus_questions)
    )

    notes.append(
        f"finding_count={len(findings)} · insights={insight_count} · questions={question_count}"
    )
    if mark:
        notes.append(
            "mark_for_prompt_context=true — candidates only; prompts_injected=false"
        )

    try:
        twin = compose_recursive_twin_note_taker(
            parent_asset_id=parent,
            source_excerpt=source_excerpt,
            existing_twin_asset_id=existing_twin_asset_id,
            operator_ack=operator_ack,
            focus_questions=focus_questions if focus_questions else None,
        )
    except RecursiveTwinNoteTakerComposeError as e:
        raise TwinChaseAnalysisFeedComposeError(str(e)) from e
    notes.extend(twin.notes)

    feed_ready = twin.twin_propose_ready and len(findings) > 0 and operator_ack
    if not feed_ready:
        notes.append(
            "feed_ready=false — operator_ack required"
            if not operator_ack
            else "feed_ready=false"
        )
    else:
        notes.append(
            "feed_ready=true — twin scaffold ready from chase feed; twin_written=false"
        )

    if (
        twin.twin_written is not False
        or twin.prompts_injected is not False
        or twin.live_dispatch_authorized is not False
    ):
        raise TwinChaseAnalysisFeedComposeError(
            "invariant: twin honesty flags must remain false"
        )

    notes.extend(
        (
            "twin_written=false",
            "record_persisted=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
        )
    )

    return TwinChaseAnalysisFeedCompose(
        session_id=session,
        parent_asset_id=parent,
        finding_count=len(findings),
        insight_count=insight_count,
        question_count=question_count,
        twin=twin,
        mark_for_prompt_context=mark,
        feed_ready=feed_ready,
        twin_written=False,
        record_persisted=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="twin_chase_analysis_feed_compose_advisory",
    )


def format_twin_chase_analysis_feed_summary(
    c: TwinChaseAnalysisFeedCompose,
) -> str:
    return (
        f"feed_ready={c.feed_ready} · findings={c.finding_count} · "
        f"insights={c.insight_count} · questions={c.question_count} · "
        f"twin_written=false · record_persisted=false · prompts_injected=false · "
        f"live_dispatch_authorized=false"
    )


__all__ = [
    "TwinChaseAnalysisFeedCompose",
    "TwinChaseAnalysisFeedComposeError",
    "compose_twin_chase_analysis_feed",
    "format_twin_chase_analysis_feed_summary",
]
