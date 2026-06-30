# ASR SR-10 source census producer

**Status:** partial. The deterministic producer exists; the live
`reports/source_census.json` artifact is still operator-gated on a production corpus
run.

## Decision

`tools.source_census.compute_source_census(con, source)` is the single producer for
the source-onboarding corpus-value census consumed by `tools/lint/source_gate.py`.
It reads the persisted `documents` table and emits the existing `SourceCensus`
contract:

- metadata completeness: title plus persisted HTTP(S) origin link
- linkback resolvability: persisted HTTP(S) origin link present
- dedup overlap: repeat high-confidence identity keys from `substrate.dedup`
- T1/open share: advisory rights signals from `rights_tier` and `content_class`

The producer performs no network fetches. Live HTTP reachability would make the
gate nondeterministic and belongs in a separate operator audit. The gate's
"linkback-resolvable" metric therefore means "the corpus row has a usable origin
URI persisted in SQL."

## Remaining SR-10 Work

Run the producer against the real corpus after the arXiv ingest window is healthy,
commit `reports/source_census.json`, and calibrate the provisional thresholds
against that first measured baseline. Until the artifact exists, `source_gate.py`
continues to pass with an explicit "no census" message.

## Verification

Synthetic tests in `tests/test_source_gate.py` cover arXiv version dedup,
non-reference source-local dedup, unrelated-row filtering, and the empty-source
structural failure row.
