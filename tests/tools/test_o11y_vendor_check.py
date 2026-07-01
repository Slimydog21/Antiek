from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tools.lint.o11y_vendor_check import find_violations


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_clean_tree_has_no_violations(tmp_path: Path) -> None:
    assert find_violations(tmp_path) == []


def test_flags_forbidden_submodule_import(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app.py", "import sentry_sdk.integrations.flask\n")

    violations = find_violations(tmp_path)

    assert violations == ["src/app.py:1 — sentry_sdk (§16)"]


def test_flags_opentelemetry_dotted_import(tmp_path: Path) -> None:
    _write(tmp_path / "src" / "app.py", "from opentelemetry.exporter.otlp import X\n")

    violations = find_violations(tmp_path)

    assert violations == ["src/app.py:1 — opentelemetry (§16)"]


def test_flags_direct_python_dependency_forms(tmp_path: Path) -> None:
    _write(tmp_path / "requirements.txt", "datadog==1.0\n")
    _write(
        tmp_path / "pyproject.toml",
        """
[project]
dependencies = [
  "sentry-sdk @ git+https://example.invalid/sentry-sdk.git",
]

[tool.poetry.dependencies]
python = "^3.14"
datadog = "^1.0"
""".lstrip(),
    )

    violations = find_violations(tmp_path)

    assert "requirements.txt:1 — datadog (§16)" in violations
    assert "pyproject.toml:3 — sentry-sdk (§16)" in violations
    assert "pyproject.toml:8 — datadog (§16)" in violations


def test_flags_direct_js_dependency(tmp_path: Path) -> None:
    package_json = {
        "dependencies": {
            "@sentry/browser": "latest",
        },
    }
    _write(tmp_path / "apps" / "x" / "package.json", json.dumps(package_json, indent=2))

    violations = find_violations(tmp_path)

    assert violations == ["apps/x/package.json:3 — @sentry/browser (§16)"]


def test_inline_comment_does_not_count_as_dependency(tmp_path: Path) -> None:
    _write(
        tmp_path / "requirements.txt",
        "httpx>=0.27  # replaces datadog\n"
        "\"httpx>=0.27\",  # replaces sentry-sdk\n",
    )

    assert find_violations(tmp_path) == []


def test_skips_venv_site_packages(tmp_path: Path) -> None:
    _write(
        tmp_path / ".venv" / "lib" / "site-packages" / "foo.py",
        "import statsd\n",
    )

    assert find_violations(tmp_path) == []


def test_benign_prefix_lookalikes_are_not_flagged(tmp_path: Path) -> None:
    _write(
        tmp_path / "src" / "app.py",
        "import prometheusish\n"
        "import sentry_sdkish\n",
    )

    assert find_violations(tmp_path) == []
