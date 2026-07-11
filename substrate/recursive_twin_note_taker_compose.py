"""Recursive twin note-taker compose (pure).

twin_written, prompts_injected, live_dispatch_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class RecursiveTwinNoteTakerComposeError(ValueError):
    """Fail-closed validation for recursive twin note-taker."""


@dataclass(frozen=True)
class RecursiveTwinNoteTakerCompose:
    parent_asset_id: str
    existing_twin_asset_id: str | None
    source_excerpt_chars: int
    focus_question_count: int
    twin_scaffold_sections: tuple[str, ...]
    twin_propose_ready: bool
    twin_written: bool
    prompts_injected: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "parent_asset_id": self.parent_asset_id,
            "existing_twin_asset_id": self.existing_twin_asset_id,
            "source_excerpt_chars": self.source_excerpt_chars,
            "focus_question_count": self.focus_question_count,
            "twin_scaffold_sections": list(self.twin_scaffold_sections),
            "twin_propose_ready": self.twin_propose_ready,
            "twin_written": False,
            "prompts_injected": False,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "recursive_twin_note_taker_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RecursiveTwinNoteTakerComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_recursive_twin_note_taker(
    *,
    parent_asset_id: object,
    source_excerpt: object,
    operator_ack: object,
    existing_twin_asset_id: object | None = None,
    focus_questions: object | None = None,
) -> RecursiveTwinNoteTakerCompose:
    """Propose twin note-taker pack. Never writes or dispatches."""
    if not isinstance(operator_ack, bool):
        raise RecursiveTwinNoteTakerComposeError(
            "operator_ack must be an explicit boolean"
        )
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    excerpt = _require_nonempty(source_excerpt, field="source_excerpt")

    notes: list[str] = [
        "twin_written=false — twin document not created/updated",
        "prompts_injected=false — no live LLM note-taker prompt injection",
        "live_dispatch_authorized=false — no automatic twin agent dispatch",
        "insights/questions not invented — scaffold only + caller focus_questions",
    ]

    existing: str | None = None
    if existing_twin_asset_id is not None:
        existing = _require_nonempty(
            existing_twin_asset_id, field="existing_twin_asset_id"
        )
        notes.append(f"existing_twin_asset_id={existing}")
    else:
        notes.append("existing_twin_asset_id=null — new twin proposal")

    sections: list[str] = [
        f'<section data-role="source-excerpt" data-parent="{parent}">{excerpt}</section>',
        f'<section data-role="insights-placeholder" data-parent="{parent}"><!-- caller/LLM fills; pure layer does not invent --></section>',
        f'<section data-role="questions-placeholder" data-parent="{parent}"><!-- caller/LLM fills; pure layer does not invent --></section>',
    ]

    focus_question_count = 0
    if focus_questions is not None:
        if not isinstance(focus_questions, list):
            raise RecursiveTwinNoteTakerComposeError(
                "focus_questions must be an array when set"
            )
        for i, q in enumerate(focus_questions):
            qq = _require_nonempty(q, field=f"focus_questions[{i}]")
            sections.append(
                f'<section data-role="focus-question" data-parent="{parent}">{qq}</section>'
            )
            focus_question_count += 1

    notes.append(
        f"source_excerpt_chars={len(excerpt)} · focus_question_count={focus_question_count}"
    )

    twin_propose_ready = operator_ack is True
    if not twin_propose_ready:
        notes.append("twin_propose_ready=false — operator_ack required")
    else:
        notes.append(
            "twin_propose_ready=true — provisional twin scaffold ready (still twin_written=false)"
        )
    notes.extend(
        (
            "twin_written=false",
            "prompts_injected=false",
            "live_dispatch_authorized=false",
        )
    )

    return RecursiveTwinNoteTakerCompose(
        parent_asset_id=parent,
        existing_twin_asset_id=existing,
        source_excerpt_chars=len(excerpt),
        focus_question_count=focus_question_count,
        twin_scaffold_sections=tuple(sections),
        twin_propose_ready=twin_propose_ready,
        twin_written=False,
        prompts_injected=False,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="recursive_twin_note_taker_compose_advisory",
    )


__all__ = [
    "RecursiveTwinNoteTakerCompose",
    "RecursiveTwinNoteTakerComposeError",
    "compose_recursive_twin_note_taker",
]
