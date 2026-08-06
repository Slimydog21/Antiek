# SWARM BRIEF — glm-cc — generic doc→HTML upload endpoint

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. STACKED on the round-1 reader-snapshot lane — the sanitized reader_html store +
serve gate already exist here (read them first).

## Hard guardrails (you have a fabrication history — every claim must be backed by a command you ran)
- Work ONLY inside this worktree (`/tmp/antiek-swarm2/glm-upload`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm2/doc-upload`.
- NO stub-theater and NO fabricated claims. If genuinely blocked, write `BLOCKED.md` and stop.
- Tests must actually run and assert real behavior. venv: `~/Antiek/platform/.venv/bin/python`,
  run from worktree root. ruff + mypy --strict on new code.

## Context already on this branch (do NOT rebuild)
`substrate/reader_html/store.py` (`store_reader_html` — sanitizes + stamps SANITIZER_VERSION) and
the `GET /sources/{id}/reader-html` fail-closed serve gate. Reuse `store_reader_html` for storage.
Also read `substrate/books/html_sanitizer.py` and any markitdown/PDF→text usage in the repo.

## The sub-goal
Ingest an UPLOADED document (not a URL) and make it viewable as sanitized HTML. Read this spec IN
FULL first (section 5A / S4):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/doc-to-html-and-style-wheel.md`

### Scope (bounded — exactly this)
`POST /sources/upload` (multipart): `file` + a required `acquisition_attestation`
(`user_owned`|`personal_reading`, the Bartz lawful-acquisition receipt).
- Sniff type by MAGIC BYTES first (`%PDF-`, `PK\x03\x04`, leading `<`), extension second.
- PDF → extract to text/HTML (reuse the repo's PDF path) → sanitize → store.
- `.html` → sanitize (allowlist) → store. `.md`/`.txt` → markdown→safe-HTML → sanitize → store.
- `.epub`/PK-zip → `409 {"detail": "EPUB goes through the authorized book-acquisition ceremony"}`
  — do NOT fork that lane.
- Store via `store_reader_html` (sanitizer version-provenance); `content_class` from attestation
  (`personal_reading` unless `user_owned`).

### CRITICAL guardrail (this is the whole point)
The stored/served body MUST pass the trusted version-provenance sanitizer — NEVER store raw
uploaded HTML as trusted (stored-XSS class). If the existing store/sanitizer API can't do this,
write `BLOCKED.md` — do NOT store unsanitized HTML.

### Acceptance (must pass for real)
Tests (fixtures, no live net): uploading a small PDF fixture → stored + served as sanitized
`content_format=html`; uploading `.epub`/PK-zip → 409; an uploaded HTML with a `<script>` → the
STORED body is sanitized (red-proof test); missing/invalid attestation → 4xx. Report exact pass
counts.

### Non-goals
NO generic-URL ingest (that's the reader-snapshot lane, already built). NO EPUB port (409 only).
NO frontend. NO reader convergence. Just the upload endpoint + conversion + sanitizer + store.

## When done
`git add -A && git commit -m "feat(reader): POST /sources/upload → sanitized HTML"`, then write
`DONE.md`: files, exact test command + real result, honest gaps.
