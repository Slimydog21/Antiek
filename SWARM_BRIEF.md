# SWARM BRIEF — codex-cc — anydoc ingestion adapter (memory-spec S1)

Autonomous coding agent. Execute ONE bounded sub-goal completely, in THIS worktree only. Real
production code. This executes S1 of the just-written agent-facing-memory spec.

## Hard guardrails
- Work ONLY inside this worktree (`/tmp/antiek-swarm3/codex-anydoc`). NEVER `cd` out, touch
  `~/Antiek/platform`/another worktree/`main`, or `git push`. Commit to `swarm3/anydoc-adapter`.
- NO stub-theater. If blocked, `BLOCKED.md` + stop. venv: `~/Antiek/platform/.venv/bin/python`,
  run tests from worktree root. ruff + mypy --strict on new code.
- **Do NOT `pip install firecrawl-anydoc` into the shared venv** (it is shared across worktrees —
  a real install is operator gate G1). Your tests MUST mock the anydoc binding so they are
  hermetic and pass whether or not the wheel is installed.

## The sub-goal
Wire firecrawl/anydoc (`firecrawl-anydoc`, MIT, pure-Rust, Python binding → clean GFM markdown)
into Antiek's file extraction so Office/ODF/RTF/CSV documents — which HARD-FAIL today — ingest as
clean markdown. Read this spec section IN FULL first (S1 + section 4):
`/Users/slimydog/Antiek/.infinite/goal-2026-08-06-usable-v1/specs/agent-facing-memory-anydoc.md`

### Verified current failure (the thing you fix)
`substrate/research_bridge/extractors.py::extract_text` (~line 55) returns `ok=False` "no extractor
lib installed" for `.docx/.doc/.rtf` (and Office/ODF/CSV have no branch at all). Read it + the
`ExtractionResult` type first.

### Scope (bounded — exactly this)
1. `pyproject.toml`: add an optional extra, e.g. `docs = ["firecrawl-anydoc>=0.1.6,<0.2"]`.
2. `extractors.py`: add `_extract_via_anydoc(data, *, filename, content_type)` that imports the
   anydoc python binding (find the REAL import/module name from the package) and converts bytes →
   GFM markdown; on `ImportError` (extra not installed) return `ExtractionResult(ok=False,
   reason="install the 'docs' extra (firecrawl-anydoc) to ingest Office/ODF/RTF/CSV")` — a
   graceful degrade, NEVER a crash. Return `kind="markdown"`, `extractor="anydoc"`,
   `converter_version="anydoc/0.1.6"`. Dispatch these extensions to it: `docx doc pptx ppt xlsx
   xls odt ods odp rtf csv` (and their variants). **Do NOT route `.epub` here** — EPUB stays on
   the authorized book-acquisition path (do not bypass its rights ceremony). Leave `.pdf` on the
   existing `_extract_pdf`.
3. `ingest_file.py` (or wherever chunking happens): when `kind=="markdown"`, prefer the
   heading-aware `chunk_markdown` over `_chunk_paragraphs` (~line 154).

### Acceptance (must pass for real — anydoc MOCKED)
Tests: with the anydoc binding MOCKED to return canned GFM (tables + headings) for a fake
`.docx/.xlsx/.pptx/.odt/.rtf/.csv`, `extract_text` returns `ok=True`, `kind="markdown"`, with the
table/heading content preserved (these all return `ok=False` today); with the import mocked to
raise `ImportError`, it degrades to `ok=False` with the install hint (no crash); markdown input
produces heading-aware chunks. Report exact pass counts. mypy --strict clean.

### Non-goals
NO EPUB routing (rights ceremony). NO PDF change. NO memory/graph layer (that's S2+, a later
lane). NO real wheel install. NO OCR. Just the extraction adapter + chunk preference + tests.

## When done
`git add -A && git commit -m "feat(ingest): anydoc adapter for Office/ODF/RTF/CSV -> markdown"`,
then write `DONE.md`: files, exact test command + real result, honest gaps (incl. G1 install).
