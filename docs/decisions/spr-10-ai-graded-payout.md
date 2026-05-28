# AI-graded payout for Speak interviews — design decision

**Date:** 2026-05-28
**Branch:** `caffen/lr-spr10`
**Source spec:** Speak SPR-10 (public/private feed + publish matrix +
AI-graded payout + compounding interviewer), milestone M3
**Status:** built. Scoped to ESCROW accrual only — disbursement stays
operator-gated (G2/G3). The Goodhart/rubric-gaming risk is recorded
**OPEN** (`docs/roadmap/ROADMAP.html:280`), not solved.

## The question

After an interview, how much (if anything) should the contributor be
paid, and **who decides**? The requester (the person who commissioned
the biography / wanted the information) is the obvious grader — they know
their need. But a requester who controls payout has a direct conflict of
interest.

## Decision 1 — the grader is an AI verifier, NOT the requester

`substrate/speak/payout_verifier.py` grades each interview's transcript
against the requester's *information goal* and returns a quality signal
in `[0, 1]`. The grade is produced by a **dispatched verifier-shaped
pass** (`substrate.dispatch.dispatch`, `role="verifier"` — Hermes-primary
per §16, no self-host, no second runtime) or, with no model keys, by a
**deterministic keyword/coverage rubric**.

### Steelman of the rejected alternative (rigor #2): user-graded payout

The requester knows their need better than any rubric. A human catches
nuance an LLM/heuristic misses — a short answer that lands one
devastating, exactly-on-point detail; an emotionally true memory that
doesn't tick keyword boxes. A requester grading their own commission
would, in the good case, pay generously for substance the rubric
under-scores.

### Why it loses

Direct **moral hazard**: a requester who can deny a good interview keeps
the data for free, and the interviewee has no recourse. The asymmetry is
the whole point of Speak's contributor promise ("if you say important
facts, you get paid") — a promise the requester can't be trusted to
honour against their own wallet. So the verifier grades, and it
deliberately **absorbs occasional under-grading** to protect the
interviewee: the requester **cannot unilaterally deny a passing
interview**.

This is enforced **structurally**, not by a runtime assertion. There is
no production code path by which a requester denies a passing interview:
`economics_mode.resolve_policy` has no "public but no split" override (the
binding split rule lives there and only there), and `release_payout` takes
the verifier's score as its sole grading input — the requester supplies
the information goal and money bounds, never a pass/deny verdict. The
canonical proof is `test_economics_has_no_public_but_no_split_path`. An
earlier draft of this module shipped an `assert_requester_cannot_deny`
guard plus a 403 endpoint branch in `speak_routes.py`; both were **dead
code** (no caller could reach a deny path to guard against), and
advertising a reachable deny endpoint that does not exist was misleading,
so they were **removed** in the SPR-10 sharpen pass.

**Reconsider-if:** a verifier that **demonstrably under-grades nuanced
answers at a measured rate** (e.g. a sample of human-judged-good
interviews the verifier fails) reopens user-grading — most likely as a
*requester-can-raise-but-not-lower* affordance (asymmetric, preserving
the moral-hazard guard). If the operator decides nuance matters more than
the hazard for a specific cohort, raise it **before** shipping the
requester-cannot-deny guard to that cohort.

## Decision 2 — payout routes via the §9 contribution measurement, not a flat fee

`release_payout` feeds the graded scores into
`contributor.accrue_contributions(quality_scores=...)`, which applies the
§9.3 Option-B weighting (claim_confidence × tier) and slop-gates anything
below the threshold. Payout therefore scales with **measured
contribution**, not a flat per-interview fee.

**Why:** a flat fee rewards showing up, not contributing — it invites
low-effort answers and can't express "this person shaped the story more."
The §9 path is already the audited, single-writer accrual mechanism; a
parallel flat-fee path would be a second, divergent money surface
(rejected). With zero ad buyers the dollar amounts are `$0`; the share
**fractions** are still tracked, so the surface never shows a fictional
balance.

**Reconsider-if:** a measured case where §9 weighting produces a clearly
unfair split (e.g. one corroborating voice that's load-bearing but
low-confidence earns near-nothing) reopens the weighting — that is the
*attribution algorithm* fork already recorded OPEN at
`ROADMAP.html:280`, not a flat-fee return.

## The honest limitation (rigor #1) — this is NOT a solved verifier

`payout_verifier` is a **prompt-rubric / heuristic**, not a trained
grader. Its docstring says so. A heuristic grader is **gameable**: an
interviewee who learns the rubric can keyword-pad an answer and score
well without saying anything substantive (Goodhart). We do **not** claim
to have solved this and we do **not** build an anti-gaming system here.
What the code does instead:

- it **flags** the risk per-interview (`gamed_risk`, set when coverage is
  high but substance is low — the keyword-padding signature). A flag, not
  a detector.
- it distinguishes a **bad-but-honest** interview (kept + labelled
  `honest`, payout withheld) from a **gamed** one — they are different
  things and the system says which.
- the Goodhart / attribution-gaming risk stays **OPEN** at
  `docs/roadmap/ROADMAP.html:280` and master spec §9.7. Referenced, not
  re-added, not claimed closed.

## The hard operator-gate boundary (NOT crossed)

Nothing in this milestone closes, flips, or bypasses G2/G3/G7/G8.
`release_payout` **accrues to escrow only** — it never calls
`attempt_disbursement`, which still refuses pre-gate
(`contributor.py:292`, untouched). `tools/stripe_connect/` and
`substrate/ad_inventory/payout.py` are untouched. The UI **reads**
`gate_status` and shows the gates as *not yet activated*; there is no
affordance anywhere to close one.

## Hardcoded threshold — source named

`PASSING_SCORE` reuses `contributor.DEFAULT_SLOP_THRESHOLD` (0.4). It is
**deliberately the same number** as the §9 slop gate so the verifier's
"passed" and the routing's "earns" agree; a divergence would let an
interview "pass" here yet earn `$0` in routing (an incoherent surface).
A future trained grader that calibrates a different pass bar must change
it in **both** places together, with a recorded rationale.

## New event

`SPEAK_INTERVIEW_GRADED` (`speak.interview.graded`) is added as a
**Speak-local string constant** in `substrate/speak/events.py`, NOT a
central `ActionType`. Per that module's standing doctrine this keeps the
codegen-staleness gate green with no TS drift (no
`EVENT_SCHEMA_VERSION` bump). Promote to the enum only if/when these
events need TS members, in a dedicated codegen-regenerated commit.
