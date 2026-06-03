# Flywheel Prod Cutover — Turn Compounding On in Production

**Audience**: you (the operator), once the research-DEPTH flywheel is proven
at prod shape and you are deciding whether to flip it on in production.

**Time**: ~30 minutes of pre-flight verification + the operator window for the
prod-shaped benchmark run; the cutover deploy itself is the routine
`code-update.md` flow.

> **SPR-11 did NOT cut over.** This runbook is the *checklist*. SPR-11 (the
> EXIT of the Antiek Flywheel Foundation) built the prod-shape benchmark
> selector, extended the prod-parity assert to cover flywheel liveness, and
> added the `/health` `flywheel_ready` field — but it executed **no deploy**,
> closed **no operator gate**, set **no prod keys**, and ran **no live
> prod-shaped benchmark**. The live prod-shaped run and the cutover are
> operator gates. This document makes the cutover *evidenced*, not *asserted*.

> **2026-06-03 UPDATE — flywheel-liveness is no longer blocking-by-default on
> deploy.** Commit `873d95b0` (PR #68,
> `docs/decisions/prod-parity-flywheel-informational.md`) **demoted** the
> deploy-time flywheel-liveness assert from blocking to **informational**,
> because prod is dead for TWO reasons and only one is a code defect: (a) the
> reuse WIRE is dead at the prod entrypoint (`cascade_routes.py:367` omits
> `retrieval_substrate`; **Antiek Convergence SPR-02** fixes this), and (b)
> prod is an **empty corpus** (no `knowledge.reused` events from real research
> activity yet — needs a corpus ingest; arXiv is 429-banned). Forcing the
> assert on the empty box would red every correct deploy. The deploy task now
> takes an **`antiek_require_flywheel`** toggle (default `false`); set it
> `true` only when BOTH the wire (SPR-02) and a prod corpus exist — see the
> re-arm step below. This AGREES with the new reachability gate's known-red
> window (`docs/decisions/reachability-gate.md`): the flywheel is allowed red
> only during SPR-01 → SPR-02; the in-process reachability probe greens on the
> WIRE alone, this deploy assert additionally needs the corpus.

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

1. **The prod-shaped benchmark reproduced the compounding curve** —
   *operator window*. Run, on the box, with prod model-tier credentials and a
   reuse-CONSUMING browse loop (the host-local demo loop is reuse-blind, so a
   mock run cannot prove this):

   ```bash
   cd /opt/antiek
   python -m compounding.benchmark.run --profile prod \
       --n <operator-ratified-n> \
       --material-floor <ratified-floor> \
       --control-tolerance <ratified-tolerance>
   #  → writes compounding/benchmark/results/prod-<sha>.json
   #    (the diff-able twin of the dev spr09_run.json)
   ```

   The `--profile prod` selector (`compounding/benchmark/profiles/prod.toml`)
   flips `mock_run=False` and points dispatch at the prod tiers. It loads **no**
   mock fixtures — assert this in the run log.

   Interpret the `prod-<sha>.json` result **honestly** (rigor #1): EITHER
   "cost-to-resolve falls as the graph grows; slope reproduces dev within
   tolerance" OR "does **NOT** reproduce — here is the curve + the gap." A
   non-reproduction is a valid finding and a **STOP** for cutover — see
   *Reconsider-if* below. Never swap real dispatch back to mocks or soften the
   tolerance to manufacture a green.

2. **The parity assert is green against LIVE prod — including the flywheel,
   verified with `--require-flywheel`.** Post-#68 the flywheel is informational
   by default, so to *gate the cutover on it* you must opt in explicitly:

   ```bash
   python tools/prod_parity/check.py \
       --url https://api.antiek.ai \
       --expected-sha $(git rev-parse origin/main) \
       --require-flywheel
   echo $?   # 0 = SHA matches main + providers live + flywheel live
   ```

   With `--require-flywheel`, `tools/prod_parity/check.py` blocks on **three**
   things: deployed `build_sha` == main's tip, `registered_providers`
   non-empty, AND `flywheel_ready` true. Exit 1 naming the flywheel condition
   means the box reports a **dead** flywheel — a STOP. (Without the flag the
   flywheel only warns; that is the default the deploy uses until the toggle is
   flipped.)

3. **`GET /health` reports `flywheel_ready: true`** on the box.

   ```bash
   curl -s https://api.antiek.ai/health | python -m json.tool
   #  expect: "flywheel_ready": true,  "knowledge_reuse_count": >= 1
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

   **The deploy enforces SHA + provider parity unconditionally** (`deploy.yml`,
   the *"prod-parity assert — deployed SHA == box HEAD + providers live (+
   flywheel when re-armed)"* task, `delegate_to: localhost`, no `when:` guard).
   **Flywheel-liveness is re-armed by the `antiek_require_flywheel` toggle**
   (default `false` post-#68). To make a dead flywheel *fail the play* again,
   run the deploy with the toggle on — **only after** precondition 2 + 3 are
   green (wire landed + corpus produced >=1 reuse event):

   ```bash
   ansible-playbook -i inventory.ini playbooks/deploy.yml -e antiek_require_flywheel=true
   ```

   This appends `--require-flywheel` to the parity check so the box cannot
   silently ship a non-compounding flywheel **once compounding has been
   demonstrated on prod**. Leave it off (omit the `-e`) until then, or every
   correct deploy onto the still-empty box would red.

4. Re-run precondition 2 + 3 against live prod to confirm green post-deploy.

---

## Reconsider-if (what reverses the recommendation)

Stop the cutover — or roll back if already deployed — if ANY of these is true.
These are the evidence that the flywheel is not ready for prod:

| Signal | What it means | Action |
|---|---|---|
| `prod-<sha>.json` does **NOT** reproduce dev's compounding slope | It compounds in dev but **not on prod** — the exact failure SPR-11 guards | **STOP.** Record the curve + gap in the handoff; do not cut over. Investigate the gap (prod tiers? latency? reuse loop not consuming the pack?) |
| `tools/prod_parity/check.py` exits 1 naming the **flywheel** condition | `flywheel_ready` is false on the box — retrieval substrate did not open, or zero `knowledge.reused` events | **STOP.** The deploy assert will also red. Fix liveness before cutover |
| `tools/prod_parity/check.py` exits 1 on **SHA mismatch** | Deployed code is not main's tip | Deploy main first (routine), then re-check — this is the checker working, not a defect |
| `tools/prod_parity/check.py` exits 2 | Could not reach `/health` (network / Cloudflare) | Resolve reachability first; an unreachable box is not a cutover candidate |
| A §9.0 servability regression appears | The flywheel would reuse non-servable units | **STOP.** §9.0 deny-by-default is non-negotiable; do not relax it to pass |

---

## What this runbook does NOT do

- It does **not** run a deploy. The `ansible-playbook ... deploy.yml`
  invocation is the operator's, in step 3, after the preconditions are green.
- It does **not** fabricate a prod curve. If the operator-window run does not
  reproduce, that is the finding — see *Reconsider-if*.
- It does **not** close any operator gate, set prod keys, or merge any branch
  on the operator's behalf.

---

## Reference artefacts

- `tools/prod_parity/check.py` — the parity checker. SHA + providers always
  block; flywheel liveness blocks only with `--require-flywheel` (post-#68
  default is informational).
- `infrastructure/ansible/playbooks/deploy.yml` — the post-deploy parity task
  (SHA + providers blocking on every deploy; flywheel blocking only when
  `antiek_require_flywheel=true`).
- `docs/decisions/prod-parity-flywheel-informational.md` — why the deploy
  flywheel assert was demoted (#68) and the re-arm RECONSIDER-IF.
- `docs/decisions/reachability-gate.md` + `tools/reachability/known_red.json` —
  the pre-merge reachability gate + the agreed SPR-01 → SPR-02 known-red window.
- `/health` `flywheel_ready` + `knowledge_reuse_count` —
  `interfaces/research/api/app.py` (`HealthResponse`, `_probe_flywheel`).
- `compounding/benchmark/profiles/prod.toml` + `--profile prod` —
  the prod-shape benchmark selector (`compounding/benchmark/run.py`,
  `compounding/benchmark/profiles.py`).
- `compounding/benchmark/results/prod-<sha>.json` — the prod-shaped result
  artifact the operator-window run writes (the diff-able twin of the dev
  `spr09_run.json`).
- `code-update.md` — the routine deploy flow the cutover reuses.
