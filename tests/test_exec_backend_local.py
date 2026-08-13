"""``LocalProcessBackend`` behavior tests (spec S2) — real subprocesses.

These are the acceptance tests the brief requires, run for real against the
host's ``sh`` / ``echo`` / ``sleep`` / ``cat`` / ``head`` (no mocking):

  * ``exec(["echo","hi"], timeout_s=5)`` → exit 0, ``"hi"`` in stdout, a
    ``duration_ms``;
  * a command exceeding its timeout (``["sleep","10"], timeout_s=1``) returns
    a structured ``timed_out`` result — not a hang, not an unhandled raise;
  * ``put_file`` / ``get_file`` round-trip;
  * ``destroy()`` removes the workspace dir.

Plus the invariants that make Stage 0 honest: the parent env is never
inherited (no host-secret leak), egress policy is enforced by refusal (I4),
output is capped (I1), and the SIGKILL escalation covers a process that
ignores SIGTERM (so the timeout kill cannot leak a stuck child).
"""

from __future__ import annotations

import logging
import time

import pytest

from runtime.exec_backend import (
    ALLOW_ALL,
    DENY_ALL,
    MAX_OUTPUT_BYTES,
    LocalProcessBackend,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    WorkspaceProfile,
)


@pytest.fixture
def backend(tmp_path: str) -> LocalProcessBackend:
    return LocalProcessBackend(workdir_base=tmp_path)


async def make_workspace(backend: LocalProcessBackend) -> object:
    return await backend.create(
        WorkspaceProfile(name="test"), limits=ResourceLimits(), net_policy=ALLOW_ALL
    )


# --- acceptance: exec ----------------------------------------------------


async def test_echo_returns_exit_zero_with_output_and_duration(
    backend: LocalProcessBackend,
) -> None:
    ws = await make_workspace(backend)
    result = await ws.exec(["echo", "hi"], timeout_s=5)  # type: ignore[attr-defined]
    assert result.exit_code == 0
    assert "hi" in result.stdout
    assert result.duration_ms >= 0
    assert result.timed_out is False


async def test_nonzero_exit_code_propagates(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    result = await ws.exec(["sh", "-c", "exit 42"], timeout_s=5)  # type: ignore[attr-defined]
    assert result.exit_code == 42


# --- acceptance: timeout (structured result, not a hang) -----------------


async def test_timeout_returns_structured_result_not_a_hang(
    backend: LocalProcessBackend,
) -> None:
    ws = await make_workspace(backend)
    start = time.monotonic()
    result = await ws.exec(["sleep", "10"], timeout_s=1)  # type: ignore[attr-defined]
    wall = time.monotonic() - start
    # structured timeout result — never a hang, never an unhandled exception
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.duration_ms >= 900  # it actually waited ~the declared timeout
    assert wall < 6  # …not 10s; the process group was killed


async def test_timeout_kills_a_sigterm_ignorer(
    backend: LocalProcessBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A child that traps SIGTERM must still die via the SIGKILL escalation so
    # the kill path cannot leak a stuck child. Shorten the grace so the test
    # stays fast.
    import runtime.exec_backend.local_process as local_process

    monkeypatch.setattr(local_process, "_KILL_GRACE_S", 1.0)
    ws = await make_workspace(backend)
    start = time.monotonic()
    result = await ws.exec(  # type: ignore[attr-defined]
        ["sh", "-c", "trap '' TERM; sleep 30"], timeout_s=1,
    )
    wall = time.monotonic() - start
    assert result.timed_out is True
    assert result.exit_code == -1
    assert wall < 6  # 1s timeout + ~1s grace, not 30s


# --- acceptance: files ---------------------------------------------------


async def test_put_get_roundtrip_bytes(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    payload = bytes(range(256)) * 4  # 1024 bytes incl. NULs and high bytes
    await ws.put_file("out/result.bin", payload)  # type: ignore[attr-defined]
    assert await ws.get_file("out/result.bin") == payload  # type: ignore[attr-defined]


async def test_get_missing_file_raises(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    with pytest.raises(FileNotFoundError):
        await ws.get_file("out/nope.bin")  # type: ignore[attr-defined]


# --- acceptance: destroy -------------------------------------------------


async def test_destroy_removes_workspace_dir(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    root = ws.root  # type: ignore[attr-defined]
    assert root.exists()
    await ws.destroy()  # type: ignore[attr-defined]
    assert not root.exists()


async def test_destroy_is_idempotent(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    await ws.destroy()  # type: ignore[attr-defined]
    await ws.destroy()  # type: ignore[attr-defined]  # second call is a no-op
    assert not ws.root.exists()  # type: ignore[attr-defined]


# --- honesty invariants --------------------------------------------------


async def test_put_file_rejects_path_escape(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    for escape in ("../escape.txt", "/etc/passwd", "out/../../escape"):
        with pytest.raises(ValueError):
            await ws.put_file(escape, b"x")  # type: ignore[attr-defined]


async def test_parent_environment_not_inherited(
    backend: LocalProcessBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The host's secrets live in the parent env; the child must NOT see them.
    monkeypatch.setenv("ANTIEK_LEAK_SENTINEL", "host-secret-do-not-leak")
    ws = await make_workspace(backend)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["sh", "-c", "printf %s \"$ANTIEK_LEAK_SENTINEL\""], timeout_s=5,
    )
    assert result.exit_code == 0
    assert "host-secret-do-not-leak" not in result.stdout
    assert result.stdout == ""  # the var is unset in the minimal-env child


async def test_profile_env_baseline_is_passed(tmp_path: str) -> None:
    backend = LocalProcessBackend(workdir_base=tmp_path)
    ws = await backend.create(
        WorkspaceProfile(name="t", env=(("PROFILE_VAR", "from-profile"),)),
        limits=ResourceLimits(),
        net_policy=ALLOW_ALL,
    )
    result = await ws.exec(["sh", "-c", "printf %s \"$PROFILE_VAR\""], timeout_s=5)
    assert result.exit_code == 0
    assert result.stdout == "from-profile"


async def test_exec_env_override_is_passed(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["sh", "-c", "printf %s \"$MYVAR\""], timeout_s=5, env={"MYVAR": "passed"},
    )
    assert result.exit_code == 0
    assert result.stdout == "passed"


async def test_missing_binary_returns_structured_127(
    backend: LocalProcessBackend,
) -> None:
    ws = await make_workspace(backend)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["definitely-not-a-real-binary-xyzzy"], timeout_s=5,
    )
    assert result.exit_code == 127  # shell "command not found" convention
    assert result.stderr != ""


async def test_empty_argv_raises(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    with pytest.raises(ValueError):
        await ws.exec([], timeout_s=5)  # type: ignore[attr-defined]


async def test_deny_all_policy_rejected_at_create(
    backend: LocalProcessBackend,
) -> None:
    # I4: plain subprocess has no network filter, so a policy it cannot
    # enforce is refused loudly at create(), never silently ignored.
    with pytest.raises(NetPolicyUnsupported):
        await backend.create(
            WorkspaceProfile(name="t"), limits=ResourceLimits(), net_policy=DENY_ALL,
        )


async def test_allowlist_policy_rejected_at_create(
    backend: LocalProcessBackend,
) -> None:
    with pytest.raises(NetPolicyUnsupported):
        await backend.create(
            WorkspaceProfile(name="t"),
            limits=ResourceLimits(),
            net_policy=NetPolicy(NetPolicyKind.ALLOWLIST, allow=("1.2.3.4",)),
        )


async def test_output_truncated_beyond_cap(backend: LocalProcessBackend) -> None:
    # 3 MiB of NULs — past the 2 MiB cap. Must not deadlock and must cap.
    ws = await make_workspace(backend)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["sh", "-c", "head -c 3145728 /dev/zero"], timeout_s=20,
    )
    assert result.exit_code == 0
    assert result.truncated is True
    assert len(result.stdout) == MAX_OUTPUT_BYTES


async def test_stdin_is_piped_to_child(backend: LocalProcessBackend) -> None:
    ws = await make_workspace(backend)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["cat"], timeout_s=5, stdin=b"piped-via-stdin",
    )
    assert result.exit_code == 0
    assert result.stdout == "piped-via-stdin"


def test_probe_is_offline_and_logs_honesty(
    backend: LocalProcessBackend, caplog: pytest.LogCaptureFixture
) -> None:
    # "local" has nothing to probe and must not touch the network; it logs one
    # honesty line about which ResourceLimits fields it actually enforces.
    with caplog.at_level(logging.INFO, logger="antiek.exec_backend.local"):
        backend.probe()  # must not raise
    assert any(
        "LocalProcessBackend ready" in rec.getMessage() for rec in caplog.records
    )
