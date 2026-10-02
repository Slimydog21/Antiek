# Antiek — agent onboarding

**You're picking up this codebase cold. Read this file before anything else.**

## What Antiek is

A research workstation + creation surface + interview-as-acquisition product
unified on one substrate. The canonical spec is `docs/master-product-spec.md`
(~3,000 lines). The substrate is DuckDB + typed event log; voice/style
discipline (§5) is non-negotiable; the IP-attribution + ad-economics
mechanism (§9) is the strategically consequential layer.

## Read these in order

1. **`docs/operator_gate_actions.md`** — current status of the binding
   gates blocking activation (its quick-status table is the live
   register; counts in prose rot). The "Operator Activities"
   section at the bottom is the cross-session breadcrumb.
2. **`docs/agent-execution/HARD_TO_VARY.md`** + **`docs/agent-execution/TEMPLATES.md`**
   — mandatory for all agent sessions before diagnosing Research/cascade bugs or
   claiming verification. Phase A→E protocol; forbidden patterns F1–F8; handoff
   paste from templates.
3. **`docs/master-product-spec.md`** — the spec. §14 is the sprint
   sequence; §14.3 is the binding ordering discipline; §16 is the explicit
   REJECT list.
4. **`docs/sprint_track_reconciliation.md`** — explains the two parallel
   sprint sequences (master-spec 11→22 + UI-redesign 0→12).
5. **`docs/decisions/`** — one markdown per closed gate or binding
   decision. Quick browse here tells you what's been settled.

## Don't propose engineering until you read this

As of 2026-05-23 session-end, the **engineering scope of the spec is
essentially complete** (run `./.venv/bin/python -m pytest tests/ -q` for
the live test count — this file's own history proves literal counts rot).
The bottleneck is operator action on the open gates (quick-status table
in `docs/operator_gate_actions.md`). Before you suggest new engineering work:

- Check `docs/operator_gate_actions.md` "Operator Activities" section.
- Verify the bottleneck isn't already a known operator-bound item.
- If a real engineering gap exists, audit against the section
  `## Genuine remaining gaps, exhaustively` in the latest in-session
  audit (the v4 audit content lives in this README's git history;
  search for `phase2_execution_audit` files in `docs/`).

## Critical invariants — DO NOT VIOLATE

1. **DuckDB single-writer.** `--workers 1` on uvicorn, period. Per §16.
   The only-writer invariant is enforced at `runtime/db_lock.py` and the
   antiek.service systemd unit.
2. **Voice/style discipline.** Master-spec §5. Prose flows, no LLM-slop,
   no forced bullets, claim spans inline. Applies to prose AND UI.
3. **Substrate-as-source-of-truth.** Every claim cites chunks. Every chunk
   cites documents. Every document carries `ip_holder_id` (even null).
   Don't break the provenance chain.
4. **Sprint 18 legal gate.** Payouts gate strictly on retrieval-time
   gating in production + publisher opt-in. Per §9.0. Currently G1
   closed; G2 + G3 open. Don't propose money-routing changes that
   bypass.
5. **Single-operator until Sprint 22.** Compounding hasn't been
   demonstrated yet. Premature multi-user destroys the moat. G7 gates
   the multi-user pivot at ~Nov 2026 earliest.
6. **Single email provider.** Use what's configured in
   `ANTIEK_EMAIL_PROVIDER`. AgentMail is the current choice (per
   2026-05-23 verdict in `docs/operator_gate_actions.md`); custom-domain
   upgrade is deferred.

## What's running on prod

- `antiek.service` — FastAPI substrate at `https://api.antiek.ai`
- `antiek-continuous-research.service` — §7.3/§7.4 evidentiary-gap
  daemon (since 2026-05-23)
- Cloudflare Pages — frontend at `https://antiek.ai` (auto-builds from
  `main`)
- Cloudflare Tunnel — `api.antiek.ai` → Hetzner CCX23

Auth: magic-link via AgentMail. Per
`infrastructure/runbooks/magic-link-auth.md` and
`infrastructure/runbooks/agentmail-setup.md`.

## When you write code

- Tests live in `tests/`. Run `./.venv/bin/python -m pytest tests/ -q`.
- Frontend at `apps/reading/`. TS strict; run `npx tsc -b` to check.
- Don't add files to mainline branches; the operator's parallel-stream
  tooling commits in big batches, so collisions are common. Commit
  what's yours; let the parallel stream commit theirs.
- The §16 REJECT list is canonical: no Daytona/Modal/Pulumi/etc, no
  PostHog vendor tone, no ε > 10 on DP claims, no premature scaling.

## Before you touch the PR board — read this, it is the dominant cost

Measured 2026-09-22 across the 28 PRs merged in one day: **each one consumed a
median of 6 CI runs — ~58 job-slots where 9 would do. A 6.4x waste multiplier.**
That, not the runner ceiling, is what makes the board slow. Twenty concurrent
job-slots is ample for ~320 PRs/day at one cycle each; observed throughput was 30.

Why it happens: `main-gate-integrity` sets `strict_required_status_checks_policy`,
so a branch must be up to date with main at merge time, against a ~63-minute CI
run. **main's commit rate varies by an order of magnitude and that decides
whether merging is winnable at all** — measured 2026-09-22: a 2.7-minute median
gap over 24h (163 commits, inflated by a burst period) but **44.7 minutes over
the quiet 3 hours that followed** (6 commits). Measure it before you plan a
merge: `git log origin/main --since="3 hours ago" --format=%cI`. When the gap is
minutes, a rebased branch is BEHIND again before CI finishes and the run is
wasted; when it is ~45 minutes, a green PR can be updated and merged inside one
window.

- **Update-branch exactly ONE PR at a time — the one you intend to merge next.**
  Never in a batch. A batch fires 2 runs per PR (`CI` + `enforce-declared-bar`)
  and the first merge invalidates every other one.
- **`ps aux | grep -iE "gh run|gh api|gh pr"` before driving any PR.** Several
  agent sessions run against this repo at once. Two loops applying
  BEHIND->update-branch to the same PR cannot converge: `ci.yml` keys
  `cancel-in-progress` on the PR ref, so each session's rebase kills the other's
  in-flight CI. Exactly one writer per branch.
- **Do NOT auto-rerun a run whose conclusion is `cancelled`.** Under
  `cancel-in-progress`, cancelled is the NORMAL state of a superseded attempt;
  re-running it re-triggers the same rule. Re-run at most once, only when the run
  is `completed`, and only for an ORPHANED run (cancelled with no newer run on
  that branch) — that case does leave required checks unreported forever.
- **Never bulk-cancel runs to free capacity.** Each cancelled run costs a blocked
  PR needing a manual rerun, and `gh run cancel`/`rerun` both return 0 for
  requests they do not fulfil — verify `run_attempt` incremented.
- A merge QUEUE would fix this structurally and is **not available**: the rule is
  organization-only and this repo is user-owned, so `merge_queue` returns 422
  `Invalid rule`. The `merge_group:` triggers already in `ci.yml` and
  `enforce_declared_bar.yml` are waiting on a repo transfer to an org.

<!-- BEGIN: s16-research-fanout-exemption (unified SPR-02; operator-ratified 2026-05-25) -->
- **§16 exemption — research fan-out only.** The operator ratified one
  scoped carve-out on 2026-05-25: *research-runner fan-out* (and only that)
  may execute on an external provider via `runtime/remote_exec/`, so a DRW
  cascade can run N sub-question researches genuinely concurrently off-host
  rather than capped at the host VM. Daytona is the one implementation
  behind the `RemoteExecProvider` interface. Everything else in the §16
  REJECT line above is **unchanged**: dispatch stays Hermes-primary (no
  Daytona/Modal/Prime as a dispatch provider for non-research inference);
  the DuckDB single-writer invariant is untouched (remote researches append
  only to their own per-investigation event logs — the serialized host
  funnel through `runtime/db_lock` remains the sole graph writer); ε > 10
  on DP claims and premature scaling stay rejected. Host-local
  (`HostLocalRunner`) is the automatic fallback when remote-exec is disabled
  or the provider is unavailable. Rationale + reconsider-if:
  `docs/decisions/s16-research-fanout-exemption.md`.
<!-- END: s16-research-fanout-exemption -->

<!-- BEGIN: agent-failure-regression (managed by SPR-E2 of antiek-hashimoto-engineering) -->
- **Agent-failure regression library.** Every observed agent failure
  (a production path that produced wrong/surprising output) gets a YAML
  fixture at `tests/regression/agent_failures/<slug>.yaml` BEFORE the
  fix lands. The fixture must fail (or be GAP-marked) until the
  mitigation ships. See `tests/regression/agent_failures/README.md`
  for the onboarding flow. Programmatic failure logging via
  `orchestration.agent_failure_log.record()` (JSONL append-only at
  `~/.antiek/agent_failures.jsonl`, daily rotation). The library's
  current set: `ls tests/regression/agent_failures/` (a prose count here
  went stale within weeks — fixtures get added and marked mitigated on
  main faster than this file is edited).
<!-- END: agent-failure-regression -->

<!-- BEGIN: craft-signature (managed by SPR-E7 of antiek-hashimoto-engineering) -->
- **Craft signature: inline-rubric latency.** `substrate.synthesis_rubric.scorer.score_synthesis`
  p95 must stay within 10% of the locked baseline (194.85 μs at git
  `640a31c`, 2026-05-24). Enforced OPERATOR-SIDE via
  `python -m benchmarks.rubric_latency --check-regression`. CI runs it
  INFORMATIONALLY only: `ci.yml:190` pipes it to `|| echo "::warning
  title=Latency check is informational on CI..."`, because the shared
  runner reports a false +120% on a microsecond benchmark. (Corrected
  2026-09-20: this read "CI fails on regression".) Every other
  perf dimension is explicitly "good enough" — see `docs/craft_signature.md`
  for the policy + the locked numbers. To re-mint the baseline after a
  deliberate perf change: `python -m benchmarks.rubric_latency --update-baseline`
  (operator-only; do not run in CI).
<!-- END: craft-signature -->

<!-- BEGIN: test-integrity-floor (managed by SPR-06 of antiek-beck-test-integrity) -->
- **Test-integrity floor (Beck desiderata).** Five read-only tools under
  `tools/` measure whether Antiek's suite is behavior-sensitive, isolated,
  deterministic, and not mock-ratio-regressing. They do NOT rewrite product
  tests.
  - Census (shared input): `tools/test_census.py` + `tools/test_census_baseline.json`
  - Fake-gate detector: `tools/fake_gate_detector.py` + `mutants/` +
    `mutants/survivors_baseline.json`
  - Desiderata lint: `tools/lint/test_desiderata_check.py`
  - Flaky quarantine (opt-in, not per-PR CI): `tools/flaky_quarantine.py` +
    `tests/quarantine.toml`
  - Mock-budget gate: `tools/lint/mock_budget_check.py` +
    `tools/lints/baselines/mock_budget.json`
  - CI workflow: `.github/workflows/test_integrity.yml` (additive — `ci.yml`
    untouched). The three wired gates (detector, lint, budget) are
    **informational-first**: they run on every relevant PR, print full
    `path:line` findings to the log, surface `::warning::` on nonzero tool
    exit, and do NOT red the build until baselines settle.
  - Reconciliation doc: `docs/decisions/test-integrity-ci-floor.md` — each
    gate's flip-to-blocking condition (reconsider-if). **Do NOT** flip one to
    blocking without that written condition. **Do NOT** silently bump the
    mock-budget baseline or the survivor baseline — re-mint is operator-only
    via `capture` with a documented reason.
  - Last test-integrity update: 2026-06-04 (ABT/SPR-06)
<!-- END: test-integrity-floor -->

## What changed in the 2026-05-23 session

| Commit | What |
|---|---|
| `7450ef1` | Inline rubric scoring after Phase 6 — closes §14.4 gap |
| `13f4f2f` | Continuous-research daemon systemd + `__main__` |
| `38b13be` | Dispatch verdict self-grade fallback |
| `eeaf084` | TZ-aware window comparison in verdict |
| `bc4022e` | Verdict reads `emitted_at` + G4 closure note |
| `d7b9296` | Dispatch verdict + G5 follow-up documented |
| `417fa1f` | AgentMail custom-domain deferral |
| `00d5cac` | AgentMail provider |

Three gates closed (G1, G4, G5). Two services now running on prod
(`antiek`, `antiek-continuous-research`). 2,703 tests, 100% green.
