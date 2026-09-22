# Login destination policy — 2026-09-20

Malformed login destinations could throw `SecurityError` during history replacement or retain an unusable destination through passkey setup. Frontend and backend now accept only root-relative strings starting with one slash, without backslashes or ASCII control characters (U+0000–001F and U+007F). Invalid destinations fall back to `/`; valid paths, queries, fragments and Unicode remain intact. No extra percent-decoding or URL rewriting is performed.

## Failure Dossier

### Signatures

Source and `inspect.signature` agree: `_is_safe_relative(path: str) -> bool`; `_resolve_redirect(next_path: str) -> str`. New frontend boundary: `safeNext(value: unknown): string`. Inspection output: `.audit/env-contracts.log`.

### Numbered failure chain

1. `Login/index.tsx` accepted raw query `next` or history state `from`, and raw `claimLogin` response `next`.
2. Login called actual React Router `navigate(destination, {replace: true})`.
3. Router resolved `/\\outside.example/path` to a path interpreted by the browser URL parser as another origin. `replaceState` threw `SecurityError`; unlike Router's push branch, replacement has no `location.assign` fallback.
4. Backend `_is_safe_relative` accepted backslashes and controls; `/auth/request` stored them and `/auth/claim` returned them as JSON. The callback's actual Starlette response percent-encoded a backslash, so this audit did not demonstrate an HTTP open redirect or XSS.

The pre-fix real Login test failed with the history exception. Four of five frontend cases failed; one valid destination passed. Five of ten backend route cases failed. Full logs: `.audit/login-red.log` and `.audit/backend-red.log`. LLM/provider contacted on failure path: no.

## Scope Map

| Entry point | Evidence |
|---|---|
| Authenticated Login query and history-state destination | Real Login inside BrowserRouter, rejected backslash/external scheme, nonstring state; valid query/fragment and state preserved |
| Email handoff polling | Actual component, mocked auth service boundary; invalid claim destination falls back, with and without setup |
| Typed email-code claim | Actual component and form interactions, real BrowserRouter; malformed query sent as `/`, malformed response normalized in both setup branches |
| Passkey success / skip setup | Uses the same normalized `nextPath`; hardware ceremony and button-specific paths not driven |
| Backend request → stored attempt → code claim | Actual FastAPI routes and mock email provider; rejected destinations become `/` in JSON; valid query/fragment preserved |
| Backend callback | Actual route; invalid destination falls back with configured frontend origin and without one |

## Handoff

### Env Card

- Date: 2026-09-20 UTC.
- Repo: `/Users/slimydog/Antiek/.worktrees/login-next-policy-20260920`.
- Branch: `fix/login-next-policy-20260920`.
- Base and observed `origin/main`: `f24981db2bde8ce2fb88158fc54460cfd168c294`.
- Python: `/Users/slimydog/Antiek/platform/.venv/bin/python`, 3.12.13.
- Node: `/opt/homebrew/opt/node@22/bin/node`, 22.22.0.
- Final dependencies: clean `npm ci` from unchanged branch lock; React Router and react-router-dom 6.30.4, @remix-run/router 1.23.3, Vitest 4.1.10, jsdom 29.1.1.
- Initial red/green frontend run used a temporary symlink to `frontend-dependency-patches-20260920` dependencies (Router 6.30.6). It was removed before clean install and final verification.
- Initial gate network: npm registry install only. The later Chrome checks use loopback mocked auth HTTP as described below, without production auth calls or live email. Python `ANTIEK_HOME` and `ANTIEK_DUCKDB_PATH` were scratch paths before final imports; pytest additionally isolates each database.

### Not proved

Chrome component integration is verified below, using mocked auth HTTP responses and a synthetic destination screen. No live email/passkey ceremony, production session authorization, deployment, full workstation E2E, full product suite, or elimination of Router dependency advisories is proved. The regression establishes navigation failure, not confirmed external navigation or XSS.

### Status

Local scoped tests and typecheck pass. Independent GLM review accepted the source at 93/100; eight Chrome integration cases subsequently passed. Draft PR3269 remains subject to CI and integration; not merged or deployed.

### Files touched

`apps/reading/src/modes/Login/index.tsx`, adjacent `Login.redirect.test.tsx`, `apps/reading/src/lib/safeNext.ts` and its test, `interfaces/research/api/auth.py`, `tests/test_magic_link_auth.py`, this dossier, and the three browser artifacts under `docs/diagnostics/assets/login-next-policy-20260920/`. No App.tsx or manifests changed.

### Milestones (checkboxes)

- [x] Reproduce actual Login and backend response regressions before production edits.
- [x] Normalize query/state and both claim-response branches.
- [x] Align backend persisted destination policy.
- [x] Clean dependency install, focused frontend suite, full magic-link module, typecheck.
- [x] Independent source review (GLM ACCEPT 93/100).
- [x] Eight Chrome component/HTTP integration cases with sanitized artifacts.
- [ ] CI and integration.

### Gate results

Commands ran from repo root except npm tests/typecheck, which ran from `apps/reading`. npm used `PATH=/opt/homebrew/opt/node@22/bin:$PATH`. Full command output retained; counts are local results.

| Command | Exit | Result / full log |
|---|---|---|
| `npm test -- src/modes/Login/Login.redirect.test.tsx` before fix | 1 | 4 failed, 1 passed; `.audit/login-red.log` |
| Python pytest selected new backend cases before fix | 1 | 5 failed, 5 passed; `.audit/backend-red.log` |
| `npm --prefix apps/reading ci` | 0 | `.audit/npm-ci.log`; existing dependency advisories remain outside scope |
| `npm test -- src/modes/Login/Login.redirect.test.tsx src/lib/safeNext.test.ts src/lib/auth.test.ts` | 0 | 40 passed / 3 files; `.audit/login-final.log` |
| `npm run typecheck` | 0 | `.audit/typecheck.log` |
| `ANTIEK_HOME=$PWD/.audit/runtime ANTIEK_DUCKDB_PATH=$PWD/.audit/runtime/graph.duckdb PYTHONPATH=$PWD /Users/slimydog/Antiek/platform/.venv/bin/python -m pytest tests/test_magic_link_auth.py -q` | 0 | 54 passed, existing Starlette/httpx deprecation warning; `.audit/backend-green.log` |
| `git diff --check` | 0 | No whitespace errors |

### Decisions mid-flight

Treat the issue as navigation failure. Starlette encodes backslashes in Location headers, while claim JSON retains them. Validate both frontend destination entry points and backend persistence instead of assuming the response header and JSON boundaries behave alike.

### Assumptions surfaced

Login destinations are strings containing root-relative application paths. Router state objects are not accepted as destinations. Explicit malformed query values fall back to `/` rather than silently selecting history state. Backslashes and controls are rejected anywhere, including query/fragment; ordinary encoded characters are preserved.

### Steelman rejected alternative

A Router upgrade alone could address dependency advisories, but would leave the application's destination contract implicit and divergent between query, history state and backend claim responses. The route-level regressions pin the product behavior independently of that migration.

### Open questions

Independent source critic accepted the repair. Full workstation and hardware passkey acceptance remain separate from the recorded Chrome fixture checks.

### Next sprint can start when

Draft PR3269 passes its remaining integration gates; any wider routing change must coordinate the existing App.tsx owner.

### Out-of-scope temptations

Router upgrade, route taxonomy, App.tsx, manifests, callback origin configuration, deployment and unrelated auth refactoring.

### Strict typing follow-up

Strict mypy initially reported 101 errors in the test file and none in `auth.py`. The base commit has 97 errors under the same command/module context. The four introduced errors were missing annotations on the two new tests and their calls to the untyped shared `_client`. The follow-up annotates those two tests and `_client(monkeypatch: pytest.MonkeyPatch) -> TestClient`, without ignores or unrelated test cleanup.

The final result is **63 existing test-file errors; no introduced errors; production auth.py clean**. Typing `_client` also removes its existing missing annotation plus 33 baseline untyped-call diagnostics. This is a clean change relative to baseline, not a clean strict-mypy test file. Existing debt includes other untyped tests and `_requested_code`'s pre-existing incorrect return annotation.

Baseline command: `/Users/slimydog/Antiek/platform/.venv/bin/python -m mypy --strict --follow-imports=silent --explicit-package-bases --shadow-file interfaces/research/api/auth.py .audit/base-auth.py --shadow-file tests/test_magic_link_auth.py .audit/base-test_magic_link_auth.py interfaces/research/api/auth.py tests/test_magic_link_auth.py`. The shadow files contain exactly those files from `f24981db2`; module names, working directory, configuration and imported dependencies remain identical. Exit 1; full log `.audit/login-mypy-base.log`.

Final command: same mypy command without the two `--shadow-file` options. Exit 1; full log `.audit/login-mypy-followup.log`. `.audit/login-mypy-delta.json` records the diagnostic delta and confirms every remaining diagnostic matches a base diagnostic at an unchanged source line.

Reverification: the canonical pytest command above passed all 54 tests, exit 0 (`.audit/backend-typed-followup.log`); Ruff on `auth.py` and `test_magic_link_auth.py` passed, exit 0 (`.audit/login-ruff-followup.log`). Original commit `9a0837d2943a98bc5d5907e1dcdde75084c22eec` remains intact for independent-review provenance.


### Browser integration and review follow-up

The orchestrator drove eight Chrome cases through browser-harness: malformed slash/backslash, external HTTPS and JavaScript scheme queries; empty `next`; a valid path with query/fragment; a typed-code claim returning malformed `next`; its passkey-setup variant; and skipping setup. All observed destinations matched expectations, and every captured `error`/`unhandledrejection` list was empty. These are captured page-error events, not a claim that every browser diagnostic channel was inspected.

The harness mounts the real Login component, AuthProvider and BrowserRouter, uses real loopback HTTP requests to mocked auth responses, and renders a synthetic destination display outside Login. This proves component and navigation integration in Chrome; it does not prove email delivery, hardware passkeys, backend authorization, or the full workstation. The source component/helper hashes, harness hashes, raw-evidence hashes, sanitized request observations and screenshot hashes are in [browser-verification.json](assets/login-next-policy-20260920/browser-verification.json). No claim secrets, session cookies or submitted code values are included. Screenshots show [setup](assets/login-next-policy-20260920/setup.png) and the [valid destination](assets/login-next-policy-20260920/destination.png).

The source review in `.audit/login-next-independent-review.log` returned **GLM ACCEPT — 93/100**, covering source commit `9a0837d2943a98bc5d5907e1dcdde75084c22eec`. Its boundary-coverage suggestions are addressed by four additional component cases: explicit empty query and numeric, boolean and array-valued state destinations. The same frontend command above now passes **44 tests across three files**, exit 0; full output `.audit/login-review-followup-tests.log`. Production source did not change in this evidence update. The review predates these extra assertions and browser artifacts.

Red-evidence provenance: the original five-case red run used the name “replaces a malformed next query with home without a history SecurityError”; that case later became a parameterized invalid-query test. Nonstring history-state coverage likewise became parameterized, and typed-code/other cases were added after the red run. The historical red log proves the original failure modes; it is not a red run of all 44 final cases.

The parser basis is the [WHATWG URL Standard, relative slash state](https://url.spec.whatwg.org/#relative-slash-state): for a special scheme such as HTTP, a slash or backslash at that state transitions toward authority parsing; a backslash records a validation error without necessarily terminating parsing. This explains why a slash/backslash destination can designate another host at the URL layer. Login's observed pre-fix behavior is still a failed same-origin history replacement, not demonstrated external navigation.

Before this follow-up, `python3 .infinite/validate-control-plane.py` at the harness root returned `CONTROL_PLANE_OK agents=649 active_portfolio=9 owned_surfaces=1729 lease_tip=818a73788`. The expanded claim explicitly owns these three browser assets. `git fetch origin` ran before the evidence commit. Browser/server processes were left under the orchestrator's ownership.
