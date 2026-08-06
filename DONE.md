# DONE — style-wheel HTTP API + per-user fork persistence (S2)

Executed on branch `swarm2/style-wheel-api`, worktree
`/tmp/antiek-swarm2/deepseek-stylapi`, against `fed3b27e1` (the committed
forkable-style-system backend: `services/html_projection/styles.py`,
`renderer.restyle_artifact`). No push.

## What shipped

| File | Role |
|---|---|
| `substrate/styles/__init__.py` | Package marker (exports `UserStyleStore`). |
| `substrate/styles/store.py` | Per-user fork persistence: DuckDB table `user_styles` keyed `(user_id, name)`. Writes funnel through `runtime.db_lock` (single-writer invariant); reads via `connect_read`. Table DDL is module-owned (`CREATE TABLE IF NOT EXISTS` on the write path) — `substrate/graph/schema.py` untouched. `created_at` is stored data only, giving deterministic fork order (`ORDER BY created_at, name`). `save()` replaces a fork in place via `ON CONFLICT DO UPDATE` (wheel position stable across edits). `delete()` is idempotent (returns bool). |
| `interfaces/research/api/style_routes.py` | `style_router`: `GET /styles` (builtins + caller's forks), `POST /styles` (validate → persist; 409 builtin override, 422 validation), `DELETE /styles/{name}` (204; 409 builtin, 404 unknown), `GET /artifacts/{id}/render?style=` (load stored projection HTML → `restyle_artifact` — no model call; 404 missing artifact/unknown style, 422 no-island, 413 oversize). Style resolution happens in the route (spec R5) and is passed by value. |
| `interfaces/research/api/app.py` | One-line `include_router(style_router)` beside the supersession include (additive). |
| `tests/test_style_api.py` | 28 TestClient tests (below). |

## Exact test command + real result

```
~/Antiek/platform/.venv/bin/python -m pytest tests/test_style_api.py -q
→ 28 passed, 1 warning (starlette deprecation warning from the venv's httpx)
```

Wider verification run from worktree root:

```
~/Antiek/platform/.venv/bin/python -m pytest tests/test_style_api.py \
  tests/test_supersession_routes.py tests/test_write_routes.py \
  tests/test_artifact_routes.py services/html_projection/tests/ -q
→ 459 passed, 1 warning
```

Ruff: `python -m ruff check substrate/styles/ interfaces/research/api/style_routes.py tests/test_style_api.py` → **All checks passed!**
Mypy strict: `python -m mypy substrate/styles/ interfaces/research/api/style_routes.py` → **0 errors in the new files** (repo-wide run surfaces only pre-existing errors in untouched files, incl. a `substrate/exhaustive.py` syntax-check artifact of mypy 2.1.0 on py3.12 vs the CI py3.14 baseline — `git diff` confirms that file is untouched).

Declared-bar CI gates (exact workflow invocation):
`python -m tools.lints.declared_bar enforce ruff --baseline-file tools/lints/baselines/declared_ruff.json` → pass (no output).
`python -m tools.lints.declared_bar enforce mypy --baseline-file tools/lints/baselines/declared_mypy.json` → 1 NEW violation, `substrate/exhaustive.py:116:0 NEW mypy:syntax` — **not introduced by this change** (file has zero diff; pre-existing environment drift, see above).

## Acceptance coverage (all pass for real, 28 tests)

- Create a fork → appears in `GET /styles` (builtin wheel order + fork last) — `test_create_fork_appears_in_listing`.
- Render an artifact in a style → `<style>` block differs from default while the data island is unchanged — asserted byte-for-byte: the restyled stylesheet equals the composed target stylesheet, `extract_island` recovers the same doc-model, and the document minus the `<style>` block is identical (`test_render_artifact_in_style_changes_stylesheet_keeps_island`, plus the default-style identity case).
- Delete a fork removes it (204, gone from listing, second delete 404) — `test_delete_fork_removes_it`.
- Deleting/overriding a builtin → 409 (`test_delete_builtin_is_409`, `test_post_override_builtin_is_409`).
- POST with unsafe CSS (`@import`, `javascript:`, `<script>`, `url(...)`) → 422, nothing persisted (`test_post_unsafe_css_is_422`, 4 seeds).
- Extras: bad slug / empty label → 422; unknown style → 404; missing artifact → 404; island-less stored HTML → typed 422; per-user isolation (fork invisible to other identities, same fork name scoped per owner); user forks immediately usable on the render endpoint.

## Honest gaps / notes

- **Identity in tests**: with auth env vars unset the middleware attaches the static `__operator__` identity. Per-user tests switch identity by monkeypatching `substrate.multi_user.auth.operator_claims` (the exact seam the middleware calls per request); there is no header-based user spoofing path. Per-user behavior in real multi-user auth is untested here (single-operator until Sprint 22 per CLAUDE.md).
- **Render endpoint input**: `restyle_artifact` requires a projection data island. The ANT-AHT research-artifact store's HTML (`substrate/research_artifact/render.py`) is NOT projection-engine output, so those files 422 honestly ("no usable projection data island") rather than rendering — the endpoint serves projection-engine artifacts (island-bearing), which is exactly the spec's restyle contract.
- **Stored-fork revalidation**: forks re-run `validate_style` on load (defense in depth); a stored fork that would fail a tightened validator is skipped with a log line rather than bricking the wheel (every row was validated at write time, so this only happens after a future gate tightening).
- **`created_at`**: wall-clock DB default used ONLY for wheel ordering, never as render input (rendering stays deterministic per spec I3/R5).
- **Response shape**: `GET /styles` returns full entries incl. `theme_css` (no separate per-style detail endpoint in this bounded scope); `builtin: bool` distinguishes house styles from forks. No `base_style_id` lineage tracking (out of the bounded brief; `ProjectionStyle` has no lineage field).
- **No frontend** (per non-goals), no changes to `styles.py`/`renderer.py`.
- The empty `swarm-run.log` is gitignored; `SWARM_BRIEF.md` is included in the commit per the brief's `git add -A` instruction.
