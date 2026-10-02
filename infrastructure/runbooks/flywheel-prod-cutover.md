# Flywheel Prod Cutover — Turn Compounding On in Production

**Audience**: you (the operator), once the research-DEPTH flywheel is proven
at prod shape and you are deciding whether to flip it on in production.

**Time**: ~15 minutes of pre-flight verification. Budget nothing for the
prod-shaped benchmark run: it is **blocked on `main`** (precondition 1), not
waiting on your calendar. The cutover deploy itself is the routine
`code-update.md` flow.

> **Re-verified against `main` @ `3d7f7f16` on 2026-09-22.** Every command
> below was re-run or its symbols re-read at that SHA; observed exit codes are
> quoted inline. Five claims did not survive it and have been corrected; the
> two that would have hurt you are precondition 1 (the prod-shaped benchmark
> does not execute at all, it is refused) and the cutover's old promise that a
> deploy cannot ship a dead flywheel (it can). Re-read both even if you have
> run this checklist before.

> **SPR-11 did NOT cut over.** This runbook is the *checklist*. SPR-11 (the
> EXIT of the Antiek Flywheel Foundation) built the prod-shape benchmark
> selector, added a flywheel-liveness check to the prod-parity tool
> (informational by default, blocking only under `--require-flywheel`), and
> added the `/health` `flywheel_ready` field — but it executed **no deploy**,
> closed **no operator gate**, set **no prod keys**, and ran **no live
> prod-shaped benchmark**. The live prod-shaped run and the cutover are
> operator gates. This document makes the cutover *evidenced*, not *asserted*.

---

## What "the flywheel" means here

The research-DEPTH flywheel is the claim that each investigation deposits
reusable, provenance-carrying knowledge units, and future investigations
retrieve + reuse them (the `knowledge.reused` event in
`substrate/schemas/events.py`), so the cost-to-resolve a question falls as the
graph grows. SPR-09 proved the *instrument* is falsifiable in a dev-shaped
mock harness. The one question left — the one that strands ambitious systems —
is **"does it compound on prod, or only in dev?"**

The box itself is the cautionary tale: it has already sat several PRs behind
`main`, and a stale-SPA drift shipped to `api.antiek.ai` undetected for an
extended period. Dev-green is not prod-green here.

---

## Preconditions (must be green)

Do **not** cut over until ALL of these are green. Each names the real artefact
that proves it.

1. **The prod-shaped benchmark reproduced the compounding curve** — **BLOCKED
   on `main`, not merely deferred.** No invocation of this run executes today.
   `compounding/benchmark/run.py:290-291` is
   `if profile.uses_real_dispatch: return _refuse_prod_run(profile)` — no env
   gate, no flag, no host check — and `profiles/prod.toml` sets
   `mock_run = false` + `dispatch_mode = "real"`, so `uses_real_dispatch` is
   always true. Running it on the box at `/opt/antiek` with prod credentials
   produces the identical refusal. Re-run 2026-09-22 with the profile's own
   baked values, so the angle-bracket placeholders were not the cause:

   ```bash
   cd /opt/antiek
   python -m compounding.benchmark.run --profile prod \
       --n 20 --material-floor 0.0 --control-tolerance 0.0 \
       > /tmp/prod-bench.out 2>&1; echo $?
   #  → 2. /tmp/prod-bench.out opens:
   #    REFUSED: --profile 'prod' is a PROD-SHAPED real-dispatch run
   #    (mock_run=False, dispatch_mode='real').
   ```

   Read that refusal; do **not** obey it. It prints back the *same* command you
   just ran as the "operator-window run", so following the instruction loops.
   (Exit 2 is the gate. If you get exit 1 and `ImportError: cannot import name
   'UTC'` instead, that is your interpreter — a bare `python` on the Mac is
   anaconda 3.9 — and the refusal never even printed.)

   Three runtime prerequisites are genuinely missing — prod model-tier
   credentials, the box, and a reuse-CONSUMING browse loop (the host-local demo
   loop is reuse-blind) — but supplying all three still will not start the run,
   because the refusal is unconditional. Unblocking it is a code change: gate
   `run.py:290` behind an explicit opt-in (e.g. `--i-am-the-operator-window`)
   so the refusal stays the default and the operator window is the narrow
   exception. Until that lands, record precondition 1 as **open** in the
   handoff. Do not write "deferred to the operator window" — that reads as
   ready-when-you-are, and it is not.

   Two further things to fix before the first real run, or its output will lie:

   - **The output path is not wired.** `--out` defaults to
     `compounding/benchmark/results/spr09_run.json` (`run.py:42`, `run.py:261`),
     and the profile's `out_filename_template = "prod-{sha}.json"` reaches
     exactly one non-test call site — `run.py:233`, *inside the refusal
     message*. A lifted run would overwrite the dev artifact rather than
     produce its twin. Pass `--out` explicitly, or wire the template into the
     `--out` default first.
   - **The parameters are placeholders.** `prod.toml` carries
     `parameters_ratified = false`; `n=20 / floor=0.0 / tolerance=0.0` exist so
     the printed command is exact, not because anyone ratified them
     (decision §0.2).

   The one step here that does run today is the pilot that derives the numbers
   you would ratify. It needs a 3.11+ interpreter — a bare `python` on the Mac
   is anaconda 3.9 and dies importing `datetime.UTC`:

   ```bash
   ./.venv/bin/python -m compounding.benchmark.run --pilot > /tmp/pilot.out 2>&1; echo $?
   #  → 0. On the mock path it proposes n=5, material_floor=0,
   #    control_tolerance=0 and says why: "headline CV is 0
   #    (deterministic/zero-variance pilot — the mock path); n clamped to
   #    MIN_PROPOSED_N=5." Those are NOT the live numbers — re-run the pilot in
   #    the operator window, against real provider variance, before ratifying.
   ```

   When the run does become possible, the `--profile prod` selector
   (`compounding/benchmark/profiles/prod.toml`) flips `mock_run=False` and
   points dispatch at the prod tiers. It loads **no** mock fixtures — assert
   this in the run log.

   Interpret the resulting prod artifact **honestly** (rigor #1): EITHER
   "cost-to-resolve falls as the graph grows; slope reproduces dev within
   tolerance" OR "does **NOT** reproduce — here is the curve + the gap." A
   non-reproduction is a valid finding and a **STOP** for cutover — see
   *Reconsider-if* below. Never swap real dispatch back to mocks or soften the
   tolerance to manufacture a green.

2. **The parity assert is green against LIVE prod — and you must ask it a
   stricter question than the deploy does.**

   ```bash
   python tools/prod_parity/check.py \
       --url https://api.antiek.ai \
       --expected-sha "$(git rev-parse origin/main)" \
       --require-flywheel \
       > /tmp/parity.out 2>&1; echo $?
   #  0 = SHA matches main + providers live + flywheel live
   #  (drop --require-flywheel and 0 means only the first two)
   ```

   `--require-flywheel` is not decoration, and it is **not** what the deploy
   runs. `assert_parity` (`tools/prod_parity/check.py:119`) gates **two**
   things — deployed `build_sha` == main's tip, and `registered_providers`
   non-empty — and its own docstring says the SPR-11 flywheel-liveness check is
   "INTENTIONALLY NOT here". Liveness lives in `flywheel_warnings` (line 227)
   and is a `::warning` that leaves the exit code alone unless the flag is set.
   Mutation control, feeding the checker a health body with
   `flywheel_ready=False`: `assert_parity` returns `[]`,
   `run(default)` exits **0**, `run(require_flywheel=True)` exits **1**.
   Without the flag, exit 0 cannot tell you the flywheel is alive — and on a
   cutover, liveness is the only property you are buying.

   The demotion is deliberate and dated:
   `docs/decisions/prod-parity-flywheel-informational.md` (2026-06-03) made
   liveness informational after it red-flagged an otherwise correct deploy. So
   do not "fix" the checker — pass the flag.

   Today's reading is itself a trap: prod reports `flywheel_ready: true` and
   `knowledge_reuse_count: 1`, so **both** forms exit 0 and the weaker one
   looks like it proved something. (Both re-run 2026-09-22 against
   `https://api.antiek.ai` at `3d7f7f16`: exit 0 either way, 5 providers.)

   Exit 1 naming the flywheel condition — reachable only with the flag — means
   the box reports a **dead** flywheel: a STOP.

3. **`GET /health` reports `flywheel_ready: true`** on the box.

   ```bash
   curl -s https://api.antiek.ai/health | python -m json.tool
   #  expect: "flywheel_ready": true,  "knowledge_reuse_count": >= 1
   #  observed 2026-09-22: true / 1, build_sha 3d7f7f16…, 5 providers
   ```

   `flywheel_ready` is the `/health` field added in SPR-11
   (`interfaces/research/api/app.py`, `HealthResponse` + `_probe_flywheel`).
   It is true iff the personal graph opens read-only AND >= 1
   `knowledge.reused` event is observable. The probe never raises — `false`
   means "not provably live," which is the safe red.

4. **§9.0 deny-by-default servability still holds.** No retrieval-time gating
   regression: the flywheel reuses only servable units. (Do not relax §9.0 or
   the §14.4 synthesizer pin to make a number look better.)

---

## The cutover (operator-only)

The cutover is not a special mechanism — it is the routine deploy of the
flywheel-enabled `main` to the box, after the preconditions are green.

1. Confirm all four **Preconditions** above are green and recorded.
2. Merge the flywheel work to `main` (operator approves the PR).
3. Deploy via the standard flow — see **`code-update.md`**:

   ```bash
   cd ~/Desktop/Antiek/infrastructure/ansible
   ansible-playbook -i inventory.ini playbooks/deploy.yml
   ```

   **The deploy enforces SHA + providers, NOT flywheel liveness.** `deploy.yml`
   does run the prod-parity assert as a **blocking** post-deploy task (line 751:
   *"prod-parity assert — deployed SHA == box HEAD + providers live"*,
   `delegate_to: localhost`, no `when:` guard — both still true). But the
   command it builds at lines 753-756 passes only `--url` and `--expected-sha`.
   Confirm it yourself — nothing on main promotes liveness to blocking:

   ```bash
   grep -rn 'require.flywheel\|require_flywheel' infrastructure/ansible/ .github/workflows/ > /tmp/rf.out 2>&1; echo $?
   #  → 1, /tmp/rf.out empty (grep matched nothing). Re-run 2026-09-22.
   ```

   Scope it to `infrastructure/ansible/`, not all of `infrastructure/`: this
   runbook lives under `infrastructure/runbooks/` and names the flag a dozen
   times, so the wider grep matches itself and reads as a false positive.

   A deploy onto a dead flywheel therefore prints a `::warning` and the play
   passes. The box **can** silently ship a non-compounding flywheel;
   precondition 2, run by you with `--require-flywheel`, is the only thing
   standing in front of that.

   That gap is closeable, and its closing condition is already met: the
   decision doc's RECONSIDER-IF says to flip the playbook to
   `--require-flywheel` once prod has produced >= 1 `knowledge.reused` event,
   and `/health` reports `knowledge_reuse_count: 1` today. Making that edit to
   `deploy.yml:753-756` is an operator change outside this runbook. Until it
   lands, never read a green deploy as a green flywheel.

4. Re-run precondition 2 (with `--require-flywheel`) + precondition 3 against
   live prod to confirm green post-deploy.

---

## Reconsider-if (what reverses the recommendation)

Stop the cutover — or roll back if already deployed — if ANY of these is true.
These are the evidence that the flywheel is not ready for prod:

| Signal | What it means | Action |
|---|---|---|
| The prod-shaped artifact does **NOT** reproduce dev's compounding slope (unobservable while precondition 1 is blocked — this is the rule for when the run becomes possible) | It compounds in dev but **not on prod** — the exact failure SPR-11 guards | **STOP.** Record the curve + gap in the handoff; do not cut over. Investigate the gap (prod tiers? latency? reuse loop not consuming the pack?) |
| `tools/prod_parity/check.py --require-flywheel` exits 1 naming the **flywheel** condition | `flywheel_ready` is false on the box — retrieval substrate did not open, or zero `knowledge.reused` events | **STOP.** The deploy will **not** red alongside you: it passes no `--require-flywheel` and only emits a `::warning`. You are the gate. Fix liveness before cutover |
| `tools/prod_parity/check.py` exits 1 on **SHA mismatch** | Deployed code is not main's tip | Deploy main first (routine), then re-check — this is the checker working, not a defect |
| `tools/prod_parity/check.py` exits 2 | Could not reach `/health` (network / Cloudflare) | Resolve reachability first; an unreachable box is not a cutover candidate |
| A §9.0 servability regression appears | The flywheel would reuse non-servable units | **STOP.** §9.0 deny-by-default is non-negotiable; do not relax it to pass |

---

## What this runbook does NOT do

- It does **not** run a deploy. The `ansible-playbook ... deploy.yml`
  invocation is the operator's, in step 3, after the preconditions are green.
- It does **not** run the prod-shaped benchmark, and neither can you today —
  `run.py:290` refuses every prod-profile invocation with exit 2. See
  precondition 1.
- It does **not** fabricate a prod curve. If the operator-window run does not
  reproduce, that is the finding — see *Reconsider-if*.
- It does **not** close any operator gate, set prod keys, or merge any branch
  on the operator's behalf.

---

## Reference artefacts

- `tools/prod_parity/check.py` — the parity checker: **two** blocking
  assertions (SHA + providers, `assert_parity` at line 119) plus flywheel
  liveness as an informational warning (`flywheel_warnings` at line 227) that
  blocks only under `--require-flywheel`.
- `docs/decisions/prod-parity-flywheel-informational.md` (2026-06-03) — why
  liveness is informational on deploy, and the RECONSIDER-IF that prod's
  `knowledge_reuse_count: 1` now satisfies.
- `infrastructure/ansible/playbooks/deploy.yml` (task at line 751, cmd at
  753-756) — the **blocking** post-deploy parity task that fires on every
  deploy. It passes no `--require-flywheel`.
- `/health` `flywheel_ready` + `knowledge_reuse_count` —
  `interfaces/research/api/app.py` (`HealthResponse`, `_probe_flywheel`).
- `compounding/benchmark/profiles/prod.toml` + `--profile prod` —
  the prod-shape benchmark selector (`compounding/benchmark/run.py`,
  `compounding/benchmark/profiles.py`). Carries
  `parameters_ratified = false`.
- `compounding/benchmark/results/prod-<sha>.json` — the prod-shaped result
  artifact the operator-window run is *supposed* to write. **Not wired on
  main**: `--out` defaults to `spr09_run.json`, and `out_filename_template` is
  read only by the refusal message (`run.py:233`).
- `code-update.md` — the routine deploy flow the cutover reuses.
