"""Tests for substrate/hooks/ -- registry, contract, loader, isolation."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from substrate.hooks import (
    HookContext,
    HookRegistry,
    HookShortCircuit,
    load_extensions,
)


def _ctx(seam_id: str = "test_seam", extension_id: str = "core") -> HookContext:
    return HookContext(seam_id=seam_id, extension_id=extension_id, call_id="c-1", project_id=None)


class _RecordingPre:
    def __init__(self, tag: str, return_value: dict | None = None) -> None:
        self.tag = tag
        self.return_value = return_value
        self.calls: list[tuple[HookContext, dict]] = []

    def __call__(self, ctx: HookContext, **kwargs: Any) -> dict | None:
        self.calls.append((ctx, dict(kwargs)))
        return self.return_value


class _RecordingPost:
    def __init__(self, tag: str, transform=None) -> None:
        self.tag = tag
        self.transform = transform
        self.calls: list[tuple[HookContext, Any, dict]] = []

    def __call__(self, ctx: HookContext, result: Any, **kwargs: Any) -> Any:
        self.calls.append((ctx, result, dict(kwargs)))
        return self.transform(result) if self.transform else result


class _RecordingErr:
    def __init__(self, tag: str, recover: Any = None) -> None:
        self.tag = tag
        self.recover = recover
        self.calls: list[tuple[HookContext, BaseException, dict]] = []

    def __call__(self, ctx: HookContext, exc: BaseException, **kwargs: Any) -> Any | None:
        self.calls.append((ctx, exc, dict(kwargs)))
        return self.recover


def test_register_to_undeclared_seam_raises_keyerror() -> None:
    reg = HookRegistry()
    with pytest.raises(KeyError):
        reg.register_hook("not_declared", _RecordingPre("t"), "pre", "core")


def test_double_declare_raises_valueerror() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")
    with pytest.raises(ValueError):
        reg.declare_seam("s")


def test_mis_typed_hook_fails_at_register() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")
    with pytest.raises(TypeError):
        reg.register_hook("s", "not a hook", "pre", "ext")


def test_invalid_stage_raises_valueerror() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")
    with pytest.raises(ValueError):
        reg.register_hook("s", _RecordingPre("t"), "before", "ext")  # type: ignore[arg-type]


def test_hooks_run_in_priority_then_registration_order() -> None:
    order: list[str] = []

    class _OrderingHook:
        def __init__(self, tag: str) -> None:
            self.tag = tag

        def __call__(self, ctx: HookContext, **kw: Any) -> None:
            order.append(self.tag)
            return None

    reg = HookRegistry()
    reg.declare_seam("s")
    a, b, c = _OrderingHook("a"), _OrderingHook("b"), _OrderingHook("c")
    reg.register_hook("s", b, "pre", "ext", priority=5)
    reg.register_hook("s", a, "pre", "ext", priority=1)
    reg.register_hook("s", c, "pre", "ext", priority=5)
    reg.dispatch_pre("s", _ctx("s"))
    assert order == ["a", "b", "c"]


def test_pre_short_circuit_skips_primitive_runs_post() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")

    class _Sc:
        def __call__(self, ctx: HookContext, **kw: Any) -> None:
            raise HookShortCircuit(result="short-circuited")

    post = _RecordingPost("p")
    reg.register_hook("s", _Sc(), "pre", "ext")
    reg.register_hook("s", post, "post", "ext")

    primitive_called = []

    def primitive(**kw: Any) -> str:
        primitive_called.append(True)
        return "primitive ran"

    result = reg.dispatch("s", _ctx("s"), primitive, x=1)
    assert result == "short-circuited"
    assert primitive_called == []
    assert len(post.calls) == 1


def test_error_hook_recovery_returns_recovered_value() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")
    err = _RecordingErr("e", recover="recovered")
    reg.register_hook("s", err, "err", "ext")

    def primitive(**kw: Any) -> str:
        raise RuntimeError("boom")

    assert reg.dispatch("s", _ctx("s"), primitive) == "recovered"


def test_error_hook_none_chain_re_raises_original() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")
    err1 = _RecordingErr("e1", recover=None)
    err2 = _RecordingErr("e2", recover=None)
    reg.register_hook("s", err1, "err", "ext")
    reg.register_hook("s", err2, "err", "ext")

    def primitive(**kw: Any) -> None:
        raise ValueError("original")

    with pytest.raises(ValueError, match="original"):
        reg.dispatch("s", _ctx("s"), primitive)


def test_register_during_dispatch_does_not_mutate_snapshot() -> None:
    reg = HookRegistry()
    reg.declare_seam("s")

    class _Mutator:
        def __call__(self, ctx: HookContext, **kw: Any) -> None:
            reg.register_hook("s", _RecordingPre("intruder"), "pre", "ext", priority=99)
            return None

    reg.register_hook("s", _Mutator(), "pre", "ext")
    reg.dispatch_pre("s", _ctx("s"))
    assert len(reg._snapshot(reg._pre, "s")) == 2


def _write_ext(root: Path, name: str, body: str, disabled: bool = False) -> Path:
    d = root / "antiek_extensions" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "extension.py").write_text(textwrap.dedent(body))
    if disabled:
        (d / ".disabled").touch()
    return d


def test_loader_loads_extension_and_calls_register(tmp_path: Path) -> None:
    _write_ext(
        tmp_path, "ext_a",
        "from substrate.hooks import HookRegistry\n"
        "def register(registry: HookRegistry) -> None:\n"
        "    pass\n",
    )
    reg = HookRegistry()
    results = load_extensions(reg, project_root=tmp_path)
    assert len(results) == 1
    assert results[0].status == "loaded"


def test_loader_respects_disabled_marker(tmp_path: Path) -> None:
    _write_ext(tmp_path, "ext_skip", "def register(registry): pass", disabled=True)
    reg = HookRegistry()
    results = load_extensions(reg, project_root=tmp_path)
    assert results[0].status == "disabled"


def test_loader_failure_does_not_halt_session(tmp_path: Path) -> None:
    _write_ext(tmp_path, "ext_broken", "raise ImportError('intentional')")
    _write_ext(tmp_path, "ext_ok", "def register(registry): pass")
    reg = HookRegistry()
    results = load_extensions(reg, project_root=tmp_path)
    by_id = {r.extension_id: r for r in results}
    assert by_id["project:ext_broken"].status == "failed"
    assert by_id["project:ext_ok"].status == "loaded"


def test_loader_missing_register_callable_fails_extension(tmp_path: Path) -> None:
    _write_ext(tmp_path, "ext_no_reg", "x = 1")
    reg = HookRegistry()
    results = load_extensions(reg, project_root=tmp_path)
    assert results[0].status == "failed"


def test_loader_no_extensions_dir_returns_empty_list(tmp_path: Path) -> None:
    reg = HookRegistry()
    assert load_extensions(reg, project_root=tmp_path) == []
