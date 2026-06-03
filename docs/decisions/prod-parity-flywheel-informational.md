# Prod-parity: flywheel-liveness is informational on deploy (not blocking)

**Date:** 2026-06-03
**Status:** Decided (operator-approved during the 2026-06-03 deploy).
**Scope:** `tools/prod_parity/check.py` + its use as a BLOCKING post-deploy task
in `infrastructure/ansible/playbooks/deploy.yml`.

## Context

`tools/prod_parity/check.py` asserted three things, all BLOCKING the deploy:
(a) deployed `build_sha` == expected, (b) `registered_providers` non-empty,
(c) the SPR-11 flywheel is live (`flywheel_ready` true / `knowledge_reuse_count
> 0`).

On the 2026-06-03 deploy of `main` (`7d9caa6`: §9 retrieval-gate closure + ASR
SR-00..09 + PostHog Feel), the deploy landed correctly — `/health` reported the
new `build_sha`, 5 providers registered, both frontends served — but the
playbook exited non-zero on (c): `flywheel_ready: false, knowledge_reuse_count:
0`.

## Decision

(c) is **informational by default**: a `::warning` that does NOT fail the run.
(a) and (b) remain **blocking**. A new `--require-flywheel` flag (and
`run(..., require_flywheel=True)`) promotes (c) back to blocking on demand.

## Why

Flywheel liveness is a **product-maturity signal**, not a **deploy-correctness
invariant**. `flywheel_ready` only becomes true once the box has an ingested
corpus AND ≥ 1 `knowledge.reused` event from real research activity. A correct
code deploy onto an unfed box **cannot** make it true — so hard-failing the
deploy on it red-flags every correct deploy. The prod box is currently unfed:
the corpus ingest window is an operator-gated deferral (arXiv is 429-banned; see
`engineering_deferrals.md` D17/D18), so `flywheel_ready` is legitimately false.

SHA + providers, by contrast, ARE properties the deploy is responsible for and
can always satisfy — they stay blocking (they are the catch that surfaced the
original stale-SPA drift SPR-07 was built for).

This does not weaken the SPR-11 signal: a dead flywheel is still surfaced loudly
(GitHub `::warning` + stderr), and the scheduled `prod_parity.yml` probe was
already `continue-on-error`. We removed a *false blocking* condition, not the
*signal*.

## RECONSIDER-IF

Once an operator corpus ingest has produced ≥ 1 `knowledge.reused` event on
prod (i.e. compounding is genuinely live), flip the deploy playbook's
prod-parity task to pass `--require-flywheel` so a *regression* to a dead
flywheel reds the deploy again. At that point (c) is a real invariant — the box
has demonstrated compounding, so losing it IS a deploy-correctness failure. That
is the original SPR-11 intent, now correctly sequenced *after* the corpus
exists rather than before.

### 2026-06-03 amendment (Antiek Convergence SPR-01 / M6) — the re-arm is now wired and sequenced

The re-arm is no longer a manual code edit: `deploy.yml` takes an
**`antiek_require_flywheel`** toggle (default `false`) that appends
`--require-flywheel` when set. The flip is gated on BOTH conditions, in order,
because prod's dead flywheel has TWO causes and #68 only neutralized the
false-block from the second:

1. **The WIRE lands (Antiek Convergence SPR-02).** Prod's flywheel is dead not
   only because the corpus is empty but because the prod entrypoint never
   injects the substrate: `interfaces/research/api/cascade_routes.py:367` builds
   `HostLocalRunner(...)` with `retrieval_substrate=None`, so
   `runtime/research_runner/host_local.py:259` early-returns the reuse hook.
   SPR-02 wires it. Until then, even a fed corpus could not emit
   `knowledge.reused` from the real launch path.
2. **The corpus produces ≥ 1 reuse event on prod** (the original #68 condition).

Run `ansible-playbook ... deploy.yml -e antiek_require_flywheel=true` only when
both hold (see `infrastructure/runbooks/flywheel-prod-cutover.md`).

**Agreement with the pre-merge reachability gate.** Antiek Convergence SPR-01
also installed a *pre-merge* reachability probe
(`tools/reachability/probes/flywheel.py`, `docs/decisions/reachability-gate.md`)
that asserts the same compounding outcome (`knowledge_reuse_count > 0`) but
**in-process, against a temp DuckDB, with no corpus** — because the reuse
assembler emits `knowledge.reused` even with zero prior units
(`substrate/context_pack/knowledge_reuse.py:652`), so the in-process probe
greens on the **wire alone**. Both gates agree the flywheel is allowed to be red
**only during the SPR-01 → SPR-02 window** — the reachability gate enforces this
with a known-red entry carrying a hard expiry
(`tools/reachability/known_red.json`, `until_date 2026-07-03`), and this deploy
toggle stays off until the wire **and** the corpus exist. The honest difference
in scope: the reachability probe gates the WIRE (pre-merge); this deploy assert
gates LIVE PROD COMPOUNDING (wire + corpus), which is strictly more.

## Verification

- `tests/test_prod_parity.py`: `assert_parity` gates only SHA + providers;
  `flywheel_warnings` names a dead flywheel; `run` exits 0 on a dead flywheel by
  default and 1 under `require_flywheel`.
- Live: `python tools/prod_parity/check.py --url https://api.antiek.ai
  --expected-sha <main>` exits 0 (warns on the flywheel); adding
  `--require-flywheel` exits 1 until the corpus ingest runs.
