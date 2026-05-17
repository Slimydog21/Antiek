# middleware/source_tier/

Rule-based source-tier assignment with LLM-downward adjustment.

## The asymmetry

The LLM can argue that a source is **less** reliable than the rules
say. It cannot argue that a source is **more** reliable than the rules
say. This is by design — the LLM cannot rationalize weak sources
upward into load-bearing assertions.

See architecture_notes §4.

## Tiers

Defined in `substrate/constants.py:SOURCE_TIERS`:

```
peer_reviewed, preprint, primary_interview, official_filing,
journalism_quality, journalism_general, social_media, unverified
```

`primary_interview` is the new tier added in this consolidation
(DeepBlu lineage). It sits with its own staleness rules — a subject's
stated facts about their own life don't go stale the way market data
does, but their stated opinions about current events do.

## Events emitted

- `assign_tier` — for each source, with the rule-determined tier and
  any LLM-suggested downward adjustment
