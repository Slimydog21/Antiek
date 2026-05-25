# Remote-exec research fan-out — enable, run, fall back, disable

**What this covers**: turning on off-host research fan-out so a Deep Research
Workspace cascade runs its N sub-question researches concurrently in Daytona
sandboxes instead of capped at the single host VM. This sits behind the §16
research-fan-out exemption (operator-ratified 2026-05-25; see
`docs/decisions/s16-research-fanout-exemption.md`). It does **not** change the
dispatch posture (Hermes-primary) or the DuckDB single-writer invariant.

**What stays true with this on**:
- Remote researches append only to their own per-investigation event logs.
  The serialized host funnel (`runtime/remote_exec/funnel.py` → DRW's
  `PromotionFunnel` through `runtime/db_lock`) is still the **only** graph
  writer. `--workers 1` is untouched.
- Cost flows through the same `DispatchCall` events host-local dispatch emits,
  bounded by the shared `TOTAL_ACQUISITION_BUDGET_USD` aggregate cap.
- Host-local (`HostLocalRunner`) remains the **automatic fallback** — disable
  remote-exec, or run on a box without the SDK/credentials, and the factory
  returns the host-local runner with one logged line. No code change.

**Default state**: OFF. Remote-exec is opt-in. Everything below is an operator
action; the agent test suite never runs live Daytona.

---

## Prerequisites

- A Daytona account + API key (operator-side; this is the spend gate).
- The optional dependency installed on the VM:
  ```bash
  pip install -e '.[remote_exec]'
  ```
  Without it, enabling remote-exec falls back to host-local and logs why
  (loud, not silent) — so a half-finished install never silently runs on the
  host pretending to be remote.

---

## Step 1 — Credentials env

The Daytona SDK reads its credential from `DAYTONA_API_KEY`
(`runtime/remote_exec/daytona.py` `_resolve_api_creds`). Append to
`/etc/antiek/secrets.env` (idempotent — overwrite if present):

```
ANTIEK_REMOTE_EXEC_ENABLED=1
DAYTONA_API_KEY=dtn_...
DAYTONA_TARGET=...            # optional region/target; omit for the default
```

Then re-chown + restart, same as the email-provider swap:

```bash
chown root:antiek /etc/antiek/secrets.env
chmod 0640 /etc/antiek/secrets.env
systemctl restart antiek
sleep 2
systemctl is-active antiek
```

`ANTIEK_REMOTE_EXEC_ENABLED` is the master switch the factory
(`runtime/remote_exec/factory.py` `remote_exec_enabled`) reads. A config-level
`enabled=True/False` passed to `build_research_runner` overrides the env flag
if a caller ever needs to force one way.

---

## Step 2 — Budget config

Remote-exec **shares the aggregate budget** with host-local research — there
is no separate remote cap (see the open question in
`docs/decisions/s16-research-fanout-exemption.md`). The aggregate ceiling is
`substrate.constants.TOTAL_ACQUISITION_BUDGET_USD` (default `$10.0`). Each
research also carries its own per-research `BudgetCap.cost_usd`.

- **Per-research cap exceeded** → that one leaf halts (`BUDGET_HALTED`); its
  siblings keep running.
- **Aggregate cap exceeded** → no *new* leaves launch; the refusal surfaces a
  reason on the leaf's status stream and a `investigation.chase_halted` event
  with `reason: aggregate_budget`. Running leaves complete.

To raise the aggregate ceiling, edit `substrate/constants.py`
(`TOTAL_ACQUISITION_BUDGET_USD`) — this is a deliberate code change, not a
config flip, by the master spec §16 "never default-uncapped" discipline.

The cost is **realized**: it comes off the sandbox's reported per-step
`cost_usd` (sandbox time slice + the inference the loop ran), emitted as
`DispatchCall` events the SPR-07 cost surface reads with no special-casing —
only the `provider` field names "daytona".

---

## Step 3 — Fallback behavior (what to expect, not a step)

The factory selects the runner at launch:

| Condition | Runner | Log |
|---|---|---|
| `ANTIEK_REMOTE_EXEC_ENABLED` unset/`0` | `HostLocalRunner` | none (documented default) |
| enabled + SDK + creds present | `RemoteResearchRunner` | one INFO line |
| enabled + SDK or creds **missing** | `HostLocalRunner` | one **WARNING** line |

The WARNING line names the fallback so a misconfiguration is visible:

```bash
journalctl -u antiek -n 100 --no-pager | grep -i "falling back to"
```

If you see that line and expected remote, check (a) the SDK is installed in
the venv the service uses, and (b) `DAYTONA_API_KEY` is in the service's
environment (`systemctl show antiek -p Environment`, or it is in
`/etc/antiek/secrets.env`).

---

## Step 4 — Operator-gated live smoke

> **This step requires Daytona credentials + spend. It is an operator action;
> the agent does not run it.** The automated suite proves isolation, budget
> halt, cancel teardown, and fallback against a fake provider with zero
> network (`tests/test_remote_exec_*.py`).

Launch a small 3-leaf cascade remotely and confirm three things:

1. **Three concurrent sandboxes.** With remote-exec enabled, cascade a problem
   into exactly 3 sub-questions and watch the Daytona dashboard show 3
   sandboxes provisioned near-simultaneously (not serialized).
2. **Merge.** After the three complete, confirm 3 insight/question promotions
   landed in the graph via the single funnel — query the graph:
   ```bash
   ssh -i ~/.ssh/antiek_ed25519 root@<vm> \
     'cd /opt/antiek && ./.venv/bin/python -c "
   from runtime.db_lock import connect_read
   con = connect_read(\"<graph.duckdb>\")
   print(con.execute(\"SELECT count(*) FROM nodes WHERE node_type IN (\x27insight\x27,\x27question\x27)\").fetchone())
   "'
   ```
3. **Cost.** Confirm `DispatchCall` events with `provider=daytona` recorded the
   realized cost, and the aggregate spend moved by that amount (not an
   estimate):
   ```bash
   journalctl -u antiek -n 200 --no-pager | grep -i dispatch
   ```

Sandbox teardown: each leaf tears its sandbox down on completion, cancel, or
error (`RemoteResearchRunner._teardown`, idempotent). After the smoke, confirm
the Daytona dashboard shows **zero lingering sandboxes** — a leak here is one
of the reconsider-if triggers in the decision record.

---

## Step 5 — Disable (one env flip back to host-local)

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm>
sudoedit /etc/antiek/secrets.env       # set ANTIEK_REMOTE_EXEC_ENABLED=0
systemctl restart antiek
sleep 2
systemctl is-active antiek
```

That is the entire revert: the factory now returns `HostLocalRunner`, cascades
run at the host-local ceiling, and the `runtime/remote_exec/` code stays in the
tree dormant. No code change, no redeploy beyond the restart. This one-flip
revert is the mechanical guarantee behind the decision record's reconsider-if:
if remote-exec proves fragile or expensive at the host-local-ceiling level,
flip it off and the amendment is marked superseded.

---

## Why a runbook and not a default-on feature

Remote-exec adds a vendor dependency (Daytona) and a spend surface (sandbox
time). The steelman for staying host-local-first is recorded in
`docs/decisions/s16-research-fanout-exemption.md` (the `parameter_extractor`
loky/external-kill failure class can reappear at the sandbox-fleet boundary).
We honor it by keeping host-local the automatic fallback and gating the live
run behind this runbook rather than flipping it on for everyone. The operator
turns it on when a real cascade is host-capped and the spend is justified, and
off again with one env flip.

---

## Companion docs

- `docs/decisions/s16-research-fanout-exemption.md` — the §16 scope + rationale
  + reconsider-if.
- `CLAUDE.md` §16 — the scoped exemption paragraph.
- `runtime/remote_exec/` — provider interface, Daytona provider, remote runner,
  single-writer funnel, cost path, factory.
- `runtime/research_runner/` — the host-local runner (the fallback) + DRW's
  serialized `PromotionFunnel` this reuses.
- `infrastructure/runbooks/agentmail-setup.md` — the secrets.env + restart
  idiom this runbook mirrors.
