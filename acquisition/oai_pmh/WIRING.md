# SPR-07 wiring follow-up

The acquisition owner should replace search/poll discovery with `OaiPmhHarvester`
for bulk metadata jobs, while retaining the existing governed arXiv paths for any
remaining point fetches. The existing `acquisition/arxiv` implementation was
inspected: its current throttle is durable, but the historical process-local
throttle/no-sentinel design is the recorded May 2026 failure; OAI-PMH is arXiv's
designated bulk interface (https://info.arxiv.org/help/oa/index.html).

After SPR-06 lands, add adapters from each cached record (including `fetched_at`)
to its corpus contract. Do not add PDF fetching or paywall fallback: inaccessible
Substack archive records are intentionally metadata-only.
