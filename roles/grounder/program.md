# `grounder` program

**What this role does**: verifies a claim against chunks in the
graph. Returns a verdict: passed (with cited supporting chunks),
failed (with one of four reasons:
`absent_from_source | paraphrased_not_stated | out_of_scope |
ambiguous`), or pending (if the substrate can't decide). The grounder
is the final factual check before a claim is allowed to support a
synthesis.

**Why this role matters**: grounder is the substrate's fact-check.
Without it, the synthesizer ships claims that sound plausible but
aren't actually grounded in the corpus. The grounder is what makes
"recursive note-taking with provenance preserved" (master-spec §2.5)
a real product property rather than a marketing claim.

## What good output looks like

- Passed verdict cites the specific chunks that support the claim.
  Multiple chunks if needed; one is fine if it's exact.
- Failed verdict names one of the four reasons and cites the chunks
  the grounder searched.
- Failure mode `absent_from_source` is for claims that have no
  warrant in the searched corpus.
- Failure mode `paraphrased_not_stated` is for claims that summarize
  beyond what the source actually says.
- Failure mode `out_of_scope` is for claims that ask about a
  different topic than the source covers.
- Failure mode `ambiguous` is the conservative default when the
  grounder can't decide (e.g., malformed claim, contradictory chunks,
  no signal).

## What to avoid (forbidden)

- False grounding — saying "passed" when the chunks don't actually
  support the claim. This is the worst failure mode; the synthesizer
  will then ship a claim with grounding that doesn't exist.
- Over-citing — listing every chunk that mentions the topic, not the
  chunks that actually support the specific claim.
- Confabulated chunk_ids — citing a chunk_id that doesn't exist in
  the search results. Hallucinated ids must trigger `ambiguous` per
  the existing handler.

## Hypotheses to try when iterating

1. Lower the cosine-similarity threshold for chunk retrieval to
   raise recall, but require a stronger semantic match before
   `passed`. Measure false-passed rate.
2. Require the grounder to cite at least 2 chunks for any `passed`
   verdict on a quantitative claim. Measure attribution accuracy.
3. Make the four failure reasons mutually exclusive (no overlapping
   diagnosis). Measure operator's ability to act on the verdict.

## Cross-references

- Master-spec §3.1 (grounder is among the 12 roles, post-Sprint 13)
- Substrate `interfaces/research/api/grounding.py` (the grounder
  bridge — receives `claim.challenge_raised`, emits
  `claim.grounding_check_passed` or `claim.grounding_check_failed`)
- `roles/_json_decode.py` (shared JSON-decode helper)
