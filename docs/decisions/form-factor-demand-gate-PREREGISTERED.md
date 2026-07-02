# PRE-REGISTERED — form-factor demand gate (HPRJ SPR-08 M1)

**This document is committed BEFORE any telemetry, detector, or UI work exists.
Its thresholds, window, and verdict mapping are IMMOVABLE once the window opens.
The git history of this file IS the pre-registration proof; it is never amended
after the first tester sees a link.** The analysis (`services/demand_gate/
analysis.py`) pins this file's commit hash.

## The question this gate answers

Does anyone other than the operator actually want a new HTML *file format*, or do
people merely enjoy nicely rendered documents (which every web page already is)?
The operator's original "Adobe-creates-PDF" framing was broken by the
2026-06-12 egghead tribunal (no scarcity around an open spec with universally
distributed renderers); the tribunal left exactly one honest path: **evidence**.

## The confound this gate controls for

**Operator-joy, n=1.** The operator loves these artifacts. That is the
documented confound, NOT evidence. The whole design exists to distinguish the
operator's enthusiasm (and testers politely clicking "download") from a real
signal. Therefore the measurement counts ONLY what a download cannot fake.

## What does NOT count

Downloads, opens, time-on-page, and compliments do **not** count. They measure
"nicer app," not "new format." A high download count with zero round-trips is a
**retire** result, not a partial sustain.

## What DOES count (the only admissible evidence)

Mechanical, third-party, unpromptable signals:

1. **Organic round-trip** — a `.antiek` / `.antiek.html` exported by a
   non-operator, carried elsewhere or modified externally, and re-imported,
   detected mechanically (`services/demand_gate/roundtrip_detector.py`). A
   `traveled-and-changed` round-trip (re-imported with a different signature) is
   the strongest admissible signal.
2. **Third-party reader** — someone else's tool parsing `.antiek` **unpaid and
   unprompted** (we do not build one ourselves — that would contaminate the
   signal).
3. **Agent-unprompted adoption** — an agent choosing the `.antiek` envelope over
   Markdown/HTML **without being told to**, documented.

## Window and N

- **Window:** 2 weeks, fixed. No extension (an extension is itself a finding —
  recorded in the verdict, threshold untouched).
- **N testers:** operator pins N in [5, 15] (master-spec assumption) before the
  window opens; non-operator testers only.

## Verdict mapping (immovable)

- **SUSTAIN** ⟺ **at least one** of {organic round-trip (1), third-party reader
  (2), agent-unprompted adoption (3)} is observed in the window.
- **RETIRE** ⟺ none of the above is observed. A retire verdict is a **successful
  test** — it retires the form-factor framing in writing; the HTML projection
  layer (already shipped: SPR-02..07) stands on its own regardless.

There is no middle verdict. Download/open counts, however high, map to RETIRE.

## Neutrality precondition

The dual offer (share link vs file download) MUST be bias-neutral (equal
prominence, neutral copy, documented ordering). A file-biased offer would
manufacture exactly the signal the operator hopes for, voiding a positive
result. Neutrality is what makes a SUSTAIN believable.

## Roles (do not blur)

- **Agent:** builds the detector, the analysis, the neutral offer, both verdict
  templates, and the runbook. Never recruits, never nudges, never moves a
  threshold.
- **Operator:** recruits N testers, opens/closes the window, signs the verdict.
  The window is not agent-runnable.

## If anyone wants to move a threshold mid-window

That desire is a **finding**. Record it verbatim in the verdict doc; leave the
threshold alone. Pre-registration is the whole sprint.
