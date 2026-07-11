# BUILDER-REPORT — settings-add-model-byok (LANE-A, session b8c6422a)

Branch `settings/add-model-byok` off `d76604d18` (origin/main tip). All work
inside this worktree. Not pushed, no PR, app.py and runtime/byok/* untouched.

## What was built

**Backend — `interfaces/research/api/settings_models_admin.py` (new)**

- `POST /settings/models/user` — register a user-added provider/model
  (`provider_kind` ∈ {openai_compat, anthropic}, `model_id`, `display_name`,
  `api_key`, `base_url` required for openai_compat). Key encrypted at rest via
  `runtime.byok.store.store_credential` (SecretBox), `pipeline_kind="model_provider"`.
- `GET /settings/models/user` — inventory with `key_present` / `registered` /
  `enabled` flags; never key material (the response models have no key field).
- `DELETE /settings/models/user/{id}` — removes the registry record and the
  name from the `app.state.registered_providers` seam.
- **Real registration:** on POST and at boot, a provider instance
  (`_UserOpenAICompatProvider` / `_UserAnthropicProvider`, subclasses of the
  house adapters) is registered through `substrate.dispatch.router.register_provider`
  — the SAME seam `register_default_providers` uses — and its name is unioned
  into `app.state.registered_providers`, so `GET /settings/models` and `/health`
  show it as ready and `get_provider(name)` dispatches to it. No files owned by
  other lanes were needed for this; no STOP condition was hit.
- Durable non-secret registry: `(ANTIEK_HOME|~/.antiek)/settings/user_models.json`
  (override `ANTIEK_USER_MODELS_PATH`), following the DaemonBudget JSON-sidecar
  precedent. No DuckDB → single-writer/db_lock rule untouched.
- Mount: `register_settings_budget_routes` (settings_budget.py) gained a
  local-import + register call — the settings-local pattern; region-disjoint
  from `estimate_prompt_cost` and the spent/remaining arithmetic.

**Frontend**

- `apps/reading/src/api/settingsModels.ts` — client following settings.ts patterns.
- `apps/reading/src/modes/Settings/AddModelPanel.tsx` — Lemon-style panel:
  inventory (key-present + ready badges, remove w/ confirm), add form
  (LemonSelect kind, LemonInput fields, `type="password"` key input). Key is
  write-only: cleared from the field at submit, never rendered afterward.
- `apps/reading/src/modes/Settings/index.tsx` — 4-insertion/2-deletion diff:
  import + mount `<AddModelPanel />` before the "Coming later" card, drop the
  now-shipped add-model bullet, repoint the models-card footnote.

**Tests**

- `tests/test_settings_models_admin.py` — 18 tests, offline/deterministic
  (byok artifact/key-file/registry redirected to tmp via env; real dispatch
  registry, reset around each test; zero network — no provider `call()` ever).
  Covers: add→key_present + registration proof through the registered-providers
  seam; the **key-absent invariant** (plaintext absent from every response
  body, from registry + byok artifact bytes, from caplog/capsys — mirrors
  test_byok_store's byte-level assertion); delete-effective-immediately;
  11 malformed-input cases all value-free; duplicate 409; anthropic kind;
  boot-time reload; disabled-record skip.
- `apps/reading/src/modes/Settings/AddModelPanel.test.tsx` — 3 vitest cases:
  inventory + badges + no key material rendered; submit-through-client with
  key field cleared and masked (`type="password"`); disabled-until-complete.

## Key design decisions

1. **BYOK reuse: option (a) — `runtime.byok.store` reused directly.**
   `store_credential(record_id, key, pipeline_kind="model_provider")` /
   `load_credential` / `list_credentials`. `CredentialMetadata` generalizes
   cleanly (handle = record id, pipeline_kind discriminates from X creds in the
   shared artifact). The only X-flavored residue is the opaque `cred-x-` id
   prefix — cosmetic, not semantic. Option (b) would have duplicated
   artifact/key-file plumbing for zero security gain. No third pattern exists;
   `runtime/byok/*` is unmodified.
2. **Decrypt-at-call-time, not decrypt-at-registration.** The provider
   subclasses override the adapters' `_resolve_api_key` seam to load+reveal
   from the byok store per call, re-checking the durable registry first.
   Consequences: plaintext never sits in provider instance state, and DELETE
   is effective immediately — the dispatch registry has no public unregister,
   but a removed/disabled record refuses key resolution, making any lingering
   in-process entry inert (pinned by a test). Trade-off accepted: dependence on
   a private method name in the two adapters, pinned by tests that exercise the
   override.
3. **POST parses its body by hand.** FastAPI's automatic 422 echoes request
   input — for a missing-field error the echo is the WHOLE body, api_key
   included. Manual parsing keeps every 4xx value-free; a parametrized test
   posts the real key with a missing sibling field and asserts the key is not
   in the response.
4. **DELETE (no enabled-toggle endpoint) shipped.** Delete + re-add covers the
   single-operator need; the registry's `enabled` field is honored read-side
   (boot reload skips disabled records — tested), giving a manual escape hatch
   without a speculative write surface. Orphaned SecretBox ciphertext after
   DELETE is documented in code (store exposes no delete; the blob is
   unreadable without the 0600 master key and unreachable without the record).
5. **Startup-handler reload via `app.router.on_startup`.** `create_app` assigns
   `app.state.registered_providers` AFTER the settings routes mount, so
   mount-time union would be clobbered; startup events run later. Starlette
   1.x removed `add_event_handler`, but the router's `on_startup` list still
   drains through the default lifespan (create_app passes no custom lifespan) —
   verified by the boot-reload test through the real mount seam.
6. **User base_url convention**: full base including version prefix +
   `/chat/completions` appended — the dominant house pattern (openrouter /
   hermes / xiaomi / zai), avoiding the documented double-`/v1` 404 class.

## Acceptance results (verbatim, trimmed)

Environment: fresh CPython **3.14.5** venv in the worktree (CI parity;
`pip install -c tools/lints/constraints.txt -e '.[dev,arxiv,pdf,urls,embedding,youtube,rss]'`),
mypy 2.1.0, ruff 0.15.15 (constraint-pinned).

```
$ .venv/bin/python -m pytest tests/test_settings_models_admin.py -q
18 passed, 1 warning in 0.41s
  (warning = StarletteDeprecationWarning from fastapi/testclient.py itself, not this code)

$ .venv/bin/ruff check interfaces/research/api/settings_models_admin.py tests/test_settings_models_admin.py
All checks passed!
exit=0

$ .venv/bin/mypy --strict interfaces/research/api/settings_models_admin.py
Success: no issues found in 1 source file
exit=0

$ npx vitest run src/modes/Settings/AddModelPanel.test.tsx   # from apps/reading
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

## Additional gates run (beyond the acceptance list)

- `npx vitest run src/modes/Settings/` → 2 files, 5 tests passed (existing
  Settings.test.tsx still green with the panel mounted).
- `npm run typecheck` (tsc -b --noEmit) → clean, exit 0.
- `tools/codegen/emit_types.py --stdout` vs committed types.ts → **not stale**
  (settings API responses are hand-typed in TS by house convention, like
  settings.ts).
- `tools/lint/boundary_check.py`, `owner_boundary_check.py`,
  `serve_guard_check.py` → all OK.
- Declared-bar gates: `declared_bar enforce ruff` → exit 0.
  `declared_bar enforce mypy` → exit 1 with exactly one finding,
  `substrate/exhaustive.py:116:0: NEW mypy:syntax` — **pre-existing**: the
  gate output on base commit d76604d18 is byte-identical (diff verified).
  Not caused by this lane; likely a local-toolchain artifact vs CI.
- Neighbor suites `test_settings_budget_api.py`, `test_byok_store.py`,
  `test_dispatch_bootstrap.py` → 23/24 pass; the 1 failure
  (`test_health_endpoint_reports_registered_providers`) **pre-exists on the
  base commit** and is shell-env leakage on this Mac (OPENROUTER/XIAOMI keys
  set in the operator env; test passes with them unset, and CI empties them).
- Full backend suite (`pytest tests/ -q -m "not integration"`, CI-parity env
  with all provider keys emptied):
  **6 failed, 6427 passed, 17 skipped, 3 deselected, 2 xfailed in 21m22s.**
  All 6 failures reproduce IDENTICALLY on the base commit d76604d18 (re-run
  verified): `test_coordination_no_fork.py` (3 roadmap-reconciliation tests),
  `test_retrieval_bench.py::test_run_benchmark_emits_artifact`, and 2
  `test_retrieval_substrate_interface.py[turbopuffer]` tests — the latter two
  are shell-env leakage (`TURBOPUFFER_API_KEY` is set in the operator env;
  the tests expect a credential-absent skip). None touch settings, byok, or
  dispatch registration; not caused by this lane.
- Full frontend vitest suite (`npx vitest run`): **173 files / 1368 tests, all
  passed** (21.1s). `npm run lint:tokens`, `lint:type`, `check:tokens`,
  `npx tsc --noEmit` → all clean.

## Known gaps / honest notes

- **Lingering in-process dispatch-registry entry after DELETE** (until next
  boot): the router exposes no unregister and reaching into
  `_PROVIDER_REGISTRY` privates was rejected. Mitigated to inertness by the
  registry-checked key resolution (tested); nothing references the name after
  the seam-set discard.
- **Orphaned ciphertext after DELETE** in the byok artifact — see decision 4.
- **No dispatch-tier binding**: user models don't appear in
  substrate/dispatch/config.yaml tiers (dispatch-time model-picking is
  explicitly out of scope / contested territory per the brief's non-goals).
  The provider is dispatchable by name via `get_provider`; tier wiring is a
  later sprint's call.
- **`_resolve_api_key` is a private seam** of the two adapters — an upstream
  rename would break user providers loudly (ProviderError absent; tests pin
  the behavior). Accepted over holding plaintext in instance state.
- The `409` detail interpolates the derived record id (slug of display_name)
  — non-secret by construction.

## NOT RUN

- Live provider calls (forbidden by the brief; no network anywhere in tests).
- E2E/Playwright, Storybook, lost-pixel visual tests (no story added; panel
  follows existing primitives; visualtest workflow exists but was not run).
- The interview/export optional-extra suites and `-m integration` tests
  (excluded on CI too).
- `python -m pytest` on CPython 3.12 (platform venv) — the 3.14 CI-parity venv
  was used instead, per the brief's 3.14 warning.
- Deploy/prod verification (out of scope: no push, no PR).

## Fix round 1 (codex adversarial refute — 5 CONFIRMED findings)

What changed per finding:

1. **base_url credential smuggling (FIXED).** `_parse_create` now validates
   via `urllib.parse.urlsplit`: scheme ∈ {http, https}, non-empty host, and
   NO userinfo / query / fragment — a key-bearing URL
   (`https://user:secret@host`, `?key=sk-...`, `#...`) is rejected with a
   value-free 422 (the URL is never interpolated into the error). Module
   docstring's secret-handling section updated: keys travel ONLY in
   `api_key`; base_url is structurally prevented from carrying credentials.
2. **Unbounded lengths (FIXED).** `_MAX_KEY_LEN = 512` (longest real
   provider keys are in the low hundreds of chars — OpenAI ~164,
   Anthropic ~108; justified in a comment) and `_MAX_BASE_URL_LEN = 2048`;
   over-length inputs get value-free 422s and never reach the byok store
   (test asserts the credential artifact is not even created).
3. **Stale seam names after registry corruption/loss (FIXED, honestly).**
   (a) `reload_user_providers` now RECONCILES at boot: `user-`-prefixed seam
   names without an enabled registry record are discarded (default provider
   names prefix-guarded, never touched). (b) `GET /settings/models/user`
   surfaces `stale_registered: list[str]` (user-* seam names lacking a
   registry record) — surfacing, not hiding; the panel renders an amber
   note when non-empty. The lenient registry read is UNCHANGED (corrupt
   file still must not crash boot).
4. **Delete→re-add credential accumulation (ACCEPTED + DOCUMENTED).** The
   byok store is append-only (no replace/delete API; `runtime/byok/*`
   off-limits). Each delete→re-add cycle orphans one more ciphertext blob —
   bounded by operator behavior, never a plaintext hazard. Documented in
   the module docstring and in a second DELETE response note. No second
   write path into the artifact.
5. **Vacuous boot-ordering test (FIXED — the test, not the code).** New
   `test_boot_reload_lands_after_create_app_state_assignment` imports the
   REAL `create_app(register_wrestling=False, register_providers=False)`
   (offline), asserts `app.state.registered_providers == set()` before the
   lifespan (assignment done, reload not yet run), then inside the
   TestClient context asserts the set is exactly `{"user-my-deepseek"}` —
   the reload landed AFTER the assignment and the seam was not clobbered.

New regression tests for findings 1–3 (`test_credential_bearing_base_url_rejected_value_free`,
`test_over_length_inputs_rejected_value_free`,
`test_live_registry_corruption_surfaces_stale_registered`,
`test_boot_reconcile_discards_stale_user_names`). Test count: **18 → 23**
(all 18 originals stay green, unmodified).

Frontend delta: `UserModelsResponse.stale_registered` added to
`settingsModels.ts`; AddModelPanel renders the stale-registrations note;
test mock updated.

### Fix-round acceptance (verbatim, trimmed)

```
$ .venv/bin/python -m pytest tests/test_settings_models_admin.py -q
23 passed, 1 warning in 1.09s

$ .venv/bin/ruff check interfaces/research/api/settings_models_admin.py tests/test_settings_models_admin.py
All checks passed!
exit=0

$ .venv/bin/mypy --strict interfaces/research/api/settings_models_admin.py
Success: no issues found in 1 source file
exit=0

$ npx vitest run src/modes/Settings/AddModelPanel.test.tsx   # from apps/reading
 Test Files  1 passed (1)
      Tests  3 passed (3)
```

Also re-run: both Settings vitest suites (2 files / 5 tests passed),
`npx tsc --noEmit` clean, neighbor suites
(test_settings_budget_api + test_byok_store + test_dispatch_bootstrap,
provider-key env unset) 24/24 passed.

### Fix round 2 (codex QA round — 1 residual on finding 1's base_url)

Round 2 confirmed findings 2–5 converged; one residual on the base_url
validator. Scope was the `base_url` block of `_parse_create` ONLY.

What changed:

- **Malformed authority → clean 422, not 500 (FIXED).** `urlsplit` raises
  `ValueError` on an unclosed IPv6 bracket (`https://[::1/v1`), and
  `.port` raises `ValueError` on a non-numeric port — both previously
  surfaced as an uncaught HTTP 500. The parse + `.hostname` + `.port`
  access is now wrapped in one `try/except ValueError → _reject(...)`
  (value-free message).
- **Empty hostname rejected (FIXED).** `https://:443/v1` has a truthy
  `netloc` but an empty `hostname`; the check now requires `parts.hostname`
  truthy, not just `netloc`.
- **Port validated (FIXED, same mechanism).** `parts.port` is accessed
  inside the same try/except, so a present-but-invalid port is a value-free
  422, not a 500.

Deliberately UNCHANGED (codex flagged, but not defects): mixed-case scheme
(`urlsplit` lowercases it — valid) and well-formed bracketed IPv6
(`https://[::1]:8000/v1` — legitimate local endpoint; brief only required
rejecting userinfo/query/fragment). A new test asserts the well-formed IPv6
still returns 201 so the try/except cannot silently over-reject it.

New regression tests: `test_malformed_base_url_is_clean_422_not_500`
(parametrized: unclosed-bracket / non-numeric-port / empty-hostname — 3
cases, each value-free) and `test_well_formed_ipv6_base_url_accepted`
(201 + provider registered with the IPv6 base_url). Test count: **23 → 27**.

Round-2 acceptance (verbatim, trimmed):

```
$ .venv/bin/python -m pytest tests/test_settings_models_admin.py -q
27 passed, 1 warning in 1.06s

$ .venv/bin/ruff check interfaces/research/api/settings_models_admin.py tests/test_settings_models_admin.py
All checks passed!  (exit 0)

$ .venv/bin/mypy --strict interfaces/research/api/settings_models_admin.py
Success: no issues found in 1 source file  (exit 0)

$ npx vitest run src/modes/Settings/   # unaffected
 Test Files  2 passed (2)  /  Tests  5 passed (5)
```

## Commits

- `ab365c920` feat(settings): user-added model providers with byok-encrypted keys
- `bb5ac16d7` feat(reading): AddModelPanel — BYOK add-model UI in Settings
- `c8579a456` docs(settings): builder report
- `fa17dee38` fix(settings): close adversarial-refute findings 1-3, 5; document 4
- HEAD (this commit) — fix round 2: base_url malformed-authority hardening
  (SHA cannot self-embed; see `git log -1`)
