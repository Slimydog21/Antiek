#!/usr/bin/env python3
"""Block reintroduction of native-PDF surfaces in the Reading application.

The checker deliberately uses only the standard library.  It is conservative about
what constitutes PDF evidence: generic blobs, downloads, iframes, and vector assets
are not violations by themselves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SOURCE_SUFFIXES = {".ts", ".tsx", ".js", ".jsx"}
BUNDLE_SUFFIXES = {".js", ".mjs", ".cjs", ".css"}
DEPRECATION_MESSAGE = "PdfViewer is deprecated; use HtmlReader"
ALLOWED_KEYS = {"file", "rule", "fingerprint", "reason", "owner", "expires", "review_condition"}
REQUIRED_KEYS = {"file", "rule", "fingerprint", "reason", "owner"}


class ConfigurationError(ValueError):
    """An invalid allowlist or invocation (exit status 2)."""


@dataclass(frozen=True, order=True)
class Finding:
    file: str
    line: int
    rule: str
    evidence: str

    @property
    def fingerprint(self) -> str:
        normalized = " ".join(self.evidence.split())
        material = f"{self.file}\0{self.line}\0{self.rule}\0{normalized}".encode()
        return hashlib.sha256(material).hexdigest()

    def message(self) -> str:
        return f"{self.file}:{self.line}: {self.rule}: {self.evidence.strip()}"


def _mask_comments(text: str) -> str:
    """Replace JS comments with spaces while preserving strings and line offsets."""
    out = list(text)
    i = 0
    state = "code"
    quote = ""
    while i < len(text):
        ch = text[i]
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if state == "code":
            if ch in "'\"`":
                state, quote = "string", ch
            elif ch == "/" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 1
                state = "line"
            elif ch == "/" and nxt == "*":
                out[i] = out[i + 1] = " "
                i += 1
                state = "block"
        elif state == "string":
            if ch == "\\":
                i += 1
            elif ch == quote:
                state = "code"
        elif state == "line":
            if ch == "\n":
                state = "code"
            else:
                out[i] = " "
        else:
            if ch == "*" and nxt == "/":
                out[i] = out[i + 1] = " "
                i += 1
                state = "code"
            elif ch != "\n":
                out[i] = " "
        i += 1
    return "".join(out)


def _fold_literal_concatenations(text: str) -> str:
    """Fold adjacent static string literals while preserving byte offsets."""
    pattern = re.compile(r"([\"'])([^\"'\n]*)\1\s*\+\s*([\"'])([^\"'\n]*)\3")
    while True:
        match = pattern.search(text)
        if match is None:
            return text
        folded = f"{match.group(1)}{match.group(2)}{match.group(4)}{match.group(1)}"
        replacement = folded + " " * (len(match.group(0)) - len(folded))
        text = text[: match.start()] + replacement + text[match.end() :]


def _fold_static_template_interpolations(text: str) -> str:
    pattern = re.compile(r"\$\{\s*([\"'])([^\"'\n]*)\1\s*\}")
    while True:
        match = pattern.search(text)
        if match is None:
            return text
        value = match.group(2)
        replacement = value + " " * (len(match.group(0)) - len(value))
        text = text[: match.start()] + replacement + text[match.end() :]


def _source_files(root: Path) -> Iterable[Path]:
    source = root / "apps/reading/src"
    if not source.is_dir():
        raise ConfigurationError(f"source directory does not exist: {source}")
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        low = path.name.lower()
        if re.search(r"(?:^|\.)((?:spec|test|stories?|fixture))\.", low):
            continue
        if any(
            part in {"__tests__", "test", "tests", "stories", "fixtures"} for part in path.parts
        ):
            continue
        yield path


def _add(findings: list[Finding], rel: str, rule: str, text: str, match: re.Match[str]) -> None:
    line = text.count("\n", 0, match.start()) + 1
    evidence = text.splitlines()[line - 1].strip() if text.splitlines() else match.group(0)
    findings.append(Finding(rel, line, rule, evidence[:300]))


def _matches(pattern: str, text: str, flags: int = re.IGNORECASE) -> Iterable[re.Match[str]]:
    return re.finditer(pattern, text, flags)


def _mask_source_rejection(text: str) -> str:
    pattern = re.compile(
        r"if\s*\([^\n)]*[\"']PdfViewer[\"'][^\n)]*\)\s*"
        r"return\s*[\"']PdfViewer is deprecated; use HtmlReader[\"']\s*;?"
    )
    return pattern.sub(lambda match: " " * len(match.group(0)), text)


def _mask_rejection_literal(text: str) -> str:
    pattern = re.compile(
        r"if\s*\(\s*[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.panel_kind\s*"
        r"={2,3}\s*([\"'])PdfViewer\1\s*\)\s*return\s*"
        r"([\"'])PdfViewer is deprecated; use HtmlReader\2\s*;?"
    )
    masked = pattern.sub(lambda match: " " * len(match.group(0)), text)
    ternary = re.compile(
        r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*\.panel_kind\s*={2,3}\s*"
        r"([\"'])PdfViewer\1\s*\?\s*([\"'])"
        r"PdfViewer is deprecated; use HtmlReader\2\s*:"
    )
    masked = ternary.sub(lambda match: " " * len(match.group(0)), masked)
    literal = re.compile(r"([\"'])PdfViewer is deprecated; use HtmlReader\1")
    return literal.sub(lambda match: " " * len(match.group(0)), masked)


def scan_source(root: str | Path) -> list[Finding]:
    """Return deterministic findings from production Reading source."""
    base = Path(root).resolve()
    findings: list[Finding] = []
    for path in _source_files(base):
        raw = path.read_text(encoding="utf-8", errors="replace")
        text = _fold_static_template_interpolations(
            _fold_literal_concatenations(_mask_comments(raw))
        )
        rel = path.relative_to(base).as_posix()

        safe = _mask_source_rejection(text)
        for match in _matches(r"\bPdfViewer\b", safe, 0):
            _add(findings, rel, "pdfviewer-runtime", raw, match)

        for match in _matches(r"(?:\bpdfjs(?:Lib)?\b|pdfjs-dist|pdf\.worker|PDF\.js)", text):
            _add(findings, rel, "pdfjs-runtime", raw, match)

        # A sink needs local PDF evidence; generic iframe/object/embed usage is valid.
        sink_pattern = r"(?:<\s*(?:object|embed|iframe)\b[^>]{0,600}(?:\.pdf\b|application/pdf|blob:)[^>]*>|(?:object|embed|iframe)[^\n;]{0,240}(?:\.pdf\b|application/pdf|blob:))"
        for match in _matches(sink_pattern, text, re.IGNORECASE | re.DOTALL):
            _add(findings, rel, "pdf-embed-sink", raw, match)
        for match in _matches(
            r"\b\w+\.(?:src|data)\s*=\s*[\"'][^\"']*(?:\.pdf\b|application/pdf|blob:pdf)[^\"']*[\"']",
            text,
            re.IGNORECASE,
        ):
            _add(findings, rel, "pdf-embed-sink", raw, match)
        for match in _matches(
            r"(?:window\.open\s*\(|location(?:\.href)?\s*=|navigate\s*\()[^;\n]{0,300}[\"'][^\"']*\.pdf(?:[?#][^\"']*)?[\"']",
            text,
            re.IGNORECASE,
        ):
            _add(findings, rel, "pdf-navigation", raw, match)

        pdf_literal_vars = {
            match.group(1)
            for match in _matches(
                r"(?:const|let|var)\s+(\w+)\s*=\s*[\"'][^\"']*(?:\.pdf\b|application/pdf)[^\"']*[\"']",
                text,
            )
        }
        for variable in sorted(pdf_literal_vars):
            variable_pattern = re.escape(variable)
            for match in _matches(
                rf"<\s*(?:object|embed|iframe)\b[^>]{{0,600}}(?:src|data)\s*=\s*\{{\s*{variable_pattern}\s*\}}[^>]*>",
                text,
                re.IGNORECASE | re.DOTALL,
            ):
                _add(findings, rel, "pdf-embed-sink", raw, match)
            for match in _matches(
                rf"\b\w+\.(?:src|data)\s*=\s*(?:{variable_pattern}|[\"'][^\"']*\.pdf[^\"']*[\"'])",
                text,
                re.IGNORECASE,
            ):
                _add(findings, rel, "pdf-embed-sink", raw, match)

        # Lightweight intrafile taint: PDF Blob -> object URL -> rendering/navigation.
        pdf_vars: set[str] = set()
        url_vars: set[str] = set()
        for match in _matches(
            r"(?:const|let|var)\s+(\w+)\s*=\s*new\s+Blob\s*\([^;]{0,600}(?:application/pdf|\.pdf\b)",
            text,
            re.IGNORECASE | re.DOTALL,
        ):
            pdf_vars.add(match.group(1))
            _add(findings, rel, "pdf-blob-source", raw, match)
        for match in _matches(
            r"(?:const|let|var)\s+(\w+)\s*=\s*new\s+Blob\s*\([^;]{0,600}type\s*:\s*(\w+)",
            text,
            re.IGNORECASE | re.DOTALL,
        ):
            if match.group(2) in pdf_literal_vars:
                pdf_vars.add(match.group(1))
                _add(findings, rel, "pdf-blob-source", raw, match)
        for match in _matches(
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:URL\.)?createObjectURL\s*\(\s*(\w+)\s*\)", text
        ):
            if match.group(2) in pdf_vars:
                url_vars.add(match.group(1))
                _add(findings, rel, "pdf-blob-object-url", raw, match)
        tainted = pdf_vars | url_vars
        if tainted:
            names = "|".join(re.escape(name) for name in sorted(tainted))
            flow = rf"(?:window\.open|location(?:\.href)?\s*=|navigate\s*\(|<\s*(?:object|embed|iframe)\b[^>]*(?:src|data)\s*=)[^\n;>]{{0,240}}\b(?:{names})\b"
            for match in _matches(flow, text, re.IGNORECASE):
                _add(findings, rel, "pdf-blob-navigation", raw, match)
        direct_flow = r"(?:window\.open|location(?:\.href)?\s*=|navigate\s*\()[^;\n]{0,300}createObjectURL\s*\([^)]*(?:application/pdf|\.pdf\b)"
        for match in _matches(direct_flow, text, re.IGNORECASE):
            _add(findings, rel, "pdf-blob-navigation", raw, match)

        # Every produced legacy route is rejected.  The four inbound declarations are
        # explicit fingerprinted exceptions, rather than a syntactic loophole.
        for match in _matches(r"[\"'`]\/wrestle(?:\/|\b|[\"'`])", text, 0):
            _add(findings, rel, "direct-wrestle-route", raw, match)

    return sorted(set(findings))


def scan_bundle(bundle_dir: str | Path, root: str | Path | None = None) -> list[Finding]:
    """Scan emitted JS/CSS and asset names for executable native-PDF residue."""
    directory = Path(bundle_dir).resolve()
    if not directory.is_dir():
        raise ConfigurationError(f"bundle directory does not exist: {directory}")
    base = Path(root).resolve() if root else directory
    findings: list[Finding] = []
    paths = sorted(p for p in directory.rglob("*") if p.is_file())
    bundle_text: dict[Path, str] = {
        path: path.read_text(encoding="utf-8", errors="replace")
        for path in paths
        if path.suffix.lower() in BUNDLE_SUFFIXES
    }
    pdf_blob_present = any(
        re.search(r"new\s+Blob\s*\([\s\S]{0,600}application/pdf", raw, re.IGNORECASE)
        for raw in bundle_text.values()
    )
    for path in paths:
        rel = path.relative_to(base).as_posix() if path.is_relative_to(base) else path.as_posix()
        name = path.name
        if re.search(r"(?:pdfjs|pdf[._-]?worker|pdf[._-]?render)", name, re.IGNORECASE):
            findings.append(Finding(rel, 1, "bundle-pdf-residue", name))
        if path.suffix.lower() not in BUNDLE_SUFFIXES:
            continue
        raw = bundle_text[path]
        safe = _mask_rejection_literal(raw)
        patterns = (
            (
                "bundle-pdfjs-residue",
                r"(?:pdfjs-dist|\bpdfjs(?:Lib)?\b|pdf\.worker|GlobalWorkerOptions|getDocument\s*\()",
            ),
            ("bundle-pdf-render-residue", r"(?:renderTextLayer|PDFPageProxy|PDFDocumentProxy)"),
            ("bundle-pdfviewer-residue", r"\bPdfViewer\b"),
            (
                "bundle-pdf-embed-residue",
                r"(?:jsx|jsxs|createElement)\s*\(\s*[\"'](?:object|embed|iframe)[\"'][^;]{0,500}(?:\.pdf\b|application/pdf|blob:pdf)",
            ),
            (
                "bundle-pdf-blob-residue",
                r"new\s+Blob\s*\([\s\S]{0,600}application/pdf[\s\S]{0,600}createObjectURL",
            ),
            (
                "bundle-pdf-blob-residue",
                r"new\s+Blob\s*\([\s\S]{0,600}application/pdf",
            ),
            (
                "bundle-pdf-embed-residue",
                r"(?:jsx|jsxs|createElement)\s*\([^;]{0,500}[\"'][^\"']*\.pdf(?:[?#][^\"']*)?[\"']",
            ),
        )
        for rule, pattern in patterns:
            for match in _matches(pattern, safe):
                _add(findings, rel, rule, raw, match)
        if pdf_blob_present:
            for match in _matches(
                r"createObjectURL\s*\([^)]*\)[\s\S]{0,300}(?:window\.open|location(?:\.href)?\s*=|navigate\s*\(|(?:jsx|jsxs|createElement)\s*\(\s*[\"'](?:object|embed|iframe)[\"'])",
                safe,
                re.IGNORECASE,
            ):
                _add(findings, rel, "bundle-pdf-blob-residue", raw, match)
    return sorted(set(findings))


def load_allowlist(path: str | Path) -> list[dict[str, str]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"cannot read allowlist: {exc}") from exc
    if not isinstance(value, list):
        raise ConfigurationError("allowlist must be a JSON array")
    return value


def validate_allowlist(
    entries: Sequence[object], findings: Sequence[Finding], root: str | Path
) -> list[Finding]:
    """Validate exceptions and return findings not covered by them."""
    base = Path(root).resolve()
    by_key = {(f.file, f.rule, f.fingerprint): f for f in findings}
    seen: set[tuple[str, str, str]] = set()
    covered: set[Finding] = set()
    for index, raw in enumerate(entries):
        label = f"allowlist entry {index + 1}"
        if not isinstance(raw, dict):
            raise ConfigurationError(f"{label} must be an object")
        unknown = set(raw) - ALLOWED_KEYS
        if unknown:
            raise ConfigurationError(f"{label} has unknown fields: {', '.join(sorted(unknown))}")
        missing = REQUIRED_KEYS - set(raw)
        if missing:
            raise ConfigurationError(f"{label} is missing fields: {', '.join(sorted(missing))}")
        if ("expires" in raw) == ("review_condition" in raw):
            raise ConfigurationError(
                f"{label} must have exactly one of expires or review_condition"
            )
        if any(not isinstance(raw.get(key), str) or not raw[key].strip() for key in REQUIRED_KEYS):
            raise ConfigurationError(f"{label} fields must be non-empty strings")
        file = raw["file"]
        if (
            any(char in file for char in "*?[{}")
            or Path(file).is_absolute()
            or ".." in Path(file).parts
        ):
            raise ConfigurationError(f"{label} file must be a literal repository-relative path")
        if not (base / file).is_file():
            raise ConfigurationError(f"{label} references missing file: {file}")
        if "expires" in raw:
            try:
                expiry = date.fromisoformat(raw["expires"])
            except (TypeError, ValueError) as exc:
                raise ConfigurationError(f"{label} expires must be an ISO date") from exc
            if expiry < date.today():
                raise ConfigurationError(f"{label} expired on {expiry.isoformat()}")
        elif not isinstance(raw["review_condition"], str) or not raw["review_condition"].strip():
            raise ConfigurationError(f"{label} review_condition must be a non-empty string")
        if re.fullmatch(r"[0-9a-f]{64}", raw["fingerprint"]) is None:
            raise ConfigurationError(
                f"{label} fingerprint must be 64 lowercase hexadecimal characters"
            )
        key = (file, raw["rule"], raw["fingerprint"])
        if key in seen:
            raise ConfigurationError(f"{label} duplicates an earlier entry")
        seen.add(key)
        finding = by_key.get(key)
        if finding is None:
            same_file_rule = [f for f in findings if f.file == file and f.rule == raw["rule"]]
            same_fingerprint = [f for f in findings if f.fingerprint == raw["fingerprint"]]
            if same_file_rule:
                raise ConfigurationError(f"{label} fingerprint mismatch")
            if same_fingerprint:
                raise ConfigurationError(f"{label} fingerprint belongs to a different file or rule")
            raise ConfigurationError(f"{label} is stale (no matching finding)")
        covered.add(finding)
    return [finding for finding in findings if finding not in covered]


def scan(root: str | Path, bundle_dir: str | Path | None = None) -> list[Finding]:
    findings = scan_source(root)
    if bundle_dir is not None:
        findings.extend(scan_bundle(bundle_dir, root))
    return sorted(set(findings))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--bundle-dir", type=Path)
    args = parser.parse_args(argv)
    try:
        findings = scan(args.root, args.bundle_dir)
        remaining = validate_allowlist(load_allowlist(args.allowlist), findings, args.root)
    except ConfigurationError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2
    for finding in remaining:
        print(finding.message())
    return 1 if remaining else 0


if __name__ == "__main__":
    raise SystemExit(main())
