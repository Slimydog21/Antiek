"""EPUB extractor (M5).

EPUB is a ZIP containing:
  - ``META-INF/container.xml`` → points at the OPF manifest.
  - ``<rootfile>.opf`` → declares spine order of XHTML content files.
  - ``content.opf``'s ``<metadata>`` → title, creator (author),
    language, date.
  - One XHTML file per chapter (linked in spine order).

We parse the OPF for metadata + spine, walk each XHTML file in order,
strip tags to plain text, and synthesize page boundaries at
``WORDS_PER_PAGE`` words.

Why stdlib only (zipfile + xml.etree): EPUB is structurally simple
when you don't need DRM handling. ``ebooklib`` adds value when
you're doing rich rendering or non-spine resources; for text
extraction the stdlib is enough. INGESTION_NOTES.md documents this
trade-off.

Page synthesis must be deterministic so re-extracting the same EPUB
yields the same chunks (idempotency guarantee mirrors arXiv adapter
behavior). We use a strict words-per-page count starting from the
first chapter — no randomness, no chapter-boundary heuristics that
might change across runs.
"""

from __future__ import annotations

import io
import os
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from xml.etree import ElementTree as ET

# Per INGESTION_NOTES.md.
WORDS_PER_PAGE = 250

# OPF / DC namespaces. EPUB 2 + 3 use these.
_NS = {
    "container": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}


@dataclass(frozen=True)
class EpubPage:
    """One synthesized page. ``page_index`` is 1-based — the reader
    UI is 1-based, and matching that in the substrate keeps cross-
    references obvious."""

    page_index: int
    chapter_index: int
    chapter_title: Optional[str]
    text: str
    word_count: int


@dataclass(frozen=True)
class EpubExtraction:
    """Output of ``extract_epub``. ``chapters`` is the structural
    spine (chapter titles in order); ``pages`` is the synthesized
    pagination the chunker downstream consumes."""

    title: Optional[str]
    author: Optional[str]
    language: Optional[str]
    published_at: Optional[datetime]
    chapters: list[str] = field(default_factory=list)
    pages: list[EpubPage] = field(default_factory=list)
    word_count: int = 0
    text: str = ""


def _xml_text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    txt = el.text.strip()
    return txt or None


def _read_container(zf: zipfile.ZipFile) -> str:
    """Return the OPF file path from META-INF/container.xml."""
    with zf.open("META-INF/container.xml") as f:
        tree = ET.parse(f)
    root = tree.getroot()
    rootfile = root.find(".//container:rootfile", _NS)
    if rootfile is None:
        raise ValueError("EPUB missing META-INF/container.xml rootfile")
    path = rootfile.get("full-path")
    if not path:
        raise ValueError("EPUB rootfile missing full-path attribute")
    return path


def _read_opf(zf: zipfile.ZipFile, opf_path: str):
    """Return (metadata_dict, spine_paths). Spine paths are normalized
    against the OPF's directory so they resolve in the zip namespace."""
    with zf.open(opf_path) as f:
        tree = ET.parse(f)
    root = tree.getroot()
    md_el = root.find("opf:metadata", _NS)
    metadata: dict[str, Optional[str]] = {
        "title": _xml_text(md_el.find("dc:title", _NS)) if md_el is not None else None,
        "creator": _xml_text(md_el.find("dc:creator", _NS)) if md_el is not None else None,
        "language": _xml_text(md_el.find("dc:language", _NS)) if md_el is not None else None,
        "date": _xml_text(md_el.find("dc:date", _NS)) if md_el is not None else None,
    }

    manifest_el = root.find("opf:manifest", _NS)
    items: dict[str, str] = {}
    if manifest_el is not None:
        for it in manifest_el.findall("opf:item", _NS):
            iid = it.get("id")
            href = it.get("href")
            if iid and href:
                items[iid] = href

    spine_el = root.find("opf:spine", _NS)
    spine_paths: list[str] = []
    opf_dir = os.path.dirname(opf_path)
    if spine_el is not None:
        for it in spine_el.findall("opf:itemref", _NS):
            idref = it.get("idref")
            if idref and idref in items:
                href = items[idref]
                path = os.path.normpath(os.path.join(opf_dir, href)) if opf_dir else href
                spine_paths.append(path.replace("\\", "/"))
    return metadata, spine_paths


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_SCRIPT_STYLE_RE = re.compile(
    r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL,
)
_TITLE_RE = re.compile(r"<h1[^>]*>(.*?)</h1>", re.IGNORECASE | re.DOTALL)


def _xhtml_to_text(xhtml: str) -> tuple[Optional[str], str]:
    """Strip XHTML to plain text. Returns (chapter_title, body_text).
    The chapter title is the first ``<h1>`` (case-insensitive) if any."""
    title_match = _TITLE_RE.search(xhtml)
    chapter_title = None
    if title_match:
        raw = _TAG_RE.sub("", title_match.group(1))
        chapter_title = _WS_RE.sub(" ", raw).strip() or None
    no_script = _SCRIPT_STYLE_RE.sub(" ", xhtml)
    stripped = _TAG_RE.sub(" ", no_script)
    text = _WS_RE.sub(" ", stripped).strip()
    return chapter_title, text


def _paginate(
    chapter_texts: list[tuple[Optional[str], str]],
    *,
    words_per_page: int = WORDS_PER_PAGE,
) -> list[EpubPage]:
    """Deterministic pagination. Splits each chapter into successive
    ``words_per_page``-word slices. Each page knows its 1-based index
    + the chapter it came from."""
    pages: list[EpubPage] = []
    page_index = 1
    for chapter_index, (title, body) in enumerate(chapter_texts):
        if not body:
            continue
        words = body.split()
        if not words:
            continue
        for i in range(0, len(words), words_per_page):
            slice_words = words[i: i + words_per_page]
            page_text = " ".join(slice_words)
            pages.append(EpubPage(
                page_index=page_index,
                chapter_index=chapter_index,
                chapter_title=title,
                text=page_text,
                word_count=len(slice_words),
            ))
            page_index += 1
    return pages


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    candidate = raw.strip()
    # EPUB ``dc:date`` may be "YYYY", "YYYY-MM-DD", or full ISO. Try
    # progressive parses; bail on the first that works.
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d", "%Y"):
        try:
            return datetime.strptime(candidate[: len(fmt) + 2], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        if candidate.endswith("Z"):
            candidate = candidate[:-1] + "+00:00"
        dt = datetime.fromisoformat(candidate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def extract_epub(
    *,
    epub_bytes: bytes,
    words_per_page: int = WORDS_PER_PAGE,
) -> EpubExtraction:
    """Extract an EPUB byte blob → text + chapter list + synthesized
    pages. Deterministic: same bytes + same words_per_page → same
    pages."""
    bio = io.BytesIO(epub_bytes)
    with zipfile.ZipFile(bio) as zf:
        opf_path = _read_container(zf)
        metadata, spine_paths = _read_opf(zf, opf_path)
        chapter_texts: list[tuple[Optional[str], str]] = []
        for path in spine_paths:
            try:
                with zf.open(path) as f:
                    raw = f.read()
            except KeyError:
                continue
            try:
                xhtml = raw.decode("utf-8")
            except UnicodeDecodeError:
                xhtml = raw.decode("latin-1", errors="replace")
            title, text = _xhtml_to_text(xhtml)
            chapter_texts.append((title, text))

    chapters = [t or f"Chapter {i + 1}" for i, (t, _) in enumerate(chapter_texts)]
    pages = _paginate(chapter_texts, words_per_page=words_per_page)
    full_text = "\n\n".join(t for _, t in chapter_texts if t)
    word_count = sum(p.word_count for p in pages)

    return EpubExtraction(
        title=metadata.get("title"),
        author=metadata.get("creator"),
        language=metadata.get("language"),
        published_at=_parse_date(metadata.get("date")),
        chapters=chapters,
        pages=pages,
        word_count=word_count,
        text=full_text,
    )
