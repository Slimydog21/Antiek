# middleware/archive/

Synthesis archival with version stamping.

## What gets stamped

Every archived synthesis records:
- `ANTIEK_PARAM_VERSION` (from `substrate/constants.py`)
- The full skill-version triple: `(domain_version, process_version, verification_version)`
- The dispatch configuration hash (so we can tell which routing was in
  effect)
- The list of source attributions
- The list of unresolved sub-questions

## Storage

Archived syntheses live in DuckDB (table `archived_syntheses`) and as
Markdown files at `~/.antiek/syntheses/` for human review.

## Events emitted

- `archive_synthesis` — with the full stamp metadata
