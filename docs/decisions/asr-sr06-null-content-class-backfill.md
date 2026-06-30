# ASR SR-06 NULL content_class backfill

**Status:** partial. The offline operator tool exists and is tested; the
production DB backfill has not been run.

## Decision

`tools.backfill_null_content_class` is the SR-06 migration surface for legacy
`documents.content_class IS NULL` rows. It is dry-run by default, rejects the
substrate default DB path, and mutates rows only through
`update_document_gate_columns` under the existing DuckDB write lock.

Classification is conservative:

- third-party personal-ingest document types -> `personal_reading`
- `metadata.license_content_class` -> that explicit valid class
- arXiv rows with T2/T3 rights tier -> `restricted_pending_opt_in`
- `book_assets.license_basis` with CC0/CC-BY markers -> the corrected open class
- unresolved rows block `--apply` unless the operator passes
  `--allow-unresolved-to-gated`

The explicit unresolved flag is intentional. SR-07 should not flip NULL
fail-closed until the operator has either classified every NULL row or moved the
remaining ambiguous rows to the gated floor.

## Operator Path

1. Run a dry-run against a non-default DB path:
   `uv run --extra dev python -m tools.backfill_null_content_class --db-path /path/to/antiek.duckdb`
2. Inspect unresolved rows and repair metadata where possible.
3. Apply only when the dry-run is acceptable:
   `uv run --extra dev python -m tools.backfill_null_content_class --db-path /path/to/antiek.duckdb --apply`
4. If unresolved rows should be denied by default instead of hand-classified, add
   `--allow-unresolved-to-gated`.

## Verification

`tests/test_backfill_null_content_class.py` covers dry-run purity, deterministic
classification, unresolved refusal, explicit gated fallback, idempotency,
gate-helper usage, event emission, and the prod guard.
