# Run Real Investigations — the operator traffic runbook

**Audience**: the operator, running the 5–10 real investigations that unlock G5
(dispatch-tier verdict), feed G7 (six-month compounding demonstration), and
populate the §14.4 measurement window. This is action #2 in
`docs/operator_gate_actions.md` and the single highest-leverage thing only the
operator can do: the substrate is healthy, but no fresh traffic has gone
through it since 2026-05-23.

**Time budget**: ~10 minutes of operator attention per investigation; the
investigation itself runs ~2–5 minutes unattended once launched. Budget ~1 hour
for the first cohort of 5.

**Cost**: per-investigation dispatch cost against your own provider keys. The
substrate caps a single investigation at the configured per-investigation
budget; a cohort of 5 typically runs well under $5 total. Watch the live cost
meter if you have the web app open.

**What this runbook is NOT**: it does not close any gate by itself. Running
investigations *produces the signal* the gates consume. G5 closes when you
re-run the dispatch-tier verdict CLI against the fresh `rubric.scored` events;
G7 closes on six months of accumulated signal. Both need this runbook first.

**On the code pointers below**: they name symbols, not line numbers. Every
line anchor this runbook used to carry had rotted — all five pointed at
unrelated code, one of them off by 2,312 lines — so each pointer is now
something `git grep -n '<symbol>' -- interfaces/research/api/app.py` finds in
one command, which is what you want at 2am and not a number that drifts every
time someone inserts a route.

---

## Step 0 — Preflight: is the substrate ready for a real run?

Every check must pass before you spend a real dispatch call. The curls name
`https://api.antiek.ai` literally and run from anywhere with network access —
your laptop is fine. No environment variable redirects them (`ANTIEK_API_BASE`
is read by `tools/prod_parity/check.py` and by nothing in this runbook), so
point them at another host by editing the URL. The two VM-side checks — the
`build_sha` comparison and sourcing provider env — do need a shell on the box.

Every interpreter call is `python3`, deliberately. The VM installs `python3`,
`python3-venv`, `python3-pip` and `python3-dev` and not `python-is-python3`
(`infrastructure/ansible/playbooks/setup.yml`), so a bare `python` exits 127
there even though it happens to work on a Mac with anaconda on PATH.

```bash
# 0a. Is the service up + on the build you expect?
curl -sS https://api.antiek.ai/health | python3 -m json.tool
```

What you are reading:
- `build_sha` — must equal `origin/main` tip (`git -C /opt/antiek rev-parse HEAD`
  on the VM). A stale sha means a code update did not deploy; fix that first
  (`infrastructure/runbooks/code-update.md`).
- `schema_version` — the DB migration head. A mismatch with the code's expected
  version means the deploy half-applied; do not run investigations.
- `flywheel_ready` / `knowledge_reuse_count` — the compounding signal. Starts
  `false`/`0` on a fresh graph and flips as prior investigations get reused.

```bash
# 0b. Are the dispatch provider keys registered? (the gate the whole AI is on)
curl -sS https://api.antiek.ai/health | python3 -c "
import json, sys
h = json.load(sys.stdin)
print('registered_providers:', h.get('registered_providers'))
print('providers_ready:', h.get('providers_ready'))
"
```

`registered_providers` is the `list[str]` of dispatch providers that
bootstrapped with a key; `providers_ready` is the boolean the launch path gates
on (`providers_ready` on `class HealthResponse`,
`interfaces/research/api/app.py`). The keyed first-run capture (read a
synthesis → accrual view → honest G2/G3 payout refusal) is actionable only when
these are populated. If the list is empty or missing the synthesis tier, the
investigation will degrade to local-only / no-synthesis rather than fail — **a
green preflight with no keys is not "research works."** Source the provider env
on the VM (`/etc/antiek/secrets.env`) and restart `antiek` if needed
(`infrastructure/runbooks/magic-link-auth.md` for the auth side).

```bash
# 0c. Do you hold a credential the API accepts? Answer this BEFORE Step 1 —
# every /investigations call sits behind the operator gate.
export ANTIEK_OPERATOR_TOKEN='…'   # from /etc/antiek/secrets.env on the VM
curl -sS -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  https://api.antiek.ai/investigations/credential-check | python3 -m json.tool
```

`{"investigation_id": "credential-check", "status": "not_found"}` is the
**pass**: the gate let you through and there is simply no investigation by
that name. A `401` carrying `"code": "operator_auth_required"` means the
credential is missing or wrong, and every command from Step 1 onward fails the
same way — which is how this runbook used to read, sending
`Cookie: ANTIEK_SESSION=` from a variable it never set.

The middleware accepts any one of three credentials (`magic-link-auth.md` has
the full picture): the `ANTIEK_OPERATOR_TOKEN` bearer used above, which is the
machine path probes and CI already take; a Cloudflare Access service-token
pair; or the `ANTIEK_SESSION` cookie minted by a browser sign-in at
`https://antiek.ai/login`. To use the cookie instead, copy it out of DevTools →
Application → Cookies, `export ANTIEK_SESSION='…'`, and swap every
`-H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN"` below for
`-H "Cookie: ANTIEK_SESSION=$ANTIEK_SESSION"`. The rest of this runbook is
written against the bearer because it is the one you can hold in a terminal.

---

## Step 1 — Launch one investigation (the cold-question entry point)

`POST /investigations` is the operator-facing cold-question surface (handler
`async def post_investigation` in `interfaces/research/api/app.py`; the
decorator above it is split across lines, so grep the handler name, not the
route string). One question in, a full Loop-1 trajectory out.

```bash
curl -sS -X POST https://api.antiek.ai/investigations \
  -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "<your real research question, >= 3 chars>",
    "max_sub_questions": 8,
    "research_tier": null
  }' | python3 -m json.tool
```

Field guidance (load-bearing — read before you change a default):

- **`question`** (required, ≥3 chars): a real question you want answered. The
  cohort's value is in *real* questions; throwaway questions produce
  throwaway rubric signal.
- **`max_sub_questions`** (default 8, 1–20): how many sub-questions the
  decomposer fans out. Raise for breadth, lower for cost/focus.
- **`research_tier`** (default `null`): **leave `null` unless you mean to
  override.** `null` = no override → the config-pinned synthesizer primary
  runs (the §14.4 measurement window pins the synthesizer to Opus; setting
  `"deep"` here would persist and silently displace that Opus primary once
  `DEEPSEEK_API_KEY` is set, corrupting the G5 measurement). Pick a tier
  explicitly only when you are deliberately testing a specific tier. See the
  comment block above `research_tier: Literal["fast", "deep"] | None` on
  `InvestigationStartRequest` in `app.py` — this is the one field where
  a wrong default breaks the measurement you are trying to produce.
- **`investigation_id`**: omit it (auto-generated) for every fresh run,
  including a re-run of the same question. A known id is an idempotent
  replay of that start: the same body returns the original `start_event_id`
  and runs nothing (polling then shows the earlier run's result), and a
  different body is refused with 409 `investigation_id_conflict`. Reuse an
  id only to safely retry a start whose response you did not receive.

Save the returned `investigation_id` — you poll with it next.

---

## Step 2 — Poll until terminal

```bash
# Replace <id> with the investigation_id from Step 1.
curl -sS https://api.antiek.ai/investigations/<id> \
  -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" | python3 -m json.tool
```

Read the `status` field (`status: str` on `class InvestigationStatusResponse`
in `app.py`, whose docstring lists these same four literals):

| `status` | Meaning | Action |
|---|---|---|
| `not_found` | no events for this id at all | the POST did not register; re-launch |
| `in_progress` | start event present, no terminal event yet | wait ~30s, poll again |
| `completed` | `investigation.completed` present | go to Step 3 |
| `failed` | `investigation.failed` present | read `terminal_payload` for the cause |

While `in_progress`, `current_phase` (1–9) and `last_delivered_action_type`
show where the chain is. The protocol is nine phases, not eight — the field is
declared `phase: int | None = Field(default=None, ge=1, le=9)` — so a
`current_phase` of 9 is the last phase, not an out-of-range reading. A long
stall at one phase with no new delivered events is the signal to check the
dispatch logs, not to keep polling.

---

## Step 3 — Read the synthesis + capture the rubric signal

When `status == "completed"`:

- **`rubric_score`** (SPR-11 M3, `rubric_score: RubricScore | None` on
  `InvestigationStatusResponse`) is the §14.4 inline-rubric verdict
  for this investigation's synthesis, read from the persisted `rubric.scored`
  event. **`null` is an honest absent value, never a fabricated number** — a
  completed investigation with `rubric_score: null` means no scored event was
  emitted (the synthesis rubric scorer at `substrate/synthesis_rubric/` did not
  fire); that is itself a finding to report, not a pass.
- **`terminal_payload`** carries the archived synthesis handle. The
  human-facing artifact is the `MASTER.md` synthesis (master-spec §2.4); read
  it against the voice/style bar (§5) — em-dash count ≤2/thesis, no padding
  constructions, sector vocabulary absorbed.

This `rubric.scored` event per investigation is exactly the signal the G5
dispatch-tier verdict consumes. You need ≥5–10 of these before re-running the
verdict.

---

## Step 4 — Run the cohort + close the measurement gates

Repeat Steps 1–3 for 5–10 real questions. Vary the domains so the sector-
vocabulary and grounding signals are meaningful, not overfit to one topic.

After the cohort:

**Close G5 (dispatch-tier verdict).** Re-run the verdict CLI against the
fresh events (this is the re-open trigger documented in
`docs/operator_gate_actions.md` G5):

```bash
ssh -i ~/.ssh/antiek_ed25519 root@167.235.202.98 \
  '/opt/antiek/.venv/bin/python -m tools.dispatch_tier_verdict \
   --events /home/antiek/.antiek/research_events/ --since 2026-05-23 \
   --output /opt/antiek/docs/decisions/dispatch-tier-verdict.md'
```

Pass `--output` absolutely, as above. Its default is the *relative*
`docs/decisions/dispatch-tier-verdict.md` and this ssh lands you in `/root`,
so without it the verdict is written to `/root/docs/decisions/` — and because
the CLI creates parent directories silently, nothing errors and you go looking
for a file the repo never received. The verdict then sits on the VM, so pull
it down before you can tick the checklist item below, and commit it:

```bash
scp -i ~/.ssh/antiek_ed25519 \
  root@167.235.202.98:/opt/antiek/docs/decisions/dispatch-tier-verdict.md \
  docs/decisions/
```

Expect a real verdict (`keep_opus_primary` or `flip_to_hermes_primary`) based
on actual rubric scores, not the pre-2026-05-23 self-grade fallback.

**Feed G7 (compounding demonstration).** Each completed investigation adds to
the graph; `knowledge_reuse_count` (from `/health`) ticks up when a later
investigation cites a chunk first ingested in an earlier one. The G7 bar is
≥100 investigations + ≥20% cross-investigation reuse + ≥3 published artifacts
+ ≥1 unsolicited peer inquiry — a six-month accumulation, not a single cohort.
This runbook starts that curve.

---

## What "done" looks like for this runbook

- [ ] Preflight passed: `/health` shows the current `build_sha` and registered
      dispatch providers.
- [ ] 5–10 real investigations reached `status: completed` with a non-null
      `rubric_score` each.
- [ ] G5 dispatch-tier verdict re-run against the fresh events; outcome
      recorded in `docs/decisions/`.
- [ ] (Ongoing) the compounding curve has fresh data toward G7.

## If something is honestly broken

- A `completed` investigation with `rubric_score: null` → the synthesis rubric
  scorer did not fire; do not paper over it. File the symptom (the
  `investigation_id` + the null score) per the agent-failure regression
  library convention (`tests/regression/agent_failures/`).
- Repeated `failed` status → read `terminal_payload`; a provider-unconfigured
  503 means the keys are not registered (Step 0b), not a substrate bug.
- Stale `build_sha` → deploy first (`code-update.md`); running investigations
  against old code produces signal against old behavior.
