from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools.lint.capability_guidance_check import validate

REPO = Path(__file__).resolve().parent.parent


def _fixture(tmp_path: Path, *, route: str = "/settings", anchor: str = "present") -> Path:
    catalog = tmp_path / "apps/reading/src/workspace/capabilityGuidanceLinks.ts"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(
        'export const capabilityGuidanceLinks = {\n  example: "/settings#present",\n};\n',
        encoding="utf-8",
    )
    settings = tmp_path / "apps/reading/src/modes/Settings/index.tsx"
    settings.parent.mkdir(parents=True)
    settings.write_text(f'<section id="{anchor}" />', encoding="utf-8")
    app = tmp_path / "apps/reading/src/App.tsx"
    app.write_text(f'<Route path="{route}" element={{<Settings />}} />', encoding="utf-8")
    return tmp_path


def test_accepts_a_served_settings_anchor(tmp_path: Path) -> None:
    assert validate(_fixture(tmp_path)) == ()


def test_rejects_missing_route_and_anchor(tmp_path: Path) -> None:
    errors = validate(_fixture(tmp_path, route="/preferences", anchor="absent"))
    assert errors == (
        "apps/reading/src/App.tsx: /settings route is not served",
        "apps/reading/src/workspace/capabilityGuidanceLinks.ts: example targets missing Settings anchor: present",
    )


def test_rejects_repository_docs_target_anywhere_in_reading_source(tmp_path: Path) -> None:
    repo = _fixture(tmp_path)
    source = repo / "apps/reading/src/example.tsx"
    source.write_text('const href = "/docs/htmlspec/not-served.html";', encoding="utf-8")
    assert validate(repo)[-1] == (
        "apps/reading/src/example.tsx: repository-only /docs target is not a served app route"
    )


def test_current_catalog_destinations_are_reachable() -> None:
    result = subprocess.run(
        [sys.executable, "tools/lint/capability_guidance_check.py", str(REPO)],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "typed Settings destinations are reachable" in result.stdout
