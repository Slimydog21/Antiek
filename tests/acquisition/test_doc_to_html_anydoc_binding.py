"""Office documents must convert with no anydoc CLI anywhere on the host.

`ANYDOC_BIN` resolves at import time to `shutil.which("anydoc")` or, failing
that, the bare string `"anydoc"`. Nothing is on PATH on the production host —
`infrastructure/ansible/playbooks/deploy.yml:108` installs the *binding* via the
`docs` extra and never the CLI — so `_run_anydoc` raised `FileNotFoundError`,
returned None, and every Office/ODF/RTF/CSV upload fell through to the PDF and
OCR arms that cannot read them.

It worked on developer machines, which is exactly why it survived: `anydoc` and
`docling` sit in `~/.local/bin` here. Every test below therefore pins
`ANYDOC_BIN` and `DOCLING_BIN` to paths that cannot exist, so a passing run
proves the in-process binding did the work and not a CLI that production does
not have.

Fixtures are built by hand rather than with python-docx or openpyxl, neither of
which is a dependency of this project. They are real containers — anydoc parses
them, it is not stubbed.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from acquisition.doc_to_html import converter

_OOXML = "http://schemas.openxmlformats.org/"


def _docx(text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Types xmlns="{_OOXML}package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{_OOXML}package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{_OOXML}officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        zf.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<w:document xmlns:w="{_OOXML}wordprocessingml/2006/main">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>",
        )
    return buf.getvalue()


def _xlsx(rows: tuple[tuple[str, ...], ...]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Types xmlns="{_OOXML}package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            "</Types>",
        )
        zf.writestr(
            "_rels/.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{_OOXML}package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{_OOXML}officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        zf.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0"?><workbook xmlns="{_OOXML}spreadsheetml/2006/main" '
            f'xmlns:r="{_OOXML}officeDocument/2006/relationships">'
            '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{_OOXML}package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{_OOXML}officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        body = "".join(
            f'<row r="{i + 1}">'
            + "".join(
                f'<c r="{chr(65 + j)}{i + 1}" t="inlineStr"><is><t>{cell}</t></is></c>'
                for j, cell in enumerate(row)
            )
            + "</row>"
            for i, row in enumerate(rows)
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0"?><worksheet xmlns="{_OOXML}spreadsheetml/2006/main">'
            f"<sheetData>{body}</sheetData></worksheet>",
        )
    return buf.getvalue()


@pytest.fixture(autouse=True)
def _no_cli_anywhere(monkeypatch: pytest.MonkeyPatch) -> None:
    """Production's posture: the binding is installed, no CLI exists.

    Both names are resolved at import time, so pinning the module attributes is
    what makes this real — clearing PATH alone would not move them.
    """
    monkeypatch.setattr(converter, "ANYDOC_BIN", "/nonexistent/bin/anydoc")
    monkeypatch.setattr(converter, "DOCLING_BIN", "/nonexistent/bin/docling")
    monkeypatch.setenv("PATH", "/nonexistent")


@pytest.mark.parametrize(
    "name,payload,fmt,expected_fragment",
    [
        ("report.docx", _docx("Antiek converts this without a CLI"), "docx", "without a CLI"),
        ("figures.xlsx", _xlsx((("region", "revenue"), ("emea", "42"))), "xlsx", "revenue"),
        ("rows.csv", b"name,value\nalpha,1\nbeta,2\n", "csv", "alpha"),
    ],
    ids=["docx", "xlsx", "csv"],  # payloads are binary; unnamed ids are unreadable
)
def test_converts_through_the_binding_with_no_cli_present(
    tmp_path: Path, name: str, payload: bytes, fmt: str, expected_fragment: str
) -> None:
    asset = tmp_path / name
    asset.write_bytes(payload)

    markdown, engine = converter.convert_to_markdown_with_engine(str(asset), fmt=fmt)

    assert engine == "anydoc_binding", f"{name} did not go through the binding"
    assert markdown.strip(), f"{name} converted to empty markdown"
    assert expected_fragment in markdown, f"{name} lost its content: {markdown[:200]!r}"


def test_the_cli_arm_really_is_unavailable_in_these_tests() -> None:
    """Control.

    If `ANYDOC_BIN` still pointed at a working CLI, every assertion above would
    pass for the wrong reason — which is the shape of failure this repo has
    already shipped once. Prove the CLI arm returns None under the fixture.
    """
    assert converter.ANYDOC_BIN == "/nonexistent/bin/anydoc"
    assert (
        converter._run_anydoc(
            Path("/nonexistent/file.docx"), fmt="docx", timeout=5, max_output=1024
        )
        is None
    )


def test_the_docs_extra_is_actually_installed() -> None:
    """Guard: this whole file is vacuous without the binding.

    CI installed `.[dev,arxiv,pdf,urls,embedding,youtube,rss]` while the
    production deploy installs `[pdf,urls,embedding,docs,turbopuffer_shadow]`.
    The `docs` extra — firecrawl-anydoc — was in prod and not in CI, so no test
    could ever exercise the conversion path production actually runs, and the
    three tests above failed on arrival with "anydoc, docling failed".

    This asserts the import DIRECTLY rather than using `importorskip`. A skip
    would be worse than the bug: the suite would go green on a machine missing
    the binding, and the next person to drop `docs` from the extras list would
    get a clean board while every Office upload broke in production. Failing
    loudly is the point.
    """
    from importlib import import_module

    try:
        import_module("anydoc")
    except ModuleNotFoundError:  # pragma: no cover - the failure this guards
        raise AssertionError(
            "firecrawl-anydoc is not installed. Add the 'docs' extra: "
            "pip install -e '.[...,docs]'. Production installs it via "
            "infrastructure/ansible/playbooks/deploy.yml; CI must match or this "
            "file measures nothing."
        ) from None
