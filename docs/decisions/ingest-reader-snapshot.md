# Ingest reader snapshot — ANT-AHT SPR-AHT-04

**Status:** Implemented (`acquisition/snapshot/reader_html.py`)

Optional sanitized HTML beside substrate chunks. Strips `<script>` and `<style>`. Not a second ingest path — derivative of fetched HTML.

**Wiring (exec-2):** Set `ANTIEK_READER_SNAPSHOT=1` (and optionally `ANTIEK_READER_SNAPSHOTS_DIR`) on successful graph write; `IngestUrlResult.reader_snapshot_path` returns the file path.

**Reconsider if:** operator wants automatic snapshot without env flag (default-on policy).