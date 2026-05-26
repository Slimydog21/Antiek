# `style_extractor` program

**What this role does**: reads the top-K corpus chunks for an
investigation BEFORE synthesis and produces a brief (~150-300 word)
sector-specific style guide describing the corpus's voice, vocabulary,
and argumentation patterns. The guide is injected into the synthesizer's
context pack as a `kind="style_guide"` layer so the synthesis absorbs
the field's own register instead of generic AI English (master-spec §5;
`docs/strategy/voice-and-style-discipline.md` §"Change 3").

**Why this role exists**: a per-corpus EXTRACTED guide adapts to ANY
sector. Hardcoding sector hints in the synthesizer prompt does not
generalize: it re-introduces generic English for any domain the
hardcoded list does not anticipate. The trade-off is one extra
flash-tier dispatch per qualitative investigation (~$0.0002) plus the
added dispatch surface — which is why the role is feature-flagged OFF by
default and proven inert when off.

## Output shape (JSON)

```json
{
  "vocabulary": ["8-15 sector terms, as written in the corpus"],
  "argumentation_pattern": "2-3 sentences on how claims are structured",
  "sentence_rhythm": "one sentence on typical sentence length/shape",
  "forbidden_in_this_register": ["2-4 out-of-register patterns"],
  "voice_summary": "1-2 prescriptive sentences for a writer"
}
```

The parser (`parser.py`) enforces the counts and rejects extra keys.
A malformed response raises `StyleExtractorValidationError`; the
context-pack wiring catches it and SKIPS injection — assembly never
crashes on a bad guide.

## Feature flag + skip heuristic

Both live in `substrate/context_pack/style_guide.py`:

- **Flag**: `ANTIEK_STYLE_EXTRACTOR_ENABLED`. **Default OFF.** With the
  flag off, `maybe_style_guide_layer(...)` returns `None`, no
  `style_guide` layer is added, and the assembled context pack is
  byte-identical to today. The live synthesis path is unchanged.
- **Skip heuristic**: `should_run_style_extractor(sub_questions)` returns
  `False` (skip) when **>50%** of the decomposer's sub-questions are
  pure-quantitative. The realizable quantitative signal in the substrate
  is the decomposer's per-sub-question `evidence_type_required`
  (`quantitative | qualitative | mixed`); a sub-question counts as
  quantitative when `evidence_type_required == "quantitative"`. (The
  design doc names hypothetical categories `parameter_extraction` /
  `quantitative_metric`; those are not in the `SubQuestionCategory`
  enum, so the heuristic keys off the enum that actually exists. See the
  module docstring for the mapping note.)

## Context-pack injection

The new layer is `kind="style_guide"`, priority `40` — the same as
`long_term_skill` per the design doc ("priority similar to
long_term_skill"). It renders between `phase_metadata` and
`long_term_skill`/`graph_evidence` in canonical order and is
truncatable under budget pressure (it is background conditioning, not
mandatory).

## What is operator-bound (NOT done in this worktree)

- **The keyed first-run.** There are no provider keys here, so the role
  cannot call a model. Unit tests cover prompt construction, parsing
  (against fixtures), the skip heuristic, and the assembler injection.
  The first real run (flag ON, real qualitative investigation, live
  flash-tier dispatch) is operator-bound.
- **Wiring `style_extractor` → a flash tier** in
  `substrate/dispatch/config.yaml` (`role_tiers`).
- **The bridge handler** (subscribe → dispatch → parse → inject the
  layer into the synthesizer's pack) lands when the operator activates
  the flag; the role + wiring it depends on are in place.

## Cross-references

- `docs/strategy/voice-and-style-discipline.md` §"Change 3" — the design.
- `roles/synthesizer/program.md` (hypothesis #3) — the A/B target.
- `roles/thought_partner/prompt.py` (`sector_style_guide` param) — an
  existing consumer surface for the same guide.
