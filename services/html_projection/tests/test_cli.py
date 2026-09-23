"""``python -m services.html_projection.cli`` — Markdown through the engine.

What the CLI must guarantee for a committed render to mean anything: the same
source yields the same bytes (so ``cmp`` is a valid staleness check), the page
passes the zero-script gate even when the source tries not to, the wheel style
only swaps the stylesheet, and the leading H1 becomes the title once rather
than twice.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from services.html_projection import cli, gate
from services.html_projection.island import extract_island

_REPO = Path(__file__).resolve().parents[3]

SAMPLE = """\
# Sample document

Companion: [thesis](./thesis.md).

## Rules

| State | Render as |
| --- | --- |
| Loading | `Loading…` |

- one
- two

```
code <b>here</b>
```

Text with <script>alert(1)</script> and a javascript:alert(2) link.
"""


def _strip_style(html: str) -> str:
    return re.sub(r"<style>.*?</style>", "", html, flags=re.DOTALL)


def test_render_is_deterministic_and_script_free() -> None:
    first = cli.render_markdown(SAMPLE, document_id="sample.md")
    second = cli.render_markdown(SAMPLE, document_id="sample.md")
    assert first == second
    assert gate.find_violations(first) == []
    assert "alert(1)" not in first.replace("&lt;script&gt;alert(1)&lt;/script&gt;", "")
    assert "<h1 class=\"antiek-doc-title\">Sample document</h1>" in first
    # The leading H1 is the title, not also the first heading block (the
    # third copy of the text is the data island, which round-trips the title).
    assert first.count("<h1") == 1
    assert 'class="antiek-heading">Sample document' not in first
    assert "Rules" in first and "<table" in first and "<li" in first


def test_style_only_swaps_the_stylesheet() -> None:
    antiek = cli.render_markdown(SAMPLE, document_id="sample.md", style="antiek")
    slate = cli.render_markdown(SAMPLE, document_id="sample.md", style="slate")
    assert antiek != slate
    assert _strip_style(antiek) == _strip_style(slate)
    assert extract_island(antiek) == extract_island(slate)


def test_split_title_only_lifts_a_leading_h1() -> None:
    assert cli.split_title("# Title\n\nBody") == ("Title", "\nBody")
    assert cli.split_title("Intro\n\n# Not first\n") == (None, "Intro\n\n# Not first\n")
    assert cli.split_title("## Second level\n") == (None, "## Second level\n")


def test_unknown_style_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = tmp_path / "x.md"
    src.write_text("# X\n\nbody\n", encoding="utf-8")
    assert cli.main([str(src), "--style", "no-such-style"]) == 2
    assert "unknown style" in capsys.readouterr().err
    assert cli.main([str(tmp_path / "missing.md")]) == 2


def test_module_entry_point_writes_the_page_to_stdout(tmp_path: Path) -> None:
    src = tmp_path / "doc.md"
    src.write_text(SAMPLE, encoding="utf-8")
    runs = [
        subprocess.run(
            [sys.executable, "-m", "services.html_projection.cli", str(src), "--document-id", "doc.md"],
            cwd=_REPO,
            capture_output=True,
            check=True,
        ).stdout
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
    assert runs[0] == cli.render_markdown(SAMPLE, document_id="doc.md").encode("utf-8")
    assert runs[0].startswith(b"<!DOCTYPE html>")
