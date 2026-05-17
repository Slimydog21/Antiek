# substrate/attribution/

Source-to-output citation tracking.

Two source classes need different handling:

- **Public sources** (papers, books, articles, public web content) —
  attribution is to a public document. URL or DOI plus retrieval
  timestamp suffices.
- **Primary interview sources** (DeepBlu lineage) — attribution is to
  a person who explicitly contributed material. The schemas carry
  consent metadata, contribution scope, and citation-rights flags.

## Contract

Every node in the graph carries `source_attribution_id` references
back to the original chunk(s) it was extracted from. Every synthesis
records the full attribution chain. There is no path from a synthesis
sentence to "we don't know where this came from."

This is also load-bearing for the eventual monetization layer in
DeepBlu (revenue sharing requires reliable contribution accounting),
though that layer is deferred.
