# `evidence_retriever` program

**What this role does**: for each sub-question from the decomposer,
retrieves relevant chunks from the graph + ranks them by source tier,
then extracts `supporting_claims` (claims the chunks support) and
`evidentiary_gaps` (where evidence is missing or contradictory). The
output is structured into Antiek's canonical `insights + open
questions` shape.

**Why this role matters**: evidence_retriever is the substrate's
hand-eye coordination. It turns sub-questions into structured
evidence-claim pairs. The synthesizer's output is only as good as the
claim/gap structure this role produces.

## What good output looks like

- Each supporting_claim cites specific `chunk_id`s. No floating
  claims.
- Source tiers are visible (1=peer-reviewed primary, 5=anonymous /
  aggregator). The synthesizer uses tier to weight claims.
- Evidentiary_gaps are honest. If the evidence is weak, surface the
  gap. The chase loop uses gaps as next-question seeds.
- Claims are extracted in the sector's vocabulary, not generic
  paraphrase.

## What to avoid (forbidden)

- Speculation framed as evidence. If the chunk doesn't support the
  claim, don't extract it.
- Over-citing — listing every chunk that mentions the topic, rather
  than the chunks that actually support the specific claim.
- Hiding low-tier sources without the tier annotation. The
  synthesizer needs the tier signal.
- Generic paraphrase that strips sector vocabulary. The
  evidence_retriever is upstream of the synthesizer; vocabulary
  preservation starts here.

## Hypotheses to try when iterating

1. Drop the bottom-tier sources entirely (tier 4-5 excluded from
   supporting_claims; surface them only as evidentiary_gaps).
   Measure synthesis quality at the cost of recall.
2. Force one evidentiary_gap per sub-question even when the evidence
   looks strong (challenges the role to surface counter-evidence).
   Measure challenger-role triggering downstream.
3. Cite up to 3 chunks per claim, not unlimited. Measure attribution
   accuracy (per §9.3 Option B).

## Cross-references

- Master-spec §2.1 (insight/question structure)
- Master-spec §9 (chunk citations are the attribution substrate)
- Master-spec §14.4 (evidence_retriever stays on Hermes-primary)
