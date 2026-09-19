"""The exec-backend join at the cascade launch site — behavioural, not shaped.

WHY THIS FILE WAS REWRITTEN
---------------------------
The previous version of this file asserted, against the AST of
``cascade_routes.launch``, that ``runner`` is *never reassigned inside the
``ANTIEK_EXEC_BACKEND`` guard*, and called that "the flag cannot change which
runner the session gets". At the time, the guard's entire body was::

    _exec_backend = build_execution_backend(...)
    logger.info("ExecutionBackend wired: %s (runner remains %s)", ...)

So the tests passed because the seam did nothing. Every assertion was about
the *shape* of a log statement, and all three would have stayed green forever
while no agent code ever ran anywhere but in the API process. That is a test
encoding a bug as the specification — the second time on this project — and it
is worth naming plainly: an AST assertion over a branch that has no effects
cannot distinguish "wired" from "logged". The tests below assert effects.

(One inherited assertion survives on its merits: the flag-unset path must
construct no backend. It is now proven by spying on the real factory during a
real loop build, which is strictly stronger than parsing the source for a
guard.)

WHAT THE CONTRACT ACTUALLY IS, now that the seam is joined
----------------------------------------------------------
  * flag unset  → ``_research_loop_factory`` returns the contract gather stub,
    byte-identical to today, and ``build_execution_backend`` is never called.
  * flag set    → the loop is the contained gather loop and running it drives
    the backend: ``create`` → ``put_file`` → ``exec`` × N → ``get_file`` →
    ``destroy``. Asserted on the recorded calls and on the returned bytes
    reaching the ``StepEvent``s, never on a log line or a constructed object.
  * flag set to a backend that is unavailable → the launch path RAISES. A
    silent downgrade to ``local`` would run untrusted code unsandboxed while
    the operator believed it was contained.
  * the runner is NOT swapped by the flag. That is deliberate and is what
    preserves single-writer: ``HostLocalRunner`` keeps ``on_emit`` bound to the
    promotion funnel, so contained results return through the one existing
    serialized writer. The brief for this lane expected the join to reassign
    ``runner``; it should not, and ``test_flag_does_not_swap_the_runner``
    pins the opposite.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Mapping, Sequence

import pytest

import interfaces.research.api.cascade_routes as cascade_mod
from runtime.exec_backend.factory import BACKEND_ENV, build_execution_backend
from runtime.exec_backend.interface import (
    ALLOW_ALL,
    DENY_ALL,
    BackendUnavailable,
    ExecResult,
    ExecutionBackend,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceProfile,
)
from runtime.exec_backend.local_process import LocalProcessBackend
from runtime.research_runner.budget import BudgetManager
from runtime.research_runner.contained_gather import (
    ARTIFACT_PATH,
    PROGRAM_PATH,
    REQUEST_PATH,
    make_contained_gather_loop,
)
from runtime.research_runner.host_local import LoopContext, make_contract_gather_stub
from runtime.research_runner.protocol import BudgetCap, ResearchPlan

# ---------------------------------------------------------------------------
# Test doubles: a backend that records what it was asked to do.
# ---------------------------------------------------------------------------


class RecordingWorkspace:
    """Records every seam call. ``exec`` replays a canned stdout so the test
    can prove the *returned bytes* reach the StepEvent, not just that a call
    happened."""

    def __init__(self, workspace_id: str, calls: list[tuple[str, object]]) -> None:
        self._id = workspace_id
        self._calls = calls
        self._files: dict[str, bytes] = {}

    @property
    def workspace_id(self) -> str:
        return self._id

    async def exec(
        self,
        argv: Sequence[str],
        *,
        timeout_s: float,
        env: Mapping[str, str] | None = None,
        cwd: str | None = None,
        stdin: bytes | None = None,
    ) -> ExecResult:
        self._calls.append(("exec", (list(argv), timeout_s)))
        step = argv[-1]
        self._files.setdefault(ARTIFACT_PATH, b"")
        self._files[ARTIFACT_PATH] += (
            b'{"step": ' + str(step).encode() + b', "uid": 65534}\n'
        )
        return ExecResult(
            exit_code=0,
            stdout=f"[recorded] pass {step} as uid 65534\n",
            stderr="",
            duration_ms=1,
        )

    async def put_file(self, path: str, content: bytes) -> None:
        self._calls.append(("put_file", path))
        self._files[path] = content

    async def get_file(self, path: str) -> bytes:
        self._calls.append(("get_file", path))
        return self._files[path]

    async def destroy(self) -> None:
        self._calls.append(("destroy", self._id))


class RecordingBackend:
    """Structural ``ExecutionBackend`` that honours any net policy, so the
    join can be exercised without a container runtime."""

    def __init__(self, name: str = "recording") -> None:
        self._name = name
        self.calls: list[tuple[str, object]] = []

    @property
    def name(self) -> str:
        return self._name

    def probe(self) -> None:
        self.calls.append(("probe", None))

    async def create(
        self,
        profile: WorkspaceProfile,
        *,
        limits: ResourceLimits,
        net_policy: NetPolicy,
    ) -> RecordingWorkspace:
        self.calls.append(("create", (profile.image, net_policy.kind)))
        return RecordingWorkspace(f"ws-{len(self.calls)}", self.calls)


assert isinstance(RecordingBackend(), ExecutionBackend)
assert isinstance(RecordingWorkspace("x", []), Workspace)


def _ctx(sub_question: str = "what is the seam?") -> LoopContext:
    plan = ResearchPlan(
        investigation_id="inv-exec-join",
        sub_question=sub_question,
        budget=BudgetCap(cost_usd=1.0, max_steps=50),
    )
    return LoopContext(plan, BudgetManager())


async def _drain(loop_fn, ctx: LoopContext) -> list:
    return [ev async for ev in loop_fn(ctx)]


# ---------------------------------------------------------------------------
# DONE-BAR 2 — flag unset is byte-identical to today
# ---------------------------------------------------------------------------


class TestFlagUnsetIsUnchanged:
    def test_unset_returns_the_contract_gather_stub(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Same loop, same events, same costs as before this lane. The stub is
        a closure, so identity comparison is impossible; compare the emitted
        event stream instead, which is what every downstream consumer sees."""
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)

        produced = asyncio.run(_drain(cascade_mod._research_loop_factory(), _ctx()))
        reference = asyncio.run(
            _drain(make_contract_gather_stub(steps=2, cost_per_step=0.01), _ctx())
        )

        assert [(e.kind, e.text, e.cost_usd, e.data) for e in produced] == [
            (e.kind, e.text, e.cost_usd, e.data) for e in reference
        ]

    def test_unset_never_builds_a_backend(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The inherited "default path constructs no backend" invariant, now
        proven by effect rather than by parsing the source for a guard."""
        monkeypatch.delenv(BACKEND_ENV, raising=False)
        monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)
        called: list[object] = []
        monkeypatch.setattr(
            cascade_mod,
            "build_execution_backend",
            lambda *a, **k: called.append((a, k)),
        )

        cascade_mod._research_loop_factory()

        assert called == [], "flag-unset path constructed an ExecutionBackend"


# ---------------------------------------------------------------------------
# DONE-BAR 3 — flag set: execution actually reaches the backend
# ---------------------------------------------------------------------------


class TestFlagSetDrivesTheBackend:
    def test_running_the_loop_drives_the_whole_workspace_lifecycle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        backend = RecordingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=2, cost_per_step=0.01)

        asyncio.run(_drain(loop_fn, _ctx()))

        kinds = [name for name, _ in backend.calls]
        assert kinds == [
            "create",
            "put_file",   # the program
            "put_file",   # the request
            "put_file",   # request refreshed for pass 0
            "exec",
            "put_file",   # request refreshed for pass 1
            "exec",
            "get_file",   # artifact export
            "destroy",
        ], backend.calls

        paths = [arg for name, arg in backend.calls if name == "put_file"]
        assert paths == [PROGRAM_PATH, REQUEST_PATH, REQUEST_PATH, REQUEST_PATH]
        assert ("get_file", ARTIFACT_PATH) in backend.calls

        # Every exec carries a mandatory timeout (invariant I1).
        for name, arg in backend.calls:
            if name == "exec":
                argv, timeout_s = arg  # type: ignore[misc]
                assert timeout_s > 0
                assert argv[1] == "gather.py"

    def test_bytes_from_the_workspace_reach_the_step_events(self) -> None:
        """The proof that this is execution and not construction: the text of
        each step event is the stdout the workspace returned."""
        backend = RecordingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=2)

        events = asyncio.run(_drain(loop_fn, _ctx()))
        steps = [e for e in events if e.kind == "step"]

        assert [e.text for e in steps] == [
            "[recorded] pass 0 as uid 65534",
            "[recorded] pass 1 as uid 65534",
        ]

    def test_note_carries_the_exported_artifact(self) -> None:
        """The note is what the promotion funnel promotes; it is built from the
        workspace's exported out/ artifact, not from host-side invention."""
        backend = RecordingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=3)

        events = asyncio.run(_drain(loop_fn, _ctx()))
        notes = [e for e in events if e.kind == "note"]

        assert len(notes) == 1
        assert notes[0].data["contained_passes"] == 3
        assert notes[0].data["ran_as_uid"] == 65534
        assert notes[0].data["gather_mode"] == "exec_backend"

    def test_a_failed_contained_step_fails_the_leaf(self) -> None:
        """A step that did not run is not a step that found nothing. The loop
        raises rather than emitting a note the operator would read as
        evidence."""

        class FailingWorkspace(RecordingWorkspace):
            async def exec(self, argv, *, timeout_s, env=None, cwd=None, stdin=None):
                return ExecResult(
                    exit_code=2, stdout="", stderr="boom", duration_ms=1
                )

        class FailingBackend(RecordingBackend):
            async def create(self, profile, *, limits, net_policy):
                self.calls.append(("create", (profile.image, net_policy.kind)))
                return FailingWorkspace("ws-fail", self.calls)

        backend = FailingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=1)

        with pytest.raises(Exception, match="exited 2"):
            asyncio.run(_drain(loop_fn, _ctx()))

        assert ("destroy", "ws-fail") in backend.calls, "workspace leaked on failure"

    def test_real_subprocess_runs_the_program(self, tmp_path) -> None:
        """End to end against a REAL backend: a real child process, the real
        program source, real files in and out. ALLOW_ALL is passed explicitly
        because LocalProcessBackend refuses DENY_ALL (see the egress test) —
        this test proves the program executes, not that it is contained."""
        backend = LocalProcessBackend(workdir_base=str(tmp_path))
        loop_fn = make_contained_gather_loop(
            backend,
            steps=2,
            interpreter=sys.executable,
            net_policy=ALLOW_ALL,
            image=None,
        )

        events = asyncio.run(_drain(loop_fn, _ctx("does the child really run?")))
        steps = [e for e in events if e.kind == "step"]
        notes = [e for e in events if e.kind == "note"]

        assert len(steps) == 2
        for i, ev in enumerate(steps):
            assert ev.text.startswith(f"[contained] pass {i} ")
            assert "does the child really run?" in ev.text
        assert notes[0].data["contained_passes"] == 2
        # The program reports the uid it actually ran as. Under this backend
        # that is the service user — which is exactly the exposure the docker
        # backend exists to close, and why local is not a sandbox.
        assert notes[0].data["ran_as_uid"] == __import__("os").getuid()


# ---------------------------------------------------------------------------
# DONE-BAR 5 — unavailable must raise, never downgrade
# ---------------------------------------------------------------------------


class TestNoSilentDowngrade:
    def test_docker_absent_raises_out_of_the_loop_factory(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Docker is not running on this machine, so this is the real path.
        The launch path must surface BackendUnavailable; returning a
        LocalProcessBackend here would run untrusted code on the bare host
        while the operator believed it was contained."""
        monkeypatch.setenv(BACKEND_ENV, "docker")
        monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)

        with pytest.raises(BackendUnavailable):
            cascade_mod._research_loop_factory()

    def test_unknown_kind_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(BACKEND_ENV, "gvisor-someday")
        monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)

        with pytest.raises(BackendUnavailable, match="unknown ExecutionBackend kind"):
            cascade_mod._research_loop_factory()

    def test_local_backend_refuses_the_declared_no_egress_policy(
        self, tmp_path
    ) -> None:
        """The stronger half of "never silently downgrade": even when the
        operator picks ``local`` deliberately, it cannot serve the loop's
        declared DENY_ALL, so it refuses at create() (invariant I4) instead of
        gathering with full host egress."""
        backend = LocalProcessBackend(workdir_base=str(tmp_path))
        loop_fn = make_contained_gather_loop(backend, steps=1, net_policy=DENY_ALL)

        with pytest.raises(NetPolicyUnsupported):
            asyncio.run(_drain(loop_fn, _ctx()))

    def test_default_net_policy_is_deny_all(self) -> None:
        backend = RecordingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=1)

        asyncio.run(_drain(loop_fn, _ctx()))

        create = next(arg for name, arg in backend.calls if name == "create")
        assert create[1] is NetPolicyKind.DENY_ALL

    def test_exec_backend_and_exa_gather_are_mutually_exclusive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both flags set means the operator has asked for contained gather and
        for a loop that retrieves and ingests in-process. Honouring either
        silently would leave a false belief about containment."""
        monkeypatch.setenv(BACKEND_ENV, "local")
        monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")

        with pytest.raises(RuntimeError, match="mutually exclusive"):
            cascade_mod._research_loop_factory()


# ---------------------------------------------------------------------------
# DONE-BAR 4 — no second DuckDB writer
# ---------------------------------------------------------------------------


class TestSingleWriterPreserved:
    def test_the_join_module_names_no_host_writer(self) -> None:
        """Same grep-proof discipline as ``runtime/remote_exec/funnel.py`` and
        ``tests/test_exec_backend_interface.py``: the join module contains none
        of the host-side graph-write identifiers, so it cannot be a writer."""
        import pathlib

        import runtime.research_runner.contained_gather as mod

        assert mod.__file__ is not None
        src = pathlib.Path(mod.__file__).read_text(encoding="utf-8")
        for token in ("connect_write", "ingest_lock", "log_event", "duckdb"):
            assert token not in src, f"{token} reached the contained gather join"

    def test_results_return_only_through_on_emit(self) -> None:
        """The runner-level proof. ``HostLocalRunner`` forwards note/question
        events to ``on_emit``, which the cascade binds to ``funnel.submit`` —
        the single serialized writer. Driving the contained loop through the
        real runner shows every promotable result arriving there and nowhere
        else."""
        from runtime.research_runner.host_local import HostLocalRunner

        backend = RecordingBackend()
        loop_fn = make_contained_gather_loop(backend, steps=2)
        promoted: list = []

        async def capture(ev) -> None:
            promoted.append(ev)

        async def scenario() -> None:
            runner = HostLocalRunner(loop_fn, on_emit=capture, seal_on_complete=False)
            plan = ResearchPlan(
                investigation_id="inv-single-writer",
                sub_question="does anything else write?",
                budget=BudgetCap(cost_usd=1.0, max_steps=50),
            )
            handle = await runner.start("inv-single-writer", plan)
            async for _ in runner.stream(handle):
                pass

        asyncio.run(scenario())

        assert [e.kind for e in promoted] == ["note"]
        assert promoted[0].data["contained_passes"] == 2


# ---------------------------------------------------------------------------
# The runner is deliberately NOT swapped
# ---------------------------------------------------------------------------


class TestRunnerIsNotSwapped:
    def test_flag_does_not_swap_the_runner(self) -> None:
        """``launch`` constructs exactly one runner, a ``HostLocalRunner``, and
        the exec-backend flag does not appear anywhere near it. This is the
        assertion the old AST test was reaching for but got right for the wrong
        reason: the runner must stay fixed because it owns ``on_emit`` and the
        budget, so swapping it is how a second writer would get in. What the
        flag changes is the loop the runner drives.
        """
        import ast
        import pathlib

        src = pathlib.Path(cascade_mod.__file__).read_text(encoding="utf-8")
        tree = ast.parse(src)
        launch = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
            and n.name == "launch"
            and any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Name)
                and c.func.id == "HostLocalRunner"
                for c in ast.walk(n)
            )
        )
        runner_assigns = [
            node
            for node in ast.walk(launch)
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "runner" for t in node.targets
            )
        ]
        assert len(runner_assigns) == 1
        call = runner_assigns[0].value
        assert isinstance(call, ast.Call)
        assert isinstance(call.func, ast.Name)
        assert call.func.id == "HostLocalRunner"
        assert "BACKEND_ENV" not in {
            n.id for n in ast.walk(launch) if isinstance(n, ast.Name)
        }, "the exec-backend flag leaked back into launch(); it belongs in the loop factory"

    def test_factory_symbols_still_imported_in_cascade(self) -> None:
        assert cascade_mod.build_execution_backend is build_execution_backend
        assert cascade_mod.BACKEND_ENV == "ANTIEK_EXEC_BACKEND"
