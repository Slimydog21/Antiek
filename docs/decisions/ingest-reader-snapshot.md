# Ingest reader snapshot — ANT-AHT SPR-AHT-04

**Status:** Implemented (`acquisition/snapshot/reader_html.py`)

Canonical allowlisted HTML beside substrate chunks. It is a derived reading
projection, not a second ingest authority.

**SPR-AHT-08 override:** URL and PDF ingestion always returns a projection path.
Successful owner-readable URL ingests are viewable. Low-text extraction and
rights-unresolved books produce explicit non-viewable receipts. The retired
`ANTIEK_READER_SNAPSHOT` switch is ignored; `ANTIEK_READER_SNAPSHOTS_DIR` still
relocates the derived store.

**Books:** `ingest_pdf` remains fail-closed until `ingest_servable_book` resolves
content class, rights holder, owner scope, and servability. The resolved
projection is viewable only when the authoritative servability permits owner or
full-text reading.

**Replacement:** changed URL content is rejected on the default ignore path.
Explicit replacement archives chunks with downstream references as a historical
document revision, marks projection publication pending in document metadata,
atomically replaces the file, then acknowledges the exact projection hash as
ready. Alias resolution always regenerates from current substrate and rights
authority, repairing missing, stale, or pending files without a network fetch.
