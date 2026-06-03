# ASR SR-09 P5: chunk provenance — personal_reading non-citable

**Date:** 2026-06-02  
**Sprint:** SR-09 (code-only slice; P4 OAI daemon out of scope)  
**Depends on:** SR-07 (NULL fail-closed retrieval gate), Personal-Reading Lane SPR-01

## Decision

Public synthesis and attribution-eligible citation sets must treat
`personal_reading` chunks and parent documents as **non-citable**. Owner paths
may retrieve full bodies under privileged `policy_tag`s; that read access does
not confer citation eligibility.

The policy is encoded in codegen and enforced by GATE-CONFORMANCE:

| Artifact | Role |
|----------|------|
| `tools/codegen/chunk_provenance.py` | `NON_CITABLE_CONTENT_CLASSES`, `is_chunk_citable`, `is_document_citable`, `provenance_policy_errors()` |
| `tools/codegen/check_conformance.py` | Calls `chunk_provenance_errors()`; exit 1 on drift |
| `tests/test_conformance_gate.py` | Positive alignment + injected drift negative |

## Cross-vocabulary alignment (what the gate checks)

`provenance_policy_errors()` asserts `personal_reading` is simultaneously:

- in `NON_CITABLE_CONTENT_CLASSES` (this module)
- in `NON_ATTRIBUTABLE_CONTENT_CLASSES` (`collective_graph/eligibility.py`)
- absent from `PUBLIC_GRAPH_CONTENT_CLASSES` (`ad_inventory/attribution.py`)
- in `PERSONAL_ONLY_CONTENT_CLASSES` and `_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES` (`graph/retrieval_gate.py`)
- absent from `SERVABLE_CONTENT_CLASSES` (`substrate/constants.py`)

A maintainer who removes the class from one set but not another gets a loud CI
failure instead of a silent citation leak.

## Steelman rejected

**Shortcut:** skip codegen; rely on existing `test_personal_reading_lane.py` only.

**Why it fails §9.0:** retrieval/serve tests prove read-path exclusion, not that
synthesis provenance vocabularies stay aligned after parallel edits. SR-09's
GATE-CONFORMANCE is the compound sprint's mechanical close for P5; weakening it
would leave P5 narrative-only while SR-10 still depends on "SR-09 partial."

## Out of scope (this pass)

- `arxiv_oai_sync` systemd / live OAI (operator P4)
- `mock source_census` / network census
- Runtime citation filter in synthesis paths (future; policy is pinned here first)

## Verification

```bash
python tools/codegen/check_conformance.py   # exit 0
pytest tests/test_conformance_gate.py -q    # green
```