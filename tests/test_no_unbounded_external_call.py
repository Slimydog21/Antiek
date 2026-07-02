"""Tests for tools.lints.no_unbounded_external_call."""

from __future__ import annotations

import json
from pathlib import Path

from tools.lints.baseline import SCHEMA_VERSION, BaselineSchema, ViolationKey
from tools.lints.cli_with_baseline import main as baseline_main
from tools.lints.no_unbounded_external_call import main, scan_file


def test_timeoutless_external_calls_are_flagged_and_main_exits_1(
    tmp_path: Path,
) -> None:
    sample = tmp_path / "violations.py"
    sample.write_text(
        "\n".join(
            [
                "import httpx",
                "import requests",
                "import socket",
                "from httpx import Client as HClient",
                "from requests import get as rget",
                "",
                "def f():",
                "    httpx.get('https://example.com')",
                "    requests.post('https://example.com')",
                "    socket.create_connection(('example.com', 443))",
                "    HClient()",
                "    rget('https://example.com')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    violations = scan_file(sample)
    assert {v.call for v in violations} == {
        "httpx.get",
        "requests.post",
        "socket.create_connection",
        "HClient",
        "rget",
    }
    assert main([str(sample)]) == 1


def test_external_calls_with_timeout_are_clean(tmp_path: Path) -> None:
    sample = tmp_path / "clean.py"
    sample.write_text(
        "\n".join(
            [
                "import httpx",
                "import requests",
                "import socket",
                "from httpx import Client as HClient",
                "from requests import get as rget",
                "",
                "def f():",
                "    httpx.get('https://example.com', timeout=20.0)",
                "    requests.post('https://example.com', timeout=20.0)",
                "    socket.create_connection(('example.com', 443), timeout=20.0)",
                "    socket.create_connection(('example.com', 443), 20.0)",
                "    HClient(timeout=20.0)",
                "    rget('https://example.com', timeout=20.0)",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    assert scan_file(sample) == []
    assert main([str(sample)]) == 0


def test_baselined_finding_does_not_refail(tmp_path: Path) -> None:
    sample = tmp_path / "legacy.py"
    sample.write_text(
        "\n".join(
            [
                "import httpx",
                "",
                "def f():",
                "    httpx.get('https://example.com')",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    violation = scan_file(sample)[0]
    baseline_file = tmp_path / "baseline.json"
    schema = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint="no_unbounded_external_call",
        generated_at="",
        violations=[
            ViolationKey(
                path=str(violation.path),
                line=violation.line,
                col=violation.col,
                kind=f"unbounded-external-call:{violation.call}",
            )
        ],
    )
    baseline_file.write_text(json.dumps(schema.to_json()), encoding="utf-8")

    rc = baseline_main(
        [
            "enforce",
            "unbounded_external_call",
            "--paths",
            str(sample),
            "--baseline-file",
            str(baseline_file),
        ]
    )
    assert rc == 0
