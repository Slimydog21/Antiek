# Decision: Boat full VMs as Antiek's compute backbone, on a product plane and a build plane that share one bill and never a key

**Date:** 2026-11-09 (UTC)
**Status:** PROPOSED, awaiting the owner's ratification. Nothing in this record
is in force. Its CLAUDE.md §16 amendment (Decision §6) takes effect only at
gate G2, and activation on either plane needs the owner's written go after the
gates below. **This proposal neither authorizes nor executes the AWS
production migration** of `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md`,
and it **does not displace that record's lane-host arrangement for the peer
research tenants** (solcoa, volantis, inferact). The cloud CEO's review of
the first handoff (draft PR #3826) and its re-review of v2 (`d0b2e85aa`)
requested changes; this revision answers both ("Review of PR #3826 and round
2", with its "Round 3") and stays PROPOSED.
**Lane:** `boat-backbone-decision-20261109`: this record and
`infrastructure/runbooks/boat-backbone.md` only. The adapter
`runtime/exec_backend/boat_backend.py` belongs to the code lane and is
described here as it stands, uncommitted, in the working tree on `79b66b1`
(modified 17:38 +03 on 2026-11-09, SHA-256
`f05833d139260ae99994bff008a3903358a00b0fc2a137ab742263f1408df2f8`, beside
`tests/test_exec_backend_boat.py` at SHA-256
`1fb2d33aa553383dd9f4442d3b03239cc955d95d4a9d457223656bb4ab6f054a`, after the
round-2 fixes of the review's findings S1 to S3, D4 and D5, the
orchestrator's follow-up after round 2 and round 3's answers to the v2
re-review); if the code
changes before review, the code wins and this record follows.
**Coordination:** the cloud CEO owns review and the PR; its review of PR
#3826 says its manager record
`/opt/data/antiek/operations/boat-backbone-2026-11-09.json` records that (no
lane here read that record). The draft
PR is #3826 (https://github.com/Slimydog21/Antiek/pull/3826), whose head for
the first handoff is `21b0db5` on base `79b66b1`. The Beads peer run
`run_7f565b3db2e242189d71baf23037246f` (idempotency key
`boat-backbone-beads-20261109-ceo`) completed BLOCKED: it found no usable
canonical ledger, so there is no Beads id and no ledger was initialized [M,
the cloud CEO's review of PR #3826].
**Implements on ratification:** the runbook above; the factory registration
written out in `boat_backend.py`'s "Activation (after ratification)" section.
**Amends on ratification:** CLAUDE.md §16, by one added block (Decision §6);
and, for Antiek's own product and build planes only, three clauses of the
2026-10-07 record, each quoted with its section in Decision §3. This lane
edits neither file.
**Leaves unchanged:** `docs/decisions/s16-research-fanout-exemption.md`, and
every other clause of the 2026-10-07 record.

Evidence labels follow the 2026-10-07 record: **[M]** measured, **[I]**
inferred from measured facts, **[A]** assumed. [M] here means one of five
things: a read-only measurement the workflow orchestrator made on 2026-11-09
with Boat CLI 1.0.96 and the REST API, or in the cloud CEO's dashboard, and
passed to this lane as a verified fact (this lane ran no credentialed Boat call and read no key); a named Boat
documentation page saved from docs.boat.dev on 2026-11-09, cited by file name
(`pricing.md` is docs.boat.dev/pricing, and so on), or the OpenAPI contract
`boat-v1.yaml`, cited as "OpenAPI", which wins where the two disagree; or this
repository at `79b66b1` plus the uncommitted `boat_backend.py`; or a live run
the orchestrator made after the lanes, with its receipt ("Live evidence"); or
a statement in the cloud CEO's review of PR #3826, as its PR body captures
it, which this lane did not re-measure (cited as "the cloud CEO's review of
PR #3826"). Boat's comparisons with other vendors are Boat's own published
claims.

## Context

### Two kinds of compute that must never be confused

The **product plane** is compute inside the product. The `ExecutionBackend`
seam (`runtime/exec_backend/interface.py`) runs untrusted agent code in a
disposable workspace that touches the world only through `exec` and files,
and the cascade's browse loop already runs its gather step through that seam
whenever `ANTIEK_EXEC_BACKEND` is set (`interfaces/research/api/cascade_routes.py:388`,
`runtime/research_runner/contained_gather.py`) [M]. The **build plane** is
compute used to build Antiek: development boxes, production-shaped tests, CI
and the cloud CEO's coding-swarm lanes. A product workspace runs on behalf of
a user of Antiek; a build box runs on behalf of the people writing it. Mixing
them would let a build swarm spend the product's limits, let a product
workspace receive a developer's GitHub token, and make every cost line
ambiguous.

### Boat, as documented

A Boat sandbox is a whole Linux virtual machine with its own kernel, disk and
IP address; sandboxes share no disk and no processes; the `user` account has
passwordless `sudo`, so anyone with a shell is root in that VM [M,
`security.md`]. Every size runs Docker and systemd and exposes `/dev/kvm` [M,
`llms.txt`, `ci.md`]. Boat's snapshot page tells anyone who blocks egress to
reload an nftables `socket cgroupv2` rule whenever the agent restarts [M,
`snapshots_stop.md`], so the guest runs a cgroup v2 hierarchy [I]. Boat's CI
page names the Ubuntu 24.04 `wine64` path [M, `ci.md`], so the image is
Ubuntu 24.04 [I]. A small probe VM then measured Ubuntu 24.04.4, kernel 6.8,
systemd 255 on cgroup v2 [M, "Live evidence"].

Billing is per second while a sandbox runs; a stopped sandbox costs no
machine time [M, `pricing.md`]. `default` (4 vCPU, 8 GB) costs USD 0.036/h,
`small` (2/4) half that, `large` (8/16) twice that, and `xlarge` (16/32)
USD 0.20/h, the last only on the USD 100 plan or higher; no size has a GPU
[M, `pricing.md`]. Machines are in Germany, Finland and France only, and
"Snapshot copies can be stored outside the EU" [M, `security.md`]. Boat bills
no egress [M, `pricing.md`]. Auto-stop defaults to one hour after create or
resume, goes to 30 days on a paid plan, and can be turned off with
`--no-auto-stop` [M, `limits.md`, `long-running-tasks_auto-stop.md`]. A stop
removes the machine and keeps the disk for at least 14 days; there is no
pause, and memory is lost [M, `concepts.md`]. Snapshots are taken every minute
while a sandbox runs and at each stop, and a delete erases the sandbox with
its snapshots [M, `concepts.md`]. A create with `snapshots: false` captures
nothing in the background, and stopping it "erases its disk the way zero data
retention does" [M, OpenAPI `CreateSandboxRequest.snapshots`].

A command that waits for its result times out at 30 s by default and 600 s at
most; a detached command has no limit [M, `limits.md`]. Boat has no API
setting for network rules: outbound is open, and blocking it for untrusted
code means running that code as a separate Linux account and inserting
owner-match `iptables`/`ip6tables` rules at the top of `OUTPUT`, never on
`user`, whose packets carry Boat's tunnel; snapshots do not keep the rules [M,
`hosting_firewall.md`, `security.md`]. Create and fork accept an
`Idempotency-Key`, kept for 24 hours [M, `api_v1.md`]. Starts (create, fork,
resume) are never queued: above the included number a start is paid from the
wallet at USD 0.03 to 0.07, and above the maximum it fails with `429` [M,
`limits.md`].

### The Boat account on 2026-11-09

- **One subscription, on the organization.** The owner's checkout landed at
  about 06:25Z (the subscription's `periodEnd` is 2026-12-09T06:25:35Z). At
  about 06:27Z the orchestrator measured, through `GET /limits`, `boat org
  list` and `boat list`, one `box_20` subscription on org Antiek
  (`team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3`): `billingStatus` active,
  `accessTier` standard, `canStart` true, `maxActiveSandboxes` 100,
  `planIncluded.vmHours` 555.56, starts 200 a day, 60 an hour and 12 a minute
  [M]. The checkout moved the owner's personal plan and personal sandboxes
  into the organization, and **the account's active wallet is Antiek** [M].
- **The research boxes now bill to Antiek.** `bx_235rmpn3` ("pareta.ai") and
  `bx_35hs5p53` ("airspace.co") belong to the Boat Research session, show team
  Antiek and live in environment `base` [M]. They are neither product nor
  build. Nothing in this record or its runbook touches them. Their sizes were
  not measured.
- **One environment exists, and it passes everything.** Only `base`, the
  default, exists; it has `passSecrets`, `passAgentsCredentials` and
  `passGithub` true [M]. A sandbox created in it receives the owner's
  variables, GitHub token and model credentials [M, `environments_access.md`].
- **Organization keys cannot manage the account.** They get `403
  api_key_org_forbidden` on account settings (webhooks, AI credentials,
  billing, keys, members) and `403 api_key_org_mismatch` on a request that
  names another organization or Personal [M; `api-keys.md`].
- **Historical, before about 06:25Z.** Org Antiek read
  `subscription_required`, and the personal account was on the trial: 2
  sandboxes at once, a two-hour auto-stop maximum and 25 h of compute [M,
  earlier orchestrator measurements carried in this lane's facts], with 5 /
  25 / 75 starts, the trial's documented start limits [M, `free-trial.md`].
  None of this is current.

### The plane keys and environments, in progress

The owner is creating the environments `antiek-build` and `antiek-product`
and minting one `ci`-preset key per plane, restricted with `--env` to that
plane's environment, then pasting them into the cloud CEO [M]. Boat grants a
scoped key's request only when the action is on the key **and** the target
sandbox is in the key's sandbox set or one of its environments; the default
is deny [M, `api-keys_scopes.md`]. The presets are `read-only`, `full-sandbox`
(operate a sandbox without create, resume, fork, delete or account writes),
`ci` (`full-sandbox` plus create, resume, fork and `sandbox.delete-own`,
"delete the sandboxes this key created", with no account admin) and `admin`
(`*`) [M, `api-keys_scopes.md`]. `sandbox.delete-own` joined `ci` later, so
only a newly minted `ci` key has it [M, `api-keys_scopes.md`]. Three things
the saved pages and the OpenAPI do not say, and that G3.1 and G3.2 observe:
whether `ci` carries `account.read` (which `GET /limits` needs), whether it
carries `environment.read` (which `GET /environments` needs), and whether an
environment-restricted key may create outside its environment (for example
with `noEnv`, which attaches a sandbox to no environment [M, OpenAPI
`environment` field]). The Antiek organization key given in chat may read
environments but not write them: its `POST /environments` was refused with
403 `api_key_action_forbidden`, "This API key cannot perform
environment.write" [M, 08:24Z, "Live evidence"], so the owner creates both
plane environments.

### The cloud CEO and Omarchy

The cloud CEO is the Hermes Agent Cloud instance "Anti-Ek"
(`https://anti-ek-1699.agents.nousresearch.com`, `HERMES_HOME` `/opt/data`,
model `gpt-6.1-sol`, a local terminal in an 8 GB container). It installed Boat
CLI 1.0.96 at `/opt/data/.ascii/bin/boat` with Boat's official installer,
its onboarding step removed, and supplied the verified binary locally: the
GitHub release asset, its SHA-256 verified, because the boat.dev download
returned HTTP 504 [M; the installer use as the cloud CEO's review of PR
#3826 corrects it]. `ANTIEK_BOAT_ORG` is set in its environment;
`BOAT_API_KEY` and `BOAT_BUILD_API_KEY` are not yet [M]. Its hourly swarm,
cron `b413595fcdd5`, has no paid-compute or doctrine-change authority [M];
its prompt now carries an explicit owner-instruction Boat hold, with its
schedule and enabled state unchanged, and the staged `boat-backbone` skill
is not installed [M, the cloud CEO's review of PR #3826].

Omarchy, the owner's machine, has an Intel i9-9880H (16 threads), 15 GiB of
RAM, 237 GB of free disk and Docker, and hosts the `antiek-worker` gateway on
127.0.0.1:8643 behind Tailscale Funnel [M]. The owner's standing rules this
record follows: never print secrets, do not execute the AWS migration, and
flag any change to locked doctrine for the owner's sign-off [M]. **Omarchy
execution and host-owned credentials are permitted** under current owner
policy, as the cloud CEO's review in PR #3826 (Spec/doctrine finding 1) states
it [M, the cloud CEO's review of PR #3826], and the cloud CEO's SOUL says the
same in its section "Current instructions supersede historical deployment
assumptions": keeping every credential off Omarchy is no longer an accurate
deployment instruction, and current authorization permits Omarchy execution
[M, read by the orchestrator in the cloud CEO's dashboard on 2026-11-09]. This
record follows them and drops the blanket Omarchy rule its earlier drafts
repeated; only where the plane keys may be stored stays open (sign-off 5).
Three rules stay: no
subscription credential or owner login is copied into Boat (a sandbox, an
environment or a key); the Boat Research boxes `bx_235rmpn3` and
`bx_35hs5p53` stay excluded from everything here; and no Boat plane key
appears in argv, a log or a receipt.

### What `BoatBackend` does today

`runtime/exec_backend/boat_backend.py` is **dark**: `_VALID_KINDS` in
`factory.py:35` is `{"local", "docker"}`, so `ANTIEK_EXEC_BACKEND=boat` raises
`BackendUnavailable` ("unknown ExecutionBackend kind 'boat'"), the package
`__init__` does not re-export it, and no other module imports it [M, checked
hermetically on 2026-11-09]. What it does once constructed [M, read from the
module at `f05833d1`]:

- **Credentials.** It reads exactly one key, `BOAT_API_KEY`, at use time on
  every request, and sends it only in the `Authorization: Bearer` header; a
  missing or malformed key raises `BackendUnavailable` without echoing it, and
  Boat's error text loses it and every other key-shaped run. So does what a
  success answer puts in an exception or a WARNING: a `GET /limits` refusal,
  an environment's `proxyAiCredentials`, a sandbox record's team or
  environment, a failed state's error, and a command's exit code, status,
  stderr tail or parsed output (the `iptables` read-back, the credential and
  hardlink markers, the exec trailer). The current key and any key-shaped
  run become `[redacted]` before any cut, so no piece of a key survives a
  cut, and a message about a sandbox record names the sandbox id the create
  answer gave, which was checked, never the record's own `id`. It reads no
  `BOAT_BUILD_API_KEY` and has no fallback to any other credential. `BOAT_API_URL` overrides the base URL
  (default `https://boat.dev/api/v1`, `https` only except loopback).
- **Environment.** `ANTIEK_BOAT_ENVIRONMENT` names the environment product
  workspaces are created in, default `antiek-product`; the name is validated,
  and `antiek-build` is refused with `BackendUnavailable`.
- **Org pin.** `ANTIEK_BOAT_ORG` is optional in code; when set it must be a
  `team_...` id (a name is refused). It is sent as `X-Boat-Org` on `GET
  /limits`, `POST /sandboxes` and `GET /sandboxes`, and as `?org=` on `GET
  /environments`, and it is verified twice: `probe()` compares `GET /limits`
  `teamId` with it (when the key may read `GET /limits`), and `create()`
  compares the new sandbox's `team.id` with
  it, deleting the sandbox on a mismatch or when no read of it carried `team`.
- **`probe()`** is synchronous (`asyncio.run`) and makes two reads. `GET
  /limits` must carry `canStart: true` (and match the pin); an answer with no
  boolean `canStart` is refused as shape drift, and a scope `403`
  (`api_key_action_forbidden` or `api_key_sandbox_forbidden`) on this read
  alone is logged as a WARNING and left to the per-create org checks. `GET
  /environments` must list the product environment passing nothing: it
  refuses an environment that is not *Safe for third parties* while any of
  `passGithub`, `passSecrets`, `passSandboxCredentials`,
  `passAgentsCredentials` is not off, and, whatever `safeForThirdParties`
  says, one whose `proxyAiCredentials` is present and not the boolean
  `false` (`true`, `null` or a string; review finding S1). An environment
  without `proxyAiCredentials` is accepted on that field, because the OpenAPI
  `SandboxEnvironment` lists the four `pass*` flags as required and not it;
  the module names capturing a live environments shape as an activation
  gate (Decision §5 item 11). It reads flags only, never `envContents`.
  This read **fails closed**: a scope `403` on it, the environment missing from the listing,
  or its name listed more than once, raises `BackendUnavailable`, as does any
  other refusal. The `BoatBackend ready` line logs only the org id, machine
  type names and counts, each checked for its shape.
- **Create.** Before `POST /sandboxes`, every create repeats the fail-closed
  `GET /environments` check, so a product environment that passes anything
  is refused before anything is billed. The body is: the smallest machine
  type covering `cpu_cores`, `memory_mb` and `disk_mb` (the `ResourceLimits`
  defaults of 1.0 / 2,048 MB / 2,048 MB give `small`); `ttlSeconds` = `wall_clock_s` clamped to 60 s .. 30
  days (default 900 s), so auto-stop is never off; `environment` as above;
  `snapshots: false` on every create, with no constructor override (passing
  `snapshots=` raises `TypeError`; review finding D5); `visibility: "private"`; the
  name `antiek-ws-<profile slug>-<first 8 hex of the workspace id>`; labels
  `antiek-workspace=<workspace id>` and `antiek-profile=<slug>`; and the header
  `Idempotency-Key: antiek-ws-<workspace id>`. **`noEnv` is deliberately not
  sent**, because a `noEnv` sandbox is attached to no environment and would
  fall outside a key limited with `--env`; protection rests on the environment
  passing nothing, which Boat says is "exactly like `noEnv`" [M, OpenAPI]. The
  workspace id is a fresh UUID hex; the Boat id (`bx_...`) is the workspace's
  `sandbox_id` property, which is not part of the `Workspace` protocol.
- **Record and in-VM checks.** After the create and again at readiness it
  refuses a sandbox record that names another `environment`, says
  `holdsCreatorLogins: true`, or carries `snapshots` with any value but
  `false`, and it refuses a sandbox when neither record carries `snapshots`
  at all, since snapshots off could then not be verified (the OpenAPI does
  not require the field; both live `Sandbox` shapes carry it [M,
  `LIVE_SHAPES.md`]). Its provisioning command then runs Boat's own
  documented check inside the VM: none of `~/.git-credentials`,
  `~/.config/gh/hosts.yml`, `~/.claude/.credentials.json` or
  `~/.codex/auth.json` may exist; `~/.config/ascii/boat/config.json`, which
  Boat wrote into both measured `noEnv` VMs, may hold only `api_url` and
  `channel` (the keyless shape measured there, "Live evidence", and inferred
  for a safe environment [I]; a symlink, a path that is not a readable
  regular file, any other field or a key-shaped string is a credential); and none of `OPENAI_API_KEY`,
  `ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`, `CHATGPT_ACCOUNT_ID`,
  `GH_TOKEN`, `GITHUB_TOKEN` may be set, reporting names only. The same
  command checks that the kernel protects hardlinks
  (`fs.protected_hardlinks = 1`) and refuses a VM without it. The in-VM check
  is a spot check of the names the docs list; only the environment-flag
  check covers secrets whose names the owner chose. Any failure deletes the
  sandbox and raises `BackendUnavailable`.
- **Provisioning and exec.** It creates a system account `antiek-runner` with
  no sudo and no home, and a workspace root under `/tmp/antiek-ws/` with a
  control dir `<id>.ctl/` for the exec lock and the fence files. Every `exec`
  sends one wrapper that takes the VM's exec lock (`flock` on
  `<id>.ctl/lock`, waiting at most 5 s before refusing `busy`), runs nothing
  if its fence file `<nonce>.cancel` exists, and reaps every `antiek-runner`
  process before the workload starts: an unconfirmed reap refuses the
  workload (`_reap || _fin reap_failed`). It runs the argv as
  `antiek-runner` under `env -i`, `setsid` and `timeout` with a 5 s kill
  grace, synchronously when `timeout_s` is at most 580 s (`ceil(timeout_s)` +
  5 s kill grace + 15 s of wrapper slack fits Boat's 600 s cap) and detached
  with polling above that; output is capped at the seam's 2 MiB per stream.
  After every `exec`, whether the workload exited or timed out, it tries to
  kill every remaining `antiek-runner` process, give the tree back to `user`
  and strip group and other write and the set-id bits, and it does so before
  it returns or propagates an uncertain outcome. A confirmed cleanup
  establishes termination and restoration (I7). An unconfirmed one claims no
  termination: the workspace stays unclean, every later workload and file
  call is refused until a restoration is confirmed, and `destroy()` stays
  available.
- **The reap fails closed (review finding S2).** `pkill` runs inside `sudo -n
  sh -c '...; echo rc=$?'`, so only `pkill`'s own exit 1 for both selectors
  (`-U` and `-u`) counts as "none matched", and exit 0 repeats the round.
  Exit 2 or 3, 127, 128+n, no status at all (sudo refused), or a process
  still found after 50 rounds 0.1 s apart leaves the reap unconfirmed.
- **An interrupted exec is cleaned up (review finding S3).** After a lost
  answer (a 5xx, or a transport failure once the request may have left), a
  success answer without the wrapper's trailer (on either dispatch path), or
  a cancellation, the `exec` runs a shielded cleanup before it releases the
  workspace lock. For a detached command whose `processId` is known it first
  sends `DELETE /commands/{processId}`. The cleanup command then writes the
  fence file of every interrupted exec, reaps while it waits for the VM's
  exec lock (up to 200 rounds, each a reap and 0.1 s), and, holding the
  lock, reaps and restores. Only a cleanup that got the lock and confirmed
  both counts. A cancellation that lands during the cleanup returns at once
  while the cleanup carries on, and the next call waits for it. A command Boat refused with a
  4xx, or one that never connected, gets no cleanup.
- **Unclean workspace.** An `exec` that ends without confirming its reap and
  restore (a trailer whose clean flag is 0, a refused start, a lost or
  trailerless answer whose immediate cleanup was not confirmed) marks the
  workspace unclean. Every later `exec`,
  `put_file` or `get_file` first re-runs the cleanup and is refused
  (`ExecutionBackendError`, "could not be taken back") until one is
  confirmed; if the sandbox has vanished meanwhile, each raises
  `WorkspaceLost` and sends no wrapper. The module never destroys a
  workspace on its own (I6: the caller owns `destroy()`, which works on an
  unclean workspace). One workspace serves one `exec`, `put_file` or
  `get_file` at a time, under a per-workspace lock. It never retries a
  command.
- **Net policy (I4).** `DENY_ALL` inserts an owner REJECT for the runner's uid
  at the top of `OUTPUT` in both `iptables` and `ip6tables`, with no loopback
  or established-traffic exception (tighter than Boat's recipe), reads the
  rules back, checks that no rule blocks `user` and that the runner cannot
  sudo, and re-checks the first rule before every `exec`; any failure deletes
  the sandbox and raises `NetPolicyUnsupported`. `ALLOWLIST` is refused before
  any network call.
- **Teardown.** `destroy()` sends `DELETE /sandboxes/{id}` with
  `X-Ascii-Confirm-Delete`, is idempotent, never raises, and logs a failed
  delete loudly; any failure or cancellation during create deletes what was
  made, shielded from a second cancellation. A create whose answer was lost
  (a 5xx, a connection dropped after the request went out, a cancellation in
  flight) is recovered by re-sending the same `POST` with the same
  `Idempotency-Key`, which returns the sandbox bound to that key (up to three
  tries while Boat answers `409 idempotency_in_progress`), and deleting it;
  if the first request never reached Boat, that re-`POST` may itself create
  the sandbox, at the cost of one start. A label sweep follows as a second
  net, deleting only a sandbox carrying this workspace's label whose `access`
  is `owner`. It writes no file ledger.
- **Spend ledger lines (review finding D4).** On logger
  `antiek.exec_backend.boat`, at INFO: `BoatBackend sandbox accepted:
  sandbox=<bx id> workspace=<id> type=<machine type> ttlSeconds=<n>
  createdAt=<time> via=<create|repost|sweep>` once per sandbox id the
  process learns through the create or a recovery, the moment it learns
  it (an unidentified or unlogged create stays possible, Decision §7), so a
  sandbox that then fails
  provisioning, or that the re-`POST` or the label sweep recovers after a
  lost answer, is on it; `BoatBackend sandbox deleted: sandbox=<bx id>
  workspace=<id> via=<destroy|orphan> result=<deleted|not-found>` once per
  confirmed delete; and, unchanged, `BoatBackend created workspace
  <workspace id> (sandbox <bx id> ..., type=..., ttl=...s, environment=...,
  ...)` for a fully provisioned workspace only, and `BoatBackend deleted
  sandbox <bx id> (workspace <workspace id>)` when `destroy()` deletes. The
  accepted line carries Boat's type and TTL when the record carries them in
  the right type, the requested ones otherwise, and Boat's `createdAt`. Each
  value is checked for its own shape before it is logged (a machine type
  name, an integer, an RFC 3339 date-time) and logged as `unknown`
  otherwise, as is any key-shaped value or one holding the current key.

The module's own "Where the docs are silent" section names the gaps it
handles: combining `noEnv` with `environment`; the `ci` preset's reads (a
scope refusal of `GET /limits` is tolerated, one of `GET /environments` is
fatal); `GET /limits` without the required `canStart`, refused as shape
drift; `environments_access.md`'s `effective` field, which the OpenAPI
`SandboxEnvironment` lacks, so the documented rule is applied to the flags;
whether live environments listings carry `proxyAiCredentials` (an absent
field is accepted; capturing a live shape is an activation gate, Decision
§5 item 11); whether
one listing can hold two environments of one name (refused); how long Boat
holds an `Idempotency-Key` after a failed create; whether `pkill` matches
zombie processes (an unfinished reap is unconfirmed); whether `DELETE
/commands/{processId}` reaches a workload that `setsid` moved into its own
session, and whether a synchronous command keeps running after its answer
was lost (neither is relied on: the reap and the fence files are); and
whether live sandbox records carry `environment` and `holdsCreatorLogins`
(the OpenAPI documents both; the saved live shapes show neither, so each is
checked when present and the in-VM check always runs). It also records that
"Every command and its output are kept 90 days in the command history" [M,
OpenAPI `POST /sandboxes/{sandboxId}/commands`]. The code lane's
`tests/test_exec_backend_boat.py` is present, uncommitted, beside it.

### The 2026-10-07 argument this proposal has to answer

That record chose Antiek-owned AWS lane hosts over sandbox vendors as the
agent-CPU backbone for the peer research tenants. Its numbers [M,
`infrastructure/terraform-aws/README.md` cost table]: an r8g.xlarge (4 vCPU,
32 GiB) at USD 0.25058/h is USD 201.62 a month all-in at 24x7 on-demand
(instance, EBS, public IPv4) or USD 139.09 on a 1-year EC2 Instance Savings
Plan; about 24 lanes fit under a `lanes.slice` with MemoryMax 26G, so a
lane-month costs USD 8.40 on-demand or USD 5.80 on the plan, against about
USD 24.5 on Prime and USD 30.5 on Modal Sandboxes; idle stop brings the host
to USD 108.33 at 50% uptime and USD 61.69 at 25%, because EBS keeps billing.
Lanes measured 0.5 to 1 GiB each, under swap pressure [M, 2026-10-07
Context].

### The two execution seams

`ExecutionBackend` is the lower seam: `exec` and files, with no streaming and
no steering. Its invariants are a mandatory `exec` timeout with capped output
(I1), no host writer in the package (I2, held by the grep in
`tests/test_exec_backend_interface.py:115`), single-writer ingest outside
(I3), a declared net policy that a backend enforces or refuses (I4), no SDK
types in signatures (I5), idempotent `destroy()` (I6) and no shared process
pool (I7) [M]. The cascade joins it at the browse loop: `_research_loop_factory`
(`cascade_routes.py:341`) builds the backend and returns
`make_contained_gather_loop`, which declares `DENY_ALL` by default
(`contained_gather.py:216`) and returns results only as `StepEvent`s through
`HostLocalRunner` to `on_emit=funnel.submit`, so the promotion funnel stays
the one graph writer (`tests/test_cascade_exec_backend_wiring.py:425`,
`TestSingleWriterPreserved`); the route refuses `ANTIEK_EXEC_BACKEND` together
with `ANTIEK_DRW_GATHER=exa` (`cascade_routes.py:375-387`) [M]. What reaches
the workspace today is the placeholder `GATHER_PROGRAM`, which performs no
retrieval [M, `contained_gather.py`].

`RemoteExecProvider` is the upper, research fan-out seam: it must stream
events out of a live in-sandbox loop and relay steering into it. Its one
implementation, `DaytonaProvider`, names an in-sandbox leaf `python -m
antiek.remote.research_leaf` (`runtime/remote_exec/daytona.py:111`) that does
not exist in this tree, so its `run` raises; the registry is pinned to
Daytona by `tests/test_remote_exec_provider_registry.py`; and the research
fan-out exemption lists "a second remote-exec provider" as out of scope [M].
A Boat backend behind `ExecutionBackend` is therefore outside every §16
carve-out ratified so far.

## Decision

### 1. Boat full VMs are the backbone of both planes; the planes share one bill and nothing else

| | PRODUCT plane | BUILD plane |
|---|---|---|
| Purpose | Boat as compute inside the Antiek product: `BoatBackend` workspaces behind `ExecutionBackend` | Boxes for building Antiek: development, production-shaped tests, CI, the CEO's coding-swarm lanes |
| Billing | the one `box_20` subscription of org Antiek | the same subscription |
| Boat environment | `antiek-product`, *Safe for third parties* on, `proxyAiCredentials` off | `antiek-build`, with GitHub, secrets, Boat credentials and agent credentials all off until the owner's D-18 ruling (PROPOSED) |
| Key | `BOAT_API_KEY`: owner-minted `ci`-preset organization key, `--env antiek-product` | `BOAT_BUILD_API_KEY`: owner-minted `ci`-preset organization key, `--env antiek-build` |
| Selected by | `ANTIEK_BOAT_ENVIRONMENT`, default `antiek-product`; the code refuses `antiek-build` | the runbook's build wrapper `B`, which adds `--environment antiek-build` to every `new` and refuses any environment flag; forks and resumes inherit their source's environment [M, OpenAPI fork `environment`; I for resume]. Using the build key outside `B` is forbidden, except G3.1 step 2's read and G3.2 Part B's two deliberate attempts |
| Organization | `ANTIEK_BOAT_ORG` = `team_50b5a1d3-82bd-433e-b203-4f0f7fd3adb3`, read and verified by `BoatBackend` | the same value, checked by the wrapper and passed as `--org` on every CLI call |
| Read by | `BoatBackend`, which reads no other key | the runbook's build wrapper, which reads no other key and refuses to run when the key is unset or `ANTIEK_BOAT_ORG` is not the team id |
| Names | `antiek-ws-*`, labels `antiek-workspace` and `antiek-profile` (the code's own) | `antiek-build-*` where the CLI can set a name [A], and the build ledger in every case |
| First tier | none: a workspace is contained on Boat or refused | Omarchy, at no marginal cost, and the only tier for lanes that need the owner's subscription logins |
| Key lives in | the cloud CEO's environment for the gates; at enable, also the production host's `/etc/antiek/secrets.env` | the cloud CEO's environment only |
| Governed by | CLAUDE.md §16 as amended (Decision §6) and the product envelope (Decision §7) | the build envelope (Decision §7) and the owner's approval; operator tooling outside §16, for the owner to confirm |

Both keys must resolve to `ANTIEK_BOAT_ORG`. **There is no credential
fallback between planes, ever**: product code reads only `BOAT_API_KEY`;
build tooling reads only `BOAT_BUILD_API_KEY` and stops when it is unset,
rather than letting the CLI fall back to `BOAT_API_KEY` or a stored login; and
the two key values must differ (G3.1 compares them without printing either).
The unscoped organization admin key and the personal account key stay with
the owner and are never installed where an agent runs.

The separation holds for credentials, environments and names. It does not
hold for limits: both planes and the research boxes draw on the same 100
active sandboxes, the same 12 / 60 / 200 starts, the same 555.56 included
hours and the same wallet [M]. Boat's per-member caps cannot split them,
because both plane keys belong to the same member, the owner, who mints them
[I, from `limits.md` `member_limit_reached` and `team_member_cap_reached`,
which cap a member, not a key]. Decision §7 therefore
divides the windows by policy, and "What would change this" names the point
at which the build plane moves to its own organization.

**Installed is not activated.** Boat CLI 1.0.96 in the cloud CEO's
environment, `ANTIEK_BOAT_ORG` set there, and later two keys beside it make
Boat reachable and nothing more. Until the owner approves activation in
writing (product plane: G1 to G3.3 closed, the open activation gates of
Decision §5 that concern it closed or accepted in writing, item 10 only by
passing G3.2 Parts A and B, and the owner's go; build plane: G3.2 Parts B and C passed,
the owner's explicit ruling on the build plane under §16 (open sign-off
4), any amendment that ruling requires ratified with the other doctrine
rulings of G2, the Decision §5 activation gates that concern the build
plane (at least code-side cost and pacing limits) closed or accepted in
writing, and then the owner's approval of the build envelope after the
build smoke; Decision §5 "Prerequisites by gate" holds both lists), **the cloud
CEO's hourly swarm, cron `b413595fcdd5`, does not treat installed Boat as a
dispatch target on either plane**, and nothing selects Boat by default. The
test of eligibility is that recorded approval, never the presence of the
binary, of `ANTIEK_BOAT_ORG` or of a key. Because the swarm has no
paid-compute authority [M], it also never runs G3.2 or G3.3.

### 2. The 2026-10-07 argument, answered on its own terms

That argument was never against virtual machines. It was that per-sandbox
metering bills the wait, while a packed host divides one machine's price
across about 24 waiting lanes. Boat bills the wait too: a running sandbox
costs the same each second whatever its CPU does, and Boat says so [M,
`pricing.md`, "boat has one price per size, per hour"]. What changes is that a
Boat sandbox is the same kind of object as a lane host, a whole Linux VM with
root and systemd, so the lane-host pattern (one slice capping the sum, one
transient unit per lane, a root-written exit record, a duplicate unit name
refused) can run inside it [I]. G3.2 Part C checks those systemd primitives
on one `small` box: a slice with `MemoryMax`, a transient unit inside it, a
refused duplicate unit name and a root-written exit record. It does not run
compute's own lane-host helper and does not measure how many lanes fit.
Packing survives the move; the price of the box is what moves.

| 24x7, 730 h | vCPU / RAM | USD / month | USD per GiB-month | Lanes at 0.75 per GiB | USD per lane-month | vs lane host on-demand | vs lane host 1-yr plan |
|---|---|---|---|---|---|---|---|
| Lane host r8g.xlarge, all-in, on-demand [M] | 4 / 32 GiB | 201.62 | 6.30 | 24 | 8.40 | 1.00 | 1.45 |
| Lane host, 1-yr EC2 Instance Savings Plan [M] | 4 / 32 GiB | 139.09 | 4.35 | 24 | 5.80 | 0.69 | 1.00 |
| 4 x Boat `default`, packed [I] | 16 / 32 GB | 105.12 | 3.29 | 24 | 4.38 | 0.52 | 0.76 |
| 1 x Boat `xlarge`, packed [I] (needs the USD 100 plan) | 16 / 32 GB | 146.00 | 4.56 | 24 | 6.08 | 0.72 | 1.05 |
| 24 x Boat `small`, one lane per VM [I] | 48 / 96 GB | 315.36 | 3.29 | 24 | 13.14 | 1.56 | 2.27 |

`small`, `default` and `large` all cost USD 3.29 per GB-month (USD 0.0045 per
GB-hour) against the lane host's USD 0.00863 per GiB-hour on-demand and
USD 0.00595 on the plan [I]. Because plan dollars come back as VM time at list
price [M, `pricing.md`, "It is not a fee"], the marginal cost of Boat time is
the list price whether it is drawn from included hours or from the wallet [I].
On `box_20`, four `default` VMs at 24x7 use 2,920 default-hours: 555.56
included and 2,364.44 from the wallet at USD 0.036, USD 85.12, for USD 105.12
in all, assuming nothing else drew on the included hours [I]. At 50% and 25%
uptime the four cost USD 52.56 and 26.28, where the lane host costs USD 108.33
and 61.69, because a stopped Boat sandbox costs no machine time and its disk
is kept at no charge, while the stopped lane host keeps paying USD 15.05 a
month of EBS [M prices, I sums; README].

The assumptions carry the conclusion, so they are stated. Lanes are taken at
the 2026-10-07 density of 24 per 32 GiB (0.75 per GiB), from a footprint that
record itself calls unreconciled [A]. Six lanes per 8 GB VM ignores the OS,
Docker and Boat-agent overhead that four VMs pay four times and one host pays
once [A, unmeasured]. Boat publishes "GB" and AWS bills GiB; if Boat's are
decimal, its per-GiB prices are 7.4% higher, which moves 0.52 to 0.56 and
reverses no ratio [I]. A lane VM is assumed to start once a month, so it buys
no extra starts [A]. Boat's vCPUs are shared and no CPU model is promised: the
same pricing page reports 28.06 benchmark runs a second on a Ryzen 9 9950X
host and 8.88 on a Hetzner host [M, `pricing.md`], a spread that waiting-bound
lanes (median 1.0% CPU per process [M, 2026-10-07 Context]) barely feel and CI
feels a great deal.

Read plainly: packed, Boat undercuts the lane host by about half on-demand and
by about a quarter against the Savings Plan; unpacked, one VM per lane loses
by 1.6x to 2.3x, which is the 2026-10-07 point restated. The build plane packs.
The product plane does not, on purpose (Decision §5), because a product
workspace lives for minutes and the VM is its isolation boundary.

### 3. Exactly which 2026-10-07 clauses this proposal amends, and which it leaves

Three clauses are amended, for Antiek's own product and build planes only. For
the peer research tenants each stands as written.

**3.1 Amended: Decision §1, its heading.**

> ### 1. The agent-CPU backbone is Antiek-owned Linux lane hosts, governed by the compute dispatcher

Effect: amended by addition. For Antiek's own product and build planes the
compute backbone is Boat full VMs under this record. For the peer tenants the
heading stands, and the same section's "The tenants are the research projects
(solcoa, volantis, inferact)" is not touched.

**3.2 Amended: Decision §1, its rationale paragraph.**

> Why not a sandbox vendor as the backbone: lanes spend almost all their time waiting on model APIs, and per-sandbox metering bills that wait. Packing waiting-bound, RAM-bound lanes into one host under cgroups is 3-5x cheaper per lane-month, gives cgroup kill-the-tree semantics and node-local dedupe (a duplicate unit name is refused), and keeps lanes resumable from PROGRESS files without a 24-hour session cap.

Effect on the build plane: a full-VM vendor whose VMs are packed like a lane
host is not "per-sandbox metering" in this clause's sense, so for the build
plane the clause stops barring Boat. Kill-the-tree and unit-name dedupe come
with systemd inside the VM; Boat adds create-level idempotency [M,
`api_v1.md`]; a paid plan's auto-stop runs to 30 days or off, so there is no
24-hour cap [M, `limits.md`]; and PROGRESS-file resumability survives a stop
because the disk does [M, `concepts.md`].

Effect on the product plane: the clause is set aside on a different ground,
the one stated at 3.3. Product workspaces are not packed and are not
waiting-bound lanes, and this record accepts per-sandbox metering for them
because the VM is their isolation boundary. The packing argument above does
not apply to them. For the peer tenants the clause stands as written.

**3.3 Amended: Decision §8, row L18.**

> | L18 low CPU with long wall time is billed waiting | the backbone is a packed host, not per-sandbox metering |

Effect: for the build plane the row holds (boxes are packed). For the product
plane this record deliberately accepts per-sandbox metering, one VM per
workspace, because product workspaces are short-lived (900 s auto-stop by
default) rather than waiting-bound lanes, and because the VM boundary is what
isolates one workspace's untrusted code from the next [M, `security.md`, "One
sandbox per end user"].

The clauses below are **not amended**, and this proposal acts under or beside
them:

- **Decision §1:** "The lane host carries **no Antiek code or credential**
  (D-18/D-19/D-36; compute 1.6.0 refuses project `antiek` on hosts)." Boat
  boxes are not lane hosts and compute's node backend does not place work on
  them; lane hosts stay free of Antiek code and credentials.
- **Decision §1:** "Antiek's own in-product seams (`ExecutionBackend`,
  `RemoteExecProvider`, the unmerged `runtime/compute_admission/` of PR #3728)
  are a separate system held for the §16 amendment and ADR 0017; this decision
  does not touch them." This proposal is the §16 amendment that clause
  anticipated, for `ExecutionBackend` alone. `RemoteExecProvider` is untouched,
  `runtime/compute_admission/` is absent at `79b66b1`, and ADR 0017 is not in
  this repository, so this record does not claim to satisfy it.
- **Decision §2:** "Neither is the backbone: both meter the wait (above), and
  neither suits a long single-writer workload." Modal and Prime keep their
  tiers under the compute dispatcher for the peer tenants.
- **Decision §4:** "It remains in the EU, so PR #3728's "Antiek-user jobs
  require a backend declared EU" rule is satisfied;" Applied to Boat, whose
  machines are in the EU and whose snapshot copies may not be (review
  checklist, line 1).
- **Consequences:** "Interpretation this record relies on, for the operator to
  confirm: D-18's "Antiek credentials stay on the Mini" governs Antiek
  *development* on the compute layer, not the production host, which holds its
  runtime credentials on AWS exactly as it did on Hetzner (critic C17)."
  Carried to the build plane as an open owner sign-off (a build box with
  GitHub on holds a token that can push to Antiek). D-18's own text lives in
  `~/offload/DECISIONS.md`, which this lane could not read.
- **What would change this:** "**Lane demand moves into Antiek's product** (an
  operator §16 / ADR 0017 ruling, PR #3728): the in-product seams get their own
  placement decision; lane hosts would need an Antiek-credential policy they do
  not have today." This record is that placement decision for
  `ExecutionBackend`. It places the seam on Boat, not on lane hosts, so lane
  hosts gain no Antiek-credential policy.
- **What would change this:** "**A metered vendor stops billing idle wait**
  (per-active-CPU pricing at lane scale) or Prime publishes a post-launch price
  below a packed host: revisit item 2." Not triggered as written, because Boat
  bills idle wait. The Decision §2 table is offered as input should the owner
  revisit the peer tenants' placement; this proposal does not.
- **Status, Decision §1 and §3:** lane host #1, the production move to
  eu-north-1, and the cutover that "waits for the operator's go (runbook gate
  G0)". Not amended, not authorized, not executed.

### 4. Where Boat loses

- **Region and residency.** EU machines only, and snapshot copies may be
  stored outside the EU [M, `security.md`]; the Boat agent "uploads snapshots
  to `boat.dev` and to snapshot storage" [M, `snapshots_stop.md`]. There is no
  Gulf or KSA region to move to.
- **No GPU** on any size [M, `pricing.md`].
- **Starts are rationed and never queued.** Every product workspace is one
  start. A 20-leaf cascade launched inside one minute needs 8 starts above the
  included 12: USD 0.28 from the wallet at the documented brackets (six at
  USD 0.03, two at USD 0.05), or, with an empty wallet and invoiced extra
  starts off, eight leaves fail with `429` [I from `limits.md`]. The minute
  maximum is 36 starts (three times included) [M, `limits.md`].
- **Single vendor.** One company holds the VMs, the snapshots and the wallet.
  SOC 2 is "in progress" and the 99.95% uptime is Boat's own measurement [M,
  `security.md`]; retention cleanup of stopped disks "currently runs in
  report-only mode" [M, `pricing.md`] and can start deleting.
- **Egress control is the sharpest loss.** Boat has no API for network rules
  [M, `hosting_firewall.md`]. A `DENY_ALL` workspace is only as good as
  owner-match rules inside a VM whose `user` has passwordless sudo, rules that
  snapshots do not keep and that turn the sandbox `degraded` if they catch
  `user` [M, `security.md`, `hosting_firewall.md`]. The lane host, by contrast,
  accepts no inbound connection and is reached only over Tailscale [M,
  `lane-host.md`]; a Boat sandbox accepts inbound SSH and Boat's agent port
  8911 by design [M, `security.md`, `hosting_firewall.md`].
- **Shared limits** across planes and the research boxes (Decision §1).
- **Smaller points.** A stop keeps no memory and a resume brings a new IP [M,
  `concepts.md`]; containers inside one sandbox share its kernel and Boat does
  not isolate them [M, `security.md`], so packing is safe only within one
  trust domain.

### 5. Product plane: `BoatBackend` behind `ExecutionBackend`, as the code stands

One workspace is one Boat sandbox. That keeps the VM boundary between
workspaces, which is Boat's own advice for work done for users [M,
`security.md`], and costs little: a two-minute `small` workspace uses about
USD 0.0006 of VM time [I]. The binding constraint is starts, not money.

What the code already holds, against the seam's invariants: every create
names the configured environment, defaulting to `antiek-product`, and
refuses `antiek-build` (deployment policy requires `antiek-product` and the
Antiek org pin; code-side mandatory pinning and affirmative environment
read-back remain open activation gates, items 3 and 8); the environment is
checked to pass nothing at probe and before every create, fail closed, then
on the sandbox record when it carries `environment`, and inside the VM
before any workload runs;
`proxyAiCredentials` refused whenever it is present and not `false` (S1); an
auto-stop on every create; `snapshots: false` on every create, with no
constructor override and the record's `snapshots` read back and required
(D5), so no
snapshot of a product workspace exists and a stop erases the disk [M,
OpenAPI]; a reap that fails closed and refuses the next workload (S2); an
interrupted `exec` fenced, reaped and restored under the VM's exec lock
before any other call proceeds, or the workspace kept unclean (S3); a spend
ledger line for each sandbox id the process learns through the create or a
recovery and for each confirmed delete, subject to the process or its log
delivery failing, so an unidentified or unlogged create stays possible and
makes the accounting incomplete (D4); the org pin, when `ANTIEK_BOAT_ORG`
is set, checked at probe (when the key may read `GET /limits`) and on
every new sandbox; an `Idempotency-Key` on every create; delete on `destroy()`,
idempotently (I6); `DENY_ALL` enforced and verified or refused (I4);
`ALLOWLIST` refused; the timeout and output caps (I1); no SDK types (I5); none
of the host-writer identifiers (I2, the grep test covers every module of the
package); a cleanup attempted before every `exec` that may have run
returns, with termination claimed only when it is confirmed and the
workspace otherwise kept unclean (I7); and loud
`BackendUnavailable` instead of any downgrade [M, the module and `factory.py`
docstring].

What does not yet hold. Each item must hold by the gate "Prerequisites by
gate" below gives it:

1. **The environment is the protection, so it must be right before the first
   create.** Without `noEnv`, a product sandbox receives whatever
   `antiek-product` passes. The backend now reads the environment's flags at
   probe and again before every create and refuses, fail closed, before
   anything is billed; the in-VM check after the create is a second net that
   sees only the names the docs list. What stays open is the flags' meaning:
   the code applies the documented rule ("safe for third parties" on means
   nothing passes) because the OpenAPI has no `effective` field. G3.1 step 6
   and the owner's dashboard record of the flags close this before G3.2.
2. **The `ci` preset's reads are undocumented.** If the product key may not
   read `GET /limits` [`account.read`, M, `api-keys_scopes.md`], `probe()`
   logs a WARNING and proceeds, and there is then no client-side `canStart`
   check: a create relies on Boat's own admission of the `POST`, and the org
   pin on the `X-Boat-Org` header and the sandbox `team` read-back. The
   owner accepts that or re-mints the key. If it may not
   read `GET /environments` [`environment.read`, M, `api-keys_scopes.md`],
   the backend refuses to start at all, at probe and at every create, and the
   owner must re-mint the key with that read on `antiek-product`. G3.1
   records which reads each key has.
3. **`ANTIEK_BOAT_ORG` is optional in code.** This record requires it set to
   the team id wherever `BOAT_API_KEY` is; making it mandatory in code is a
   follow-up for the code lane.
4. **Creates are not paced.** The backend creates as fast as the runner asks,
   and the runner admits 20 at once (`host_local.py:87`,
   `DEFAULT_MAX_CONCURRENCY = 20`). Decision §7's start shares are policy that
   the owner applies when approving a plan, not code.
5. **No spend cap in code.** `ExecutionBackend` has no cost channel; the
   contained loop charges a notional USD 0.01 a step
   (`cascade_routes.py:399`) to `TOTAL_ACQUISITION_BUDGET_USD` (USD 10,
   `substrate/constants.py:141`), which therefore never sees Boat's realized
   dollars. Master-spec §16 asks for "Hard caps in code, configurable upward by
   the operator, never default-uncapped" for the chase daemon; here the hard
   stop is Boat-side (Decision §7) and a code-side cap is a follow-up. Until
   it lands, the product plane's spend ceiling is a daily check by the owner,
   or by the cloud CEO at the owner's direction (Decision §7, "How the
   ceilings are checked"), not an enforced limit, and G2 says so explicitly.
6. **Boat keeps command history.** "Every command and its output are kept 90
   days in the command history", readable while the sandbox is stopped [M,
   OpenAPI]; whether a delete erases it is not documented. The create leaves
   `monitoring` at Boat's default; with it off Boat keeps "no command or
   process output, process list or CPU/RAM samples" and its history calls
   answer `409 monitoring_off` [M, OpenAPI], which may break the backend's
   detached path (it polls `GET /commands/{processId}`), since the docs do not
   say whether that call counts as history. The gather program's output
   therefore sits in Boat's history for up to 90 days unless the reviewer
   rules otherwise (checklist, line 1).
7. **No file ledger.** The record of what the product plane created is the
   backend's journal lines (the accepted and deleted lines among them) and
   the `antiek-workspace` label. A durable ledger is a follow-up; the reaper
   rule (runbook) works from what exists.
8. **Exact-environment enforcement is partial.** Every create names the
   configured environment (default `antiek-product`; another valid name
   other than `antiek-build` is accepted), and the code refuses
   `antiek-build`, but the read-back
   refuses another environment only when Boat's record carries
   `environment` (the saved live list and info shapes do not show it; the
   create answers of both probe VMs did), and whether the key's `--env`
   restriction refuses a create outside its environment is unobserved (G3.2
   Part B). Requiring the field in code is a follow-up.
9. **TTL policy and code differ.** Decision §7 keeps product `wall_clock_s`
   at or below 3,600 s, but the code clamps `ttlSeconds` only to 60 s .. 30
   days, so a caller that asks for more gets it. A code-side cap at the
   policy value is a follow-up.
10. **No env-scoped live acceptance.** The only live run of the module
    (module `bb49ebe3`, "Live evidence" run 1) stopped before any create,
    its receipt `all_ok: false`, and the current module `f05833d1` has never
    run against Boat. G3.2 Part A, with the product key in `antiek-product`,
    is that acceptance.
11. **No live environments shape is recorded.** The module accepts an
    environment that lacks `proxyAiCredentials`, because the OpenAPI
    `SandboxEnvironment` does not require the field, and its docstring
    names its own ACTIVATION GATE: capture a live environments shape first
    and, if it carries the field, refuse an environment that lacks it before
    the backend is wired in. No live shape is recorded yet: `LIVE_SHAPES.md`
    has no `GET /environments` section, and the live smoke's receipt ("Live
    evidence" run 1) records refusals and environment names, not fields
    [M]. G3.1 step 6 records, through the CLI, whether each listed
    environment carries the field (`proxyAiPresent`); if any does, the code
    lane makes an environment without it a refusal before G2's
    registration.

**Activation gates that stay open.** The cloud CEO's review of PR #3826 keeps
five of these as activation gates that neither a default-off adapter nor an
aggregate test count certifies: the mandatory org pin (item 3),
exact-environment enforcement (item 8), code-side per-plane cost and pacing
limits (items 4 and 5, and the build plane's, which has none in code
either), the policy-versus-code TTL gap (item 9) and env-scoped live
acceptance (item 10). Item 10 closes with G3.2 Parts A and B, before G2; the other four
are closed in code or accepted by the owner in writing before the plane they
concern is activated.
The module names a sixth itself, the live `proxyAiCredentials` shape (item
11), which closes as item 11 says, before G2's registration. Round 2 closed
none of the six.

**Prerequisites by gate.** The single place each item and gate closes; the
gates table, the review checklist and the runbook's "Enable and activation"
refer to it. The order stays G1 (met), G4, G3.1, K, G3.2, G2, G3.3,
activation.

| Before | What must hold |
|---|---|
| G3.2, the paid smoke | G4 and K done. G3.1 passed, which closes item 1 (each environment's flags recorded, with the owner's dashboard record) and item 2 (each key's reads recorded, and a missing `account.read` accepted by the owner in writing or the key re-minted), and records item 11's live field (`proxyAiPresent`). The owner's separate written approval of the smoke envelope (Decision §7). |
| G2, the ratification and the product registration | G3.2 Parts A and B passed, with their receipt, which closes item 10; a failed or incomplete Part A or B blocks G2 until it is rerun and passes, and cannot be waived at G2 (Part C concerns the build plane and gates only its activation). Item 11 closed: if any environment carries `proxyAiCredentials`, an environment without it is refused in code. Items 6 and 7 closed, or accepted by the owner in writing. Item 5 accepted for now: the spend ceilings stay a daily check (Decision §7), with the code-side cap scheduled. The envelopes of Decision §7 ratified. The doctrine rulings: the §16 amendment (Decision §6), the three 2026-10-07 clause amendments (Decision §3), and open sign-off 4's build ruling with any amendment it requires. Open sign-offs 1 and 2 answered (sign-off 3 is K; sign-off 5 needs no answer while the runbook's "Credentials" table stays as it is). |
| Activation of the product plane | G2 met. G3.3 passed. Items 3, 4, 5, 8 and 9 closed in code, or accepted by the owner in writing (item 10 is already closed by G3.2 Parts A and B, never by acceptance). The owner's separate written go. |
| Activation of the build plane | The doctrine rulings of G2 ratified (the product registration is not needed). G3.2 Parts B and C passed; a failure of Part A alone blocks only the product plane. The build plane's code-side cost and pacing limits closed, or accepted by the owner in writing. The owner's written approval of the build envelope after Part C. |

`RemoteExecProvider` is not targeted. Its contract streams events out of a
live loop and steers into it, the in-sandbox program it would run does not
exist, which is why `DaytonaProvider.run` raises today, and `contained_gather.py`
(lines 9-26) records that an adapter over `ExecutionBackend` "is not merely
unbuilt, it is unbuildable over this interface". The registry is pinned to
Daytona by test and the research fan-out exemption rules out a second
provider. A Boat `RemoteExecProvider` is its own future decision, after the
leaf exists.

**The registration ratification flips** is the diff the module's
"Activation (after ratification)" section already writes out, confined to
`factory.py`: `"boat"` joins `_VALID_KINDS`, and one branch after the docker
branch imports `BoatBackend` locally, calls `probe()` and logs `ExecutionBackend
selected: boat (via ...)`. It moves no default: unset still means no backend
for the cascade and `local` for direct callers. The same change flips
`EXPECTED_FACTORY_KINDS` in `tests/test_exec_backend_boat.py` and replaces its
dark-module guards with a factory test mirroring `TestFactoryDockerKind`, as
the module says; that test file is present, uncommitted, and must land with
the code lane first.

### 6. The §16 amendment, proposed text

Inserted into CLAUDE.md directly after the research fan-out block, between
`<!-- BEGIN: s16-boat-execution-backend (operator-ratified YYYY-MM-DD) -->`
and `<!-- END: s16-boat-execution-backend -->`, with the date filled at
ratification and every other REJECT clause left byte-identical:

> - **§16 amendment: Boat as the product's compute backbone, `ExecutionBackend` only.**
>   The operator ratified on YYYY-MM-DD a second scoped carve-out: agent-code
>   execution behind the `ExecutionBackend` seam (`runtime/exec_backend/`) may
>   run in Boat full-VM sandboxes, selected only by `ANTIEK_EXEC_BACKEND=boat`,
>   billed to the Boat organization Antiek and authenticated only by
>   `BOAT_API_KEY`, a `ci`-preset organization key restricted to the
>   `antiek-product` environment, with `ANTIEK_BOAT_ORG` pinned. Every Boat
>   workspace starts in `antiek-product`, an environment that passes nothing
>   of the owner's (Boat's *Safe for third parties*), checked before every
>   create and again before any workload runs; it has snapshots off and an
>   auto-stop, is deleted on
>   `destroy()`, and either enforces its declared net policy or refuses it
>   with `NetPolicyUnsupported`. This
>   authorizes no general Boat execution and no inference or dispatch routing
>   change: dispatch stays Hermes-primary (`substrate/dispatch/` untouched, no
>   Boat integrated agents, no Boat AI-credentials proxy), and the DuckDB
>   single-writer invariant is untouched (a workspace receives and returns
>   bytes, and the promotion funnel through `runtime/db_lock` remains the only
>   graph writer; `--workers 1` holds). `RemoteExecProvider` stays Daytona-only
>   under the research fan-out exemption above; ε > 10 on DP claims and
>   premature scaling stay rejected; the 2026-10-07 AWS decision and its
>   peer-tenant lane hosts are unchanged and no AWS step is executed. Nothing
>   schedules Boat, including the cloud CEO's hourly swarm, before the
>   operator's written activation. Unsetting `ANTIEK_EXEC_BACKEND` returns the
>   cascade to its default gather loop with no code change; while it is set
>   there is no silent fallback. Boat boxes used to build Antiek (development,
>   production testing, CI, coding swarms) are operator tooling under their
>   own key `BOAT_BUILD_API_KEY` in the `antiek-build` environment; this
>   paragraph neither covers nor authorizes them, and no key is shared between
>   the two. Rationale, gates and reconsider-if:
>   `docs/decisions/boat-compute-backbone-2026-11-09.md`.

The block's sentence on Boat boxes used to build Antiek assumes the answer to
open sign-off 4 (build-plane use is operator tooling outside §16). G2 does not
close until the owner answers it. If the owner asks for §16 cover instead,
that sentence is replaced at G2 by a build-plane carve-out drafted then, and
the rest of the block stands. Build-plane activation waits on the same
ruling: whichever way the owner rules, the ruling is explicit and recorded,
and any amendment it requires (a build-plane carve-out, or a change to this
block) is ratified before the build plane is activated.

### 7. Envelopes per plane, set before any paid run (PROPOSED defaults)

No paid Boat run on either plane happens outside these envelopes. Every
figure is a PROPOSED default for the owner to accept or change; none is in
force. "VM time" is at list price, whether drawn from included hours or the
wallet. The account-wide hard stop is Boat-side and shared: the wallet is
funded by hand only, auto top-up stays off, and invoiced extra starts stay
off (off by default [M, `limits.md`]), so once included time and wallet are
spent, new starts fail with `402 billing_required` rather than bill [M,
`limits.md`]. What happens to sandboxes already running at that moment is on
`billing.md#running-out`, which was not saved.

**PRODUCT plane**

| | G3.2 Part A | G3.2 Part B, this key's one attempt | G3.3, after G2 | Steady state after activation |
|---|---|---|---|---|
| Spend ceiling | USD 0.10; expected at most USD 0.012 even if both sandboxes live to their TTL (2 `small` x 1,200 s) [I]; no extra starts | USD 0.05 for Part B's three attempts together (this one and the build key's two); expected USD 0, since a refused create starts nothing [A]; at most USD 0.0045 if this attempt is accepted and lives to its TTL [I] | USD 0.10; expected at most USD 0.0135 (3 `small` x 900 s) [I]; no extra starts | USD 1.00 a day and USD 15 a billing period of product VM time, checked daily as below; no extra starts |
| Size | `small` (`ResourceLimits(wall_clock_s=1200)`, otherwise defaults) | `small` | `small`: the cascade passes no limits, so the `ResourceLimits()` defaults apply (1.0 vCPU, 2,048 MB) | `small` unless a caller's `ResourceLimits` need more; `xlarge` is unavailable on `box_20` |
| Max TTL | 1,200 s per sandbox; all of G3.2 inside 30 minutes | 900 s | 900 s, the default `wall_clock_s` (`contained_gather.py:241`, `interface.py:122`) | `ttlSeconds` = `wall_clock_s` (900 s by default); callers keep `wall_clock_s` at or below 3,600 s (policy: the code clamps only to 30 days); auto-stop never off |
| Max concurrency | one at a time, two in total | one attempt | three at once | 20 at once (the runner's cap); at most 8 creates in any minute (plans of at most 8 sub-questions per launch), 36 an hour, 120 a day |
| Storage | `snapshots: false`, verified on the sandbox record; sandbox disk teardown checked by delete and not-found evidence, which does not certify deletion of Boat's command history, monitoring records or other retained metadata (item 6 and the privacy ruling) | nothing kept: an accepted attempt is deleted at once | as Part A | the same; `monitoring` per the reviewer's ruling |
| Egress | Boat bills none [M]; one `ALLOW_ALL` workspace, then one `DENY_ALL` workspace whose blocked request is the expected result | none: no command runs | `DENY_ALL` (the contained gather default) | `DENY_ALL`; `ALLOW_ALL` only when a caller declares it; `ALLOWLIST` refused |
| Credential scope | `BOAT_API_KEY` and `ANTIEK_BOAT_ORG` in the cloud CEO's environment, `BOAT_BUILD_API_KEY` removed from the process; every sandbox in `antiek-product`, which passes nothing, with the in-VM credential check passing; workload as `antiek-runner` under `env -i`; no key inside a sandbox | `BOAT_API_KEY` in the cloud CEO's environment, outside the wrapper on purpose; the target `antiek-build` passes nothing at this point | a staging run of the service in the cloud CEO's environment, or on another staging host the owner names and the runbook's "Credentials" table records first, with `BOAT_API_KEY`, `ANTIEK_BOAT_ORG` and `ANTIEK_EXEC_BACKEND=boat` and without `BOAT_BUILD_API_KEY` | on the production host, `BOAT_API_KEY`, `ANTIEK_BOAT_ORG` and `ANTIEK_EXEC_BACKEND=boat` only (`ANTIEK_BOAT_ENVIRONMENT` unset, so `antiek-product`), never `BOAT_BUILD_API_KEY` |
| Data scope | synthetic strings only | none | three reviewed, synthetic sub-questions; the placeholder gather program | the investigation id, the sub-question and the gather program; no graph handle, DuckDB path, ingest lock, credential or user file |
| Teardown | `destroy()` twice per workspace; each id answers not-found after it answered found; active count back to baseline where `GET /limits` carries it | an accepted attempt is deleted at once with the same key and recorded, and G3.2 fails on separation | `destroy()` through the cascade; each journaled id answers not-found | `destroy()` on every path (`contained_gather.py`'s `finally`); the auto-stop as backstop, which with snapshots off erases the disk; the reaper acts only on ids Antiek recorded |

**BUILD plane**

| | G3.2 Part B, this key's two attempts | G3.2 Part C, build smoke | Steady state after activation |
|---|---|---|---|
| Spend ceiling | inside Part B's USD 0.05; expected USD 0 for the cross-plane attempt; the no-environment observation may start one box; at most USD 0.009 for both at their TTL [I] | USD 0.10; expected at most USD 0.009 (one `small` x 1,800 s) [I] | USD 5 a day and USD 50 a billing period of build VM time (four `default` boxes for 24 h cost USD 3.46 [I]), checked daily as below; no extra starts |
| Size | `small` | `small` | `default` (six lanes a box at the 2026-10-07 density [A]); `large` only with a recorded reason |
| Max TTL | 900 s | 1,800 s | 7,200 s for one-shot boxes and swarm forks (Boat's own recipe value [M, `recipes_parallel-agents.md`]), extended only while a lane runs; `--no-auto-stop` only with the owner's approval |
| Max concurrency | one attempt at a time | one box | four boxes at once (32 GB, the lane-host comparison's capacity); at most 4 creates in any minute (one per 15 s), 20 an hour, 60 a day |
| Storage | nothing kept | nothing kept | snapshots only on boxes that stop to resume a lane from PROGRESS; at most two saved snapshots (of the account's ten included [M, `pricing.md`]); a stopped box deleted within 7 days, inside Boat's 14 |
| Egress | none: no command runs | open: package installs and an anonymous clone of the public repository | the same; no `boat host` public URL |
| Credential scope | `BOAT_BUILD_API_KEY` outside the wrapper, for these two attempts only; the targets are `antiek-product` and no environment, both passing nothing | `BOAT_BUILD_API_KEY` through `B`, pinned to `antiek-build`, which passes nothing | the same until the D-18 ruling; after it, at most a GitHub token scoped to `Slimydog21/Antiek` as the owner rules; never an Antiek production secret, never a Boat or model credential |
| Data scope | none | the public repository `Slimydog21/Antiek` | the same plus build outputs and synthetic fixtures; no production data, no `/etc/antiek/secrets.env` content, no DuckDB file |
| Teardown | an accepted attempt is deleted at once with the build key and recorded | delete on completion; the id answers not-found; a `destroyed_at` ledger row | delete when the lane completes; stop only to resume; the reaper acts only on build-ledger ids; never touch `bx_235rmpn3` or `bx_35hs5p53` |

**How the ceilings are checked.** Neither plane has a code-side cost cap or
file ledger yet (Decision §5 items 5 and 7), and `GET /limits` shows one
wallet for both planes and the research boxes, so its deltas cannot split
spend by plane [M, OpenAPI `LimitsFields.wallet`, "The one wallet of this
account or organization"]. The runbook's "Watching spend" gives the daily
check. Each method gives a list-price figure of the sandboxes it knows,
always labelled incomplete:

- **Product:** the backend logs one `BoatBackend sandbox accepted` line per
  sandbox id it learns through the create or a recovery (`via=create`, `repost`
  or `sweep`), and one `BoatBackend sandbox deleted` line per confirmed
  delete [M, the module at `f05833d1`]. Billed provisioning failures and
  lost creates that the same-key re-`POST` or the label sweep recovered are
  therefore counted, which the earlier sum of `BoatBackend created
  workspace` lines missed. Each accepted sandbox counts at its full
  `ttlSeconds`, which bounds that sandbox, because the auto-stop ends
  billing at most one TTL after the create and the backend neither resumes
  nor extends a sandbox [I]. The sum is still **incomplete, not an upper
  bound**: a lost create that neither the re-`POST` nor the sweep found
  leaves at most a WARNING and no sandbox id, and none at all when the
  create, or the same-key re-`POST`, was answered without a usable sandbox
  id and the sweep's listing then found nothing (the module logs nothing for
  that path; the create raises `WorkspaceProvisionError` to its caller); a
  service killed between Boat's answer and the log line leaves nothing; and
  a sandbox accepted before the window opened is outside it [M, the module
  at `f05833d1`]. The check therefore counts the WARNINGs there are, lists
  every `antiek-ws-` sandbox the product key can see that no accepted line
  names (the only net for the silent paths), and treats either as a stop.
  At the default 900 s on `small` a workspace costs at most USD 0.0045, so the product's share of 120
  starts a day caps a day's VM time at USD 0.54 while that share holds (it
  is policy, not code: Decision §5 item 4); only longer TTLs or larger
  sizes can reach USD 1 [I]. Above the ceiling, or while the figure is
  incomplete, the actual figure is the sum of `boat usage` over the ids and
  the dashboard.
- **Build:** the build ledger's `created_at` and `destroyed_at` rows, with
  the size, give each box's lifetime, and an open row counts up to the
  moment of the check. The figure is always labelled incomplete: it is the
  list-price VM time of the boxes the ledger knows. Its count of unmatched
  intents is a warning heuristic, not a completeness proof (an unrelated id
  row can offset an unresolved intent, and the window drops older ones), so
  before any further build create, whatever the count says, every intent
  row in the whole ledger is reconciled with its own outcome (its id row or
  a recorded refusal) and `B list --all --json` is compared with the
  ledger; a count above 0, a figure above a ceiling or an unexplained
  intent stops creates until the owner rules.

Until a code-side cap lands, a ceiling is a check, not an enforcement. G2
accepts that explicitly or schedules the follow-up first.

The shared start windows, divided: 8 / 36 / 120 (minute / hour / day) for the
product plane, 4 / 20 / 60 for the build plane, and 0 / 4 / 20 left for the
research boxes' resumes and slack, which sums to the included 12 / 60 / 200.
Active at once: 20 product, 4 build, the 2 research boxes, 74 of 100 unused.
Boat's own recipe paces forks six seconds apart, at most 10 a minute, which
fits the plan only when nothing else starts [M, `recipes_parallel-agents.md`];
the build plane paces at one per 15 s to leave the product its share. Extra
starts are paid from the wallet whenever it holds money [M, `limits.md`], so
the receipts count them.

### 8. Build plane: Omarchy first, Boat second

Omarchy is the first tier because it costs nothing at the margin, and it is
the only tier for lanes that need the owner's subscription logins: 16 threads
and 15 GiB hold at most about fifteen lanes at the 2026-10-07 footprint of
1 GiB before the desktop, Docker and the gateway take their share, so fewer in
practice [I], and the gateway's health comes before any lane's. Build work
moves to a Boat box in `antiek-build` when it needs what Omarchy cannot give:
a clean full VM with root, systemd and `/dev/kvm`, a production-shaped host
for a deploy rehearsal, or more parallel lanes than Omarchy holds. Omarchy
needs no Boat key to do its share: Boat build work is driven from the cloud
CEO's environment, where the build key lives. Omarchy's own lanes run with
its host-owned credentials, which current owner policy permits (Context);
none of them, the owner's subscription logins included, is ever copied into
a Boat box or environment. A build box is an execution target for a lane
driven from the cloud CEO's environment; no model credential needs to be
inside it [I].

Coding swarms follow Boat's fork recipe (one prepared box, forked N times,
each fork one start) at the build plane's pace [M, `recipes_parallel-agents.md`].
They do not use `boat prompt` or the AI-credentials proxy under this record,
because both put model credentials in a box [M, `environments_access.md`,
`pricing.md`]. `runs-on: boat` GitHub runners need the USD 20 plan or higher,
now met, but connecting them needs a key with `account.admin` and Boat refuses
jobs from public repositories by default [M, `ci.md`], and `Slimydog21/Antiek`
is public [M]; moving `ci.yml` is not part of this decision.

## Gates and acceptance evidence

| Gate | What closes it | Owner | Evidence | State on 2026-11-09 |
|---|---|---|---|---|
| **G1** | Org Antiek on a paid plan | the owner | `box_20`, `billingStatus` active, `canStart` true, `maxActiveSandboxes` 100, 555.56 included hours to 2026-12-09T06:25:35Z | **MET** [M, about 06:27Z] |
| **G4** | Both environments exist as Decision §1 sets them; both keys sit in the cloud CEO's environment as `BOAT_API_KEY` and `BOAT_BUILD_API_KEY`, where the runbook's "Credentials" table places them | the owner | the owner records, from the dashboard, each key's name, id, preset, environment, expiry and last four characters, never the value; the CEO confirms presence by variable name only; the owner attests where each key was placed (runbook "Credentials") | in progress: environments being created, keys being minted [M] |
| **G3.1** | Read-only scope verification of each key, its organization and its environment; no sandbox is created | the cloud CEO at the owner's direction | runbook "G3.1" receipt: the CLI authenticates from `BOAT_API_KEY` alone and finds no stored login; both variables set and distinct; each key refused for Personal with `403 api_key_org_mismatch`; each key's limits read naming `teamId` = `ANTIEK_BOAT_ORG` with `canStart` true (or the `account.read` refusal recorded); each key unable to list account keys; each key's listing free of the research boxes; both environments' effective flags; the baseline of active sandboxes, included hours, wallet and starts, with any of those fields the org read does not carry recorded as absent | not run |
| **K** | The owner's ruling on the two keys pasted into a chat transcript (open sign-off 3), carried out | the owner | rotation or revocation recorded by key id; G3.1's identity steps re-run for any replacement | open |
| **G3.2** | A paid create, exec, collect and delete smoke, authorized separately by the owner after reading the G3.1 receipt, inside the Decision §7 envelopes: Part A product (`BoatBackend` directly, still unregistered), Part B cross-plane refusals (the wrappers' pins bypassed on purpose), Part C build box and its systemd packing primitives | the owner authorizes; the cloud CEO runs it | runbook "G3.2" receipt: sandbox ids and workspace ids; create-to-ready and per-step timings; exit codes; cost from `boat usage` where readable and, always, the list-price bound computed from each sandbox's create and delete times; starts used; teardown proof (each id not-found after a found-before; the active count back to baseline where the org read carries it, otherwise recorded as unavailable); no key, no token URL | not run |
| **G2** | After open sign-off 4 is answered, the owner ratifies: the §16 amendment (Decision §6); the three 2026-10-07 clause amendments of Decision §3 (its Decision §1 heading, its Decision §1 "Why not a sandbox vendor as the backbone" paragraph and its Decision §8 row L18), for Antiek's own planes only; and the envelopes, including that the spend ceilings are a daily check until a code-side ledger and cap land. The registration lands with its tests and with the "Before G2" row of Decision §5's "Prerequisites by gate" met: G3.2 Parts A and B passed (a failed or incomplete Part A or B blocks it and cannot be waived here), item 11 closed (the live `proxyAiCredentials` shape recorded by G3.1 step 6 and, if the field is present, an environment without it refused in code), and items 6 and 7 closed or accepted in writing | the owner | CLAUDE.md carries the Decision §6 block verbatim between its markers; the 2026-10-07 record carries, under each of the three clauses, a dated one-line note pointing to Decision §3 of this record, with the clause text itself byte-identical (the cloud CEO adds the notes in the ratifying change, since it owns the PR; this lane edits neither file); this Status reads ACCEPTED with the date; the factory diff and the inverted dark-module test in the same change | not ratified |
| **G3.3** | The cascade through the factory, three leaves at once, in a staging run of the service in the cloud CEO's environment, or on another staging host the owner names and the runbook's "Credentials" table records first | the owner authorizes | runbook "G3.3" receipt: the factory names `boat`; three sandboxes ran together; three notes promoted through the funnel only; teardown proof as G3.2; list-price bounds at the 900 s default TTL | cannot run before G2 |
| **Activation** | As Decision §5 "Prerequisites by gate" sets it for each plane. Product: the owner's written go after G3.3, with the open activation gates of Decision §5 closed or accepted in writing (item 10 only by passing G3.2 Parts A and B). Build: G3.2 Parts B and C passed, the owner's explicit ruling on the build plane under §16 (open sign-off 4), any amendment that ruling requires ratified with the other doctrine rulings of G2, the Decision §5 activation gates that concern the build plane (at least code-side cost and pacing limits) closed or accepted in writing, then the owner's written approval of the build envelope after Part C | the owner | the go, dated, appended to this record; until then the swarm (cron `b413595fcdd5`) keeps Boat out of its targets | not given |

The order is G1 (met), G4, G3.1, K, G3.2, G2, G3.3, activation. The swarm
runs none of them.

## Review checklist

Each line is answered yes or no, with its evidence, before G2.

1. **Residency and privacy (EU-only machines).** Boat's machines are in
   Germany, Finland and France; "Snapshot copies can be stored outside the
   EU" [M, `security.md`, which defers detail to `compliance.md#data-location`,
   not saved]; the agent uploads snapshots "to `boat.dev` and to snapshot
   storage" [M, `snapshots_stop.md`]. Product sandboxes are created with
   `snapshots: false`, so per the OpenAPI nothing is captured and no snapshot
   copy exists to leave the EU [I]; G3.2 confirms `snapshots: false` on each
   product sandbox. Build boxes that stop and resume do keep snapshots, which
   would carry a GitHub token if the D-18 ruling allows one. Boat keeps
   every command and its output for 90 days in the command history [M,
   OpenAPI], so the gather program's output outlives the workspace; where
   that history and other monitoring data are stored, whether a delete erases
   them, and where `boat.dev`'s API runs are not in the saved pages. The
   reviewer rules on `monitoring` (Decision §5 item 6), on PR #3728's EU rule
   should it merge, and accepts that there is no Gulf or KSA region.
2. **Tenant isolation.** One Boat VM per product workspace (one create per
   workspace in code); `visibility: private`; the `antiek-product`
   environment passing nothing, which also removes the in-sandbox Boat key,
   while `ASCII_TOKEN`, which can only host ports of its own sandbox, always
   stays [M, `api-keys_scopes.md`]; G3.2 records whether
   `antiek-runner` can read `/home/user/.bashrc`, where that token is set.
   Packing only within the owner's build lanes, one trust domain; the peer
   tenants never on Boat under this record; Antiek stays single-operator
   (CLAUDE.md critical invariant 5), and a multi-user pivot reopens this line.
3. **Serialized writes.** No graph handle, DuckDB path, ingest lock or
   credential crosses the seam (I2, I3); `test_no_host_writer_identifier_in_package`
   (`tests/test_exec_backend_interface.py:115`) and `TestSingleWriterPreserved`
   still pass with `boat_backend.py` in the package; the promotion funnel
   through `runtime/db_lock` stays the only graph writer; `--workers 1` is
   untouched; no Boat step writes Beads (the 2026-10-07 §7 dispatcher stays
   the only Beads writer).
4. **Credential separation.** `BOAT_API_KEY` only on the product plane,
   `BOAT_BUILD_API_KEY` only on the build plane, values distinct, both
   resolving to `ANTIEK_BOAT_ORG`; no code or wrapper falls back from one to
   the other or to a stored login; `ANTIEK_BOAT_ORG` set to the team id
   wherever `BOAT_API_KEY` is, and `ANTIEK_BOAT_ENVIRONMENT` unset or
   `antiek-product` (the code refuses `antiek-build`); the organization admin
   key and the personal account key in no agent's environment; no plane key
   in argv, in a log, in a receipt or in a Boat environment, and each key
   only where the runbook's "Credentials" table places it; no subscription
   credential or owner login copied into Boat;
   `delete-own` limits each key's deletes to its own sandboxes [M,
   `api-keys_scopes.md`]; revocation path confirmed. Every build-plane create
   goes through the runbook's `B`, which pins `antiek-build` and refuses
   `--no-env`, any other environment and `-e` values. A create with the build
   key that names no environment would land in the default `base` [M,
   OpenAPI `CreateSandboxRequest.environment`], which passes the owner's
   secrets, GitHub token and agent credentials [M]. Whether the key's `--env`
   restriction refuses such a create is not documented. G3.2 does not test it
   by creating, because a success would put the owner's credentials in a VM,
   so raw use of the build key outside `B` stays forbidden.
5. **Dispatch untouched.** No change under `substrate/dispatch/`, no Boat
   integrated agent, no AI-credentials proxy; Hermes-primary holds.
6. **Spend.** Decision §7 accepted; wallet funded by hand, auto top-up off,
   invoiced extra starts off; each G3 receipt's cost under its ceiling; the
   daily ceiling check of the runbook's "Watching spend" assigned to a named
   person; item 7 (no file ledger) closed or accepted in writing, and item 5
   (no code-side cap) accepted for now with its follow-up scheduled before
   activation (Decision §5 "Prerequisites by gate").
7. **Activation.** The swarm (cron `b413595fcdd5`) excludes Boat on both
   planes until the owner's written go, and runs no paid gate. Build
   activation also waits for G3.2 Parts B and C, for the owner's explicit
   §16 ruling on the build plane and any amendment it requires, and for the
   Decision §5 activation gates that concern the build plane.
8. **AWS and peer lane hosts.** Nothing in the change touches
   `infrastructure/terraform-aws/`, the cutover, `lane-host.md` or the peer
   tenants' placement.
9. **Code state.** The rows of Decision §5's "Prerequisites by gate" up to
   G2 met (items 1, 2, 10 and 11 closed, items 6 and 7 closed or accepted);
   `boat_backend.py` and `tests/test_exec_backend_boat.py` committed by the
   code lane; the module's plane text, `ANTIEK_BOAT_ENVIRONMENT` default and
   key name still match this record's Decision §1.
10. **Doctrine flags.** §16 (G2); the three 2026-10-07 clause amendments of
    Decision §3 (that record's Decision §1 heading, its Decision §1 "Why not
    a sandbox vendor as the backbone" paragraph and its Decision §8 row L18)
    and the dated notes that cross-reference them (G2); the open owner
    sign-offs below, with sign-off 4 answered before G2.

## Consequences

Until G2 nothing changes at runtime. After it, only an operator who sets
`ANTIEK_EXEC_BACKEND=boat` reaches Boat, and unsetting it restores the default
gather loop. Contained product work gains a remote, VM-isolated place to run
at about USD 0.0006 of VM time per two-minute `small` workspace plus a start
[I]; the cascade's budget never sees those dollars, so Boat spend is watched in
Boat (`boat usage`, `GET /limits`) and in the receipts. Building Antiek gains a
remote tier that the lane hosts refuse by design. The `box_20` plan is a fixed
USD 20 a month, already paid, and its included time does not carry over [M,
`pricing.md`].

The research boxes draw on the same 555.56 hours. If both are `default` and
run around the clock, they use 48 default-hours a day, exhaust the included
time in about 11.6 days, and then cost about USD 1.73 a day from the wallet
[I; their sizes and schedule were not measured]. That is the Boat Research
session's concern; this record notes it and does nothing.

Boat becomes a dependency of both planes; the fallbacks are one environment
variable on the product plane and Omarchy on the build plane, not a second
vendor. The 2026-10-07 record stays accepted as written, its lane host and
production move stay operator-gated and unexecuted, and the peer tenants keep
their arrangement.

## Open owner sign-offs

These are locked-doctrine or credential questions this record cannot settle.

1. **D-18 versus build boxes holding a GitHub token.** The 2026-10-07 record
   reads D-18 as "Antiek credentials stay on the Mini" for Antiek development
   on the compute layer. A build box in `antiek-build` with GitHub on would
   hold a token that can push to Antiek, inside a VM whose `user` is root and
   whose snapshots may be copied outside the EU. The PROPOSED default is
   GitHub off: boxes clone the public repository anonymously and return diffs
   to the cloud CEO, which owns review and the PR. The owner rules whether a
   token is allowed, with which scope and which TTL. D-18's text is in
   `~/offload/DECISIONS.md`, which this lane could not read.
2. **Omarchy's stored Boat CLI login can now spend the Antiek wallet.** The
   Boat Research session drives the research boxes from a stored CLI login on
   Omarchy. With the account's active wallet now Antiek, any create through
   that login that names no organization bills Antiek [I from `api-keys.md`:
   an account key bills "The organization a request names ... else your
   active wallet"]; the login file was deliberately not read. The personal
   account key the orchestrator measured earlier has scope `['*']` and never
   expires [M, earlier orchestrator measurement]. Under current instructions
   (Context) the login is a host-owned credential Omarchy may hold, and it
   is never copied into Boat; what stays open is the wallet it can spend. The
   owner rules whether the login stays account-wide, is replaced by a
   narrower key, or must name an organization on every create.
3. **Rotation of the two keys pasted into a chat transcript.** A key pasted
   into a chat lives in that transcript as long as the transcript does. The
   PROPOSED default: right after G3.1 passes, and before G3.2 spends anything,
   the owner rotates each pasted key (`POST /api-keys/{id}/rotate` replaces the
   secret "without changing expiry or scope" [M, OpenAPI]; the CLI form is
   `boat api-key rotate <id>` [M, `ci.md`]), or revokes it if it is an admin or
   personal key that no agent needs; installs any replacement in the cloud
   CEO's secret store by a path that writes no transcript; reviews each old
   key's request count (`boat api-key usage` [M, `api_v1.md`]); and has the CEO
   re-run G3.1's identity steps. Which two keys the transcript holds is the
   owner's to confirm.
4. **The build plane outside §16.** This record treats build-plane Boat use as
   operator tooling, as the 2026-10-07 record treats the dispatcher's Modal and
   Prime tiers. The owner confirms that reading or asks for §16 cover. G2
   waits for this answer, because the Decision §6 block's sentence on Boat
   boxes used to build Antiek depends on it, and so does build-plane
   activation, together with any amendment the answer requires.
5. **Where plane keys may be stored.** Omarchy execution and host-owned
   credentials are not open here: the cloud CEO's review in PR #3826
   (Spec/doctrine finding 1) states that current owner policy permits them,
   and the cloud CEO's SOUL says the same in its section "Current
   instructions supersede historical deployment assumptions": keeping every
   credential off Omarchy is no longer an accurate deployment instruction,
   and current authorization permits Omarchy execution [M, read by the
   orchestrator in the cloud CEO's dashboard on 2026-11-09]. The older
   instruction to keep Antiek credentials and keys off Omarchy disk survives
   only in that SOUL's preserved history and in earlier drafts of this
   record, not as a current rule. What the owner decides is only where the
   two plane keys may be stored: this record keeps them on the hosts the
   runbook's "Credentials" table names (the cloud CEO's environment and, at
   enable, the production host), which do not include Omarchy, until the
   owner widens that table. Permission to run on Omarchy does not by itself
   put a plane key there, and no subscription or owner login is copied into
   Boat.

## What would change this

- **The planes collide:** a product create refused for a start window or the
  active cap while build or research work holds it, a sandbox of one plane
  created in the other's environment, or a plane key that can act on the
  other plane's sandboxes. Then the build plane moves to a second Boat
  organization with its own plan; Boat allows up to five owned organizations
  once a trial is over [M, `free-trial.md`].
- **Isolation proves fragile:** a `DENY_ALL` workspace observed with egress, a
  workspace left `degraded` by its own rules, or a product sandbox that
  outlives its workspace past its TTL, more than once. Then unset
  `ANTIEK_EXEC_BACKEND`, and set `docker` on a host with a daemon to stay
  contained, as the research fan-out exemption's first reconsider-if does for
  Daytona.
- **Spend:** product VM time above its envelope without the owner raising it,
  or build above USD 5 a day.
- **Cost inverts:** measured packing on Boat (cgroup `memory.peak` per lane on
  a build box) fits 18 or fewer lanes in four `default` VMs, where Boat's
  per-lane cost reaches the lane host's plan figure (break-even 18.1 lanes), or
  12 or fewer, where it reaches the on-demand USD 8.40 (break-even 12.5); or
  Boat's `default` price rises above about USD 0.069 an hour, where its GB-hour
  meets the lane host's on-demand USD 0.00863 [I].
- **Residency:** Boat places machines outside the EU, a ratified EU-only rule
  forbids its snapshot copies, or the owner requires KSA residency: suspend
  the product plane.
- **Multi-user:** Antiek leaves single-operator mode: re-decide isolation (one
  sandbox per end user, no packing across users).
- **The vendor changes:** prices move from the 2026-11-09 page, retention
  cleanup leaves report-only mode, or an outage takes both planes down at
  once.
- **The research leaf lands:** a Boat `RemoteExecProvider` becomes its own
  decision.
- **The owner rules that D-18 or D-36 bars Antiek code from non-owned build
  boxes:** the build plane narrows to Omarchy.

## Out of scope

No dispatch or inference routing change, and no Boat integrated agents or
AI-credentials proxy on either plane. No change to the DuckDB writer, the
promotion funnel or `--workers 1`. No AWS execution of any kind: no `terraform
apply`, no cutover, no lane-host change, no change to the peer tenants'
placement. No `RemoteExecProvider` for Boat and no change to the remote-exec
registry. No change to the `ExecutionBackend` default. No CI workflow change
and no `runs-on: boat`. No edit to CLAUDE.md or to code by this lane. No GPU
work. No switch of the account's active wallet. No action of any kind on
`bx_235rmpn3` or `bx_35hs5p53`.

## Not proved by this record

No Boat API was called by this lane; the orchestrator's later live runs are
under "Live evidence". The following are absent from the saved pages and the
OpenAPI, or contradicted between them, and are G3 observations, not facts:

- `BoatBackend` end to end on a real VM: the orchestrator's run (module
  `bb49ebe3`) stopped before any create, its receipt `all_ok: false`,
  because no environment that passes nothing exists yet and the organization
  key may not create one; only the fail-closed path was proved live, and the
  current module `f05833d1` has not run against Boat at all;
- whether the round-2 reap and cleanup (the `pkill` statuses, the exec lock,
  the fence files, `DELETE /commands/{processId}`) behave on a Boat VM as
  they do on the test suite's fake VM;
- whether a VM in an environment marked safe for third parties carries the
  same keyless CLI config as the measured `noEnv` VMs [I: `api-keys_scopes.md`
  says both remove the in-sandbox key], and that Boat never puts a credential
  under the config's `api_url` or `channel`, which the content check relies on;
- whether the `ci` preset carries `account.read` or `environment.read`;
- whether an environment-restricted key may create outside its environment,
  with `noEnv` or into another named environment (G3.2 Part B observes both),
  or with no environment at all, which resolves to `base` (not tested by
  creating; checklist line 4), and the refusal code for each;
- whether such a key lists sandboxes outside its environment;
- whether live list and info records carry `environment` and
  `holdsCreatorLogins`, which the OpenAPI documents and the saved live shapes
  do not show (the create answer of both probe VMs carried both [M]);
- whether the Boat CLI authenticates from `BOAT_API_KEY` in its environment
  without `boat login` (an earlier orchestrator observation that is not in
  this lane's facts and not on a saved page; Boat's CI recipe signs in with
  `boat login --key-stdin` [M, `ci.md`]); G3.1 step 0 checks it;
- the CLI's JSON shapes for `limits`, `list`, `info`, `usage` and errors;
  whether `boat new` can set a name or labels; whether `boat fork` accepts
  `--environment`; whether `boat usage` answers after a delete;
- whether a refused create counts as a start or bills anything;
- the create-to-ready time in a named environment (a `noEnv` small VM was
  idle 2.8 s after its create, twice [M]).

The saved `LIVE_SHAPES.md` read of `GET /limits` (personal key, no org named)
lacks `canStart`, `billingStatus`, `teamId`, and also the top-level
`activeSandboxes`, `starts`, `nextStartDollars` and `machineTypes`, which the
OpenAPI documents (`activeSandboxes`, `canStart` and `billingStatus` as
required) and the orchestrator's org read at 06:27Z showed in part (`canStart`
and `billingStatus`). `probe()` refuses an answer without `canStart` as shape
drift, so a product key whose org read lacks it cannot start the backend. Its `currentLimits.activeSandboxes` sits beside
`standardLimits` and `trialLimits` and reads as a cap, not a count [I], so
it is no substitute. G3.1 records which fields the org read with each plane
key carries; where `activeSandboxes` or `starts` is absent, G3.2's baseline
comparison is recorded as unavailable, and teardown rests on the per-id
checks. Packing lanes on a Boat VM is inferred from documented root, systemd
and Docker; Part C checks the systemd primitives, not the density.

## Live evidence (the orchestrator, 2026-11-09, after the lanes)

Three runs from Omarchy, each with a receipt the handoff carries (the cloud
CEO's review attributes the uploaded receipts to Omarchy and did not run them
again). None used a plane key (none exists yet), none touched `bx_235rmpn3`
or `bx_35hs5p53`, and the two VMs together lived 14.1 s. They were one-off
development probes: they grant no continuing permission to create a VM, and
any further diagnostic VM needs its own approved envelope (runbook, Part A).

1. **`BoatBackend` fail-closed, USD 0, no sandbox**
   (`boat-backend-live-smoke-20261109.json`, 08:24:02Z to 08:24:05Z, module
   `bb49ebe3`, organization key). `probe()` refused `base` ("would pass
   account credentials ... passGithub, passSecrets, passSandboxCredentials,
   passAgentsCredentials not off") and refused the absent `antiek-product`
   ("not in this key's GET /environments listing"). The planned temporary
   environment that passes nothing could not be created: `POST /environments`
   answered 403 `api_key_action_forbidden` (`environment.write`). The run
   stopped there; `GET /limits` before and after carried `teamId` equal to
   the pin and `canStart: true`. The receipt's `all_ok` is `false` because
   environment creation was forbidden: no env-scoped create ran, and the
   module it ran, `bb49ebe3`, is an older hash than the current one.
2. **Primitives probe** (`boat-primitives-probe-20261109.json`, `bx_pqppjbcy`,
   08:26:36Z to 08:26:46Z, 10.2 s, about USD 0.00005). The personal key
   the owner gave for development and production testing, `noEnv`, `small`,
   `ttlSeconds` 1200, `visibility: private`, `org` Antiek. The create answer
   carried `team.id` Antiek, `environment: null`, `visibility: private`,
   `holdsCreatorLogins: false`. Inside: Ubuntu 24.04.4, kernel 6.8, systemd
   255 on cgroup2, passwordless `sudo` for `user`, `fs.protected_hardlinks = 1`,
   coreutils 9.4 (`env -C` works), util-linux `setsid --wait`, procps-ng
   4.0.4, iptables 1.8.10 (nf_tables), `python3` present.
   `setsid --wait timeout -k 5 2 sleep 30` returned 124 after 2.0 s. A system
   account under `-I OUTPUT 1` owner REJECT rules (both families, both `-C`
   checks 0) got no HTTPS answer from example.com while `user` got 200.
   `pkill -KILL -U` reaped a detached `setsid` child (1 process, then 0).
   `chmod -R go-w` did not follow a symlink out of its tree. `GET /files`
   answered 200 for a root-owned `0600` file (it reads with root's access [I]); `PUT /files` left a
   `user:user 0644` file. A synchronous `seq 1 2000000` came back as the
   last 8,388,608 bytes with `stdoutTruncated: true`: Boat keeps the tail.
   DELETE answered 202 twice; a GET then answered 404.
3. **Credential-surface probe** (`boat-credential-surface-probe-20261109.json`,
   `bx_x6zhp53w`, 08:27:43Z to 08:27:46Z, 3.9 s, about USD 0.00002), same
   settings. `~/.config/ascii/boat/config.json` exists in a `noEnv` VM:
   63 bytes, fields `api_url` and `channel` only, and `boat info` there
   answered 401. The `channel` value (10 characters) begins like
   `^(boat|ascii|sk)[_-]`, as the probe's own classifier flagged, but is far
   too short to be a key. `~/.claude/` held only `skills`, `~/.codex/` only
   `config.toml` and `skills`; none of the four other credential files
   existed. `GET /files` also answered 200 for a root-only file through a
   symlink in `/home/user`. DELETE answered 202 twice; a GET then answered 404.

**Finding, fixed.** Runs 2 and 3 showed that Boat writes the CLI config into
a `noEnv` VM. Module `bb49ebe3` refused any such file, so it would have
refused every workspace if a safe environment does the same [I]. The module now
counts the file as a credential only when it is a symlink, not a readable
regular file, carries a field other than `api_url`/`channel`, or holds a
key-shaped string (module `48d92441` at the time; the guard is unchanged in
`7d6330ab`). The test VM now carries the measured keyless file. Twenty new
cases (replacing one) cover accepted and refused shapes. A mutation run
against the tests of that time (`boat-backend-cfgguard-mutants-20261109.txt`,
module `48d92441`) caught 11 of 12 mutants of the guard: 11 CAUGHT and 1
SURVIVED. The survivor, M8, turns the unreadable-read fallback open; the
branch before it already refuses any unreadable or non-regular path, so that
mutant changes nothing a test can observe. That revision's suite was 283
passed and 1 Docker skip on this host; the cloud CEO's run of it gave 142
passed and 142 skipped (next section). Runs 2 and 3 answer most of what the
module's "docs are silent" list called unknown about the image and the files
API; whether `pkill` matches zombies remains open (round 2 makes an
unfinished reap fail closed), and G3.2 Part A still has to run the module
itself.

## Review of PR #3826 and round 2

The cloud CEO verified the first handoff independently (PR #3826, head
`21b0db5`, backend SHA-256
`48d924412b7d82742dda6ef19ef5adc901dfd6bd1e7c58539c323950db0618d8`) and
requested changes [M, the cloud CEO's review of PR #3826]. Its run of the
requested backend suite, with the Boat keys and org unset, gave **142 passed and 142
skipped**: 141 Boat fake-VM cases skipped because their fixture needed a
`/tmp` path that the cloud's mandatory `/opt/data/cache/scratch` cannot give,
and one skip is the unavailable Docker integration test. It therefore did
not accept the 283-pass claim. It ran no live Boat call. It raised three
standards/security findings (S1 credential guard bypass, S2 reaping fails
open, S3 uncertain exec cleanup missing) and six spec/doctrine findings (D1
stale Omarchy rule, D2 incorrect history, D3 build activation missing its
doctrine dependency, D4 incomplete spend bound, D5 snapshot prohibition not
enforced, D6 unbounded diagnostic instruction).

Round 2 answers them. In code (the code lane; module now `7d6330ab`): S1,
S2, S3, D4 and D5 as "What `BoatBackend` does today" describes them, and
test portability: the fake VM maps the VM's `/tmp` and `/home/user` onto
directories under each test's `tmp_path`, so no case needs a `/tmp` path.
The adapter stays dark: `factory.py` and `__init__.py` are untouched and the
factory's kinds are still `docker` and `local`. In this record and the
runbook: D1 (Context, Decision §8, the gates, checklist line 4, open
sign-offs 2 and 5, the runbook's "Credentials"), D2 (the header and
Context), D3 (Decision §1 and §6, the gates, checklist line 7, the runbook's
"Enable and activation"), D4 (Decision §7, the runbook's "Watching spend")
and D6 (the runbook's Part A). The five activation gates the review keeps
open stay open, and so does the module's own sixth (Decision §5 item 11).

Measured on this host on 2026-11-09 against module `7d6330ab` and tests
`8f202043`, with `BOAT_API_KEY`, `BOAT_BUILD_API_KEY` and `ANTIEK_BOAT_ORG`
unset, for `pytest tests/test_exec_backend_*.py` (381 cases, 284 of them
Boat):

- under pytest's default basetemp, under `/tmp`: **380 passed, 1 skipped**,
  the skip being the Docker integration test (`test_exec_backend_docker.py:469`,
  no daemon), in one run by the code lane at 11:17Z. The docs lane's own
  full run at about 11:22Z hit the per-user `/tmp` quota (247 passed, 134
  errors, `Disk quota exceeded`) while earlier pytest basetemps sat in
  `/tmp` (about 4.1 GB under `/tmp/pytest-of-slimydog` when measured at about
  12:00Z), so it was rerun in five chunks (96 passed and 1 skipped, then 78,
  76, 56 and 74 passed);
- under a basetemp outside `/tmp`: **380 passed, 1 skipped**, the same skip,
  in one run;
- `tests/test_exec_backend_boat.py` alone: 284 passed and none skipped in one
  run outside `/tmp`; under `/tmp` only as the four class chunks above (78,
  76, 56 and 74);
- ruff 0.15.20 check and format clean on the two Boat files, and mypy
  `Success: no issues found in 7 source files` for `runtime/exec_backend/`
  and the Boat tests.

These are this host's counts, not a cloud re-run; the review's test
acceptance needs the cloud's own run.

Mutation receipts, all made on this host by in-place mutation with a
byte-exact restore, and none reproduced in the cloud:

- `boat-backend-cfgguard-mutants-20261109.txt` (module `48d92441`): 11 of 12
  mutants of the CLI-config guard caught (above).
- `round2-code-mutants-20261109.txt` holds two runs. The first, on module
  `8d3f0876` with the 244-test file: the control passed, and all 17 mutants
  of the S1, S2, S3, D5 and D4 guards (M1 to M17) were caught. The second, on
  the current module `7d6330ab` and tests `8f202043`: the control passed 284;
  five reviewer mutants (P1 to P5: the cleanup never waiting for the exec
  lock, a cleanup without the lock still reporting clean, an answer without
  the wrapper trailer counted as clean, the accepted line no longer
  deduplicated, `WorkspaceLost` swallowed behind an unclean workspace) all
  survived the pre-fix 244-test file; against the current file all 35
  mutants (P1 to P5, the log-echo, duplicate-environment and read-back
  guards N1 to N13, and M1 to M17 again) were caught. The receipt records
  the module restored byte-exact after every mutant and the tests file restored byte-exact.

### Follow-up after round 2 (the orchestrator)

Round 2's fix stages received the review findings cut short, so a few
reviewer points never reached them; the orchestrator applied them after
the workflow, and the module moved from `7d6330ab` to `ac778a27` (tests
`8f202043` to `43b44faf`):

- **Values from success answers are scrubbed** wherever they reach an
  exception or a WARNING ("What `BoatBackend` does today", "Credentials").
  Before, a key Boat echoed in, say, `blockedReason`, a record's
  `environment` or a command's stderr reached the message, and taking the
  last 400 characters of a stderr first could keep the key's tail
  (`3456789abcdefABCDEF` of the test key, seen against `7d6330ab`). A
  two-lens read-only review of the first draft of this follow-up (module
  `53e1fc0f`) found two more paths, both older than the draft: the
  readiness answer's own sandbox id reached four refusals whole, and
  `proxyAiCredentials` was cut to 40 characters but never scrubbed, keeping
  all of a key but its last 4. It also found five values parsed from command
  output, and an error answer's other key-shaped runs, unscrubbed. All are
  fixed; against `53e1fc0f` the 14 new tests of those fixes fail, each on a
  leaked key or a piece of one.
- **A timed-out fake-VM command dies with its process group**, so no child
  left in the command's group outlives it (one moved out with `setsid` is
  left to the reap); a self-test of the fake pins it.
- **`ANTIEK_REQUIRE_FAKE_VM=1` makes a missing fake-VM tool a failure**, not
  a skip, so an acceptance run on a host without util-linux `flock` or
  `setsid --wait` cannot pass by skipping. With the tools probe forced off,
  `tests/test_exec_backend_boat.py` gave 89 passed and 232 skipped without
  the switch and 89 passed and 232 errors with it.
- The module docstring now says that `BoatBackend deleted sandbox` is
  written for every delete Boat accepted through `destroy()`, including the
  one after a failed provisioning, as this record already said; the
  runbook's Part A row names the exec refusal `no_lock`.

Measured on this host against `ac778a27` and `43b44faf`, keys and org
unset and `ANTIEK_REQUIRE_FAKE_VM=1`: `pytest tests/test_exec_backend_*.py`
gave **417 passed, 1 skipped** (the Docker test) under the default basetemp
in `/tmp` and the same outside `/tmp`; the Boat file has 321 cases, none
skipped; ruff, ruff format and mypy are clean. The receipt
`round2-echo-scrub-mutants-20261109.txt` records 35 of 35 in-place mutants
caught (K1 to K35: 34 of the scrub in the module, one of the fake's group
kill), with both files restored byte-exact after each; it replaces the first
draft's run (17 of 17 on `53e1fc0f`).

### Round 3: the re-review of v2 (`d0b2e85aa`)

The cloud CEO applied v2 as one commit, `d0b2e85aa`, on the PR branch and
reran the acceptance on its own host: 417 passed and 1 skipped (the Docker
test) with `ANTIEK_REQUIRE_FAKE_VM=1` and its mandatory scratch outside
`/tmp`, 321 Boat cases with no skip, ruff, ruff format and mypy clean, every
docs check passing and the ops kit 203 OK [M, the cloud CEO's review of PR
#3826]. Its re-review still requested changes, and it published them with
their citations in the PR body. Round 3 answers each (module `f05833d1`, tests
`1fb2d33a`):

- **S3, P2.** A success answer without the wrapper's trailer now settles
  under the shielded cleanup before the `exec` raises, on both dispatch
  paths, stopping a known detached command first (a `lost` status
  included), and leaves the workspace unclean when that settle cannot be
  confirmed ("What `BoatBackend` does today").
- **D1.** Open sign-off 5 no longer reopens the Omarchy permission, which
  the cloud CEO's SOUL's current section settles; only where the plane keys
  may be stored stays the owner's (Context, open sign-offs 2 and 5, the
  runbook's "Credentials").
- **D5.** A sandbox none of whose records carries `snapshots` is refused
  and deleted, with or without the org pin; either record saying `false` is
  enough.
- **1, gate consistency.** Decision §5 "Prerequisites by gate" is the one
  place each item and gate closes, per plane. A failed or incomplete G3.2
  Part A or B blocks G2 and cannot be waived there, and env-scoped live
  acceptance is never accepted in writing.
- **2A to 2E, guarantees.** The configured environment and the optional org
  pin are stated as the code holds them; termination is claimed only for a
  confirmed cleanup; sandbox teardown does not certify Boat's retained
  history; when `GET /limits` cannot be read there is no client-side
  `canStart` check (the module's WARNING now says so, with or without a
  pin); and the accepted line covers the sandbox ids the process learns,
  not every create.
- **3, build accounting.** The minimal option the review offered: the build
  figure is always incomplete, its unmatched count is a warning heuristic,
  and every intent row is reconciled with its own outcome before any
  further build create.

Measured on this host against `f05833d1` and `1fb2d33a`, keys and org unset and
`ANTIEK_REQUIRE_FAKE_VM=1`: `pytest tests/test_exec_backend_*.py` gave
**429 passed, 1 skipped** (the Docker test) under the default basetemp in
`/tmp` and the same outside `/tmp`; the Boat file has 333 cases, none
skipped; ruff, ruff format and mypy are clean. Against `d0b2e85aa`'s module
the new S3 and D5 tests fail, each for its intended reason. The receipt
`round3-mutants-20261109.txt` records 45 of 45 in-place mutants caught (K1
to K45), with both files restored byte-exact after each. Two read-only
review lenses, one on the code and tests and one on the doctrine, checked
round 3 against the cloud CEO's citations before the handoff, and this
revision carries their points.

The cloud CEO applied round 3 unchanged as `6662ee87` and reran the same
checks in the cloud with the same results (429 passed and 1 skipped, 333
Boat cases with no skip, the docs checker and the runbook suites passing,
the ops kit 203 OK). Its re-review found no remaining code finding (S3 P2
and D5 closed for source review) and one runbook sentence that dropped the
Parts A and B qualifier from the G2 rule [M, the cloud CEO's review of PR
#3826]. This revision makes that sentence read "a failed or incomplete
G3.2 Part A or B blocks G2 and cannot be waived there; Part C gates build
activation only", and qualifies the same way every other place that named
G3.2 as a whole where Parts A and B are meant. The mutation campaign and
the comparison against `d0b2e85aa` were not re-run in the cloud.

## Evidence

- Live receipts of 2026-11-09 ("Live evidence"): `boat-backend-live-smoke-20261109.json`,
  `boat-primitives-probe-20261109.json`, `boat-credential-surface-probe-20261109.json`,
  `boat-backend-cfgguard-mutants-20261109.txt`, and the scripts that made them
  (`live_smoke_boat_backend.py`, `live_primitives_probe.py`, `live_credprobe.py`).
- Round 2 ("Review of PR #3826 and round 2"): the cloud CEO's review of draft
  PR #3826, as its PR body captures it (the body names the manager record
  `/opt/data/antiek/operations/boat-backbone-2026-11-09.json`, which no lane
  read); the receipt
  `round2-code-mutants-20261109.txt`, `round2-echo-scrub-mutants-20261109.txt` and
  `round3-mutants-20261109.txt`; the cloud CEO's v2 re-review, as the PR #3826 body
  publishes it;
  this host's test runs on modules `7d6330ab`, `ac778a27` and `f05833d1`.
- Orchestrator measurements of 2026-11-09, read-only, Boat CLI 1.0.96 and the
  REST API: `GET /limits`, `boat org list` and `boat list` at about 06:27Z,
  after the payment of about 06:25Z (`periodEnd` 2026-12-09T06:25:35Z);
  earlier trial-era reads, now historical; the cloud CEO's install, environment
  and cron facts; the Omarchy facts.
- Boat documentation saved 2026-11-09: `pricing.md`, `limits.md`,
  `free-trial.md`, `security.md`, `hosting_firewall.md`, `concepts.md`,
  `api-keys.md`, `api-keys_scopes.md`, `environments_access.md`, `ci.md`,
  `recipes_parallel-agents.md`, `snapshots_stop.md`,
  `long-running-tasks_auto-stop.md`, `api_v1.md`, `llms.txt`, `LIVE_SHAPES.md`;
  the OpenAPI contract `boat-v1.yaml` (`CreateSandboxRequest`, `LimitsFields`,
  `/limits`, `/sandboxes`, `/api-keys`, `/api-keys/{apiKeyId}/rotate`, the
  `org` and `X-Boat-Org` parameters).
- This repository at `79b66b1`: `CLAUDE.md`; `docs/master-product-spec.md` §16;
  `docs/decisions/aws-production-and-agent-backbone-2026-10-07.md`;
  `docs/decisions/s16-research-fanout-exemption.md`;
  `infrastructure/terraform-aws/README.md` (cost table);
  `infrastructure/runbooks/lane-host.md`, `remote-exec-fanout.md`;
  `runtime/exec_backend/{interface,factory,__init__}.py` and the uncommitted
  `boat_backend.py`; `runtime/research_runner/{contained_gather,host_local}.py`;
  `runtime/remote_exec/daytona.py`; `interfaces/research/api/cascade_routes.py`;
  `tests/test_exec_backend_interface.py`, `tests/test_cascade_exec_backend_wiring.py`,
  `tests/test_remote_exec_provider_registry.py`; `substrate/constants.py:141`.
