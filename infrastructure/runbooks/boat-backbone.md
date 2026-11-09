# Runbook: Boat compute backbone (both planes: keys, read-only verification, paid smoke, enable, reaper, disable)

**Decision:** `docs/decisions/boat-compute-backbone-2026-11-09.md` (PROPOSED,
awaiting the owner's ratification). Read its Decision §1 (the two planes), §5
(what `BoatBackend` does and does not yet do) and §7 (the envelopes) first.
**State today:** OFF. `boat` is not a registered `ANTIEK_EXEC_BACKEND` kind
until gate G2 (`factory.py:35` accepts `local` and `docker`). G1 is met: org
Antiek holds one `box_20` subscription with `canStart` true since about
06:25Z on 2026-11-09. Neither plane key is installed yet (G4). The cloud
CEO's review of draft PR #3826 requested changes; this revision answers it,
and the decision stays PROPOSED.
**Who runs it:** the owner, or the cloud CEO at the owner's explicit
direction, step by step. Every command that carries a plane key runs where
the "Credentials" table installs that key: the cloud CEO's environment
(`/opt/data`, Boat CLI 1.0.96 at `/opt/data/.ascii/bin/boat`) for every gate,
unless the owner names another staging host for G3.3 and the table records
it first. The CEO's hourly swarm (cron `b413595fcdd5`) runs none of this. The agent
test suite never calls Boat.
**Code:** `runtime/exec_backend/boat_backend.py` (`BoatBackend`, dark),
`runtime/exec_backend/factory.py`, `runtime/research_runner/contained_gather.py`.

Evidence labels as in the decision record: **[M]** measured, or stated by a
named Boat page or the OpenAPI contract as saved on 2026-11-09; **[I]**
inferred; **[A]** assumed until a G3 step checks it.

**What stays true with this on.** A workspace receives and returns bytes; the
promotion funnel through `runtime/db_lock` stays the only graph writer and
`--workers 1` is untouched. No Antiek credential enters a Boat sandbox, and no
subscription credential or owner login is copied into Boat. Omarchy
execution and host-owned credentials are permitted under current owner
policy, as the cloud CEO's review in PR #3826 (Spec/doctrine finding 1)
states it, pending the owner's confirmation (decision record, Context and
open sign-off 5). No
inference or dispatch moves to Boat: dispatch stays Hermes-primary, with no
Boat integrated agent and no AI-credentials proxy. The 2026-10-07 AWS
decision, its lane hosts and the peer tenants' arrangement are unchanged, and
nothing here executes the AWS migration. Installed Boat is not a dispatch
target for the swarm on either plane until the owner approves activation.
Nothing here changes the account's active wallet: every command names the
organization with `--org`.

---

## The two planes

| | PRODUCT plane | BUILD plane |
|---|---|---|
| What runs | `BoatBackend` workspaces behind `ExecutionBackend`, inside the product | development, production-shaped tests, CI, the CEO's coding-swarm lanes |
| Boat environment | `antiek-product` (*Safe for third parties* on) | `antiek-build` (passes nothing until the owner's D-18 ruling) |
| Key | `BOAT_API_KEY` (`ci` preset, `--env antiek-product`) | `BOAT_BUILD_API_KEY` (`ci` preset, `--env antiek-build`) |
| Organization | `ANTIEK_BOAT_ORG` = `team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3` | the same |
| Sandbox names | `antiek-ws-<profile>-<8 hex>`, labels `antiek-workspace`, `antiek-profile` (set by the code) | `antiek-build-*` if `boat new --help` shows a name flag [A]; the build ledger always |
| First tier | none | Omarchy (free; the only tier for lanes that need the owner's subscription logins) |

Both planes bill the one `box_20` subscription and share its 100 active
sandboxes, its 12 / 60 / 200 starts, its 555.56 included hours and its wallet
with each other and with the Boat Research boxes `bx_235rmpn3` and
`bx_35hs5p53` [M]. Those two boxes live in environment `base` and are never
touched by anything here.

---

## Shell setup in the cloud CEO's environment

Source these lines into the shell that runs a gate. They print nothing on
success. Each wrapper refuses to run when its key is missing or when
`ANTIEK_BOAT_ORG` is not the Antiek team id, and neither falls back from one
plane's key to the other's or to a stored login.

```bash
set +x                                   # never trace a shell that holds a key
BOAT=/opt/data/.ascii/bin/boat           # the SHA-256-verified 1.0.96 binary
ORG_ID=team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3
# Every wrapper call checks the org pin; a missing or wrong pin refuses, it does not warn.
_org_ok() { [ "${ANTIEK_BOAT_ORG:-}" = "$ORG_ID" ] || { echo "STOP: ANTIEK_BOAT_ORG is not the Antiek team id" >&2; return 2; }; }
# PRODUCT plane: reads, info, exec, usage and delete. Product sandboxes are created by BoatBackend only.
P() { _org_ok || return 2
      [ -n "${BOAT_API_KEY:-}" ] || { echo "STOP: BOAT_API_KEY unset" >&2; return 2; }
      case "${1:-}" in new|fork|resume) echo "STOP: product sandboxes are created by BoatBackend only" >&2; return 2 ;; esac
      "$BOAT" --org "$ORG_ID" "$@"; }
# BUILD plane: its own key, placed in the child's environment only, never in argv.
# Every new is pinned to antiek-build; fork and resume inherit the source's environment;
# no environment flag and no -e value is accepted.
B() { _org_ok || return 2
      [ -n "${BOAT_BUILD_API_KEY:-}" ] || { echo "STOP: BOAT_BUILD_API_KEY unset" >&2; return 2; }
      case "${1:-}" in
        new|fork|resume)
          local a
          for a in "$@"; do
            case "$a" in --env*|--no-env|-e|-e?*) echo "STOP: B pins antiek-build; refusing $a" >&2; return 2 ;; esac
          done
          [ "$1" = new ] && set -- "$@" --environment antiek-build ;;
      esac
      BOAT_API_KEY="$BOAT_BUILD_API_KEY" "$BOAT" --org "$ORG_ID" "$@"; }
R="/opt/data/antiek/operations/boat-g3-$(date -u +%Y%m%dT%H%M%SZ)"; mkdir -p "$R"
```

`--org` before the subcommand is the documented form (`boat --org <org>
api-key create`) [M, `api-keys.md`]. The wrappers assume the CLI
authenticates from `BOAT_API_KEY` in its environment, ahead of any stored
login [A: an earlier orchestrator observation quoted in the drafts; it is in
neither this lane's facts nor a saved page, and Boat's own CI recipe signs in
with `boat login --key-stdin` instead [M, `ci.md`]]. G3.1 step 0 checks it
before anything else runs. That is why `B` overrides `BOAT_API_KEY` for one
child process, and why both wrappers refuse an empty key.

`B` pins `--environment antiek-build` on `new` because a create that names no
environment lands in the default environment `base` [M, OpenAPI
`CreateSandboxRequest.environment`, "Omit to use your default environment"],
and `base` passes the owner's secrets, GitHub token and agent credentials [M].
Whether the build key's `--env` restriction would refuse that create is not
documented. A fork that names no environment inherits its source's [M,
OpenAPI fork], and a resume with a new `--environment` always starts a new
machine [M, `snapshots_stop.md`], so neither is pinned; both refuse an
environment flag. `-e KEY=VALUE` passes one value into a sandbox [M, `ci.md`];
`B` refuses it so that no credential reaches a build box before the owner's
D-18 ruling. `P` creates nothing: the product plane's sandboxes come from
`BoatBackend`, which names `antiek-product` itself. Outside these wrappers and
`BoatBackend`, a plane key is used only by the Part A script's read, exec and
usage calls, G3.1 steps 0 and 2, and the three deliberate attempts of G3.2
Part B. `$R` sits beside the CEO's coordination receipt,
outside every repository [A: location proposed].

**Receipt discipline.** Every receipt line comes out of a `jq` filter that
names the fields it keeps. Never `tee` raw Boat output: create and list
answers carry `url` and `desktopUrl`, and a desktop URL carries a token [M,
OpenAPI examples]. Never print `envContents` or `secretFiles` from an
environment listing. Never run `env`, `printenv`, `set -x` or `declare -p` in
a shell holding a key. Check a key's presence by name only:
`printf '%s=%s\n' BOAT_API_KEY "${BOAT_API_KEY:+set}"`.

---

## Credentials

| Variable or key | Plane | Kind | Lives in | Never |
|---|---|---|---|---|
| `BOAT_API_KEY` | product | organization key, `ci` preset, `--env antiek-product` | the cloud CEO's environment, including the G3.3 staging run of the service there; another staging host only once the owner names it and it is added here; at enable, also the production host's `/etc/antiek/secrets.env` (`root:antiek 0640`) | argv, a log, a receipt, a Boat environment, a build command, a host this table does not name |
| `BOAT_BUILD_API_KEY` | build | organization key, `ci` preset, `--env antiek-build` | the cloud CEO's environment only | a production host, argv, a log, a receipt, the product process, a host this table does not name |
| `ANTIEK_BOAT_ORG` | both | the team id; not a secret | the cloud CEO's environment (G3.3 included); the production host at enable | |
| The unscoped organization admin key, the personal account key | the owner's | admin-scoped | with the owner | any agent's environment (the personal key is the decision record's open sign-off 2) |
| Omarchy's stored Boat CLI login | the Boat Research session's | account-wide login | Omarchy, as a host-owned credential that current owner policy permits there (decision record, open sign-off 5) | a Boat sandbox, environment or key; any plane's work. The wallet it can spend is open sign-off 2 |

The `ci` preset can create, resume and fork sandboxes, operate them, and
delete only the sandboxes that key created; it has no account admin [M,
`api-keys_scopes.md`]. An organization key is refused account settings
(`403 api_key_org_forbidden`) and any other organization or Personal (`403
api_key_org_mismatch`) [M, `api-keys.md`], so neither plane key can mint,
rotate or revoke keys; only the owner can.

### Minting (the owner, gate G4)

The dashboard with Antiek selected is the preferred path, because the secret
then never passes through a shell. The documented CLI pieces, for reference,
from the owner's own account session:

```bash
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 env new antiek-product
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 env set antiek-product --safe-for-third-parties true
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 env new antiek-build
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 env set antiek-build --github false --secrets false --boat-credentials false --agents-credentials false
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 api-key create antiek-product-ci --preset ci --env antiek-product --ttl 90d
boat --org team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3 api-key create antiek-build-ci  --preset ci --env antiek-build  --ttl 90d
```

Each flag is documented on its own (`env new` [M, `security.md`]; `env set`
and its toggles [M, `environments_access.md`]; `--org`, `--preset`, `--env`,
`--ttl` [M, `api-keys.md`]); `--org` on `env` commands and the four together
on one key are not shown [A]. If the CLI refuses a combination, stop: the
plane design rests on it. `antiek-build`'s toggles stay off until the owner's
D-18 ruling (decision record, open sign-off 1). Boat advises the shortest TTL
that works [M, `api-keys.md`]; 90 days is what Boat's CI page uses [M,
`ci.md`]; record the TTL chosen.

Each secret is shown once. The owner places it in the cloud CEO's secret
store under the variable name in the table, and records from the dashboard
each key's name, id, preset, environment, expiry and last four characters,
never the value. A key pasted into a chat transcript stays in that transcript:
see "Rotation" and the decision record's open sign-off 3.

### Rotation and revocation

- **Rotate**: `boat api-key rotate <id>` [M, `ci.md`], or the dashboard, from
  the owner's session; it replaces the secret "without changing expiry or
  scope" [M, OpenAPI]. Install the replacement in the cloud CEO's store (and,
  for the product key after enable, the production host), then re-run G3.1
  steps 1 to 4 for that key. A plane key cannot rotate itself: rotation needs a
  dashboard or CLI session or an admin-scoped key [M, OpenAPI].
- **Revoke** a leaked key first and investigate second [M, `api-keys.md`]:
  dashboard (Antiek selected, API keys) or `boat api-key revoke <id>` from the
  owner's session [M, `api_v1.md`: `DELETE /api-keys/{apiKeyId}`, "Revoke an
  API key", CLI `boat api-key revoke`]. Then delete the variable from the CEO's store and the
  production host, and for the product key follow "Fallback and disable".
- **Audit** a key's use: `boat api-key usage <id>` [M, `api_v1.md`], from the
  owner's session.

### Proof that no plane key reached a receipt or a log (the cloud CEO, after each gate)

File names and a count only; no command prints a line's content. The first
check uses the exact values of both plane keys as patterns, passed through
`printf` (a shell builtin) and a pipe, so neither value reaches any
process's argv. The others use the key shape the module itself refuses to
log, `boat_` followed by at least 24 token characters [A: the docs give only
the prefix]; the 10-character keyless `channel` value does not match it.

```bash
{ [ -n "${BOAT_API_KEY:-}" ] && [ -n "${BOAT_BUILD_API_KEY:-}" ]; } || echo "STOP: the exact-value check needs both plane keys set" >&2
grep -rlF -f <(printf '%s\n' "${BOAT_API_KEY:-}" "${BOAT_BUILD_API_KEY:-}") -- "$R" /opt/data/antiek/operations/boat-build-ledger.jsonl 2>/dev/null
grep -rlE 'boat_[A-Za-z0-9_-]{24,}' -- "$R" /opt/data/antiek/operations/boat-build-ledger.jsonl 2>/dev/null
# On the host that runs the service (the G3.3 staging run, production after enable): a count, never a line.
journalctl -u antiek --no-pager -o cat | grep -cE 'boat_[A-Za-z0-9_-]{24,}'
```

Pass: no STOP line, the two `grep -l` print nothing, and the count is 0. An
empty key makes the first check list every file, a loud failure rather than
a silent pass. No `boat login` is ever run with a plane key: it would store a
login, which the wrappers' no-fallback rule refuses. The Boat Research
session's stored CLI login on Omarchy is a host-owned credential that
current owner policy permits there; it is never copied into Boat, and the
wallet it can spend is the decision record's open sign-off 2.

---

## Envelopes and caps (PROPOSED until G2; decision record §7)

| | Product | Build | Left for research boxes and slack |
|---|---|---|---|
| Creates per rolling minute / hour / day | 8 / 36 / 120 | 4 / 20 / 60 | 0 / 4 / 20 (of the included 12 / 60 / 200) |
| Active at once | 20 (the runner's cap) | 4 | 2 research boxes; 74 of 100 unused |
| Smoke spend ceiling | Part A USD 0.10; Part B USD 0.05 for its three attempts with both keys; G3.3 USD 0.10 | Part B inside that USD 0.05; Part C USD 0.10 | |
| Smoke TTL | Part A 1,200 s; Part B 900 s; G3.3 900 s (the `ResourceLimits()` default) | Part B 900 s; Part C 1,800 s | |
| Steady spend ceiling (VM time at list price) | USD 1 a day, USD 15 a billing period; a daily check ("Watching spend") | USD 5 a day, USD 50 a billing period; a daily check | |
| Size | `small` | `default` | |
| Auto-stop | `wall_clock_s` (900 s default), at most 3,600 s; never off | at most 7,200 s, extended only while a lane runs; never off without the owner | |
| Snapshots | off (`snapshots: false` on every create; the code has no override and reads the record back) | only on boxes that stop to resume a lane | |

**The hard stop is Boat-side.** Keep the wallet funded by hand only, auto
top-up off, and invoiced extra starts off (off by default [M, `limits.md`]).
Then work beyond the included time and wallet fails with `402
billing_required` and starts beyond the windows fail with `429` rather than
bill [M, `limits.md`]. While the wallet holds money, extra starts are paid
from it at USD 0.03 to 0.07 each [M, `limits.md`]; a 20-leaf launch inside one
minute buys 8 of them for USD 0.28 [I], which is why the product share caps a
launch at 8 sub-questions until creates are paced in code. What happens to
running sandboxes when included time and wallet run out is on
`billing.md#running-out`, not saved; read it before relying on the wallet as
the only stop.

### Watching spend

**What Antiek's budget does not see.** The cascade charges a notional USD 0.01
a step (`cascade_routes.py:399`) to `TOTAL_ACQUISITION_BUDGET_USD` (USD 10,
`substrate/constants.py:141`) and never Boat's real dollars. Neither plane
has a code-side file ledger or cost cap yet (decision record §5 items 5 and
7), so the steady-state ceilings are a daily check by the owner, or by the
cloud CEO at the owner's direction, never by the swarm. The check gives a
list-price figure per plane and says whether it is an upper bound or
incomplete; it enforces nothing.

The account as a whole, read with either key:

```bash
P limits --json | jq -c '{teamId, canStart, activeSandboxes, vmHoursRemaining: .planIncluded.vmHoursRemaining,
  periodEnd: .planIncluded.periodEnd, wallet: .wallet.balanceDollars, starts, nextStartDollars}'
P usage <bx id> --json      # the bill of one sandbox, size applied [M, pricing.md]; --json [A]
```

The included-hours and wallet deltas also move with the other plane and the
research boxes, so they cannot split spend by plane.

**Product plane, from the service journal.** The backend logs one
`BoatBackend sandbox accepted: sandbox=<bx id> workspace=<id> type=<type>
ttlSeconds=<n> createdAt=<time> via=<create|repost|sweep>` line per sandbox
Boat accepted, the moment its id is known, and one `BoatBackend sandbox
deleted: sandbox=<bx id> workspace=<id> via=<destroy|orphan>
result=<deleted|not-found>` line per confirmed delete [M, the module at
`ac778a27`, "Spend ledger lines"]. A sandbox that failed provisioning after
Boat billed it, and a lost create that the same-key re-`POST` or the label
sweep recovered, each have an accepted line, so the check counts them. Each
accepted sandbox counts at its full `ttlSeconds` (an `unknown` TTL at the
code's 30-day maximum, an `unknown` size at the top rate), which bounds that
sandbox, because the auto-stop ends billing at most one TTL after the create
and the backend neither resumes nor extends a sandbox [I].

The sum is **incomplete, never an upper bound**, and the script labels it so.
Three things still escape it: a lost create that neither the re-`POST` nor
the sweep found leaves at most a WARNING naming its workspace and no sandbox
id (the script counts those workspaces as `unresolved_lost_creates`), and
none at all when the create, or the same-key re-`POST`, was answered
without a usable sandbox id and the sweep's listing then found nothing (the
module logs nothing for that path; the create raises
`WorkspaceProvisionError` to its caller); a service killed between Boat's
answer and the log line leaves no line at all; and a sandbox accepted before
the window opened is outside it. The listing after the script names every
`antiek-ws-` sandbox the product key can see that no accepted line in the
window names; for the silent paths it is the only net. Set `SINCE` to
`-24h` for the daily ceiling. For the period ceiling, set it to the billing period's start, which
is `periodEnd` minus one month (2026-11-09 06:25:35 UTC for the current
period).

```bash
SINCE=-24h; IDS=$(mktemp)
journalctl -u antiek --since="$SINCE" --no-pager -o cat | python3 -I -c '
import json, re, sys
RATE = {"small": 0.018, "default": 0.036, "large": 0.072, "xlarge": 0.20}   # USD per hour [M, pricing.md]
TOP_TTL = 2592000                                                            # the code clamps ttlSeconds to 30 days
ACC = re.compile(r"BoatBackend sandbox accepted: sandbox=(bx_\w+) workspace=(\S+) type=(\S+) ttlSeconds=(\S+) createdAt=\S+ via=(\w+)")
DEL = re.compile(r"BoatBackend sandbox deleted: sandbox=(bx_\w+) workspace=\S+ via=\w+ result=(?:deleted|not-found)")
LOST = re.compile(r"(?:same-key re-POST for the lost create|could not check for an orphaned Boat sandbox|cleanup after the lost create) of workspace (\w+)")
usd, via, found, gone, lost = {}, {}, set(), set(), set()
for line in sys.stdin:
    m = ACC.search(line)
    if m and m[1] not in usd:
        ttl = int(m[4]) if m[4].isdigit() else TOP_TTL
        usd[m[1]] = ttl / 3600 * RATE.get(m[3], 0.20)
        via[m[5]] = via.get(m[5], 0) + 1
        found.add(m[2])
    m = DEL.search(line)
    if m:
        gone.add(m[1])
    m = LOST.search(line)
    if m:
        lost.add(m[1])
print(json.dumps({"plane": "product", "accepted": len(usd), "via": via, "deleted": len(gone & set(usd)),
                  "open": len(set(usd) - gone), "unresolved_lost_creates": len(lost - found),
                  "accounted_usd": round(sum(usd.values()), 4), "label": "incomplete"}))
print("\n".join(sorted(usd)), file=sys.stderr)' 2> "$IDS"
# antiek-ws- sandboxes the product key can see that no accepted line in the window names (ids only):
P list --all --json | jq -r '.sandboxes[]? | select((.name // "") | startswith("antiek-ws-")) | .id' | sort | comm -23 - <(sort "$IDS")
rm -f -- "$IDS"
```

At the default 900 s on `small`, a workspace costs at most USD 0.0045, so the
product's 120 starts a day cap a day's VM time at USD 0.54 while that start
share holds [I]; it is policy, not code (decision record §5 item 4). Stop new
product work until the owner rules when `accounted_usd` exceeds USD 1.00 a
day (or USD 15 in the period), when `unresolved_lost_creates` is above 0, or
when the listing prints an id. An id the listing prints is either a sandbox
accepted before the window (its accepted line is in the earlier journal; a
recorded id for the reaper) or a create that escaped the log. Then the
actual figure is `P usage <id> --json` summed over every id involved, and the
dashboard.

**Build plane, from the build ledger.** Each create has an intent row
before it (`intent`, `at`), an id row with `created_at`, `type` and `ttl`
after it and, after its delete, a `destroyed_at` row. Part C and "Enable and
activation" write all three. A box that is still open counts up to now.

```bash
python3 -I - /opt/data/antiek/operations/boat-build-ledger.jsonl 86400 <<'LEDGER'
import json, sys, time
from datetime import datetime, timezone
RATE = {"small": 0.018, "default": 0.036, "large": 0.072, "xlarge": 0.20}   # USD per hour [M, pricing.md]
now = time.time(); lo = now - float(sys.argv[2])
made, gone, intents = {}, {}, 0
for line in open(sys.argv[1], encoding="utf-8"):
    row = json.loads(line)
    if "intent" in row:
        at = datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp()
        intents += at >= lo
    if "created_at" in row:
        made[row["sandbox"]] = (float(row["created_at"]), row.get("type", "xlarge"))
    if "destroyed_at" in row:
        gone[row["sandbox"]] = float(row["destroyed_at"])
usd = sum(max(0.0, min(gone.get(b, now), now) - max(t, lo)) / 3600 * RATE.get(k, 0.20)
          for b, (t, k) in made.items())
unmatched = max(0, intents - sum(1 for t, _ in made.values() if t >= lo))
print(json.dumps({"plane": "build", "window_s": round(now - lo), "boxes": len(made),
                  "open": len(set(made) - set(gone)), "unmatched_intents": unmatched,
                  "list_price_usd": round(usd, 4), "label": "incomplete" if unmatched else "upper bound"}))
LEDGER
```

The second argument is the window in seconds: 86400 for the daily ceiling of
USD 5.00, or the seconds since the period's start for the USD 50 ceiling.
The figure is an upper bound only when `unmatched_intents` is 0: an intent
row without its id row is a create whose outcome is unknown (Part C's
"returned no sandbox id" stop), so the label turns to `incomplete`, and
`B list --all --json` against the ledger finds the box if it exists. If the
figure is above either ceiling, or incomplete, stop issuing `B` creates
until the owner rules. Either plane's figure covers only creates made
through `BoatBackend` or `B` and logged or ledgered. That is why nothing
else may create with a plane key.

**Every smoke receipt also carries a list-price bound per sandbox:** (delete
time minus create time) times the size's hourly rate. This is an upper
bound, because billing starts at `provisioned` [M, `concepts.md`].

---

## G3.1: read-only scope verification (no sandbox is created)

In the cloud CEO's environment, after the shell setup, with both keys
installed. Nothing here starts or changes a sandbox.

```bash
# 0. The CLI authenticates from BOAT_API_KEY alone, and there is no stored login to fall back to.
#    The child of the first line holds no key, so its message is safe to keep (first 200 characters).
nokey=$(env -u BOAT_API_KEY -u BOAT_BUILD_API_KEY "$BOAT" --org "$ORG_ID" limits --json 2>&1); rc=$?
printf '%s\nrc=%s\n' "${nokey:0:200}" "$rc" > "$R/g31-0-nokey.txt"; unset nokey
for f in P B; do $f limits --json 2>&1 | jq -c --arg k "$f" '{step:"env_key", key:$k, teamId:(.teamId // null),
  code:(.code // .error.code // null), status:(.status // .error.status // null)}' | tee -a "$R/g31.jsonl"; done

# 1. Presence and distinctness, by name only.
{ for v in ANTIEK_BOAT_ORG BOAT_API_KEY BOAT_BUILD_API_KEY; do printf '%s=%s\n' "$v" "${!v:+set}"; done
  [ "$BOAT_API_KEY" != "$BOAT_BUILD_API_KEY" ] && echo keys=distinct || echo keys=SAME; } | tee "$R/g31-1-presence.txt"

# 2. Each key is an organization key: naming Personal is refused.
"$BOAT" --org personal list --json 2>&1 | jq -c '{step:"org_key", key:"product", code:(.code // .error.code // null), status:(.status // .error.status // null)}' | tee -a "$R/g31.jsonl"
BOAT_API_KEY="$BOAT_BUILD_API_KEY" "$BOAT" --org personal list --json 2>&1 | jq -c '{step:"org_key", key:"build", code:(.code // .error.code // null), status:(.status // .error.status // null)}' | tee -a "$R/g31.jsonl"

# 3. Each key reads Antiek's limits (needs account.read).
for f in P B; do $f limits --json 2>&1 | jq -c --arg k "$f" '{step:"limits", key:$k, teamId, canStart, billingStatus, accessTier,
  blockedReason, activeSandboxes, maxActiveSandboxes, vmHoursRemaining:(.planIncluded.vmHoursRemaining // null),
  periodEnd:(.planIncluded.periodEnd // null), wallet:(.wallet.balanceDollars // null), starts,
  present:{activeSandboxes:has("activeSandboxes"), starts:has("starts"), machineTypes:has("machineTypes")},
  types:[.machineTypes[]? | select(.available) | .type], code:(.code // .error.code // null)}' | tee -a "$R/g31.jsonl"; done

# 4. Neither key can see or manage account keys.
for f in P B; do $f api-key list --json 2>&1 | jq -c --arg k "$f" '{step:"keys", key:$k, code:(.code // .error.code // null),
  status:(.status // .error.status // null), n:((.apiKeys // []) | length)}' | tee -a "$R/g31.jsonl"; done

# 5. Each key's reach: which sandboxes it can list, every state.
for f in P B; do $f list --all --json 2>&1 | jq -c --arg k "$f" '{step:"reach", key:$k,
  rows:[.sandboxes[]? | {id, name, state, team:.team.id}], code:(.code // .error.code // null)}' | tee -a "$R/g31.jsonl"; done

# 6. What each environment passes (never envContents or secretFiles), and whether the live
#    shape carries proxyAiCredentials at all (decision record §5 item 11).
for f in P B; do $f env list --json 2>&1 | jq -c --arg k "$f" '{step:"envs", key:$k, envs:[.environments[]? | {name, isDefault,
  safeForThirdParties, passGithub, passSecrets, passSandboxCredentials, passAgentsCredentials, proxyAiCredentials,
  proxyAiPresent:has("proxyAiCredentials")}], code:(.code // .error.code // null)}' | tee -a "$R/g31.jsonl"; done
```

The CLI's JSON shapes for these commands are assumed to mirror the REST
answers (`GET /limits`, `GET /sandboxes`, `GET /api-keys`, `GET
/environments`) [A]; `boat list` shows running sandboxes only unless given
`--all` [M, `llms.txt`].

| Step | Expected | If not |
|---|---|---|
| 0 | `g31-0-nokey.txt`: an authentication refusal (not signed in, or a 401) and a non-zero `rc`; then, for `P` and `B`, either a `teamId` or a 403 scope code such as `api_key_action_forbidden`, never an authentication error | the key-less call succeeds: a stored login exists in this environment and the wrappers' no-fallback rule is void; stop until the owner removes it. `P` or `B` gets an authentication error: the CLI does not read `BOAT_API_KEY` from its environment, and the wrappers cannot work; stop. The owner then decides between per-plane stored logins in separate configuration directories in the CEO's environment and driving the build plane through the REST API; this record makes neither change |
| 1 | three `=set` lines and `keys=distinct` | stop: G4 is not done, or one key is installed under both names |
| 2 | `code: "api_key_org_mismatch"`, `status: 403`, for both keys [M, `api-keys.md`] | stop: a key that can name Personal is an account key; it must not be a plane key |
| 3, product | `teamId` equal to `ANTIEK_BOAT_ORG`, `canStart: true`, `billingStatus: "active"`, `accessTier: "standard"`, `maxActiveSandboxes: 100`, `small` in `types`; `present` true for `activeSandboxes` and `starts` (the OpenAPI documents both; the saved live shape of a personal read lacks them) | `code: "api_key_action_forbidden"` means the `ci` preset lacks `account.read`: record it; `BoatBackend.probe()` then logs a WARNING and checks `canStart` and the pin per create only (decision record §5 item 2), and the owner accepts that or re-mints the key. `canStart: false`, no `canStart` at all (`BoatBackend` refuses such an answer as shape drift), or a `teamId` other than Antiek's: stop |
| 3, build | the same fields | a refusal is recorded, not a stop (build tooling does not call `probe()`); a wrong `teamId` is a stop |
| 4 | for each key, a 403 (`api_key_org_forbidden` or `api_key_action_forbidden`) or `n: 0` (a restricted caller "receives `apiKeys: []`" [M, OpenAPI]) | `n` above 0: an unrestricted key; stop |
| 5 | for each key, `rows: []`; above all, neither `bx_235rmpn3` nor `bx_35hs5p53` | either research box listed: the key reaches `base`; record it, act on no listed id, stop for the owner |
| 6 | `antiek-product` with `safeForThirdParties: true` and `proxyAiCredentials: false` (its toggles may still read `true`; that switch overrides them [M, `environments_access.md`]), or with the field absent (`proxyAiPresent: false`, which the module accepts; the owner's dashboard record then shows the proxy off); `antiek-build` with all four `pass*` false, or `safeForThirdParties: true`; `base` absent from each key's list. Record every listed environment's `proxyAiPresent`: this is the live shape the module names as an activation gate, and if any is `true`, the code lane makes an environment without the field a refusal before G2's registration (decision record §5 item 11) | `base` listed: the key reaches the owner's default environment; stop. `antiek-product` passing anything: stop and fix the environment before any create (decision record §5 item 1). Product key refused (`api_key_action_forbidden` or `api_key_sandbox_forbidden`), or `antiek-product` missing from its list: stop. `BoatBackend` refuses to start without that read (it fails closed at probe and at every create), so the owner re-mints the product key with `environment.read` on `antiek-product` (decision record §5 item 2). Build key refused: the owner reads the same flags from the dashboard and records them, because build tooling does not read them; G3.2 does not start without that record |

The baseline for G3.2 is step 3: `activeSandboxes`, `vmHoursRemaining`,
`wallet` and `starts`. If `present` shows `activeSandboxes` or `starts`
absent, record it: G3.2's comparison for that field is then marked
unavailable, never passed, and teardown rests on the per-id checks alone. Do
not substitute `currentLimits.activeSandboxes`, which sits beside
`standardLimits` and `trialLimits` and reads as a cap, not a count [I,
OpenAPI `LimitsFields`]. The owner reads this receipt and rules on open
sign-off 3 (the pasted keys) before authorizing G3.2.

---

## G3.2: the paid smoke (separately authorized by the owner)

Envelope: decision record §7. `small` only. Part A: at most two product
sandboxes, one at a time, TTL 1,200 s, USD 0.10. Part B: three create
attempts with TTL 900 s that should all be refused except possibly the
no-environment observation, USD 0.05 for the three together. Part C: one
build box, TTL 1,800 s, USD 0.10. The whole run fits inside 30 minutes, uses
synthetic data only, and deletes on completion. Expected starts: three (two
in Part A, one in Part C), six at worst, plus one for any Part A create whose
answer is lost and recovered by the backend's same-key re-`POST`; all inside
the included windows.

### Part A: `BoatBackend` directly, before registration (product plane)

This needs an Antiek checkout carrying `boat_backend.py`, with its `.venv`, in
the cloud CEO's environment. The script uses the `ExecutionBackend` interface
plus the Boat workspace's `sandbox_id` property, and the CLI only through `P`'s
key. It prints JSON lines and no secret.

```bash
cat > "$R/boat_smoke_a.py" <<'PY'
"""G3.2 Part A: BoatBackend directly (unregistered). JSON lines out; never a secret.

BoatBackend and the Boat CLI both read BOAT_API_KEY and ANTIEK_BOAT_ORG from the
environment; this script never prints them or puts them in argv.
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import time

from runtime.exec_backend.boat_backend import BoatBackend
from runtime.exec_backend.interface import (
    ALLOW_ALL,
    DENY_ALL,
    NetPolicyUnsupported,
    ResourceLimits,
    WorkspaceProfile,
)

BOAT = os.environ["BOAT"]
ORG = os.environ["ANTIEK_BOAT_ORG"]
if ORG != "team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3":
    sys.exit("STOP: ANTIEK_BOAT_ORG is not the Antiek team id")
LEDGER = os.environ["SMOKE_LEDGER"]
SMALL_USD_PER_H = 0.018
LIMITS = ResourceLimits(wall_clock_s=1200)  # 1.0 vCPU / 2,048 MB -> small; ttlSeconds 1200
OWNER_CHECK = (
    'echo "[${ANTHROPIC_API_KEY:+anthropic}${OPENAI_API_KEY:+openai}'
    '${CLAUDE_CODE_OAUTH_TOKEN:+claude}${GH_TOKEN:+gh}]"; '
    "ls ~/.git-credentials ~/.config/gh/hosts.yml "
    "~/.claude/.credentials.json ~/.codex/auth.json 2>&1; "
    # Boat wrote a keyless CLI config into both measured VMs: print its field names only.
    "echo \"boat-config-fields: $(tr -d ' \\t\\r\\n' < ~/.config/ascii/boat/config.json "
    "| grep -Eo '\"[^\"]+\":' | tr -d '\":' | sort | tr '\\n' ' ')\"; "
    "BOAT_NO_UPDATE=1 boat info --json 2>&1 | grep -Eo '\"status\":[[:space:]]*[0-9]+' | tail -n 1"
)


def emit(**fields):
    print(json.dumps(fields, sort_keys=True), flush=True)


def cli(*args):
    done = subprocess.run([BOAT, "--org", ORG, *args], capture_output=True, text=True, timeout=180)
    return done.returncode, done.stdout, done.stderr


def info(sid):
    rc, out, err = cli("info", sid, "--json")
    try:
        doc = json.loads(out or err)
    except ValueError:
        return {"rc": rc, "raw": (out or err).strip()[-200:]}
    box = doc.get("sandbox") or {}
    error = doc.get("error")
    code = doc.get("code") or (error.get("code") if isinstance(error, dict) else error)
    keep = ("name", "state", "health", "type", "ttlSeconds", "snapshots", "environment", "labels")
    return {"rc": rc, "code": code, "team": (box.get("team") or {}).get("id"),
            **{k: box.get(k) for k in keep}}


async def one(backend, label, policy):
    t_create = time.time()
    try:
        ws = await backend.create(WorkspaceProfile(name=f"g3-{label}"), limits=LIMITS, net_policy=policy)
    except NetPolicyUnsupported as exc:
        emit(step="create", policy=policy.kind.value, result="NetPolicyUnsupported", reason=str(exc)[:200])
        return
    sid = getattr(ws, "sandbox_id", "")
    with open(LEDGER, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"sandbox": sid, "workspace": ws.workspace_id, "created_at": t_create}) + "\n")
    emit(step="create", policy=policy.kind.value, sandbox=sid, workspace=ws.workspace_id,
         ready_s=round(time.time() - t_create, 1))
    try:
        emit(step="info", sandbox=sid, **info(sid))
        rc, out, _ = cli("exec", sid, OWNER_CHECK)
        emit(step="owner_credentials", rc=rc, out=out.strip()[-400:])
        rc, out, _ = cli("exec", sid, "id -u")
        emit(step="user_uid", rc=rc, out=out.strip()[-20:])
        fetch = "import urllib.request as u; print(u.urlopen('https://example.com', timeout=5).status)"
        for name, argv in (
            ("runner_uid", ["id", "-u"]),
            ("python3", ["python3", "--version"]),
            ("runner_sudo", ["sudo", "-n", "true"]),
            ("bashrc", ["sh", "-c", "test -r /home/user/.bashrc && echo readable || echo unreadable"]),
            ("egress", ["python3", "-c", fetch]),
        ):
            t = time.time()
            r = await ws.exec(argv, timeout_s=30)
            emit(step=name, exit=r.exit_code, out=r.stdout.strip()[:120], s=round(time.time() - t, 2))
        t = time.time()
        r = await ws.exec(["sleep", "30"], timeout_s=3)
        emit(step="timeout", timed_out=r.timed_out, exit=r.exit_code, s=round(time.time() - t, 1))
        await ws.put_file("in/smoke.txt", b"antiek-boat-smoke\n")
        r = await ws.exec(["sh", "-c", "cat ../in/smoke.txt > ../out/collected.txt"], timeout_s=30)
        collected = await ws.get_file("out/collected.txt")
        emit(step="collect", exit=r.exit_code, roundtrip=collected == b"antiek-boat-smoke\n")
        rc, out, _ = cli("usage", sid, "--json")
        emit(step="usage", rc=rc, out=out.strip()[-400:])
    finally:
        t = time.time()
        await ws.destroy()
        await ws.destroy()  # idempotent by contract (I6)
        t_deleted = time.time()
        emit(step="destroy", sandbox=sid, s=round(t_deleted - t, 1), lived_s=round(t_deleted - t_create, 1),
             list_price_bound_usd=round((t_deleted - t_create) / 3600 * SMALL_USD_PER_H, 5))
    emit(step="gone", sandbox=sid, **info(sid))


async def run(backend):
    await one(backend, "allow", ALLOW_ALL)
    await one(backend, "deny", DENY_ALL)


def main():
    # The backend's own log lines (probe state, created and deleted sandbox ids)
    # go to stderr; they carry ids, never the key. httpx request lines are muted.
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(levelname)s %(name)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    backend = BoatBackend()
    backend.probe()  # synchronous by contract (it calls asyncio.run): outside the event loop
    emit(step="probe", backend=backend.name)
    asyncio.run(run(backend))
    return 0


if __name__ == "__main__":
    sys.exit(main())
PY
cd "${ANTIEK_CHECKOUT:?set ANTIEK_CHECKOUT to the Antiek checkout carrying boat_backend.py and its .venv}"
export SMOKE_LEDGER="$R/g32a-ledger.jsonl"; : > "$SMOKE_LEDGER"
env -u BOAT_BUILD_API_KEY BOAT="$BOAT" PYTHONPATH="$PWD" .venv/bin/python "$R/boat_smoke_a.py" \
  2> >(tee "$R/g32a-backend.log" >&2) | tee "$R/g32a.jsonl"
```

`env -u BOAT_BUILD_API_KEY` keeps the build key out of the product process
altogether. `g32a-backend.log` keeps the backend's own lines, among them one
`BoatBackend sandbox accepted` line per sandbox Boat accepted and one
`BoatBackend sandbox deleted` line per confirmed delete; they carry ids and
shape-checked tokens, never the key. `boat info --json` answers with a `sandbox` object [M,
`pricing.md`]; `boat exec <id> '<command>'` is the documented check form [M,
`security.md`].

| Step | Expected | Fails the smoke if |
|---|---|---|
| `probe` | `backend: "boat"`, and on stderr `BoatBackend ready; wallet=team_50b5...; environment=antiek-product (passes nothing)` | it raises: read the message. A missing or refused key is G4's. An environment that passes credentials (`proxyAiCredentials` present and not `false` included, whatever `safeForThirdParties` says), a refused or incomplete `GET /environments` read, the environment's name listed twice, a `GET /limits` answer without `canStart`, or a pin mismatch is a stop. A WARNING that `GET /limits` is forbidden is decision §5 item 2: record it. `probe()` logs nothing about whether its environments read carried `proxyAiCredentials`; that live shape is G3.1 step 6's `proxyAiPresent` record (decision record §5 item 11) |
| `create` (allow) | a `bx_` sandbox id, a hex workspace id; `ready_s` is the first measured create-to-ready time | `BackendUnavailable` from the environments read before the create: the environment passes something and nothing was created (decision §5 item 1). `BackendUnavailable` naming a credential found inside the VM, a record that reports snapshots on, or a VM without `fs.protected_hardlinks = 1`: the backend deleted the sandbox, and `g32a-backend.log` has its accepted and deleted lines; record the message. `unknown_environment`: G4 is incomplete. A 403 such as `api_key_sandbox_forbidden`: the key cannot create even in its own environment. Each is a stop |
| `info` | `name` starts `antiek-ws-g3-allow-`; `type: "small"`; `ttlSeconds: 1200`; `snapshots: false`; `team` equal to `ANTIEK_BOAT_ORG`; `health: "ok"`; `environment: "antiek-product"` where the record carries it (the OpenAPI documents the field; the saved live shapes do not show it) | no TTL, `snapshots: true`, another team or another environment |
| `owner_credentials` | `[]`, then `No such file or directory` for each of the four files: the check Boat documents for a protected sandbox [M, `security.md`]; then `boat-config-fields: api_url channel` and `"status":401`, the keyless CLI config and the refused in-box CLI measured in a `noEnv` VM [M, ADR "Live evidence"; I for a safe environment] | any name inside the brackets, any of the four files present, any other config field, or an in-box `boat info` that is not 401: `antiek-product` passes something and the backend's own in-VM check missed it; the `finally` deletes; the smoke fails |
| `user_uid`, `runner_uid` | two different numbers, neither `0` | equal, or `0` |
| `python3` | exit 0, `Python 3.x` (the gather program needs it) | missing: G3.3 cannot pass |
| `runner_sudo` | non-zero exit | exit 0: the runner can sudo |
| `bashrc` | recorded as `readable` or `unreadable` | not a failure; it answers checklist line 2 (whether the runner can read `ASCII_TOKEN`) |
| `egress` (allow) | exit 0, `200` | |
| `timeout` | `timed_out: true`, `exit: -1`, `s` far below 30 | it waited 30 s: I1 is broken |
| any `exec` step | no exception | `ExecutionBackendError` naming `reap_failed`, `busy`, `no_lock` or "could not be taken back": the reap or an interrupted exec's cleanup was not confirmed and the workspace is unclean (decision record, "What `BoatBackend` does today"); the `finally` destroys it; record the message and stop |
| `collect` | `exit: 0`, `roundtrip: true` | false |
| `usage` | a bill for the sandbox (format not documented) | non-zero `rc`: record; the list-price bound stands |
| `destroy` | printed once after two calls; `lived_s` and `list_price_bound_usd` | an exception: I6 is broken |
| `gone` | a not-found answer (`rc` non-zero, a not-found `code`) where `info` had answered | `info` still answers: teardown failed; delete the id with `P delete <id> --yes --json` and record the failure |
| `create` (deny) | either `result: "NetPolicyUnsupported"` (the cascade join then cannot use Boat, G3.3 is skipped, and the product plane fails G3.2 as the decision's reconsider-if says), or a workspace whose `egress` exits non-zero while `info` still reads `health: "ok"` | `egress` exit 0, or `health: "degraded"` |

The `info` and `gone` pair keeps the teardown proof from being vacuous: the
key could see the sandbox before the delete, so its absence afterwards means
something. Cost: the sum of `list_price_bound_usd` (expected under USD 0.012)
and the `usage` bills, both under USD 0.10. Every `bx_` id of a `BoatBackend
sandbox accepted` line in `g32a-backend.log` must also have a `BoatBackend
sandbox deleted` line; an accepted id with no `destroy` step in `g32a.jsonl`
(a create that failed after Boat billed it) counts at its 1,200 s TTL in the
cost, and an accepted id with no deleted line fails the smoke until `P
delete <id> --yes --json` confirms it.

If every create fails with `BackendUnavailable` naming
`~/.config/ascii/boat/config.json (holds more than api_url and channel)`, a
Boat CLI or image update has probably added a keyless field. The check rests on
Boat never putting a credential under `api_url` or `channel`. **Stop**: create
nothing more, record the refusal message, and ask the owner. Looking inside a
VM to read the new field names would be a further paid create outside this
envelope; it needs the owner's separate written approval of its own
envelope (its credential, budget, TTL, ledger and teardown) before it runs.
The development probes of 2026-11-09 (decision record, "Live evidence")
grant no continuing permission, and the pattern in `boat_backend.py` is
widened only by the code lane after the owner rules.

### Part B: cross-plane creates are refused (no start when passing)

These are the only commands in this runbook that use a plane key outside its
wrapper, on purpose: each one aims a key at the other plane's environment, or
at no environment.

```bash
part_b() {
  _org_ok || return 2
  { [ -n "${BOAT_API_KEY:-}" ] && [ -n "${BOAT_BUILD_API_KEY:-}" ]; } || { echo "STOP: Part B needs both plane keys" >&2; return 2; }
  local f='{step:$s, code:(.code // .error.code // null), status:(.status // .error.status // null), id:(.id // .sandbox.id // null)}'
  env -u BOAT_BUILD_API_KEY "$BOAT" --org "$ORG_ID" new --environment antiek-build --type small --ttl 900 --json 2>&1 |
    jq -c --arg s product_into_build "$f" | tee -a "$R/g32b.jsonl"
  BOAT_API_KEY="$BOAT_BUILD_API_KEY" "$BOAT" --org "$ORG_ID" new --environment antiek-product --type small --ttl 900 --json 2>&1 |
    jq -c --arg s build_into_product "$f" | tee -a "$R/g32b.jsonl"
  BOAT_API_KEY="$BOAT_BUILD_API_KEY" "$BOAT" --org "$ORG_ID" new --no-env --type small --ttl 900 --json 2>&1 |
    jq -c --arg s build_no_env "$f" | tee -a "$R/g32b.jsonl"
}
part_b
```

None of the three can expose a credential: `antiek-build` and
`antiek-product` pass nothing at this point, and `--no-env` passes nothing [M,
`environments_access.md`]. Expected for the first two: a 403 (most likely
`api_key_sandbox_forbidden` [M, `api-keys_scopes.md`; the exact code for a
create is not documented]) and no `id`. If either returns an `id`, delete it
with the key that made it (`P delete <id> --yes --json` for the first,
`B delete <id> --yes --json` for the second), record it, and stop: G3.2 fails
on separation. The third is an observation, not a pass or fail. It shows
whether an environment-restricted key may still create a sandbox attached to
no environment (`noEnv`). The product code never does that (it names its
environment). If the build key can, its environment restriction does not
confine every create, and the decision record's "planes collide" trigger is
the place to weigh it. If it returns an `id`, delete it at once with `B
delete` and record it.

A fourth case is deliberately not attempted: a build-key create that names no
environment. It would resolve to `base` [M, OpenAPI], which passes the owner's
secrets, GitHub token and agent credentials, so a success would put them in a
VM. `B` makes that create impossible by pinning `antiek-build`, and the
decision record's checklist line 4 carries the residual.

### Part C: one build box (build plane)

```bash
part_c() {
  local id t0 t1 t2 del PACKING
  local BUILD_LEDGER=/opt/data/antiek/operations/boat-build-ledger.jsonl     # [A] location proposed
  printf '{"plane":"build","intent":"g3.2 part C","at":"%s"}\n' "$(date -u +%FT%TZ)" >> "$BUILD_LEDGER"
  t0=$(date +%s)
  id=$(B new --type small --ttl 1800 --json | jq -r 'select(.event == "ready") | .id' | head -n 1)
  t1=$(date +%s)
  case "$id" in
    bx_?*) ;;
    *) echo "STOP: the create returned no sandbox id; compare 'B list --all --json' with the ledger before anything else" >&2
       return 1 ;;
  esac
  printf '{"plane":"build","sandbox":"%s","type":"small","ttl":1800,"created_at":%s,"ready_s":%s}\n' "$id" "$t0" "$((t1 - t0))" >> "$BUILD_LEDGER"
  B info "$id" --json | jq -c '{step:"info", name:.sandbox.name, type:.sandbox.type, ttlSeconds:.sandbox.ttlSeconds,
    environment:.sandbox.environment, team:.sandbox.team.id, health:.sandbox.health}' | tee -a "$R/g32c.jsonl"
  B exec "$id" 'echo "[${ANTHROPIC_API_KEY:+anthropic}${OPENAI_API_KEY:+openai}${GH_TOKEN:+gh}]"; ls ~/.git-credentials ~/.config/gh/hosts.yml 2>&1; echo "boat-config-fields: $(tr -d " \t\r\n" < ~/.config/ascii/boat/config.json | grep -Eo "\"[^\"]+\":" | tr -d "\":" | sort | tr "\n" " ")"; BOAT_NO_UPDATE=1 boat info --json 2>&1 | grep -Eo "\"status\":[[:space:]]*[0-9]+" | tail -n 1' > "$R/g32c-credentials.txt"
  # The lane-host primitives: a slice capping the sum, a transient unit in it,
  # a refused duplicate unit name, and an exit record written by root.
  PACKING=$(cat <<'SH'
set -u
echo "systemd: $(systemctl --version | head -n 1)"
echo "controllers: $(cat /sys/fs/cgroup/cgroup.controllers)"
echo "nproc: $(nproc)"
printf '[Slice]\nMemoryMax=512M\nTasksMax=256\n' | sudo -n tee /run/systemd/system/lanes.slice > /dev/null
sudo -n systemctl daemon-reload
sudo -n install -d -m 0750 /run/lane-records
sudo -n systemd-run --quiet --unit=lane-g3-a --slice=lanes.slice -p MemoryMax=256M -p TasksMax=64 \
  -p 'ExecStopPost=/bin/sh -c "printenv SERVICE_RESULT EXIT_CODE EXIT_STATUS > /run/lane-records/lane-g3-a"' \
  /bin/sh -c 'sleep 15; exit 3' && echo unit-started
sudo -n systemd-run --quiet --unit=lane-g3-a --slice=lanes.slice /bin/true && echo DUPLICATE-ACCEPTED || echo duplicate-refused
echo "slice-memory-max: $(cat /sys/fs/cgroup/lanes.slice/memory.max)"
echo "unit-memory-max: $(cat /sys/fs/cgroup/lanes.slice/lane-g3-a.service/memory.max)"
sleep 17
echo "exit-record: $(sudo -n cat /run/lane-records/lane-g3-a | tr '\n' ' ')owner=$(sudo -n stat -c %U /run/lane-records/lane-g3-a)"
SH
)
  B exec "$id" --timeout 120 -- bash -c "$PACKING" > "$R/g32c-packing.txt" 2>&1
  B exec "$id" 'git clone --quiet --depth 1 https://github.com/Slimydog21/Antiek.git /tmp/antiek && git -C /tmp/antiek rev-parse --short HEAD' > "$R/g32c-collect.txt"
  B usage "$id" --json > "$R/g32c-usage.json"
  del=$(B delete "$id" --yes --json | jq -c '{step:"delete", ok}')
  t2=$(date +%s)
  printf '%s\n' "$del" | tee -a "$R/g32c.jsonl"
  case "$del" in
    *'"ok":true'*) printf '{"plane":"build","sandbox":"%s","destroyed_at":%s}\n' "$id" "$t2" >> "$BUILD_LEDGER" ;;
    *) echo "STOP: delete of $id not confirmed; it stays open in the ledger" >&2 ;;
  esac
  B info "$id" --json 2>&1 | jq -c '{step:"gone", code:(.code // .error.code // null), status:(.status // .error.status // null)}' | tee -a "$R/g32c.jsonl"
  awk -v s="$((t2 - t0))" 'BEGIN { printf "{\"step\":\"cost\",\"lived_s\":%d,\"list_price_bound_usd\":%.5f}\n", s, s / 3600 * 0.018 }' | tee -a "$R/g32c.jsonl"
}
part_c
```

The `select(.event == "ready") | .id` pattern is Boat's own, and so is
checking for an empty id before using it [M, `ci.md`]. Also documented:
`boat new --environment` [M, `security.md`], which `B` adds;
`boat exec <id> --timeout <s> -- bash -c ...` [M, `ci.md`];
`boat delete <id> --yes --json` [M, `ci.md`]; and `boat usage <id>` [M,
`pricing.md`]. `--json` on `usage` and the `ok` field of the delete answer
are [A]. Without `ok: true`, the box stays open in the ledger, so the spend
check and the reaper still see it.

| Output | Expected | Fails if |
|---|---|---|
| `info` | `type: "small"`, `ttlSeconds: 1800`, `environment: "antiek-build"`, `team` Antiek, `health: "ok"` | another environment or team |
| `g32c-credentials.txt` | `[]`, `No such file or directory` for each file, `boat-config-fields: api_url channel` and `"status":401` (the keyless CLI config measured in a `noEnv` VM [M, ADR "Live evidence"; I for `antiek-build`]) | any credential present, any other config field, or an in-box `boat info` that is not 401, while `antiek-build` should pass nothing |
| `g32c-packing.txt` | `systemd 254` or later [M: 255 on Ubuntu 24.04.4, the ADR's probe VM]; `controllers:` with `cpu`, `memory` and `pids`; `nproc: 2`; `unit-started`; `duplicate-refused`; `slice-memory-max: 536870912`; `unit-memory-max: 268435456`; `exit-record: exit-code exited 3 owner=root`. On Boat these are [A] until G3.2 runs. The same systemd calls, run by this lane as user units on systemd 262, gave the refusal, both `memory.max` values and `exit-code exited 3` [I] | no `memory` controller, `DUPLICATE-ACCEPTED`, a `memory.max` of `max`, or a missing exit record or one not owned by root: the packing primitives (decision record §2) fail on Boat; record it |
| `g32c-collect.txt` | a short commit hash of `Slimydog21/Antiek` | the clone fails: record (egress or git) |
| `delete`, `gone` | `ok: true`, then a not-found answer | the box still answers: delete again by id, record the failure |
| `cost` | `list_price_bound_usd` under USD 0.10 (expected under 0.009) | above it |

### After all three parts

```bash
P limits --json | jq -c '{step:"limits_after", activeSandboxes, vmHoursRemaining:(.planIncluded.vmHoursRemaining // null),
  wallet:(.wallet.balanceDollars // null), starts, present:{activeSandboxes:has("activeSandboxes"), starts:has("starts")}}' | tee -a "$R/g32a.jsonl"
```

Pass requires all of these:

- `activeSandboxes` is present in both this read and the G3.1 baseline, and
  equals the baseline (the research boxes unchanged).
- Where `starts` is present in both reads, the starts used rose by the number
  of accepted creates.
- A field absent from either read is recorded as unavailable, never as a
  pass.
- Every ledger id answered not-found after it had answered found. This
  teardown proof always applies.

If every ledger id is gone but `activeSandboxes` differs, the research boxes
are the likely cause. The owner checks them in the dashboard; nothing here
acts on them.

**The G3.2 receipt** is `$R`'s JSONL files and text files, summarized into the
PR as: sandbox ids and workspace ids; create-to-ready and per-step timings;
exit codes; cost (the `usage` bills where readable, the list-price bounds
always, and the included-hours and starts deltas with the research boxes'
share noted); and the teardown proof. It contains no key, no URL that carries
a token and no environment value.

---

## G3.3: the cascade through the factory (after G2)

Run this after the registration diff has merged and the owner has ratified.
It runs in a staging run of the service in the cloud CEO's environment, from
the same checkout as Part A [A: that the service runs in the CEO's 8 GB
container], and production waits for activation. If the owner names another
staging host instead (current owner policy permits Omarchy execution), that
host is added to the "Credentials" table before the key goes there. The
service's environment has `BOAT_API_KEY`, `ANTIEK_BOAT_ORG` and
`ANTIEK_EXEC_BACKEND=boat`, and does not have `BOAT_BUILD_API_KEY`.
`ANTIEK_DRW_GATHER` is unset or `stub`, because the route refuses `exa`
together with an exec backend (`cascade_routes.py:375-387`). The leaves get
the `ResourceLimits()` defaults: `small`, TTL 900 s (`contained_gather.py:241`,
`interface.py:122`).

1. `ANTIEK_EXEC_BACKEND=boat .venv/bin/python -c 'from runtime.exec_backend.factory import build_execution_backend as b; print(b().name)'`
   prints `boat` (`probe()` makes two read-only calls, `GET /limits` and `GET
   /environments`); with the variable unset it prints `local`.
2. Create a plan with exactly three reviewed, synthetic sub-questions (`POST
   /research/plans`), approve it (`/research/plans/{root_id}/approve`), give
   any spend approval the plan asks for, and launch it
   (`/research/plans/{root_id}/launch`), the way the Research UI does.
3. While it runs, `P list --json | jq '[.sandboxes[] | select(.name | startswith("antiek-ws-"))] | length'`
   reads 3: the leaves provisioned together, not one after another.
4. The service journal shows three `BoatBackend sandbox accepted:` lines
   (`via=create`), three `BoatBackend created workspace <workspace>
   (sandbox bx_... ...)` lines and three `contained gather complete:
   investigation=... backend=boat workspace=<workspace> passes=2
   ran_as_uid=...` lines (`contained_gather.py:308`); the workspace ids join
   them. The `bx_` ids of the accepted lines are G3.3's ledger; an accepted
   line without a created line is a billed provisioning failure and counts
   at its TTL.
5. Three notes were promoted through the funnel, and only through it (the
   graph query of `remote-exec-fanout.md` Step 4).
6. Each `bx_` id answers not-found from `P info <id> --json`, the journal shows
   a `BoatBackend sandbox deleted:` line for each accepted id, and the
   list-price bounds sum under USD 0.10 (at most USD 0.0135: three `small` at
   their 900 s TTL).

---

## Enable and activation

Activation is the owner's written go, dated and appended to the decision
record, never the presence of the CLI, of `ANTIEK_BOAT_ORG` or of a key.
Until a go names a plane, the swarm (cron `b413595fcdd5`) keeps Boat out of
its dispatch targets for that plane, and nothing selects Boat by default.
The activation gates the decision record's §5 keeps open (the mandatory org
pin, exact-environment enforcement, code-side per-plane cost and pacing
limits, the policy-versus-code TTL gap, env-scoped live acceptance) are
closed, or accepted by the owner in writing, before the plane they concern
is activated. The module's own sixth, the live `proxyAiCredentials` shape
(§5 item 11), closes earlier, before G2's registration, from G3.1 step 6's
record.

**Product plane**, after G3.3 and the owner's go, on whatever host is
production at the time (this runbook moves no host), mirroring
`remote-exec-fanout.md` Step 1:

```bash
sudoedit /etc/antiek/secrets.env
#   ANTIEK_EXEC_BACKEND=boat
#   ANTIEK_BOAT_ORG=team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3
#   BOAT_API_KEY=<typed or pasted by the owner in the editor>
chown root:antiek /etc/antiek/secrets.env
chmod 0640 /etc/antiek/secrets.env
systemctl restart antiek; sleep 2; systemctl is-active antiek
```

Never `BOAT_BUILD_API_KEY` on a production host. Leave
`ANTIEK_BOAT_ENVIRONMENT` unset (the code's default is `antiek-product`; it
refuses `antiek-build`). `ANTIEK_DRW_GATHER` must not be `exa`. The backend is built at each cascade launch, not at service start,
so launch one small cascade and read
`journalctl -u antiek -n 200 --no-pager | grep "ExecutionBackend selected"`:
expected `ExecutionBackend selected: boat (via $ANTIEK_EXEC_BACKEND='boat')`.

**Build plane**, only after all four of: Part C; the owner's explicit
ruling on the build plane under §16 (decision record, open sign-off 4: build
use as operator tooling outside §16, or §16 cover), recorded, with any
amendment that ruling requires (a build-plane carve-out, or a change to the
decision record's §6 block) ratified; the decision record's §5 activation
gates that concern the build plane (at least code-side cost and pacing
limits) closed or accepted by the owner in writing; and the owner's written
approval of the build envelope. Until all four, the build key creates
nothing outside G3.2 (Part B's two attempts and Part C). Then there is no switch. Work runs on Omarchy first and goes to Boat only for a
clean full VM, a production-shaped host, or more parallel lanes than Omarchy
holds, always through `B`, inside the build envelope, with ledger rows as in
Part C (an intent row before each create; an id row with `created_at`, `type`
and `ttl` after it; a `destroyed_at` row once the delete is confirmed). Swarms
fork one prepared box, one fork every 15 s, each fork `--ttl 7200` and in the
ledger [M for the fork pattern, `recipes_parallel-agents.md`]; a fork inherits
the source's `antiek-build` [M, OpenAPI fork]. No `boat prompt`, no AI-credentials proxy, no
`boat host`, no `runs-on: boat`.

---

## Ledgers and the reaper rule

**Product.** The code writes no file ledger. Its record is the journal on
logger `antiek.exec_backend.boat`: `BoatBackend sandbox accepted:
sandbox=<bx id> ...` for every sandbox Boat accepted (provisioning failures
and recovered lost creates included), `BoatBackend sandbox deleted:
sandbox=<bx id> ...` for every confirmed delete, and the unchanged
`BoatBackend created workspace <workspace> (sandbox <bx id> ...)` and
`BoatBackend deleted sandbox <bx id> (workspace <workspace>)`; plus each
sandbox's `antiek-workspace` label, and, for a smoke, its ledger file and
`g32a-backend.log`. **Build.** The build ledger in the CEO's
environment: an intent row before each create, the id row (with `type` and
`ttl`) after it, a `destroyed_at` row once the delete is confirmed. `boat new` from the CLI sends no
`Idempotency-Key` [A: not shown in the saved pages], so a failed CLI create is
never retried blindly; list by ledger time before trying again.

A plane's reaper deletes a sandbox only when all of these hold:

1. its id is in **that plane's** record (an accepted line or ledger row) with
   no matching delete;
2. its name carries that plane's prefix (`antiek-ws-` or `antiek-build-`), or,
   on the build plane where names cannot be set, its id is in the build ledger;
3. it is older than its create time plus its TTL plus 15 minutes, so its
   auto-stop has had its turn;
4. it is neither `bx_235rmpn3` nor `bx_35hs5p53`, which sit on a deny-list
   checked first.

It runs with its own plane's key, never an admin key; `delete-own` means a
plane key cannot delete what it did not create anyway [M,
`api-keys_scopes.md`], but the rule stands on the record, not on that. It
deletes and never stops, extends or resumes. It writes the outcome to the
record, and it reports, without touching, every sandbox under its prefix that
its record does not name. A prefix match or a label alone never authorizes a
delete, and neither does being visible in a listing.

---

## Fallback and disable

**Product plane.** There is no automatic fallback while
`ANTIEK_EXEC_BACKEND=boat` is set, by design: the factory refuses to downgrade
isolation silently (`factory.py` module docstring), so a Boat outage, an
exhausted wallet or a revoked key makes contained leaves fail loudly with
`BackendUnavailable` or `WorkspaceProvisionError`. To disable:

```bash
sudoedit /etc/antiek/secrets.env       # delete the ANTIEK_EXEC_BACKEND line
systemctl restart antiek; sleep 2; systemctl is-active antiek
```

With the variable unset, `_research_loop_factory` returns the stub gather
loop, or Exa when `ANTIEK_DRW_GATHER=exa` (`cascade_routes.py:402-404`), and
Antiek makes no Boat call. To stay contained without Boat, set
`ANTIEK_EXEC_BACKEND=docker` on a host with a daemon. In an emergency the
owner revokes the product key first; every Boat call then fails closed, and
reaping recorded ids afterwards needs a replacement key or the dashboard. A
sandbox whose delete failed stops at its auto-stop, and with snapshots off its
disk is erased then [M, OpenAPI].

**Build plane.** Stop issuing `B` commands, run the build reaper, and revoke
the build key if needed. Omarchy carries the build work alone again.

---

## Then and now

*Historical, before the owner's checkout at about 06:25Z on 2026-11-09.* The
personal trial allowed 2 sandboxes at once, a two-hour auto-stop at most and
25 h of compute [M, earlier orchestrator measurements carried in this lane's
facts], with 5 / 25 / 75 starts [M, `free-trial.md`]. Org Antiek read
`subscription_required` [M], because organizations get no trial [M,
`free-trial.md`].

*Now, as measured at about 06:27Z.* One `box_20` subscription on org Antiek:
`billingStatus` active, `accessTier` standard, `canStart` true, 100 at once,
555.56 included hours to 2026-12-09T06:25:35Z, 12 / 60 / 200 starts; the
research boxes moved into the organization with the personal plan and hold two
of the 100; the account's active wallet is Antiek [M]. Auto-stop may run to 30
days or off on this plan [M, `limits.md`].

---

## Never

- Touch `bx_235rmpn3` or `bx_35hs5p53`: no stop, extend, resume, fork, exec
  or delete.
- Put a Boat plane key in argv, a log, a receipt, a commit, a chat or a Boat
  environment's secrets, or on a host the "Credentials" table does not name.
- Copy a subscription credential or owner login (Omarchy's stored Boat CLI
  login, the owner's model or GitHub logins) into a Boat sandbox,
  environment or key.
- Create a diagnostic or probe VM outside a gate's envelope without the
  owner's separate written approval of its credential, budget, TTL, ledger
  and teardown; earlier development probes grant no continuing permission.
- Let one plane use the other's key, or let either fall back to a stored
  login; run `boat login` with a plane key.
- Use a plane key outside its wrapper (`P`, `B`) or `BoatBackend`. The only
  exceptions are the Part A script's read, exec and usage calls, G3.1 steps 0
  and 2, and the three deliberate attempts of G3.2 Part B. Never create with
  the build key without `--environment antiek-build`, which `B` adds.
- Use the organization admin key or the personal account key in automation.
- Change the account's active wallet; every command names the organization
  with `--org` instead.
- Create a sandbox in `base`, or a product sandbox outside `antiek-product`,
  without an auto-stop, with snapshots on, or stopped instead of deleted; set
  `ANTIEK_BOAT_ENVIRONMENT` to anything but `antiek-product`.
- Put any key from Antiek's `secrets.env` into either Boat environment.
- Use Boat integrated agents (`boat prompt`), the AI-credentials proxy or
  `boat host` for anything Antiek: dispatch stays Hermes-primary.
- Treat installed Boat as an eligible target for the swarm (cron
  `b413595fcdd5`) before the owner's written go, or let the swarm run a paid
  gate.
- Turn on auto top-up or invoiced extra starts, or turn off a product
  workspace's auto-stop, without the owner's go.
- Run anything here that touches `infrastructure/terraform-aws/`, the AWS
  cutover or the lane hosts.

## Companion docs

- `docs/decisions/boat-compute-backbone-2026-11-09.md`: the decision, the two
  planes, the 2026-10-07 clauses amended and left, the envelopes, the gates,
  the review checklist and the open owner sign-offs.
- `runtime/exec_backend/boat_backend.py`: the module docstring's
  "Activation (after ratification)" section holds the exact factory diff G2
  applies.
- `infrastructure/runbooks/remote-exec-fanout.md`: the `secrets.env` and
  restart idiom this runbook mirrors, and the graph query for promotions.
- `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md` and
  `infrastructure/runbooks/lane-host.md`: unchanged by this runbook.
