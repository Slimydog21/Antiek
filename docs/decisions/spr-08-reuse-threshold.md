# Reuse groundedness threshold — the trust gate's only knob (AFF SPR-08)

**Decision date:** 2026-06
**Status:** ✅ Committed
**Owner:** Antiek Flywheel Foundation SPR-08
**Base SHA:** `d2a39a0` (origin/main tip in the SPR-08 worktree; `EVENT_SCHEMA_VERSION` was `25` at this tip, bumped to `26` by this sprint).

SPR-08 attaches a groundedness score to every reusable knowledge unit and gates
SPR-06's reuse injection so a unit is reused **only if** its score
≥ `REUSE_GROUNDEDNESS_THRESHOLD` **AND** it passes §9.0 servability. The honesty
thesis: the flywheel reuses prior knowledge into NEW investigations, so an
ungrounded unit does not just sit in the graph — it seeds the next synthesis.
Without this gate the loop amplifies hallucination at the same rate it amplifies
signal.

---

## Value

```
REUSE_GROUNDEDNESS_THRESHOLD = 0.5   # substrate/flywheel/reuse_gate.py
```

Env-overridable via `REUSE_GROUNDEDNESS_THRESHOLD` (read once at import through a
single helper that rejects garbage / out-of-range values loudly). This is the
**only** trust knob — the gate, the tests, and the emitted `reuse.gated` event
all read this one constant (no second hardcoded bar).

---

## Why 0.5 — "at least as strict as supported"

The threshold is anchored to the shipped #27 scorer's
`DEFAULT_SUPPORTED_THRESHOLD = 0.5` (`substrate/eval/groundedness/scorer.py:47`)
and is **never weaker than it**. The scorer calls a claim `supported` iff its
score ≥ that threshold; the reuse gate reuses a unit only if it would be called
supported. So the gate inherits the scorer's calibration rather than inventing a
second, drifting bar — a unit the scorer would not call supported is never
re-seeded into a new investigation. The score itself is the deterministic
`lexical` backend's verdict (coverage of the claim's content tokens by its cited
chunk text, with a negation-polarity penalty and a fabricated-number penalty).

An operator who wants a stricter bar sets `REUSE_GROUNDEDNESS_THRESHOLD` higher
(e.g. `0.9`); the mutation test `test_m3_override_excludes_a_unit_the_default_admits`
proves an override at 0.9 excludes a 0.6 unit that the 0.5 default admits.
Lowering it below 0.5 would reuse units the scorer would not call supported —
allowed mechanically, but it weakens the trust gate, so it must be a deliberate,
recorded operator choice.

---

## What the gate does NOT claim (honesty)

The lexical proxy is a **coverage + polarity + number proxy, not a judge**. It
rewards a claim whose content tokens are covered by its cited evidence and
penalises negation flips + fabricated numbers, but its blind spots are real:

- a faithful-sounding paraphrase that subtly distorts a relation can still score
  high (token overlap survives the distortion);
- a *correct* claim phrased in disjoint vocabulary can score low (low overlap);
- it has no world model, so it cannot catch a claim that is internally coherent
  with its evidence but factually wrong about the world.

So this gate does **not** make reuse "safe". Its claim is narrow and provable:
it excludes below-threshold + non-servable units, mutation-proven (M4) and
logged (M5, one `reuse.gated` event per exclusion). The future A/B path to a
real judge is #27's `llm_judge` backend (off by default, never exercised in CI);
promoting it from observation to gate is a later sprint's decision, recorded
against `substrate/eval/groundedness/PROMOTE_TO_GATE.md`.

---

## Servability is independent and single-sourced

The gate's second condition — §9.0 servability — is read from the unit's
`servability.serves_full_text` tag (recorded at deposit by the §9.0 classifier;
deny-by-default). The gate never re-derives servability; `substrate/contracts/servable.py`
remains the single owner. The two conditions are **independent**: a perfectly
grounded but non-servable unit is excluded (reason `non-servable`); a servable
but below-threshold unit is excluded (reason `below-threshold`); a unit failing
both records BOTH reasons on one event.

---

## Steelman of the rejected alternative — "reuse everything, let the synthesizer judge"

(Rigor #2 — the strongest counter-argument, recorded here because the gate is a
judgment call about where filtering belongs.)

**Steelman.** The synthesizer is a far better judge than a lexical proxy: it reads
each unit in context and can discount a weak prior. Gating reuse upstream discards
signal a smart model would salvage, and a 0.5 lexical bar will false-exclude
correct-but-low-overlap units. Reuse is injection-into-context (SPR-06's framing),
not substitution — the research loop still runs — so why pre-filter at all?

**Rebuttal.** The flywheel's thesis is *compounding*: a reused unit seeds the NEXT
synthesis, whose output becomes a future prior. An ungrounded unit injected into
context is not one bad answer — it is laundered into the graph as established
context and re-injected forever, so the loop amplifies hallucination at the same
rate it amplifies signal (the staleness risk SPR-06 explicitly deferred to this
sprint). "Let the synthesizer judge" assumes the synthesizer reliably resists
confidently-stated, densely-citable priors — exactly the failure the truth axis
exists to catch (a fluent lie scores high on the FORM-axis style rubric, §14.4).
The pre-filter is not a hard safety claim: it excludes only what is below the
scorer's own *supported* bar or non-servable, both logged (M5) and reversible by
one knob, and #27's `llm_judge` backend is the path to the smarter filter the
steelman wants — without leaving the loop ungated in the interim. Servability is
non-negotiable regardless: a non-servable unit's text must never reach a context
pack (§9.0), and "let the synthesizer judge" cannot relax that.

---

## What the unit's groundedness slot stores (Decision A)

SPR-08 deliberately persists only the **float** `verdict.score` on the unit's
`KnowledgeUnitContract.groundedness_score` slot — it does NOT widen the frozen
contract to hold the full `ClaimGroundednessVerdict`. The full attribution
(`scorer_id`, the `supported` verdict, `cited_chunk_ids`, `rationale`) is carried
on the typed `reuse.gated` event and is reproducible from the deterministic
`lexical` scorer, so nothing load-bearing is lost: the slot answers "how
grounded?" in one comparable number, and the event answers "scored by which
scorer, and excluded why?" (`test_m1_projection_fills_slot_with_scorer_return`
proves a real deposited unit's emitted record carries `scorer_id` + the actual
score — not a constant). This avoids a `contracts.ts` regeneration and an SPR-04
conformance change for attribution the event already carries.

The trade-off, stated plainly: the slot alone cannot be re-audited for the
`rationale`/`cited_chunk_ids` behind a score — that detail lives on the event
stream, not the node, and an *admitted* unit (no `reuse.gated` event) carries its
score's provenance only implicitly (it is always the `lexical` scorer's float, by
this design). If a future sprint needs per-unit rationale on the node itself,
widening the slot (and regenerating the contract types) is the reconsider path.

---

## Reconsider if

- The SPR-09 compounding benchmark shows the gate excludes genuinely-useful
  grounded units at the 0.5 bar (false-exclusion rate too high) → consider
  lowering, or promoting the `llm_judge` backend for a more accurate score.
- The benchmark shows ungrounded units still leaking into syntheses at 0.5
  (false-admission rate too high) → raise the bar, or promote the judge.
- A labelled groundedness set (the `PROMOTE_TO_GATE.md` criterion) lands and
  re-tunes `DEFAULT_SUPPORTED_THRESHOLD` → re-anchor this threshold to the new
  value (it tracks the scorer's bar, it does not float independently).
