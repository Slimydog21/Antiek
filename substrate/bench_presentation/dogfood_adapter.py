"""Dogfood-judgment → Antiek-bench usage-event adapter (pure).

The production-signal half of the recursive benchmark loop (ask #11). The
operator reads a book, asks questions, and judges the answers (good/bad). Those
judgments are the REAL production signal about which models perform well on
reading/research tasks. This adapter turns those judgments into the
``{task, success}`` events that ``propose_next_week_weights`` consumes to
re-weight the benchmark weekly.

Without this adapter, the recursive loop is architecturally broken: usage-learn
has no events, and the benchmark never learns from real usage.

**Pure transformation** against the pinned §2 contract shapes. The adapter takes
already-read judged-answer rows (the caller resolves them from the event log via
the producer's accessor) and maps:

    verdict ∈ {"good", "bad"}  →  success = (verdict == "good")

Hard-to-vary invariants (each is a test):

1. **Empty rows → incomplete, no invented events.** ``incomplete=True`` when no
   valid events are produced — mirrors usage-learn's incomplete-on-empty.
2. **success is real bool; reject non-bool.** A verdict not in ``{"good","bad"}``
   is SKIPPED + counted, never coerced (mirrors ``_as_bool_success``).
3. **No resolvable parent answer → skip.** Can't attribute a model; counted in
   notes. Never invents a model_id.
4. **Ungrounded answer (no dispatch receipt) → skip.** No model to learn about;
   no learning signal for model-ranking. Counted honestly.
5. **Owner-scoped.** Only the owner's own judgments feed the owner's bench —
   cross-owner rows are skipped (privacy + relevance).

The adapter is advisory (``authority="dogfood_adapter_advisory"``): it produces
evidence, never routing authority. Model choice and spend remain operator-controlled.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

GOOD_VERDICTS = frozenset({"good"})
BAD_VERDICTS = frozenset({"bad"})
VALID_VERDICTS = GOOD_VERDICTS | BAD_VERDICTS

# The base task family (matches usage-learn's {task}::edge_cases convention).
TALK_TO_BOOK_TASK = "read.talk_to_book"


class DogfoodAdapterError(ValueError):
    """Fail-closed: malformed input that can't be attributed."""


@dataclass(frozen=True)
class UsageEvent:
    """One event for ``propose_next_week_weights``: {task, success}."""

    task: str
    success: bool


@dataclass(frozen=True)
class DogfoodAdapterResult:
    """The adapter's output: events + honest accounting."""

    events: list[UsageEvent] = field(default_factory=list)
    skipped_non_bool: int = 0
    skipped_no_model: int = 0
    skipped_no_parent: int = 0
    skipped_wrong_owner: int = 0
    incomplete: bool = True
    notes: list[str] = field(default_factory=list)
    authority: str = "dogfood_adapter_advisory"
    week_id: str = ""


def dogfood_judgments_to_usage_events(
    judged_answer_rows: Sequence[Mapping[str, object]],
    *,
    owner_id: str,
    week_id: str = "",
) -> DogfoodAdapterResult:
    """Transform dogfood judgment rows into bench usage events.

    Each row is expected to carry (per the pinned §2 contract from #1777):
    - ``verdict``: ``"good"`` or ``"bad"`` (the operator's judgment)
    - ``owner_id``: the owner who judged (owner-scoped filtering)
    - ``answer_id`` / ``parent_event_id``: link to the parent ``read.book_answered``
    - ``model`` (optional, from the resolved parent): the model that produced the answer
    - ``grounded`` (optional, from the parent): whether a dispatch receipt exists

    Rows missing required fields or with invalid verdicts are SKIPPED + counted,
    never coerced or invented.
    """

    if not owner_id.strip():
        raise DogfoodAdapterError("owner_id must be non-empty")

    events: list[UsageEvent] = []
    skipped_non_bool = 0
    skipped_no_model = 0
    skipped_no_parent = 0
    skipped_wrong_owner = 0

    for row in judged_answer_rows:
        # Owner scoping: only the owner's own judgments feed the owner's bench.
        row_owner = row.get("owner_id")
        if row_owner != owner_id:
            skipped_wrong_owner += 1
            continue

        # Verdict must be a real string in {good, bad} — reject non-bool, never coerce.
        verdict = row.get("verdict")
        if not isinstance(verdict, str) or verdict not in VALID_VERDICTS:
            skipped_non_bool += 1
            continue

        # Resolve the parent answer to attribute a model.
        answer_id = row.get("answer_id") or row.get("parent_event_id")
        if not answer_id:
            skipped_no_parent += 1
            continue

        # Must have a model to learn about (grounded dispatch receipt).
        model = row.get("model")
        grounded = row.get("grounded")
        if not model or grounded is False:
            skipped_no_model += 1
            continue

        events.append(
            UsageEvent(
                task=TALK_TO_BOOK_TASK,
                success=(verdict in GOOD_VERDICTS),
            )
        )

    incomplete = len(events) == 0
    notes: list[str] = []
    if skipped_non_bool:
        notes.append(f"{skipped_non_bool} row(s) skipped: non-bool/unknown verdict")
    if skipped_no_model:
        notes.append(f"{skipped_no_model} row(s) skipped: ungrounded or no-model answer")
    if skipped_no_parent:
        notes.append(f"{skipped_no_parent} row(s) skipped: no resolvable parent answer")
    if skipped_wrong_owner:
        notes.append(f"{skipped_wrong_owner} row(s) skipped: wrong owner")
    if incomplete:
        notes.append("no valid events produced — usage-learn will report incomplete")

    return DogfoodAdapterResult(
        events=events,
        skipped_non_bool=skipped_non_bool,
        skipped_no_model=skipped_no_model,
        skipped_no_parent=skipped_no_parent,
        skipped_wrong_owner=skipped_wrong_owner,
        incomplete=incomplete,
        notes=notes,
        authority="dogfood_adapter_advisory",
        week_id=week_id,
    )


__all__ = [
    "BAD_VERDICTS",
    "DogfoodAdapterError",
    "DogfoodAdapterResult",
    "GOOD_VERDICTS",
    "TALK_TO_BOOK_TASK",
    "UsageEvent",
    "VALID_VERDICTS",
    "dogfood_judgments_to_usage_events",
]
