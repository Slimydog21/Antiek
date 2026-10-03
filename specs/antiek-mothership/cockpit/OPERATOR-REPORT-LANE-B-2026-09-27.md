# Operator report, lane B (Antiek Sweep v2), 2026-09-27 00:30Z

These items need you, and no agent can act on them. Each one gives its default until you rule, so nothing is blocked on a silent guess. Facts are read-only observations made at this time.

## 1. Production is 113 commits behind main, and deploys are cancelled

- **Prod** is `build_sha 570cf6f2f`, the #3511 merge at 2026-09-26 12:07Z (`GET https://api.antiek.ai/health`, `schema_version 40`).
- **Main** is `b41f4ec9b` (#3412). Prod is its ancestor, 113 commits back.
- **The last four `deploy_backend.yml` runs** (d61e5256d ×3, b41f4ec9b) all ended `cancelled`.
- **The unblocker** is #3529 ("fix(caddy): file-matcher root is a path"). It is first in the Antiek Nudge train. Its declared checks are partly green, and pytest shards 0–3 are still pending.
- **Your action:** none while the train runs. If the train stalls, #3529 is the one PR to prioritise. Every other handed-off PR (LB-2 #3530, LB-34 #3531, LB-12 #3537, LB-33 #3534, LB-4a #3527, #3528) only reaches users after it deploys.

## 2. `migrate_owner_namespace --apply` on prod (from #3382, merged 2026-09-24)

- #3382 aligned the owner namespace in code. Prod data needs its migration applied (`specs/antiek-mothership/index.html`, the decision table).
- Agents may not SSH to prod or write to it, so this is yours.
- **Your action:** run it once the train has deployed a main that contains #3382 (every main since 2026-09-24 does).

## 3. Q-B1: are there committed source merges on prod?

- **The question:** "Does prod hold any `source_merge.committed` without a later `.restored`?"
- **The evidence to check:** `source_merge_body_commits` rows with no matching `source_merge_body_restores` row.
- **If no:** `restore` retires with the same 410 as the other source-merge routes (LB-33), and LB-33b is not built.
- **If yes:** `restore` stays live, API-only, and LB-33b adds a receipt read.
- **Default until you answer:** `restore` stays live.

## 4. Q-B2: house ads on non-book documents?

- **The question:** "May house ads and impression accrual run on non-book documents opened in the reader?"
- For anything not from arXiv, the backend sets `ad_eligible == servable` (`substrate/books/serve_guard.py`). Once LB-35 opens non-books, servable web pages and arXiv T1 papers would carry ad rails.
- **Default: off.** Lane A mounts no ad rail on `is_book: false`.

## 5. Q-B3: LB-35 defaults (non-book reader serving)

Each has a conservative default, from `cockpit/LB-35-SPEC-2026-09-27.md` §6:

| Question | Default |
|---|---|
| Q2: is a whole-book upload a non-book? | Yes, by `document_type` |
| Q3: `/ask` on unregistered non-books | Stays 404, out of scope |
| Q5: `ip_holder_id` in the non-book fallback | Null |
| Q6: is the takedown record deleted on reinstate? | Yes |

**Your action:** confirm or override any of them.

## 6. O-11: standing autonomy consent versus D4's per-flag consent

- R28 (sub-agent-level management of autonomous research) wants a standing consent envelope `{max_cents, expires_at}` per agent.
- Signed decision D4 requires per-flag consent for every launch. O-11 is the only open exception to a signed decision.
- **Default:** per-flag consent (LB-28). No envelope routes or events are built.

## 7. The continuous-research daemon's budget variable is unread on prod

- The systemd unit sets `…_BUDGET_USD_PER_DAY`. The code reads `…_HOURLY_BUDGET_USD`, so prod runs on the code default.
- #3415 (audit wave 4, open, in the train) fixes the unit.
- **Your action:** after #3415 deploys, confirm the unit's environment carries the budget you intend.

## 8. Open calls recorded by the audits

- `docs/decisions/audit-wave4-open-calls.md` covers four calls, carried on #3415: opted-out holder escrow, demand-gate wiring, the daemon cap lock (`budget.py` is byte-frozen by the §7.4 tripwire test), and Prime Agent ceiling billing.
- `docs/decisions/audit-wave5-open-calls.md` covers five calls, carried on the wave-5 branch. That branch goes to main through the B0 integration PR, which opens after #3415 merges.

## 9. Containment housekeeping (LB-0), for you and the merge authority

- **Done:** `allow_auto_merge` is `false`. The repo setting was read just now.
- **#3516** ("promote(reformat)") is still open. LB-0 recommends closing it as superseded by #3522/#3527.
- **#3514** ("promote(companion)") is still open. LB-9 replaces it with a §1.12-shaped rebuild, now being specified.
- **#3477** (the reformatting spec) is still open. It should carry a supersession banner for §1.11a and `spawnChild` before any merge.

## 10. Critic capacity (informational)

- GLM (glmf-codex) is out of quota until 2026-09-27 19:02 local.
- codex is out until 2026-09-30.
- MiMo is available now and runs sandbox-only.
- Different-lineage reviews before 19:02 use MiMo. The rev-9 contract audit uses MiMo for round 1 and GLM after the reset.

## What is moving without you

- **The merge train** (Antiek Nudge) lands #3529, then the safety PRs.
- **B0 integration.** B0 is the parent's branch record before a child starts, the base for highlight → island → sub-agent. It is being merged onto main as `fix/b0-wave5-integration-20260927`. Its PR opens after #3415.
- **LB-3** (agent threads as right-pane tabs: honest states, listings, per-thread fetch, turns) and **LB-9** (the companion document plus the owner-safe evidence base) are being specified from signed contract rev 8.10, then built red-first.
- **Rev 9 of the thread contract** is waiting on lane A's Part 2 fold. Part 1 now carries §1.4c and A06, with Astra's four round-2 amendments. After the fold it goes to a different-lineage audit and both signatures.
