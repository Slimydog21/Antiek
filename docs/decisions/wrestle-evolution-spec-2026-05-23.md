# Wrestle Evolution — spec + integration verdict (2026-05-23)

**Decision date:** 2026-05-21 (spec lock) → 2026-05-23 (integration session-end)
**Status:** ⏳ Code complete on `wrestle-evolution/integration` branch; **push to `origin/main` pending operator review**.
**Scope:** Recasts the Wrestle reading workflow (`apps/reading/src/modes/WrestleApp/`) from a researcher-grade three-pane shell into a dual-market product (researcher + cozy reader), substrate-first, with the behavior store as the on-policy RL substrate.

## Where everything lives

- **Spec bundle (ON MAIN):** `specs/wrestle-evolution/` — 11 sprint pages + index.html, generated 2026-05-21 via `/htmlspec` from operator brainstorm. Self-contained HTML (no network), Lemon UI styling (no PostHog brand copying).
- **Integration branch (NOT ON MAIN):** `wrestle-evolution/integration` — 58 commits ahead of `main`, all tests passing (209 pytest + 115 vitest + tsc clean). **Not pushed to origin.** Every file path under "What shipped" below lives on this branch only until the operator merges.
- **Sprint feature branches (NOT ON MAIN):** `wrestle-evolution/spr-01-...` through `spr-11-...` (11 branches) + three staging branches (`wave-1-staging`, `wave-2-spr08-staging`, `wave-3-spr09-staging`). All local; all unpushed.

## Six binding decisions (locked during spec generation)

| # | Decision | Why |
|---|---|---|
| 1 | **Dual-market positioning is real** (researcher + 50-year-old cozy reader), not a thought experiment | Operator confirmed during `/htmlspec` interview. Reading-mode toggle is first-class. Universal library is the consumer onboarding wedge. Sprint 17+ positioning gets an update layer. |
| 2 | **Native `.antiek` container lands Sprint 18** alongside the notebook surface | Born-Antiek content (notebooks, deliverables, public-graph contributions) is a richer object than any PDF; PDF export becomes the lossy projection target. PDF stays source-of-truth for imported content (sidecar overlay carries user data). |
| 3 | **Behavior store deletes future events on opt-out only** — trained models persist | Industry-standard (OpenAI, Anthropic). Trust Center wording: "we stop collecting; trained models persist." Stronger posture (re-train on delete) is operationally prohibitive at Loop-3 trajectory volumes. EU regulator ruling is the documented reverser; tracked under G8/§14.2. |
| 4 | **Substrate-first wave sequencing** | Wave 1 (behavior store, voice anchor, ingest backend) → Wave 2 (5 surfaces + per-doc notebook recast) → Wave 3 (.antiek native + sidecar + per-theme notebook). Avoids the "surfaces emit into ad-hoc tables, retroactive normalization" failure mode the master spec named. |
| 5 | **Three-tier notes model** | Tier-1 = session event stream in `substrate/behavior/` (behavior regime, privacy-gated, RL data). Tier-2 = per-document notebook in `services/notebooks/` (knowledge regime, IP, auto-populated from Tier-1, no authoring). Tier-3 = per-theme notebook (hand-curated initially, cross-document, ships to Sprint 19 Brainstorming Workstation when it lands). Replaces the earlier "ambient notebook" framing that conflated session traces with knowledge artifacts. |
| 6 | **Gutter cross-doc links replace CrossDocSidebar from default** | The brainstorm identified eyeball-distance as the cross-doc UX failure. Gutter pills (in-PdfViewer, 1–3 per highlight) supersede the sidebar. CrossDocSidebar removed from default panel starters; reachable via Cmd+Shift+J slide-out. |

## What shipped on the integration branch (58 commits)

**All file paths in this section live on `wrestle-evolution/integration`, NOT on `origin/main`.** Categorized by spec section the work satisfies:

### Substrate (Wave 1 + later additions)
- `substrate/behavior/` — Tier-1 store, 19-type closed taxonomy, DP shuffler (ε=1.0/δ=1e-9), opt-in consent gate, emit API + TS client mirror, 3 reward-proxy backfill workers (immediate + medium real; deep real via deliverables join)
- `substrate/behavior/sessions.py` — derived `last_session_at` + `is_returning_user` over `behavior_events` (no new table — the data was already there)
- `substrate/voice/` — voice_note_anchor primitive with `(document_id, page, bbox)` + `chunk_id` dual-key; SPR-02 honored the chunks-geometry gap with a documented no-op until the chunker landed
- `substrate/graph/migrations/0001_chunks_geometry_and_raw_bytes.sql` — added `chunks.page`, `chunks.bbox`, `documents.raw_bytes_path`; folded into `ensure_initialized`
- `substrate/notebooks/` — deliverables publication overlay (publication_uri + published_at columns + `deliverable_citations` join table), `reward_deep` worker join

### Services
- `services/ingestion/` — universal-library ingest pipeline; inherited + fixed all 5 SPR-03 arXiv failure modes (cross-process throttle, banned-until sentinel, SSL env exports, 10× metadata cache)
- `services/library/raw_bytes_store.py` — content-addressed PDF/HTML/EPUB store at `~/.antiek/raw/<sha2>/<sha256>.<ext>`; dedup-by-hash, integrity-verify-by-hash
- `services/library/thumbnails.py` — PDF page-1 thumbnail generator (pdf2image / PyMuPDF fallback; graceful no-backend stub)
- `services/voice/audio_store.py` — voice-note audio at `~/.antiek/audio/<voice_note_id>.opus`; 1:1 keyed by voice_note_id
- `services/notebooks/` — per-doc notebook recast (Sprint 18 Wedge 2 tightening: drop "+ new block" authoring; auto-populate from Tier-1; demote-noise UX); per-theme notebook (Tier-3, Sprint 19 alignment)
- `services/antiek_format/` — `.antiek` native + sidecar containers; deterministic ZIP_STORED + 1980 timestamps for byte-identical writes; Ed25519 signature; markdown projection fallback; `_FORBIDDEN_SUBSTRATE_FIELDS` byte-grep enforces the master-spec invariant
- `services/cross_doc/` — gutter links query layer; P99 latency 9.0ms measured against 10k chunks + 500 edges
- `processing/chunking/pdf_chunker.py` — PDF page-tagging decorator over the existing markdown chunker; stamps page + proportional vertical-band bbox per chunk (no PyMuPDF/pdfplumber dep)

### HTTP routes (21 mounted, all in `interfaces/research/api/`)
- `library.py` — POST `/api/library/ingest`, GET `/api/library/ingest/{job_id}`
- `voice.py` — POST `/api/voice/anchor`, GET `/api/voice/anchor/{id}/audio`
- `cross_doc_links.py` — POST `/api/cross_doc/links` (gutter)
- `notebooks.py` — GET/POST `/api/notebooks/by-doc/{id}` + auto-populate + demote
- `themes.py` — list/create/read themes; promote/reorder/dismiss-stale; export (.antiek + markdown; PDF=501 honest stub)
- `share_bundle.py` — POST `/api/library/share-bundle` (lazy-fetches arxiv PDFs via the SPR-03 hardened fetcher on demand)
- `users.py` — GET `/api/users/me/is-returning`
- `admin_reward_proxy.py` — POST `/api/admin/reward-proxy/run` + `@app.on_event("startup")` sweep

### UI surfaces (`apps/reading/src/`)
- `modes/WrestleApp/` — reading-mode toggle + Cmd+R; Cmd+K AI command palette; Cmd+Shift+J CrossDocs slide-out; ?chunk= URL param parsing + scrollToChunkWhenReady; ShareWithAnnotations button
- `modes/Library/` — URL paste bar + library card grid + folders/tags sidebar + empty state
- `modes/Notebook/` — per-doc notebook (PerDocNotebook + DemoteZone + 6 block types) + per-theme notebook (PerThemeNotebook + PromoteToTheme + ThemesIndex + SuggestedThemes stub) + ThemeSaveAs
- `modes/WrestleApp/PdfViewer/` — voice anchor recording UI (HighlightToolbar + VoiceAnchor + VoiceRecorder + VoiceGlyph + VoiceGlyphLayer + VoicePlayback) + gutter pills (Gutter + GutterPill + CitePreview)
- `workspace/` — `ThemesIndex` registered as a `PanelKind` so Sprint 19 can mount it

### Behavior-event taxonomy (v2; 19 total types)
18 of 19 emit at real call sites. The 19th — `highlight_removed` — has the schema but no UI affordance; recorded as deferral D12 below.

## Why this is the right call

- The substrate-first sequencing held: every Wave 2 surface emits through `emit_behavior_event` rather than ad-hoc tables. No retroactive normalization debt.
- The .antiek invariant held: `_FORBIDDEN_SUBSTRATE_FIELDS` byte-grep + writer pre-flight refusal make it mechanically impossible to ship chunks/embeddings/edges inside a `.antiek` file. Substrate evolution stays unblocked.
- The auto-populate-not-author rule on per-doc notebooks is enforced at 4 layers (BLOCK_TAXONOMY.md docs, persistence `__post_init__` raises, Prose component ORPHAN warning, DOM-level vitest greps for "+ new block").
- Every reward-proxy join SQL is documented + the workers are idempotent + the FastAPI startup sweep means the columns populate on every boot.

## Open follow-ups (operator-decision)

| Item | Owner | Inputs needed |
|---|---|---|
| **Push the integration branch** | Operator | Code review of 58 commits; `git push -u origin wrestle-evolution/integration` (or all 14 branches via the explicit list in CLAUDE.md's git-log if cherry-picking) |
| **DP shuffler ε/δ ratification** for `behavior_training_export` | Operator | Confirm "medium" sensitivity (ε=1.0, δ=1e-9) is correct for highlight/AI/click data before any production export runs. Documented in `substrate/behavior/PRIVACY.md`. |
| **Auto-retry policy** for ingest 5xx | Operator | SPR-03 chose "fail clearly"; operator decides whether to add tenacity-style exponential backoff |
| **Redis provisioning** for production ingestion throttle | Ops | `ANTIEK_INGEST_REDIS_URL` must point at a real Redis instance; otherwise throttle degrades to no-op |
| **`write_log` migration ownership** | Substrate | The "db_lock: write_log insert failed (non-fatal)" warning pre-exists; needs a canonical migration |
| **`highlight_removed` UI affordance** | Design | See deferral D12 in `engineering_deferrals.md` |
| **Dev-env installs** | Operator | `scripts/install-optional-deps.sh` covers Playwright + TipTap + pdf2image + fakeredis+fastapi as independent groups |

## How this relates to the rest of the spec

The Wrestle Evolution work is **additive to the master spec**, not a replacement. It sharpens Sprint 18's Wedge 2 (the per-document notebook surface), extends Sprint 19 (per-theme notebooks land panel-ready for the Brainstorming Workstation), and adds the substrate that the master spec's reward chain (interaction → notebook → deliverable → publication, §5.6) requires — chunk geometry, raw bytes storage, deliverable publication overlay, audio blobs.

- Touches `master-product-spec.md`: no changes. The decisions above are operator-ratified extensions; the spec body remains the design-intent document.
- Touches `operator_gate_actions.md`: no new gates surfaced. The five remaining ones (G2, G3, G6, G7, G8) are unchanged.
- Touches `engineering_deferrals.md`: one new entry, D12 (`highlight_removed` UI affordance).

## Test inventory on the branch

| Layer | Count | Detail |
|---|---|---|
| Python pytest (substrate + services + processing, less fakeredis-deps) | 209 passing | Includes 38 new tests added across gap-closure passes |
| TypeScript tsc | 0 errors | `pnpm tsc -b --noEmit` clean |
| Vitest | 115 passing + 9 INTEGRATION-SKIP | The 9 skips assert against a pre-sprint-6 DOM shape that doesn't exist in PanelHost-land; test-seed rewrite is operator scope |
| Storybook | builds clean | 16+ new stories across Library, Notebook, voice components |

## Companion artifacts

- `specs/wrestle-evolution/index.html` (on main) — the master spec page; open in any browser, no network needed
- `specs/wrestle-evolution/sprint-NN-*.html` (on main) — 11 sprint pages, each self-contained with the five-values rigor block
- `specs/wrestle-evolution/README.md` (on main) — machine-readable summary
- `scripts/install-optional-deps.sh` (on integration branch only) — one-shot installer for the 4 dev-env dep groups; lands on main when the operator pushes the branch
- This file (on main)
