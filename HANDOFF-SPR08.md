## Sprint SPR-08 — Handoff

### Status
DONE

### Files touched
- `acquisition/web_layer/__init__.py:1` — exports the public web-layer contract.
- `acquisition/web_layer/interfaces.py:1` — vendor-neutral discovery/extraction Protocols and provenance-bearing results; credentials are absent by construction.
- `acquisition/web_layer/cost.py:1` — pure Decimal cost records with dated, cited vendor rows.
- `acquisition/web_layer/exa_discovery.py:1` — injected Exa-shaped search/findSimilar adapter, clock, HTTP, configuration red-proof, and provenance parsing.
- `acquisition/web_layer/jina_extract.py:1` — injected GET-only Jina Reader-prefix extraction adapter on the documented free basic path.
- `acquisition/web_layer/stub_extract.py:1` — second extraction implementation with a different, in-process document-map shape.
- `acquisition/web_layer/pipeline.py:1` — discover → bounded select → extract composition and exact cost aggregation.
- `acquisition/web_layer/WIRING.md:1` — frozen research-loop, URL-ingest, legal-gate, run-actual, and SPR-06 follow-ups.
- `tests/test_web_layer.py:1` — fixed-clock recorded fixtures, socket guard, key red-proof, one shared extraction suite, and pipeline proof.

### Milestones
- [x] M1: Adapter interfaces + cost record — commit `7b0e5065d`; Protocol separation and hand-computed Exa/Jina examples pass.
- [x] M2: Exa-class discovery implementation — commit `76f1e1af4`; search and highlight-spawn findSimilar fixtures pass; missing key fails before HTTP and never renders.
- [x] M3: Jina-class extraction implementation + swap stub — commit `60372025a`; both implementations pass the same parametrized test body without vendor branches.
- [x] M4: Composition pipeline + tests + WIRING.md — commit `3a8e1ec42`; 3 hits → 2 extractions and exact record aggregation pass.

### Verification gate results
- pytest: pass

  ```text
  .........                                                                [100%]
  9 passed in 0.19s
  ```

- mypy strict: pass

  ```text
  Success: no issues found in 7 source files
  ```

- ruff: pass

  ```text
  All checks passed!
  ```

- seam purity: pass by path inspection. The spec's literal command exits 0 but Git's pathless summary survives `grep -v web_layer`:

  ```text
   9 files changed, 782 insertions(+)
  ```

  The stricter supplemental command
  `git diff --name-only origin/campaign/research-reading-spine-2026-07-09-main -- . | grep -v -E '^(acquisition/web_layer/|tests/test_web_layer\.py$)'`
  produced no output. The complete changed path list is exactly the nine files listed above.

### WIRING.md entries added (frozen-file needs documented, not edited)
- `runtime/research_runner/` → invoke only after paid-operation reservation and persist individual cost records into SPR-01 actuals.
- Highlight-spawn owner → call `find_similar` from the existing source URL, then legal-gate and explicitly promote.
- `acquisition/urls/adapter.py` → retain canonical document identity/event/chunk/graph authority after selection.
- SPR-06 corpus owner → adapt accepted canonical URL documents, full-text provenance, and cost references; never feed extraction directly to synthesis.

### Decisions made mid-flight
- Decision: use Jina's documented free, no-key basic Reader path and estimate `$0.00` per URL. Official Jina material says keyed higher-rate use is token-billed, so treating a keyed call as a fixed `$0.00` URL would be dishonest. A future keyed adapter needs a separate output-token-priced row. Reverse this when Jina publishes and the owner approves a stable token price/usage contract.
- Decision: selection is injected and mechanically constrained to discovery-returned hits. This enforces doctrine I-8 and reverses only if a separately reviewed URL authority is introduced.
- Decision: preserve vendor-native precision in each `Decimal` record and round only in presentation. This avoids systematic aggregation loss.

### Assumptions surfaced (rigor #1)
- Price rows are list-price snapshots verified/re-read 2026-07-11, not billed ground truth. Exa findSimilar remains the integration document's `$1/1k` snapshot and is explicitly absent from Exa's public price table.
- The doctrine's roughly 70%/10× cost advantage is NOT MEASURED here; it still requires live W0 traffic and deployment evidence.
- Tests prove local synchronous contract behavior and prohibit real sockets; they do not prove vendor availability, latency, response drift, or paid billing.

### Steelman of rejected alternative (rigor #2)
- A bundled search+extract vendor offers one credential, one invoice, fewer network hops, and potentially lower end-to-end latency with pre-digested snippets. It becomes preferable if measured composed-stack latency is qualitatively worse or price movement erases the separation advantage. The current choice preserves explicit provenance, cheaper basic reading, and independent swap freedom.

### Open questions discovered
- What is Exa findSimilar's current public billable price? Exa/operator billing owner; it is not listed on the current public pricing page.
- Which accepted paid-operation/run-actual contract should receive these records? SPR-01 integration owner after its stack lands.
- Will production need Jina's keyed higher-rate tier? Acquisition operator after W0 load evidence; that decision requires token-usage accounting rather than the basic-path URL row.

### Next sprint can start when
- The runtime owner has a legal-gated, budget-authorized adoption seam and SPR-06 names its canonical ingested-document adapter; live cost claims wait for W0 traffic.
