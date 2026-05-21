# `synthesizer` program

**What this role does**: produces the human-facing MASTER.md
deliverable at the end of an investigation. Takes the role outputs
along the trajectory (decomposer sub-questions, evidence_retriever
supporting_claims + evidentiary_gaps, parameter_extractor quantitative
parameters, connector relationships) and produces a structured
synthesis with thesis components, falsification conditions, execution
risks, and chunk-level citations.

**Why this role is special**: synthesis is the operator-facing artifact.
Voice and style discipline (master-spec §5) is enforced HERE. The
synthesizer's output is what the operator reads, edits, and exports.
Every other role can fail loudly and the system self-corrects. The
synthesizer cannot — its output is the product.

## What good output looks like

- Prose flows. Top-level structure (insights vs. open questions) stays;
  within each section, full paragraphs that argue.
- Sector vocabulary absorbed from the corpus. Radar engineers don't say
  "competitive moat"; VC analysts don't say "sidelobe reduction." Use
  the field's own words.
- Confidence conveyed by sentence rhythm and word choice. Never by
  appending "(high confidence)" markers.
- Chunk citations inline as spans, not appended as a separate
  references section.
- Each thesis component is falsifiable and the falsification condition
  is named.

## What to avoid (forbidden)

- Em-dashes everywhere. One per thesis, maximum.
- Bullet-point staccato within paragraphs. Bullets only at the
  top-level insights / open-questions delineation.
- Padding constructions: "It is important to note that," "It should
  be observed," "It can be argued that." Target: zero.
- Hedging modifiers that undermine claims with evidence. If the
  evidence is strong, say so directly. If it's weak, say that.
- Generic AI English independent of subject matter. The output should
  read like a researcher in the field wrote it, not like an LLM
  describing a researcher in the field.
- Identical structural flow regardless of subject. A synthesis about
  neutral atom physics should not have the same paragraph cadence as
  a synthesis about credit-default-swap markets.

## Hypotheses to try when iterating

These are mutation targets for autoresearch Wedge 1 (Sprint 19+):

1. Drop all hedging modifiers from thesis-component prose. Measure
   verifier pass rate.
2. Force one falsification condition per thesis component (not "where
   reasonable"). Measure operator acceptance.
3. Inject `style_extractor` output as a `style_guide` context-pack
   layer; A/B against synthesizer-alone. Measure sector-vocab overlap
   per §5.4 verification.
4. Strip explicit confidence markers ("high confidence," "moderate
   confidence") and rely on sentence rhythm. Measure operator's
   ability to recover the confidence signal from rhythm alone.
5. Constrain to one em-dash per thesis component (hard limit, not
   guideline). Measure prose readability.

## Cross-references

- Master-spec §5.1-§5.5 (voice/style discipline canonical source)
- Master-spec §2.4 (synthesis as the human-facing artifact)
- Master-spec §14.4 (dispatch tier measurement — synthesizer is pinned
  to Opus primary for Sprint 17-20 measurement)
- `integration_autoresearch.md` Wedge 1 (this file is the mutation
  target for prompt autoresearch)
