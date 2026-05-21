# `parameter_extractor` program

**What this role does**: extracts quantitative parameters from chunks
— numbers, units, uncertainties, dates, methodologies. The downstream
synthesizer relies on these to make claims with quantitative weight.

**Why this role matters**: research syntheses live and die on
numbers. A parameter extracted without units is misleading; a number
extracted without uncertainty is overstated; a parameter without
methodology is unverifiable. This role's accuracy determines whether
the synthesis is checkable or hand-wavy.

## What good output looks like

- Every parameter has: value, units, uncertainty (or "unstated"),
  source chunk_id, methodology summary (one phrase).
- Units in the field's preferred convention. Energy in eV not joules
  if the source is condensed-matter; eV not Hartree if the source is
  atomic.
- Uncertainty as stated in the source. If the source says "10% error
  bar," extract that; don't substitute "approximately."
- Dates of measurement attached. A parameter from a 2018 paper is not
  the same as a parameter from a 2025 preprint.

## What to avoid (forbidden)

- Missing units. Reject and re-prompt rather than emit a unitless
  number.
- Missing uncertainty without an "unstated" flag. The downstream
  consumer needs to know whether uncertainty is absent or
  unknowable.
- Rounding values that the source gives precisely. If the source says
  99.42%, extract 99.42%, not "~99%."
- Inventing methodology. If the source doesn't say how the parameter
  was measured, the methodology field is empty, not fabricated.

## Hypotheses to try when iterating

1. Require uncertainty as a 95% confidence interval where the source
   permits. Measure downstream synthesizer's calibration.
2. Force units in the canonical convention for the document's primary
   discipline (extract discipline from the document's `section_path`
   or topic classification). Measure operator-acceptance rate.
3. Add a `temporal_decay` annotation — parameters from sources
   >5 years old get flagged for staleness review (master-spec
   middleware/temporal/).

## Cross-references

- Master-spec §3.1 (12 roles, parameter_extractor among the 5
  orchestrate.py originals)
- Substrate `middleware/source_tier/` (tier affects how confident
  the synthesizer treats the parameter)
- Substrate `middleware/temporal/` (parameter staleness flagging)
