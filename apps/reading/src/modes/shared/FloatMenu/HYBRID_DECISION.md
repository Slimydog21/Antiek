# FloatMenu M4 — "Hybrid" Deep-research decision note

Living Roadmap SPR-04 M4. This records what is **verified** vs **stubbed** in
the Hybrid path, and what would resolve the open boundary. Per rigor #1
(intellectual honesty) and the SPR-03 M4 lesson: **do not ship a
non-functional thing claimed as met.** This file is the honest record.

## What Hybrid is meant to be

Today (M2), Deep-research launches a child investigation **immediately** from a
highlight (the reused chase path). The "Hybrid" idea is: before launching, the
AI **decides whether to ask clarifying questions** — "let it tick the boxes,
then launch." The AI jumps in only when the selection is ambiguous enough that
a cold launch would waste a research; otherwise it launches straight away.

## What is LIVE (verified)

- **Flag plumbing.** `FloatMenu` takes `hybridEnabled` (default `false`).
- **Flag OFF (default) = M2 exactly.** With the flag off there is no Hybrid
  affordance at all; Deep-research launches immediately via the chase path.
  This is the verified, shipped behavior and the default everywhere.
- **Flag ON surfaces a clearly-labelled affordance.** With `hybridEnabled`
  true, the menu shows a `data-floatmenu-hybrid` row reading
  **"Hybrid — coming (AI asks first)"** with a tooltip stating it is not yet
  functional and pointing here. It is **reachable** and **honestly marked
  unfinished** — it is NOT a fake that looks done, and it is NOT a hard
  dependency of M1–M3.

## What is STUBBED (NOT yet functional)

- The **ask-vs-launch decision** itself. There is no model call that inspects
  the selection and returns "ask these clarifying questions" vs "launch now."
  The affordance renders the intent; it does not execute it.
- The **clarifying-question turn loop** (collect answers → fold into the
  spawn_context → then launch).

The affordance does not pretend otherwise — its label and tooltip say "coming"
and "not yet functional."

## The open boundary (what would resolve it)

The hard question is **when should the AI ask vs. just launch?** That is partly
a product judgment, not only an engineering one:

- A heuristic (selection length / ambiguity / missing entities) is cheap but
  crude and will annoy on clear selections.
- A model "should I ask?" pre-classification is more faithful but costs a round
  trip and a §16 dispatch on every Deep-research, and can over-ask.

**Who can answer:** the operator (product call on the ask-rate the
reader-for-understanding will tolerate), informed by a measured Deep-research
launch sample (how often a cold launch produced a wasted/off-target research).
Until that measurement exists, hardening the boundary would be guessing — so M4
stays a flagged, honest stub by design, exactly as the sprint spec marks it
("the boundary … is partly an open question, so do not harden it").

## Reverse-if

If the measured wasted-launch rate is low, Hybrid is not worth the latency/cost
and this stub is deleted rather than finished — the immediate-launch M2 path is
the right default and Hybrid was a speculative add.
