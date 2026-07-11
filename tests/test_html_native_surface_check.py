from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from tools.lint.html_native_surface_check import (
    ConfigurationError,
    Finding,
    load_allowlist,
    scan_bundle,
    scan_source,
    validate_allowlist,
)

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tools/lint/html_native_surface_check.py"


def source_tree(tmp_path: Path, text: str, name: str = "planted.tsx") -> Path:
    target = tmp_path / "apps/reading/src" / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ('import { PdfViewer } from "./PdfViewer";', "pdfviewer-runtime"),
        ("const panel = new PdfViewer(props);", "pdfviewer-runtime"),
        ("return <PdfViewer document={doc} />;", "pdfviewer-runtime"),
        ('import * as pdfjs from "pdfjs-dist";', "pdfjs-runtime"),
        ('worker.src = "pdf.worker.js";', "pdfjs-runtime"),
        ("const engine = PDF.js;", "pdfjs-runtime"),
        ('return <object data="/paper.pdf" />;', "pdf-embed-sink"),
        ('return <embed type="application/pdf" src={url} />;', "pdf-embed-sink"),
        ('return <iframe src="blob:pdf-document" />;', "pdf-embed-sink"),
        ('navigate("/wrestle/abc");', "direct-wrestle-route"),
        ('window.location.href = "/wrestle";', "direct-wrestle-route"),
        ('return <a href="/wrestle/42">old</a>;', "direct-wrestle-route"),
        ('navigate("/wrest" + "le/42");', "direct-wrestle-route"),
        ('navigate(`/wrest${"le"}/42`);', "direct-wrestle-route"),
        ('location.href = "/view" + ".pdf";', "pdf-navigation"),
    ],
)
def test_forbidden_source_forms(tmp_path: Path, text: str, rule: str) -> None:
    source_tree(tmp_path, text)
    assert rule in {finding.rule for finding in scan_source(tmp_path)}


def test_pdf_blob_dataflow_to_navigation_and_sink(tmp_path: Path) -> None:
    source_tree(
        tmp_path,
        """const pdf = new Blob([bytes], {type: "application/pdf"});
const url = URL.createObjectURL(pdf);
window.open(url);
return <iframe src={url} />;""",
    )
    rules = [finding.rule for finding in scan_source(tmp_path)]
    assert rules.count("pdf-blob-navigation") == 2


def test_pdf_variable_flows_into_jsx_dom_and_blob_mime(tmp_path: Path) -> None:
    source_tree(
        tmp_path,
        """const pdfUrl = "/paper.pdf";
const mime = "application/pdf";
const pdf = new Blob([bytes], {type: mime});
const objectUrl = URL.createObjectURL(pdf);
const frame = document.createElement("iframe");
frame.src = pdfUrl;
return <object data={pdfUrl} />;""",
    )
    rules = [finding.rule for finding in scan_source(tmp_path)]
    assert rules.count("pdf-embed-sink") == 2
    assert "pdf-blob-object-url" in rules


def test_cross_file_pdf_blob_object_url_cannot_hide(tmp_path: Path) -> None:
    source_tree(
        tmp_path,
        'export const pdf = new Blob([bytes], {type: "application/pdf"});\n'
        "export const url = URL.createObjectURL(pdf);",
        "pdfUrl.ts",
    )
    source_tree(tmp_path, 'import { url } from "./pdfUrl"; window.open(url);', "viewer.ts")
    assert "pdf-blob-object-url" in {finding.rule for finding in scan_source(tmp_path)}


def test_three_file_pdf_blob_chain_fails_at_authoritative_source(tmp_path: Path) -> None:
    source_tree(
        tmp_path,
        'export const pdf = new Blob([bytes], {type: "application/pdf"});',
        "blob.ts",
    )
    source_tree(
        tmp_path,
        'import { pdf } from "./blob"; export const url = URL.createObjectURL(pdf);',
        "url.ts",
    )
    source_tree(tmp_path, 'import { url } from "./url"; window.open(url);', "view.ts")
    assert "pdf-blob-source" in {finding.rule for finding in scan_source(tmp_path)}


def test_rejection_does_not_mask_executable_code_on_same_line(tmp_path: Path) -> None:
    source_tree(
        tmp_path,
        'new PdfViewer(); if (kind === "PdfViewer") return "PdfViewer is deprecated; use HtmlReader";',
    )
    findings = scan_source(tmp_path)
    assert len(findings) == 1
    assert findings[0].rule == "pdfviewer-runtime"


@pytest.mark.parametrize(
    "text",
    [
        '// PdfViewer pdfjs <object data="x.pdf"> /wrestle',
        '/* docs: use PDF.js and /wrestle, never <iframe src="x.pdf"> */',
        'if (item.panel_kind === "PdfViewer") return "PdfViewer is deprecated; use HtmlReader";',
        'const audio = new Blob([bytes], {type: "audio/mpeg"}); URL.createObjectURL(audio);',
        'const archive = new Blob([bytes], {type: "application/zip"}); download(archive);',
        'return <iframe src="https://example.test/page" />;',
        'return <object type="image/svg+xml" data="icon.svg" />;',
        'acquireAndArchive("paper.pdf");',
    ],
)
def test_legitimate_source_is_clean(tmp_path: Path, text: str) -> None:
    source_tree(tmp_path, text)
    assert scan_source(tmp_path) == []


def test_tests_stories_and_fixtures_are_out_of_scope(tmp_path: Path) -> None:
    for name in ("bad.test.ts", "bad.stories.tsx", "fixture.spec.js"):
        source_tree(tmp_path, 'new PdfViewer(); navigate("/wrestle")', name)
    assert scan_source(tmp_path) == []


def test_bundle_residue_and_safe_rejection(tmp_path: Path) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.js").write_text(
        'throw new Error("PdfViewer is deprecated; use HtmlReader");\nPDFPageProxy; pdfjs.getDocument(x)',
        encoding="utf-8",
    )
    (bundle / "pdf-worker-a1.js").write_text("", encoding="utf-8")
    rules = {finding.rule for finding in scan_bundle(bundle)}
    assert rules == {"bundle-pdf-residue", "bundle-pdfjs-residue", "bundle-pdf-render-residue"}


def test_minified_bundle_rejection_branch_is_clean_but_cannot_mask_runtime(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.js").write_text(
        'function f(e){if(e.panel_kind==="PdfViewer")return"PdfViewer is deprecated; use HtmlReader"}',
        encoding="utf-8",
    )
    assert scan_bundle(bundle) == []
    (bundle / "index.js").write_text(
        'new PdfViewer();function f(e){if(e.panel_kind==="PdfViewer")return"PdfViewer is deprecated; use HtmlReader"}',
        encoding="utf-8",
    )
    assert [finding.rule for finding in scan_bundle(bundle)] == ["bundle-pdfviewer-residue"]


def test_minified_bundle_rejects_compiled_pdf_sink_and_blob_flow(tmp_path: Path) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.js").write_text(
        'jsx("iframe",{src:"/paper.pdf"});new Blob([x],{type:"application/pdf"});createObjectURL(x)',
        encoding="utf-8",
    )
    assert {finding.rule for finding in scan_bundle(bundle)} == {
        "bundle-pdf-blob-residue",
        "bundle-pdf-embed-residue",
    }


def test_minified_bundle_rejects_dynamic_pdf_iframe_tag(tmp_path: Path) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.js").write_text(
        'const Tag="iframe";jsx(Tag,{src:"/paper.pdf"})', encoding="utf-8"
    )
    assert "bundle-pdf-embed-residue" in {finding.rule for finding in scan_bundle(bundle)}


def test_split_bundle_pdf_blob_flow_cannot_hide(tmp_path: Path) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "pdf.js").write_text(
        'export const p=new Blob([x],{type:"application/pdf"})', encoding="utf-8"
    )
    (bundle / "viewer.js").write_text("const u=createObjectURL(p);window.open(u)", encoding="utf-8")
    assert "bundle-pdf-blob-residue" in {finding.rule for finding in scan_bundle(bundle)}


def test_minified_ternary_rejection_is_not_runtime(tmp_path: Path) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.js").write_text(
        'const x=e.panel_kind==="PdfViewer"?"PdfViewer is deprecated; use HtmlReader":null',
        encoding="utf-8",
    )
    assert scan_bundle(bundle) == []


def valid_entry(finding: Finding, **updates: str) -> dict[str, str]:
    entry = {
        "file": finding.file,
        "rule": finding.rule,
        "fingerprint": finding.fingerprint,
        "reason": "Temporary compatibility boundary",
        "owner": "reading-platform",
        "review_condition": "Remove after migration",
    }
    entry.update(updates)
    return entry


def planted_finding(tmp_path: Path) -> Finding:
    source_tree(tmp_path, 'navigate("/wrestle");')
    return scan_source(tmp_path)[0]


def test_exact_fingerprint_covers_only_one_finding(tmp_path: Path) -> None:
    source_tree(tmp_path, 'navigate("/wrestle");\nnavigate("/wrestle");')
    findings = scan_source(tmp_path)
    remaining = validate_allowlist([valid_entry(findings[0])], findings, tmp_path)
    assert remaining == [findings[1]]
    assert findings[0].fingerprint != findings[1].fingerprint


@pytest.mark.parametrize(
    "mutate, message",
    [
        (lambda e: e.update(extra="x"), "unknown fields"),
        (lambda e: e.pop("owner"), "missing fields"),
        (lambda e: e.pop("reason"), "missing fields"),
        (lambda e: e.pop("review_condition"), "exactly one"),
        (lambda e: e.update(expires="2030-01-01"), "exactly one"),
        (lambda e: e.update(file="apps/reading/src/*.tsx"), "literal"),
        (lambda e: e.update(file="apps/reading/src/{one,two}.tsx"), "literal"),
        (lambda e: e.update(file="apps/reading/src/missing.tsx"), "missing file"),
        (lambda e: e.update(fingerprint="not-a-fingerprint"), "lowercase hexadecimal"),
        (lambda e: e.update(fingerprint="0" * 64), "fingerprint mismatch"),
        (lambda e: e.update(expires="not-a-date", review_condition=None), "exactly one"),
        (lambda e: e.update(expires="2020-01-01", review_condition=None), "exactly one"),
    ],
)
def test_malformed_allowlist(tmp_path: Path, mutate, message: str) -> None:
    finding = planted_finding(tmp_path)
    entry = valid_entry(finding)
    mutate(entry)
    with pytest.raises(ConfigurationError, match=message):
        validate_allowlist([entry], [finding], tmp_path)


def test_expired_entry(tmp_path: Path) -> None:
    finding = planted_finding(tmp_path)
    entry = valid_entry(finding)
    entry.pop("review_condition")
    entry["expires"] = (date.today() - timedelta(days=1)).isoformat()
    with pytest.raises(ConfigurationError, match="expired"):
        validate_allowlist([entry], [finding], tmp_path)


def test_duplicate_and_stale_entries(tmp_path: Path) -> None:
    finding = planted_finding(tmp_path)
    entry = valid_entry(finding)
    with pytest.raises(ConfigurationError, match="duplicates"):
        validate_allowlist([entry, entry.copy()], [finding], tmp_path)
    with pytest.raises(ConfigurationError, match="stale"):
        validate_allowlist([entry], [], tmp_path)


def test_wrong_file_fingerprint(tmp_path: Path) -> None:
    finding = planted_finding(tmp_path)
    other = source_tree(tmp_path, "export {};", "other.ts")
    entry = valid_entry(finding, file=other.relative_to(tmp_path).as_posix())
    with pytest.raises(ConfigurationError, match="different file"):
        validate_allowlist([entry], [finding], tmp_path)


def test_allowlist_loader_rejects_non_array(tmp_path: Path) -> None:
    path = tmp_path / "allow.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="JSON array"):
        load_allowlist(path)


def test_current_tree_is_clean_with_checked_in_allowlist() -> None:
    findings = scan_source(REPO)
    remaining = validate_allowlist(
        load_allowlist(REPO / "tools/lint/html_native_surface_allowlist.json"), findings, REPO
    )
    assert remaining == []
    assert len(findings) == 4


@pytest.mark.parametrize(
    ("source", "allowlist", "expected"),
    [("export {};", [], 0), ("new PdfViewer();", [], 1), ("export {};", {}, 2)],
)
def test_cli_exit_codes(tmp_path: Path, source: str, allowlist: object, expected: int) -> None:
    source_tree(tmp_path, source)
    path = tmp_path / "allow.json"
    path.write_text(json.dumps(allowlist), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(tmp_path), "--allowlist", str(path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == expected


def test_diagnostics_are_deterministic_path_line(tmp_path: Path) -> None:
    source_tree(tmp_path, "\nnew PdfViewer();")
    finding = scan_source(tmp_path)[0]
    assert finding.message().startswith("apps/reading/src/planted.tsx:2: pdfviewer-runtime:")
