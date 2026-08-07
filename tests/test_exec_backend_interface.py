"""Interface-contract tests for the ``ExecutionBackend`` seam (spec S1).

These hold the *frozen* part — the dataclasses, the error taxonomy, the two
protocols, and the mechanical invariants. They do not run any real process;
process-level behavior is in ``tests/test_exec_backend_local.py`` and the
cross-backend contract is in ``tests/test_exec_backend_conformance.py``.

Every invariant carries its mechanical check here (the spec's "rigor" value):
the grep-proof that no host writer leaks into the package (I2, mirroring
``runtime/remote_exec/funnel.py``), the ``TypeError`` guarantee that
``timeout_s`` has no default (I1), the frozen-dataclass guarantee, and the
no-SDK-types-in-signatures guarantee (I5).
"""

from __future__ import annotations

import dataclasses
import inspect
import pathlib

import pytest
from exec_backend_fakes import FakeBackend

from runtime.exec_backend import (
    ALLOW_ALL,
    DENY_ALL,
    MAX_OUTPUT_BYTES,
    BackendUnavailable,
    ExecResult,
    ExecutionBackend,
    ExecutionBackendError,
    LocalProcessBackend,
    NetPolicy,
    NetPolicyKind,
    NetPolicyUnsupported,
    ResourceLimits,
    Workspace,
    WorkspaceLost,
    WorkspaceProfile,
    WorkspaceProvisionError,
)
from runtime.exec_backend.local_process import _LocalWorkspace

#: The three host-side graph-write identifiers that must never appear in the
#: package. Kept as data, not interpolated into any docstring, so this file's
#: own grep does not pollute the audit.
_FORBIDDEN_HOST_WRITER_TOKENS = ("connect_write", "db_lock", "event_log")


def test_exec_timeout_is_mandatory_and_keyword_only() -> None:
    # I1: timeout_s has NO default and is keyword-only. There is no safe
    # default for "how long may untrusted code run", so the signature refuses
    # to compile a call that omits it.
    sig = inspect.signature(_LocalWorkspace.exec)
    params = sig.parameters
    assert "timeout_s" in params
    p = params["timeout_s"]
    assert p.default is inspect.Parameter.empty, "timeout_s must be required"
    assert p.kind == inspect.Parameter.KEYWORD_ONLY, "timeout_s must be keyword-only"


def test_create_limits_and_net_policy_are_mandatory_keyword_only() -> None:
    # limits + net_policy are mandatory (declared even when only ALLOW_ALL is
    # honored) — I4. No silent default policy.
    sig = inspect.signature(LocalProcessBackend.create)
    params = sig.parameters
    for name in ("limits", "net_policy"):
        assert params[name].default is inspect.Parameter.empty, f"{name} must be required"
        assert params[name].kind == inspect.Parameter.KEYWORD_ONLY


def test_exec_result_is_structured_not_a_popen() -> None:
    # I1: ExecResult is a frozen dataclass with exactly the structured fields,
    # never a raw Popen/stream.
    fields = {f.name for f in dataclasses.fields(ExecResult)}
    assert fields == {"exit_code", "stdout", "stderr", "duration_ms",
                      "timed_out", "truncated"}
    r = ExecResult(exit_code=0, stdout="hi", stderr="", duration_ms=3)
    assert r.exit_code == 0
    assert r.stdout == "hi"
    assert r.duration_ms == 3
    assert r.timed_out is False
    assert r.truncated is False


def test_seam_dataclasses_are_frozen() -> None:
    for cls in (NetPolicy, ResourceLimits, WorkspaceProfile, ExecResult):
        params = getattr(cls, "__dataclass_params__", None)
        assert params is not None and params.frozen is True, cls
    r = ExecResult(exit_code=0, stdout="", stderr="", duration_ms=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.exit_code = 5  # type: ignore[misc]


def test_net_policy_singletons_and_enum() -> None:
    assert ALLOW_ALL.kind is NetPolicyKind.ALLOW_ALL
    assert DENY_ALL.kind is NetPolicyKind.DENY_ALL
    assert ALLOW_ALL.allow == ()
    kinds = {k.value for k in NetPolicyKind}
    assert kinds == {"allow_all", "deny_all", "allowlist"}
    allowlist = NetPolicy(NetPolicyKind.ALLOWLIST, allow=("10.0.0.0/8", "example.com"))
    assert allowlist.allow == ("10.0.0.0/8", "example.com")


def test_error_taxonomy_subclasses_runtime_error() -> None:
    # Mirrors runtime/remote_exec/provider.py: one RuntimeError base, concrete
    # subclasses. ``except ExecutionBackendError`` catches them all.
    assert issubclass(ExecutionBackendError, RuntimeError)
    for sub in (BackendUnavailable, WorkspaceProvisionError,
                NetPolicyUnsupported, WorkspaceLost):
        assert issubclass(sub, ExecutionBackendError)
        assert issubclass(sub, RuntimeError)


def test_no_host_writer_identifier_in_package() -> None:
    # I2 grep-proof, mirrored from runtime/remote_exec/funnel.py. The three
    # host-side graph-write identifiers appear in ZERO files of the package.
    pkg_dir = pathlib.Path(runtime_exec_backend_file()).resolve().parent
    hits: list[str] = []
    for src in sorted(pkg_dir.rglob("*.py")):
        text = src.read_text(encoding="utf-8")
        for token in _FORBIDDEN_HOST_WRITER_TOKENS:
            if token in text:
                hits.append(f"{src.relative_to(pkg_dir)}: {token}")
    assert not hits, f"host-writer identifiers leaked into exec_backend: {hits}"


def runtime_exec_backend_file() -> str:
    import runtime.exec_backend as pkg

    assert pkg.__file__ is not None
    return pkg.__file__


#: Top-level module names of provider SDKs that must never be imported by the
#: interface (I5). Checked against the AST's actual import statements — not as
#: bare substrings, so the docstring may still *name* ``daytona``/an SDK as
#: prose precedent without tripping the guard (the thing that matters is an
#: import, not a mention).
_FORBIDDEN_SDK_MODULES = frozenset(
    {"docker", "e2b", "daytona", "daytona_sdk", "modal", "boto3", "kubernetes"}
)


def test_interface_has_no_provider_sdk_imports() -> None:
    # I5: provider SDK types never cross the interface. interface.py must be
    # pure stdlib — no docker/e2b/daytona SDK import sneaks in. We parse the
    # AST and inspect real import statements rather than grepping substrings,
    # so a legitimate prose reference to the daytona lazy-import idiom does not
    # false-positive while an actual import is still caught.
    import ast

    import runtime.exec_backend.interface as iface

    assert iface.__file__ is not None
    src = pathlib.Path(iface.__file__).read_text(encoding="utf-8")
    imported_roots: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])
    leaked = imported_roots & _FORBIDDEN_SDK_MODULES
    assert not leaked, f"forbidden SDK import in interface.py: {sorted(leaked)}"


def test_output_cap_constant_is_two_mib() -> None:
    assert MAX_OUTPUT_BYTES == 2 * 1024 * 1024


@pytest.mark.parametrize(
    "backend",
    [FakeBackend(), LocalProcessBackend()],
    ids=["fake", "local"],
)
def test_backend_satisfies_protocol_structurally(backend: object) -> None:
    # runtime_checkable: the fake and the real backend both satisfy
    # ExecutionBackend without inheriting it — the seam is structural.
    assert isinstance(backend, ExecutionBackend)
    assert isinstance(backend, ExecutionBackend)  # name/probe/create present


async def test_workspaces_satisfy_protocol_structurally(tmp_path: str) -> None:
    local = LocalProcessBackend(workdir_base=tmp_path)
    local_ws = await local.create(
        WorkspaceProfile(name="t"), limits=ResourceLimits(), net_policy=ALLOW_ALL,
    )
    fake_ws = await FakeBackend().create(
        WorkspaceProfile(name="t"), limits=ResourceLimits(), net_policy=ALLOW_ALL,
    )
    assert isinstance(local_ws, Workspace)
    assert isinstance(fake_ws, Workspace)
    # opaque, ID-addressed (I6)
    assert isinstance(local_ws.workspace_id, str) and len(local_ws.workspace_id) > 0
    assert isinstance(fake_ws.workspace_id, str) and len(fake_ws.workspace_id) > 0
