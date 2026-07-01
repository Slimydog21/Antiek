# Information-hiding leak audit — Ousterhout Ch. 5 lens

- Generated: `2026-07-01T14:17:12.642972+00:00`
- Files scanned: **1263** · first-party modules indexed: 674
- SPR-01 ranking joined: True (tool `9b84d12463ac`)
- Counts: L1=18 · L2=0 · L3=0
- Actionable (unfenced target): **14** · fenced targets segregated: 4

**Precision over recall** — a false positive misdirects an SPR-03/04 refactor. L3 is candidate-only.

## Top 30 actionable leaks (unfenced target, by target rank_score)

| # | caller path:line | leaked name | ← target module | cat | target rank |
|--:|------------------|-------------|-----------------|:---:|------------:|
| 1 | `acquisition/arxiv/enrich_openalex.py:64` | `_maybe_json` | `substrate.graph.ops` | L1 | 0.462098 |
| 2 | `acquisition/arxiv/oai_persist.py:52` | `_maybe_json` | `substrate.graph.ops` | L1 | 0.462098 |
| 3 | `acquisition/substack/adapter.py:62` | `_exists` | `substrate.graph.ops` | L1 | 0.462098 |
| 4 | `substrate/attribution/compute.py:179` | `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` | `substrate.graph.retrieval_gate` | L1 | 0.311346 |
| 5 | `substrate/contracts/servable.py:37` | `_SERVABLE_STATUSES` | `substrate.books.servability` | L1 | 0.241416 |
| 6 | `acquisition/arxiv/oai_pmh.py:44` | `_TierTally` | `substrate.schemas.documents` | L1 | 0.152244 |
| 7 | `acquisition/arxiv/oai_records.py:22` | `_TierTally` | `substrate.schemas.documents` | L1 | 0.152244 |
| 8 | `acquisition/arxiv/pdf_fetch.py:65` | `_looks_like_pdf` | `acquisition.openaccess.unpaywall` | L1 | — |
| 9 | `acquisition/arxiv/rate_governor.py:59` | `_ResponseLike` | `acquisition.arxiv.throttle` | L1 | — |
| 10 | `acquisition/search/exa/__main__.py:202` | `_parse_event_ts` | `acquisition.search.retention` | L1 | — |
| 11 | `acquisition/urls/__main__.py:14` | `_main` | `acquisition.urls.paulgraham` | L1 | — |
| 12 | `processing/extraction/extract.py:62` | `_extract_json_object` | `interfaces.research.api.wrestling` | L1 | — |
| 13 | `roles/cascade_planner/approval.py:34` | `_json` | `roles.cascade_planner.persist` | L1 | — |
| 14 | `substrate/unit_dedup.py:90` | `_cosine` | `interfaces.research.api.cross_doc` | L1 | — |

## Verification (milestone 4 — hand-labeled precision)

**L1/L2 precision: 14/14 (100%)** · Every actionable leak is a genuine private-name import (the imported name, pre-alias, is underscore-private) — 0 false positives. 10 are cross-package true leaks; 4 are same-subpackage co-ownership candidates (still true positives — the import IS of a private name across a module boundary; whether to close is SPR-03/04's call per rigor #2). L2=0: the import-rooted detector is proven working on a crafted fixture (flags dedup._registry._field, excludes self._cache and public chains) — this codebase leaks by IMPORTING the private name (L1), not by attribute-walking (L2). L3 (--include-l3) found 0 re-implementations of the 8 seeded canonical dedup helpers.

| caller path:line | ← target | verdict | note |
|------------------|----------|---------|------|
| `acquisition/arxiv/enrich_openalex.py:64` | `substrate.graph.ops._maybe_json` | true leak | acquisition depends on graph.ops's private JSON helper (cross-package) |
| `acquisition/arxiv/oai_persist.py:52` | `substrate.graph.ops._maybe_json` | true leak | same private helper, second caller |
| `acquisition/substack/adapter.py:62` | `substrate.graph.ops._exists` | true leak | private existence helper reused cross-package |
| `substrate/attribution/compute.py:179` | `substrate.graph.retrieval_gate._NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` | true leak | attribution couples to a §9.0 retrieval-gate private constant — a real coupling to the strategically-consequential layer |
| `substrate/contracts/servable.py:37` | `substrate.books.servability._SERVABLE_STATUSES` | true leak | private status set imported across modules |
| `acquisition/arxiv/oai_pmh.py:44` | `substrate.schemas.documents._TierTally` | true leak | private schema class leaked into acquisition |
| `acquisition/arxiv/oai_records.py:22` | `substrate.schemas.documents._TierTally` | true leak | same private class, second caller |
| `acquisition/arxiv/pdf_fetch.py:65` | `acquisition.openaccess.unpaywall._looks_like_pdf` | true leak | cross-subpackage private predicate (arxiv <- openaccess) |
| `acquisition/arxiv/rate_governor.py:59` | `acquisition.arxiv.throttle._ResponseLike` | true leak (co-ownership candidate) | sibling within acquisition.arxiv; may be intentional co-ownership — SPR-03/04 decides |
| `acquisition/search/exa/__main__.py:202` | `acquisition.search.retention._parse_event_ts` | true leak (co-ownership candidate) | within acquisition.search; possibly intended |
| `acquisition/urls/__main__.py:14` | `acquisition.urls.paulgraham._main` | true leak (co-ownership candidate) | a __main__ delegating to a sibling's _main — common pattern, still a private-name import |
| `processing/extraction/extract.py:62` | `interfaces.research.api.wrestling._extract_json_object` | true leak | processing couples to an interface-layer private JSON extractor (fallback import w/ type:ignore) |
| `roles/cascade_planner/approval.py:34` | `roles.cascade_planner.persist._json` | true leak (co-ownership candidate) | within roles.cascade_planner; sibling co-ownership |
| `substrate/unit_dedup.py:90` | `interfaces.research.api.cross_doc._cosine` | true leak | the spec-anticipated case (rigor #2): a substrate module depends on an interface-layer private (imported as _unit_cosine) — a real inversion worth SPR-03/04 attention |

