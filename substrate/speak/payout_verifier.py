"""Speak SPR-10 — the AI-graded payout verifier.

The spec wants payout for an interview to scale with how well the
transcript answered the REQUESTER's information goal — graded by an AI
verifier, NOT by the requester. The requester knows their need, but a
requester who also controls whether an interview "passes" has a direct
moral hazard: deny a perfectly good interview to keep the data for free,
and the interviewee has no recourse. So the grade is produced by a
dispatched verifier-shaped pass, the requester cannot deny a passing
interview, and a payout that releases routes through the §9 contribution
measurement (``contributor.accrue_contributions``) into ESCROW — never
disbursed pre-gate.

HONEST FRAMING (rigor #1 — read this before trusting the word "verifier")
-------------------------------------------------------------------------
This is NOT a trained grader. There is no RL-tuned or fine-tuned
"verifier model" behind it. ``grade_interview`` dispatches a
PROMPT-RUBRIC to the cross-family ``verifier`` role over Hermes (§16, no
self-host, no second runtime) and parses a scalar in [0, 1]; with no
``dispatch_fn`` it falls back to a DETERMINISTIC keyword/coverage rubric
so the lifecycle is testable and honest with no model keys. Either way
it is a HEURISTIC, and a heuristic grader is gameable: an interviewee
who learns the rubric can pad an answer with the goal's keywords and
score well without saying anything substantive (Goodhart). That risk is
recorded OPEN — ``docs/roadmap/ROADMAP.html:280`` ("Payout Goodhart /
attribution-gaming … remain a live design fork") and master spec §9.7 —
and this module does NOT claim to have solved it. It does NOT build an
anti-gaming system; it labels the limitation and keeps the door for a
real trained grader open (the reconsider-if in the decision doc:
``docs/decisions/spr-10-ai-graded-payout.md``).

WHAT IT DOES, PRECISELY
-----------------------
1. ``grade_interview`` — score one interview's transcript against the
   requester's goal → ``InterviewGrade(score ∈ [0,1], passed, honest,
   gamed_risk, rationale)``. Persists the grade (kept, never discarded —
   even a failing/bad-but-honest interview is retained + labeled). Emits
   ``SPEAK_INTERVIEW_GRADED``.
2. ``release_payout`` — take the graded scores for a project's interviews
   and route them through ``accrue_contributions(quality_scores=...)``,
   which §9.3-Option-B-weights them and slop-gates anything below
   ``slop_threshold``. Enforces the requester's BUDGET + per-interview
   CAP. Accrues to escrow; NEVER calls ``attempt_disbursement`` (money
   stays gated on G2/G3).

THE MORAL-HAZARD GUARD IS STRUCTURAL, NOT A FUNCTION CALL
---------------------------------------------------------
"The requester cannot deny a passing interview's payout" is not enforced
by a runtime assertion — it holds STRUCTURALLY because there is NO code
path by which a requester denies a passing interview in the first place.
``economics_mode.resolve_policy`` has no "public but no split" / no
override that yields public-without-the-algorithmic-split (the binding
rule lives there and only there), and ``release_payout`` takes the
verifier's score as its sole input — the requester supplies the goal +
money bounds, never a pass/deny verdict. The canonical proof is
``test_economics_has_no_public_but_no_split_path``: for every invitation
mode, a public project ⇒ ``split_applies is True``. An earlier draft
shipped an ``assert_requester_cannot_deny`` guard + a 403 endpoint branch;
both were DEAD (no production caller could reach a deny path) and were
removed — advertising a reachable deny endpoint that does not exist was
misleading. See ``docs/decisions/spr-10-ai-graded-payout.md``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Callable, Optional

from .contributor import AccrualLine, accrue_contributions, DEFAULT_SLOP_THRESHOLD
from .events import SPEAK_INTERVIEW_GRADED, record_speak_event
from .schema import ensure_speak_schema

# The passing score. SOURCE: the slop gate threshold already shipped in
# ``contributor.DEFAULT_SLOP_THRESHOLD`` (0.4) — a grade at or above it
# is "not slop" and earns; below it earns $0 (contributor.py:175). We
# deliberately reuse that ONE number rather than minting a second,
# divergent threshold: the verifier's "passed" and the §9 slop gate must
# agree, or an interview could "pass" here yet earn $0 in routing (an
# incoherent surface). If a future trained grader calibrates a different
# pass bar, change it HERE and in the slop gate together, and record why.
PASSING_SCORE: float = DEFAULT_SLOP_THRESHOLD


class BudgetExhausted(Exception):
    """Raised when the requester's payout budget is exhausted. The
    interview is still RECORDED + graded — only further payout stops
    (edge case (c): budget exhausted mid-project)."""


@dataclass(frozen=True)
class InterviewGoal:
    """What the REQUESTER wants the interview to cover, plus the money
    bounds. Numbers come from the requester's input, never from the air
    (rigor #3)."""

    information_goal: str
    # The points the requester wants ticked. Used by the deterministic
    # rubric's coverage score AND handed to the dispatched verifier.
    must_cover: tuple[str, ...] = ()
    budget_usd: Decimal = Decimal("0")
    # Maximum payout for any single interview (so one interview can't
    # drain the budget). 0 ⇒ no per-interview cap beyond the budget.
    per_interview_cap_usd: Decimal = Decimal("0")


@dataclass(frozen=True)
class InterviewGrade:
    interview_id: str
    project_id: str
    score: float                  # in [0, 1]
    passed: bool                  # score >= PASSING_SCORE
    # A "bad but honest" interview answered sincerely but thinly/off-goal:
    # it withholds payout (didn't pass) yet is KEPT + labeled honest, not
    # discarded and not treated as gamed (edge case (a)).
    honest: bool
    # The OPEN Goodhart risk made legible per-interview: the heuristic
    # MAY have been satisfied by keyword-padding rather than substance.
    # This is a FLAG, not a solved detector (rigor #1 / edge case (b)).
    gamed_risk: bool
    rationale: str
    graded_by: str                # "hermes:verifier" | "deterministic-rubric"


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------


def _transcript_text(turns: list[dict]) -> str:
    """Concatenate an interviewee's answers (informant turns) into one
    string the rubric / verifier scores. Interviewer prompts are excluded
    — we grade what the PERSON said, not what we asked."""
    return "\n".join(
        str(t.get("text", ""))
        for t in turns
        if t.get("role") == "informant" and t.get("text")
    )


_VERIFIER_SYSTEM = (
    "You are a verifier grading whether an interview transcript answered a "
    "requester's information goal. You are NOT the requester and you do not "
    "represent their financial interest; your job is to protect a sincere "
    "interviewee from being under-graded. Score how well the transcript "
    "covered the goal, on a 0.0–1.0 scale. Reward substance; do NOT reward "
    "an answer that merely repeats the goal's keywords without saying "
    "anything (that is gaming). Reply with JSON only: "
    '{"score": <float 0..1>, "honest": <bool>, "gamed_risk": <bool>, '
    '"rationale": "<one sentence>"}.'
)


def _verifier_prompt(goal: InterviewGoal, transcript: str) -> str:
    cover = "\n".join(f"  - {c}" for c in goal.must_cover) or "  (none specified)"
    return (
        f"INFORMATION GOAL:\n  {goal.information_goal}\n\n"
        f"POINTS THE REQUESTER WANTS COVERED:\n{cover}\n\n"
        f"INTERVIEW TRANSCRIPT (the interviewee's answers):\n{transcript or '(empty)'}\n\n"
        "Grade per the system instructions. JSON only."
    )


def _parse_verifier_json(raw: str) -> dict:
    """Parse the verifier's JSON reply, tolerating fenced/extra text. A
    malformed reply is a verifier failure, not a silent 0 — the caller's
    deterministic fallback handles a missing verifier, but a verifier
    that REPLIED with garbage should surface (we raise ValueError)."""
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        raise ValueError(f"verifier reply contained no JSON object: {raw!r}")
    return json.loads(m.group(0))


def _deterministic_grade(goal: InterviewGoal, transcript: str) -> dict:
    """The no-model, honest fallback rubric. NOT a trained grader (rigor
    #1) — a keyword-coverage + substance heuristic:

      • coverage: fraction of ``must_cover`` points whose salient words
        appear in the transcript (0 must-cover ⇒ coverage from goal
        keywords);
      • substance: a length/diversity proxy so a one-word "yes" scores
        low even if it happens to contain a keyword.

    ``gamed_risk`` is TRUE when coverage is high but substance is low —
    the signature of keyword-padding. This flags, it does not prevent
    (the OPEN Goodhart risk)."""
    text = transcript.lower()
    words = re.findall(r"[a-z']+", text)
    n_words = len(words)
    unique = len(set(words))

    targets = list(goal.must_cover) or _keywords(goal.information_goal)
    if not targets:
        coverage = 1.0 if n_words > 0 else 0.0
    else:
        hit = 0
        for t in targets:
            kws = _keywords(t)
            if kws and any(k in text for k in kws):
                hit += 1
        coverage = hit / len(targets)

    # Substance proxy: saturates around ~60 words of reasonably varied
    # speech. A terse or repetitive answer scores low here regardless of
    # keyword hits.
    substance = min(1.0, n_words / 60.0) * (unique / n_words if n_words else 0.0)
    score = round(0.6 * coverage + 0.4 * substance, 4)

    gamed_risk = coverage >= 0.5 and substance < 0.2
    # Honest-but-bad: a sincere answer (real substance) that simply didn't
    # cover the goal well. Distinct from gamed (keyword-padding).
    honest = substance >= 0.2 and not gamed_risk
    return {
        "score": score,
        "honest": honest,
        "gamed_risk": gamed_risk,
        "rationale": (
            f"deterministic rubric: coverage={coverage:.2f}, "
            f"substance={substance:.2f} over {n_words} words"
        ),
    }


_STOP = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "about", "what", "how", "did", "do", "was", "were", "is", "are", "his",
    "her", "their", "they", "he", "she", "it", "that", "this", "you", "your",
})


def _keywords(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z']{3,}", text.lower()) if w not in _STOP]


def grade_interview(
    con: Any,
    *,
    project_id: str,
    interview_id: str,
    goal: InterviewGoal,
    transcript_turns: Optional[list[dict]] = None,
    dispatch_fn: Optional[Callable[..., Any]] = None,
) -> InterviewGrade:
    """Grade one interview's transcript against the requester's goal.

    The grade is produced by the AI verifier (``dispatch_fn`` — production
    passes ``substrate.dispatch.dispatch``), NOT by the requester. With
    ``dispatch_fn=None`` the deterministic rubric grades it (honest no-key
    behaviour). The grade is PERSISTED (kept, never discarded — a
    failing/bad-but-honest interview is retained + labeled, edge case (a))
    and emits ``SPEAK_INTERVIEW_GRADED``.

    ``transcript_turns`` defaults to the interview's stored
    ``transcript_turns`` so the caller need not re-load them.
    """
    ensure_speak_schema(con)
    if transcript_turns is None:
        row = con.execute(
            "SELECT transcript_turns FROM interviews WHERE interview_id = ?",
            [interview_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"interview {interview_id!r} not found")
        try:
            transcript_turns = json.loads(row[0]) if row[0] else []
        except (TypeError, ValueError):
            transcript_turns = []
    transcript = _transcript_text(transcript_turns)

    if dispatch_fn is not None:
        # AI-graded via Hermes (§16 — the cross-family ``verifier`` role,
        # no self-host, no second runtime). A verifier that fails to
        # produce parseable JSON falls back to the deterministic rubric
        # rather than silently scoring 0 (an unparsed reply must not
        # withhold a sincere interviewee's pay).
        try:
            result = dispatch_fn(
                prompt=_verifier_prompt(goal, transcript),
                role="verifier",
                investigation_id=f"speak-grade-{interview_id}",
                system=_VERIFIER_SYSTEM,
            )
            raw = result if isinstance(result, str) else getattr(result, "text", str(result))
            parsed = _parse_verifier_json(raw)
            graded_by = "hermes:verifier"
        except Exception:  # noqa: BLE001 — verifier unavailable/garbled → honest fallback
            parsed = _deterministic_grade(goal, transcript)
            graded_by = "deterministic-rubric"
    else:
        parsed = _deterministic_grade(goal, transcript)
        graded_by = "deterministic-rubric"

    score = max(0.0, min(1.0, float(parsed.get("score", 0.0))))
    passed = score >= PASSING_SCORE
    gamed_risk = bool(parsed.get("gamed_risk", False))
    # If the verifier omits ``honest`` (the deterministic rubric always
    # supplies it; only the Hermes path can omit it), default it to the same
    # substance-based shape the fallback uses rather than ``score > 0.0`` —
    # which would mislabel a FAILING AI-graded interview as honest. A
    # sub-passing or flagged-gamed interview is NOT defaulted to honest; an
    # interview the verifier scored as passing (and didn't flag gamed) is.
    honest = bool(parsed.get("honest", passed and not gamed_risk))
    rationale = str(parsed.get("rationale", ""))[:1000]

    grade = InterviewGrade(
        interview_id=interview_id, project_id=project_id, score=score,
        passed=passed, honest=honest, gamed_risk=gamed_risk,
        rationale=rationale, graded_by=graded_by,
    )
    _persist_grade(con, goal, grade)
    record_speak_event(
        SPEAK_INTERVIEW_GRADED,
        {"interview_id": interview_id, "score": score, "passed": passed,
         "honest": honest, "gamed_risk": gamed_risk, "graded_by": graded_by},
        project_id=project_id,
    )
    return grade


def _persist_grade(con: Any, goal: InterviewGoal, grade: InterviewGrade) -> None:
    """Persist the grade so it is KEPT (rigor #3a): a bad-but-honest or
    failing interview's transcript + label survive — only the payout is
    withheld. Idempotent per interview (a re-grade overwrites)."""
    con.execute(
        "DELETE FROM speak_interview_grades WHERE interview_id = ?",
        [grade.interview_id],
    )
    con.execute(
        "INSERT INTO speak_interview_grades "
        "(interview_id, project_id, information_goal, score, passed, honest, "
        " gamed_risk, rationale, graded_by) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [grade.interview_id, grade.project_id, goal.information_goal,
         grade.score, grade.passed, grade.honest, grade.gamed_risk,
         grade.rationale, grade.graded_by],
    )


def get_grade(con: Any, interview_id: str) -> Optional[InterviewGrade]:
    row = con.execute(
        "SELECT interview_id, project_id, score, passed, honest, gamed_risk, "
        "rationale, graded_by FROM speak_interview_grades WHERE interview_id = ?",
        [interview_id],
    ).fetchone()
    if row is None:
        return None
    return InterviewGrade(
        interview_id=row[0], project_id=row[1], score=float(row[2]),
        passed=bool(row[3]), honest=bool(row[4]), gamed_risk=bool(row[5]),
        rationale=row[6], graded_by=row[7],
    )


def project_grades(con: Any, project_id: str) -> list[InterviewGrade]:
    rows = con.execute(
        "SELECT interview_id FROM speak_interview_grades WHERE project_id = ? "
        "ORDER BY graded_at",
        [project_id],
    ).fetchall()
    return [g for r in rows if (g := get_grade(con, r[0])) is not None]


# ---------------------------------------------------------------------------
# Release — route graded payout through §9, into escrow, within budget/cap
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PayoutRelease:
    accrual_lines: tuple[AccrualLine, ...]
    quality_scores: dict[str, float]
    budget_usd: Decimal
    spent_usd: Decimal           # accrued within this release (to escrow)
    capped_interview_ids: tuple[str, ...] = field(default_factory=tuple)
    budget_exhausted: bool = False


def release_payout(
    con: Any,
    *,
    project_id: str,
    goal: InterviewGoal,
    ad_revenue_usd: Decimal,
    publication_id: Optional[str] = None,
    impression_ref: Optional[str] = None,
) -> PayoutRelease:
    """Release graded payout for a project's interviews, routed through §9.

    The graded scores (from ``grade_interview``) become the
    ``quality_scores`` map handed to ``contributor.accrue_contributions``
    — so payout is §9.3-Option-B contribution-WEIGHTED, not a flat fee,
    and anything below the slop threshold earns $0 there. The requester's
    BUDGET + per-interview CAP are passed INTO ``accrue_contributions``, so
    the clamp binds the ACTUAL escrow ledger (the rows written to
    ``speak_accruals`` AND the ``ip_holders.escrow_balance_usd`` increments),
    not a downstream report:

      • a single interview's accrued amount is clamped to
        ``per_interview_cap_usd`` BEFORE it is written + escrowed (edge case
        (d)-adjacent: one interview cannot drain the budget);
      • once cumulative escrow accrual reaches ``budget_usd``, no further
        payout accrues — the remaining interviews are still graded +
        recorded, just not paid (edge case (c): budget exhausted).

    The INVARIANT after this call: the real ``speak_accruals`` sum and the
    real escrow balances for this project are ≤ ``budget_usd`` and no single
    interview's accrual exceeds ``per_interview_cap_usd``. ``spent_usd`` is
    the sum of what ACTUALLY accrued, read off the same clamped lines.

    Everything here ACCRUES TO ESCROW. This function NEVER calls
    ``attempt_disbursement`` — money does not leave escrow before the
    G2/G3 legal gate (and with zero ad buyers ``ad_revenue_usd`` is $0
    anyway; the share fractions are still tracked).
    """
    ensure_speak_schema(con)
    grades = project_grades(con, project_id)
    # The §9 routing input: graded score per interview. A FAILING interview
    # carries its real (sub-threshold) score so the §9 slop gate excludes it
    # — payout is withheld for bad-but-honest interviews without discarding
    # the transcript (it's already persisted by grade_interview).
    quality_scores = {g.interview_id: g.score for g in grades}

    # 0 ⇒ "no bound"; translate to None so accrue_contributions accrues in
    # full when the requester set no budget/cap.
    cap = Decimal(goal.per_interview_cap_usd)
    budget = Decimal(goal.budget_usd)
    lines = accrue_contributions(
        con, project_id=project_id, ad_revenue_usd=ad_revenue_usd,
        publication_id=publication_id, impression_ref=impression_ref,
        quality_scores=quality_scores, slop_threshold=PASSING_SCORE,
        budget_usd=budget if budget > 0 else None,
        per_interview_cap_usd=cap if cap > 0 else None,
    )

    # The release report reads off the now-authoritative ledger: the clamp
    # already bound what was written + escrowed, so spent_usd is just the sum
    # of the actual accrued amounts, and capped/exhausted are the flags
    # accrue_contributions set on the lines it wrote.
    spent = sum((l.amount_usd for l in lines if not l.slop_gated), Decimal("0"))
    capped = [l.interview_id for l in lines if l.capped]
    exhausted = any(l.budget_clamped for l in lines)

    return PayoutRelease(
        accrual_lines=tuple(lines),
        quality_scores=quality_scores,
        budget_usd=budget,
        spent_usd=spent,
        capped_interview_ids=tuple(capped),
        budget_exhausted=exhausted,
    )
