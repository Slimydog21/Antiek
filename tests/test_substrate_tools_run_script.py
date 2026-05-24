"""Tests for substrate/tools -- sandbox, preflight, adapter_map, run_script."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from substrate.observability.burn import BurnRecorder
from substrate.observability.burn_context import (
    BurnContext,
    reset_burn_context,
    set_burn_context,
)
from substrate.tools.adapter_map import DuplicateAdapterName, build_import_map
from substrate.tools.run_script import _USAGE_MARKER_PREFIX, _parse_usage_marker, is_enabled, run_script
from substrate.tools.run_script_preflight import DENO_MIN_VERSION, preflight
from substrate.tools.sandbox import SandboxPolicy, ScriptResult

_DENO = shutil.which("deno")
_HAVE_DENO = _DENO is not None
_deno_required = pytest.mark.skipif(not _HAVE_DENO, reason="deno not installed")


@pytest.fixture(autouse=True)
def _reset_burn_cache():
    BurnRecorder._reset_instances()
    yield
    BurnRecorder._reset_instances()


def test_sandbox_policy_deny_all_emits_no_flags() -> None:
    assert SandboxPolicy.deny_all().to_deno_flags() == []


def test_sandbox_policy_emits_only_nonempty_flags() -> None:
    p = SandboxPolicy(allow_net=("api.exa.ai",), allow_env=("EXA_API_KEY",))
    flags = p.to_deno_flags()
    assert "--allow-net=api.exa.ai" in flags
    assert "--allow-env=EXA_API_KEY" in flags
    assert not any(f.startswith("--allow-read") for f in flags)


def test_sandbox_policy_is_frozen() -> None:
    p = SandboxPolicy(allow_net=("a",))
    with pytest.raises((AttributeError, TypeError)):
        p.allow_net = ("evil.com",)  # type: ignore[misc]


def test_sandbox_policy_multiple_hosts() -> None:
    p = SandboxPolicy(allow_net=("api.exa.ai", "browserbase.com:443"))
    [flag] = [f for f in p.to_deno_flags() if f.startswith("--allow-net")]
    assert flag == "--allow-net=api.exa.ai,browserbase.com:443"


def test_preflight_returns_unavailable_when_deno_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("shutil.which", lambda name: None if name == "deno" else "/usr/bin/" + name)
    p = preflight()
    assert p.available is False
    assert p.error is not None and "deno not found" in p.error
    assert not p.usable


def test_preflight_min_version_constant_is_sensible() -> None:
    assert DENO_MIN_VERSION == (1, 40, 0)


def _write_adapter(project_root: Path, ext: str, name: str, body: str = "export const x = 1;") -> Path:
    d = project_root / "antiek_extensions" / ext / "adapters" / name
    d.mkdir(parents=True, exist_ok=True)
    f = d / "index.ts"
    f.write_text(body)
    return f


def test_build_import_map_empty_when_no_extensions(tmp_path: Path) -> None:
    assert build_import_map(tmp_path) == {"imports": {}}


def test_build_import_map_discovers_adapter(tmp_path: Path) -> None:
    f = _write_adapter(tmp_path, "exa-pack", "exa")
    m = build_import_map(tmp_path)
    assert m["imports"]["exa"] == f.resolve().as_uri()


def test_build_import_map_multiple_extensions(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "exa-pack", "exa")
    _write_adapter(tmp_path, "browserbase-pack", "browserbase")
    m = build_import_map(tmp_path)
    assert set(m["imports"].keys()) == {"exa", "browserbase"}


def test_build_import_map_duplicate_name_raises(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "ext_a", "exa")
    _write_adapter(tmp_path, "ext_b", "exa")
    with pytest.raises(DuplicateAdapterName, match="exa"):
        build_import_map(tmp_path)


def test_parse_usage_marker_picks_last() -> None:
    stdout = (
        "first line\n"
        f"{_USAGE_MARKER_PREFIX} " + json.dumps({"input_tokens": 1, "output_tokens": 1, "model": "wrong"}) + "\n"
        f"{_USAGE_MARKER_PREFIX} " + json.dumps({"input_tokens": 10, "output_tokens": 5, "cached_tokens": 2, "model": "claude-opus-4-7"}) + "\n"
        "trailing\n"
    )
    assert _parse_usage_marker(stdout) == (10, 5, 2, "claude-opus-4-7")


def test_parse_usage_marker_absent_returns_zeros() -> None:
    assert _parse_usage_marker("just some output\nno marker here\n") == (0, 0, 0, None)


def test_parse_usage_marker_malformed_json_returns_zeros() -> None:
    assert _parse_usage_marker(f"{_USAGE_MARKER_PREFIX} not json\n") == (0, 0, 0, None)


def test_run_script_kill_switch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ANTIEK_DISABLE_RUN_SCRIPT", "1")
    assert not is_enabled()
    r = run_script("console.log('x')", project_root=tmp_path)
    assert r.exit_code == -1
    assert "disabled" in r.stderr
    assert not r.ok


def test_run_script_returns_degraded_result_when_deno_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTIEK_DISABLE_RUN_SCRIPT", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    r = run_script("console.log('x')", project_root=tmp_path)
    assert r.exit_code == -1
    assert "preflight failed" in r.stderr
    assert not r.ok


@_deno_required
def test_run_script_hello_world(tmp_path: Path) -> None:
    r = run_script(
        "console.log('hello'); console.log('world');",
        policy=SandboxPolicy.deny_all(),
        timeout_s=10,
        project_root=tmp_path,
    )
    assert r.ok
    assert "hello" in r.stdout and "world" in r.stdout


@_deno_required
def test_run_script_timeout_enforced(tmp_path: Path) -> None:
    r = run_script(
        "while(true){}",
        policy=SandboxPolicy.deny_all(),
        timeout_s=1,
        project_root=tmp_path,
    )
    assert r.wall_timed_out
    assert r.duration_ms < 4000


@_deno_required
def test_run_script_env_filtered(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_SECRET_FOO", "should-not-leak")
    r = run_script(
        "console.log(JSON.stringify(Deno.env.get('ANTIEK_SECRET_FOO')))",
        policy=SandboxPolicy(allow_env=()),
        timeout_s=10,
        project_root=tmp_path,
    )
    assert "should-not-leak" not in r.stdout


@_deno_required
def test_run_script_network_denied_by_default(tmp_path: Path) -> None:
    r = run_script(
        "try { await fetch('https://example.com/'); console.log('REACHED'); } "
        "catch (e) { console.log('BLOCKED:', e.name); }",
        policy=SandboxPolicy.deny_all(),
        timeout_s=10,
        project_root=tmp_path,
    )
    assert "REACHED" not in r.stdout


@_deno_required
def test_run_script_emits_burn_event(tmp_path: Path) -> None:
    ctx = BurnContext(session_id="rs-1", project_root=tmp_path)
    token = set_burn_context(ctx)
    try:
        r = run_script(
            f"console.log('{_USAGE_MARKER_PREFIX} ' + JSON.stringify("
            "{input_tokens: 42, output_tokens: 7, model: 'test-model'}));",
            policy=SandboxPolicy.deny_all(),
            timeout_s=10,
            project_root=tmp_path,
        )
        assert r.ok
    finally:
        reset_burn_context(token)

    recorder = BurnRecorder.for_project(tmp_path)
    rows = recorder.query("SELECT * FROM burn_events WHERE tool_id='run_script'")
    assert len(rows) == 1
    assert rows[0]["input_tokens"] == 42
