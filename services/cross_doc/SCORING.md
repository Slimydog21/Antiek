# Cross-doc score fusion (SPR-07 M1)

## Final weights

```
similarity:    0.7
user_asserted: 0.2
citation:      0.1
```

These are the defaults baked into `services/cross_doc/query.py`
(`SCORING_WEIGHTS`). They are mutable at import time so an operator can
override via test fixtures or a future ENV-var path; callers may also
pass `weights=` directly to `get_cross_doc_links`.

## Why these numbers (rigor #1 — intellectual honesty)

**They are heuristic, not principled.** This is the first cut. SPR-07
ships the score-fusion harness; the weights themselves are operator
defaults that will be tuned by the behavior-events funnel once the
gutter pills have been in dogfood for ≥2 weeks. The handoff calls this
out as an open question.

### What CrossDocSidebar did

The pre-SPR-07 surface (`apps/reading/src/components/CrossDocSidebar.tsx`)
**did not implement a vector-similarity score fusion**. It listed the
events emitted by the connector role's
`cross_doc.question_answered` payloads — a different signal entirely
(operator-asked-question routed across documents via the agent loop).

That means there are **no prior in-repo weights to inherit**. The
honest framing is "no precedent — first cut, document the choice".

### How the three weights were chosen

- **Similarity = 0.7 (dominant)**. Similarity is the only signal
  available for *every* candidate and it scales continuously in
  [0, 1] (clamped — see `_collect_candidates` clamp on negative
  cosines). The boolean edge signals are sparse boosts on top. We do
  NOT want a candidate with no edge but high similarity (0.9) to be
  beaten by a candidate with weak similarity (0.1) plus an
  user-asserted edge. The 0.7/0.2 split achieves that:
    - hit-with-edge (sim 0.4 + user-asserted): 0.7·0.4 + 0.2 = 0.48
    - hit-without-edge (sim 0.9): 0.7·0.9 = 0.63
    - hit-with-both-edges (sim 0.4 + user + cite): 0.48 + 0.1 = 0.58

  The high-similarity-no-edge result wins, which is the intuition we
  want today (edges are sparse and noisy; similarity is dense and
  noisy).

- **User-asserted = 0.2**. User-asserted edges are operator-authored
  intent — the operator literally said "these two passages are
  connected". That deserves a meaningful boost. We hold it back from
  outweighing strong similarity because the substrate has not yet
  shipped the user-asserted-edge creation UI (it's out-of-scope for
  SPR-07 — see "Out of scope" in the sprint HTML). Until that UI is
  live, user-asserted edges are rare and any present-in-fixture
  evidence is high-trust; the 0.2 weight reflects "trust but don't
  let it dominate similarity".

- **Citation = 0.1**. Citation edges come from extractors (Sprint 4
  connector + Sprint 11 grounder paths). Their recall and precision
  are unmeasured against ground truth today. 0.1 is the conservative
  weight: present-in-result is a small positive nudge, absent is
  not a penalty. If/when the citation extractor lands a measured
  P/R, this weight is the one to revisit first.

## What would change these weights

The pill-funnel events emit four signals: `surfaced`, `previewed`,
`clicked`, `dismissed`. Two readings tell us the weights are wrong:

1. **High dismiss rate on high-similarity-no-edge results** — means
   pure-similarity is over-weighted (the model is matching topic but
   the operator finds the result irrelevant). Lower `similarity`,
   raise `user_asserted` + `citation`.

2. **High click-through on user-asserted-with-low-similarity** —
   means user-asserted is *under*-weighted (we surfaced because of
   the edge but the score-rank buried it). Raise `user_asserted`.

The metric to read is `cross_doc_link_clicked / cross_doc_link_surfaced`,
sliced by the `source` field (which leg each pill came from). If the
ratios diverge sharply by source, the weights are mis-tuned for the
operator's actual preferences.

## What this score is NOT

- **It is not a probability.** The fused score is in
  [0, ~1.0] for a typical mix of {sim, edge} signals but not
  normalised. Don't read it as P(relevant).
- **It is not a learned ranker.** Sprint 7 is the heuristic baseline.
  An on-policy RL pipeline that learns ranking from the
  `cross_doc_link_*` funnel is the natural successor — out of scope
  for this sprint.
- **It does not model session-coherence.** Two highlights on the
  same page that both surface the same target chunk will get the
  same score; we do not down-weight recently-surfaced targets.
  Listed as an open question for the next gutter-related sprint.

## Diversity guard

Score fusion alone would produce "3 chunks from the same book" runs.
The query layer enforces a `DEFAULT_MAX_PER_DOCUMENT = 1` cap (per
target document). This is independent of the weights and is what
prevents the "echo chamber" failure mode the brainstorm called out.
The cap is configurable per-call but the default is operator-tested
intuition: 3 different documents is more useful than 3 different
spots in the same document.

## Open questions for the next iteration

- Should we down-weight by document recency (operator just opened
  that doc → don't re-surface)?
- Should `user_asserted` weight scale with the asserting user's
  trust (single-operator = 1; multi-user opens this up)?
- Citation direction (cites vs cited_by): cited-by is "this doc
  influenced me" — different intent than "I read this for that".
  Today they share the `citation` flag.

These are not blocking SPR-07 closure; they belong in the
gutter-iteration sprint that consumes the first 2 weeks of funnel
data.
