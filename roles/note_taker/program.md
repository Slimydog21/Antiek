# `note_taker` program

**What this role does**: produces per-document notes in Antiek's
canonical `insights + open questions` structure. Runs on document
ingestion (Loop 2 wrestling events) and surfaces emergent notes that
become first-class graph nodes. The note-taker is what makes
recursive note-taking — master-spec §1's core engine — actually
happen.

**Why this role matters**: every document the substrate touches gets
distilled into insights and open questions by this role. The
operator's vision in voice notes 2026-05-17 is explicit: "LLMs are
fantastic at taking notes... the entire structure of this note-taking
is the core engine of my insight." The note-taker is that engine.

## What good output looks like

- Insights are distilled claims with chunk-level citations. Each
  carries a confidence assessment and source tier.
- Open questions are gaps the document raises but doesn't answer.
  Tagged with category and evidence-type-needed.
- Notes embody the sector's vocabulary. A note on a quantum paper
  uses condensed-matter-physics terms; a note on a 10-K uses
  finance terms. **The note-taker is upstream of the synthesizer
  on voice/style** — vocabulary preservation starts here.
- Notes are emergent, not enumerative. A note that says "this is
  MORE than a quote of one claim" is good; a note that just restates
  a sentence is not.

## What to avoid (forbidden)

- Bullet staccato within notes. Notes are prose distillations, not
  enumerations.
- Ignoring sector vocabulary. If the document uses "sidelobe
  reduction" the note must use "sidelobe reduction," not "noise
  reduction in the secondary lobes of the radiation pattern."
- Unattributed insights — every note must reference the chunks that
  motivated it via `source_event_ids`. Unattributed = hallucination,
  dropped by the parser.
- More than 5 notes per substantive event. The note-taker is
  selective by design; too many notes dilute signal.

## Hypotheses to try when iterating

1. Force one open question per insight (paired structure). Measure
   chase-loop triggering rate.
2. Require notes to be more than 2 sentences each (no single-sentence
   notes). Measure emergent-insight quality.
3. Tag notes by confidence-level: emergent notes from cross-doc
   linking (high-novelty) versus emergent notes from single-doc
   wrestling (lower-novelty). Measure operator's selective endorsement.

## Cross-references

- Master-spec §1 (recursive note-taking as the core engine)
- Master-spec §2.1 (insight/question structure as the canonical shape)
- Substrate `interfaces/research/api/note_taking.py` (the bridge that
  triggers note_taker on substantive wrestling events)
- Master-spec §13.9 (user-contributed public-graph notes pass through
  this role's voice-style scoring before attribution eligibility)
