# `creative_writer` program

**What this role does**: expands outline blocks into prose for
deliverables on Surface C — Creation Workstation (master §4.3, §10).
Takes the section's title + ordered list of attached insight blocks
+ deliverable kind + style_guide, and produces prose that argues
from the blocks, preserving citations.

**Why this role matters**: the creation surface is what the operator
SELLS (master §1.3 economics flip). A `creative_writer` that
produces LLM slop has zero value because the operator will rewrite
the paragraph anyway. A `creative_writer` that produces output
indistinguishable from the operator's own voice, citing the
operator's own graph, is the productivity multiplier that justifies
the surface existing.

## What good output looks like

- Prose that argues from the attached blocks, not just enumerates
  them.
- Each paragraph cites the specific blocks that contributed (the
  `prose_provenance` map).
- Inline claim-span citations preserved; chunk_ids referenced.
- Voice and style **stricter than the synthesizer**, because this is
  the publishable artifact. The synthesizer produces a researcher's
  notebook; the creative_writer produces a published deliverable.
- Section-aware coherence — paragraphs flow into each other across
  sections without repetition.

## What to avoid (forbidden)

- LLM slop. Master-spec §5.1 forbidden patterns apply with extra
  vigilance.
- Ignoring chunk citations. Every claim in the prose must trace to a
  block, which must trace to chunks, which must trace to documents.
  Breaking the chain breaks the substrate's compounding asset
  (master §2.5).
- Operator-asserted claims (per master §10.4 Option B) treated as
  graph-grounded without flagging. These claims have `source_tier=5`
  unless operator manually attaches chunk citations.
- Generic transitions ("Furthermore," "Additionally," "It is worth
  noting"). Use sector-specific connectives or none.

## Hypotheses to try when iterating

1. Force one em-dash maximum per section, not per thesis. Measure
   prose readability against the synthesizer's per-thesis cap.
2. Require the creative_writer to explicitly identify which blocks
   contributed to each paragraph BEFORE generating prose (plan first,
   write second). Measure prose-provenance accuracy.
3. Inject the deliverable's prior sections as additional context to
   prevent repetition. Measure cross-section coherence per master §10.6
   Sprint 14 multi-section coherence requirement.

## Cross-references

- Master-spec §4.3 (Surface C — Creation Workstation)
- Master-spec §10 (Creation surface detailed spec)
- Master-spec §5 (voice/style — synthesizer-level discipline, extra
  strict here)
- Substrate `deliverables` and `deliverable_sections` tables
  (master §10.2)
