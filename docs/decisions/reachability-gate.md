# Reachability gate — blocking, pre-merge, outcome-asserting

**Decision date:** 2026-06-03
**Status:** ✅ Active (blocking on `pull_request:[main]` + `push:[main]` via the
`reachability` job in `.github/workflows/ci.yml`; the flywheel probe is
intentionally known-red until SPR-02 — see the escape valve below)
**Owner:** Antiek — Convergence SPR-01 (keystone)
**Scope:** a new `tools/reachability/` probe runner + a blocking CI job + the
fifth done-bar convention. Does **not** touch the flywheel wire (that is SPR-02);
this sprint installs the gate that catches it and confirms it is red.

## The decision

Install a **blocking, pre-merge, outcome-asserting** reachability gate: a
runner that boots the app through the production `create_app()` factory, drives
each declared feature through its real route(s), and asserts an **observable
outcome**. Any BLOCKED probe (outside an unexpired known-red window) fails the
build. The fifth done-bar criterion (`tools/reachability/README.md`) makes every
later sprint declare and prove reachability-from-prod for each feature it ships.

## Why — the four properties are load-bearing, and four weaker forms already failed here

The flagship compounding flywheel shipped **dead in prod** while every gate
passed: `interfaces/research/api/cascade_routes.py:367` builds
`HostLocalRunner(...)` without `retrieval_substrate` (left `None`); the reuse
hook `runtime/research_runner/host_local.py:259` early-returns on `None`; so no
`knowledge.reused` event fires and `/health` reports
`knowledge_reuse_count=0`. It passed because every gate verified a **brick**,
not **reachability from the real product**. The gate's four properties each
correspond to a weaker form that was *actually tried in this codebase and
failed to catch this exact bug*:

1. **Outcome-asserting (not static-presence).** A unit/contract test asserts a
   brick behaves; the compounding benchmark even *injects* the substrate prod
   never injects (`compounding/benchmark/harness.py:344`), so it can never see a
   missing wire — it supplies the wire. **Static presence** (does the code/route
   exist?) is also insufficient: the static `tools/lint/reachability_gate.py`
   gate confirms a route is *linked*, not that the feature *works*. The flywheel
   route exists and is linked; it is still dead. → the gate must assert the
   **feature outcome** (`knowledge_reuse_count > 0`), booted via the bare
   factory.

2. **Booted-via-real-factory (not fixture-injected).** The injected-substrate
   harness is the proof that an injecting test green-lights a dead wire. A probe
   that injected `retrieval_substrate` / stubbed providers / built the runner
   directly would recreate the blind spot. → boot via `create_app()` the prod
   way; drive the **route**, which builds the runner as prod does.

3. **Blocking (not advisory / not operator-optional).** The prod-parity check
   (`tools/prod_parity/check.py`) **already existed** as a separate flywheel
   probe and was **demoted to informational** on 2026-06-03 (commit `873d95b0`,
   PR #68) — an advisory `::warning` that does not fail. An advisory signal that
   surfaced the dead flywheel was present and the dead flywheel still shipped:
   informational ≠ enforced. Likewise an **operator-optional** check (run it if
   you remember) is skipped exactly when it matters. → the gate must propagate a
   non-zero exit as a required, failing check (no `continue-on-error`, no
   `::warning::`-only).

4. **Pre-merge (not post-deploy-only).** The one blocking prod-parity surface is
   *post-deploy* (`infrastructure/ansible/playbooks/deploy.yml`), which fires
   only after the bad code is already on prod, and which (correctly, for the
   empty-corpus reason — see the prod-parity decision) does not block on the
   flywheel by default. A post-deploy gate cannot stop the merge; it can only
   notice after the fact. → the gate runs on every PR, in-process, before merge.

In one line: **the prod-parity flywheel probe already existed as a separate
check and was demoted/ignored; the load-bearing properties are blocking +
pre-merge + booted-via-real-factory + outcome-asserting, which an unmarked,
fixture-injected pytest does not guarantee.**

## Steelman of the rejected alternative — "just add a `pytest -m integration` test"

Strongest form: a separate runner is more machinery; an integration-marked
pytest reuses the suite, the runner, the CI install, and the developer's muscle
memory. Fewer moving parts wins **if the four properties hold**.

Why it does not hold *as the marker is configured here*:

- CI runs `pytest -m "not integration"` (`ci.yml`) and **no test is marked
  `integration`** — an integration-marked test would be *excluded* from the
  gate by default. The marker would have to be made required (a CI change of the
  same size as a new job) before it blocks anything.
- A pytest fixture is the *native idiom for dependency injection* — the path of
  least resistance is exactly the `retrieval_substrate=`-injecting fixture that
  caused the bug. The standalone runner makes "boot via the bare factory, do not
  inject" the **only** shape, and the no-injection grep
  (`grep -n "retrieval_substrate\|register_providers=False\|stub"
  tools/reachability/`) is a mechanical guard a pytest fixture can not offer.
- The fifth done-bar wants a *first-class, enumerable* artifact ("≥ 1
  reachability proof per feature"), discoverable + listable
  (`--list`) + selectable (`--only`) independent of the 5,400-test suite, and
  runnable in pytest-free deploy/hook environments.

**Verdict:** keep the standalone runner. If a future `pytest -m reachability`
marker is made *required* AND carries all four properties (in particular a lint
that forbids fixture injection inside reachability tests), it could subsume the
runner — fewer moving parts would then win. Until then the runner is the
defensible choice. (Note: the runner's own self-test *is* a pytest —
`tests/test_reachability_runner.py` — so the suite still proves the runner's
exit semantics; the runner is the *gate*, pytest is the *proof the gate works*.)

## The known-red escape valve (so SPR-01 merges without faking green)

SPR-01 ships the flywheel probe **RED on purpose** — the wire is not landed
(that is SPR-02), so the probe must be red today as proof the gate catches the
dead flywheel. To merge SPR-01 without faking green and without the red being
ignored forever, `tools/reachability/known_red.json` lists the `flywheel` probe
with a tracking link (SPR-02) and a **hard expiry** (`2026-07-03`). While
unexpired the runner reports the RED but exits 0; when SPR-02 lands it **deletes
the entry** (the probe greens on its own); if SPR-02 slips past the expiry the
valve **self-closes** and the gate reds. The valve can never become silently
permanent: every entry must carry both a link and an expiry, and a missing /
malformed expiry is treated as expired (fail-closed).

This window is **consistent with the prod-parity decision**
(`docs/decisions/prod-parity-flywheel-informational.md`): both agree the
flywheel is allowed to be red **only during SPR-01 → SPR-02**. The one
difference is scope, and it is honest: this in-process probe asserts the **wire**
(it goes green the instant `retrieval_substrate` is connected — the reuse
assembler emits `knowledge.reused` even with zero prior units,
`substrate/context_pack/knowledge_reuse.py:652`, so no corpus is needed),
whereas prod-parity `--require-flywheel` asserts **live prod compounding**, which
additionally needs a fed corpus. So: wire-fix (SPR-02) turns THIS probe green;
wire-fix **plus** a prod corpus ingest turns the prod-parity check green. See
the prod-parity decision's RECONSIDER-IF and `infrastructure/runbooks/
flywheel-prod-cutover.md`.

## RECONSIDER-IF

- A `pytest -m reachability` marker is made **required** in CI **and** a lint
  forbids fixture injection inside reachability tests **and** the runner's
  `--list`/`--only`/known-red-with-expiry affordances are reproduced — then fold
  the runner into the marker (fewer moving parts).
- The known-red valve accumulates more than ~1–2 entries, or any entry is
  renewed more than once — that signals the gate is being routed around rather
  than satisfied; tighten the policy (e.g. require operator sign-off to renew).

## Verification (all run at SPR-01 ship)

- App boots via the real factory: `python -c "from
  interfaces.research.api.app import create_app; create_app()"` + TestClient
  `GET /health` → 200, `registered_providers: []` (credential-empty). ✅
- Runner self-test: `python -m pytest tests/test_reachability_runner.py -q`
  → 8 passed (BLOCKED on a false outcome, REACHABLE on a true one, valve opens
  on unexpired / self-closes on expired). ✅
- Flywheel probe RED on main: the probe with an empty known-red exits 1,
  `[BLOCKED] flywheel: knowledge_reuse_count == 0 (feature_dead)`. ✅
- No injection: `grep -n "retrieval_substrate\|register_providers=False\|stub"
  tools/reachability/` shows only docstrings naming the anti-pattern — no actual
  `create_app(...)` / `HostLocalRunner(...)` injecting call. ✅
- CI blocking: the `reachability` job runs `python -m
  tools.reachability.probe_runner` with no `continue-on-error` / `|| echo` /
  `::warning::`-only — its pass/fail is exactly the runner's exit code. ✅
