# VERDICT (template, pre-written) — RETIRE the form-factor framing

**Status: TEMPLATE — apply only if the analysis returns RETIRE at window
close.** A RETIRE verdict is a **successful test**, not a failed sprint. It is
written as cleanly as SUSTAIN would be. Pre-written so it is not authored under
the disappointment of a negative result.

- **Criteria commit:** `006e66f29fcc2723d09581488055b258b98466b4`
  (`docs/decisions/form-factor-demand-gate-PREREGISTERED.md`)
- **Window:** [start] – [end] · **N testers:** [N] · **Signed:** [operator, date]

## What was measured (and did NOT appear)

[Paste the analysis `counts` — all zero on the admissible axes.] Over the window,
with N non-operator testers and a bias-neutral dual offer, there were:

- **0 organic round-trips** by a non-operator;
- **0 third-party readers** of `.antiek`;
- **0 documented agent-unprompted adoptions.**

[If downloads/opens were high, state it:] There were [n] downloads and [n]
opens. Per the pre-registered criteria these measure "people enjoy nicely
rendered documents" — which every web page already is — not "people want a new
HTML file format." High download counts are exactly the n=1-adjacent signal the
gate was built to discount.

## The decision

The **form-factor framing is retired.** Antiek does not invest further in
`.antiek` as a *new file format to mint* — no public launch, no format spec
site, no "announcing .antiek." The 2026-06-12 tribunal's framing held up: no
scarcity exists around an open spec with universally distributed renderers, and
the evidence test the bet owed came back negative.

## What stands, unchanged

The HTML projection layer **ships and stays**: the deterministic script-free
renderer, the widget library, the signed `.antiek` container + single-file
variant, the rights-filtered exports, and the island-only ingest boundary
(SPR-02..07) are all useful on their own merits — portable, offline, tamper-
evident, rights-safe document export. RETIRE removes only the *new-format-as-
strategy* claim. The artifacts are good; the moat thesis around them was not.

## What was learned

[1–3 sentences: e.g., the operator's love of the artifacts was the confound the
gate correctly isolated; "nicer rendered document" demand is real but is not a
format moat; the projection layer's value is utility, not novelty.]

## Any threshold-move desire during the window (rigor #1)

[Record verbatim any urge to extend the window or move a threshold once the
zeros were visible. It was a finding, not acted on. If none: "none."]
