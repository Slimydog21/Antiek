"""AFF SPR-09 M1 — the frozen compounding-benchmark question set.

The immutable, operator-supplied question set the benchmark weighs the flywheel
against. Each question carries an explicit ``overlap_class`` declaring its
relationship to the seeded prior knowledge units — the operator's *claim* about
what should compound, recorded as data so the benchmark can TEST it rather than
assert it.

Cells (OPERATOR_INPUTS §2, which supersedes the sprint page's three-way
``{known_overlap, irrelevant_seed, no_seed}`` labels):

  * ``high_overlap``        — the headline cell. Seeded units directly answer or
                              accelerate the question. 5 questions: 3 external
                              (answerable from fetchable sources, so a cold arm's
                              cost is not dominated by failing to reach internal
                              facts), 1 synthesis-on-top (relevant seed but NO node
                              states the answer — the anti-tautology probe), and 1
                              internal-knowledge probe reported SEPARATELY, not
                              pooled into the headline.
  * ``partial_overlap``     — dose-response cell. Each seeded with a topically
                              adjacent note that helps framing but not the answer.
                              Load-bearing: the verdict requires high-overlap
                              savings > partial savings > control (≈0).
  * ``zero_overlap_control``— the validity gate. Four disjoint domains no seeded
                              node can accelerate. Each must stay FLAT. The
                              irrelevant-seed arm seeds the SAME node count as warm
                              but off-topic, so this cell isolates "relevance"
                              from "graph-presence".

The set is frozen by a content-addressed ``frozen_sha`` computed over the
canonical serialization of the questions (the sha field itself excluded), so a
second load returns the identical sha and any edit to a question, its overlap
class, or its seeded units changes the sha and is detectable. We follow the
``benchmarks/baseline.json`` idiom (``seed`` + a stable provenance hash) rather
than inventing a new fixture format, and mirror ``benchmarks/fixtures.py``'s
seed-as-mint-date convention.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass

# The three §2 cells. ``high_overlap`` is the headline; ``zero_overlap_control``
# is the validity gate; ``partial_overlap`` is the load-bearing dose-response
# middle. These are the only valid overlap classes — the loader rejects any
# other value (M1: every overlap_class valid).
OVERLAP_CLASSES: tuple[str, ...] = (
    "high_overlap",
    "partial_overlap",
    "zero_overlap_control",
)

# A high-overlap question that is the internal-mechanism probe is reported
# ALONGSIDE the headline, never pooled into it (§2 de-pooling). The set marks it
# with ``headline_pooled=False``; the rest of the high-overlap cell pools.
QUESTION_SET_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "question_set.json")


@dataclass(frozen=True)
class BenchmarkQuestion:
    """One frozen question + its operator-supplied overlap label.

    ``seeded_unit_ids`` names the prior-investigation knowledge units the
    question is labelled against — for the warm/irrelevant arms these drive what
    the deposit→retrieve→reuse surface is seeded with. ``headline_pooled``
    distinguishes the high-overlap external+synthesis questions (pooled into the
    headline delta) from the internal-mechanism probe (reported separately)."""

    question_id: str
    text: str
    overlap_class: str
    seeded_unit_ids: tuple[str, ...]
    headline_pooled: bool

    def __post_init__(self) -> None:
        if self.overlap_class not in OVERLAP_CLASSES:
            raise ValueError(
                f"{self.question_id}: invalid overlap_class {self.overlap_class!r}; "
                f"expected one of {OVERLAP_CLASSES}"
            )


@dataclass(frozen=True)
class QuestionSet:
    """The loaded, frozen question set. ``frozen_sha`` is content-addressed over
    the canonical question serialization; ``seed`` drives the benchmark's
    deterministic run harness."""

    questions: tuple[BenchmarkQuestion, ...]
    seed: int
    frozen_sha: str
    version: str

    def by_class(self, overlap_class: str) -> list[BenchmarkQuestion]:
        return [q for q in self.questions if q.overlap_class == overlap_class]

    def headline_questions(self) -> list[BenchmarkQuestion]:
        """The high-overlap external+synthesis questions pooled into the
        headline delta (the internal-mechanism probe is excluded)."""
        return [
            q for q in self.questions
            if q.overlap_class == "high_overlap" and q.headline_pooled
        ]

    def control_questions(self) -> list[BenchmarkQuestion]:
        return self.by_class("zero_overlap_control")

    def __len__(self) -> int:
        return len(self.questions)


def _canonical_question_payload(questions: Sequence[dict]) -> bytes:
    """The bytes the ``frozen_sha`` is computed over.

    Each question is reduced to its frozen fields in a fixed key order and the
    questions are sorted by ``question_id``, so the sha depends only on the
    content of the set, never on dict ordering or the presence of the sha field
    itself. Any change to a question's text, class, or seeded units changes
    these bytes and therefore the sha."""
    reduced = [
        {
            "question_id": q["question_id"],
            "text": q["text"],
            "overlap_class": q["overlap_class"],
            "seeded_unit_ids": list(q["seeded_unit_ids"]),
            "headline_pooled": bool(q.get("headline_pooled", True)),
        }
        for q in questions
    ]
    reduced.sort(key=lambda q: q["question_id"])
    return json.dumps(reduced, sort_keys=True, separators=(",", ":")).encode("utf-8")


def compute_frozen_sha(questions: Sequence[dict]) -> str:
    """Content-addressed sha of the question set. ``sha256:`` prefix mirrors the
    ``_sha256_prefix`` convention used in ``substrate/dispatch/router.py``."""
    return "sha256:" + hashlib.sha256(_canonical_question_payload(questions)).hexdigest()


def load_question_set(path: str = QUESTION_SET_PATH) -> QuestionSet:
    """Load + verify the frozen question set.

    Verifies the recorded ``frozen_sha`` matches a freshly computed sha over the
    questions — so a hand-edit to the JSON that does not also update the sha is
    caught at load (the set is frozen, not merely labelled frozen). Re-loading
    the same path always yields the identical ``frozen_sha`` (M1 acceptance:
    ``test_frozen``)."""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)

    recorded_sha = raw["frozen_sha"]
    computed_sha = compute_frozen_sha(raw["questions"])
    if recorded_sha != computed_sha:
        raise ValueError(
            f"question set sha mismatch: recorded {recorded_sha} but the content "
            f"hashes to {computed_sha} — the set was edited without re-freezing."
        )

    questions = tuple(
        BenchmarkQuestion(
            question_id=q["question_id"],
            text=q["text"],
            overlap_class=q["overlap_class"],
            seeded_unit_ids=tuple(q["seeded_unit_ids"]),
            headline_pooled=bool(q.get("headline_pooled", True)),
        )
        for q in raw["questions"]
    )

    # M1 acceptance: at least one question per class; high_overlap +
    # zero_overlap_control both non-empty (the validity control depends on the
    # latter, the headline on the former).
    present = {q.overlap_class for q in questions}
    missing = set(OVERLAP_CLASSES) - present
    if missing:
        raise ValueError(f"question set is missing overlap classes: {sorted(missing)}")

    return QuestionSet(
        questions=questions,
        seed=int(raw["seed"]),
        frozen_sha=recorded_sha,
        version=str(raw.get("version", "")),
    )
