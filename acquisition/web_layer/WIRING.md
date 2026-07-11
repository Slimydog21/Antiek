# Web-layer wiring follow-ups

This sprint is additive and intentionally does not edit frozen integration sites.
The pipeline only extracts URLs returned by discovery; it does not write graph
state, bypass the legal gate, or feed extraction output directly to synthesis.

## Research-loop adoption

- `runtime/research_runner/` owner: invoke `WebPipeline.search_and_extract` from
  the source-acquisition phase only after the paid-operation/budget authority has
  reserved the provider call. Persist each returned `CostRecord` into SPR-01 run
  actuals. Do not reconstruct costs from totals.
- Highlight-spawn owner: call `DiscoveryAdapter.find_similar` with the selected
  highlight's existing source URL, then place proposals through the same legal
  gate and explicit promotion path used by `acquisition/search/exa/`. Do not
  auto-ingest pipeline results.
- `acquisition/urls/adapter.py` owner: after legal/operator selection, pass the
  selected URL and full `ExtractionResult.text` through the existing canonical
  URL document-id, event, chunking, and graph-write authority. This layer must
  not mint a second document identity or emit `DocumentLoadedPayload` itself.

## SPR-06 corpus contract

The SPR-06 owner should add a narrow adapter from accepted, canonically ingested
URL documents to its corpus contract. The adapter must expose source URL, full
text/span provenance, and the corresponding per-call cost references; it must
not consume extraction text directly as synthesis input (doctrine I-2).

## Operational constraints

- Enforce the retrieval-time legal gate between discovery and extraction.
- Keep `EXA_API_KEY` isolated to discovery. This Jina reference uses the
  documented free no-key Reader path; any future keyed higher-rate adapter must
  own a separate `JINA_API_KEY` namespace and a token-priced cost row.
- Re-verify every row in `cost.py` before paid adoption. A material Jina price
  increase or Exa search decrease that erases the composed-stack advantage is
  the explicit trigger to reconsider the pairing.
- Browser-render escalation remains a named mono-vendor Plan B. Do not silently
  fall through from this HTTP layer to Browserbase or AnchorBrowser.
