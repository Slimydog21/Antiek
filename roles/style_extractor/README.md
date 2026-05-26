# roles/style_extractor/

Per-corpus writing-style extraction, run before synthesis.

Input: the top-K corpus chunks for an investigation.
Output: a 150-300 word JSON style guide (vocabulary, argumentation
pattern, sentence rhythm, forbidden register, voice summary).

## Mechanics

The role characterizes HOW the corpus writes — its register and terms of
art — not what it says. The parser validates the JSON shape and rejects
extras / count violations loudly. The resulting `StyleGuide` renders into
a `kind="style_guide"` context-pack layer that conditions the
synthesizer's prose toward the field's own voice (master-spec §5).

## Tier

Flash. One extra dispatch per qualitative investigation (~$0.0002).

## Feature-flagged + heuristic-gated

OFF by default. Flag `ANTIEK_STYLE_EXTRACTOR_ENABLED` and the skip
heuristic (`>50% quantitative sub-questions ⇒ skip`) both live in
`substrate/context_pack/style_guide.py`. With the flag off the assembled
pack is byte-identical to today.

## Operator-bound

No provider keys in the worktree, so the live first run (flag on, real
qualitative investigation) is operator-bound. See `program.md`.
