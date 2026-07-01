# Phase 2 Execution Audit Addendum (v5) - 2026-07-01

**Scope:** current-state reconciliation after the DuckLake query-time routing
slice landed on `reader/integration`.

**Reference baseline:** `docs/phase2_execution_audit_v4_2026_05_23.md`.

**Current commit evidence:** `23048220 feat(ducklake): route default graph path through catalog`.

---

## 1. What changed since v4

v4 identified one remaining engineering-side blocker:

> v3 section 7 item #16: Application-layer routing through DuckLake catalog at query time.

That item is now implemented at the production call-path level:

- `substrate/multi_user/graph_router.py` exposes
  `build_graph_router_from_env()` and `default_personal_graph_handle()`.
- `ANTIEK_DUCKLAKE_CATALOG_DB` constructs a persistent
  `DuckLakeCatalog` backed by `SqliteCatalogBackend`.
- `substrate/graph/default_db_path()` preserves the explicit
  `ANTIEK_DUCKDB_PATH` override, then routes through the catalog-backed
  `GraphRouter` when `ANTIEK_DUCKLAKE_CATALOG_DB` is configured, then
  falls back to `substrate.constants.DUCKDB_PATH`.
- The catalog backend is cached per expanded catalog path, so API routes
  that call `default_db_path()` repeatedly do not open a fresh SQLite
  catalog connection per request.

Focused proof:

```bash
pytest tests/test_multi_user.py tests/test_privacy_control_plane_docs.py \
  tests/test_write_routes.py tests/test_api_sprint18_19_endpoints.py -q
```

Result on July 1, 2026: `62 passed`.

Second-pass adversarial review via `grok` reported: `NO BLOCKERS`.

---

## 2. Reconciled status

The v4 line:

> Net engineering-side-blocked: 1 item (#16, the GraphRouter
> catalog-consultation edit, blocked by OA-010 path).

is no longer current.

**Current reconciled state:** net engineering-side-blocked items known from
v4: **0**.

This does **not** mean every Phase 2 activation gate is closed. It means the
one remaining engineering-side code path v4 named has been executed and
verified. The remaining blockers are operator action, real-data
accumulation, production deploy verification, or spec-defined deferrals.

---

## 3. OA-010 is narrowed, not closed

OA-010 remains `PARTIALLY MITIGATED`.

What is now mitigated:

- The DuckLake query-time catalog route exists in the API's existing
  `default_db_path()` call path.
- The historical "substrate ready, app path missing" gap is gone.
- The privacy/trust/marketplace/payout/operator route registrations still
  have executable doc tests guarding their presence.

What is still open:

- A fresh-session drift audit must prove the historically reverted tracked
  files stay stable after independent commit sequences:
  `interfaces/research/api/app.py`, `apps/reading/src/App.tsx`, and
  `tools/stripe_connect/__init__.py`.
- If those files drift again, OA-010 remains an integration-process problem,
  not a missing DuckLake-routing implementation.

Closure proof for OA-010 remains the proof written in
`docs/OPERATOR_ACTIONS.md`: edit + commit + fresh-session return with the
tracked edits still present.

---

## 4. Recommended next action ordering

1. Keep `docs/OPERATOR_ACTIONS.md` as the authoritative operator gate list.
2. Do not pre-build anything listed in `docs/engineering_deferrals.md`.
3. Run the OA-010 drift audit after at least one independent commit sequence.
4. If drift holds, close OA-010.
5. Otherwise, the remaining high-leverage work is operator-side:
   counsel review, publisher opt-in, production deploy verification, real
   investigations to feed G6/G7/G8, and the public Trust Center deploy.

---

## 5. Honest verdict

As of July 1, 2026, the Phase 2 substrate engineering scope remains executed
within the boundaries of the spec, and the v4 exception for DuckLake
query-time routing is resolved. The project is now bottlenecked by operator
gates, real production traffic, and explicitly deferred work, not by a known
unimplemented substrate call path.
