# Demand-gate runbook (HPRJ SPR-08 M6)

The operator's reproducible procedure for the form-factor demand window. The
agent built everything referenced here; **the operator runs the window.** The
agent does NOT recruit testers, does NOT nudge them, and does NOT touch the
thresholds (`docs/decisions/form-factor-demand-gate-PREREGISTERED.md`).

## Pre-flight (once, before opening the window)

1. Confirm the criteria are pre-registered and unamended:
   `git log --follow docs/decisions/form-factor-demand-gate-PREREGISTERED.md`
   — its commit must precede every other SPR-08 commit.
2. Confirm the detector + analysis are green:
   `./.venv/bin/python -m pytest tests/test_roundtrip_detector.py tests/test_demand_gate_analysis.py -q`
3. Pin **N** in [5, 15] and the **start/end dates** (2-week window). Write them
   into the verdict template headers now (not the thresholds — those are fixed).
4. Confirm the share surface offers URL-view and file-download with **equal
   prominence** (the neutrality precondition). If the dual-offer UI is not yet
   neutral, the window MUST NOT open — a file-biased offer voids a SUSTAIN.

## Onboarding a tester (neutral script — say exactly this, nothing more)

> "Here's an Antiek research workspace. Use it however's useful to you over the
> next two weeks. When you want to keep or share something, there are two
> options offered side by side — a share link and a file download. Pick whatever
> suits you. That's it."

Do **not**: mention `.antiek`, the format, "a new file type," or the download
button specifically. Do not follow up about downloads. Do not send tutorials on
the format. Neutral onboarding, then hands off. Any deviation is a finding to
record in the verdict, and it taints that tester's signal.

## During the window

- Do nothing. No nudges, no reminders about files, no threshold edits. If you
  (or anyone) want to move a threshold or extend the window, **that desire is
  itself a finding** — write it verbatim into the verdict doc and leave the
  threshold alone.

## Closing the window + producing the verdict

1. At the end date, stop accepting new tester activity.
2. Collect the demand-gate events (the four telemetry types + any
   `demand_gate.roundtrip_detected` from the detector, plus any documented
   third-party-reader / agent-unprompted observations). Every event needs a
   timezone-aware `emitted_at`. A hand-documented third-party-reader or
   agent-unprompted observation must name the `tool` / `agent`, name who in
   `user_id` (not you), and cite an `evidence_ref` (a link or id the signed
   verdict points at). Anything missing is not admissible.
3. Run the analysis (reproducible, criteria-hash-pinned) with the tester ids
   and window pinned in pre-flight step 3:
   ```python
   from services.demand_gate.analysis import compute_verdict
   v = compute_verdict(
       events,
       operator_user_id="<your-user-id>",
       tester_ids={"<tester-1>", ...},   # the N pinned ids, 5 <= N <= 15
       window_start=<aware start datetime>,
       window_end=<start + 14 days>,
   )
   print(v.verdict, v.counts, v.criteria_commit)
   ```
   A round-trip counts only when the re-importer (`user_id`) and at least one
   exporter (`exported_by`) are pinned testers, no exporter is the operator,
   and it falls inside the window. An unmodified re-import is attributed to
   whoever exported those exact bytes; an edited one to every exporter of the
   document, so an operator export of any version refuses it. Tester ids that
   differ only by case or whitespace are one person and raise
   `GateNotRunnable`. `GateNotRunnable` means no verdict exists: the window or
   tester set breaks the pre-registration, or no `export_offered` event
   reached a pinned tester in the window (the offer was never instrumented).
   Do not sign either template; record it as a finding.
4. Apply the matching template: `docs/decisions/verdict-sustain.md` **or**
   `docs/decisions/verdict-retire.md`. Fill only the bracketed fields; do not
   edit the reasoning. Sign + date.
5. Commit the signed verdict. **Either outcome is success** — a RETIRE retires
   the format framing in writing and the projection layer stands regardless.

## Dry-run check (agent-runnable, proves the runbook is followable)

The detector + analysis tests ARE the dry run of steps 2–3 against synthetic
events: `pytest tests/test_roundtrip_detector.py tests/test_demand_gate_analysis.py`
exercises both verdict directions end to end without a live window.
