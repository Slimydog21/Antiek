"""Tests for scripts/lint_context_injection."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "lint_context_injection",
    Path(__file__).parent.parent / "scripts" / "lint_context_injection.py",
)
assert _SPEC and _SPEC.loader
_lint = importlib.util.module_from_spec(_SPEC)
sys.modules["lint_context_injection"] = _lint
_SPEC.loader.exec_module(_lint)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def test_r1_flags_self_messages_mutation(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "loop.py",
        "class Loop:\n"
        "    def __init__(self):\n"
        "        self._messages = []\n"
        "    def go(self, msg):\n"
        "        self._messages = self._messages + [msg]\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert any(f.rule == "R1" for f in findings)


def test_r1_allowed_in_hooks_subtree(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "hooks" / "fake.py",
        "class X:\n"
        "    def go(self):\n"
        "        self._messages = []\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R1" for f in findings)


def test_r1_flags_msgs_append(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "fmt.py",
        "def add(messages, new):\n"
        "    messages.append(new)\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert any(f.rule == "R1" and "append" in f.message for f in findings)


def test_r2_flags_os_environ_outside_allowlist(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "leak.py",
        "import os\n"
        "def go():\n"
        "    return os.environ.get('SECRET')\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert any(f.rule == "R2" for f in findings)


def test_r2_allowed_in_observability(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "observability" / "thing.py",
        "import os\n"
        "FLAG = os.environ.get('ANTIEK_DISABLE_X')\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R2" for f in findings)


def test_r3_flags_module_level_list(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "globals.py",
        "REGISTERED = []\n"
        "MAP = {}\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    rules = [f.rule for f in findings]
    assert rules.count("R3") == 2


def test_r3_skips_allowed_names(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "ok.py",
        "__all__ = ['x']\n"
        "logger = []\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R3" for f in findings)


def test_r3_skips_constants_file(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "constants.py",
        "SOME_LIST = ['a', 'b']\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R3" for f in findings)


def test_r4_flags_inject_function_without_hook_dispatch(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "sneak.py",
        "def _inject_system_warning(messages):\n"
        "    pass\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert any(f.rule == "R4" and "_inject_system_warning" in f.message for f in findings)


def test_r4_allowed_when_hook_dispatch_present(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "ok.py",
        "from substrate.hooks import HookContext\n"
        "def _inject_thing(ctx: HookContext):\n"
        "    pass\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R4" for f in findings)


def test_r5_flags_system_prompt_assignment(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "agent" / "x.py",
        "def go():\n"
        "    system_prompt = 'You are helpful.'\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert any(f.rule == "R5" for f in findings)


def test_r5_allowed_in_hooks(tmp_path: Path) -> None:
    src = _write(
        tmp_path / "substrate" / "hooks" / "p.py",
        "def go():\n"
        "    system_prompt = 'core'\n",
    )
    findings = _lint.lint_file(src, tmp_path)
    assert not any(f.rule == "R5" for f in findings)


def test_severity_filter(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write(
        tmp_path / "substrate" / "agent" / "x.py",
        "REGISTERED = []\n"
        "def _inject_thing(): pass\n",
    )
    rc = _lint.main([str(tmp_path / "substrate"), "--severity", "high", "--root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "R4" in out
    assert "R3" not in out


def test_json_output(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    _write(
        tmp_path / "substrate" / "agent" / "x.py",
        "def _inject_x(): pass\n",
    )
    import json
    rc = _lint.main([str(tmp_path / "substrate"), "--json", "--root", str(tmp_path)])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert any(f["rule"] == "R4" for f in data)


def test_exit_code_always_zero(tmp_path: Path) -> None:
    _write(
        tmp_path / "substrate" / "agent" / "x.py",
        "def _inject_evil(): pass\n",
    )
    assert _lint.main([str(tmp_path / "substrate"), "--root", str(tmp_path)]) == 0


def test_unparseable_file_does_not_crash(tmp_path: Path) -> None:
    bad = tmp_path / "substrate" / "broken.py"
    bad.parent.mkdir(parents=True)
    bad.write_text("def x(:\n  pass\n")
    findings = _lint.lint_file(bad, tmp_path)
    assert findings == []
