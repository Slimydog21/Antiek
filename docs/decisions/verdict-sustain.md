# VERDICT (template, pre-written) — SUSTAIN the form-factor framing

**Status: TEMPLATE — apply only if the analysis returns SUSTAIN at window
close.** Pre-written so the post-test edit is a checkbox, not an essay written
under motivated reasoning. Fill the bracketed fields from
`services/demand_gate/analysis.py` output; do not edit the reasoning.

- **Criteria commit:** `006e66f29fcc2723d09581488055b258b98466b4`
  (`docs/decisions/form-factor-demand-gate-PREREGISTERED.md`)
- **Window:** [start] – [end] · **N testers:** [N] · **Signed:** [operator, date]

## The admissible evidence (the only thing that earned this verdict)

[Paste the analysis `counts`.] SUSTAIN required ≥1 of:

- **Organic round-trips (non-operator):** [n] — [for each: document_id,
  returned_unmodified vs traveled_and_changed]. A traveled-and-changed
  round-trip is the strongest signal: a real person carried a `.antiek` out,
  changed it elsewhere, and brought it back.
- **Third-party readers:** [n] — [tool, who, that it was unpaid + unprompted].
- **Agent-unprompted adoption:** [n] — [agent, the unprompted choice of the
  envelope over Markdown/HTML].

Downloads/opens/compliments are NOT in this count and did not contribute.

## What SUSTAIN unlocks (and what it does NOT)

SUSTAIN means the format earned the right to *more investment*, justified by the
specific categories above — NOT a public launch on enthusiasm. Concretely, the
next bets it licenses, each still gated on its own evidence:

- If the signal was **third-party readers**: a published `.antiek` spec + a
  conformance suite (others are already parsing it; document the contract).
- If the signal was **traveled-and-changed round-trips**: a first-class
  external-edit reconcile path (people are editing artifacts elsewhere).
- If the signal was **agent-unprompted adoption**: an agent-facing format
  affordance / MCP surface.

## What stays true regardless

The HTML projection layer (SPR-02..07) shipped and stands on its own. SUSTAIN
adds format-investment justification; it does not retroactively make the layer
more correct — it was already correct.

## Any threshold-move desire during the window (rigor #1)

[Record verbatim any urge — operator's or agent's — to move a threshold
mid-window. It was a finding, not acted on. If none: "none."]
