from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.cli import __main__ as unified
from substrate.cli import projections


def test_mode_is_required_and_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as missing:
        projections.main([])
    assert missing.value.code == 2
    with pytest.raises(SystemExit) as both:
        projections.main(["--dry-run", "--apply"])
    assert both.value.code == 2


def test_help_and_unified_dispatch(capsys: pytest.CaptureFixture[str]) -> None:
    assert unified.main(["--help"]) == 0
    assert "projections" in capsys.readouterr().out
    with pytest.raises(SystemExit) as help_exit:
        unified.main(["projections", "--help"])
    assert help_exit.value.code == 0
    assert "--lease-seconds" in capsys.readouterr().out


def test_json_dry_run_and_lease_seconds_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class Report:
        candidates = would_convert = conversion_failed = 0

        def canonical_json_bytes(self) -> bytes:
            return b'{"dry_run":true}'

    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return Report()

    monkeypatch.setattr(projections, "backfill_projections", fake)
    assert (
        projections.main(
            [
                "--dry-run",
                "--json",
                "--db-path",
                str(tmp_path / "db"),
                "--source-object-root",
                str(tmp_path / "source"),
                "--html-object-root",
                str(tmp_path / "html"),
                "--lease-seconds",
                "12.5",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == {"dry_run": True}
    assert seen["apply"] is False and seen["lease_seconds"] == 12.5


def test_apply_human_output_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class Report:
        plan_id = "hpb-test"
        candidates = 2
        would_convert = 1
        conversion_failed = 1

    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return Report()

    monkeypatch.setattr(projections, "backfill_projections", fake)
    assert (
        projections.main(
            [
                "--apply",
                "--db-path",
                str(tmp_path / "db"),
                "--source-object-root",
                str(tmp_path / "source"),
                "--html-object-root",
                str(tmp_path / "html"),
                "--worker-id",
                "cli-worker",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == ("plan hpb-test: 2 candidates, 1 convertible, 1 failed\n")
    assert seen["apply"] is True and seen["worker_id"] == "cli-worker"


def test_pyproject_entrypoint_is_unified() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    assert 'antiek = "substrate.cli.__main__:main"' in pyproject.read_text()
