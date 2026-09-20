"""``DockerBackend`` behavior tests (spec S5) — docker CLI mocked, one real e2e.

The ``docker`` CLI is a host dependency, so the acceptance tests run against
an injected fake client (``FakeDockerClient``) that satisfies the
``DockerClient`` seam structurally: it records every invocation (args,
timeout, stdin), behaves like the daemon for the file-carrying ``exec``
operations (``mkdir`` / ``tee`` in, ``cat`` out), and can script arbitrary
results — including the timed-out ``docker exec`` that must trigger the
container kill. That makes these assertions:

  * protocol conformance (the backend and its workspaces satisfy the frozen
    protocols; ``timeout_s`` stays mandatory);
  * ``create`` builds the right ``docker run`` invocation — detached, named
    ``antiek-ws-<hex>``, non-root, read-only rootfs, tmpfs scratch, cpu/mem
    limits, and ``--network none`` exactly when ``net_policy=DENY_ALL``;
  * ``exec`` builds the right ``docker exec`` invocation (env / cwd / stdin
    flags) with the caller's ``timeout_s``, and a timeout yields a structured
    ``ExecResult(timed_out=True)`` after force-killing the container;
  * ``put_file``/``get_file`` round-trip raw bytes through the same
    ``tee``/``cat`` transport the real client uses;
  * ``destroy`` removes the container and is idempotent (I6).

One end-to-end test runs against a real docker daemon, skipped when the CLI
or daemon is unavailable.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from runtime.exec_backend import (
    ALLOW_ALL,
    DENY_ALL,
    BackendUnavailable,
    DockerBackend,
    ExecResult,
    ExecutionBackend,
    ExecutionBackendError,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceProfile,
    WorkspaceProvisionError,
)
from runtime.exec_backend.docker_backend import DockerClient, DockerClientResult


class FakeDockerClient:
    """In-memory stand-in for the docker CLI.

    Satisfies the ``DockerClient`` protocol structurally (no inheritance).
    ``run`` records ``(args, timeout_s, stdin)`` per call; the ``exec`` verb
    behaves like the daemon for the file transport — ``mkdir -p`` succeeds,
    ``tee <path>`` stores ``stdin`` under the path, ``cat <path>`` returns
    the stored bytes or fails like a missing file. A ``scripted`` queue is
    consumed FIFO for every call, so a test can force any verb to fail or to
    time out.
    """

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.timeouts: list[float | None] = []
        self.stdins: list[bytes | None] = []
        self.files: dict[str, bytes] = {}
        self.scripted: list[DockerClientResult] = []

    def calls_for(self, verb: str) -> list[list[str]]:
        return [call for call in self.calls if call[0] == verb]

    def user_exec_calls(self) -> list[list[str]]:
        """The ``exec`` invocations made by workspace code — everything after
        the provisioning phase (``create`` = one ``run`` + one ``mkdir``, so
        from the third call on)."""
        return [call for call in self.calls[2:] if call[0] == "exec"]

    async def run(
        self,
        args: Sequence[str],
        *,
        timeout_s: float | None = None,
        stdin: bytes | None = None,
    ) -> DockerClientResult:
        self.calls.append(list(args))
        self.timeouts.append(timeout_s)
        self.stdins.append(stdin)
        if self.scripted:
            return self.scripted.pop(0)
        verb = args[0]
        if verb == "exec":
            if "mkdir" in args:
                return DockerClientResult(exit_code=0, stdout=b"", stderr=b"")
            target = args[-1]
            if target.startswith("/workspace/"):
                rel = target.removeprefix("/workspace/")
                if "tee" in args:
                    self.files[rel] = stdin or b""
                    return DockerClientResult(exit_code=0, stdout=b"", stderr=b"")
                if "cat" in args:
                    content = self.files.get(rel)
                    if content is None:
                        return DockerClientResult(
                            exit_code=1,
                            stdout=b"",
                            stderr=(
                                f"cat: can't open '{target}': "
                                "No such file or directory"
                            ).encode(),
                        )
                    return DockerClientResult(exit_code=0, stdout=content, stderr=b"")
            return DockerClientResult(exit_code=0, stdout=b"", stderr=b"")
        return DockerClientResult(exit_code=0, stdout=b"", stderr=b"")


@pytest.fixture
def fake_client() -> FakeDockerClient:
    return FakeDockerClient()


async def make_workspace(
    client: FakeDockerClient,
    *,
    profile: WorkspaceProfile | None = None,
    limits: ResourceLimits | None = None,
    net_policy: NetPolicy = ALLOW_ALL,
    runtime: str | None = None,
) -> object:
    backend = DockerBackend(client=client, runtime=runtime)
    return await backend.create(
        profile or WorkspaceProfile(name="test"),
        limits=limits or ResourceLimits(),
        net_policy=net_policy,
    )


# --- protocol conformance ------------------------------------------------


def test_backend_satisfies_protocol_structurally(
    fake_client: FakeDockerClient,
) -> None:
    backend = DockerBackend(client=fake_client)
    assert isinstance(backend, ExecutionBackend)
    assert backend.name == "docker"
    assert backend.probe() is None  # type: ignore[func-returns-value]


def test_fake_client_satisfies_docker_client_protocol(
    fake_client: FakeDockerClient,
) -> None:
    assert isinstance(fake_client, DockerClient)


async def test_workspace_satisfies_protocol(fake_client: FakeDockerClient) -> None:
    ws = await make_workspace(fake_client)
    assert isinstance(ws, Workspace)
    assert isinstance(ws.workspace_id, str) and len(ws.workspace_id) > 0
    assert ws.container_name == f"antiek-ws-{ws.workspace_id}"  # type: ignore[attr-defined]


async def test_exec_without_timeout_raises_typeerror(
    fake_client: FakeDockerClient,
) -> None:
    # I1 holds here too: timeout_s is mandatory and keyword-only.
    ws = await make_workspace(fake_client)
    with pytest.raises(TypeError):
        await ws.exec(["echo", "hi"])  # type: ignore[attr-defined]


async def test_exec_result_shape(fake_client: FakeDockerClient) -> None:
    ws = await make_workspace(fake_client)
    result = await ws.exec(["echo", "hi"], timeout_s=5)  # type: ignore[attr-defined]
    assert isinstance(result, ExecResult)
    assert isinstance(result.exit_code, int)
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert isinstance(result.duration_ms, int)
    assert result.duration_ms >= 0
    assert result.timed_out is False
    assert result.truncated is False


async def test_exec_empty_argv_raises(fake_client: FakeDockerClient) -> None:
    ws = await make_workspace(fake_client)
    with pytest.raises(ValueError):
        await ws.exec([], timeout_s=5)  # type: ignore[attr-defined]


# --- create: the docker run invocation -----------------------------------


async def test_create_runs_detached_hardened_container(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client, limits=ResourceLimits(cpu_cores=1.5, memory_mb=512))
    runs = fake_client.calls_for("run")
    assert len(runs) == 1
    argv = runs[0]
    assert argv[0] == "run" and argv[1] == "-d"
    assert "--name" in argv
    assert argv[argv.index("--name") + 1] == ws.container_name  # type: ignore[attr-defined]
    assert "--user" in argv and argv[argv.index("--user") + 1] == "65534:65534"
    assert "--read-only" in argv
    tmpfs_indexes = [i for i, part in enumerate(argv) if part == "--tmpfs"]
    assert len(tmpfs_indexes) == 2
    assert argv[tmpfs_indexes[0] + 1] == "/tmp"
    assert argv[tmpfs_indexes[1] + 1] == "/workspace"
    assert "--cpus" in argv and argv[argv.index("--cpus") + 1] == "1.5"
    assert "--memory" in argv and argv[argv.index("--memory") + 1] == "512m"
    assert "--pids-limit" in argv and argv[argv.index("--pids-limit") + 1] == "256"
    assert "--security-opt" in argv
    assert argv[argv.index("--security-opt") + 1] == "no-new-privileges"
    assert "--network" not in argv  # ALLOW_ALL → default bridge, no flag
    assert argv[-3:] == ["alpine:latest", "sleep", "infinity"]
    # the conventional subdirs are provisioned inside the container
    mkdirs = fake_client.calls_for("exec")
    assert len(mkdirs) == 1
    assert mkdirs[0][-5:] == ["mkdir", "-p", "/workspace/in", "/workspace/out", "/workspace/work"]


async def test_create_deny_all_adds_network_none(
    fake_client: FakeDockerClient,
) -> None:
    await make_workspace(fake_client, net_policy=DENY_ALL)
    argv = fake_client.calls_for("run")[0]
    assert "--network" in argv
    assert argv[argv.index("--network") + 1] == "none"


async def test_create_allowlist_raises_netpolicy_unsupported(
    fake_client: FakeDockerClient,
) -> None:
    backend = DockerBackend(client=fake_client)
    policy = NetPolicy(NetPolicyKind.ALLOWLIST, allow=("10.0.0.0/8",))
    with pytest.raises(NetPolicyUnsupported):
        await backend.create(
            WorkspaceProfile(name="t"), limits=ResourceLimits(), net_policy=policy
        )
    assert fake_client.calls == []  # refused before any daemon contact


async def test_create_forwards_profile_env(fake_client: FakeDockerClient) -> None:
    await make_workspace(
        fake_client, profile=WorkspaceProfile(name="t", env=(("FOO", "bar"),))
    )
    argv = fake_client.calls_for("run")[0]
    assert "-e" in argv
    assert argv[argv.index("-e") + 1] == "FOO=bar"


async def test_create_runtime_passthrough(fake_client: FakeDockerClient) -> None:
    await make_workspace(fake_client, runtime="runsc", net_policy=DENY_ALL)
    argv = fake_client.calls_for("run")[0]
    assert "--runtime" in argv
    assert argv[argv.index("--runtime") + 1] == "runsc"


async def test_create_runtime_from_env_var(
    fake_client: FakeDockerClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTIEK_EXEC_DOCKER_RUNTIME", "runsc")
    await make_workspace(fake_client)
    assert "--runtime" in fake_client.calls_for("run")[0]


async def test_create_run_failure_raises_provision_error(
    fake_client: FakeDockerClient,
) -> None:
    fake_client.scripted = [
        DockerClientResult(
            exit_code=125, stdout=b"", stderr=b"Unable to find image 'nope:latest' locally"
        )
    ]
    backend = DockerBackend(client=fake_client)
    with pytest.raises(WorkspaceProvisionError):
        await backend.create(
            WorkspaceProfile(name="t", image="nope:latest"),
            limits=ResourceLimits(),
            net_policy=ALLOW_ALL,
        )


async def test_create_mkdir_failure_rolls_back_container(
    fake_client: FakeDockerClient,
) -> None:
    fake_client.scripted = [
        DockerClientResult(exit_code=0, stdout=b"", stderr=b""),
        DockerClientResult(exit_code=1, stdout=b"", stderr=b"mkdir: permission denied"),
    ]
    backend = DockerBackend(client=fake_client)
    with pytest.raises(WorkspaceProvisionError):
        await backend.create(
            WorkspaceProfile(name="t"), limits=ResourceLimits(), net_policy=ALLOW_ALL
        )
    run_argv = fake_client.calls_for("run")[0]
    container_name = run_argv[run_argv.index("--name") + 1]
    removes = fake_client.calls_for("rm")
    assert removes == [["rm", "-f", container_name]]  # rollback removed it


# --- exec: the docker exec invocation ------------------------------------


async def test_exec_builds_docker_exec_invocation(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    result = await ws.exec(["echo", "hi"], timeout_s=5)  # type: ignore[attr-defined]
    name = ws.container_name  # type: ignore[attr-defined]
    user_execs = fake_client.user_exec_calls()
    assert user_execs == [["exec", "-w", "/workspace/work", name, "echo", "hi"]]
    exec_index = fake_client.calls.index(user_execs[0])
    assert fake_client.timeouts[exec_index] == 5.0
    assert fake_client.stdins[exec_index] is None
    assert result.exit_code == 0
    assert result.timed_out is False


async def test_exec_env_cwd_stdin_flags(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    result = await ws.exec(  # type: ignore[attr-defined]
        ["cat"], timeout_s=5, env={"X": "y z"}, cwd="work/sub", stdin=b"piped-data",
    )
    name = ws.container_name  # type: ignore[attr-defined]
    user_execs = fake_client.user_exec_calls()
    assert user_execs == [
        ["exec", "-e", "X=y z", "-w", "/workspace/work/sub", "-i", name, "cat"]
    ]
    exec_index = fake_client.calls.index(user_execs[0])
    assert fake_client.stdins[exec_index] == b"piped-data"
    assert result.exit_code == 0


async def test_exec_timeout_returns_structured_result_and_kills_container(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    fake_client.scripted = [
        DockerClientResult(exit_code=-1, stdout=b"", stderr=b"", timed_out=True)
    ]
    result = await ws.exec(["sleep", "60"], timeout_s=1)  # type: ignore[attr-defined]
    assert result.timed_out is True
    assert result.exit_code == -1
    assert result.duration_ms >= 0
    kills = fake_client.calls_for("kill")
    assert kills == [["kill", ws.container_name]]  # type: ignore[attr-defined]
    # the container kill came after the timed-out exec, not before
    exec_index = fake_client.calls.index(fake_client.user_exec_calls()[0])
    assert fake_client.calls.index(kills[0]) > exec_index


# --- files: tee-in / cat-out round-trips ----------------------------------


async def test_put_get_roundtrip_binary_payload(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    payload = bytes(range(256)) * 4  # NULs and high bytes must survive verbatim
    await ws.put_file("out/artifact.bin", payload)  # type: ignore[attr-defined]
    assert await ws.get_file("out/artifact.bin") == payload  # type: ignore[attr-defined]
    # the transport was tee-in / cat-out through the container
    assert any("tee" in call for call in fake_client.calls_for("exec"))
    assert any("cat" in call for call in fake_client.calls_for("exec"))


async def test_put_get_roundtrip_nested_path(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    await ws.put_file("out/deep/nested/file.txt", b"ok")  # type: ignore[attr-defined]
    assert await ws.get_file("out/deep/nested/file.txt") == b"ok"  # type: ignore[attr-defined]
    # the mkdir for the nested parent ran before the tee
    mkdirs = [
        call for call in fake_client.calls_for("exec") if "mkdir" in call
    ]
    assert any("/workspace/out/deep/nested" in call for call in mkdirs)


async def test_put_file_rejects_path_escape(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    for escape in ("../escape.txt", "/etc/passwd", "out/../../escape"):
        with pytest.raises(ValueError):
            await ws.put_file(escape, b"x")  # type: ignore[attr-defined]
    # nothing beyond the provision mkdir reached the daemon
    assert fake_client.user_exec_calls() == []


async def test_get_missing_file_raises_filenotfound(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    with pytest.raises(FileNotFoundError):
        await ws.get_file("out/nope.bin")  # type: ignore[attr-defined]


# --- destroy: idempotent container removal --------------------------------


async def test_destroy_removes_container(fake_client: FakeDockerClient) -> None:
    ws = await make_workspace(fake_client)
    await ws.destroy()  # type: ignore[attr-defined]
    removes = fake_client.calls_for("rm")
    assert removes == [["rm", "-f", ws.container_name]]  # type: ignore[attr-defined]


async def test_destroy_is_idempotent(fake_client: FakeDockerClient) -> None:
    ws = await make_workspace(fake_client)
    await ws.destroy()  # type: ignore[attr-defined]
    await ws.destroy()  # type: ignore[attr-defined]  # second call is a no-op
    assert len(fake_client.calls_for("rm")) == 1


async def test_destroy_tolerates_container_already_removed(
    fake_client: FakeDockerClient,
) -> None:
    ws = await make_workspace(fake_client)
    fake_client.scripted = [
        DockerClientResult(
            exit_code=1, stdout=b"", stderr=b"Error: No such container: antiek-ws-xyz"
        )
    ]
    await ws.destroy()  # type: ignore[attr-defined]  # must not raise


# --- probe: loud unavailability -------------------------------------------


def test_probe_raises_backend_unavailable_when_daemon_down(
    fake_client: FakeDockerClient,
) -> None:
    fake_client.scripted = [
        DockerClientResult(
            exit_code=1,
            stdout=b"",
            stderr=b"error during connect: Cannot connect to the Docker daemon",
        )
    ]
    backend = DockerBackend(client=fake_client)
    with pytest.raises(BackendUnavailable):
        backend.probe()


# --- one real end-to-end test (skips when docker is unavailable) ----------


@pytest.fixture
def real_docker_backend() -> DockerBackend | None:
    """A backend whose probe passes against the real daemon, else None."""
    backend = DockerBackend()
    try:
        backend.probe()
    except ExecutionBackendError:
        return None
    return backend


async def test_real_docker_end_to_end(
    real_docker_backend: DockerBackend | None,
) -> None:
    if real_docker_backend is None:
        pytest.skip("docker CLI or daemon unavailable")
    ws = await real_docker_backend.create(
        WorkspaceProfile(name="e2e"), limits=ResourceLimits(), net_policy=DENY_ALL
    )
    try:
        await ws.put_file("work/hello.txt", b"swarm-e2e\n")
        result = await ws.exec(
            ["sh", "-c", "cat /workspace/work/hello.txt; echo stderr-line >&2"],
            timeout_s=30,
        )
        assert result.exit_code == 0
        assert "swarm-e2e" in result.stdout
        assert "stderr-line" in result.stderr
        assert await ws.get_file("work/hello.txt") == b"swarm-e2e\n"
    finally:
        await ws.destroy()
