# SPR-01 Transport Manifest — services/antiek_format/ (wrestle-evolution → main)

**Sprint:** SPR-01, Antiek HTML Projection Layer (`~/specs/antiek-html-projection/`)
**Date:** 2026-06-12
**Status:** **BLOCKED-ON-SCOPE-DECISION** — M1 complete; M2–M6 deliberately not started.
**Source:** `wrestle-evolution/integration` @ `7f3aa89` (read-only checkout `~/Desktop/Antiek-integration`)
**Target base:** `origin/main` @ `acbe947` (fork point with source branch: `1892c779`)
**Working branch:** `caffen/hprj-SPR-01` (this file is a run artifact; whether it ships in the final PR is the next spin's call — the PR body must carry this manifest's content either way)

---

## 1. The separability honesty event (why this is BLOCKED)

The sprint page and the orchestrator both pre-committed the protocol: *if the format
slice imports branch-only modules, STOP after the inventory and record a scope
decision rather than transporting piecemeal.* The condition fired, and it is not a
technicality:

1. **The ratified format is two containers, not one.** Binding decision #2 in
   `docs/decisions/wrestle-evolution-spec-2026-05-23.md` ratifies the native
   container **and** the sidecar: "PDF stays source-of-truth for imported content
   (**sidecar overlay carries user data**)"; its shipped-inventory line reads
   "`services/antiek_format/` — .antiek **native + sidecar** containers".
   `SPEC.md` §11 ("Sidecar Variant (SPR-10)") is ~40% of the format spec.
2. **The sidecar half is functionally wired to branch-only substrate.**
   `sidecar_reader.apply_sidecar()` imports `substrate.behavior.taxonomy`
   (BehaviorEventType), `substrate.voice` (CHUNKER_VERSION), and
   `substrate.voice.anchor_api` (BBox, resolve_chunk_for_bbox) at call time —
   none exist on main (verified by import attempt; see §6). Its gate test
   `test_sidecar_e2e.py` imports `services.ingestion.sidecar_detector` at module
   level → **uncollectable on main** (verified: `ModuleNotFoundError`, 22 test
   functions / ~31% of the slice's test surface).
3. **Those upstream modules are exactly what this sprint's Out-of-scope forbids
   merging** ("behavior events, voice anchors"). So the full ratified slice cannot
   land without violating the sprint's scope, and a core-only landing is a partial
   transport of a ratified decision — a scope cut I (the builder) do not have the
   authority to make. Hence: scope decision required.

M2's acceptance bar — "imports resolve with **zero references** into branch-only
code" — is unsatisfiable by any transport of the full 17-file slice, and
satisfiable by a core-only cut only after someone with authority rules that the
cut does not fork the format lineage.

---

## 2. Per-file manifest (every file accounted)

### services/antiek_format/ — 17 files on branch @ 7f3aa89

| # | File | Verdict | Evidence |
|---|------|---------|----------|
| 1 | `__init__.py` | TRANSPORT (edit required under Option A) | Module-level re-exports of sidecar symbols (`apply_sidecar`, `write_sidecar`, `AnchorRow`, …). Imports cleanly on main because the sidecar modules guard their branch-only imports (spike CLAIM-1, §6). Under a core-only ruling the sidecar re-export block must be removed — a hand edit that must stay in this manifest. |
| 2 | `SPEC.md` | TRANSPORT (with caveat) | Pure doc. §11 documents the sidecar; under core-only landing it documents a variant not present on main — needs a status annotation or ships as-is with the absence named in the PR body. |
| 3 | `SIGNATURE_NOTES.md` | TRANSPORT | Pure doc, container-scoped key-management decisions. |
| 4 | `manifest.schema.json` | TRANSPORT | Data; consumed by `native_reader._validate_manifest`. |
| 5 | `native_writer.py` | TRANSPORT | stdlib + intra-slice only. Deterministic ZIP_STORED/1980-timestamps writer; `_FORBIDDEN_SUBSTRATE_FIELDS` lives here. |
| 6 | `native_reader.py` | TRANSPORT | stdlib + intra-slice; `jsonschema` is a **lazy, guarded** import with a manual-validation fallback (lines 416–420). |
| 7 | `markdown_projector.py` | TRANSPORT | stdlib + intra-slice only. |
| 8 | `signature.py` | TRANSPORT (dep addition required) | **Module-level `cryptography` import** (lines 39–43) — `cryptography` is in neither main's `pyproject.toml` nor the prod venv (verified: `ModuleNotFoundError`). The branch never declared it either — a latent defect on the branch; its tests passed in an env that happened to have it. `runtime.db_lock.connect_write` exists on main, branch left db_lock untouched (empty diff), call shape `connect_write(db_path, purpose=...)` is compatible (verified by running `ensure_keypair` against main's db_lock — spike CLAIM-3a). |
| 9 | `sidecar_writer.py` | ENTANGLED-SOFT | Module imports clean. `substrate.voice.CHUNKER_VERSION` is a function-level import with `except ImportError: CHUNKER_VERSION = "v1.0.0"` fallback (lines 482–485). Writer functions on main but stamps the fallback chunker version. |
| 10 | `sidecar_reader.py` | **ENTANGLED-HARD** | `read_sidecar` works on main; `apply_sidecar` imports `runtime.db_lock` (ok) + `substrate.behavior.taxonomy` + `substrate.voice` + `substrate.voice.anchor_api` at call time (lines 469–481) — the latter three are branch-only (§6). On main, `apply_sidecar` is dead-on-arrival code. |
| 11 | `tests/__init__.py` | TRANSPORT | Empty/marker. |
| 12 | `tests/conftest.py` | TRANSPORT | Imports only `WriterInput`, `ensure_keypair`; keypair table is create-on-demand, no substrate schema needed. |
| 13 | `tests/test_writer.py` | TRANSPORT | Core suite; passes against main substrate (§6). |
| 14 | `tests/test_reader.py` | TRANSPORT | Core suite; passes against main substrate (§6). |
| 15 | `tests/test_projector.py` | TRANSPORT | Core suite; passes against main substrate (§6). |
| 16 | `tests/test_e2e.py` | TRANSPORT | Core suite; passes against main substrate (§6). |
| 17 | `tests/test_sidecar_e2e.py` | **ENTANGLED-HARD** | Module-level `from services.ingestion.sidecar_detector import …` (branch-only) + in-test `from substrate.voice import CHUNKER_VERSION` (line 589); exercises `apply_sidecar` against a substrate DB. **Uncollectable on main** (verified). 22 test functions — the sidecar gates (sidecar determinism, hash-mismatch refusal, idempotency, unsigned-restore flagging) live ONLY here. |

Note: the branch has no `services/antiek_format/fixtures/` directory — fixtures are
constructed in-test/conftest. The sprint page's gate table references fixture paths
that will be created in M3 by whoever executes the transport.

### Export routes — named by the sprint page as `api/themes.py`, `api/share_bundle.py`

Actual location on branch: `interfaces/research/api/` (no top-level `api/` tree on
either branch or main; main HAS `interfaces/research/api/` with 33 route modules).

| File | Verdict | Evidence |
|------|---------|----------|
| `interfaces/research/api/themes.py` | **LEAVE** | Imports `services.notebooks.theme_persistence` — branch-only notebook surface (the route-level honesty event the orchestrator pre-named). SPR-06 of this spec wires routes later. |
| `interfaces/research/api/share_bundle.py` | **LEAVE** | It is the **sidecar** share flow: imports `services.antiek_format.sidecar_writer` + `ensure_keypair` + `substrate.graph.default_db_path` (exists on main) — but the flow only makes sense with the sidecar half landed; travels with the sidecar scope ruling. |
| `interfaces/research/api/app.py` (mount hunks `_register_themes(app)` / `_register_share_bundle(app)`) | **LEAVE** | Travel with the two routes above. |

### Out-of-slice modules a widened transport would drag in (NOT transported; sized for the ruling)

| Module | Size | Why it would come |
|--------|------|-------------------|
| `substrate/voice/` | ~1,860 lines (anchor_api.py 399, anchor_schema, migrate, migrations, workers, 665 lines of tests) | `apply_sidecar` anchor re-resolution (`resolve_chunk_for_bbox`, SPEC §11.3) |
| `substrate/behavior/` (at least `taxonomy.py`) | behavior store; taxonomy is one file but semantically opens the Tier-1 behavior regime | `apply_sidecar` voice-note restore emits `BehaviorEventType` |
| `substrate/graph/migrations/0001_chunks_geometry_and_raw_bytes.sql` + `ops.py` delta | ~85 lines | `chunks.page`/`chunks.bbox` columns anchor resolution queries |
| `services/ingestion/sidecar_detector.py` | 1 file, imports = stdlib + httpx + the slice itself (separable in isolation) — but lives in `services/ingestion/` (full ingest pipeline, Redis throttle, extractors) | `test_sidecar_e2e.py` module-level import |

All three substrate trees are explicitly named in this sprint's Out-of-scope
("three-tier notes surface, behavior events, voice anchors").

---

## 3. Drift measurement (M1 acceptance criterion 3)

- `origin/main` is **576 commits** ahead of the fork point `1892c779`.
- Commits on main touching `services/`, `interfaces/research/api/themes.py`,
  `interfaces/research/api/share_bundle.py`, or any `api/` tree since the fork
  point: **zero** (verified: empty `git log` over those paths). The slice lands
  net-new; there are no textual-conflict hazards, only the import-graph hazards
  in §1.
- `runtime/db_lock.py`: unchanged on the branch vs fork point (empty diff);
  main's `connect_write` is call-compatible (verified functionally).
- `substrate.graph.default_db_path`: exists on main (`substrate/graph/__init__.py:23`).
- Branch `pyproject.toml` delta vs fork point: **empty** — the branch added no
  dependency declarations despite requiring `cryptography` (latent branch defect,
  see §4).

---

## 4. Dependency additions transport requires

| Dep | Required? | Evidence |
|-----|-----------|----------|
| `cryptography` | **Mandatory** | Module-level in `signature.py`, which `__init__.py` imports unconditionally. Absent from main's `pyproject.toml` AND prod venv (verified `ModuleNotFoundError`). Without it the package does not import at all. |
| `jsonschema` | Optional (recommend declaring) | Lazy import with documented manual-validation fallback. Declaring it makes main validate manifests on the same path the branch's tests exercised. |

Note: main already carries `pynacl` (Ed25519-capable via `nacl.signing`). Porting
`signature.py` to pynacl would avoid the new dep but mutates ratified, gate-proven
code during transport — REJECT for this sprint; if desired it is an SPR-04-or-later
format-owner decision.

---

## 5. Scope-decision options (for the orchestrator/operator — not mine to make)

**Option A — Land the native-container core now; sequence the sidecar behind its substrate.**
Transport files 1–8, 11–16 (14 of 17), leave 9, 10, 17 + routes behind; hand-edit
`__init__.py` to drop sidecar re-exports; annotate SPEC.md §11 (or PR-body note).
- For: every downstream sprint (SPR-04 shell, SPR-06 emission, SPR-08 demand gate)
  consumes the **native** container only; 49 core tests proven green against main's
  substrate (§6); zero branch-only references afterward; M3's three gates
  (determinism / signature / forbidden-fields) all live in the core.
- Against: partial transport of ratified decision #2 (sidecar is named in it);
  two hand-edited files (manifest-documented); 22 sidecar tests stay behind.
- If chosen, the landing PR + amendment draft must state: *the sidecar variant
  lands when its substrate (voice anchors + behavior taxonomy + chunks-geometry
  migration) lands; it is sequenced, not dropped* — keeping decision #2's lineage
  one chain.

**Option B — Land all 17 files, leave/skip the sidecar e2e test.** REJECT.
Ships `apply_sidecar` as dead code that ImportErrors on main, violates M2's
zero-references bar, and lands a gate that has never been red OR green on main —
precisely the gate-dishonesty the sprint page forbids.

**Option C — Widen the transport to voice/behavior/ingestion substrate.** REJECT
at builder level: directly violates this sprint's Out-of-scope and silently merges
Wave-1 wrestle-evolution substrate without operator review. Only the operator can
re-scope this.

**Option D — Re-implement against the decision doc (the interview's rejected
alternative).** M1 evidence says transport got CHEAPER, not costlier, for the core
(net-new paths, zero drift conflicts, 49 tests already green on main's substrate)
— so the rejected alternative gained no strength there. For the sidecar the
blocker is substrate absence, which re-implementation cannot fix either. Transport
remains the right method; **the open question is the slice boundary, not the
method.**

**Builder's recommendation: Option A**, with the sidecar sequencing sentence in
the amendment draft. Reversal condition: if the operator rules the sidecar half
must land in the same PR as the native container (one-decision-one-landing), then
Option C's substrate set is the true transport scope and this spec's Out-of-scope
needs an operator amendment first.

---

## 6. Mechanical evidence (spike run, /tmp only — nothing landed on any branch)

Scratch venv (`uv venv` + `cryptography`, `duckdb`, `pytest`, `jsonschema`),
slice copied to `/tmp/hprj-m1-spike/services/antiek_format`, main's substrate via
`PYTHONPATH=<SPR-01 worktree @ acbe947>`:

1. `import services.antiek_format` → clean; 32 public exports (guards hold).
2. Branch-only imports against main: `substrate.behavior.taxonomy`,
   `substrate.voice`, `substrate.voice.anchor_api`,
   `services.ingestion.sidecar_detector` → all `ModuleNotFoundError` (so
   `apply_sidecar`'s call-time import block cannot succeed on main).
3. `ensure_keypair("user-spike", db_path=…)` against **main's**
   `runtime.db_lock.connect_write` → works (pre-existing, documented-on-main
   non-fatal `write_log` warning observed — named in the 2026-05-23 decision doc
   as pre-existing).
4. Determinism: double `write_antiek` of the same input → **byte-identical**
   (sha256 `fd4d3fb8387f88a7…` both runs). `read_antiek` → `signature_valid=True`;
   `project_to_markdown` → 276 bytes.
5. Core test files (`test_writer`, `test_reader`, `test_projector`, `test_e2e`):
   **49 passed in 1.25s** against main's substrate.
6. `test_sidecar_e2e.py` collection: **ERROR — `ModuleNotFoundError: No module
   named 'services.ingestion'`**; 0 of 22 tests collectable.

Spike directory removed after evidence capture.
