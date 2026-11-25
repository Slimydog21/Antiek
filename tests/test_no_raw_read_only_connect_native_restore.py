"""The native restore verifier's read-only open is the lint's sole exception."""

from pathlib import Path

import pytest

from tools.lints.no_raw_read_only_connect import scan_file

VERIFIER = "tools/deploy/backup_native_restore_verify.py"
CALL = "duckdb.connect(str(path), read_only=True, config=_DUCKDB_CONFIG)"


def _scan(tmp_path: Path, source: str, *, relative_path: str = VERIFIER) -> list[int]:
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return [violation.line for violation in scan_file(path)]


def test_real_native_verifier_has_one_exempt_open() -> None:
    path = Path(__file__).resolve().parents[1] / VERIFIER
    assert scan_file(path) == []


def test_exact_open_is_exempt_only_once_in_observer(tmp_path: Path) -> None:
    source = f"def _observe_native(path):\n    {CALL}\n    {CALL}\n"
    assert _scan(tmp_path, source) == [3]


@pytest.mark.parametrize(
    "source,relative_path,expected_lines",
    [
        (f"def other(path):\n    {CALL}\n", VERIFIER, [2]),
        (f"class Checker:\n    def _observe_native(self, path):\n        {CALL}\n", VERIFIER, [3]),
        (
            f"def _observe_native(path):\n    def nested():\n        {CALL}\n",
            VERIFIER,
            [3],
        ),
        (f"def _observe_native(path):\n    {CALL}\n", "tools/deploy/other.py", [2]),
        (
            f"def _observe_native(path):\n    {CALL}\n",
            "eviltools/deploy/backup_native_restore_verify.py",
            [2],
        ),
        (
            "def _observe_native(path):\n    duckdb.connect(str(path), read_only=True)\n",
            VERIFIER,
            [2],
        ),
        (
            "def _observe_native(path):\n"
            "    duckdb.connect(str(path), read_only=True, config={})\n",
            VERIFIER,
            [2],
        ),
        (
            "def _observe_native(path):\n"
            "    duckdb.connect(other_path, read_only=True, config=_DUCKDB_CONFIG)\n",
            VERIFIER,
            [2],
        ),
    ],
)
def test_other_raw_reads_remain_violations(
    tmp_path: Path, source: str, relative_path: str, expected_lines: list[int]
) -> None:
    assert _scan(tmp_path, source, relative_path=relative_path) == expected_lines


def test_other_function_still_flags_with_exempt_call_present(tmp_path: Path) -> None:
    source = f"def _observe_native(path):\n    {CALL}\n\ndef other(path):\n    {CALL}\n"
    assert _scan(tmp_path, source) == [5]
