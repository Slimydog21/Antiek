# CODE NOTES — antiek-oym-p1 worktree

P1 implementation (Own Your Mind brief: docs/own-your-mind/12-p1-change-list.md).
Working ledger, not documentation. Branch `feat/own-your-mind-p1-privacy`,
fresh checkout of origin/main @ 569f4366f. No commits, no pushes, no git
mutations — files only.

## P1 §2 — Privacy toggles wired (backend + frontend + tests)

Wires the previously-unwired telemetry store
(`substrate/telemetry_preferences/preferences.py`, zero API/UI references
before this work) to the PrivacyDashboard. The API is the store's first
consumer.

### Implemented files

- `interfaces/research/api/settings_privacy.py` (new) — the API:
  - `GET /settings/privacy` → every surface of the LIVE production
    registry (`substrate/dp_shuffler/production.py`): surface_name,
    sensitivity, epsilon_per_day, opt_in_required, description,
    enabled, default_enabled. `enabled` = `is_enabled(...)` with
    `default_when_missing = not opt_in_required`; forbidden surfaces are
    pinned OFF (architecturally not collected). Descriptions come from a
    registry-name-keyed copy of the PrivacyDashboard's CATEGORY_DESCRIPTIONS
    (reconciled: the dashboard's old `source_tier_preference_signals` key
    never matched the registry's `source_tier_preference` — the API
    surfaces the registry name and keeps the dashboard's copy under it).
  - `PUT /settings/privacy` `{surface_name, enabled}` → 404 for surfaces
    not in the registry; 400 (honest message) for enabling a
    `sensitivity == "forbidden"` surface; upsert via `set_preference`;
    returns the updated row.
  - Store factory `create_preference_store()`: `ANTIEK_TELEMETRY_DB` wins,
    then `(ANTIEK_HOME)/telemetry/preferences.sqlite` (repo's canonical
    state-dir override, cf. `substrate/event_log/events.py` /
    `runtime/connectors/rate_governor.py`), then in-memory when no state
    dir is configured — never an implicit write to the operator's real
    `~/.antiek`. Unwritable sqlite path → in-memory fallback. Store is
    held on `app.state.telemetry_preference_store`, created lazily per
    app lifetime.
  - Registered in `interfaces/research/api/app.py` next to the settings
    registration (~line 1747): `register_settings_privacy_routes(app)`.
  - User scoping: `request.state.user_id` (fallback `__operator__`),
    matching `settings_models_admin.request_owner_user_id`.
- `tests/test_settings_privacy.py` (new) — 10 tests: canonical GET with
  registry-derived defaults (skill ON, source-tier OFF by opt-in, query
  forbidden), description reconciliation, PUT flip + GET reflection,
  forbidden-enable 400 (and disable accepted as no-op), unknown 404,
  extra-field 422, per-user scoping, sqlite persistence across a factory
  round-trip via `ANTIEK_TELEMETRY_DB`, in-memory fallback with no state
  dir, unwritable-path fallback.
- `apps/reading/src/api/privacy.ts` (new) — typed client:
  `fetchPrivacySettings()` / `setPrivacySurface(name, enabled)` over
  `apiFetch`, following the `src/api/settings.ts` pattern.
- `apps/reading/src/modes/PrivacyDashboard/index.tsx` (modified) — per-
  category `role="switch"` toggles driven by GET /settings/privacy with
  optimistic update + rollback on PUT failure (saving state disables the
  in-flight switch); forbidden surface renders as a locked row
  ("never collected (architectural) — locked", no toggle); ε badges,
  substrate-wide ε total, architectural guarantees, and deletion UI
  preserved. Server description is authoritative; the local
  CATEGORY_DESCRIPTIONS map (keys fixed to registry names) is a fallback.
  No Lemon Switch primitive exists in `src/components/lemon/` — used a
  repo-idiomatic button-based switch (checkbox styling precedent +
  `role="switch"`/`aria-checked`).
- `apps/reading/src/modes/PrivacyDashboard/PrivacyDashboard.test.tsx`
  (new) — 4 vitest tests (vi.mock for `../../lib/api` apiFetch +
  `../../api/privacy`): toggle rendering with registry-derived state,
  forbidden-surface lock, PUT on change with optimistic update, rollback
  + error surface on failure.

### Verification output (tails)

- `uv run pytest tests/test_settings_privacy.py -q` → `10 passed, 1
  warning` (warning: pre-existing StarletteDeprecationWarning on
  fastapi.testclient import).
- `uv run ruff check` on the new Python files + `app.py` → `All checks
  passed!`
- `cd apps/reading && npx tsc --noEmit` → exit 0.
- `npx vitest run src/modes/PrivacyDashboard/PrivacyDashboard.test.tsx`
  → `4 passed`.
- Full `npx vitest run` → `239 passed (239), 2012 passed (2012)` — no
  baseline failures on this fresh origin/main checkout.

### Deviations

- None material. Notes: (1) venv bootstrap needed dev+pdf extras
  (`uv sync --extra dev --extra pdf --extra arxiv`) because
  `create_app()` transitively imports `acquisition.books.reader` which
  hard-requires pypdf — mirrors CI's `-e '.[dev,arxiv,pdf,...]'`
  install; the parent's `uv run pytest` command then works as written.
  (2) The store factory deliberately returns in-memory when neither
  ANTIEK_TELEMETRY_DB nor ANTIEK_HOME is set (never implicit `~/.antiek`
  writes) — stricter than a temp-dir default, and satisfies the
  test-isolation requirement (conftest sets ANTIEK_HOME per test).
  (3) The DP-shuffler ε-consumption half of P1 §2 (preference rows
  feeding per-category ε budgets) is NOT in this change: `record_telemetry`
  already consults the registry but no collection site calls
  `is_enabled` yet — that wiring is the next P1 item, per the change
  list.
