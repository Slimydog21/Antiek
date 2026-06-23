# Write outline bridge — ANT-AHT SPR-AHT-06

`GET /research/{id}/artifact/blocks` returns `OutlineBlockRef` rows (`node_id`, `kind`, `label`, `artifact_path`) for Write Lego drag.

**UI (exec-5):** `ArtifactOutlineShelf` in `DistillView` loads blocks + `POST …/artifact/export`; drags emit `PaletteDragPayload` / `DRAG_MIME` (same contract as Repository).

Blocks are graph-backed; HTML is packaging only.