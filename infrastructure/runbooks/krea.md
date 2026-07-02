# Krea image generation — token, balance, wiring, rotation, kill switch

**Status: first-contact tooling restored against the #110 adapter as of
2026-07-02.** The current mainline substrate exposes the capped Krea
proxy and this runbook describes the no-key typed-fallback smoke used
before live activation. The live-key preflight remains section 5: the
rotation mandate written from the 2026-06-12 leak.

The substrate side already shipped: `interfaces/research/api/krea_routes.py`
is the secure broker — the browser only ever talks to `/krea/*`; the
server reads `KREA_API_TOKEN` at call time from its environment (locally
a manually-sourced `~/Desktop/Antiek/.env`, on prod
`/etc/antiek/secrets.env` via the systemd unit's `EnvironmentFile`).
The upstream/secret-store name may still be `KREA_API_KEY`, but every
Antiek runtime consumer aliases that value into `KREA_API_TOKEN`. With
no token wired, everything degrades gracefully after operator auth admits
the request: `/krea/*` answers a typed
`503 {"enabled": false, "reason": "no_key"}` and the UI keeps its
deterministic placeholder.

Prod-state honesty: a direct prod request without an accepted operator
credential returns the app-level `401 operator_auth_required` before the
Krea route runs. That is distinct from Krea graceful absence: once the
operator-auth middleware admits the request, an unset or blank
`KREA_API_TOKEN` returns typed 503 `reason: no_key`. Section 3 therefore
starts by checking the live file, never assuming.

Sections:

1. Mint a token
2. Fund the API balance — **the money step; separate from any subscription**
3. Wire the token (local + prod; alias `KREA_API_KEY` to `KREA_API_TOKEN`)
4. Verify with the capped smoke (and the plumbing it traverses)
5. Rotate a key — written from the 2026-06-12 leak
6. Emergency stop — kill switch FIRST
7. Cost table (current pricing, cited)

---

## 1 — Mint a token

Tokens are minted at <https://www.krea.ai/settings/api-tokens>
(docs: <https://docs.krea.ai/developers/api-keys-and-billing.md>).

1. Toggle to the correct **workspace** first — the token belongs to a
   workspace, and only workspace **owners and admins** can create one.
2. Create the token and name it datewise (e.g. `antiek-prod-2026-06`) so
   the rotation procedure in section 5 can tell old from new at a glance.
3. Copy the value once, paste it directly into the wiring step (section
   3), and nowhere else. **Never paste it into a chat, a ledger, a
   commit, or a command line that gets transcribed** — that exact move
   caused the 2026-06-12 leak (section 5).

Key format (observed from the 2026-06-12 leaked key; docs.krea.ai does
not document the format): an **`id:secret` pair** — two
machine-generated halves joined by a colon, shaped like

```
00000000-0000-0000-0000-000000000000:FAKE-FAKE-FAKE-FAKE-this-is-not-a-real-secret
```

(that example is obviously fake; both halves of a real one are
high-entropy). The colon matters for leak-sweeping: it makes the key
greppable as a shape, not just as a variable name — see section 5
step 6.

## 2 — Fund the API balance (the money step)

**The API bills from a PREPAID USD balance that is separate from any web
subscription's compute units.** A Pro/Max plan with thousands of compute
units still answers **HTTP 402** on every API call if this balance is
empty — the substrate surfaces that as the typed 503 reason
`no_api_balance`. Money for the API goes in exactly one place:

- Fund at <https://www.krea.ai/app/api> — only workspace **owners** can
  top up. Presets $10 / $25 / $50 / $100; custom amounts $5 minimum,
  $10,000 maximum. There is no API free tier.
  (Source: <https://docs.krea.ai/developers/api-keys-and-billing.md>.)
- Krea bills **completed jobs only** — "Failed and cancelled jobs are
  not billed" (same doc). Note the substrate's local daily cap counts
  submit-accepts instead, deliberately overcounting in the safe
  direction (see `krea_routes.py`'s billing-accounting comment).

For first contact, the $5–$10 range is plenty: the default model costs
$0.007/request (section 7), so even the full default daily cap (50
units) burns only ~$0.35/day.

## 3 — Wire the token

### Alias trap — `KREA_API_KEY` vs `KREA_API_TOKEN`

Krea and some secret stores use the natural name `KREA_API_KEY`. The
#110 adapter does **not** read that name; it reads only
`KREA_API_TOKEN`. Modal secret `krea-api-key` may hold an env var named
`KREA_API_KEY`, but deployment glue must export the same value to
`KREA_API_TOKEN` before starting Antiek. Never set both to different
values. If they diverge, rotate the key and rewrite the secret source of
truth before live smoke.

### Step 0 — check before assuming (prod)

You cannot know from a dev machine whether a token is already wired.
Check the live file first — this prints a **count, never the value**:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip> \
  "grep -c '^KREA_API_TOKEN=.' /etc/antiek/secrets.env"
# 1 → a token is already wired (you are ROTATING: use section 5)
# 0 → no token yet (continue below)
# grep: ...No such file → secrets.env missing; run the setup playbook first
```

### Local (dev Mac)

Append to `~/Desktop/Antiek/.env` (gitignored; **nothing auto-loads
it** — you source it manually):

```
KREA_API_TOKEN=<paste-token-here>
# Optional only if your local secret source is named like Krea's docs:
# KREA_API_KEY=<same-token>; export KREA_API_TOKEN="$KREA_API_KEY"
```

Then load it into the shell that starts the server:

```bash
cd ~/Desktop/Antiek
set -a; source .env; set +a
```

### Prod (Hetzner VM)

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
sudoedit /etc/antiek/secrets.env
```

Fill in the `KREA_API_TOKEN=` line. If the source secret arrives as
`KREA_API_KEY`, alias it into `KREA_API_TOKEN` in the unit environment
before the process starts; the adapter will not read `KREA_API_KEY`
directly. The ansible template ships the token line empty with the
optional knobs commented —
`infrastructure/ansible/templates/secrets.env.j2`; the playbook places
that template with `force: false` so a populated live file is never
overwritten: `infrastructure/ansible/playbooks/setup.yml:341-349`).
Then restart — systemd loads the file only at unit start
(`EnvironmentFile=` in `infrastructure/ansible/templates/antiek.service.j2:42`):

```bash
systemctl restart antiek
sleep 2
systemctl is-active antiek
```

The current #110 knobs are:

| Env var | Default / use |
|---|---|
| `KREA_API_TOKEN` | Required for live upstream calls; unset/blank returns typed 503 `no_key`. |
| `ANTIEK_KREA_BASE_URL` | Defaults to `https://api.krea.ai`; override only for proxying or upstream host changes. |
| `ANTIEK_KREA_MODEL_PATH` | Defaults to `bfl/flux-1-dev`; the model lives in the upstream URL path. |
| `KREA_POLL_BUDGET_S` | Defaults to `30`; max time `/krea/scene` waits for a submitted job before typed fallback. |
| `KREA_DAILY_UNIT_CAP` | Defaults to `50`; `tools/krea_smoke.py --serve` forces `3` unless you explicitly override. |
| `KREA_RATE_LIMIT_MAX` | Defaults to `6` per 60 seconds. |
| `KREA_CACHE_TTL_S` | Defaults to `3600`; warm identical scene-state hits are not billed. |
| `KREA_KILL_SWITCH` | Truthy value forces typed fallback before token/budget/rate checks. |

Leave optional knobs commented unless section 6 or 7 gives you a reason.

## 4 — Verify with the capped smoke

`tools/krea_smoke.py` encodes the whole first-contact procedure and is
**secret-safe by construction**: it never reads `KREA_API_TOKEN` (only
the server holds it), never prints any environment value, and strips
query strings from printed image URLs. `tests/test_krea_smoke.py` proves
all of that with stdout snapshots, not inspection. It is stdlib-only, so
it runs with any `python3` — no venv needed.

It calls `GET /krea/scene` twice with an identical scene-state: the
first call may bill **one** unit; the second must answer `cached: true`
(the de-bill proof). Exit codes: `0` live art verified · `3` typed
fallback (read the printed decision-table row) · `1` assertion failure
(e.g. the repeat re-billed) · `2` transport/auth error.

### Local

```bash
cd ~/Desktop/Antiek
set -a; source .env; set +a        # loads KREA_API_TOKEN for the server, silently
./.venv/bin/python tools/krea_smoke.py --serve
```

`--serve` spawns its own capped server on port 8000 — it forces
`KREA_DAILY_UNIT_CAP=3` into that subprocess's environment unless you
explicitly set the cap yourself (worst case 3 × $0.007 ≈ **$0.02**).
Don't use `--serve` while another local server holds the DuckDB lock;
in that case cap your own server instead:

```bash
KREA_DAILY_UNIT_CAP=3 ./.venv/bin/uvicorn interfaces.research.api.app:app --workers 1
# second terminal:
./.venv/bin/python tools/krea_smoke.py
```

### Prod (on-box; copy-paste, prints no secret)

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
export ANTIEK_OPERATOR_TOKEN="$(grep -m1 '^ANTIEK_OPERATOR_TOKEN=' /etc/antiek/secrets.env | cut -d= -f2-)"
cd /opt/antiek && python3 tools/krea_smoke.py --base-url https://api.antiek.ai
```

The `export` line loads the operator bearer via command substitution —
nothing is echoed; the smoke attaches it as the `Authorization` header
and scrubs it from every printed line. Going through
`https://api.antiek.ai` exercises the full prod path (Cloudflare Tunnel
→ Caddy → uvicorn); for edge-bypass debugging use
`--base-url http://127.0.0.1:8001` (uvicorn's prod port,
`infrastructure/ansible/group_vars/all.yml:72`).

When the run finishes, **close the loop at the dashboard**: open
<https://www.krea.ai/app/api> and confirm the balance moved by exactly
the number of fresh generations the script reported (it prints this
reminder itself).

### The plumbing the smoke traverses (verified in-tree 2026-06-12)

All citations are file:line in this repo — re-verify them rather than
trusting this list if the files have churned since:

- **Caddy edge allowlist** — `/krea*` is in the one-line `@api_routes`
  path matcher: `infrastructure/ansible/templates/Caddyfile.j2:46`.
  Drift is CI-guarded by `tests/test_caddy_allowlist_coverage.py`
  (a registered route missing from the allowlist fails CI).
- **Vite dev proxy** — `"/krea": "http://localhost:8000"` in
  `apps/reading/vite.config.ts:33`, so the dev browser is same-origin
  and never sees the token.
- **Operator auth, four prod paths** — middleware in
  `interfaces/research/api/app.py`: (1) Antiek session cookie
  `app.py:1260-1282`; (2) Cloudflare Access email header
  `app.py:1284-1291`; (3) Cloudflare Access service token
  `app.py:1293-1313`; (4) `Authorization: Bearer $ANTIEK_OPERATOR_TOKEN`
  `app.py:1315-1324`. **The smoke uses path 4** (bearer, sourced from
  the secrets file as above, never echoed). `/health` is auth-open by
  design (`app.py:1187-1201`), which is why the smoke's stage 0 needs no
  credential.
- **Secrets file → process env** — `EnvironmentFile={{ antiek_secrets_file }}`
  at `infrastructure/ansible/templates/antiek.service.j2:42`;
  `antiek_secrets_file` resolves to `/etc/antiek/secrets.env` at
  `infrastructure/ansible/group_vars/all.yml:57`.

## 5 — Rotate a key (mandatory before live activation)

**Why this section exists**: on 2026-06-12 a previously-used Krea key
(an `id:secret` pair) was found sitting in **plaintext in a spec run
ledger** (`~/specs/moomba-web-tailscale/.caffenagent/run-ledger.md:85` —
an "obviously fine" example command line, `KREA_API_KEY=<value> ...`,
pasted into a transcript). It was redacted the same day; **rotation is
still pending** and is SPR-08's preflight step zero. The failure class
is *secret in a transcript* — which is also why the smoke script in
section 4 is structurally unable to print one.

0. **If you suspect the key is being abused right now**: revoke it at
   <https://www.krea.ai/settings/api-tokens> immediately and/or flip the
   kill switch (section 6) — Krea art degrades to a placeholder, so
   unlike an LLM key (`secret-rotation.md`) there is **no uptime reason
   to keep a leaked key valid while you mint its replacement**. Then
   continue below.
1. **Mint the new key** (section 1). Datewise name.
2. **Wire it** — local `.env` and/or prod `secrets.env` (section 3),
   replacing the old value.
3. **Restart** the substrate (`systemctl restart antiek`; locally,
   restart your sourced shell + server).
4. **Verify** with the smoke (section 4). Expect a fresh `200` then
   `cached: true` — or `no_api_balance` if the balance is empty (fix at
   section 2; a 402 is money, not the key).
5. **Revoke the old key** at <https://www.krea.ai/settings/api-tokens>.
   Only now — after the new key is verified working.
6. **Sweep for plaintext copies.** This prints file **names** only,
   never values:

   ```bash
   grep -rIlE --exclude-dir=.git --exclude-dir=.venv --exclude-dir=node_modules \
     'KREA_API_(TOKEN|KEY)=[^[:space:]<#]{8}' \
     ~/Desktop/Antiek ~/specs ~/dev ~/.zsh_history 2>/dev/null
   ```

   (The `{8}` requires 8+ value characters, so placeholders like
   `<paste-token-here>` / `<REDACTED-...>`, empty template lines, and
   this runbook's own grep examples never false-positive.) The only
   acceptable hit is `~/Desktop/Antiek/.env` (the gitignored live
   copy). Every other hit is a leak: open it and replace the value
   with `<REDACTED-YYYY-MM-DD-rotated>`. Then a second pass for the old
   key pasted *without* the variable name — grep for the first 8
   characters of the **old key's id half** (the part before the colon;
   the id alone cannot authenticate, so this search string is safe to
   type):

   ```bash
    grep -rIl -F '<first-8-chars-of-old-key-id>' ~/Desktop/Antiek ~/specs ~/dev 2>/dev/null
   ```

   Type a **leading space** before that command (the block above ships
   one) so the key fragment stays out of shell history — needs bash
   `HISTCONTROL=ignorespace`/`ignoreboth` or zsh `setopt HIST_IGNORE_SPACE`.

**Scan-path reality (honest)**: this repo has **no in-repo secret
scanner** — no gitleaks/trufflehog config, no pre-commit hook, and none
of the workflows in `.github/workflows/` scan for secrets (verified
2026-06-12; CI deliberately runs pytest + boundary lints only).
Detection relies on the operator's **global** tooling: the `hardenx` CLI
(a triage layer over VizopsAI's `harden`, installed globally via
`uv tool`) run as a pre-ship reflex — `hardenx --strict ~/Desktop/Antiek`
— ideally paired with `gitleaks` for detection breadth (hardenx triages;
it does not widen detection). The `KREA_API_(TOKEN|KEY)=` pattern and
the `id:secret` shape above are what you hand whichever scanner you
point at this tree.

## 6 — Emergency stop (kill switch FIRST)

Spending must stop **now** (runaway loop, suspected abuse, surprise
bill). Do this, in this order:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
printf '\nKREA_KILL_SWITCH=1\n' >> /etc/antiek/secrets.env
systemctl restart antiek
```

Then, for spend that bypasses this server entirely, also revoke the key
at <https://www.krea.ai/settings/api-tokens> — that is the only
**restart-free** stop, because it kills the key upstream.

**Why the kill switch beats deleting the key** (do not "just remove the
token line" under stress):

- It is **additive** — appending one line cannot corrupt the other
  secrets in the file the way a stressed `sudoedit` of existing lines
  can.
- It is **key-independent and checked first**: the gate order in
  `krea_routes.py` (`_gate`) is kill-switch → no-key → budget → rate
  limit, so the switch wins even if a copy of the token survives
  somewhere you didn't think of (a duplicated line, a unit-file
  `Environment=`). Key *removal* only works if you find every copy —
  that is the restart-ordering/coverage risk the switch doesn't have.
- Honesty about the restart: **both** approaches need the
  `systemctl restart` for the process env to change (systemd reads
  `EnvironmentFile` at unit start). The switch's advantage is that the
  single restart lands deterministically in the off state.
- A restart alone is **not** a spend stop — the daily budget counter is
  process-local and **resets on restart** (documented at
  `krea_routes.py`'s `_BudgetState`).

Verify the stop: run the smoke (section 4) and expect
`503 reason: kill_switch`. Resume later by removing the line and
restarting; the typed fallback means the UI was showing its placeholder
the whole time, not errors.

## 7 — Cost table (current pricing)

Fetched 2026-06-12. Prices are Krea's fixed per-request API prices in
USD, drawn from the prepaid API balance (section 2). Re-check before
budget decisions — the citation is the source of truth, not this table.

| What | Price | Source |
|---|---|---|
| `bfl/flux-1-dev` (the default `ANTIEK_KREA_MODEL_PATH`) | **$0.007 / request** | <https://docs.krea.ai/api-reference/image/flux.md> |
| `krea/krea-2/medium` (named alternative path) | $0.03 / request | <https://docs.krea.ai/api-reference/krea/krea-2-medium.md> |
| Other catalog models (Flux $0.04, Flux 1.1 Pro $0.06, Imagen 4 $0.04, Nano Banana Pro $0.15 …) | varies | <https://www.krea.ai/features/api> (the per-model catalog the billing doc points at) |
| Capped smoke run (3-unit cap, section 4) | ≤ $0.021 | 3 × $0.007 |
| Default daily ceiling (`KREA_DAILY_UNIT_CAP=50`) | ≤ $0.35/day (≈ $10.50/mo) | 50 × $0.007 |
| Minimum top-up | $5 (presets $10/$25/$50/$100; max $10,000) | <https://docs.krea.ai/developers/api-keys-and-billing.md> |

Two budget facts worth keeping next to each other: a $5 minimum top-up
survives ≥ 14 maxed-out days at the default cap and model; and swapping
`ANTIEK_KREA_MODEL_PATH` changes unit economics — `krea-2/medium` is
~4.3× the default's price, so the same 50-unit cap means ~$1.50/day,
not $0.35. Billing semantics: Krea bills completed jobs only;
the substrate's cap counts submit-accepts (overcounting is the safe
direction for a runaway guard).

---

## Companion docs

- `interfaces/research/api/krea_routes.py` — the proxy: gate order,
  budget/cache derivations, reason vocabulary, doc-transcribed wire
  shapes (live verification pending SPR-08)
- `tools/krea_smoke.py` + `tests/test_krea_smoke.py` — the capped smoke
  and the tests that prove its secret-safety
- `apps/reading/.env.example` — the full KREA_* knob documentation
- `infrastructure/runbooks/secret-rotation.md` — the LLM-key rotation
  this section 5 deliberately diverges from (graceful fallback → revoke
  can come first)
- `infrastructure/runbooks/magic-link-auth.md` — the four-path auth
  middleware the smoke's bearer rides
- `infrastructure/SKILL.md` — production deployment manual
