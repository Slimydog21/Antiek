"""Boat backend: one disposable Boat cloud VM per workspace. DARK, not registered.

``BoatBackend`` is an ``ExecutionBackend`` whose workspaces are Boat sandboxes
(https://boat.dev): full Linux virtual machines with their own kernel, disk
and IP address, created and driven over Boat's public REST API (OpenAPI
``boat-v1.yaml``, server ``https://boat.dev/api/v1``). It satisfies the same
frozen ``ExecutionBackend`` / ``Workspace`` protocols as
``LocalProcessBackend`` and ``DockerBackend``, so a consumer swapping
``docker`` for ``boat`` would change one construction site and nothing else.

Plane
-----
This module is the PRODUCT plane: Boat as compute *inside* the Antiek product.
Both planes bill the one Boat subscription of the Antiek organization; they
differ by key and by environment, and never share either:

* PRODUCT (this module): key ``$BOAT_API_KEY``, an owner-minted ``ci``-preset
  key limited with ``--env`` to the environment ``antiek-product``.
  Workspaces are created in ``$ANTIEK_BOAT_ENVIRONMENT`` (default
  ``antiek-product``).
* BUILD (not this module): boxes that build, test and run CI for Antiek, in
  the environment ``antiek-build`` with the key ``$BOAT_BUILD_API_KEY``.

There is no credential fallback between planes: this module reads
``$BOAT_API_KEY`` and nothing else, never the build key, and it refuses
``antiek-build`` as its environment.

Status: DARK
------------
CLAUDE.md §16 rejects external execution vendors except the ratified
research-fanout exemption (``docs/decisions/s16-research-fanout-exemption.md``),
which names Daytona behind ``RemoteExecProvider`` and nothing else. This
module is therefore not registered in ``factory.py``, not re-exported from the
package ``__init__``, and imported by no production module.
``tests/test_exec_backend_boat.py`` pins the factory's valid kinds to
``{"local", "docker"}`` so wiring Boat in is a deliberate, visible flip, the
precedent ``runtime/remote_exec/prime_exec.py`` set.

Activation (after ratification)
-------------------------------
Wiring this backend in needs an operator-ratified amendment to CLAUDE.md §16
(drafted in ``docs/decisions/boat-compute-backbone-2026-11-09.md``). Until it
is ratified nothing below may be applied. The ratification PR applies exactly
this diff to ``runtime/exec_backend/factory.py``::

    --- a/runtime/exec_backend/factory.py
    +++ b/runtime/exec_backend/factory.py
    @@
    -_VALID_KINDS: frozenset[str] = frozenset({"local", "docker"})
    +_VALID_KINDS: frozenset[str] = frozenset({"local", "docker", "boat"})
    @@ def build_execution_backend(
             backend = DockerBackend()
             backend.probe()
             logger.info("ExecutionBackend selected: %s (via %s)", backend.name, selected_via)
             return backend

    +    if effective == "boat":
    +        # Local import, the docker branch's idiom: the default path never
    +        # loads the Boat adapter. probe() is the loud gate: a missing
    +        # BOAT_API_KEY, a wallet that cannot start sandboxes or an org-pin
    +        # mismatch (both when GET /limits is readable), or an environment
    +        # that passes account credentials raises BackendUnavailable here,
    +        # never a local backend wearing boat's name.
    +        from .boat_backend import BoatBackend
    +
    +        backend = BoatBackend()
    +        backend.probe()
    +        logger.info("ExecutionBackend selected: %s (via %s)", backend.name, selected_via)
    +        return backend
    +
         raise BackendUnavailable(

The same PR flips ``EXPECTED_FACTORY_KINDS`` in
``tests/test_exec_backend_boat.py`` to include ``"boat"``, replaces the
dark-module guards there with a factory test that mirrors
``TestFactoryDockerKind``, and records the amendment in ``docs/decisions/``
and the CLAUDE.md §16 exemption block.

Transport and the key
---------------------
Plain REST over ``httpx`` (already a core dependency); no Boat SDK, no new
dependency. The base URL defaults to ``https://boat.dev/api/v1`` and is
overridable with ``BOAT_API_URL`` (``https`` only, except loopback hosts).
``BOAT_API_KEY`` is read **at use time**, on every request, and travels only
in the ``Authorization: Bearer`` header. It is never logged, never placed in an
exception message (Boat's error text is scrubbed of it, and transport errors
are re-raised outside the original ``except`` block so no chained exception
carries it), and never put in a command, a file, a label or the sandbox
environment. The transport, the async ``sleep`` and the monotonic ``clock`` are
injectable; the test suite runs the whole lifecycle against an in-memory fake
behind ``httpx.MockTransport``. ``probe`` is synchronous and drives the async
client through ``asyncio.run``, the same contract as ``DockerBackend.probe``:
call it from a sync context.

Org pin
-------
``ANTIEK_BOAT_ORG`` (or ``org=``) optionally pins the billing organization. It
must be an organization **id** (``team_...``): Boat reports the wallet it read
as ``teamId`` (``GET /limits``) and the wallet a sandbox bills as ``team.id``
(``Sandbox``), both ids, so only an id pin can be compared; a name pin is
refused rather than half-checked. The pin is sent as ``X-Boat-Org`` on the
three operations that take it (``GET /limits``, ``GET /sandboxes``,
``POST /sandboxes``); per Boat's key docs an organization key asked for
another organization answers ``403 api_key_org_mismatch``, and an account key
bills the named organization. It is then verified twice: ``probe`` compares
``GET /limits`` ``teamId`` with the pin (when the key may read ``GET
/limits``), and ``create`` compares the new
sandbox's ``team.id`` with the pin (deleting the sandbox on a mismatch, or
when no read of it carried ``team``).

Provisioning (``create``)
-------------------------
* ``ResourceLimits`` map to the smallest Boat machine type whose vCPU, memory
  and documented disk all cover ``cpu_cores`` / ``memory_mb`` / ``disk_mb``:
  ``small`` 2/4096, ``default`` 4/8192, ``large`` 8/16384, ``xlarge``
  16/32768 (disk 51/51/111/251 GB per ``pricing.md``, "the space for your own
  files"). Anything larger is refused with ``WorkspaceProvisionError`` naming
  the limit, before any network call.
* ``wall_clock_s`` becomes ``ttlSeconds`` (Boat's auto-stop, which counts
  from creation; clamped to 60 s .. 30 days), so an abandoned workspace stops
  by itself. Sandboxes are always created with ``snapshots: false``: the
  proposed product doctrine keeps snapshots off, so the constructor has no
  override (passing ``snapshots=`` is a ``TypeError``). Per the OpenAPI that
  makes a stop erase the disk "the way zero data retention does": an
  abandoned workspace leaves no snapshot behind (I6). The ``Sandbox``
  record's ``snapshots`` ("False when the sandbox was created with snapshots
  off") is read back: a record that carries it with any value but ``false``
  is refused and the sandbox deleted, and so is a sandbox whose create and
  readiness answers both leave it out, since snapshots off could then not be
  verified. The OpenAPI does not list the field as required, but both
  2026-11-09 live ``Sandbox`` shapes (``LIVE_SHAPES.md``) carry it.
* ``environment: <ANTIEK_BOAT_ENVIRONMENT>`` (default ``antiek-product``).
  ``noEnv`` is deliberately **not** sent: per the OpenAPI a ``noEnv`` sandbox
  is attached to no environment (``Sandbox.environment`` is null), which would
  put it outside a key limited with ``--env``. No account secrets or agent
  logins may reach the VM; that is verified, not assumed (see "Credentials").
* ``visibility: "private"``, labels ``antiek-workspace=<id>`` and
  ``antiek-profile=<profile>``, an ``Idempotency-Key`` derived from the
  workspace id, and the name ``antiek-ws-<profile>-<8 hex>``.
  ``profile.env`` is applied explicitly to every ``exec`` (see below), not
  through Boat's create-time ``env``, because the workload environment is
  scrubbed and would never see it.
* ``GET /sandboxes/{id}`` is polled until ``ready``/``idle``/``running``
  (api_v1.md "Recommended flow") with a bounded deadline (``ready_timeout_s``,
  default 180 s). Timeout, a failed state (``error``, ``cancelled``,
  ``archiving``, ``archived``), a 404, any later provisioning failure, or a
  cancellation of ``create`` deletes what was created and re-raises; the
  delete runs shielded, so a second cancellation cannot interrupt it.
* A create whose answer was lost (a 5xx, a dropped connection after the
  request went out, a cancellation while ``POST /sandboxes`` was in flight)
  is recovered the documented way before raising: the same ``POST`` with the
  same ``Idempotency-Key`` and body returns the sandbox bound to that key
  (``409 idempotency_in_progress`` while it is still minted: wait and ask
  again, at most 3 times), which is then deleted. A label sweep follows as a
  second net (only a sandbox carrying this workspace's label that this caller
  owns is deleted, never a teammate's). A connection that was never
  established skips the re-``POST`` (Boat cannot have seen it). When the
  first request never reached Boat, the re-``POST`` itself may create the
  sandbox; it is deleted the same way, at the cost of one start.
* One provisioning command checks the credentials, checks that the kernel
  protects hardlinks (``fs.protected_hardlinks = 1``; see "Execution"),
  creates the workload account ``antiek-runner`` (a system account, no sudo,
  no home) and the workspace root ``<root_base>/<id>/`` with the conventional
  ``in/``, ``out/`` and ``work/`` dirs, plus a ``<id>.ctl/`` control dir (mode
  0700, owned by Boat's ``user`` account) for stdin and output spool files,
  the exec lock and the fence files (see "Execution").
  ``root_base`` (default ``/tmp/antiek-ws``) must lie under ``/tmp`` or
  ``/home/user``, because the files API accepts nothing else
  (``FileWriteRequest.path``).

Credentials
-----------
The product environment must pass nothing of the account into a sandbox
(Boat's "Safe for third parties"). Three checks, each loud:

1. ``probe`` and every ``create`` (before ``POST /sandboxes``, so nothing is
   billed) read ``GET /environments?org=<pin>`` and refuse an environment
   that is not "safe for third parties" while any of ``passGithub``,
   ``passSecrets``, ``passSandboxCredentials``, ``passAgentsCredentials`` is
   not ``false``, and, whatever ``safeForThirdParties`` says, an environment
   whose ``proxyAiCredentials`` (AI-credential placeholders) is present and
   not ``false``. The OpenAPI ``SandboxEnvironment`` lists the four ``pass*``
   flags as required but not ``proxyAiCredentials``, so an environment
   without that field is accepted on it; a present value that is not the
   boolean ``false`` (``true``, ``null``, a string) is refused.
   This read fails closed: an environment missing from the listing, listed
   more than once under its name (which one a create by name uses is not
   documented, so no one entry's flags can stand for it), or a key whose
   scope may not read it (``403 api_key_action_forbidden`` /
   ``api_key_sandbox_forbidden``), is refused with ``BackendUnavailable``,
   because nothing inside the VM can see secrets whose names the owner chose
   (``passSecrets``). Only these flags are read; ``envContents`` is never
   logged or kept.
2. ``create`` refuses a sandbox whose record says ``holdsCreatorLogins: true``
   or names another ``environment``.
3. The provisioning command runs Boat's own documented check (``security.md``
   "Check a sandbox"; ``environments_access.md`` "What a normal sandbox
   receives") inside the VM: none of ``~/.git-credentials``,
   ``~/.config/gh/hosts.yml``, ``~/.claude/.credentials.json``,
   ``~/.codex/auth.json`` may exist; ``~/.config/ascii/boat/config.json`` (the
   in-sandbox boat key's home) may hold only ``api_url`` and ``channel``,
   because Boat wrote that keyless file into both ``noEnv`` VMs measured on
   2026-11-09 (inferred for a safe environment);
   and none of ``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``,
   ``CLAUDE_CODE_OAUTH_TOKEN``, ``CHATGPT_ACCOUNT_ID``, ``GH_TOKEN``,
   ``GITHUB_TOKEN`` may be set. Only the names found are reported, never a
   value. This is a spot check of the fixed names the docs list; check 1 is
   the one that covers user-named secrets.

A failure of any of them deletes what was created (if anything) and raises
``BackendUnavailable`` (a configuration error a retry cannot fix).

Execution (``exec``, I1 and I7)
-------------------------------
Boat's agent runs commands as ``user``, which has passwordless sudo. Workload
code never runs as ``user``: every ``exec`` sends one POSIX ``sh`` wrapper
that

1. takes the workspace's exec lock (``flock`` on ``<id>.ctl/lock``; one
   wrapper at a time in the VM: it waits at most 5 s, then refuses with
   ``busy``), exits without running anything if its fence file exists (see
   "Interrupted exec" below), kills anything still running as
   ``antiek-runner`` (nothing should be; see step 4) and refuses to start
   unless that reap is confirmed (status ``reap_failed``), and, under
   ``DENY_ALL``, re-checks that the owner REJECT rule is still the first
   ``OUTPUT`` rule for both address families, refusing to run if it drifted;
2. hands the workspace tree to ``antiek-runner`` (``chown -hR``, never
   following symlinks), resolves the requested ``cwd`` with ``realpath`` *as
   the runner* and refuses one that escapes the root (a symlink planted by an
   earlier step), mirroring ``local_process``'s ``_jailed``;
3. runs ``sudo -n -u antiek-runner -- env -i -C <cwd> PATH=.. LANG=..
   HOME=<root> <profile env> <exec env> setsid --wait timeout -k 5 <T> argv``.
   Every argv element and env assignment is ``shlex.quote``-d, so spaces,
   quotes, ``$``, backticks and newlines arrive verbatim. ``env -i`` scrubs
   everything the VM's environment carries (``ASCII_TOKEN``, ``BOAT_ID``, ..).
   ``setsid`` gives the workload its own session and ``timeout`` its own
   process group; at ``T`` the whole group gets TERM and, 5 s later, KILL.
   stdin is a file written through the files API into the control dir and
   opened by the wrapper (the workload inherits the descriptor, it cannot
   read the control dir);
4. spools stdout/stderr to files in the control dir, then, whether the
   workload exited or timed out, kills every remaining ``antiek-runner``
   process (real or effective uid, repeated until ``pkill`` reports that
   nothing matched; the account exists only for this workspace). A confirmed
   reap establishes that nothing the workload started outlives its ``exec``;
   an unconfirmed one claims nothing and leaves the workspace unclean
   ("Unclean workspace"). One process tree per ``exec``, no reuse (I7);
5. gives the tree back to ``user`` (``chown -hR``) and strips group/other
   write and set-id bits (``chmod -R go-w,ug-s``; the group bits are the ACL
   mask, so a named-user ACL entry loses write too), so no path in the tree
   is writable by the runner between calls. It then prints at most
   ``MAX_OUTPUT_BYTES + 1`` bytes of each stream (so Boat's own 8 MiB
   per-stream cap can never cut the result) and a trailer carrying the exit
   code, the timed-out flag, the true stream sizes and whether steps 4-5
   completed.

``chown -hR`` changes the owner of a hardlink's target, which lives outside
the tree too; with ``fs.protected_hardlinks = 1`` the runner can only
hardlink files it owns or may already read and write, so the handoff gives it
nothing new. Provisioning refuses a VM without that setting.

The reap fails closed. ``pkill`` runs inside a root ``sh -c`` that prints
its exit status, so sudo's own failure (also status 1) cannot pass for
``pkill``'s "no process matched" (1). Status 0 (something was signalled)
repeats the round; 1 for both selectors (``-U`` and ``-u``) confirms the
reap; anything else (2 syntax error, 3 fatal error, 127 missing tool,
128+n killed by a signal, no status printed because sudo refused) is an
error that ends the reap unconfirmed at once, as does a reap still finding
processes after 50 rounds, 0.1 s apart. Unconfirmed at the start of an
``exec``, it refuses the workload (nothing has been handed to the runner);
at the end, the tree is still taken back and the trailer's clean flag is 0.

A workspace serves one ``exec``, ``put_file`` or ``get_file`` at a time:
calls queue on a per-workspace lock, because steps 1, 4 and 5 act on the
whole account and the whole tree. ``destroy`` does not queue.

Interrupted exec. When an ``exec``'s wrapper may still run, or may still
start, while this host no longer waits for it (a lost answer: a 5xx, or a
transport failure after the request may have left; a success answer without
the wrapper's trailer, on either dispatch path; a cancellation of the
caller; anything else raised once the request was sent), the ``exec`` runs a
cleanup before it releases the lock. For a detached command whose
``processId`` is known it first stops it (``DELETE /commands/{processId}``).
Then one cleanup command writes the fence file ``<id>.ctl/<nonce>.cancel`` of
every interrupted exec (a wrapper that has not taken the exec lock yet finds
it there and runs nothing), waits for the exec lock while reaping (a wrapper
that holds it sees its workload killed and finishes), and, holding the
lock, reaps and restores. Only a cleanup that got the lock and confirmed the
reap and restore counts. It runs shielded: a cancellation that lands while it
runs returns at once, but the cleanup keeps running and the next call on the
workspace waits for it before anything else. A command Boat refused (4xx) or one that never
left this host (no connection was made) needs none. The API-level timeouts
(a synchronous ``timedOut: true``, the detached backstop) run the same
cleanup.

Unclean workspace. If an ``exec`` ends without confirming steps 4-5 (a
trailer whose clean flag is 0, a refused start, a lost or trailerless
answer whose immediate cleanup could not be confirmed), the workspace is marked unclean: every later
``exec``, ``put_file`` or ``get_file`` first re-runs the cleanup and is
refused (``ExecutionBackendError``, "could not be taken back") until one is
confirmed. This module does not destroy the workspace on its own (I6: the
caller owns ``destroy()``, which always works); a caller that cannot wait
destroys it.

A ``timeout_s`` whose wrapper budget (``ceil(timeout_s) + 20`` s) fits Boat's
600 s synchronous cap (``CommandRequest.timeoutSeconds``, 1-600) uses
``POST /commands``; a longer one starts the wrapper with ``detached: true``
(no time limit) and polls ``GET /commands/{processId}``, with a host-side
deadline that stops the command (``DELETE /commands/{processId}``) and cleans
up if the in-box timeout somehow did not fire. A synchronous answer with
``timedOut: true`` gets the same cleanup. The result is a structured
``ExecResult``: ``timed_out=True`` with ``exit_code=-1`` on timeout, streams
capped at ``MAX_OUTPUT_BYTES`` with ``truncated=True``, ``duration_ms``
measured host-side. A missing binary or ``cwd`` returns exit 127, the shell's
"not found" convention ``LocalProcessBackend`` uses.

Net policy (I4)
---------------
* ``ALLOW_ALL``: honored; the VM's outbound default is open.
* ``DENY_ALL``: Boat has no API network rules (``hosting_firewall.md``), so
  the rule is enforced inside the VM the way that page prescribes for
  untrusted code: a separate Linux account without sudo, and an owner rule
  inserted at the top of ``OUTPUT`` (``-I OUTPUT 1``) for both ``iptables``
  and ``ip6tables``. ``user`` (Boat's agent and its WireGuard tunnel) is never
  matched. One deliberate tightening over the page's recipe: it also accepts
  loopback and established traffic for the runner; this backend does not,
  because loopback reaches in-VM services that run as ``user``, which has
  passwordless sudo. The rules are then **read back** with ``-S OUTPUT`` and
  verified (owner REJECT first in both families, matching the runner's
  numeric uid, the runner distinct from root and ``user``, no rule blocking
  ``user``, the runner unable to sudo). If applying or verifying fails, the
  sandbox is deleted and ``NetPolicyUnsupported`` raised. Firewall rules are
  not kept in snapshots; this backend never resumes or forks, so that cannot
  bite.
* ``ALLOWLIST``: refused with ``NetPolicyUnsupported`` before any network
  call. Owner rules can match CIDRs but not hostnames, and resolving a
  hostname once into addresses would be an approximation, not enforcement.

Files
-----
``put_file``/``get_file`` take workspace-relative paths, rejecting absolute
paths and ``..`` escapes before any network call (same semantics as
``local_process``). A short in-VM ``realpath`` check then refuses a path
whose canonical form leaves the root through a symlink, and the transfer
itself goes through ``PUT``/``GET /sandboxes/{id}/files``, which the OpenAPI
says canonicalizes the path again. The check and the transfer are two API
calls, so the check only holds because nothing can change the tree between
them: the call holds the workspace lock (no ``exec`` runs), the last ``exec``
killed every runner process and left the tree owned by ``user`` with no
group/other write (a runner process started later, e.g. by ``cron``, still
cannot rename or replace anything in it), and an unclean workspace is cleaned
first (see "Execution"). Under those conditions a planted link is seen by the
check and refused. ``put_file`` also refuses a target that exists and is not
a regular file (a FIFO would block the write). Content moves with
``encoding: base64``, binary-safe, up to Boat's documented 5 MiB per file;
larger artifacts raise ``ExecutionBackendError`` rather than arriving
truncated.

Error taxonomy
--------------
Boat answers errors with the ``ErrorEnvelope`` (``status``, ``code``,
``message``, ``error{code,message,status,details}``, ``requestId``); the code
and ``requestId`` are carried into every message.

* ``BackendUnavailable``: missing or malformed ``BOAT_API_KEY``, a malformed
  org pin or environment name, HTTP 401, 402 (``billing_required``, ...), 403
  (``environment_forbidden``, ``api_key_*``, ``org_suspended``; machine-class
  refusals excepted), 400 ``unknown_environment``,
  ``trial_compute_limit_reached``, ``canStart: false`` (Boat's
  ``blockedReason`` is in the message), a ``GET /limits`` answer without the
  required ``canStart`` (shape drift), an org-pin mismatch, an environment
  that passes account credentials, whose flags cannot be read or whose name
  is listed more than once, a sandbox record that reports snapshots on, a
  sandbox none of whose records carries ``snapshots`` (or, under an org pin,
  ``team``), a VM that does not protect hardlinks.
* ``WorkspaceProvisionError``: oversize limits, 429 start/concurrency limits,
  503 capacity, 5xx and transport failures on create (and on its environment
  read), machine-class refusals (``trial_machine_class_not_allowed``,
  ``machine_class_plan_required``), ready timeout, failed provisioning.
* ``NetPolicyUnsupported``: ``ALLOWLIST``; ``DENY_ALL`` rules that could not be
  applied or verified, or that drifted before an ``exec``.
* ``WorkspaceLost``: the sandbox vanished mid-use (404) or has no machine any
  more (409 ``machine_not_running`` / ``sandbox_not_ready``, e.g. it hit its
  auto-stop), the workspace root vanished, or the workspace was destroyed.
* ``ExecutionBackendError``: anything else mid-use, including an ``exec``
  refused because its reap could not be confirmed (``reap_failed``), the
  exec lock is held (``busy``) or cannot be opened (``no_lock``), and any
  call refused on an unclean workspace.

``destroy()`` sends ``DELETE /sandboxes/{id}`` with the required
``X-Ascii-Confirm-Delete: <id>`` header; it is idempotent (a 404 or a second
call is a no-op) and never raises, logging loudly instead, like
``DockerBackend``. It works on an unclean workspace too.

Spend ledger lines
------------------
Each sandbox id this process learns is logged once at INFO on logger
``antiek.exec_backend.boat``, the moment it learns it, subject to the
process or its log delivery failing (a create answered without a usable
id, or lost while the process died, stays unlogged): when the create
answered (``via=create``), when the documented same-key re-``POST`` found it
after a lost answer (``via=repost``), or when the label sweep found it
(``via=sweep``)::

    BoatBackend sandbox accepted: sandbox=<bx id> workspace=<id>
    type=<machine type> ttlSeconds=<n> createdAt=<time> via=<how>

(one line in the log; wrapped here). Every confirmed delete is logged once,
``result=deleted`` for an accepted delete and ``result=not-found`` for a 404::

    BoatBackend sandbox deleted: sandbox=<bx id> workspace=<id>
    via=<destroy|orphan> result=<deleted|not-found>

``type``, ``ttlSeconds`` and ``createdAt`` are the ``Sandbox`` record's values
when it carries them (``createdAt`` is optional in the OpenAPI), the
requested type and TTL otherwise. Each is checked for its own shape before
it is logged: ``type`` must be one of the four machine type names,
``ttlSeconds`` an integer and ``createdAt`` an RFC 3339 date-time; anything
else is logged as ``unknown``. A sandbox that then fails provisioning was
still accepted (and billed), so it has an accepted line and, once deleted, a
deleted line, but no ``BoatBackend created workspace`` line. That line and
``BoatBackend deleted sandbox`` are kept unchanged for the existing ledger
parse; the first is written only for a fully provisioned workspace, the
second for every delete Boat accepted through ``destroy()``, including the
one after a failed provisioning. No line
carries the key, even from a server that echoes it in a success answer: of
what Boat returns, the ledger lines and the probe's ``BoatBackend ready``
line log only ids, machine type names, numbers and date-times, each checked
for its shape, and a key-shaped value (or one holding the current key) is
always logged as ``unknown``.

Where the docs are silent (and what this module does)
-----------------------------------------------------
* Combining ``noEnv`` with ``environment`` on create: undocumented; only
  ``environment`` is sent.
* Whether the ``ci`` preset carries ``account.read`` (``GET /limits``) and
  ``environment.read`` (``GET /environments``): ``api-keys_scopes.md`` does not
  list a preset's actions. A scope ``403`` (``api_key_action_forbidden`` /
  ``api_key_sandbox_forbidden``) on ``GET /limits`` is logged as a WARNING and
  ``probe`` goes on, because the per-create checks (the ``X-Boat-Org``
  header, the ``team.id`` read-back) still hold the org pin. The same ``403``
  on ``GET /environments`` is fatal (see "Credentials"): if the ``ci`` key
  cannot read its own environment, this backend cannot be used with it.
* ``environments_access.md`` names an ``effective`` field that shows what an
  environment's sandboxes really get; the OpenAPI ``SandboxEnvironment`` has
  no such field, so the documented rule ("safe for third parties" on means
  nothing passes, whatever the toggles say) is applied to the flags instead.
* Whether live ``GET /environments`` answers always carry
  ``proxyAiCredentials``: the OpenAPI does not list it as required and no
  live environments shape is recorded (``LIVE_SHAPES.md`` has none), so an
  environment without the field is accepted on it. ACTIVATION GATE: capture
  a live environments shape first; if it carries the field, refuse an
  environment that lacks it before this backend is wired in.
* Whether one ``GET /environments`` listing can hold two environments with
  the same name (personal and organization environments both exist, per
  ``ResourceAccess`` and the ``OrgId`` parameter text): not documented. Such
  a listing is refused (see "Credentials").
* ``GET /limits`` without ``canStart``: the OpenAPI marks it required; the
  2026-11-09 personal-key shape in ``LIVE_SHAPES.md`` lacks it. ``probe``
  refuses such an answer as shape drift, naming the missing field.
* How long after a failed create the ``Idempotency-Key`` is released ("within
  ~2 minutes"), and so whether a same-key re-``POST`` creates a new sandbox:
  not exact. Whatever the re-``POST`` returns is deleted.
* Whether ``pkill`` matches zombie processes in the Boat image: the reap loop
  repeats at most 50 times, 0.1 s apart, and an unfinished reap is
  unconfirmed (fails closed, see "Execution").
* Whether Boat's ``DELETE /commands/{processId}`` reaches a workload that
  ``setsid`` moved into its own session, and whether a synchronous command
  keeps running after its HTTP answer was lost: not documented, so neither is
  relied on; the reap and the fence files are.
* Whether live responses carry ``environment`` and ``holdsCreatorLogins``: the
  OpenAPI documents both, the 2026-11-09 read-only shapes (``LIVE_SHAPES.md``)
  show neither, so each is checked when present and the in-VM check is the
  one that always runs. ``team`` is in both, so the org pin requires it. The
  ``POST /sandboxes`` answer did carry ``environment``, ``holdsCreatorLogins``,
  ``visibility`` and ``team`` on 2026-11-09 (two ``noEnv`` probe VMs).
* Which shell runs a command string, and whether it is a login shell: the
  wrapper is plain POSIX ``sh`` and brackets its output with per-call markers,
  so banner noise from a login shell cannot corrupt a result.
* What the base image ships: the wrapper needs ``sudo``, ``useradd``,
  ``iptables``/``ip6tables``, GNU coreutils (``env -C``, ``timeout``,
  ``realpath``, ``date +%s%N``, ``head -c``, ``chmod``), util-linux
  ``setsid --wait`` and ``flock``, procps ``pkill`` and ``sysctl`` (or a
  readable ``/proc/sys/fs/protected_hardlinks``). A missing tool fails
  provisioning or the exec loudly (a missing ``pkill`` is status 127, an
  unconfirmed reap). Measured 2026-11-09 on a small VM (``bx_pqppjbcy``, a
  primitives probe, not this module): Ubuntu 24.04.4, kernel 6.8, systemd 255
  on cgroup v2, passwordless ``sudo`` for ``user``, every tool probed present
  (coreutils 9.4, procps-ng 4.0.4, iptables 1.8.10 nf_tables; ``realpath``,
  ``date +%s%N`` and ``flock`` were not probed), ``fs.protected_hardlinks = 1``;
  ``setsid --wait timeout -k 5 2`` returned 124 after 2 s; with owner REJECT
  rules at ``-I OUTPUT 1`` in both families (both ``-C`` checks 0) a system
  account got no HTTPS answer while ``user`` still got 200;
  ``pkill -KILL -U`` reaped a detached ``setsid`` child; ``chmod -R go-w`` did
  not follow a symlink out of the tree. Boat's own 8 MiB cap keeps the
  *tail* of a synchronous stream (``stdoutTruncated: true``), which the
  in-box ``head -c`` makes moot.
* How the files API treats symlinks: on 2026-11-09 ``GET /files`` answered
  200 for a root-owned ``0600`` file, so it reads with root's access [I], and
  answered 200 for a second root-only file through a link in ``/home/user``
  (another VM), so it follows symlinks; ``PUT /files`` left a ``user``-owned
  ``0644`` file. So the in-VM
  ``realpath`` check before every transfer, done while no runner process is
  alive and the tree is ``user``-owned without group/other write, is what
  confines file access to the workspace.
* How non-UTF-8 command output is encoded in the JSON answer: Boat returns
  strings; bytes are re-derived from them, so binary stdout is not exact.
  Use ``get_file`` for binary artifacts.
* A workload killed by a signal reports the shell's ``128 + n``, not
  ``LocalProcessBackend``'s ``-n``; only the timeout path maps to ``-1``.
* The command text (argv and env assignments, never the key) is kept in
  Boat's command history for 90 days (``POST /commands`` description), so a
  caller must not pass secrets through ``argv`` or ``env``.
* ``profile.image`` (a container image name) has no Boat equivalent; Boat
  boots its own VM image, so the hint is logged and ignored.
* Retries: none, except the documented same-``Idempotency-Key`` re-``POST``
  that only finds and deletes a sandbox whose create answer was lost. A
  command is never re-sent (a ``502`` may mean it already ran);
  ``409 sandbox_starting`` (prose) / ``boat_starting`` (OpenAPI) cannot follow
  a successful readiness wait except on an out-of-band restart, and surfaces
  as ``ExecutionBackendError``.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import contextlib
import logging
import math
import os
import posixpath
import re
import shlex
import time
import uuid
from collections.abc import Awaitable, Callable, Coroutine, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

import httpx

from .interface import (
    MAX_OUTPUT_BYTES,
    BackendUnavailable,
    ExecResult,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    WorkspaceLost,
    WorkspaceProfile,
    WorkspaceProvisionError,
)

#: Boat's public API base (OpenAPI ``servers``; api_v1.md).
DEFAULT_BOAT_API_URL: str = "https://boat.dev/api/v1"

#: Env var that overrides the API base URL.
BOAT_API_URL_ENV: str = "BOAT_API_URL"

#: Env var holding the PRODUCT-plane bearer key. Read at use time, never stored.
BOAT_API_KEY_ENV: str = "BOAT_API_KEY"

#: Optional org pin, an organization id (``team_...``), sent as ``X-Boat-Org``.
BOAT_ORG_ENV: str = "ANTIEK_BOAT_ORG"

#: Env var naming the Boat environment product workspaces are created in.
BOAT_ENVIRONMENT_ENV: str = "ANTIEK_BOAT_ENVIRONMENT"

#: The product plane's environment when ``$ANTIEK_BOAT_ENVIRONMENT`` is unset.
DEFAULT_BOAT_ENVIRONMENT: str = "antiek-product"

#: The build plane's environment. Refused here: planes never share anything.
BUILD_PLANE_ENVIRONMENT: str = "antiek-build"

#: Where workspace roots live inside the VM. Must sit under ``/tmp`` or
#: ``/home/user`` (the files API refuses anything else).
DEFAULT_ROOT_BASE: str = "/tmp/antiek-ws"

#: The VM directories the files API accepts (``FileWriteRequest.path``).
_FILES_API_ROOTS: tuple[str, ...] = ("/tmp", "/home/user")

#: The Linux account workload code runs as. Never ``user`` (passwordless sudo).
RUNNER_ACCOUNT: str = "antiek-runner"

#: Sandbox-name prefix; ``create`` makes ``antiek-ws-<profile>-<8 hex>``.
SANDBOX_NAME_PREFIX: str = "antiek-ws-"

#: Boat machine types, smallest first: (type, vCPU, memory MB, disk MB). vCPU
#: and memory from ``CreateSandboxRequest.type`` / ``pricing.md`` (2/4, 4/8,
#: 8/16, 16/32 GB); disk is ``pricing.md``'s "space for your own files" (51,
#: 51, 111, 251 GB), in the same 1 GB = 1024 MB convention as memory.
MACHINE_TYPES: tuple[tuple[str, int, int, int], ...] = (
    ("small", 2, 4096, 51 * 1024),
    ("default", 4, 8192, 51 * 1024),
    ("large", 8, 16384, 111 * 1024),
    ("xlarge", 16, 32768, 251 * 1024),
)

#: The machine type names, the only ``type`` values a log line carries.
_MACHINE_TYPE_NAMES: frozenset[str] = frozenset(name for name, *_ in MACHINE_TYPES)

#: Boat's cap on a synchronous ``POST /commands`` (``timeoutSeconds`` 1-600).
SYNC_COMMAND_CAP_S: int = 600

#: Boat's per-file cap on the files API read and write (413 above it).
FILE_API_CAP_BYTES: int = 5 * 1024 * 1024

#: TERM-to-KILL grace inside the VM, same value as ``local_process``.
_KILL_GRACE_S: int = 5

#: Budget for the wrapper's own work around the workload (chown, realpath,
#: spool reads) when sizing the API-level command timeout.
_WRAPPER_SLACK_S: int = 15

#: A command sent while a sandbox starts waits up to 60 s (api_v1.md).
_START_WAIT_S: float = 60.0

#: HTTP timeout for ordinary calls (file calls may wait up to 60 s too).
_HTTP_TIMEOUT_S: float = 90.0

#: API timeout for the short helper commands (path resolution, cleanup).
_HELPER_TIMEOUT_S: int = 60

#: API timeout for the provisioning command (credential check, ``useradd``, dirs).
_PROVISION_TIMEOUT_S: int = 120

_DEFAULT_READY_TIMEOUT_S: float = 180.0
_DEFAULT_POLL_INTERVAL_S: float = 2.0

#: Same-key re-``POST``s while Boat still mints a create whose answer was lost
#: (``409 idempotency_in_progress``), ``poll_interval_s`` apart.
_REDISCOVER_ATTEMPTS: int = 3

#: HTTP timeout for best-effort cleanup calls (lost-create recovery, sweep).
_CLEANUP_HTTP_TIMEOUT_S: float = 30.0

#: Rounds of "kill every runner process" (0.1 s apart) before the wrapper
#: reports an unfinished reap.
_REAP_ROUNDS: int = 50

#: How long an exec wrapper waits for the exec lock in the control dir
#: before refusing with ``busy`` (nothing else should hold it; see
#: "Interrupted exec").
_EXEC_LOCK_WAIT_S: int = 5

#: Rounds (each a reap and 0.1 s) a cleanup waits for an interrupted
#: wrapper to release the exec lock before it reports itself unconfirmed.
_CLEANUP_LOCK_ROUNDS: int = 200

#: Name of the exec lock, and suffix of a fence file, in the control dir.
_EXEC_LOCK_NAME: str = "lock"
_FENCE_SUFFIX: str = ".cancel"

#: Stable spend-ledger lines (see "Spend ledger lines"). Field names and
#: order are a contract for the ledger parse; only ids and plain tokens go in.
_ACCEPTED_LOG: str = (
    "BoatBackend sandbox accepted: sandbox=%s workspace=%s type=%s ttlSeconds=%s "
    "createdAt=%s via=%s"
)
_DELETED_LOG: str = "BoatBackend sandbox deleted: sandbox=%s workspace=%s via=%s result=%s"
_LOG_TOKEN_RE = re.compile(r"^[A-Za-z0-9._:+-]{1,64}$")
#: The OpenAPI ``format: date-time`` (RFC 3339), the only ``createdAt`` logged.
_DATE_TIME_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,9})?"
    r"(?:Z|[+-][0-9]{2}:[0-9]{2})$"
)

#: ``ttlSeconds`` bounds: a floor so a tiny ``wall_clock_s`` cannot auto-stop
#: the VM before it is ready, and Boat's maximum (2592000 s, 30 days).
_MIN_TTL_S: int = 60
_MAX_TTL_S: int = 2_592_000

#: The workload's whole inherited environment besides ``HOME`` and the
#: profile/exec variables.
_WORKLOAD_PATH: str = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
_WORKLOAD_LANG: str = "C.UTF-8"

#: Tolerance when deciding in the VM whether exit 124/137 came from the
#: timeout firing rather than from the workload itself.
_TIMEOUT_EPSILON_NS: int = 50_000_000

#: Credential files an environment that passes the owner's logins writes into
#: the home of ``user`` (environments_access.md, security.md). Relative to $HOME.
_CREDENTIAL_FILES: tuple[str, ...] = (
    ".git-credentials",
    ".config/gh/hosts.yml",
    ".claude/.credentials.json",
    ".codex/auth.json",
)

#: The boat CLI config in the home of ``user``, where the in-sandbox boat key
#: lives (api-keys_scopes.md). Boat wrote the file into both ``noEnv`` VMs
#: measured on 2026-11-09, so its presence proves nothing: in ``bx_x6zhp53w``
#: it held exactly ``api_url`` and ``channel`` (63 bytes) and ``boat info``
#: there answered 401; a VM of an environment marked safe for third parties is
#: inferred to match. It counts as a credential when it is a symlink, not a
#: readable regular file, holds anything but those two string fields, or holds
#: a key-shaped string. This rests on Boat never putting a credential under
#: ``api_url`` or ``channel``; a CLI or image update that adds a keyless field
#: makes every create fail loudly with this reason, and the field names (never
#: values) are what to inspect before widening the pattern.
_BOAT_CLI_CONFIG: str = ".config/ascii/boat/config.json"

#: The keyless shape of ``_BOAT_CLI_CONFIG`` once whitespace is stripped
#: (POSIX ERE for ``grep -Ex``): ``{}``, or only ``api_url``/``channel``
#: string fields; an escaped quote or any other field does not match.
_BOAT_CLI_CONFIG_KEYLESS_ERE: str = (
    r'\{\}|\{"(api_url|channel)":"[^"\\]*"(,"(api_url|channel)":"[^"\\]*")*\}'
)

#: A boat API key anywhere in a string (POSIX ERE; the same pattern in Python).
_KEY_SHAPED_ERE: str = r"boat_[A-Za-z0-9_-]{24,}"
_KEY_SHAPED_RE = re.compile(_KEY_SHAPED_ERE)

#: Credential variables the same pages name (model credentials). The docs say
#: "your GitHub token" without naming its variable; ``GH_TOKEN`` and
#: ``GITHUB_TOKEN`` are the two names ``gh`` reads.
_CREDENTIAL_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "CHATGPT_ACCOUNT_ID",
    "GH_TOKEN",
    "GITHUB_TOKEN",
)

#: ``SandboxEnvironment`` flags that pass something of the account in.
_ENV_PASS_FLAGS: tuple[str, ...] = (
    "passGithub",
    "passSecrets",
    "passSandboxCredentials",
    "passAgentsCredentials",
)

_READY_STATES: frozenset[str] = frozenset({"ready", "idle", "running"})
_FAILED_STATES: frozenset[str] = frozenset({"error", "cancelled", "archiving", "archived"})
_MACHINE_CLASS_CODES: frozenset[str] = frozenset(
    {"trial_machine_class_not_allowed", "machine_class_plan_required"}
)
_LOST_CONFLICT_CODES: frozenset[str] = frozenset({"machine_not_running", "sandbox_not_ready"})
#: 403 codes that mean "this key's scope lacks the action", not "wrong org".
_SCOPE_FORBIDDEN_CODES: frozenset[str] = frozenset(
    {"api_key_action_forbidden", "api_key_sandbox_forbidden"}
)
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
#: ``components.parameters.SandboxId`` pattern.
_SANDBOX_ID_RE = re.compile(r"^bx_[23456789abcdefghjkmnpqrstuvwxyz]{8}$")
#: An organization id as ``Org.id`` spells it for an organization.
_ORG_ID_RE = re.compile(r"^team_[A-Za-z0-9-]{1,100}$")
#: ``CreateSandboxEnvironmentRequest.name``: letters, digits, dot, dash, underscore; max 64.
_ENVIRONMENT_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
_REJECT_RULE_RE = re.compile(r"^-A OUTPUT -m owner --uid-owner (\d+) -j REJECT(?:\s|$)")
_LOOPBACK_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1"})


# --- small pure helpers -----------------------------------------------------


def select_machine_type(limits: ResourceLimits) -> str:
    """The smallest Boat machine type covering ``cpu_cores``, ``memory_mb`` and
    ``disk_mb``.

    Raises ``WorkspaceProvisionError`` naming the limit that no type covers,
    so an oversize request fails before anything is created or billed."""
    for type_name, vcpu, memory_mb, disk_mb in MACHINE_TYPES:
        if limits.cpu_cores <= vcpu and limits.memory_mb <= memory_mb and limits.disk_mb <= disk_mb:
            return type_name
    largest, max_vcpu, max_mb, max_disk = MACHINE_TYPES[-1]
    over: list[str] = []
    if limits.cpu_cores > max_vcpu:
        over.append(f"cpu_cores={limits.cpu_cores:g} > {max_vcpu}")
    if limits.memory_mb > max_mb:
        over.append(f"memory_mb={limits.memory_mb} > {max_mb}")
    if limits.disk_mb > max_disk:
        over.append(f"disk_mb={limits.disk_mb} > {max_disk}")
    raise WorkspaceProvisionError(
        f"ResourceLimits exceed the largest Boat machine type {largest!r} "
        f"({max_vcpu} vCPU / {max_mb} MB / {max_disk} MB disk): {', '.join(over)}"
    )


def _ttl_seconds(wall_clock_s: float) -> int:
    return max(_MIN_TTL_S, min(_MAX_TTL_S, math.ceil(wall_clock_s)))


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug[:60].strip("-") or "ws"


def _sandbox_name(profile_name: str, workspace_id: str) -> str:
    return f"{SANDBOX_NAME_PREFIX}{_slug(profile_name)}-{workspace_id[:8]}"


def _has_control_chars(text: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in text)


def _jail(path: str) -> str:
    """Workspace-relative, normalized path, or ``ValueError``. Absolute paths
    and anything whose normal form climbs out of the root are rejected before
    any network call; symlink escapes are caught in the VM (``realpath``)."""
    if not isinstance(path, str) or not path:
        raise ValueError(f"path escapes workspace root: {path!r}")
    if _has_control_chars(path):
        raise ValueError(f"path contains control characters: {path!r}")
    if posixpath.isabs(path):
        raise ValueError(f"path escapes workspace root: {path!r}")
    norm = posixpath.normpath(path)
    if norm == ".." or norm.startswith("../"):
        raise ValueError(f"path escapes workspace root: {path!r}")
    return norm


def _env_items(env: Mapping[str, str] | Sequence[tuple[str, str]], origin: str) -> list[str]:
    """Validated ``KEY=value`` assignments, in order."""
    pairs = env.items() if isinstance(env, Mapping) else env
    out: list[str] = []
    for key, value in pairs:
        if not isinstance(key, str) or not _ENV_KEY_RE.match(key):
            raise ValueError(f"invalid {origin} variable name: {key!r}")
        if not isinstance(value, str) or "\x00" in value:
            raise ValueError(f"invalid {origin} value for {key}: NUL bytes are not allowed")
        out.append(f"{key}={value}")
    return out


def _read_api_key() -> str:
    """``$BOAT_API_KEY``, read now. Loud ``BackendUnavailable`` when absent or
    malformed; the value itself is never echoed. Only this one variable is
    read: the build plane's key is never a fallback."""
    key = os.environ.get(BOAT_API_KEY_ENV, "")
    if not key:
        raise BackendUnavailable(
            f"${BOAT_API_KEY_ENV} is not set: the Boat backend has no credential. "
            "Set it to the product-plane key (the owner-minted ci-preset key limited "
            f"to the {DEFAULT_BOAT_ENVIRONMENT!r} environment) in the service "
            "environment. No other variable is ever used in its place."
        )
    if any(ch.isspace() or not ch.isprintable() for ch in key):
        raise BackendUnavailable(
            f"${BOAT_API_KEY_ENV} is malformed (whitespace or control characters); "
            "the value is not shown"
        )
    return key


def _redact(text: str, key: str) -> str:
    return text.replace(key, "[redacted]") if key else text


def _scrub(text: str, key: str | None = None) -> str:
    """``text`` with the key (``key``, else the current ``$BOAT_API_KEY``) and
    every key-shaped run replaced, so a server that echoes a key cannot get
    it into an exception or a WARNING. Scrub before cutting: a cut could
    leave part of a key that no longer looks like one."""
    if key is None:
        key = os.environ.get(BOAT_API_KEY_ENV, "")
    return _KEY_SHAPED_RE.sub("[redacted]", _redact(text, key))


def _shown(value: Any, limit: int = 120) -> str:
    """``repr`` of a value Boat returned, for a message: scrubbed, then cut.
    A string is scrubbed before ``repr`` as well, which could escape a key."""
    if isinstance(value, str):
        value = _scrub(value)
    return _scrub(repr(value))[:limit]


def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _tail(text: str, limit: int = 400) -> str:
    return _scrub(text).strip()[-limit:]


def _new_marker() -> str:
    return f"ANTIEK_BOAT_{uuid.uuid4().hex}"


def _marker_pairs(stdout: str, marker: str) -> list[tuple[str, str]]:
    """``(key, value)`` pairs from ``<marker>:key=value`` lines, in order."""
    prefix = f"{marker}:"
    pairs: list[tuple[str, str]] = []
    for line in stdout.splitlines():
        if line.startswith(prefix):
            key, _, value = line[len(prefix) :].partition("=")
            pairs.append((key, value))
    return pairs


def _marker_fields(stdout: str, marker: str) -> dict[str, str]:
    return dict(_marker_pairs(stdout, marker))


def _validate_api_url(url: str) -> str:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if not parts.netloc or parts.scheme not in ("https", "http"):
        raise BackendUnavailable(f"{BOAT_API_URL_ENV} is not an http(s) URL: {url!r}")
    if parts.scheme == "http" and host not in _LOOPBACK_HOSTS:
        raise BackendUnavailable(
            f"{BOAT_API_URL_ENV} must use https (the bearer key would travel in clear): {url!r}"
        )
    return url.rstrip("/")


def _validate_root_base(root_base: str) -> str:
    """A normalized absolute path strictly below ``/tmp`` or ``/home/user``:
    the files API reaches nothing else, and the provisioning command
    ``chmod``s the base itself, so it may never be one of those two dirs."""
    if (
        not root_base.startswith("/")
        or _has_control_chars(root_base)
        or posixpath.normpath(root_base) != root_base
        or not any(root_base.startswith(f"{top}/") for top in _FILES_API_ROOTS)
    ):
        raise ValueError(
            "root_base must be a normalized absolute path below /tmp or /home/user "
            f"(the files API's roots): {root_base!r}"
        )
    return root_base


def _log_token(value: Any) -> str:
    """``value`` as one plain token for a log line, else ``unknown``. A
    key-shaped value, or one holding the current key, is never a token: a
    server that echoes the key in a success answer cannot put it in a log."""
    if isinstance(value, bool):
        return "unknown"
    text = str(value) if isinstance(value, int | str) else ""
    key = os.environ.get(BOAT_API_KEY_ENV, "")
    if _KEY_SHAPED_RE.search(text) or (key and key in text):
        return "unknown"
    return text if _LOG_TOKEN_RE.match(text) else "unknown"


def _machine_token(value: Any) -> str:
    """A machine type name for a log line; ``unknown`` for anything else."""
    return value if isinstance(value, str) and value in _MACHINE_TYPE_NAMES else "unknown"


def _date_time_token(value: Any) -> str:
    """An RFC 3339 date-time for a log line; ``unknown`` for anything else."""
    if isinstance(value, str) and _DATE_TIME_RE.match(value):
        return _log_token(value)
    return "unknown"


def _wallet_token(team_id: Any) -> str:
    """The wallet a ``GET /limits`` answer names, for the probe's log line:
    an organization id, ``personal`` when it names none, else ``unknown``."""
    if team_id is None or team_id == "":
        return "personal"
    if isinstance(team_id, str) and _ORG_ID_RE.match(team_id):
        return _log_token(team_id)
    return "unknown"


def _environment_problems(env: Mapping[str, Any]) -> list[str]:
    """Why a ``SandboxEnvironment`` would pass something of the account into
    a sandbox; empty means it passes nothing. Reads flags only.

    ``proxyAiCredentials`` is checked on its own, whatever
    ``safeForThirdParties`` says: a present value that is not ``False`` is
    refused. The OpenAPI does not list it as required, so its absence is
    accepted. The four ``pass*`` flags (required) count only while the
    environment is not safe for third parties, and then anything but
    ``False`` counts as passing."""
    problems: list[str] = []
    if "proxyAiCredentials" in env and env.get("proxyAiCredentials") is not False:
        shown = _shown(env.get("proxyAiCredentials"), 40)
        problems.append(
            f"proxyAiCredentials is {shown}, not false (AI credential placeholders "
            "enter the sandbox)"
        )
    if env.get("safeForThirdParties") is not True:
        passing = [flag for flag in _ENV_PASS_FLAGS if env.get(flag) is not False]
        if passing:
            problems.append(f"safeForThirdParties is off and {', '.join(passing)} not off")
    return problems


# --- the in-VM scripts (pure builders, POSIX sh) ---------------------------


def _build_provision_script(*, marker: str, root: str, ctl: str) -> str:
    """Report account credentials present in the VM (names only), then create
    the runner account and the workspace dirs; report both uids."""
    q = shlex.quote
    return "\n".join(
        [
            "set -eu",
            "umask 022",
            f"M={q(marker)}",
            f"RUN={q(RUNNER_ACCOUNT)}",
            f"ROOT={q(root)}",
            f"CTL={q(ctl)}",
            # fs.protected_hardlinks must be 1: the exec handoff (chown -hR)
            # would otherwise give the runner any file it hardlinks into its tree.
            'PH="$(sysctl -n fs.protected_hardlinks 2>/dev/null'
            ' || cat /proc/sys/fs/protected_hardlinks 2>/dev/null)" || PH=""',
            'printf \'%s:protected_hardlinks=%s\\n\' "$M" "$PH"',
            'H="${HOME:-/home/user}"',
            "for f in " + " ".join(q(f) for f in _CREDENTIAL_FILES) + "; do",
            '  if [ -e "$H/$f" ] || [ -L "$H/$f" ]; then',
            '    printf \'%s:credential=~/%s\\n\' "$M" "$f"',
            "  fi",
            "done",
            # Boat wrote a keyless CLI config into both measured VMs; only a key
            # in it counts. A FIFO, directory or unreadable path is refused unread.
            f'CFG="$H/"{q(_BOAT_CLI_CONFIG)}',
            'if [ -L "$CFG" ]; then',
            f"  printf '%s:credential=~/%s (a symlink)\\n' \"$M\" {q(_BOAT_CLI_CONFIG)}",
            'elif [ -e "$CFG" ] && { [ ! -f "$CFG" ] || [ ! -r "$CFG" ]; }; then',
            "  printf '%s:credential=~/%s (not a readable regular file)\\n' "
            f'"$M" {q(_BOAT_CLI_CONFIG)}',
            'elif [ -e "$CFG" ]; then',
            '  N="$(tr -d \' \\t\\r\\n\' 2>/dev/null < "$CFG")" || N="<unreadable>"',
            f"  if printf '%s\\n' \"$N\" | grep -Eq {q(_KEY_SHAPED_ERE)} \\",
            f"    || ! printf '%s\\n' \"$N\" | grep -Eqx {q(_BOAT_CLI_CONFIG_KEYLESS_ERE)}; then",
            "    printf '%s:credential=~/%s (holds more than api_url and channel)\\n' "
            f'"$M" {q(_BOAT_CLI_CONFIG)}',
            "  fi",
            "fi",
            "for v in " + " ".join(q(v) for v in _CREDENTIAL_VARS) + "; do",
            '  if printenv "$v" >/dev/null 2>&1; then',
            '    printf \'%s:credential=$%s\\n\' "$M" "$v"',
            "  fi",
            "done",
            'if ! id -u "$RUN" >/dev/null 2>&1; then',
            "  sudo -n useradd --system --user-group --no-create-home "
            '--shell /usr/sbin/nologin "$RUN"',
            "fi",
            'mkdir -p -- "$ROOT/in" "$ROOT/out" "$ROOT/work" "$CTL"',
            'chmod 0755 -- "${ROOT%/*}" "$ROOT" "$ROOT/in" "$ROOT/out" "$ROOT/work"',
            'chmod 0700 -- "$CTL"',
            'printf \'%s:runner_uid=%s\\n\' "$M" "$(id -u "$RUN")"',
            'printf \'%s:owner_uid=%s\\n\' "$M" "$(id -u)"',
        ]
    )


def _build_deny_all_apply_script() -> str:
    """Insert the owner REJECT at the top of OUTPUT for both families
    (hosting_firewall.md: ``-I OUTPUT 1``; never a rule on ``user``)."""
    q = shlex.quote
    return "\n".join(
        [
            "set -eu",
            f"RUN={q(RUNNER_ACCOUNT)}",
            "for t in iptables ip6tables; do",
            '  sudo -n "$t" -w -I OUTPUT 1 -m owner --uid-owner "$RUN" -j REJECT',
            "done",
        ]
    )


def _build_deny_all_verify_script(*, marker: str) -> str:
    """Read the rules back (``-S OUTPUT``) and check the runner cannot sudo."""
    q = shlex.quote
    return "\n".join(
        [
            f"M={q(marker)}",
            f"RUN={q(RUNNER_ACCOUNT)}",
            'printf \'%s:runner_uid=%s\\n\' "$M" "$(id -u "$RUN" 2>/dev/null)"',
            'printf \'%s:owner_uid=%s\\n\' "$M" "$(id -u)"',
            "for t in iptables ip6tables; do",
            '  if rules="$(sudo -n "$t" -w -S OUTPUT 2>&1)"; then',
            "    printf '%s\\n' \"$rules\" | while IFS= read -r line; do",
            '      printf \'%s:%s=%s\\n\' "$M" "$t" "$line"',
            "    done",
            "  else",
            "    printf '%s:%s_error=%s\\n' \"$M\" \"$t\" \"$(printf '%s' \"$rules\" | tr '\\n' ' ')\"",
            "  fi",
            "done",
            'if sudo -n -u "$RUN" -- sudo -n true >/dev/null 2>&1; then',
            "  printf '%s:runner_sudo=yes\\n' \"$M\"",
            "else",
            "  printf '%s:runner_sudo=no\\n' \"$M\"",
            "fi",
        ]
    )


def _build_resolve_script(*, marker: str, root: str, rel: str, for_write: bool) -> str:
    """Canonicalize ``root/rel`` as ``user`` and refuse a symlink escape.
    Prints ``<marker>:path=<canonical>`` and ``<marker>:status=<status>``."""
    q = shlex.quote
    lines = [
        f"M={q(marker)}",
        'NL="$(printf \'\\nx\')"; NL="${NL%x}"',
        '_st() { printf \'%s:status=%s\\n\' "$M" "$1"; exit 0; }',
        f'ROOTR="$(realpath -e -- {q(root)})" || _st no_root',
        f'P="$(realpath -m -- "$ROOTR"/{q(rel)})" || _st bad_path',
        'case "$P" in *"$NL"*) _st bad_path ;; esac',
        '[ "$P" = "$ROOTR" ] && _st is_dir',
        'case "$P" in "$ROOTR"/?*) ;; *) _st escape ;; esac',
    ]
    if for_write:
        lines += [
            '[ -d "$P" ] && _st is_dir',
            '[ -e "$P" ] && [ ! -f "$P" ] && _st not_regular',
            'mkdir -p -- "${P%/*}" || _st mkdir_failed',
        ]
    else:
        lines += ['[ -f "$P" ] || { [ -d "$P" ] && _st is_dir; _st missing; }']
    lines += ['printf \'%s:path=%s\\n\' "$M" "$P"', "_st ok"]
    return "\n".join(lines)


def _restore_functions() -> list[str]:
    """POSIX ``sh`` shared by the exec wrapper and the cleanup command; needs
    ``RUN``, ``ROOT`` and ``OWNER`` set.

    ``_pk -U|-u`` runs ``pkill -KILL`` for the runner inside a root
    ``sh -c`` that prints pkill's own status, so sudo failing (also status
    1) cannot pass for "none matched": it returns 0 (signalled), 1 (none
    matched) or 2 (anything else: syntax error, fatal error, missing tool,
    killed by a signal, sudo refused). ``_reap`` repeats both selectors
    until both say none matched, and fails closed (``CLEAN=0``, status 1)
    on an error or after ``_REAP_ROUNDS`` rounds. ``_restore`` reaps, then
    gives the tree back to ``user`` and strips group/other write and set-id
    bits, in that order, even after a failed reap: once no runner process
    exists and the tree is ``user``'s with no group/other write, nothing the
    runner starts later can rename or replace anything in it. ``CLEAN=0``
    records a step that did not finish."""
    return [
        "CLEAN=1",
        "_pk() {",
        '  case "$(sudo -n sh -c \'pkill -KILL "$1" "$2" >/dev/null 2>&1; echo "rc=$?"\' '
        'sh "$1" "$RUN" 2>/dev/null)" in',
        "    rc=0) return 0 ;;",
        "    rc=1) return 1 ;;",
        "    *) return 2 ;;",
        "  esac",
        "}",
        # sh variables are global: the reap's own names (rk_*) never clash.
        "_reap() {",
        "  rk_i=0",
        f'  while [ "$rk_i" -lt {_REAP_ROUNDS} ]; do',
        "    _pk -U; rk_a=$?",
        "    _pk -u; rk_b=$?",
        '    if [ "$rk_a" -ge 2 ] || [ "$rk_b" -ge 2 ]; then CLEAN=0; return 1; fi',
        '    if [ "$rk_a" -eq 1 ] && [ "$rk_b" -eq 1 ]; then return 0; fi',
        "    rk_i=$((rk_i + 1))",
        "    sleep 0.1",
        "  done",
        "  CLEAN=0",
        "  return 1",
        "}",
        "_restore() {",
        "  _reap || :",
        '  sudo -n chown -hR "$OWNER" -- "$ROOT" >/dev/null 2>&1 || CLEAN=0',
        '  sudo -n chmod -R go-w,ug-s -- "$ROOT" >/dev/null 2>&1 || CLEAN=0',
        "}",
    ]


def _build_cleanup_script(
    *, marker: str, root: str, ctl: str, spool: Sequence[str], fence: Sequence[str]
) -> str:
    """After an API-level kill, a lost exec answer or a cancellation: fence
    the interrupted wrappers (``fence`` holds their nonces), wait for the
    exec lock while reaping, then, holding it, end every runner process and
    hand the tree back; report ``<marker>:clean=1|0``. ``clean=1`` only when
    the lock was taken and the reap and restore were confirmed."""
    q = shlex.quote
    lines = [
        f"M={q(marker)}",
        f"RUN={q(RUNNER_ACCOUNT)}",
        f"ROOT={q(root)}",
        f"CTL={q(ctl)}",
        'OWNER="$(id -u):$(id -g)"',
        *_restore_functions(),
    ]
    # Fence first: a wrapper that has not taken the lock yet finds its fence
    # file under the lock and runs nothing.
    lines += [f'touch -- "$CTL"/{q(nonce + _FENCE_SUFFIX)} || CLEAN=0' for nonce in fence]
    lines += [
        "LOCKED=0",
        f'if command exec 9>>"$CTL"/{q(_EXEC_LOCK_NAME)}; then',
        "  lk_i=0",
        f'  while [ "$lk_i" -lt {_CLEANUP_LOCK_ROUNDS} ]; do',
        "    if flock -n 9; then LOCKED=1; break; fi",
        # A wrapper still holds the lock: kill its workload so it finishes.
        "    _reap || break",
        "    lk_i=$((lk_i + 1))",
        "    sleep 0.1",
        "  done",
        "fi",
        '[ "$LOCKED" -eq 1 ] || CLEAN=0',
        "_restore",
    ]
    if spool:
        lines.append("rm -f -- " + " ".join(q(p) for p in spool) + " 2>/dev/null || :")
    lines.append('printf \'%s:clean=%s\\n\' "$M" "$CLEAN"')
    return "\n".join(lines)


def _build_exec_script(
    *,
    marker: str,
    nonce: str,
    root: str,
    ctl: str,
    spool_out: str,
    spool_err: str,
    stdin_path: str | None,
    rel_cwd: str,
    argv: Sequence[str],
    assignments: Sequence[str],
    timeout_s: float,
    deny_all: bool,
) -> str:
    """The per-``exec`` wrapper. See the module docstring, "Execution".

    Output protocol: stdout is ``<marker>:begin`` then at most
    ``MAX_OUTPUT_BYTES + 1`` workload stdout bytes; stderr is
    ``<marker>:begin``, the capped workload stderr, then a trailer line
    ``<marker>:end <status> <rc> <timed_out> <stdout_bytes> <stderr_bytes>
    <clean>`` (``clean`` 1 when every runner process was killed and the tree
    restored, or never handed over).
    """
    q = shlex.quote
    t_arg = f"{max(float(timeout_s), 0.001):.3f}"
    t_ns = max(0, int(float(timeout_s) * 1_000_000_000) - _TIMEOUT_EPSILON_NS)
    cap = MAX_OUTPUT_BYTES + 1
    spool = [spool_out, spool_err] + ([stdin_path] if stdin_path is not None else [])
    lines = [
        "umask 022",
        f"M={q(marker)}",
        f"RUN={q(RUNNER_ACCOUNT)}",
        f"ROOT={q(root)}",
        f"CTL={q(ctl)}",
        f"OUT={q(spool_out)}",
        f"ERR={q(spool_err)}",
        f"IN={q(stdin_path if stdin_path is not None else '/dev/null')}",
        'OWNER="$(id -u):$(id -g)"',
        *_restore_functions(),
        "_fin() {",
        "  rm -f -- " + " ".join(q(p) for p in spool) + " 2>/dev/null",
        '  printf \'\\n%s:end %s %s %s %s %s %s\\n\' "$M" "$1" "$2" "$3" "$4" "$5" "$CLEAN" >&2',
        "  exit 0",
        "}",
        "printf '%s:begin\\n' \"$M\"",
        "printf '%s:begin\\n' \"$M\" >&2",
        'ROOTR="$(realpath -e -- "$ROOT")" || _fin no_root -1 0 0 0',
        # One wrapper at a time in the VM; held until this shell exits.
        f'command exec 9>>"$CTL"/{q(_EXEC_LOCK_NAME)} || {{ CLEAN=0; _fin no_lock -1 0 0 0; }}',
        f"flock -w {_EXEC_LOCK_WAIT_S} 9 || {{ CLEAN=0; _fin busy -1 0 0 0; }}",
        # Fenced by a cleanup after this host gave up on this exec: run nothing.
        f'[ -e "$CTL"/{q(nonce + _FENCE_SUFFIX)} ] && _fin cancelled -1 0 0 0',
        # Nothing of an earlier exec may run alongside this one (I7): start
        # only once every runner process is confirmed gone.
        "_reap || _fin reap_failed -1 0 0 0",
    ]
    if deny_all:
        lines += [
            'RUID="$(id -u "$RUN" 2>/dev/null)" || _fin no_runner -1 0 0 0',
            "for t in iptables ip6tables; do",
            '  first="$(sudo -n "$t" -w -S OUTPUT 2>/dev/null | grep -m 1 -e \'^-A OUTPUT \')"'
            " || first=''",
            '  case "$first" in',
            '    "-A OUTPUT -m owner --uid-owner $RUID -j REJECT"'
            '|"-A OUTPUT -m owner --uid-owner $RUID -j REJECT "*) ;;',
            "    *) _fin fw_drift -1 0 0 0 ;;",
            "  esac",
            "done",
        ]
    workload = " ".join(
        [
            'sudo -n -u "$RUN" -- env -i -C "$CWD"',
            q(f"PATH={_WORKLOAD_PATH}"),
            q(f"LANG={_WORKLOAD_LANG}"),
            'HOME="$ROOTR"',
            *(q(a) for a in assignments),
            f"setsid --wait timeout -k {_KILL_GRACE_S} {t_arg}",
            *(q(a) for a in argv),
            # The workload never holds the exec lock.
            '<"$IN" >"$OUT" 2>"$ERR" 9>&-',
        ]
    )
    lines += [
        'sudo -n chown -hR "$RUN:$RUN" -- "$ROOT" || { _restore; _fin chown_failed -1 0 0 0; }',
        f'CWD="$(sudo -n -u "$RUN" -- realpath -e -- "$ROOTR"/{q(rel_cwd)} 2>/dev/null)"'
        " || { _restore; _fin cwd_missing -1 0 0 0; }",
        'case "$CWD/" in "$ROOTR"/*) ;; *) _restore; _fin cwd_escape -1 0 0 0 ;; esac',
        'sudo -n -u "$RUN" -- test -d "$CWD" || { _restore; _fin cwd_missing -1 0 0 0; }',
        'st="$(date +%s%N)"',
        workload,
        "rc=$?",
        "el=$(( $(date +%s%N) - st ))",
        "to=0",
        'if [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; then',
        f'  if [ "$el" -ge {t_ns} ]; then to=1; fi',
        "fi",
        # Whether it exited or timed out: kill what it left, take the tree back.
        "_restore",
        'ob="$(wc -c <"$OUT" 2>/dev/null | tr -dc \'0-9\')"',
        'eb="$(wc -c <"$ERR" 2>/dev/null | tr -dc \'0-9\')"',
        f'head -c {cap} "$OUT" 2>/dev/null',
        f'head -c {cap} "$ERR" >&2 2>/dev/null',
        '_fin ok "$rc" "$to" "${ob:-0}" "${eb:-0}"',
    ]
    return "\n".join(lines)


@dataclass(frozen=True)
class _Wrapped:
    status: str
    rc: int
    timed_out: bool
    out_bytes: int
    err_bytes: int
    clean: bool
    stdout: str
    stderr: str


def _after_begin(text: str, marker: str) -> str:
    """Everything after the wrapper's ``<marker>:begin`` line (login-shell
    banner noise before it is dropped); the whole text if it is absent."""
    begin = f"{marker}:begin\n"
    i = text.find(begin)
    return text[i + len(begin) :] if i >= 0 else text


def _parse_wrapped(stdout: str, stderr: str, marker: str) -> _Wrapped | None:
    """Undo the wrapper's framing; ``None`` when the trailer is missing."""
    end_tag = f"\n{marker}:end "
    out = _after_begin(stdout, marker)
    body = _after_begin(stderr, marker)
    k = body.rfind(end_tag)
    if k < 0:
        return None
    fields = body[k + len(end_tag) :].split()
    if len(fields) < 6:
        return None
    rc = _int_or_none(fields[1])
    return _Wrapped(
        status=fields[0],
        rc=rc if rc is not None else -1,
        timed_out=fields[2] == "1",
        out_bytes=_int_or_none(fields[3]) or 0,
        err_bytes=_int_or_none(fields[4]) or 0,
        clean=fields[5] == "1",
        stdout=out,
        stderr=body[:k],
    )


def _cap(text: str, total_bytes: int) -> tuple[str, bool]:
    """Cap a stream at ``MAX_OUTPUT_BYTES``; flag truncation by the true size."""
    raw = text.encode("utf-8", errors="replace")
    truncated = total_bytes > MAX_OUTPUT_BYTES or len(raw) > MAX_OUTPUT_BYTES
    if len(raw) > MAX_OUTPUT_BYTES:
        text = raw[:MAX_OUTPUT_BYTES].decode("utf-8", errors="replace")
    return text, truncated


def _deny_all_problems(
    pairs: Sequence[tuple[str, str]], *, expected_runner_uid: int | None
) -> list[str]:
    """Everything wrong with a DENY_ALL read-back; empty means verified."""
    fields: dict[str, list[str]] = {}
    for key, value in pairs:
        fields.setdefault(key, []).append(value)

    def first_int(key: str) -> int | None:
        values = fields.get(key) or []
        return _int_or_none(values[0]) if values else None

    problems: list[str] = []
    runner = first_int("runner_uid")
    owner = first_int("owner_uid")
    if runner is None:
        problems.append(f"runner account {RUNNER_ACCOUNT} not found")
    if owner is None:
        problems.append("the Boat 'user' uid could not be read")
    if runner is not None and expected_runner_uid is not None and runner != expected_runner_uid:
        problems.append(f"runner uid changed ({expected_runner_uid} -> {runner})")
    if runner is not None and (runner == 0 or runner == owner):
        problems.append(f"runner uid {runner} is root or the Boat 'user' account")
    for family in ("iptables", "ip6tables"):
        errors = fields.get(f"{family}_error")
        if errors:
            problems.append(f"{family} -S OUTPUT failed: {_scrub(errors[0])[:200]}")
            continue
        rules = [line for line in fields.get(family, []) if line.startswith("-A OUTPUT ")]
        if not rules:
            problems.append(f"{family}: OUTPUT has no rules (owner REJECT missing)")
            continue
        match = _REJECT_RULE_RE.match(rules[0])
        if match is None or runner is None or int(match.group(1)) != runner:
            problems.append(
                f"{family}: first OUTPUT rule is {_shown(rules[0], 200)}, expected the owner "
                f"REJECT for uid {runner}"
            )
        if owner is not None:
            owner_re = re.compile(rf"--uid-owner {owner}(?:\s|$)")
            if any(owner_re.search(r) and re.search(r"-j (?:REJECT|DROP)\b", r) for r in rules):
                problems.append(
                    f"{family}: a rule blocks the Boat 'user' account (uid {owner}), "
                    "which breaks Boat's agent and tunnel"
                )
    if fields.get("runner_sudo") != ["no"]:
        problems.append("the runner account can use sudo, so it could delete the rules")
    return problems


# --- HTTP layer -------------------------------------------------------------


class _BoatHTTPError(ExecutionBackendError):
    """A non-2xx answer. Internal: every public method maps it onto the
    seam's taxonomy before it leaves this module."""

    def __init__(
        self, *, method: str, path: str, status: int, code: str, message: str, request_id: str
    ) -> None:
        self.status = status
        self.code = code
        detail = f"HTTP {status} {code}"
        if message:
            detail += f": {message}"
        if request_id:
            detail += f" (requestId {request_id})"
        self.detail = detail
        super().__init__(f"Boat {method} {path} -> {detail}")


class _BoatTransportError(ExecutionBackendError):
    """No HTTP answer at all (DNS, connect, TLS, read timeout). Internal.
    ``maybe_sent`` is False only when no connection was ever established, so
    Boat cannot have seen the request."""

    def __init__(self, message: str, *, maybe_sent: bool) -> None:
        super().__init__(message)
        self.maybe_sent = maybe_sent


#: httpx failures raised before a request could leave this process.
_NOT_SENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
    httpx.UnsupportedProtocol,
    httpx.InvalidURL,
)

#: Cleanup tasks that must outlive a second cancellation of their caller; a
#: reference is held here until each one ends.
_BACKGROUND_CLEANUPS: set[asyncio.Task[None]] = set()


def _start_cleanup(cleanup: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
    """Start ``cleanup`` as a task that outlives its caller (referenced in
    ``_BACKGROUND_CLEANUPS`` until it ends). ``cleanup`` must not raise."""
    task = asyncio.ensure_future(cleanup)
    _BACKGROUND_CLEANUPS.add(task)
    task.add_done_callback(_BACKGROUND_CLEANUPS.discard)
    return task


async def _run_shielded(cleanup: Coroutine[Any, Any, None]) -> None:
    """Run ``cleanup`` to completion even if the caller is cancelled while
    waiting for it: the task keeps running on its own and the caller's
    ``CancelledError`` propagates. ``cleanup`` must not raise."""
    await asyncio.shield(_start_cleanup(cleanup))


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _http_error(
    method: str, path: str, status: int, payload: Mapping[str, Any], key: str
) -> _BoatHTTPError:
    """Read the OpenAPI ``ErrorEnvelope`` (top-level ``code``/``message``,
    mirrored in ``error{}``), scrubbing the key from every echoed string."""
    err = payload.get("error")
    err_obj: Mapping[str, Any] = err if isinstance(err, dict) else {}
    code = _str(payload.get("code")) or _str(err_obj.get("code")) or f"http_{status}"
    message = _str(payload.get("message")) or _str(err_obj.get("message")) or _str(err)
    return _BoatHTTPError(
        method=method,
        path=path,
        status=status,
        code=_scrub(code, key)[:80],
        message=_scrub(message, key)[:300],
        request_id=_scrub(_str(payload.get("requestId")), key)[:80],
    )


class _BoatApi:
    """A thin JSON client. One lazily created ``httpx.AsyncClient``; the key
    is read per request and only ever placed in the ``Authorization`` header."""

    def __init__(self, *, base_url: str, transport: httpx.AsyncBaseTransport | None) -> None:
        self._base_url = base_url
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                transport=self._transport, timeout=_HTTP_TIMEOUT_S, follow_redirects=False
            )
        return self._client

    async def aclose(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with contextlib.suppress(Exception):
                await client.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        key = _read_api_key()
        send_headers = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
        if headers:
            send_headers.update(headers)
        response: httpx.Response | None = None
        failure = ""
        maybe_sent = True
        try:
            response = await self._get_client().request(
                method,
                f"{self._base_url}{path}",
                json=dict(body) if body is not None else None,
                params=dict(params) if params is not None else None,
                headers=send_headers,
                timeout=timeout_s if timeout_s is not None else _HTTP_TIMEOUT_S,
            )
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            failure = _scrub(f"{type(exc).__name__}: {exc}", key)
            maybe_sent = not isinstance(exc, _NOT_SENT_ERRORS)
        if response is None:
            # Raised outside the except block on purpose: the httpx exception
            # (whose text could carry a header value) is not chained.
            raise _BoatTransportError(
                f"Boat {method} {path} got no HTTP answer: {failure}", maybe_sent=maybe_sent
            )
        payload = _json_object(response)
        if response.status_code >= 400:
            raise _http_error(method, path, response.status_code, payload, key)
        return payload


async def _default_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


@dataclass(frozen=True)
class _RawRun:
    stdout: str
    stderr: str
    exit_code: int | None
    api_timed_out: bool
    #: Outcome of the cleanup command run after an API-level kill; ``None``
    #: when none ran (the wrapper's own trailer then says).
    cleaned: bool | None = None


@dataclass
class _InFlight:
    """One ``exec`` on its way: what an interrupted exec needs cleaned up.
    ``sent`` turns True just before the command request may leave;
    ``process_id`` is set once a detached command is known to run."""

    nonce: str
    spool: Sequence[str]
    sent: bool = False
    process_id: int | None = None


def _may_have_run(exc: BaseException, flight: _InFlight) -> bool:
    """Whether the wrapper of ``flight`` may run (or still start) in the VM
    after ``exc`` ended the host's wait for it. False only when the request
    never left (no connection, or nothing sent yet) or Boat refused it with a
    4xx; a 5xx, a transport failure after sending, a cancellation or any
    other exception count as "may have run"."""
    if flight.process_id is not None:
        return True
    if not flight.sent:
        return False
    cause = exc.__cause__ if isinstance(exc, ExecutionBackendError) else None
    if isinstance(cause, _BoatTransportError):
        return cause.maybe_sent
    if isinstance(cause, _BoatHTTPError):
        return cause.status >= 500
    return True


# --- workspace ----------------------------------------------------------------


class _BoatWorkspace:
    """One disposable workspace backed by one Boat sandbox. Satisfies the
    ``Workspace`` protocol structurally (no inheritance)."""

    def __init__(
        self,
        *,
        workspace_id: str,
        sandbox_id: str,
        sandbox_name: str,
        root: str,
        api: _BoatApi,
        deny_all: bool,
        environment: str,
        profile: WorkspaceProfile,
        limits: ResourceLimits,
        sleep: Callable[[float], Awaitable[None]],
        clock: Callable[[], float],
        poll_interval_s: float,
        log: logging.Logger,
    ) -> None:
        self._id = workspace_id
        self._sandbox_id = sandbox_id
        self._sandbox_name = sandbox_name
        self._root = root
        self._ctl = f"{root}.ctl"
        self._api = api
        self._deny_all = deny_all
        self._environment = environment
        self._profile = profile
        self._limits = limits
        self._sleep = sleep
        self._clock = clock
        self._poll_interval_s = poll_interval_s
        self._log = log
        self._destroyed = False
        self._runner_uid: int | None = None
        #: One exec / put_file / get_file at a time (see "Execution").
        self._lock = asyncio.Lock()
        #: True while the tree may be the runner's, a runner process may live
        #: or an interrupted wrapper may still run: set before an exec,
        #: cleared by a trailer or cleanup that confirms the reap and restore.
        self._dirty = False
        #: Nonces of exec wrappers that may still start or run; every cleanup
        #: writes their fence files, a confirmed one forgets them.
        self._fence: set[str] = set()
        #: The shielded cleanup of an interrupted exec while it runs; every
        #: call waits for it before anything else (see "Interrupted exec").
        self._settling: asyncio.Task[None] | None = None

    @property
    def workspace_id(self) -> str:
        return self._id

    @property
    def sandbox_id(self) -> str:
        """The Boat sandbox (``bx_...``) backing this workspace (ops/teardown)."""
        return self._sandbox_id

    @property
    def sandbox_name(self) -> str:
        return self._sandbox_name

    @property
    def root(self) -> str:
        """The workspace root inside the VM (not a host path)."""
        return self._root

    # -- plumbing --

    def _check_alive(self) -> None:
        if self._destroyed:
            raise WorkspaceLost(f"workspace {self._id} was destroyed")

    def _use_error(self, exc: _BoatHTTPError, what: str) -> ExecutionBackendError:
        sid = self._sandbox_id
        if exc.status == 404 or (exc.status == 409 and exc.code in _LOST_CONFLICT_CODES):
            return WorkspaceLost(
                f"Boat sandbox {sid} behind workspace {self._id} is gone ({what}: "
                f"{exc.detail}); it was deleted, or stopped at its auto-stop deadline"
            )
        if exc.status in (401, 402, 403):
            return BackendUnavailable(f"Boat refused {what} on sandbox {sid}: {exc.detail}")
        if exc.status == 413:
            return ExecutionBackendError(
                f"{what} on sandbox {sid} exceeds Boat's 5 MiB files-API cap ({exc.detail})"
            )
        return ExecutionBackendError(f"Boat {what} on sandbox {sid} failed: {exc.detail}")

    async def _call(
        self,
        method: str,
        path: str,
        *,
        what: str,
        body: Mapping[str, Any] | None = None,
        params: Mapping[str, str] | None = None,
        headers: Mapping[str, str] | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        try:
            return await self._api.request(
                method, path, body=body, params=params, headers=headers, timeout_s=timeout_s
            )
        except _BoatHTTPError as exc:
            raise self._use_error(exc, what) from exc
        except _BoatTransportError as exc:
            raise ExecutionBackendError(f"{what} on sandbox {self._sandbox_id}: {exc}") from exc

    async def _command(self, script: str, *, timeout_s: int, what: str) -> dict[str, Any]:
        """One synchronous ``POST /commands`` (``CommandRequest``: ``command``,
        ``timeoutSeconds`` 1-600)."""
        if not 1 <= timeout_s <= SYNC_COMMAND_CAP_S:
            raise ValueError(f"timeoutSeconds must be 1-{SYNC_COMMAND_CAP_S}: {timeout_s}")
        return await self._call(
            "POST",
            f"/sandboxes/{self._sandbox_id}/commands",
            what=what,
            body={"command": script, "timeoutSeconds": int(timeout_s)},
            timeout_s=timeout_s + _START_WAIT_S + 30.0,
        )

    async def _write_file(self, abs_path: str, data: bytes, *, what: str) -> None:
        """``PUT /files`` (``FileWriteRequest``: ``path``, ``content``,
        ``encoding: base64``)."""
        if len(data) > FILE_API_CAP_BYTES:
            raise ExecutionBackendError(
                f"{what}: {len(data)} bytes exceeds Boat's {FILE_API_CAP_BYTES}-byte files-API cap"
            )
        answer = await self._call(
            "PUT",
            f"/sandboxes/{self._sandbox_id}/files",
            what=what,
            body={
                "path": abs_path,
                "content": base64.b64encode(data).decode("ascii"),
                "encoding": "base64",
            },
        )
        size = _int_or_none(answer.get("size"))
        if size is not None and size != len(data):
            raise ExecutionBackendError(f"{what}: Boat wrote {size} bytes, expected {len(data)}")

    async def _resolve(self, rel: str, original: str, *, for_write: bool) -> str:
        """The canonical in-VM path for ``rel``, refusing symlink escapes."""
        marker = _new_marker()
        what = "put_file" if for_write else "get_file"
        answer = await self._command(
            _build_resolve_script(marker=marker, root=self._root, rel=rel, for_write=for_write),
            timeout_s=_HELPER_TIMEOUT_S,
            what=what,
        )
        fields = _marker_fields(_str(answer.get("stdout")), marker)
        status = fields.get("status")
        target = fields.get("path", "")
        if status == "ok" and target:
            return target
        if status == "escape":
            raise ValueError(f"path escapes workspace root: {original!r}")
        if status == "is_dir":
            if for_write:
                raise IsADirectoryError(f"is a directory in workspace {self._id}: {original!r}")
            raise FileNotFoundError(f"not a file in workspace {self._id}: {original!r}")
        if status == "not_regular":
            raise ExecutionBackendError(
                f"put_file: {original!r} exists in workspace {self._id} and is not a regular file"
            )
        if status == "missing":
            raise FileNotFoundError(f"not in workspace {self._id}: {original!r}")
        if status == "no_root":
            raise WorkspaceLost(
                f"workspace {self._id} root vanished from sandbox {self._sandbox_id}"
            )
        raise ExecutionBackendError(
            f"{what}: could not resolve {original!r} in sandbox {self._sandbox_id} "
            f"(status {_shown(status)}, exit {_shown(answer.get('exitCode'))}): "
            f"{_tail(_str(answer.get('stderr')))}"
        )

    async def _cleanup_after_kill(self, spool: Sequence[str], *, raise_lost: bool = False) -> bool:
        """Fence every interrupted wrapper, wait for the exec lock, kill
        every runner process and restore the tree; True when the command
        confirmed all of it (and the fenced nonces are then forgotten).
        Never raises, except ``WorkspaceLost`` / ``BackendUnavailable`` when
        ``raise_lost``."""
        marker = _new_marker()
        fence = sorted(self._fence)
        try:
            answer = await self._command(
                _build_cleanup_script(
                    marker=marker, root=self._root, ctl=self._ctl, spool=spool, fence=fence
                ),
                timeout_s=_HELPER_TIMEOUT_S,
                what="cleanup",
            )
        except ExecutionBackendError as exc:
            if raise_lost and isinstance(exc, WorkspaceLost | BackendUnavailable):
                raise
            self._log.warning(
                "cleanup after a killed or interrupted exec in sandbox %s failed: %s",
                self._sandbox_id,
                exc,
            )
            return False
        if _marker_fields(_str(answer.get("stdout")), marker).get("clean") != "1":
            self._log.warning(
                "cleanup in sandbox %s could not confirm that no earlier exec wrapper runs, "
                "every %s process is gone and the tree is restored (exit %s)",
                self._sandbox_id,
                RUNNER_ACCOUNT,
                _shown(answer.get("exitCode")),
            )
            return False
        self._fence.difference_update(fence)
        return True

    async def _await_settling(self) -> None:
        """Wait for the shielded cleanup of an interrupted exec, if one still
        runs. A cancellation here leaves it running for the next caller."""
        task = self._settling
        if task is None:
            return
        await asyncio.shield(task)
        if self._settling is task:
            self._settling = None

    async def _ensure_restored(self, what: str) -> None:
        """Before any exec or file transfer: let a running cleanup finish;
        then, if the workspace is unclean, run the cleanup now, and refuse
        the call if it cannot be confirmed."""
        await self._await_settling()
        if not self._dirty:
            return
        if not await self._cleanup_after_kill([], raise_lost=True):
            raise ExecutionBackendError(
                f"{what} refused on sandbox {self._sandbox_id}: the workspace tree could not "
                f"be taken back from {RUNNER_ACCOUNT} after an interrupted or unclean exec "
                "(an earlier wrapper or runner process may still run). Every call is refused "
                "until a cleanup is confirmed; destroy() still works."
            )
        self._dirty = False

    async def _settle_interrupted(self, flight: _InFlight) -> None:
        """An exec whose wrapper may still run was interrupted: clean up
        before the lock is released. Shielded and recorded in ``_settling``:
        a cancellation that lands during it returns at once while the cleanup
        goes on, and every later call waits for it first (``_ensure_restored``)."""
        task = _start_cleanup(self._settle(flight))
        self._settling = task
        await asyncio.shield(task)

    async def _settle(self, flight: _InFlight) -> None:
        """Stop the detached command when its id is known, then fence, reap
        and restore. Never raises; an unconfirmed cleanup leaves the
        workspace unclean (every later call re-runs it first)."""
        sid = self._sandbox_id
        try:
            if self._destroyed:
                return
            if flight.process_id is not None:
                await self._stop_command(flight.process_id)
            if not self._destroyed and await self._cleanup_after_kill(flight.spool):
                self._dirty = False
                self._log.info(
                    "interrupted exec in sandbox %s: wrapper fenced or finished, every %s "
                    "process gone, tree restored",
                    sid,
                    RUNNER_ACCOUNT,
                )
                return
        except Exception as exc:  # a cleanup must never raise
            self._log.warning(
                "cleanup of an interrupted exec in sandbox %s failed (%s)",
                sid,
                type(exc).__name__,
            )
        self._log.warning(
            "interrupted exec in sandbox %s could not be cleaned up; the workspace stays "
            "unclean and every later call re-runs the cleanup first",
            sid,
        )

    async def _stop_command(self, process_id: int) -> None:
        """``DELETE /commands/{processId}``: stop a detached command. Never
        raises ``ExecutionBackendError``; the reap after it is what counts."""
        try:
            await self._call(
                "DELETE",
                f"/sandboxes/{self._sandbox_id}/commands/{process_id}",
                what="exec stop",
            )
        except ExecutionBackendError as exc:
            self._log.warning(
                "stopping detached command %s in sandbox %s failed: %s",
                process_id,
                self._sandbox_id,
                exc,
            )

    # -- provisioning (called by BoatBackend.create) --

    async def _provision(self) -> None:
        marker = _new_marker()
        try:
            answer = await self._command(
                _build_provision_script(marker=marker, root=self._root, ctl=self._ctl),
                timeout_s=_PROVISION_TIMEOUT_S,
                what="provision",
            )
        except BackendUnavailable, WorkspaceLost:
            raise
        except ExecutionBackendError as exc:
            raise WorkspaceProvisionError(
                f"provisioning sandbox {self._sandbox_id} failed: {exc}"
            ) from exc
        pairs = _marker_pairs(_str(answer.get("stdout")), marker)
        found = [value for key, value in pairs if key == "credential"]
        if found:
            raise BackendUnavailable(
                f"Boat environment {self._environment!r} passes account credentials into "
                f"sandbox {self._sandbox_id}: {', '.join(_scrub(v) for v in found)}. "
                "Product workspaces must get "
                "nothing of the account: mark the environment 'safe for third parties' "
                "(proxyAiCredentials off). The sandbox was deleted."
            )
        fields = dict(pairs)
        runner = _int_or_none(fields.get("runner_uid"))
        owner = _int_or_none(fields.get("owner_uid"))
        if answer.get("exitCode") != 0 or runner is None or owner is None:
            raise WorkspaceProvisionError(
                f"provisioning sandbox {self._sandbox_id} failed (exit "
                f"{_shown(answer.get('exitCode'))}): {_tail(_str(answer.get('stderr')))}"
            )
        if runner in (0, owner):
            raise WorkspaceProvisionError(
                f"runner account {RUNNER_ACCOUNT} resolved to uid {runner}, which is root "
                "or the Boat 'user' account; refusing to run workloads as it"
            )
        hardlinks = fields.get("protected_hardlinks", "").strip()
        if hardlinks != "1":
            raise BackendUnavailable(
                f"sandbox {self._sandbox_id} does not protect hardlinks "
                f"(fs.protected_hardlinks={_scrub(hardlinks)[:40] or 'unreadable'}): handing the "
                "workspace "
                f"tree to {RUNNER_ACCOUNT} (chown -hR) would give it any file it hardlinks "
                "into the tree. The sandbox was deleted."
            )
        self._runner_uid = runner

    async def _enforce_deny_all(self) -> None:
        sid = self._sandbox_id
        try:
            applied = await self._command(
                _build_deny_all_apply_script(), timeout_s=_HELPER_TIMEOUT_S, what="deny_all apply"
            )
        except BackendUnavailable, WorkspaceLost:
            raise
        except ExecutionBackendError as exc:
            raise WorkspaceProvisionError(f"applying DENY_ALL on sandbox {sid}: {exc}") from exc
        if applied.get("exitCode") != 0:
            raise NetPolicyUnsupported(
                f"DENY_ALL could not be applied on sandbox {sid}: inserting the "
                f"iptables/ip6tables owner rules exited {_shown(applied.get('exitCode'))}: "
                f"{_tail(_str(applied.get('stderr')))}"
            )
        marker = _new_marker()
        try:
            verified = await self._command(
                _build_deny_all_verify_script(marker=marker),
                timeout_s=_HELPER_TIMEOUT_S,
                what="deny_all verify",
            )
        except BackendUnavailable, WorkspaceLost:
            raise
        except ExecutionBackendError as exc:
            raise WorkspaceProvisionError(f"verifying DENY_ALL on sandbox {sid}: {exc}") from exc
        problems = _deny_all_problems(
            _marker_pairs(_str(verified.get("stdout")), marker),
            expected_runner_uid=self._runner_uid,
        )
        if problems:
            raise NetPolicyUnsupported(
                f"DENY_ALL could not be verified on sandbox {sid}: {'; '.join(problems)}"
            )
        self._log.info(
            "BoatBackend DENY_ALL verified on sandbox %s (owner REJECT first in "
            "iptables and ip6tables OUTPUT for uid %s)",
            sid,
            self._runner_uid,
        )

    # -- the Workspace protocol --

    async def exec(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> ExecResult:
        self._check_alive()
        if len(argv) == 0:
            raise ValueError("argv must be non-empty")
        words = list(argv)
        for word in words:
            if not isinstance(word, str) or "\x00" in word:
                raise ValueError(f"argv elements must be str without NUL bytes: {word!r}")
        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, int | float)
            or not math.isfinite(timeout_s)
            or timeout_s <= 0
        ):
            raise ValueError(f"timeout_s must be a positive finite number: {timeout_s!r}")
        rel_cwd = "work" if cwd is None else _jail(cwd)
        assignments = _env_items(self._profile.env, "profile env")
        if env:
            assignments += _env_items(env, "exec env")
        _read_api_key()  # a missing key refuses before anything is sent
        async with self._lock:
            self._check_alive()
            await self._ensure_restored("exec")
            return await self._exec_locked(
                words,
                timeout_s=float(timeout_s),
                rel_cwd=rel_cwd,
                cwd=cwd,
                assignments=assignments,
                stdin=stdin,
            )

    async def _exec_locked(
        self,
        words: Sequence[str],
        *,
        timeout_s: float,
        rel_cwd: str,
        cwd: str | None,
        assignments: Sequence[str],
        stdin: bytes | None,
    ) -> ExecResult:
        nonce = uuid.uuid4().hex
        marker = f"ANTIEK_BOAT_{nonce}"
        spool_out = f"{self._ctl}/{nonce}.out"
        spool_err = f"{self._ctl}/{nonce}.err"
        stdin_path: str | None = None
        start = self._clock()
        if stdin is not None:
            stdin_path = f"{self._ctl}/{nonce}.in"
            await self._write_file(stdin_path, bytes(stdin), what="exec stdin")
        spool = [spool_out, spool_err] + ([stdin_path] if stdin_path is not None else [])
        script = _build_exec_script(
            marker=marker,
            nonce=nonce,
            root=self._root,
            ctl=self._ctl,
            spool_out=spool_out,
            spool_err=spool_err,
            stdin_path=stdin_path,
            rel_cwd=rel_cwd,
            argv=words,
            assignments=assignments,
            timeout_s=timeout_s,
            deny_all=self._deny_all,
        )
        api_timeout_s = math.ceil(timeout_s) + _KILL_GRACE_S + _WRAPPER_SLACK_S
        flight = _InFlight(nonce=nonce, spool=spool)
        # From here until a trailer or a cleanup confirms otherwise, the tree
        # may be the runner's, runner processes may live and this wrapper may
        # still start.
        was_dirty = self._dirty
        self._dirty = True
        self._fence.add(nonce)
        try:
            if api_timeout_s <= SYNC_COMMAND_CAP_S:
                raw = await self._exec_sync(script, api_timeout_s, flight)
            else:
                raw = await self._exec_detached(script, timeout_s, flight)
        except BaseException as exc:
            if _may_have_run(exc, flight):
                # Lost answer, transport failure after sending, cancellation:
                # the wrapper may still run. Clean up before the lock goes.
                await self._settle_interrupted(flight)
            else:
                # Refused by Boat or never sent: nothing ran in the VM.
                self._fence.discard(nonce)
                self._dirty = was_dirty
            raise
        duration_ms = max(0, int((self._clock() - start) * 1000))
        parsed = _parse_wrapped(raw.stdout, raw.stderr, marker)
        if parsed is not None:
            # The wrapper finished: it can no longer start.
            self._fence.discard(nonce)
        if raw.cleaned is not None:
            self._dirty = not raw.cleaned
        elif parsed is not None:
            self._dirty = not parsed.clean
        else:
            # A success answer without the wrapper's trailer, and no cleanup
            # yet: the wrapper may still run or start. Settle it before the
            # lock goes, as for a lost answer (review finding S3).
            await self._settle_interrupted(flight)
        if self._dirty:
            self._log.warning(
                "exec in sandbox %s ended without confirming that every %s process is gone "
                "and the tree restored; every later call re-runs the cleanup first",
                self._sandbox_id,
                RUNNER_ACCOUNT,
            )
        return self._finish(raw, parsed, marker, duration_ms, cwd)

    async def _exec_sync(self, script: str, api_timeout_s: int, flight: _InFlight) -> _RawRun:
        flight.sent = True
        answer = await self._command(script, timeout_s=api_timeout_s, what="exec")
        api_timed_out = answer.get("timedOut") is True
        cleaned = await self._cleanup_after_kill(flight.spool) if api_timed_out else None
        return _RawRun(
            stdout=_str(answer.get("stdout")),
            stderr=_str(answer.get("stderr")),
            exit_code=_int_or_none(answer.get("exitCode")),
            api_timed_out=api_timed_out,
            cleaned=cleaned,
        )

    async def _exec_detached(self, script: str, timeout_s: float, flight: _InFlight) -> _RawRun:
        """``POST /commands`` with ``detached: true`` (no time limit), then poll
        ``GET /commands/{processId}`` (``CommandStatusResponse``) until it is
        no longer ``running``; a host-side backstop deadline stops it with
        ``DELETE /commands/{processId}``."""
        sid = self._sandbox_id
        flight.sent = True
        started = await self._call(
            "POST",
            f"/sandboxes/{sid}/commands",
            what="exec (detached)",
            body={"command": script, "detached": True},
        )
        process_id = _int_or_none(started.get("processId"))
        if process_id is None or process_id < 1:
            raise ExecutionBackendError(f"detached exec on sandbox {sid} returned no processId")
        flight.process_id = process_id
        path = f"/sandboxes/{sid}/commands/{process_id}"
        deadline = self._clock() + timeout_s + _KILL_GRACE_S + _WRAPPER_SLACK_S + _START_WAIT_S
        while True:
            await self._sleep(self._poll_interval_s)
            status = await self._call("GET", path, what="exec status")
            still_running = status.get("running") is True and status.get("status") not in (
                "exited",
                "lost",
            )
            if not still_running:
                return _RawRun(
                    stdout=_str(status.get("stdout")),
                    stderr=_str(status.get("stderr")),
                    exit_code=_int_or_none(status.get("exitCode")),
                    api_timed_out=False,
                )
            if self._clock() >= deadline:
                # Backstop only: the in-VM timeout should have fired long ago.
                await self._stop_command(process_id)
                cleaned = await self._cleanup_after_kill(flight.spool)
                return _RawRun(
                    stdout=_str(status.get("stdout")),
                    stderr=_str(status.get("stderr")),
                    exit_code=None,
                    api_timed_out=True,
                    cleaned=cleaned,
                )

    def _finish(
        self,
        raw: _RawRun,
        parsed: _Wrapped | None,
        marker: str,
        duration_ms: int,
        cwd: str | None,
    ) -> ExecResult:
        if parsed is None:
            if raw.api_timed_out:
                out, out_cut = _cap(_after_begin(raw.stdout, marker), 0)
                err, err_cut = _cap(_after_begin(raw.stderr, marker), 0)
                return ExecResult(
                    exit_code=-1,
                    stdout=out,
                    stderr=err,
                    duration_ms=duration_ms,
                    timed_out=True,
                    truncated=out_cut or err_cut,
                )
            raise ExecutionBackendError(
                f"exec on sandbox {self._sandbox_id} returned no wrapper result "
                f"(Boat exit code {raw.exit_code!r}): {_tail(raw.stderr)}"
            )
        if parsed.status in ("fw_drift", "no_runner"):
            raise NetPolicyUnsupported(
                f"DENY_ALL no longer holds on sandbox {self._sandbox_id} ({parsed.status}): "
                "the owner REJECT rule is not first in OUTPUT; refusing to run"
            )
        if parsed.status == "no_root":
            raise WorkspaceLost(
                f"workspace {self._id} root vanished from sandbox {self._sandbox_id}"
            )
        if parsed.status in ("reap_failed", "busy", "no_lock"):
            what = {
                "reap_failed": f"could not confirm that every {RUNNER_ACCOUNT} process is gone",
                "busy": "another exec wrapper still holds the exec lock",
                "no_lock": "could not open the exec lock",
            }[parsed.status]
            raise ExecutionBackendError(
                f"exec refused on sandbox {self._sandbox_id} before the workload ran: {what} "
                f"({parsed.status}). The workspace is unclean: every later call re-runs the "
                "cleanup first and is refused until it is confirmed; destroy() still works."
            )
        if parsed.status == "cwd_escape":
            raise ValueError(f"path escapes workspace root: {cwd!r}")
        if parsed.status == "cwd_missing":
            shown = cwd if cwd is not None else "work"
            return ExecResult(
                exit_code=127,
                stdout="",
                stderr=f"working directory not found in workspace {self._id}: {shown!r}",
                duration_ms=duration_ms,
            )
        if parsed.status != "ok":
            raise ExecutionBackendError(
                f"exec wrapper failed on sandbox {self._sandbox_id}: {_shown(parsed.status)}"
            )
        out, out_cut = _cap(parsed.stdout, parsed.out_bytes)
        err, err_cut = _cap(parsed.stderr, parsed.err_bytes)
        timed_out = parsed.timed_out or raw.api_timed_out
        return ExecResult(
            exit_code=-1 if timed_out else parsed.rc,
            stdout=out,
            stderr=err,
            duration_ms=duration_ms,
            timed_out=timed_out,
            truncated=out_cut or err_cut,
        )

    async def put_file(self, path: str, content: bytes) -> None:
        self._check_alive()
        rel = _jail(path)
        data = bytes(content)
        if len(data) > FILE_API_CAP_BYTES:
            raise ExecutionBackendError(
                f"put_file {path!r}: {len(data)} bytes exceeds Boat's "
                f"{FILE_API_CAP_BYTES}-byte files-API cap"
            )
        async with self._lock:
            self._check_alive()
            await self._ensure_restored("put_file")
            # Check, then use: holds because no exec runs (the lock) and the
            # runner can change nothing in the restored tree (see "Files").
            target = await self._resolve(rel, path, for_write=True)
            await self._write_file(target, data, what="put_file")

    async def get_file(self, path: str) -> bytes:
        """``GET /files?path=..&encoding=base64`` (``FileReadResponse``)."""
        self._check_alive()
        rel = _jail(path)
        async with self._lock:
            self._check_alive()
            await self._ensure_restored("get_file")
            target = await self._resolve(rel, path, for_write=False)
            answer = await self._call(
                "GET",
                f"/sandboxes/{self._sandbox_id}/files",
                what="get_file",
                params={"path": target, "encoding": "base64"},
            )
        content = _str(answer.get("content"))
        if answer.get("encoding") == "utf8":
            data = content.encode("utf-8")
        else:
            try:
                data = base64.b64decode(content, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ExecutionBackendError(
                    f"get_file {path!r}: Boat returned invalid base64"
                ) from exc
        size = _int_or_none(answer.get("size"))
        if size is not None and size != len(data):
            raise ExecutionBackendError(
                f"get_file {path!r}: Boat reported {size} bytes, decoded {len(data)}"
            )
        return data

    async def destroy(self) -> None:
        """Delete the sandbox (``DELETE /sandboxes/{id}`` with
        ``X-Ascii-Confirm-Delete: <id>``). Idempotent (I6): a 404 or a second
        call is a no-op. Never raises; a failed delete is logged loudly, and
        the sandbox then stops itself at its auto-stop deadline
        (``snapshots: false`` erases its disk on that stop)."""
        if self._destroyed:
            return
        sid = self._sandbox_id
        try:
            await self._api.request(
                "DELETE", f"/sandboxes/{sid}", headers={"X-Ascii-Confirm-Delete": sid}
            )
            self._destroyed = True
            self._log.info("BoatBackend deleted sandbox %s (workspace %s)", sid, self._id)
            self._log.info(_DELETED_LOG, sid, self._id, "destroy", "deleted")
        except _BoatHTTPError as exc:
            if exc.status == 404:
                self._destroyed = True
                self._log.info(_DELETED_LOG, sid, self._id, "destroy", "not-found")
            else:
                self._log.warning(
                    "Boat delete of sandbox %s failed (%s); it will stop at its "
                    "auto-stop deadline. Delete it manually.",
                    sid,
                    exc.detail,
                )
        except ExecutionBackendError as exc:
            self._log.warning(
                "Boat delete of sandbox %s failed (%s); it will stop at its "
                "auto-stop deadline. Delete it manually.",
                sid,
                exc,
            )
        finally:
            await self._api.aclose()


# --- backend --------------------------------------------------------------------


class BoatBackend:
    """``ExecutionBackend`` over Boat sandboxes. DARK: not registered in the
    factory (see the module docstring, "Activation (after ratification)").

    Construct with an injected ``transport`` (an ``httpx.MockTransport`` in
    tests), ``sleep`` and ``clock``; in production the defaults talk to
    ``$BOAT_API_URL`` (default ``https://boat.dev/api/v1``) with
    ``$BOAT_API_KEY`` read at use time. ``org`` and ``environment`` override
    ``$ANTIEK_BOAT_ORG`` and ``$ANTIEK_BOAT_ENVIRONMENT``; both are read and
    validated at use time, never at construction. There is no ``snapshots``
    override: every sandbox is created with ``snapshots: false``.
    """

    def __init__(
        self,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        api_url: str | None = None,
        org: str | None = None,
        environment: str | None = None,
        root_base: str = DEFAULT_ROOT_BASE,
        ready_timeout_s: float = _DEFAULT_READY_TIMEOUT_S,
        poll_interval_s: float = _DEFAULT_POLL_INTERVAL_S,
        sleep: Callable[[float], Awaitable[None]] | None = None,
        clock: Callable[[], float] | None = None,
        log: logging.Logger | None = None,
    ) -> None:
        self._transport = transport
        self._api_url = _validate_api_url(
            api_url or os.environ.get(BOAT_API_URL_ENV) or DEFAULT_BOAT_API_URL
        )
        self._org_override = org
        self._environment_override = environment
        self._root_base = _validate_root_base(root_base)
        self._ready_timeout_s = float(ready_timeout_s)
        self._poll_interval_s = float(poll_interval_s)
        self._sleep: Callable[[float], Awaitable[None]] = sleep or _default_sleep
        self._clock: Callable[[], float] = clock or time.monotonic
        self._log = log or logging.getLogger("antiek.exec_backend.boat")

    @property
    def name(self) -> str:
        return "boat"

    def _new_api(self) -> _BoatApi:
        return _BoatApi(base_url=self._api_url, transport=self._transport)

    def _org_pin(self) -> str | None:
        """The validated org pin, or ``None`` when unpinned."""
        raw = self._org_override if self._org_override is not None else os.environ.get(BOAT_ORG_ENV)
        pin = (raw or "").strip()
        if not pin:
            return None
        if not _ORG_ID_RE.match(pin):
            raise BackendUnavailable(
                f"{BOAT_ORG_ENV} must be an organization id (team_...), as GET /orgs lists "
                f"it: Boat reports wallets by id, so a name cannot be verified: {pin!r}"
            )
        return pin

    def _org_headers(self, pin: str | None) -> dict[str, str] | None:
        return {"X-Boat-Org": pin} if pin else None

    def _environment(self) -> str:
        """The validated product environment name."""
        raw = (
            self._environment_override
            if self._environment_override is not None
            else os.environ.get(BOAT_ENVIRONMENT_ENV)
        )
        name = (raw or "").strip() or DEFAULT_BOAT_ENVIRONMENT
        if not _ENVIRONMENT_NAME_RE.match(name):
            raise BackendUnavailable(
                f"{BOAT_ENVIRONMENT_ENV} is not a Boat environment name "
                f"(letters, digits, '.', '-', '_'; at most 64): {name!r}"
            )
        if name == BUILD_PLANE_ENVIRONMENT:
            raise BackendUnavailable(
                f"{BOAT_ENVIRONMENT_ENV}={name!r} is the BUILD plane's environment; product "
                "workspaces never run there (no sharing between planes)"
            )
        return name

    # -- probe --

    def probe(self) -> None:
        """Confirm the product plane can start sandboxes *now*, loudly.

        A missing ``BOAT_API_KEY``, a malformed org pin or environment name
        raises before any network call. Then two read-only calls:
        ``GET /limits`` (``X-Boat-Org: <pin>``) must carry ``canStart: true``
        and, with a pin, ``teamId == pin``; a scope ``403`` on it is logged as
        a WARNING and left to the per-create org checks.
        ``GET /environments?org=<pin>`` must list the environment passing
        nothing of the account; that read fails closed. Every other failure
        raises ``BackendUnavailable``. Synchronous by contract
        (``asyncio.run``); call it from a sync context."""
        _read_api_key()
        pin = self._org_pin()
        environment = self._environment()
        asyncio.run(self._probe(pin, environment))

    async def _probe(self, pin: str | None, environment: str) -> None:
        api = self._new_api()
        try:
            limits = await self._read_limits(api, pin)
            try:
                await self._verify_environment(api, pin, environment)
            except _BoatTransportError as exc:
                raise BackendUnavailable(f"Boat API unreachable: {exc}") from exc
            except _BoatHTTPError as exc:
                raise BackendUnavailable(
                    f"Boat refused the environments read: {exc.detail}"
                ) from exc
        finally:
            await api.aclose()
        env_state = "passes nothing"
        if limits is None:
            self._log.info(
                "BoatBackend ready (limits not readable with this key); environment=%s (%s); "
                "limits enforced=[cpu_cores, memory_mb, disk_mb via machine type; "
                "wall_clock_s via auto-stop]",
                environment,
                env_state,
            )
            return
        types = limits.get("machineTypes")
        # Only ids, machine type names and numbers reach the log: Boat's own
        # strings are not logged, so an answer echoing the key cannot leak it.
        available = (
            [
                _machine_token(t.get("type"))
                for t in types
                if isinstance(t, dict) and t.get("available") is True
            ]
            if isinstance(types, list)
            else []
        )
        self._log.info(
            "BoatBackend ready; wallet=%s; environment=%s (%s); sandboxes %s/%s; machine "
            "types available=%s; limits enforced=[cpu_cores, memory_mb, disk_mb via machine "
            "type; wall_clock_s via auto-stop]",
            _wallet_token(limits.get("teamId")),
            environment,
            env_state,
            _int_or_none(limits.get("activeSandboxes")),
            _int_or_none(limits.get("maxActiveSandboxes")),
            available or "unknown",
        )

    async def _read_limits(self, api: _BoatApi, pin: str | None) -> dict[str, Any] | None:
        """``GET /limits`` for the wallet a create would bill. ``None`` when
        the key's scope may not read it."""
        try:
            limits = await api.request("GET", "/limits", headers=self._org_headers(pin))
        except _BoatHTTPError as exc:
            if exc.status == 403 and exc.code in _SCOPE_FORBIDDEN_CODES:
                if pin is not None:
                    self._log.warning(
                        "BoatBackend probe: this key may not read GET /limits (%s); there is "
                        "no client-side canStart check: a create relies on Boat admitting the "
                        "POST, and the org pin on the X-Boat-Org header and the sandbox team "
                        "read-back",
                        exc.detail,
                    )
                else:
                    self._log.warning(
                        "BoatBackend probe: this key may not read GET /limits (%s); there is "
                        "no client-side canStart check and no %s pin, so nothing on this host "
                        "verifies the organization: a create relies on Boat admitting the POST",
                        exc.detail,
                        BOAT_ORG_ENV,
                    )
                return None
            raise BackendUnavailable(f"Boat refused the limits read: {exc.detail}") from exc
        except _BoatTransportError as exc:
            raise BackendUnavailable(f"Boat API unreachable: {exc}") from exc
        can_start = limits.get("canStart")
        if not isinstance(can_start, bool):
            # The OpenAPI (LimitsFields) requires canStart; LIVE_SHAPES.md's
            # 2026-11-09 personal-key answer lacks it. Shape drift, not billing.
            raise BackendUnavailable(
                "Boat's GET /limits answer carries no boolean 'canStart' (required by the "
                f"OpenAPI LimitsFields; got {_shown(can_start)}), so whether this wallet can start "
                "sandboxes is unknown. The response shape drifted from boat-v1.yaml: update "
                "this adapter before relying on it. Fields present: "
                f"{_scrub(', '.join(sorted(k for k in limits if isinstance(k, str))[:40]))}"
            )
        if can_start is not True:
            blocked = limits.get("blockedReason") or limits.get("startBlockedReason") or "unknown"
            raise BackendUnavailable(
                "Boat scope cannot start sandboxes now: "
                f"blockedReason={_shown(blocked)}, "
                f"billingStatus={_shown(limits.get('billingStatus'))}, "
                f"checkoutRequired={_shown(limits.get('checkoutRequired'))}, sandboxes "
                f"{_shown(limits.get('activeSandboxes'))}/"
                f"{_shown(limits.get('maxActiveSandboxes'))}. "
                "Resolve it in the Boat dashboard (billing is not part of the v1 API)."
            )
        if pin is not None:
            team_id = _str(limits.get("teamId"))
            if not team_id:
                raise BackendUnavailable(
                    f"{BOAT_ORG_ENV} pins organization {pin!r}, but Boat read the personal "
                    "wallet (no teamId): the key does not bill that organization"
                )
            if team_id != pin:
                raise BackendUnavailable(
                    f"{BOAT_ORG_ENV} pins organization {pin!r}, but the key's limits are "
                    f"for {_shown(team_id)}"
                )
        return limits

    async def _verify_environment(self, api: _BoatApi, pin: str | None, environment: str) -> None:
        """``GET /environments`` (``?org=`` is the only scope selector there)
        and refuse, fail closed, an environment that passes anything of the
        account, that is not listed, that is listed more than once under its
        name, or whose flags this key may not read.

        Raises ``BackendUnavailable`` for those; lets ``_BoatHTTPError`` (other
        refusals, 5xx) and ``_BoatTransportError`` through for the caller to
        map (``probe``: unavailable; ``create``: 5xx/transport are transient).
        Only the flags are read; ``envContents`` is never logged or kept."""
        try:
            listing = await api.request(
                "GET", "/environments", params={"org": pin} if pin is not None else None
            )
        except _BoatHTTPError as exc:
            if exc.status == 403 and exc.code in _SCOPE_FORBIDDEN_CODES:
                raise BackendUnavailable(
                    f"this key may not read GET /environments ({exc.detail}), so whether "
                    f"Boat environment {environment!r} passes account secrets into product "
                    "workspaces cannot be verified. Nothing inside the VM can see secrets "
                    "whose names the owner chose, so this is refused: mint the product key "
                    "with environment.read on its own environment."
                ) from exc
            if exc.status in (401, 402, 403):
                raise BackendUnavailable(
                    f"Boat refused the environments read: {exc.detail}"
                ) from exc
            raise
        entries = listing.get("environments")
        matches = [
            e
            for e in (entries if isinstance(entries, list) else [])
            if isinstance(e, dict) and e.get("name") == environment
        ]
        if not matches:
            raise BackendUnavailable(
                f"Boat environment {environment!r} is not in this key's GET /environments "
                "listing, so its flags cannot be verified: create it (safe for third "
                f"parties) or set {BOAT_ENVIRONMENT_ENV} to one this key can read"
            )
        if len(matches) > 1:
            # Which one a create by name lands in is not documented, so no
            # single entry's flags can stand for it.
            raise BackendUnavailable(
                f"this key's GET /environments listing has {len(matches)} environments "
                f"named {environment!r}, so which one a create would use, and whether it "
                "passes account credentials into product workspaces, cannot be verified. "
                f"Give the product environment a unique name (and set {BOAT_ENVIRONMENT_ENV})."
            )
        problems = _environment_problems(matches[0])
        if problems:
            raise BackendUnavailable(
                f"Boat environment {environment!r} would pass account credentials into "
                f"product workspaces: {'; '.join(problems)}. Mark it 'safe for third parties' "
                "with proxyAiCredentials off."
            )

    # -- create --

    async def create(
        self,
        profile: WorkspaceProfile,
        *,
        limits: ResourceLimits,
        net_policy: NetPolicy,
    ) -> _BoatWorkspace:
        if net_policy.kind is NetPolicyKind.ALLOWLIST:
            # I4: owner rules can match CIDRs, never hostnames; a one-time DNS
            # resolution would be an approximation dressed as enforcement.
            raise NetPolicyUnsupported(
                "BoatBackend cannot enforce allowlist: Boat has no API network "
                "rules and in-VM owner rules cannot honestly match hostnames. Use "
                "ALLOW_ALL or DENY_ALL."
            )
        machine_type = select_machine_type(limits)
        ttl = _ttl_seconds(limits.wall_clock_s)
        _env_items(profile.env, "profile env")  # validate before anything bills
        _read_api_key()
        pin = self._org_pin()
        environment = self._environment()
        if profile.image:
            self._log.info(
                "BoatBackend ignores profile.image=%r: Boat boots its own VM image",
                profile.image,
            )

        wid = uuid.uuid4().hex
        name = _sandbox_name(profile.name, wid)
        api = self._new_api()
        try:
            # Fail closed before anything bills (see "Credentials").
            await self._verify_environment(api, pin, environment)
        except _BoatHTTPError as exc:
            await api.aclose()
            message = f"Boat environments read before create failed: {exc.detail}"
            if exc.status >= 500 or exc.status == 429:
                raise WorkspaceProvisionError(message) from exc
            raise BackendUnavailable(message) from exc
        except _BoatTransportError as exc:
            await api.aclose()
            raise WorkspaceProvisionError(
                f"Boat environments read before create failed: {exc}"
            ) from exc
        except BaseException:
            await api.aclose()
            raise
        headers = {"Idempotency-Key": f"{SANDBOX_NAME_PREFIX}{wid}"}
        headers.update(self._org_headers(pin) or {})
        body: dict[str, Any] = {
            "type": machine_type,
            "ttlSeconds": ttl,
            "environment": environment,
            "name": name,
            "labels": {"antiek-workspace": wid, "antiek-profile": _slug(profile.name)},
            # Always off: no constructor override (proposed product doctrine).
            "snapshots": False,
            "visibility": "private",
        }
        lost = _LostCreate(api=api, wid=wid, pin=pin, body=body, headers=headers)
        failure: ExecutionBackendError | None = None
        created: dict[str, Any] = {}
        try:
            created = await api.request("POST", "/sandboxes", body=body, headers=headers)
        except _BoatHTTPError as exc:
            failure = _create_error(exc)
            if exc.status >= 500:
                # "timeouts and 5xx are safe to retry with the same key": the
                # sandbox may exist; find it with the key, then sweep.
                lost.rediscover = lost.sweep = True
        except _BoatTransportError as exc:
            failure = WorkspaceProvisionError(f"Boat sandbox create failed: {exc}")
            lost.sweep = True
            lost.rediscover = exc.maybe_sent
        except BaseException:
            # Cancelled (or interrupted) while Boat may already have accepted
            # the create: recover and delete it, shielded, then re-raise.
            lost.rediscover = lost.sweep = True
            await _run_shielded(self._discard_lost_create(lost))
            raise
        sandbox = created.get("sandbox")
        record: dict[str, Any] = sandbox if isinstance(sandbox, dict) else {}
        sandbox_id = _str(record.get("id"))
        if failure is None and not _SANDBOX_ID_RE.match(sandbox_id):
            failure = WorkspaceProvisionError(
                "Boat sandbox create answered without a usable sandbox id"
            )
            lost.sweep = True
        if failure is None:
            # Accepted and billed from here, whatever happens next.
            _log_accepted(self._log, record, lost, via="create")
        if failure is not None:
            if lost.sweep:
                await _run_shielded(self._discard_lost_create(lost))
            else:
                await api.aclose()
            raise failure

        workspace = _BoatWorkspace(
            workspace_id=wid,
            sandbox_id=sandbox_id,
            sandbox_name=name,
            root=f"{self._root_base}/{wid}",
            api=api,
            deny_all=net_policy.kind is NetPolicyKind.DENY_ALL,
            environment=environment,
            profile=profile,
            limits=limits,
            sleep=self._sleep,
            clock=self._clock,
            poll_interval_s=self._poll_interval_s,
            log=self._log,
        )
        try:
            seen = _check_sandbox_record(
                record, sandbox_id=sandbox_id, pin=pin, environment=environment
            )
            ready = await self._wait_ready(api, sandbox_id)
            seen |= _check_sandbox_record(
                ready, sandbox_id=sandbox_id, pin=pin, environment=environment
            )
            if pin is not None and "team" not in seen:
                raise BackendUnavailable(
                    f"Boat never reported which organization sandbox {sandbox_id} bills "
                    f"(no 'team' field), so the {BOAT_ORG_ENV} pin {pin!r} cannot be "
                    "verified; the sandbox was deleted"
                )
            if "snapshots" not in seen:
                raise BackendUnavailable(
                    f"Boat never reported whether sandbox {sandbox_id} has snapshots off "
                    "(no 'snapshots' field), so product doctrine's snapshots-off rule "
                    "cannot be verified; the sandbox was deleted"
                )
            await workspace._provision()
            if net_policy.kind is NetPolicyKind.DENY_ALL:
                await workspace._enforce_deny_all()
        except BaseException:
            # Nothing half-built may leak or keep billing: delete, then
            # re-raise. Shielded, so a second cancellation cannot cut it short.
            await _run_shielded(workspace.destroy())
            raise
        self._log.info(
            "BoatBackend created workspace %s (sandbox %s %r, type=%s, ttl=%ss, "
            "environment=%s, network=%s, runner uid=%s)",
            wid,
            sandbox_id,
            name,
            machine_type,
            ttl,
            environment,
            net_policy.kind.value,
            workspace._runner_uid,
        )
        return workspace

    async def _wait_ready(self, api: _BoatApi, sandbox_id: str) -> dict[str, Any]:
        """Poll ``GET /sandboxes/{id}`` until ready/idle/running, within
        ``ready_timeout_s``; return the last ``Sandbox`` record."""
        deadline = self._clock() + self._ready_timeout_s
        last = "unknown"
        while True:
            try:
                info = await api.request("GET", f"/sandboxes/{sandbox_id}")
                sandbox = info.get("sandbox")
                record: dict[str, Any] = sandbox if isinstance(sandbox, dict) else {}
                state = _str(record.get("state"))
                last = state or "unknown"
                if state in _READY_STATES:
                    return record
                if state in _FAILED_STATES:
                    error = _str(record.get("error"))
                    raise WorkspaceProvisionError(
                        f"Boat sandbox {sandbox_id} entered state {state!r} before ready"
                        + (f": {_scrub(error)[:200]}" if error else "")
                    )
            except _BoatHTTPError as exc:
                if exc.status == 404:
                    raise WorkspaceProvisionError(
                        f"Boat sandbox {sandbox_id} vanished while provisioning ({exc.detail})"
                    ) from exc
                if exc.status in (401, 402, 403):
                    raise BackendUnavailable(
                        f"Boat refused the readiness poll of {sandbox_id}: {exc.detail}"
                    ) from exc
                if exc.status < 500 and exc.status != 429:
                    raise WorkspaceProvisionError(
                        f"Boat readiness poll of {sandbox_id} failed: {exc.detail}"
                    ) from exc
                last = f"poll error {exc.code}"
            except _BoatTransportError:
                last = "poll transport error"
            if self._clock() >= deadline:
                raise WorkspaceProvisionError(
                    f"Boat sandbox {sandbox_id} not ready within {self._ready_timeout_s:g}s "
                    f"(last state {_shown(last)}); it was deleted"
                )
            await self._sleep(self._poll_interval_s)

    async def _discard_lost_create(self, lost: _LostCreate) -> None:
        """Best effort, never raises; closes ``lost.api`` at the end. Find
        and delete what a create whose answer was lost may have made.

        First (``lost.rediscover``) the documented recovery: the same
        ``POST /sandboxes`` with the same ``Idempotency-Key`` and body returns
        the sandbox bound to that key; ``409 idempotency_in_progress`` means it
        is still being minted, so wait and ask again, a bounded number of
        times. Whatever sandbox comes back is deleted. Then
        (``lost.sweep``) the label sweep, as a second net. The auto-stop TTL
        is the last backstop."""
        api = lost.api
        try:
            deleted: set[str] = set()
            if lost.rediscover:
                found = await self._rediscover(lost)
                if found is not None:
                    sid = _str(found.get("id"))
                    _log_accepted(self._log, found, lost, via="repost")
                    if await self._delete_orphan(api, sid, lost.wid):
                        deleted.add(sid)
            if lost.sweep:
                await self._sweep_orphan(api, lost, skip=deleted)
        except Exception as exc:  # cleanup must never mask the real failure
            self._log.warning(
                "cleanup after the lost create of workspace %s failed (%s); any sandbox it "
                "made stops itself at its auto-stop deadline",
                lost.wid,
                type(exc).__name__,
            )
        finally:
            await api.aclose()

    async def _rediscover(self, lost: _LostCreate) -> dict[str, Any] | None:
        """The ``Sandbox`` record Boat bound to ``lost``'s ``Idempotency-Key``
        (with a valid id), or ``None``. Never raises ``ExecutionBackendError``."""
        for attempt in range(1, _REDISCOVER_ATTEMPTS + 1):
            try:
                again = await lost.api.request(
                    "POST",
                    "/sandboxes",
                    body=lost.body,
                    headers=lost.headers,
                    timeout_s=_CLEANUP_HTTP_TIMEOUT_S,
                )
            except _BoatHTTPError as exc:
                if exc.code == "idempotency_in_progress" and attempt < _REDISCOVER_ATTEMPTS:
                    await self._sleep(self._poll_interval_s)
                    continue
                self._log.warning(
                    "same-key re-POST for the lost create of workspace %s: %s",
                    lost.wid,
                    exc.detail,
                )
                return None
            except ExecutionBackendError as exc:
                self._log.warning(
                    "same-key re-POST for the lost create of workspace %s: %s", lost.wid, exc
                )
                return None
            sandbox = again.get("sandbox")
            if isinstance(sandbox, dict) and _SANDBOX_ID_RE.match(_str(sandbox.get("id"))):
                return sandbox
            return None
        return None

    async def _delete_orphan(self, api: _BoatApi, sid: str, wid: str) -> bool:
        """``DELETE /sandboxes/{sid}``; True when it is gone (404 included).
        Never raises ``ExecutionBackendError``."""
        try:
            await api.request(
                "DELETE",
                f"/sandboxes/{sid}",
                headers={"X-Ascii-Confirm-Delete": sid},
                timeout_s=_CLEANUP_HTTP_TIMEOUT_S,
            )
        except _BoatHTTPError as exc:
            if exc.status == 404:
                self._log.info(_DELETED_LOG, sid, wid, "orphan", "not-found")
                return True
            self._log.warning(
                "could not delete orphaned Boat sandbox %s (%s); it stops at its "
                "auto-stop deadline",
                sid,
                exc.detail,
            )
            return False
        except ExecutionBackendError as exc:
            self._log.warning(
                "could not delete orphaned Boat sandbox %s (%s); it stops at its "
                "auto-stop deadline",
                sid,
                exc,
            )
            return False
        self._log.warning("deleted orphaned Boat sandbox %s of workspace %s", sid, wid)
        self._log.info(_DELETED_LOG, sid, wid, "orphan", "deleted")
        return True

    async def _sweep_orphan(self, api: _BoatApi, lost: _LostCreate, *, skip: set[str]) -> None:
        """Delete a sandbox carrying this workspace's label that this caller
        owns. In an organization's scope ``GET /sandboxes`` also lists
        teammates' sandboxes, so an entry whose ``access`` is not ``owner`` or
        whose labels do not carry this workspace id is never touched."""
        wid, pin = lost.wid, lost.pin
        try:
            listing = await api.request(
                "GET",
                "/sandboxes",
                params={"label": f"antiek-workspace={wid}"},
                headers=self._org_headers(pin),
                timeout_s=_CLEANUP_HTTP_TIMEOUT_S,
            )
        except ExecutionBackendError as exc:
            self._log.warning(
                "could not check for an orphaned Boat sandbox of workspace %s (%s); "
                "any such sandbox stops itself at its auto-stop deadline",
                wid,
                exc,
            )
            return
        sandboxes = listing.get("sandboxes")
        for entry in sandboxes if isinstance(sandboxes, list) else []:
            if not isinstance(entry, dict):
                continue
            sid = _str(entry.get("id"))
            labels = entry.get("labels")
            if (
                not _SANDBOX_ID_RE.match(sid)
                or sid in skip
                or not isinstance(labels, dict)
                or labels.get("antiek-workspace") != wid
                or entry.get("access", "owner") != "owner"
            ):
                continue
            _log_accepted(self._log, entry, lost, via="sweep")
            await self._delete_orphan(api, sid, wid)


@dataclass
class _LostCreate:
    """What ``_discard_lost_create`` needs to find a create's sandbox again:
    the exact body and headers (same key, same body) and the label. Also
    the create's spend-ledger state (the ids already logged as accepted)."""

    api: _BoatApi
    wid: str
    pin: str | None
    body: Mapping[str, Any]
    headers: Mapping[str, str]
    rediscover: bool = False
    sweep: bool = False
    accepted: set[str] = field(default_factory=set)


def _log_accepted(
    log: logging.Logger, record: Mapping[str, Any], lost: _LostCreate, *, via: str
) -> None:
    """The spend-ledger line for a sandbox Boat accepted, once per id (see
    "Spend ledger lines"). Boat's record values win over the requested type
    and TTL. Each field is checked for its own shape (a machine type name, an
    integer, an RFC 3339 date-time) and logged as ``unknown`` otherwise, so
    no string Boat returns reaches the line unchecked."""
    sid = _str(record.get("id"))
    if sid in lost.accepted:
        return
    lost.accepted.add(sid)
    machine = record.get("type") if isinstance(record.get("type"), str) else lost.body.get("type")
    ttl = _int_or_none(record.get("ttlSeconds"))
    log.info(
        _ACCEPTED_LOG,
        _log_token(sid),
        _log_token(lost.wid),
        _machine_token(machine),
        _log_token(ttl if ttl is not None else lost.body.get("ttlSeconds")),
        _date_time_token(record.get("createdAt")),
        via,
    )


def _check_sandbox_record(
    record: Mapping[str, Any], *, sandbox_id: str, pin: str | None, environment: str
) -> frozenset[str]:
    """Refuse a ``Sandbox`` record that bills another organization, sits in
    another environment, holds the creator's logins or has snapshots on.
    Each field is checked when the record carries it; returns which of
    ``team`` and ``snapshots`` it carried, for the caller to require.
    Messages name ``sandbox_id``, the id the create answer gave and that was
    checked, never the record's own ``id``."""
    sid = sandbox_id
    seen = frozenset(field for field in ("team", "snapshots") if field in record)
    if pin is not None and "team" in seen:
        team = record.get("team")
        team_id = _str(team.get("id")) if isinstance(team, dict) else ""
        if team_id != pin:
            raise BackendUnavailable(
                f"Boat sandbox {sid} bills {_shown(team_id or 'the personal wallet')}, not the "
                f"{BOAT_ORG_ENV} pin {pin!r}; the sandbox was deleted"
            )
    if "environment" in record and record.get("environment") != environment:
        raise BackendUnavailable(
            f"Boat sandbox {sid} is attached to environment {_shown(record.get('environment'))}, "
            f"not {environment!r}; the sandbox was deleted"
        )
    if record.get("holdsCreatorLogins") is True:
        raise BackendUnavailable(
            f"Boat sandbox {sid} holds its creator's personal logins "
            "(holdsCreatorLogins); the sandbox was deleted"
        )
    # Created with ``snapshots: false``; the record's ``snapshots`` is
    # "False when the sandbox was created with snapshots off" (OpenAPI).
    snapshots = record.get("snapshots")
    if "snapshots" in record and snapshots is not False:
        shown = repr(snapshots) if snapshots is None or snapshots is True else "a non-boolean"
        raise BackendUnavailable(
            f"Boat sandbox {sid} reports snapshots {shown}, not false, although it was "
            "created with snapshots off (product doctrine keeps snapshots off); the "
            "sandbox was deleted"
        )
    return seen


def _create_error(exc: _BoatHTTPError) -> ExecutionBackendError:
    """Map a refused ``POST /sandboxes`` onto the seam's taxonomy."""
    message = f"Boat refused sandbox create: {exc.detail}"
    if exc.status == 401:
        return BackendUnavailable(message)
    if exc.status == 400 and exc.code == "unknown_environment":
        return BackendUnavailable(f"{message} (does {BOAT_ENVIRONMENT_ENV} name an environment?)")
    if exc.status == 403:
        if exc.code in _MACHINE_CLASS_CODES:
            return WorkspaceProvisionError(message)
        return BackendUnavailable(message)
    if exc.status == 402:
        return BackendUnavailable(message)
    if exc.status == 429:
        if exc.code == "trial_compute_limit_reached":
            return BackendUnavailable(message)
        return WorkspaceProvisionError(message)
    if exc.status == 404:
        return BackendUnavailable(f"{message} (is {BOAT_API_URL_ENV} right?)")
    return WorkspaceProvisionError(message)


__all__ = ["BoatBackend"]
