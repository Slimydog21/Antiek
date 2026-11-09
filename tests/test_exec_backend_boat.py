"""``BoatBackend`` tests: an in-memory Boat API behind ``httpx.MockTransport``.

Hermetic: no network, no real key, no Boat sandbox. Three layers:

* **The fake API** (``FakeBoat``) speaks the OpenAPI contract
  ``boat-v1.yaml``: exact paths, the request-body field names of
  ``CreateSandboxRequest`` / ``CommandRequest`` / ``FileWriteRequest``, the
  query names of each GET, the ``X-Ascii-Confirm-Delete`` and
  ``Idempotency-Key`` / ``X-Boat-Org`` headers (with the documented replay:
  same key and body return the same sandbox, ``409 idempotency_key_reused``
  for another body), ``timeoutSeconds`` 1-600, base64 file encodings, the
  ``ErrorEnvelope`` error body, the sandbox ``state`` progression and an 8 MiB
  per-stream output cap that keeps the tail. Every request the backend sends
  that the contract does not allow is recorded as a *violation*, and the
  ``fake`` fixture fails the test at teardown if there is one, so every test
  is also a request-shape test.
* **The fake VM.** Every command the backend sends (provisioning, DENY_ALL
  apply and read-back, path resolution, the exec wrapper, cleanup) is run as
  a real local POSIX ``sh`` (asynchronously, so concurrent calls really
  overlap unless the backend serializes them), with a stub directory first on
  ``PATH`` that shadows the privileged tools (``sudo``, ``useradd``, ``id`` for
  the runner account, ``chown``, ``pkill``, ``sysctl``, ``iptables``,
  ``ip6tables``). The workspace root lives under ``tmp_path`` (which the
  fake's files API serves as the VM's ``/tmp``). So the wrapper's real
  quoting, env scrub, cwd jail, ``timeout`` group kill, ``chmod`` restore and
  ``head -c`` truncation run here, not a re-implementation of them. The stubs
  never escalate: the real ``sudo`` is asserted to be shadowed before any
  command runs. The ``sudo`` stub logs the account each command was asked to
  run as; the ``pkill`` stub kills the "runner" processes of the fake VM (the
  test user's processes whose ``HOME`` is a workspace root, which only the
  wrapper's ``env -i`` sets).
* **Dark-module guards**: the factory still rejects ``kind="boat"``, the
  package does not export the adapter, the activation diff is documented, and
  the I2 zero-file grep still holds with this module in the package.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import inspect
import json
import logging
import os
import pathlib
import re
import shutil
import signal
import stat
import subprocess
import sys
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, cast

import httpx
import pytest

import runtime.exec_backend as exec_backend_pkg
from runtime.exec_backend import (
    ALLOW_ALL,
    DENY_ALL,
    MAX_OUTPUT_BYTES,
    BackendUnavailable,
    ExecutionBackend,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceLost,
    WorkspaceProfile,
    WorkspaceProvisionError,
    build_execution_backend,
)
from runtime.exec_backend import boat_backend as bb
from runtime.exec_backend import factory as factory_mod
from runtime.exec_backend.boat_backend import BoatBackend, select_machine_type

# --- constants --------------------------------------------------------------

#: Fake bearer keys. Shaped like Boat keys, valid nowhere.
FAKE_KEY = "boat_fAkEkEyNoTrEaL0123456789abcdefABCDEF"
OTHER_KEY = "boat_rOtAtEdFaKeKeY9876543210fedcbaFEDCBA"
ACCEPTED_KEYS = frozenset({FAKE_KEY, OTHER_KEY})

#: Fake organization ids (``team_`` + uuid, the ``Org.id`` shape).
FAKE_ORG = "team_00000000-0000-4000-8000-0000000000aa"
OTHER_ORG = "team_00000000-0000-4000-8000-0000000000bb"

#: The two real research boxes that must never be touched. They appear in the
#: fake only as other people's sandboxes in an org-wide listing.
PROTECTED_SANDBOXES = frozenset({"bx_235rmpn3", "bx_35hs5p53"})

RUNNER_UID = 4242

#: The boat CLI config Boat wrote into the measured noEnv VMs, in the shape
#: measured on 2026-11-09: 63 bytes, two-space indent, exactly ``api_url``
#: (16 characters) and ``channel`` (10 characters matching
#: ``^(boat|ascii|sk)[_-]``; the exact value was not recorded).
KEYLESS_CLI_CONFIG = '{\n  "api_url": "https://boat.dev",\n  "channel": "boat_prod1"\n}\n'

#: The factory's kinds while the adapter is dark. The ratification PR flips
#: this to include "boat" (see the module docstring's activation section).
EXPECTED_FACTORY_KINDS = frozenset({"local", "docker"})

# Field and query names copied from boat-v1.yaml (OpenAPI 3.1, v1.0.0).
#: components.schemas.CreateSandboxRequest.properties
CREATE_SANDBOX_FIELDS = frozenset(
    {
        "type",
        "ttlSeconds",
        "labels",
        "env",
        "environment",
        "noEnv",
        "snapshots",
        "monitoring",
        "failFast",
        "count",
        "setupScript",
        "name",
        "visibility",
        "hostedPorts",
        "files",
        "org",
        "teamId",
        "from",
    }
)
#: components.schemas.CommandRequest.properties
COMMAND_FIELDS = frozenset({"command", "cwd", "timeoutSeconds", "detached", "stream"})
#: components.schemas.FileWriteRequest.properties
FILE_WRITE_FIELDS = frozenset({"path", "content", "encoding"})
#: paths./limits.get.parameters (query)
LIMITS_QUERY = frozenset({"org", "teamId"})
#: paths./environments.get.parameters (query)
ENVIRONMENTS_QUERY = frozenset({"org"})
#: paths./sandboxes.get.parameters (query)
SANDBOX_LIST_QUERY = frozenset(
    {
        "org",
        "limit",
        "cursor",
        "sort",
        "state",
        "name",
        "namePrefix",
        "stoppedBefore",
        "dataExpired",
        "label",
        "include",
    }
)
#: paths./sandboxes/{sandboxId}/files.get.parameters (query)
FILE_READ_QUERY = frozenset({"path", "encoding"})
#: paths./sandboxes/{sandboxId}/commands/{processId}.get.parameters (query)
COMMAND_STATUS_QUERY = frozenset({"tailBytes", "stdoutOffset", "stderrOffset"})
#: components.parameters.SandboxId
SANDBOX_ID_RE = re.compile(r"^bx_[23456789abcdefghjkmnpqrstuvwxyz]{8}$")
#: CreateSandboxRequest.labels key rule
LABEL_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,62}$")
#: CreateSandboxEnvironmentRequest.name rule
ENV_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,64}$")
MACHINE_TYPE_ENUM = frozenset({"small", "default", "large", "xlarge"})
FILE_CAP = 5 * 1024 * 1024
#: Boat's per-stream command output cap (api_v1.md; tailBytes default 8 MiB).
#: Which end a synchronous answer keeps is undocumented; the fake keeps the
#: tail (what the detached status endpoint documents), the pessimistic choice.
BOAT_STREAM_CAP = 8 * 1024 * 1024
_ID_ALPHABET = "23456789abcdefghjkmnpqrstuvwxyz"
_DROP = object()


# --- the fake VM's tool stubs -------------------------------------------------

_SUDO_STUB = """#!/bin/sh
# Test stub for sudo: drops sudo's own options and runs the command as the
# current user, logging the account it was asked to run as and the first
# words of the command (sudo.log). The runner account asking for sudo is
# refused unless the test granted it (state file runner_can_sudo).
as=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -n) shift ;;
    -u) as="$2"; shift 2 ;;
    --) shift; break ;;
    *) break ;;
  esac
done
printf '%s\\t%s %s %s\\n' "${as:-root}" "${1-}" "${2-}" "${3-}" >> "$STUB_STATE/sudo.log"
if [ "$as" = "antiek-runner" ] && [ "$1" = "sudo" ] && [ ! -e "$STUB_STATE/runner_can_sudo" ]; then
  echo "sudo: a password is required" >&2
  exit 1
fi
if [ "$1" = "chmod" ] && [ -e "$STUB_STATE/root_chmod.fail" ]; then
  echo "chmod: stub failure" >&2
  exit 1
fi
exec "$@"
"""

_ID_STUB = """#!/bin/sh
# Test stub for id: the runner account exists once useradd ran; its uid is
# the state file runner_uid.
if [ "$#" -eq 2 ] && [ "$1" = "-u" ] && [ "$2" = "antiek-runner" ]; then
  if [ -e "$STUB_STATE/runner" ]; then cat "$STUB_STATE/runner_uid"; exit 0; fi
  echo "id: 'antiek-runner': no such user" >&2
  exit 1
fi
exec __REAL_ID__ "$@"
"""

_USERADD_STUB = """#!/bin/sh
: > "$STUB_STATE/runner"
printf '%s\\n' "$*" >> "$STUB_STATE/useradd.log"
"""

_LOG_ONLY_STUB = """#!/bin/sh
printf '%s\\n' "$*" >> "$STUB_STATE/$(basename "$0").log"
exit 0
"""

_PKILL_STUB = """#!/bin/sh
# Test stub for pkill -KILL -u|-U antiek-runner. The fake VM has no second
# account, so its "runner processes" are the test user's processes whose HOME
# is a workspace root (only the wrapper's env -i sets that). Exit 0 when
# something was signalled, 1 when nothing matched: pkill's own convention.
printf '%s\\n' "$*" >> "$STUB_STATE/pkill.log"
prefix="$(cat "$STUB_STATE/runner_home_prefix")"
pids="$(grep -lzx -e "HOME=$prefix/.*" /proc/[0-9]*/environ 2>/dev/null \\
  | sed -n 's|^/proc/\\([0-9]*\\)/environ$|\\1|p')"
hit=1
for pid in $pids; do
  [ "$pid" = "$$" ] && continue
  kill -KILL "$pid" 2>/dev/null && hit=0
done
exit "$hit"
"""

_SYSCTL_STUB = """#!/bin/sh
# Test stub for sysctl -n fs.protected_hardlinks: the state file decides.
if [ "$1" = "-n" ] && [ "$2" = "fs.protected_hardlinks" ]; then
  cat "$STUB_STATE/protected_hardlinks"
  exit 0
fi
echo "sysctl: unsupported $*" >&2
exit 2
"""

_IPTABLES_STUB = """#!/bin/sh
# Test stub for iptables/ip6tables: OUTPUT rules kept in a state file.
t="$(basename "$0")"
f="$STUB_STATE/$t.rules"
if [ -e "$STUB_STATE/$t.fail" ]; then echo "$t: stub failure" >&2; exit 4; fi
[ "$1" = "-w" ] && shift
case "$1" in
  -I)
    uid="$(id -u "$7")" || exit 2
    rule="-A OUTPUT -m owner --uid-owner $uid -j REJECT"
    if [ -e "$STUB_STATE/$t.append" ]; then
      printf '%s\\n' "$rule" >> "$f"
    else
      { printf '%s\\n' "$rule"; cat "$f" 2>/dev/null; } > "$f.new" && mv "$f.new" "$f"
    fi ;;
  -S)
    printf '%s\\n' "-P OUTPUT ACCEPT"
    cat "$f" 2>/dev/null ;;
  *) echo "$t: unsupported $*" >&2; exit 2 ;;
esac
"""

#: Boat's own ufw rules sit in OUTPUT before ours is inserted at the top.
_SEED_RULES = "-A OUTPUT -j ufw-before-logging-output\n-A OUTPUT -j ufw-before-output\n"

_STUBBED_TOOLS = ("sudo", "id", "useradd", "chown", "pkill", "sysctl", "iptables", "ip6tables")


def _vm_tools_ok() -> bool:
    """The exec wrapper needs GNU coreutils and util-linux (see the module
    docstring); the fake VM runs it for real, so check they are here."""
    if sys.platform != "linux" or shutil.which("sh") is None or shutil.which("id") is None:
        return False
    probes = (
        ["env", "-C", "/", "true"],
        ["setsid", "--wait", "true"],
        ["timeout", "-k", "1", "1", "true"],
        ["realpath", "-m", "/x/../y"],
        ["head", "-c", "1", "/dev/null"],
        ["date", "+%s%N"],
        ["sleep", "0.01"],
        ["grep", "-lzx", "-e", ".*", "/proc/self/environ"],
    )
    try:
        for argv in probes:
            subprocess.run(argv, check=True, capture_output=True, timeout=10)
    except OSError, subprocess.SubprocessError:
        return False
    return True


_VM_TOOLS_OK = _vm_tools_ok()


# --- the fake Boat API -------------------------------------------------------


@dataclass
class Call:
    method: str
    route: str
    query: dict[str, list[str]]
    headers: httpx.Headers
    body: Any
    url: str


@dataclass
class Injected:
    """A scripted answer for matching method+route calls: the first ``skip``
    pass through, the next ``times`` are scripted. ``status == 0`` raises the
    transport error ``exc`` instead (its text carries the Authorization
    header, to prove redaction). ``after_effect`` lets the real handler run
    first (a create Boat accepted whose answer was lost); ``hang`` then never
    answers (until the caller is cancelled)."""

    method: str
    route: str
    status: int
    code: str
    message: str = "injected"
    times: int = 1
    after_effect: bool = False
    hang: bool = False
    skip: int = 0
    exc: type[httpx.TransportError] = httpx.ConnectError


@dataclass
class FakeClock:
    t: float = 1_000.0
    sleeps: list[float] = field(default_factory=list)

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.t += seconds
        await asyncio.sleep(0)  # a real suspension point, so cancellation can land


def _err(status: int, code: str, message: str) -> httpx.Response:
    """The OpenAPI ``ErrorEnvelope``, every required field present."""
    return httpx.Response(
        status,
        json={
            "ok": False,
            "type": "sandbox.error",
            "status": status,
            "code": code,
            "message": message,
            "error": {"code": code, "message": message, "status": status},
            "requestId": "req_fake0001",
        },
    )


def _ok(type_: str, http_status: int = 200, **fields: Any) -> httpx.Response:
    return httpx.Response(http_status, json={"ok": True, "type": type_, **fields})


def _env_record(name: str, **flags: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "name": name,
        "isDefault": name == "base",
        "latestVersionId": str(uuid.uuid4()),
        "safeForThirdParties": False,
        "passGithub": True,
        "passSecrets": True,
        "passSandboxCredentials": True,
        "passAgentsCredentials": True,
        "proxyAiCredentials": False,
        "credentialProfileId": None,
        "envContents": f"OPENAI_API_KEY=sk-envcontents-of-{name}\n",
        "secretFiles": [],
        "versions": [],
    }
    record.update(flags)
    return record


def _boat_stream(raw: bytes) -> tuple[str, bool]:
    """Boat's per-stream cap on a command answer (keeps the tail)."""
    if len(raw) > BOAT_STREAM_CAP:
        return raw[-BOAT_STREAM_CAP:].decode("utf-8", "replace"), True
    return raw.decode("utf-8", "replace"), False


class FakeBoat:
    """In-memory Boat API (see the module docstring)."""

    def __init__(self, tmp_path: pathlib.Path) -> None:
        self.tmp_path = tmp_path
        self.root_base = tmp_path / "antiek-ws"
        self.home = tmp_path / "home-user"
        self.home.mkdir()
        # Every Boat VM has a keyless CLI config (measured 2026-11-09, noEnv).
        cli_config = self.home / ".config/ascii/boat/config.json"
        cli_config.parent.mkdir(parents=True)
        cli_config.write_text(KEYLESS_CLI_CONFIG)
        self.state = tmp_path / "stub-state"
        self.state.mkdir()
        self.stubs = tmp_path / "stubs"
        self.stubs.mkdir()
        self._write_stubs()
        for family in ("iptables", "ip6tables"):
            (self.state / f"{family}.rules").write_text(_SEED_RULES)
        (self.state / "runner_uid").write_text(f"{RUNNER_UID}\n")
        (self.state / "protected_hardlinks").write_text("1\n")
        (self.state / "runner_home_prefix").write_text(os.path.realpath(self.root_base))
        self.path_env = f"{self.stubs}:{os.environ.get('PATH', '/usr/bin:/bin')}"
        for tool in _STUBBED_TOOLS:
            assert shutil.which(tool, path=self.path_env) == str(self.stubs / tool), tool

        self.calls: list[Call] = []
        self.violations: list[str] = []
        self.injected: list[Injected] = []
        self.sandboxes: dict[str, dict[str, Any]] = {}
        self.deleted: set[str] = set()
        self.polls: dict[str, int] = {}
        self.ready_after = 1
        self.state_script: list[str] = []
        self.team_for_new: str | None = None
        self.omit_team = False
        self.record_extras: dict[str, Any] = {}
        self.key_org: str | None = FAKE_ORG
        self.limits_override: dict[str, Any] = {}
        self.environments = [
            _env_record("base"),
            _env_record("antiek-product", safeForThirdParties=True),
            _env_record("antiek-product-eu", safeForThirdParties=True),
            _env_record("antiek-build"),
        ]
        self.list_extra: list[dict[str, Any]] = []
        self.extra_env: dict[str, str] = {}
        self.sync_timeouts = 0
        self.force_timed_out = 0
        self.exit_overrides: dict[str, int] = {}
        self.read_size_delta = 0
        self.create_id_override: str | None = None
        self.idem_keys: dict[str, tuple[Any, str]] = {}
        self.idem_in_progress = 0
        self.detached_hang = False
        self.delete_delay_s = 0.0
        self.processes: dict[int, dict[str, Any]] = {}
        #: Exec wrappers running right now, and every call that overlapped one.
        self.exec_running = 0
        self.overlaps: list[str] = []
        self._next_id = 0
        self._next_pid = 0

    # -- plumbing --

    def _write_stubs(self) -> None:
        real_id = shutil.which("id")
        assert real_id is not None
        scripts = {
            "sudo": _SUDO_STUB,
            "id": _ID_STUB.replace("__REAL_ID__", real_id),
            "useradd": _USERADD_STUB,
            "chown": _LOG_ONLY_STUB,
            "pkill": _PKILL_STUB,
            "sysctl": _SYSCTL_STUB,
            "iptables": _IPTABLES_STUB,
            "ip6tables": _IPTABLES_STUB,
        }
        for name, text in scripts.items():
            target = self.stubs / name
            target.write_text(text)
            target.chmod(0o755)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def violation(self, text: str) -> None:
        self.violations.append(text)

    def calls_to(self, method: str, route_re: str) -> list[Call]:
        rx = re.compile(route_re)
        return [c for c in self.calls if c.method == method and rx.fullmatch(c.route)]

    def commands(self) -> list[str]:
        return [
            c.body["command"]
            for c in self.calls_to("POST", r"/sandboxes/[^/]+/commands")
            if isinstance(c.body, dict) and isinstance(c.body.get("command"), str)
        ]

    def log_lines(self, name: str) -> list[str]:
        path = self.state / f"{name}.log"
        return path.read_text().splitlines() if path.exists() else []

    def _new_sandbox_id(self) -> str:
        n = self._next_id = self._next_id + 1
        chars = []
        for _ in range(8):
            n, r = divmod(n, len(_ID_ALPHABET))
            chars.append(_ID_ALPHABET[r])
        sid = "bx_" + "".join(reversed(chars))
        assert SANDBOX_ID_RE.match(sid) and sid not in PROTECTED_SANDBOXES
        return sid

    async def run_sh(self, script: str, sandbox_id: str, timeout_s: float) -> dict[str, Any]:
        env = {
            "PATH": self.path_env,
            "HOME": str(self.home),
            "LANG": "C.UTF-8",
            "STUB_STATE": str(self.state),
            # Every sandbox gets these two neutral variables (environments_access.md).
            "ASCII_TOKEN": "ascii-neutral-token",
            "BOAT_ID": sandbox_id,
            **self.extra_env,
        }
        proc = await asyncio.create_subprocess_exec(
            "sh",
            "-c",
            script,
            env=env,
            cwd=self.home,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout_s)
        except TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(proc.wait(), 5)
            return {
                "exitCode": None,
                "stdout": "",
                "stderr": "",
                "timedOut": True,
                "stdoutTruncated": False,
                "stderrTruncated": False,
            }
        stdout, out_cut = _boat_stream(out)
        stderr, err_cut = _boat_stream(err)
        return {
            "exitCode": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "timedOut": False,
            "stdoutTruncated": out_cut,
            "stderrTruncated": err_cut,
        }

    def _vm_path(self, raw: str) -> pathlib.Path | None:
        """Canonicalize like the files API: relative to /home/user, and only
        under /tmp or /home/user (the fake's home)."""
        candidate = raw if raw.startswith("/") else str(self.home / raw)
        real = os.path.realpath(candidate)
        if real.startswith("/tmp/") or real.startswith(f"{self.home}/"):
            return pathlib.Path(real)
        return None

    # -- the handler --

    async def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        assert request.url.path.startswith("/api/v1/"), request.url
        route = request.url.path[len("/api/v1") :]
        query = {k: request.url.params.get_list(k) for k in set(request.url.params.keys())}
        call = Call(request.method, route, query, request.headers, body, str(request.url))
        self.calls.append(call)

        for inj in self.injected:
            if inj.times > 0 and inj.method == request.method and re.fullmatch(inj.route, route):
                if inj.skip > 0:
                    inj.skip -= 1
                    break
                inj.times -= 1
                if inj.after_effect:
                    await self._dispatch(call)
                if inj.hang:
                    await asyncio.Event().wait()
                if inj.status == 0:
                    auth = request.headers.get("authorization", "")
                    raise inj.exc(f"{inj.message}; sent {auth}", request=request)
                return _err(inj.status, inj.code, inj.message)

        auth = request.headers.get("authorization", "")
        if not auth.startswith("Bearer ") or auth[len("Bearer ") :] not in ACCEPTED_KEYS:
            return _err(401, "unauthorized", "Unauthorized")
        return await self._dispatch(call)

    async def _dispatch(self, call: Call) -> httpx.Response:
        routes: list[tuple[str, str, Any]] = [
            ("GET", r"/limits", self._limits),
            ("GET", r"/environments", self._environments),
            ("POST", r"/sandboxes", self._create),
            ("GET", r"/sandboxes", self._list),
            ("GET", r"/sandboxes/(?P<sid>[^/]+)", self._get),
            ("DELETE", r"/sandboxes/(?P<sid>[^/]+)", self._delete),
            ("POST", r"/sandboxes/(?P<sid>[^/]+)/commands", self._command),
            ("GET", r"/sandboxes/(?P<sid>[^/]+)/commands/(?P<pid>[0-9]+)", self._command_status),
            ("DELETE", r"/sandboxes/(?P<sid>[^/]+)/commands/(?P<pid>[0-9]+)", self._command_stop),
            ("PUT", r"/sandboxes/(?P<sid>[^/]+)/files", self._write_file),
            ("GET", r"/sandboxes/(?P<sid>[^/]+)/files", self._read_file),
        ]
        for method, pattern, fn in routes:
            m = re.fullmatch(pattern, call.route)
            if method == call.method and m:
                sid = m.groupdict().get("sid")
                if sid is not None:
                    if not SANDBOX_ID_RE.match(sid):
                        self.violation(f"sandbox id {sid!r} breaks the SandboxId pattern")
                        return _err(400, "invalid_sandbox_id", "bad id")
                    if sid in PROTECTED_SANDBOXES:
                        self.violation(f"protected sandbox touched: {call.method} {call.route}")
                        return _err(403, "forbidden", "Forbidden")
                response = fn(call, **m.groupdict())
                if inspect.isawaitable(response):
                    response = await response
                return cast(httpx.Response, response)
        self.violation(f"no such operation in boat-v1.yaml: {call.method} {call.route}")
        return _err(404, "not_found", "no such route")

    def _check_query(self, call: Call, allowed: frozenset[str]) -> None:
        unknown = set(call.query) - allowed
        if unknown:
            self.violation(f"{call.method} {call.route}: unknown query {sorted(unknown)}")

    def _sandbox(self, sid: str) -> dict[str, Any] | None:
        if sid in self.deleted:
            return None
        return self.sandboxes.get(sid)

    @staticmethod
    def _org(call: Call) -> str | None:
        return (call.query.get("org") or [""])[0] or call.headers.get("x-boat-org")

    # -- account --

    def _limits(self, call: Call) -> httpx.Response:
        self._check_query(call, LIMITS_QUERY)
        org = self._org(call)
        if self.key_org is not None and org is not None and org != self.key_org:
            return _err(403, "api_key_org_mismatch", "This key belongs to another organization.")
        team = org or self.key_org
        data: dict[str, Any] = {
            "accessTier": "standard",
            "blockedReason": None,
            "canStart": True,
            "activeSandboxes": len(set(self.sandboxes) - self.deleted),
            "maxActiveSandboxes": 100,
            "billingStatus": "active",
            "sandboxPlanKey": "box_20",
            "machineTypes": [
                {"type": t, "available": t != "xlarge", "reason": None}
                for t in ("small", "default", "large", "xlarge")
            ],
        }
        if team:
            data["teamId"] = team
            data["teamRole"] = "owner"
        for key, value in self.limits_override.items():
            if value is _DROP:
                data.pop(key, None)
            else:
                data[key] = value
        return _ok("limits.info", **data)

    def _environments(self, call: Call) -> httpx.Response:
        self._check_query(call, ENVIRONMENTS_QUERY)
        if call.headers.get("x-boat-org"):
            self.violation("X-Boat-Org does not apply on /environments; only ?org= selects")
        return _ok("environments.list", environments=self.environments)

    # -- sandboxes --

    def _create(self, call: Call) -> httpx.Response:
        body = call.body
        if not isinstance(body, dict):
            self.violation("POST /sandboxes without a JSON object body")
            return _err(400, "invalid_json", "Request body must be valid JSON.")
        unknown = set(body) - CREATE_SANDBOX_FIELDS
        if unknown:
            self.violation(f"CreateSandboxRequest has no fields {sorted(unknown)}")
        if body.get("type", "default") not in MACHINE_TYPE_ENUM:
            self.violation(f"type {body.get('type')!r} not in the enum")
        ttl = body.get("ttlSeconds", 3600)
        if ttl is not None and (
            isinstance(ttl, bool) or not isinstance(ttl, int) or not 1 <= ttl <= 2_592_000
        ):
            self.violation(f"ttlSeconds {ttl!r} outside 1-2592000")
        labels = body.get("labels", {})
        if not isinstance(labels, dict) or len(labels) > 20:
            self.violation("labels must be an object of at most 20")
            labels = {}
        for key, value in labels.items():
            if not LABEL_KEY_RE.match(key) or not isinstance(value, str):
                self.violation(f"bad label {key!r}={value!r}")
            elif len(value.encode()) > 256:
                self.violation(f"label {key!r} value over 256 bytes")
        name = body.get("name", "")
        if not isinstance(name, str) or len(name) > 120:
            self.violation("name must be a string of at most 120")
        for flag in ("noEnv", "snapshots", "monitoring", "failFast"):
            if flag in body and not isinstance(body[flag], bool):
                self.violation(f"{flag} must be a boolean")
        if body.get("visibility", "private") not in ("private", "shared"):
            self.violation("visibility must be private or shared")
        environment = body.get("environment", "base")
        if not isinstance(environment, str) or not ENV_NAME_RE.match(environment):
            self.violation(f"environment {environment!r} is not an environment name")
        idem = call.headers.get("idempotency-key")
        if idem is not None and len(idem) > 255:
            self.violation("Idempotency-Key longer than 255")
        if environment not in {e["name"] for e in self.environments}:
            return _err(400, "unknown_environment", f"Unknown environment {environment}.")
        org = self._org(call)
        if self.key_org is not None and org is not None and org != self.key_org:
            return _err(403, "api_key_org_mismatch", "This key belongs to another organization.")
        if idem is not None and idem in self.idem_keys:
            # IdempotencyKey: same account, key and body -> the same sandbox.
            first_body, bound = self.idem_keys[idem]
            if self.idem_in_progress > 0:
                self.idem_in_progress -= 1
                return _err(409, "idempotency_in_progress", "Still creating; retry shortly.")
            if first_body != body:
                return _err(409, "idempotency_key_reused", "Key reused with another body.")
            replay = dict(self.sandboxes[bound])
            past = replay["state"] not in ("provisioning", "provisioned", "cloning")
            return _ok(
                "sandbox.created",
                200,
                status="ready" if past else "provisioning",
                ttlSeconds=replay["ttlSeconds"],
                sandbox=replay,
            )

        sid = self._new_sandbox_id()
        size = {"small": (2, 4), "default": (4, 8), "large": (8, 16), "xlarge": (16, 32)}
        vcpu, mem = size.get(str(body.get("type", "default")), (4, 8))
        team = self.team_for_new or org or self.key_org
        record: dict[str, Any] = {
            "id": sid,
            "name": name,
            "state": "provisioning",
            "error": None,
            "labels": dict(labels),
            "type": body.get("type", "default"),
            "vcpu": vcpu,
            "memoryGB": mem,
            "ttlSeconds": ttl,
            "snapshots": body.get("snapshots", True),
            "monitoring": True,
            "desktopAvailable": False,
            "snapshotAvailable": False,
            "team": {"id": team, "name": "Antiek"} if team else None,
            "createdBy": "fake",
            "access": "owner",
            **self.record_extras,
        }
        if self.omit_team:
            record.pop("team")
        self.sandboxes[sid] = record
        if idem is not None:
            self.idem_keys[idem] = (json.loads(json.dumps(body)), sid)
        answer = dict(record)
        if self.create_id_override is not None:
            answer["id"] = self.create_id_override
        return _ok("sandbox.created", 202, status="provisioning", ttlSeconds=ttl, sandbox=answer)

    def _list(self, call: Call) -> httpx.Response:
        self._check_query(call, SANDBOX_LIST_QUERY)
        wanted: list[tuple[str, str]] = []
        for item in call.query.get("label", []):
            key, _, value = item.partition("=")
            wanted.append((key, value))
        found = [
            dict(rec)
            for sid, rec in self.sandboxes.items()
            if sid not in self.deleted and all(rec["labels"].get(k) == v for k, v in wanted)
        ]
        # ``list_extra`` simulates an org-wide listing that ignores the filter;
        # a label value "__QUERIED__" takes the queried value, so a teammate's
        # sandbox can carry this workspace's label and only ``access`` differs.
        extras = []
        for entry in self.list_extra:
            copy = json.loads(json.dumps(entry))
            labels = copy.get("labels")
            if isinstance(labels, dict):
                for key, value in labels.items():
                    if value == "__QUERIED__":
                        labels[key] = dict(wanted).get(key, value)
            extras.append(copy)
        return _ok(
            "sandbox.list",
            sandboxes=found + extras,
            pageInfo={"nextCursor": None, "hasMore": False, "limit": 100},
        )

    def _get(self, call: Call, sid: str) -> httpx.Response:
        record = self._sandbox(sid)
        if record is None:
            return _err(404, "not_found", "Sandbox not found.")
        self.polls[sid] = self.polls.get(sid, 0) + 1
        if self.state_script:
            record["state"] = self.state_script.pop(0)
        elif self.polls[sid] >= self.ready_after:
            record["state"] = "ready"
        return _ok("sandbox.info", sandbox=dict(record))

    async def _delete(self, call: Call, sid: str) -> httpx.Response:
        if call.headers.get("x-ascii-confirm-delete") != sid:
            self.violation(f"DELETE {sid} without X-Ascii-Confirm-Delete: {sid}")
            return _err(409, "confirmation_required", "Confirm the delete.")
        if self._sandbox(sid) is None:
            return _err(404, "not_found", "Sandbox not found.")
        if self.delete_delay_s:
            await asyncio.sleep(self.delete_delay_s)  # a slow answer a cancel can cut
        self.deleted.add(sid)
        operation = {
            "id": "bdop_" + uuid.uuid4().hex,
            "kind": "sandbox",
            "targetId": sid,
            "reason": "explicit",
            "status": "pending",
            "attemptCount": 0,
            "requestedAt": "2026-11-09T12:00:00Z",
            "completedAt": None,
        }
        return _ok("sandbox.deleting", 202, operation=operation)

    # -- commands --

    async def _command(self, call: Call, sid: str) -> httpx.Response:
        if self._sandbox(sid) is None:
            return _err(404, "not_found", "Sandbox not found.")
        body = call.body
        if not isinstance(body, dict) or not isinstance(body.get("command"), str):
            self.violation("CommandRequest needs a string command")
            return _err(400, "invalid_json", "command required")
        unknown = set(body) - COMMAND_FIELDS
        if unknown:
            self.violation(f"CommandRequest has no fields {sorted(unknown)}")
        if body.get("stream"):
            self.violation("stream is not used by the backend")
        detached = body.get("detached", False)
        if not isinstance(detached, bool):
            self.violation("detached must be a boolean")
        timeout = body.get("timeoutSeconds", 30)
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
            self.violation(f"timeoutSeconds {timeout!r} outside 1-600")
            return _err(400, "invalid_timeout", "timeoutSeconds must be an integer 1-600.")
        script: str = body["command"]
        is_exec = "setsid --wait" in script
        if self.exec_running:
            self.overlaps.append(f"command sent while an exec wrapper ran: {script[:60]!r}")
        if detached:
            self._next_pid += 1
            pid = self._next_pid
            if self.detached_hang:
                self.processes[pid] = {"hang": True, "stopped": False}
            else:
                self.processes[pid] = {
                    "hang": False,
                    "stopped": False,
                    **(await self.run_sh(script, sid, 120)),
                }
            return _ok(
                "command.started",
                success=True,
                processId=pid,
                pid=10_000 + pid,
                command=script[:64],
                startedAt="2026-11-09T12:00:00Z",
            )
        if self.sync_timeouts > 0 and is_exec:
            self.sync_timeouts -= 1
            result: dict[str, Any] = {
                "exitCode": None,
                "stdout": "",
                "stderr": "",
                "timedOut": True,
                "stdoutTruncated": False,
                "stderrTruncated": False,
            }
        else:
            self.exec_running += int(is_exec)
            try:
                result = await self.run_sh(script, sid, timeout)
            finally:
                self.exec_running -= int(is_exec)
            if is_exec and self.force_timed_out > 0:
                self.force_timed_out -= 1
                result["timedOut"] = True
        for needle, code in self.exit_overrides.items():
            if needle in script:
                result["exitCode"] = code
        return _ok(
            "command.finished",
            success=result["exitCode"] == 0,
            commandId="cmd_fake",
            signal=None,
            cwd=str(self.home),
            **result,
        )

    def _command_status(self, call: Call, sid: str, pid: str) -> httpx.Response:
        self._check_query(call, COMMAND_STATUS_QUERY)
        proc = self.processes.get(int(pid))
        if self._sandbox(sid) is None or proc is None:
            return _err(404, "not_found", "Process not found.")
        if proc["hang"] and not proc["stopped"]:
            return _ok(
                "command.status",
                success=True,
                processId=int(pid),
                status="running",
                running=True,
                exitCode=None,
                stdout="",
                stderr="",
            )
        return _ok(
            "command.status",
            success=True,
            processId=int(pid),
            status="exited",
            running=False,
            exitCode=proc.get("exitCode"),
            stdout=proc.get("stdout", ""),
            stderr=proc.get("stderr", ""),
        )

    def _command_stop(self, call: Call, sid: str, pid: str) -> httpx.Response:
        proc = self.processes.get(int(pid))
        if self._sandbox(sid) is None or proc is None:
            return _err(404, "not_found", "Process not found.")
        proc["stopped"] = True
        return _ok(
            "command.stopped", processId=int(pid), running=False, signaled=True, command=None
        )

    # -- files --

    def _write_file(self, call: Call, sid: str) -> httpx.Response:
        if self._sandbox(sid) is None:
            return _err(404, "not_found", "Sandbox not found.")
        if self.exec_running:
            self.overlaps.append("PUT /files while an exec wrapper ran")
        body = call.body
        if not isinstance(body, dict):
            self.violation("FileWriteRequest must be an object")
            return _err(400, "invalid_json", "bad body")
        unknown = set(body) - FILE_WRITE_FIELDS
        if unknown:
            self.violation(f"FileWriteRequest has no fields {sorted(unknown)}")
        encoding = body.get("encoding", "utf8")
        if encoding != "base64":
            self.violation(f"backend must write base64 (binary-safe), sent {encoding!r}")
        try:
            data = (
                base64.b64decode(body["content"], validate=True)
                if encoding == "base64"
                else str(body["content"]).encode()
            )
        except KeyError, ValueError:
            self.violation("FileWriteRequest content is not valid base64")
            return _err(400, "invalid_json", "bad content")
        target = self._vm_path(str(body.get("path", "")))
        if target is None:
            return _err(400, "invalid_path", "Path must resolve under /home/user or /tmp.")
        if len(data) > FILE_CAP:
            return _err(413, "file_too_large", "File is over 5 MiB.")
        if not target.parent.is_dir():
            return _err(400, "invalid_path", "Parent folder does not exist.")
        if target.exists() and not target.is_file():
            # A real write onto a FIFO would block; the fake refuses instead of hanging.
            self.violation(f"files API asked to write a non-regular file: {target}")
            return _err(400, "invalid_path", "Not a regular file.")
        target.write_bytes(data)
        return _ok(
            "file.written", success=True, path=str(target), encoding=encoding, size=len(data)
        )

    def _read_file(self, call: Call, sid: str) -> httpx.Response:
        if self._sandbox(sid) is None:
            return _err(404, "not_found", "Sandbox not found.")
        if self.exec_running:
            self.overlaps.append("GET /files while an exec wrapper ran")
        self._check_query(call, FILE_READ_QUERY)
        encoding = (call.query.get("encoding") or ["utf8"])[0]
        if encoding != "base64":
            self.violation(f"backend must read base64 (binary-safe), asked {encoding!r}")
        target = self._vm_path((call.query.get("path") or [""])[0])
        if target is None or not target.is_file():
            return _err(400, "invalid_path", "No such file.")
        data = target.read_bytes()
        if len(data) > FILE_CAP:
            return _err(413, "file_too_large", "File is over 5 MiB.")
        return _ok(
            "file.read",
            success=True,
            path=str(target),
            encoding="base64",
            size=len(data) + self.read_size_delta,
            content=base64.b64encode(data).decode(),
        )


# --- fixtures and helpers -------------------------------------------------------


@pytest.fixture(autouse=True)
def _boat_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOAT_API_KEY", FAKE_KEY)
    monkeypatch.setenv("ANTIEK_BOAT_ORG", FAKE_ORG)
    for name in (
        "ANTIEK_BOAT_ENVIRONMENT",
        "BOAT_API_URL",
        "BOAT_BUILD_API_KEY",
        "ANTIEK_EXEC_BACKEND",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake(tmp_path: pathlib.Path) -> Iterator[FakeBoat]:
    if not _VM_TOOLS_OK:
        pytest.skip("the fake VM needs sh, GNU coreutils (env -C, timeout) and setsid --wait")
    if not str(tmp_path).startswith("/tmp/"):
        pytest.skip("the fake files API serves tmp_path as the VM's /tmp; it is not under /tmp")
    boat = FakeBoat(tmp_path)
    yield boat
    assert boat.violations == [], boat.violations
    assert boat.overlaps == [], boat.overlaps


def make_backend(fake: FakeBoat, clock: FakeClock | None = None, **kwargs: Any) -> BoatBackend:
    clock = clock or FakeClock()
    kwargs.setdefault("root_base", str(fake.root_base))
    return BoatBackend(transport=fake.transport(), sleep=clock.sleep, clock=clock.now, **kwargs)


async def new_ws(
    fake: FakeBoat,
    *,
    net_policy: NetPolicy = ALLOW_ALL,
    limits: ResourceLimits | None = None,
    profile: WorkspaceProfile | None = None,
    clock: FakeClock | None = None,
    **kwargs: Any,
) -> Any:
    backend = make_backend(fake, clock, **kwargs)
    return await backend.create(
        profile or WorkspaceProfile(name="research"),
        limits=limits or ResourceLimits(),
        net_policy=net_policy,
    )


def all_exception_texts(exc: BaseException) -> str:
    seen: set[int] = set()
    texts: list[str] = []
    stack: list[BaseException | None] = [exc]
    while stack:
        item = stack.pop()
        if item is None or id(item) in seen:
            continue
        seen.add(id(item))
        texts += [str(item), repr(item)]
        stack += [item.__cause__, item.__context__]
    return "\n".join(texts)


def assert_keyless(text: str) -> None:
    assert FAKE_KEY not in text
    assert OTHER_KEY not in text


def _proc_alive(pid: int) -> bool:
    """True while ``pid`` runs; a zombie (reaped later by init) counts as gone."""
    try:
        raw = pathlib.Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return False
    return raw.rsplit(")", 1)[1].split()[0] != "Z"


async def _gone(pid: int, within_s: float = 3.0) -> bool:
    for _ in range(int(within_s / 0.05)):
        if not _proc_alive(pid):
            return True
        await asyncio.sleep(0.05)
    return not _proc_alive(pid)


async def _until(predicate: Any, within_s: float = 5.0) -> bool:
    for _ in range(int(within_s / 0.01)):
        if predicate():
            return True
        await asyncio.sleep(0.01)
    return bool(predicate())


def _workload_sudo_lines(fake: FakeBoat) -> list[str]:
    return [line for line in fake.log_lines("sudo") if "\tenv " in line]


# --- dark-module guards (no fake VM needed) -------------------------------------


class TestStaysDark:
    def test_factory_kinds_unchanged(self) -> None:
        assert factory_mod._VALID_KINDS == EXPECTED_FACTORY_KINDS

    def test_factory_rejects_boat_kind(self) -> None:
        with pytest.raises(BackendUnavailable, match=r"\['docker', 'local'\]"):
            build_execution_backend(kind="boat")

    def test_factory_rejects_boat_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTIEK_EXEC_BACKEND", "boat")
        with pytest.raises(BackendUnavailable, match="unknown ExecutionBackend kind 'boat'"):
            build_execution_backend()

    def test_package_does_not_export_or_import_the_adapter(self) -> None:
        assert not hasattr(exec_backend_pkg, "BoatBackend")
        assert "BoatBackend" not in exec_backend_pkg.__all__
        factory_src = pathlib.Path(inspect.getfile(factory_mod)).read_text(encoding="utf-8")
        init_src = pathlib.Path(inspect.getfile(exec_backend_pkg)).read_text(encoding="utf-8")
        assert "boat" not in factory_src.lower()
        assert "boat" not in init_src.lower()

    def test_activation_section_shows_the_exact_factory_diff(self) -> None:
        doc = bb.__doc__ or ""
        assert "Activation (after ratification)" in doc
        assert '+_VALID_KINDS: frozenset[str] = frozenset({"local", "docker", "boat"})' in doc
        assert "+        from .boat_backend import BoatBackend" in doc
        assert "+        backend.probe()" in doc

    def test_i2_zero_file_grep_covers_this_module(self) -> None:
        # Mirrors test_exec_backend_interface.test_no_host_writer_identifier_in_package
        # and proves the scan reaches boat_backend.py.
        pkg_dir = pathlib.Path(inspect.getfile(exec_backend_pkg)).resolve().parent
        scanned = {p.name for p in pkg_dir.rglob("*.py")}
        assert "boat_backend.py" in scanned
        forbidden = ("connect_write", "db_lock", "event_log")
        text = (pkg_dir / "boat_backend.py").read_text(encoding="utf-8")
        assert [t for t in forbidden if t in text] == []

    def test_module_only_names_the_product_key_variable(self) -> None:
        # No credential fallback between planes: the build key's variable is
        # never read. It may be named in prose, never passed to os.environ.
        src = pathlib.Path(inspect.getfile(bb)).read_text(encoding="utf-8")
        assert "environ.get(BOAT_API_KEY_ENV" in src
        assert not re.search(r"environ(?:\.get)?\(\s*['\"]BOAT_BUILD_API_KEY", src)
        assert bb.BOAT_API_KEY_ENV == "BOAT_API_KEY"


class TestProtocolAndUnits:
    def test_backend_satisfies_protocol(self) -> None:
        backend = BoatBackend(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        assert isinstance(backend, ExecutionBackend)
        assert backend.name == "boat"

    def test_exec_timeout_is_mandatory_keyword_only(self) -> None:
        params = inspect.signature(bb._BoatWorkspace.exec).parameters
        assert params["timeout_s"].kind is inspect.Parameter.KEYWORD_ONLY
        assert params["timeout_s"].default is inspect.Parameter.empty

    @pytest.mark.parametrize(
        ("cpu", "mem", "disk", "expected"),
        [
            (1.0, 2048, 2048, "small"),
            (2.0, 4096, 2048, "small"),
            (2.5, 1024, 2048, "default"),
            (1.0, 4097, 2048, "default"),
            (4.0, 8192, 2048, "default"),
            (4.1, 8192, 2048, "large"),
            (8.0, 16384, 2048, "large"),
            (1.0, 2048, 60 * 1024, "large"),
            (9.0, 1024, 2048, "xlarge"),
            (16.0, 32768, 251 * 1024, "xlarge"),
        ],
    )
    def test_smallest_covering_machine_type(
        self, cpu: float, mem: int, disk: int, expected: str
    ) -> None:
        limits = ResourceLimits(cpu_cores=cpu, memory_mb=mem, disk_mb=disk)
        assert select_machine_type(limits) == expected

    @pytest.mark.parametrize(
        ("limits", "named"),
        [
            (ResourceLimits(cpu_cores=17), "cpu_cores=17 > 16"),
            (ResourceLimits(memory_mb=32769), "memory_mb=32769 > 32768"),
            (ResourceLimits(disk_mb=252 * 1024), "disk_mb"),
        ],
    )
    def test_refusal_above_xlarge_names_the_limit(self, limits: ResourceLimits, named: str) -> None:
        with pytest.raises(WorkspaceProvisionError, match=re.escape(named)):
            select_machine_type(limits)

    @pytest.mark.parametrize(
        ("wall", "ttl"), [(900, 900), (10, 60), (2_592_000, 2_592_000), (10**9, 2_592_000)]
    )
    def test_wall_clock_maps_to_ttl(self, wall: int, ttl: int) -> None:
        assert bb._ttl_seconds(wall) == ttl

    @pytest.mark.parametrize(
        "root_base", ["/tmp", "/home/user", "/etc/antiek", "/tmp/../etc/x", "tmp/x", "/tmp/a/"]
    )
    def test_root_base_must_be_below_the_files_api_roots(self, root_base: str) -> None:
        with pytest.raises(ValueError, match="root_base"):
            BoatBackend(root_base=root_base)

    def test_wrapper_parse_and_cap(self) -> None:
        m = "ANTIEK_BOAT_x"
        stdout = f"banner\n{m}:begin\nhello"
        stderr = f"{m}:begin\nwarn\n\n{m}:end ok 3 0 5 5 1\n"
        parsed = bb._parse_wrapped(stdout, stderr, m)
        assert parsed is not None
        assert (parsed.status, parsed.rc, parsed.stdout, parsed.stderr, parsed.clean) == (
            "ok",
            3,
            "hello",
            "warn\n",
            True,
        )
        unclean = bb._parse_wrapped(stdout, stderr.replace(" 5 5 1\n", " 5 5 0\n"), m)
        assert unclean is not None and unclean.clean is False
        assert bb._parse_wrapped("x", "no trailer", m) is None
        # A trailer without the clean field is not a wrapper trailer.
        assert bb._parse_wrapped(stdout, f"{m}:begin\n\n{m}:end ok 3 0 5 5\n", m) is None
        exact = "a" * MAX_OUTPUT_BYTES
        assert bb._cap(exact, MAX_OUTPUT_BYTES) == (exact, False)
        capped, cut = bb._cap(exact + "b", MAX_OUTPUT_BYTES + 1)
        assert cut is True and len(capped) == MAX_OUTPUT_BYTES

    _GOOD_READBACK: tuple[tuple[str, str], ...] = (
        ("runner_uid", "4242"),
        ("owner_uid", "1000"),
        ("iptables", "-P OUTPUT ACCEPT"),
        ("iptables", "-A OUTPUT -m owner --uid-owner 4242 -j REJECT"),
        ("iptables", "-A OUTPUT -j ufw-before-output"),
        ("ip6tables", "-P OUTPUT ACCEPT"),
        ("ip6tables", "-A OUTPUT -m owner --uid-owner 4242 -j REJECT"),
        ("ip6tables", "-A OUTPUT -j ufw-before-output"),
        ("runner_sudo", "no"),
    )

    def test_deny_all_readback_accepts_the_verified_shape(self) -> None:
        assert bb._deny_all_problems(self._GOOD_READBACK, expected_runner_uid=4242) == []

    def test_deny_all_readback_flags_a_rule_on_user(self) -> None:
        pairs = [
            *self._GOOD_READBACK,
            ("iptables", "-A OUTPUT -m owner --uid-owner 1000 -j REJECT"),
        ]
        problems = bb._deny_all_problems(pairs, expected_runner_uid=4242)
        assert any("blocks the Boat 'user' account" in p for p in problems)

    @pytest.mark.parametrize(
        ("change", "expected_uid", "named"),
        [
            # The first REJECT names another uid (the runner's rule is not first).
            (
                {"ip6tables": "-A OUTPUT -m owner --uid-owner 9999 -j REJECT"},
                4242,
                "ip6tables: first OUTPUT rule",
            ),
            (
                {"iptables": "-A OUTPUT -m owner --uid-owner 9999 -j REJECT"},
                4242,
                "iptables: first OUTPUT rule",
            ),
            # The IPv6 family has no rules at all.
            ({"ip6tables": None}, 4242, "ip6tables: OUTPUT has no rules"),
            # The runner's uid changed since provisioning.
            ({}, 4243, "runner uid changed"),
            # The runner resolves to root or to Boat's user account.
            ({"runner_uid": "0"}, None, "root or the Boat 'user'"),
            ({"runner_uid": "1000"}, None, "root or the Boat 'user'"),
            ({"runner_sudo": "yes"}, 4242, "can use sudo"),
        ],
    )
    def test_deny_all_readback_refuses(
        self, change: dict[str, str | None], expected_uid: int | None, named: str
    ) -> None:
        # ``change`` replaces a single field, or a family's first ``-A`` rule;
        # ``None`` drops every line of that family.
        pairs: list[tuple[str, str]] = []
        replaced: set[str] = set()
        for key, value in self._GOOD_READBACK:
            new = change.get(key, value)
            if new is None:
                continue
            first_rule_or_field = value.startswith("-A ") or not value.startswith("-")
            if key in change and key not in replaced and first_rule_or_field:
                pairs.append((key, new))
                replaced.add(key)
            else:
                pairs.append((key, value))
        problems = bb._deny_all_problems(pairs, expected_runner_uid=expected_uid)
        assert any(named in p for p in problems), problems

    @pytest.mark.parametrize(
        ("flags", "ok"),
        [
            ({"safeForThirdParties": True}, True),
            ({"safeForThirdParties": True, "proxyAiCredentials": True}, False),
            ({"safeForThirdParties": False}, False),
            (
                {
                    "safeForThirdParties": False,
                    "passGithub": False,
                    "passSecrets": False,
                    "passSandboxCredentials": False,
                    "passAgentsCredentials": False,
                },
                True,
            ),
        ],
    )
    def test_environment_flag_rule(self, flags: dict[str, Any], ok: bool) -> None:
        assert (bb._environment_problems(_env_record("e", **flags)) == []) is ok


# --- the key ---------------------------------------------------------------------


class TestKey:
    def test_missing_key_refuses_before_any_request(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BOAT_API_KEY")
        with pytest.raises(BackendUnavailable, match=r"\$BOAT_API_KEY is not set"):
            make_backend(fake).probe()
        with pytest.raises(BackendUnavailable, match=r"\$BOAT_API_KEY is not set"):
            asyncio.run(new_ws(fake))
        assert fake.calls == []

    def test_build_plane_key_is_never_a_fallback(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BOAT_API_KEY")
        monkeypatch.setenv("BOAT_BUILD_API_KEY", OTHER_KEY)
        with pytest.raises(BackendUnavailable) as info:
            make_backend(fake).probe()
        assert fake.calls == []
        assert_keyless(all_exception_texts(info.value))

    def test_malformed_key_refused_without_echo(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BOAT_API_KEY", f"{FAKE_KEY} \n")
        with pytest.raises(BackendUnavailable, match="malformed") as info:
            make_backend(fake).probe()
        assert_keyless(all_exception_texts(info.value))
        assert fake.calls == []

    async def test_key_is_read_at_use_time(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ws = await new_ws(fake)
        assert {c.headers["authorization"] for c in fake.calls} == {f"Bearer {FAKE_KEY}"}
        before = len(fake.calls)
        monkeypatch.setenv("BOAT_API_KEY", OTHER_KEY)
        await ws.exec(["true"], timeout_s=10)
        assert {c.headers["authorization"] for c in fake.calls[before:]} == {f"Bearer {OTHER_KEY}"}
        monkeypatch.delenv("BOAT_API_KEY")
        sent = len(fake.calls)
        with pytest.raises(BackendUnavailable, match="not set"):
            await ws.exec(["true"], timeout_s=10)
        assert len(fake.calls) == sent
        monkeypatch.setenv("BOAT_API_KEY", FAKE_KEY)
        await ws.destroy()

    async def test_key_never_leaks(self, fake: FakeBoat, caplog: pytest.LogCaptureFixture) -> None:
        caplog.set_level(logging.DEBUG)
        ws = await new_ws(fake, net_policy=DENY_ALL)
        await ws.put_file("in/a.txt", b"payload")
        assert await ws.get_file("in/a.txt") == b"payload"
        result = await ws.exec(["sh", "-c", "env; echo done"], timeout_s=10)
        assert result.exit_code == 0
        assert_keyless(result.stdout + result.stderr)

        failures: list[BaseException] = []
        # Boat's error text echoing the bearer header must come back scrubbed.
        fake.injected.append(
            Injected("GET", r"/sandboxes/[^/]+/files", 500, "http_500", f"saw Bearer {FAKE_KEY}")
        )
        with pytest.raises(ExecutionBackendError) as http_failure:
            await ws.get_file("in/a.txt")
        failures.append(http_failure.value)
        # A transport error whose text carries the header value.
        fake.injected.append(Injected("POST", r"/sandboxes/[^/]+/commands", 0, "", "refused"))
        with pytest.raises(ExecutionBackendError) as transport_failure:
            await ws.exec(["true"], timeout_s=10)
        failures.append(transport_failure.value)
        # A refused create whose message echoes it.
        fake.injected.append(
            Injected("POST", r"/sandboxes", 403, "forbidden", f"key {FAKE_KEY} refused")
        )
        with pytest.raises(BackendUnavailable) as create_failure:
            await new_ws(fake)
        failures.append(create_failure.value)
        await ws.destroy()

        for exc in failures:
            text = all_exception_texts(exc)
            assert "[redacted]" in text or "refused" in text
            assert_keyless(text)
        assert_keyless(caplog.text)
        for call in fake.calls:
            assert_keyless(call.url)
            assert_keyless(json.dumps(call.body))
            for name, value in call.headers.items():
                if name.lower() != "authorization":
                    assert_keyless(value)
        for command in fake.commands():
            assert_keyless(command)


# --- probe ----------------------------------------------------------------------


class TestProbe:
    def test_probe_reads_limits_and_environment_with_the_pin(
        self, fake: FakeBoat, caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        make_backend(fake).probe()
        (limits,) = fake.calls_to("GET", "/limits")
        assert limits.headers["x-boat-org"] == FAKE_ORG
        (envs,) = fake.calls_to("GET", "/environments")
        assert envs.query == {"org": [FAKE_ORG]}
        assert len(fake.calls) == 2
        assert "passes nothing" in caplog.text
        assert "envcontents" not in caplog.text

    @pytest.mark.parametrize(
        ("override", "match"),
        [
            ({"teamId": OTHER_ORG}, "limits are for"),
            ({"teamId": _DROP}, "personal wallet"),
            (
                {"canStart": False, "blockedReason": "subscription_required"},
                "subscription_required",
            ),
        ],
    )
    def test_probe_refuses_wrong_wallet_or_blocked_scope(
        self, fake: FakeBoat, override: dict[str, Any], match: str
    ) -> None:
        fake.limits_override = override
        with pytest.raises(BackendUnavailable, match=match):
            make_backend(fake).probe()

    def test_probe_refuses_org_mismatch_answer(self, fake: FakeBoat) -> None:
        fake.key_org = OTHER_ORG
        with pytest.raises(BackendUnavailable, match="api_key_org_mismatch"):
            make_backend(fake).probe()

    def test_org_pin_must_be_an_id(self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTIEK_BOAT_ORG", "Antiek")
        with pytest.raises(BackendUnavailable, match="organization id"):
            make_backend(fake).probe()
        with pytest.raises(BackendUnavailable, match="organization id"):
            asyncio.run(new_ws(fake))
        assert fake.calls == []

    def test_probe_live_limits_shape_without_can_start_is_shape_drift(self, fake: FakeBoat) -> None:
        # LIVE_SHAPES.md GET /limits (2026-11-09, personal key) carries no
        # canStart, billingStatus or activeSandboxes; the OpenAPI requires them.
        fake.limits_override = {
            "canStart": _DROP,
            "billingStatus": _DROP,
            "activeSandboxes": _DROP,
        }
        with pytest.raises(BackendUnavailable, match="no boolean 'canStart'") as info:
            make_backend(fake).probe()
        text = str(info.value)
        assert "shape drifted" in text and "dashboard" not in text

    def test_probe_degrades_when_the_scope_cannot_read_limits(
        self, fake: FakeBoat, caplog: pytest.LogCaptureFixture
    ) -> None:
        fake.injected.append(
            Injected("GET", "/limits", 403, "api_key_action_forbidden", "no account.read")
        )
        with caplog.at_level(logging.WARNING):
            make_backend(fake).probe()
        assert "may not read GET /limits" in caplog.text
        assert len(fake.calls_to("GET", "/environments")) == 1

    @pytest.mark.parametrize("code", ["api_key_action_forbidden", "api_key_sandbox_forbidden"])
    def test_probe_fails_closed_when_the_scope_cannot_read_environments(
        self, fake: FakeBoat, code: str
    ) -> None:
        fake.injected.append(Injected("GET", "/environments", 403, code, "no env read"))
        with pytest.raises(BackendUnavailable, match="environment.read"):
            make_backend(fake).probe()

    @pytest.mark.parametrize(
        "flags",
        [
            {"safeForThirdParties": False, "passSecrets": True},
            {"safeForThirdParties": True, "proxyAiCredentials": True},
        ],
    )
    def test_probe_refuses_an_environment_that_passes_credentials(
        self, fake: FakeBoat, flags: dict[str, Any], caplog: pytest.LogCaptureFixture
    ) -> None:
        caplog.set_level(logging.DEBUG)
        fake.environments = [_env_record("antiek-product", **flags)]
        with pytest.raises(BackendUnavailable, match="safe for third parties") as info:
            make_backend(fake).probe()
        assert "envcontents" not in all_exception_texts(info.value) + caplog.text

    def test_probe_refuses_an_unlisted_environment(self, fake: FakeBoat) -> None:
        fake.environments = [_env_record("base")]
        with pytest.raises(BackendUnavailable, match="not in this key's GET /environments"):
            make_backend(fake).probe()

    def test_build_plane_environment_refused(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTIEK_BOAT_ENVIRONMENT", "antiek-build")
        with pytest.raises(BackendUnavailable, match="BUILD plane"):
            make_backend(fake).probe()
        with pytest.raises(BackendUnavailable, match="BUILD plane"):
            asyncio.run(new_ws(fake))
        assert fake.calls == []

    def test_probe_without_pin_sends_no_org(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTIEK_BOAT_ORG")
        make_backend(fake).probe()
        assert "x-boat-org" not in fake.calls_to("GET", "/limits")[0].headers
        assert fake.calls_to("GET", "/environments")[0].query == {}


# --- create ----------------------------------------------------------------------


class TestCreate:
    async def test_request_shape(self, fake: FakeBoat) -> None:
        ws = await new_ws(
            fake, profile=WorkspaceProfile(name="Deep Research #1"), limits=ResourceLimits()
        )
        (create,) = fake.calls_to("POST", "/sandboxes")
        body = create.body
        assert set(body) <= CREATE_SANDBOX_FIELDS
        assert body == {
            "type": "small",
            "ttlSeconds": 900,
            "environment": "antiek-product",
            "name": f"antiek-ws-deep-research-1-{ws.workspace_id[:8]}",
            "labels": {"antiek-workspace": ws.workspace_id, "antiek-profile": "deep-research-1"},
            "snapshots": False,
            "visibility": "private",
        }
        assert "noEnv" not in body
        assert create.headers["idempotency-key"] == f"antiek-ws-{ws.workspace_id}"
        assert create.headers["x-boat-org"] == FAKE_ORG
        assert SANDBOX_ID_RE.match(ws.sandbox_id)
        # The environment's flags are read (fail closed) before anything bills.
        first, second = fake.calls[:2]
        assert (first.method, first.route, first.query) == (
            "GET",
            "/environments",
            {"org": [FAKE_ORG]},
        )
        assert (second.method, second.route) == ("POST", "/sandboxes")
        await ws.destroy()

    async def test_environment_override(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTIEK_BOAT_ENVIRONMENT", "antiek-product-eu")
        ws = await new_ws(fake)
        assert fake.calls_to("POST", "/sandboxes")[0].body["environment"] == "antiek-product-eu"
        await ws.destroy()

    async def test_missing_environment_refused_before_any_create(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("ANTIEK_BOAT_ENVIRONMENT", "antiek-missing")
        with pytest.raises(BackendUnavailable, match="not in this key's GET /environments"):
            await new_ws(fake)
        assert fake.calls_to("POST", "/sandboxes") == []

    async def test_unknown_environment_answer_is_a_config_error(self, fake: FakeBoat) -> None:
        fake.injected.append(
            Injected("POST", "/sandboxes", 400, "unknown_environment", "Unknown environment.")
        )
        with pytest.raises(BackendUnavailable, match="unknown_environment"):
            await new_ws(fake)

    def test_environment_flags_are_re_read_on_every_create(self, fake: FakeBoat) -> None:
        make_backend(fake).probe()
        # The owner turns the product environment unsafe after the probe.
        fake.environments = [_env_record("antiek-product", passSecrets=True)]
        with pytest.raises(BackendUnavailable, match="would pass account credentials"):
            asyncio.run(new_ws(fake))
        assert fake.calls_to("POST", "/sandboxes") == []

    @pytest.mark.parametrize("code", ["api_key_action_forbidden", "api_key_sandbox_forbidden"])
    async def test_unreadable_environment_flags_refuse_the_create(
        self, fake: FakeBoat, code: str
    ) -> None:
        fake.injected.append(Injected("GET", "/environments", 403, code, "no env read"))
        with pytest.raises(BackendUnavailable, match="environment.read"):
            await new_ws(fake)
        assert fake.calls_to("POST", "/sandboxes") == []

    async def test_environment_read_outage_is_transient(self, fake: FakeBoat) -> None:
        fake.injected.append(Injected("GET", "/environments", 503, "unavailable", "down"))
        with pytest.raises(WorkspaceProvisionError, match="environments read before create"):
            await new_ws(fake)
        assert fake.calls_to("POST", "/sandboxes") == []

    @pytest.mark.parametrize(
        ("limits", "machine"),
        [
            (ResourceLimits(cpu_cores=4, memory_mb=8192), "default"),
            (ResourceLimits(cpu_cores=6, memory_mb=1024), "large"),
            (ResourceLimits(cpu_cores=12, memory_mb=20000), "xlarge"),
        ],
    )
    async def test_limits_select_the_machine_type(
        self, fake: FakeBoat, limits: ResourceLimits, machine: str
    ) -> None:
        ws = await new_ws(fake, limits=limits)
        assert fake.calls_to("POST", "/sandboxes")[0].body["type"] == machine
        await ws.destroy()

    async def test_oversize_and_allowlist_refused_before_any_request(self, fake: FakeBoat) -> None:
        with pytest.raises(WorkspaceProvisionError, match="exceed the largest"):
            await new_ws(fake, limits=ResourceLimits(cpu_cores=32))
        with pytest.raises(NetPolicyUnsupported, match="allowlist"):
            await new_ws(fake, net_policy=NetPolicy(NetPolicyKind.ALLOWLIST, ("10.0.0.0/8",)))
        assert fake.calls == []

    async def test_bounded_readiness_wait(self, fake: FakeBoat) -> None:
        fake.ready_after = 3
        clock = FakeClock()
        ws = await new_ws(fake, clock=clock)
        assert len(fake.calls_to("GET", r"/sandboxes/[^/]+")) == 3
        assert clock.sleeps == [2.0, 2.0]
        await ws.destroy()

    async def test_readiness_timeout_deletes_the_sandbox(self, fake: FakeBoat) -> None:
        fake.ready_after = 10**9
        with pytest.raises(WorkspaceProvisionError, match="not ready within 10s"):
            await new_ws(fake, ready_timeout_s=10)
        (delete,) = fake.calls_to("DELETE", r"/sandboxes/[^/]+")
        assert delete.headers["x-ascii-confirm-delete"] == delete.route.rsplit("/", 1)[1]
        assert fake.commands() == []
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("failed", ["error", "cancelled", "archived"])
    async def test_failed_state_deletes_the_sandbox(self, fake: FakeBoat, failed: str) -> None:
        fake.state_script = ["provisioning", failed]
        with pytest.raises(WorkspaceProvisionError, match=f"entered state '{failed}'"):
            await new_ws(fake)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize(
        ("status", "code", "expected"),
        [
            (402, "billing_required", BackendUnavailable),
            (403, "environment_forbidden", BackendUnavailable),
            (403, "api_key_org_mismatch", BackendUnavailable),
            (403, "machine_class_plan_required", WorkspaceProvisionError),
            (429, "limit_reached", WorkspaceProvisionError),
            (429, "trial_compute_limit_reached", BackendUnavailable),
            (503, "no_ready_machine", WorkspaceProvisionError),
            (409, "idempotency_in_progress", WorkspaceProvisionError),
        ],
    )
    async def test_create_error_mapping(
        self, fake: FakeBoat, status: int, code: str, expected: type[Exception]
    ) -> None:
        fake.injected.append(Injected("POST", "/sandboxes", status, code, "refused"))
        with pytest.raises(expected, match=code) as info:
            await new_ws(fake)
        assert "req_fake0001" in str(info.value)

    async def test_lost_create_answer_sweeps_only_its_own_labelled_sandbox(
        self, fake: FakeBoat
    ) -> None:
        fake.injected.append(
            Injected("POST", "/sandboxes", 502, "http_502", "gateway", after_effect=True)
        )
        # An org-wide listing that ignores the label filter: the research
        # boxes of a teammate, and a sandbox of another workspace.
        fake.list_extra = [
            {"id": "bx_235rmpn3", "labels": {"antiek-workspace": "__QUERIED__"}, "access": "view"},
            {"id": "bx_35hs5p53", "labels": {"antiek-workspace": "__QUERIED__"}, "access": "use"},
            {
                "id": "bx_zzzzzzzz",
                "labels": {"antiek-workspace": "someone-else"},
                "access": "owner",
            },
        ]
        with pytest.raises(WorkspaceProvisionError, match="http_502"):
            await new_ws(fake)
        (orphan,) = fake.sandboxes
        # Recovery the documented way: the same POST, same key, same body.
        first, again = fake.calls_to("POST", "/sandboxes")
        assert again.headers["idempotency-key"] == first.headers["idempotency-key"]
        assert again.headers["x-boat-org"] == FAKE_ORG
        assert again.body == first.body
        # Then the label sweep, in the pinned org's scope.
        (listing,) = fake.calls_to("GET", "/sandboxes")
        assert listing.query["label"] == [
            f"antiek-workspace={fake.sandboxes[orphan]['labels']['antiek-workspace']}"
        ]
        assert listing.headers["x-boat-org"] == FAKE_ORG
        deletes = fake.calls_to("DELETE", r"/sandboxes/[^/]+")
        assert [d.route for d in deletes] == [f"/sandboxes/{orphan}"]
        assert fake.deleted == {orphan}

    async def test_lost_answer_still_being_minted_is_asked_again(self, fake: FakeBoat) -> None:
        fake.injected.append(
            Injected("POST", "/sandboxes", 504, "gateway_timeout", "lost", after_effect=True)
        )
        fake.idem_in_progress = 1
        clock = FakeClock()
        with pytest.raises(WorkspaceProvisionError, match="gateway_timeout"):
            await new_ws(fake, clock=clock)
        assert len(fake.calls_to("POST", "/sandboxes")) == 3
        assert clock.sleeps == [2.0]
        (orphan,) = fake.sandboxes
        assert fake.deleted == {orphan}

    async def test_connection_never_made_skips_the_re_post(self, fake: FakeBoat) -> None:
        fake.injected.append(Injected("POST", "/sandboxes", 0, "", "connection refused"))
        with pytest.raises(WorkspaceProvisionError, match="ConnectError"):
            await new_ws(fake)
        assert len(fake.calls_to("POST", "/sandboxes")) == 1
        assert len(fake.calls_to("GET", "/sandboxes")) == 1
        assert fake.sandboxes == {}

    async def test_answer_lost_after_sending_is_recovered_by_key(self, fake: FakeBoat) -> None:
        fake.injected.append(
            Injected("POST", "/sandboxes", 0, "", "reset", after_effect=True, exc=httpx.ReadError)
        )
        with pytest.raises(WorkspaceProvisionError, match="ReadError"):
            await new_ws(fake)
        assert len(fake.calls_to("POST", "/sandboxes")) == 2
        (orphan,) = fake.sandboxes
        assert fake.deleted == {orphan}

    async def test_unusable_id_answer_sweeps_by_label(self, fake: FakeBoat) -> None:
        fake.create_id_override = "not-a-sandbox-id"
        with pytest.raises(WorkspaceProvisionError, match="usable sandbox id"):
            await new_ws(fake)
        (orphan,) = fake.sandboxes
        assert len(fake.calls_to("GET", "/sandboxes")) == 1
        assert fake.deleted == {orphan}

    async def test_cancelled_create_deletes_what_boat_accepted(self, fake: FakeBoat) -> None:
        # Boat accepts the POST and mints the sandbox; the answer never comes
        # and the caller gives up (asyncio.timeout / wait_for / TaskGroup).
        fake.injected.append(
            Injected("POST", "/sandboxes", 0, "", "never", after_effect=True, hang=True)
        )
        task = asyncio.create_task(new_ws(fake))
        assert await _until(lambda: bool(fake.sandboxes))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        first, again = fake.calls_to("POST", "/sandboxes")
        assert again.headers["idempotency-key"] == first.headers["idempotency-key"]
        assert again.body == first.body
        (orphan,) = fake.sandboxes
        assert fake.deleted == {orphan}

    async def test_second_cancel_does_not_stop_the_cleanup(self, fake: FakeBoat) -> None:
        fake.injected.append(
            Injected("POST", "/sandboxes", 0, "", "never", after_effect=True, hang=True)
        )
        task = asyncio.create_task(new_ws(fake))
        assert await _until(lambda: bool(fake.sandboxes))
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert await _until(lambda: bool(fake.sandboxes) and set(fake.sandboxes) == fake.deleted)
        assert await _until(lambda: not bb._BACKGROUND_CLEANUPS)

    async def test_cancel_during_readiness_deletes_the_sandbox(self, fake: FakeBoat) -> None:
        fake.ready_after = 10**9
        task = asyncio.create_task(new_ws(fake))
        assert await _until(lambda: bool(fake.polls))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        (sid,) = fake.sandboxes
        assert fake.deleted == {sid}

    async def test_second_cancel_during_teardown_does_not_stop_the_delete(
        self, fake: FakeBoat
    ) -> None:
        fake.ready_after = 10**9
        fake.delete_delay_s = 0.2
        task = asyncio.create_task(new_ws(fake))
        assert await _until(lambda: bool(fake.polls))
        task.cancel()
        assert await _until(lambda: bool(fake.calls_to("DELETE", r"/sandboxes/[^/]+")))
        task.cancel()  # lands while the DELETE is in flight
        with pytest.raises(asyncio.CancelledError):
            await task
        (sid,) = fake.sandboxes
        assert await _until(lambda: fake.deleted == {sid})

    async def test_provision_failure_exit_code_deletes_the_sandbox(self, fake: FakeBoat) -> None:
        # Every field printed, but the provisioning command did not exit 0.
        fake.exit_overrides["useradd"] = 1
        with pytest.raises(WorkspaceProvisionError, match="provisioning sandbox .* failed"):
            await new_ws(fake)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("uid", ["0", str(os.getuid())])
    async def test_runner_that_is_root_or_user_refused(self, fake: FakeBoat, uid: str) -> None:
        (fake.state / "runner_uid").write_text(f"{uid}\n")
        with pytest.raises(WorkspaceProvisionError, match="root or the Boat 'user'"):
            await new_ws(fake)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("value", ["0", ""])
    async def test_unprotected_hardlinks_refused(self, fake: FakeBoat, value: str) -> None:
        (fake.state / "protected_hardlinks").write_text(f"{value}\n" if value else "")
        with pytest.raises(BackendUnavailable, match="does not protect hardlinks"):
            await new_ws(fake)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize(
        ("setup", "match"),
        [
            ({"team_for_new": OTHER_ORG}, "not the ANTIEK_BOAT_ORG pin"),
            ({"omit_team": True}, "cannot be verified"),
            ({"record_extras": {"environment": "base"}}, "attached to environment 'base'"),
            ({"record_extras": {"environment": None}}, "attached to environment None"),
            ({"record_extras": {"holdsCreatorLogins": True}}, "holdsCreatorLogins"),
        ],
    )
    async def test_sandbox_record_read_back(
        self, fake: FakeBoat, setup: dict[str, Any], match: str
    ) -> None:
        for name, value in setup.items():
            setattr(fake, name, value)
        with pytest.raises(BackendUnavailable, match=match):
            await new_ws(fake)
        assert len(fake.sandboxes) == 1
        assert set(fake.sandboxes) == fake.deleted
        assert fake.commands() == []

    async def test_unpinned_create_needs_no_team(
        self, fake: FakeBoat, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("ANTIEK_BOAT_ORG")
        fake.omit_team = True
        ws = await new_ws(fake)
        assert "x-boat-org" not in fake.calls_to("POST", "/sandboxes")[0].headers
        await ws.destroy()

    @pytest.mark.parametrize(
        "content",
        [
            KEYLESS_CLI_CONFIG,
            '{"api_url":"https://boat.dev","channel":"production"}',
            '{"channel": "production"}',
            '{"api_url": "https://boat.dev", "channel": "ascii-prod"}',
            # 23 characters after boat_: one short of the key-shaped threshold.
            '{"api_url": "https://boat.dev", "channel": "boat_ABCDEFGHIJKLMNOPQRSTUVW"}',
            "{}",
        ],
    )
    async def test_keyless_cli_config_is_accepted(self, fake: FakeBoat, content: str) -> None:
        (fake.home / ".config/ascii/boat/config.json").write_text(content)
        ws = await new_ws(fake)
        assert fake.deleted == set()
        await ws.destroy()

    @pytest.mark.parametrize(
        "content",
        [
            '{"api_url": "https://boat.dev", "channel": "production", "api_key": "SECRETVALUE-do-not-echo"}',
            '{"api_key": "SECRETVALUE-do-not-echo", "api_url": "https://boat.dev"}',
            # exactly 24 characters after boat_: the key-shaped threshold.
            '{"api_url": "https://boat.dev", "channel": "boat_SECRETVALUEdonotecho0123"}',
            '{"api_url": "https://boat.dev", "channel": {"key": "SECRETVALUE-do-not-echo"}}',
            '{"api_url": "https://boat.dev\\"", "channel": "SECRETVALUE-do-not-echo"}',
            # contain an allowed-shape substring: only the whole-line anchor refuses them.
            '{"api_key": "SECRETVALUE-do-not-echo", "x": {}}',
            'SECRETVALUE{"channel": "p"}',
            "SECRETVALUE-do-not-echo",
            "",
        ],
        ids=[
            "extra-field-last",
            "extra-field-first",
            "key-shaped-value-at-threshold",
            "nested",
            "escaped-quote",
            "embedded-empty-object",
            "leading-garbage",
            "not-json",
            "empty",
        ],
    )
    async def test_cli_config_holding_more_than_the_keyless_shape_refused(
        self, fake: FakeBoat, content: str
    ) -> None:
        (fake.home / ".config/ascii/boat/config.json").write_text(content)
        with pytest.raises(BackendUnavailable, match="holds more than api_url and channel") as info:
            await new_ws(fake)
        assert "~/.config/ascii/boat/config.json" in str(info.value)
        assert "SECRETVALUE" not in all_exception_texts(info.value)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("target_exists", [False, True], ids=["dangling", "to-keyless-file"])
    async def test_cli_config_symlink_refused(self, fake: FakeBoat, target_exists: bool) -> None:
        config = fake.home / ".config/ascii/boat/config.json"
        config.unlink()
        target = fake.tmp_path / "elsewhere.json"
        if target_exists:
            target.write_text(KEYLESS_CLI_CONFIG)
        config.symlink_to(target)
        with pytest.raises(BackendUnavailable, match=re.escape("config.json (a symlink)")):
            await new_ws(fake)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("kind", ["directory", "fifo", "unreadable"])
    async def test_cli_config_not_a_readable_regular_file_refused(
        self, fake: FakeBoat, kind: str
    ) -> None:
        config = fake.home / ".config/ascii/boat/config.json"
        if kind == "unreadable":
            if os.geteuid() == 0:
                pytest.skip("root reads a mode-000 file")
            config.write_text('{"api_key": "SECRETVALUE-do-not-echo"}')
            config.chmod(0)
        else:
            config.unlink()
            if kind == "directory":
                config.mkdir()
            else:
                os.mkfifo(config)
        try:
            with pytest.raises(BackendUnavailable, match="not a readable regular file") as info:
                await new_ws(fake)
        finally:
            if kind == "unreadable":
                config.chmod(0o600)
        assert "SECRETVALUE" not in all_exception_texts(info.value)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize(
        ("plant", "named"),
        [
            ("file:.claude/.credentials.json", "~/.claude/.credentials.json"),
            ("file:.git-credentials", "~/.git-credentials"),
            ("var:ANTHROPIC_API_KEY", "$ANTHROPIC_API_KEY"),
            ("var:GITHUB_TOKEN", "$GITHUB_TOKEN"),
        ],
    )
    async def test_account_credentials_in_the_vm_refused(
        self, fake: FakeBoat, plant: str, named: str
    ) -> None:
        kind, _, name = plant.partition(":")
        if kind == "file":
            target = fake.home / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("SECRETVALUE-do-not-echo")
        else:
            fake.extra_env[name] = "SECRETVALUE-do-not-echo"
        with pytest.raises(BackendUnavailable, match=re.escape(named)) as info:
            await new_ws(fake)
        assert "SECRETVALUE" not in all_exception_texts(info.value)
        assert set(fake.sandboxes) == fake.deleted

    async def test_provision_builds_the_workspace(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        root = pathlib.Path(ws.root)
        assert root.parent == fake.root_base
        for sub in ("in", "out", "work"):
            assert (root / sub).is_dir()
        ctl = pathlib.Path(f"{ws.root}.ctl")
        assert stat.S_IMODE(ctl.stat().st_mode) == 0o700
        assert ws._runner_uid == RUNNER_UID
        assert fake.log_lines("useradd") == [
            "--system --user-group --no-create-home --shell /usr/sbin/nologin antiek-runner"
        ]
        await ws.destroy()

    async def test_workspace_satisfies_protocol(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        assert isinstance(ws, Workspace)
        assert isinstance(ws.workspace_id, str) and ws.workspace_id
        await ws.destroy()


# --- DENY_ALL ---------------------------------------------------------------------


class TestDenyAll:
    async def test_applied_and_verified_by_read_back(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake, net_policy=DENY_ALL)
        reject = f"-A OUTPUT -m owner --uid-owner {RUNNER_UID} -j REJECT"
        for family in ("iptables", "ip6tables"):
            rules = (fake.state / f"{family}.rules").read_text().splitlines()
            assert rules[0] == reject
        commands = fake.commands()
        assert any("-I OUTPUT 1 -m owner --uid-owner" in c for c in commands)
        assert any("-w -S OUTPUT" in c and "runner_sudo" in c for c in commands)
        assert not any("--uid-owner user" in c for c in commands)
        result = await ws.exec(["echo", "contained"], timeout_s=10)
        assert result.stdout == "contained\n"
        await ws.destroy()

    @pytest.mark.parametrize(
        ("flag", "match"),
        [
            ("ip6tables.fail", "could not be applied"),
            ("iptables.append", "iptables: first OUTPUT rule"),
            ("ip6tables.append", "ip6tables: first OUTPUT rule"),
            ("runner_can_sudo", "can use sudo"),
        ],
    )
    async def test_unverifiable_rules_refused_and_sandbox_deleted(
        self, fake: FakeBoat, flag: str, match: str
    ) -> None:
        (fake.state / flag).touch()
        with pytest.raises(NetPolicyUnsupported, match=match):
            await new_ws(fake, net_policy=DENY_ALL)
        assert set(fake.sandboxes) == fake.deleted

    @pytest.mark.parametrize("family", ["iptables", "ip6tables"])
    async def test_drift_refuses_exec(self, fake: FakeBoat, family: str) -> None:
        ws = await new_ws(fake, net_policy=DENY_ALL)
        rules = fake.state / f"{family}.rules"
        rules.write_text("-A OUTPUT -j ACCEPT\n" + rules.read_text())
        before = len(_workload_sudo_lines(fake))
        with pytest.raises(NetPolicyUnsupported, match="fw_drift"):
            await ws.exec(["echo", "escaped"], timeout_s=10)
        assert len(_workload_sudo_lines(fake)) == before, "the workload ran despite the drift"
        await ws.destroy()

    async def test_workload_runs_as_the_runner_under_deny_all(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake, net_policy=DENY_ALL)
        await ws.exec(["true"], timeout_s=10)
        assert _workload_sudo_lines(fake) == ["antiek-runner\tenv -i -C"]
        await ws.destroy()

    async def test_allow_all_applies_no_rules(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        assert not any("-I OUTPUT 1" in c for c in fake.commands())
        assert (fake.state / "iptables.rules").read_text() == _SEED_RULES
        await ws.destroy()


# --- exec -------------------------------------------------------------------------

TRICKY_ARGV = [
    "a b",
    "it's",
    'dq"x',
    "$HOME",
    "`echo injected`",
    "$(echo injected)",
    "semi;colon",
    "new\nline",
    "*",
    "",
    "-n",
    "back\\slash",
    "tab\there",
    "ünïcode",
]


class TestExec:
    async def test_argv_arrives_verbatim(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        result = await ws.exec(["printf", "%s\x1f", *TRICKY_ARGV], timeout_s=10)
        assert result.exit_code == 0, result.stderr
        assert result.stdout.split("\x1f")[:-1] == TRICKY_ARGV
        await ws.destroy()

    async def test_environment_is_scrubbed(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake, profile=WorkspaceProfile(name="p", env=(("PROFILE_VAR", "p 1"),)))
        result = await ws.exec(["env"], timeout_s=10, env={"EXEC_VAR": "e'2"})
        seen = dict(line.split("=", 1) for line in result.stdout.splitlines())
        assert set(seen) == {"PATH", "LANG", "HOME", "PROFILE_VAR", "EXEC_VAR"}
        assert seen["HOME"] == os.path.realpath(ws.root)
        assert (seen["PROFILE_VAR"], seen["EXEC_VAR"]) == ("p 1", "e'2")
        await ws.destroy()

    async def test_cwd_default_jail_and_missing(
        self, fake: FakeBoat, tmp_path: pathlib.Path
    ) -> None:
        ws = await new_ws(fake)
        root = os.path.realpath(ws.root)
        assert (await ws.exec(["pwd"], timeout_s=10)).stdout == f"{root}/work\n"
        assert (await ws.exec(["pwd"], timeout_s=10, cwd="in")).stdout == f"{root}/in\n"
        sent = len(fake.calls)
        for bad in ("../x", "/etc", "in/../../x", ""):
            with pytest.raises(ValueError, match="escapes|control"):
                await ws.exec(["pwd"], timeout_s=10, cwd=bad)
        assert len(fake.calls) == sent
        outside = tmp_path / "outside"
        outside.mkdir()
        os.symlink(outside, pathlib.Path(ws.root) / "work" / "esc")
        with pytest.raises(ValueError, match="escapes"):
            await ws.exec(["pwd"], timeout_s=10, cwd="work/esc")
        missing = await ws.exec(["pwd"], timeout_s=10, cwd="nope")
        assert missing.exit_code == 127 and "not found" in missing.stderr
        await ws.destroy()

    async def test_stdin_travels_through_the_files_api(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        text = "line one\nline two é\n"
        result = await ws.exec(["cat"], timeout_s=10, stdin=text.encode())
        assert result.stdout == text
        (put,) = fake.calls_to("PUT", r"/sandboxes/[^/]+/files")
        assert put.body["path"].startswith(f"{ws.root}.ctl/")
        assert put.body["encoding"] == "base64"
        assert list(pathlib.Path(f"{ws.root}.ctl").iterdir()) == []
        await ws.destroy()

    async def test_exit_codes_and_missing_binary(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        assert (await ws.exec(["sh", "-c", "exit 3"], timeout_s=10)).exit_code == 3
        missing = await ws.exec(["definitely-not-a-binary-zz9"], timeout_s=10)
        assert missing.exit_code == 127 and not missing.timed_out
        await ws.destroy()

    async def test_timeout_kills_the_whole_group_in_the_box(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        script = "sleep 30 & echo $! > bg.pid; sleep 30"
        result = await ws.exec(["sh", "-c", script], timeout_s=0.5)
        assert result.timed_out is True
        assert result.exit_code == -1
        bg_pid = int((pathlib.Path(ws.root) / "work" / "bg.pid").read_text())
        assert await _gone(bg_pid), "the background child survived the timeout"
        assert {"-KILL -U antiek-runner", "-KILL -u antiek-runner"} <= set(fake.log_lines("pkill"))
        (sync,) = [
            c
            for c in fake.calls_to("POST", r"/sandboxes/[^/]+/commands")
            if "setsid --wait" in c.body["command"]
        ]
        assert sync.body["timeoutSeconds"] == 21
        await ws.destroy()

    @pytest.mark.parametrize("code", [124, 137])
    async def test_own_exit_124_or_137_is_not_a_timeout(self, fake: FakeBoat, code: int) -> None:
        ws = await new_ws(fake)
        result = await ws.exec(["sh", "-c", f"exit {code}"], timeout_s=10)
        assert (result.exit_code, result.timed_out) == (code, False)
        await ws.destroy()

    async def test_term_ignoring_workload_is_killed_in_the_box(self, fake: FakeBoat) -> None:
        # timeout -k 5: TERM at T, KILL 5 s later, by the in-box timeout, not
        # by Boat's API timeout (which would trigger the cleanup command).
        ws = await new_ws(fake)
        before = len(fake.commands())
        result = await ws.exec(["sh", "-c", "trap '' TERM; sleep 30"], timeout_s=0.3)
        assert result.timed_out is True and result.exit_code == -1
        assert len(fake.commands()) == before + 1, "an API-level cleanup had to run"
        await ws.destroy()

    async def test_nothing_the_workload_starts_outlives_its_exec(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        result = await ws.exec(
            ["sh", "-c", "sleep 30 </dev/null >/dev/null 2>&1 & echo $!"], timeout_s=10
        )
        assert result.exit_code == 0 and not result.timed_out
        assert await _gone(int(result.stdout)), "a background process outlived its exec (I7)"
        await ws.destroy()

    async def test_a_stray_runner_process_dies_before_the_workload_starts(
        self, fake: FakeBoat
    ) -> None:
        ws = await new_ws(fake)
        # A runner process left by an earlier, interrupted exec (orphaned, so
        # init reaps it once killed).
        spawn = subprocess.run(
            ["sh", "-c", "sleep 30 </dev/null >/dev/null 2>&1 & echo $!"],
            env={"HOME": os.path.realpath(ws.root), "PATH": os.environ.get("PATH", "/bin")},
            capture_output=True,
            text=True,
            check=True,
        )
        stray = int(spawn.stdout)
        try:
            probe = (
                f"sleep 0.3; if kill -0 {stray} 2>/dev/null; then echo alive; else echo dead; fi"
            )
            result = await ws.exec(["sh", "-c", probe], timeout_s=10)
            assert result.stdout == "dead\n", "a stray runner process ran alongside the workload"
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.kill(stray, signal.SIGKILL)
        await ws.destroy()

    async def test_unconfirmed_restore_marks_the_workspace_unclean(
        self, fake: FakeBoat, caplog: pytest.LogCaptureFixture
    ) -> None:
        ws = await new_ws(fake)
        await ws.put_file("out/a.txt", b"artifact")
        (fake.state / "root_chmod.fail").touch()
        with caplog.at_level(logging.WARNING):
            result = await ws.exec(["echo", "x"], timeout_s=5)
        assert (result.exit_code, result.stdout) == (0, "x\n")
        assert ws._dirty is True and "re-runs the cleanup" in caplog.text
        (fake.state / "root_chmod.fail").unlink()
        sent = len(fake.commands())
        assert await ws.get_file("out/a.txt") == b"artifact"
        assert 'pkill -KILL -U "$RUN"' in fake.commands()[sent]
        assert ws._dirty is False
        await ws.destroy()

    async def test_workload_runs_as_the_runner_with_a_scrubbed_env(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        await ws.exec(["true"], timeout_s=10)
        await ws.exec(["true"], timeout_s=10, cwd="in")
        assert _workload_sudo_lines(fake) == ["antiek-runner\tenv -i -C"] * 2
        await ws.destroy()

    async def test_tree_handed_over_then_restored_without_group_write(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        root = pathlib.Path(ws.root)
        result = await ws.exec(
            ["sh", "-c", "chmod 0777 ../out && touch ../out/f && chmod 6777 ../out/f"],
            timeout_s=10,
        )
        assert result.exit_code == 0, result.stderr
        # Group/other write and set-id bits are gone: nothing in the tree is
        # writable by the runner between calls.
        assert stat.S_IMODE((root / "out").stat().st_mode) == 0o755
        assert stat.S_IMODE((root / "out" / "f").stat().st_mode) == 0o755
        owner = f"{os.getuid()}:{os.getgid()}"
        assert fake.log_lines("chown") == [
            f"-hR antiek-runner:antiek-runner -- {ws.root}",
            f"-hR {owner} -- {ws.root}",
        ]
        await ws.destroy()

    async def test_concurrent_calls_are_serialized(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        await ws.put_file("out/r.txt", b"ready")
        slow = ["sh", "-c", "sleep 0.3; echo slow"]
        results = await asyncio.gather(
            ws.exec(slow, timeout_s=10),
            ws.exec(["echo", "fast"], timeout_s=10),
            ws.get_file("out/r.txt"),
            ws.exec(slow, timeout_s=10),
        )
        first, second, data, third = results
        assert (first.stdout, second.stdout, data, third.stdout) == (
            "slow\n",
            "fast\n",
            b"ready",
            "slow\n",
        )
        assert not any(r.timed_out for r in (first, second, third))
        # The fixture also fails the test on any recorded overlap.
        assert fake.overlaps == []
        await ws.destroy()

    async def test_runner_process_cannot_steer_a_later_file_transfer(self, fake: FakeBoat) -> None:
        # The adversarial-review scenario: an exec exits 0 but leaves a loop
        # that swaps out/r.txt between a decoy and a symlink to a file of
        # Boat's 'user'. Every later get_file must refuse or return the decoy.
        secret = fake.home / ".bashrc"
        secret.write_text("export ASCII_TOKEN=user-only-secret\n")
        ws = await new_ws(fake)
        loop = (
            "chmod 0777 ../out; echo decoy > ../out/real; "
            f"(while :; do ln -sfn {secret} ../out/l && mv -fT ../out/l ../out/r.txt; "
            "cp ../out/real ../out/c && mv -fT ../out/c ../out/r.txt; done) "
            "</dev/null >/dev/null 2>&1 & echo $!"
        )
        result = await ws.exec(["sh", "-c", loop], timeout_s=10)
        pid = int(result.stdout)
        try:
            assert result.exit_code == 0 and not result.timed_out
            assert await _gone(pid), "the swapping loop outlived its exec"
            for _ in range(10):
                try:
                    data = await ws.get_file("out/r.txt")
                except ValueError, FileNotFoundError:
                    continue
                assert b"user-only-secret" not in data
        finally:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        await ws.destroy()

    async def test_api_timeout_wins_over_a_complete_trailer(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        fake.force_timed_out = 1
        result = await ws.exec(["echo", "hi"], timeout_s=5)
        assert (result.timed_out, result.exit_code, result.stdout) == (True, -1, "hi\n")
        await ws.destroy()

    async def test_output_beyond_boats_stream_cap_keeps_the_head(self, fake: FakeBoat) -> None:
        # ~9.3 MB of stdout, over Boat's 8 MiB per-stream cap (which keeps the
        # tail here): the wrapper's head -c must keep the answer under it.
        ws = await new_ws(fake)
        result = await ws.exec(["seq", "1", "1300000"], timeout_s=30)
        assert result.truncated is True
        assert len(result.stdout.encode()) == MAX_OUTPUT_BYTES
        assert result.stdout.startswith("1\n2\n3\n")
        await ws.destroy()

    async def test_unclean_exec_is_cleaned_before_the_next_file_transfer(
        self, fake: FakeBoat
    ) -> None:
        ws = await new_ws(fake)
        await ws.put_file("out/a.txt", b"artifact")
        # Boat's API times out the exec, and the cleanup command after it fails.
        fake.sync_timeouts = 1
        fake.injected.append(
            Injected("POST", r"/sandboxes/[^/]+/commands", 500, "http_500", "boom", skip=1)
        )
        result = await ws.exec(["echo", "x"], timeout_s=5)
        assert result.timed_out is True
        sent = len(fake.commands())
        assert await ws.get_file("out/a.txt") == b"artifact"
        cleanup, resolve = fake.commands()[sent : sent + 2]
        assert 'pkill -KILL -U "$RUN"' in cleanup and "realpath -m" in resolve
        # Clean again: the next transfer goes straight to the resolve.
        sent = len(fake.commands())
        await ws.get_file("out/a.txt")
        assert "realpath -m" in fake.commands()[sent]
        await ws.destroy()

    async def test_transfer_refused_while_the_tree_cannot_be_taken_back(
        self, fake: FakeBoat
    ) -> None:
        ws = await new_ws(fake)
        await ws.put_file("out/a.txt", b"artifact")
        fake.sync_timeouts = 1
        fake.injected.append(
            Injected("POST", r"/sandboxes/[^/]+/commands", 500, "http_500", "boom", skip=1, times=2)
        )
        await ws.exec(["echo", "x"], timeout_s=5)
        with pytest.raises(ExecutionBackendError, match="could not be taken back"):
            await ws.get_file("out/a.txt")
        assert fake.calls_to("GET", r"/sandboxes/[^/]+/files") == []
        await ws.destroy()

    async def test_output_cap_sets_truncated(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        over = await ws.exec(["sh", "-c", "yes abcdefg | head -c 3145728"], timeout_s=30)
        assert over.truncated is True
        assert len(over.stdout.encode()) == MAX_OUTPUT_BYTES
        at_cap = await ws.exec(
            ["sh", "-c", f"yes abcdefg | head -c {MAX_OUTPUT_BYTES}"], timeout_s=30
        )
        assert at_cap.truncated is False
        assert len(at_cap.stdout.encode()) == MAX_OUTPUT_BYTES
        err = await ws.exec(["sh", "-c", "yes e | head -c 3000000 >&2"], timeout_s=30)
        assert err.truncated is True and len(err.stderr.encode()) == MAX_OUTPUT_BYTES
        await ws.destroy()

    async def test_sync_endpoint_up_to_the_600s_cap_then_detached(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        sync = await ws.exec(["echo", "sync"], timeout_s=580)
        assert sync.stdout == "sync\n"
        last = fake.calls_to("POST", r"/sandboxes/[^/]+/commands")[-1].body
        assert last["timeoutSeconds"] == 600 and "detached" not in last
        detached = await ws.exec(["echo", "detached"], timeout_s=581)
        assert detached.stdout == "detached\n" and detached.exit_code == 0
        start = fake.calls_to("POST", r"/sandboxes/[^/]+/commands")[-1].body
        assert start["detached"] is True and "timeoutSeconds" not in start
        assert len(fake.calls_to("GET", r"/sandboxes/[^/]+/commands/[0-9]+")) == 1
        await ws.destroy()

    async def test_detached_backstop_stops_and_cleans_up(self, fake: FakeBoat) -> None:
        clock = FakeClock()
        ws = await new_ws(fake, clock=clock)
        fake.detached_hang = True
        result = await ws.exec(["sleep", "1000"], timeout_s=700, stdin=b"x")
        assert result.timed_out is True and result.exit_code == -1
        (stop,) = fake.calls_to("DELETE", r"/sandboxes/[^/]+/commands/[0-9]+")
        assert stop.route.endswith("/commands/1")
        assert sum(clock.sleeps) >= 700 + 5 + 15 + 60
        cleanup = fake.commands()[-1]
        assert 'pkill -KILL -U "$RUN"' in cleanup and ".in" in cleanup
        assert fake.log_lines("pkill") == ["-KILL -U antiek-runner", "-KILL -u antiek-runner"]
        assert ws._dirty is False
        await ws.destroy()

    async def test_sync_api_timeout_cleans_up(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        fake.sync_timeouts = 1
        result = await ws.exec(["echo", "never"], timeout_s=5)
        assert result.timed_out is True and result.exit_code == -1
        cleanup = fake.commands()[-1]
        assert 'pkill -KILL -U "$RUN"' in cleanup and "chmod -R go-w,ug-s" in cleanup
        assert ws._dirty is False
        await ws.destroy()

    @pytest.mark.parametrize("bad", [0, -1, float("nan"), float("inf"), True])
    async def test_timeout_must_be_positive_finite(self, fake: FakeBoat, bad: Any) -> None:
        ws = await new_ws(fake)
        with pytest.raises(ValueError, match="timeout_s"):
            await ws.exec(["true"], timeout_s=bad)
        await ws.destroy()

    async def test_lost_sandbox(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        fake.injected.append(
            Injected("POST", r"/sandboxes/[^/]+/commands", 409, "machine_not_running", "stopped")
        )
        with pytest.raises(WorkspaceLost, match="machine_not_running"):
            await ws.exec(["true"], timeout_s=10)
        fake.deleted.add(ws.sandbox_id)
        with pytest.raises(WorkspaceLost, match="not_found"):
            await ws.exec(["true"], timeout_s=10)
        await ws.destroy()


# --- files ------------------------------------------------------------------------


class TestFiles:
    async def test_binary_round_trip(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        blob = bytes(range(256)) * 4
        await ws.put_file("in/deep/blob.bin", blob)
        assert (pathlib.Path(ws.root) / "in/deep/blob.bin").read_bytes() == blob
        assert await ws.get_file("in/deep/blob.bin") == blob
        (put,) = fake.calls_to("PUT", r"/sandboxes/[^/]+/files")
        assert set(put.body) == {"path", "content", "encoding"}
        assert base64.b64decode(put.body["content"]) == blob
        (get,) = fake.calls_to("GET", r"/sandboxes/[^/]+/files")
        assert get.query["encoding"] == ["base64"]
        await ws.destroy()

    async def test_jail_rejects_escapes_before_any_request(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        sent = len(fake.calls)
        for bad in ("../x", "/etc/passwd", "", "in/../../x", "a\nb"):
            with pytest.raises(ValueError):
                await ws.put_file(bad, b"x")
            with pytest.raises(ValueError):
                await ws.get_file(bad)
        assert len(fake.calls) == sent
        await ws.destroy()

    async def test_symlink_escape_refused_in_the_box(
        self, fake: FakeBoat, tmp_path: pathlib.Path
    ) -> None:
        ws = await new_ws(fake)
        secret = tmp_path / "host-secret.txt"
        secret.write_text("outside")
        os.symlink(secret, pathlib.Path(ws.root) / "out" / "link")
        with pytest.raises(ValueError, match="escapes"):
            await ws.get_file("out/link")
        with pytest.raises(ValueError, match="escapes"):
            await ws.put_file("out/link", b"overwrite")
        assert secret.read_text() == "outside"
        await ws.destroy()

    async def test_missing_and_directory(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        with pytest.raises(FileNotFoundError):
            await ws.get_file("out/none.txt")
        with pytest.raises(FileNotFoundError):
            await ws.get_file("in")
        with pytest.raises(IsADirectoryError):
            await ws.put_file("in", b"x")
        await ws.destroy()

    async def test_five_mib_cap(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        sent = len(fake.calls)
        with pytest.raises(ExecutionBackendError, match="files-API cap"):
            await ws.put_file("in/big", b"x" * (FILE_CAP + 1))
        assert len(fake.calls) == sent
        (pathlib.Path(ws.root) / "out" / "big").write_bytes(b"y" * (FILE_CAP + 1))
        with pytest.raises(ExecutionBackendError, match="5 MiB"):
            await ws.get_file("out/big")
        await ws.destroy()

    async def test_size_mismatch_is_an_error_not_a_short_artifact(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        await ws.put_file("out/a.bin", b"\x00\x01\x02")
        fake.read_size_delta = 1
        with pytest.raises(ExecutionBackendError, match="reported 4 bytes, decoded 3"):
            await ws.get_file("out/a.bin")
        await ws.destroy()

    async def test_newline_in_a_canonical_path_refused(self, fake: FakeBoat) -> None:
        # out/l -> "a\nb": printed unchecked, the marker parse would read the
        # path as ".../out/a", a different file.
        ws = await new_ws(fake)
        out = pathlib.Path(ws.root) / "out"
        (out / "a").write_text("WRONG FILE")
        (out / "a\nb").write_text("right file")
        os.symlink("a\nb", out / "l")
        with pytest.raises(ExecutionBackendError, match="could not resolve"):
            await ws.get_file("out/l")
        assert fake.calls_to("GET", r"/sandboxes/[^/]+/files") == []
        await ws.destroy()

    async def test_put_onto_a_fifo_refused(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        os.mkfifo(pathlib.Path(ws.root) / "out" / "pipe")
        with pytest.raises(ExecutionBackendError, match="not a regular file"):
            await ws.put_file("out/pipe", b"would block")
        assert fake.calls_to("PUT", r"/sandboxes/[^/]+/files") == []
        await ws.destroy()


# --- destroy ------------------------------------------------------------------------


class TestDestroy:
    async def test_idempotent(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        await ws.destroy()
        await ws.destroy()
        deletes = fake.calls_to("DELETE", r"/sandboxes/[^/]+")
        assert len(deletes) == 1
        assert deletes[0].headers["x-ascii-confirm-delete"] == ws.sandbox_id
        sent = len(fake.calls)
        with pytest.raises(WorkspaceLost, match="destroyed"):
            await ws.exec(["true"], timeout_s=10)
        with pytest.raises(WorkspaceLost, match="destroyed"):
            await ws.get_file("in/x")
        with pytest.raises(WorkspaceLost, match="destroyed"):
            await ws.put_file("in/x", b"x")
        assert len(fake.calls) == sent

    async def test_already_gone_is_fine(self, fake: FakeBoat) -> None:
        ws = await new_ws(fake)
        fake.deleted.add(ws.sandbox_id)  # deleted out of band
        await ws.destroy()
        await ws.destroy()
        assert len(fake.calls_to("DELETE", r"/sandboxes/[^/]+")) == 1

    async def test_failure_is_logged_never_raised_and_retried(
        self, fake: FakeBoat, caplog: pytest.LogCaptureFixture
    ) -> None:
        ws = await new_ws(fake)
        fake.injected.append(Injected("DELETE", r"/sandboxes/[^/]+", 500, "http_500", "boom"))
        with caplog.at_level(logging.WARNING):
            await ws.destroy()
        assert "Delete it manually" in caplog.text
        assert ws.sandbox_id not in fake.deleted
        await ws.destroy()
        assert ws.sandbox_id in fake.deleted
        assert len(fake.calls_to("DELETE", r"/sandboxes/[^/]+")) == 2
