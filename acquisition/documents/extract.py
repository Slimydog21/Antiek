"""Bounded byte-to-text extraction shared by Wrestle and Marketplace."""

from __future__ import annotations

import hashlib
import io
import posixpath
import zipfile
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import PurePosixPath
from xml.etree import ElementTree

EXTRACTOR_VERSION = "hosted-document-extractor-v1"
MAX_SOURCE_BYTES = 50 * 1024 * 1024
MAX_EPUB_ENTRIES = 2_000
MAX_EPUB_TOTAL_BYTES = 20 * 1024 * 1024
MAX_EPUB_ITEM_BYTES = 2 * 1024 * 1024
MAX_EPUB_COMPRESSION_RATIO = 1_000
MAX_TEXT_CHARS = 2_000_000
MIN_VIEWABLE_WORDS = 50


@dataclass(frozen=True)
class ExtractedTocEntry:
    title: str
    page_index: int | None
    level: int


@dataclass(frozen=True)
class ExtractedDocument:
    source_format: str
    source_byte_hash: str
    extracted_content_hash: str
    canonical_content_hash: str
    extractor_version: str
    text: str
    title: str | None
    author: str | None
    page_count: int | None
    page_word_counts: tuple[int, ...]
    toc: tuple[ExtractedTocEntry, ...]
    word_count: int
    truncated: bool
    viewable: bool
    non_viewable_reason: str | None


class _XhtmlText(HTMLParser):
    _BREAK_BEFORE = frozenset({"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "blockquote"})
    _BLOCKED = frozenset(
        {"script", "style", "svg", "math", "template", "iframe", "object", "embed", "form"}
    )

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.blocked_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in self._BLOCKED:
            self.blocked_stack.append(name)
        elif not self.blocked_stack and name in self._BREAK_BEFORE:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if self.blocked_stack and name == self.blocked_stack[-1]:
            self.blocked_stack.pop()
        elif not self.blocked_stack and name in self._BREAK_BEFORE:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if not self.blocked_stack:
            self.parts.append(data)

    def text(self) -> str:
        paragraphs = [" ".join(part.split()) for part in "".join(self.parts).split("\n\n")]
        return "\n\n".join(part for part in paragraphs if part)


def _digest(value: bytes | str) -> str:
    raw = value if isinstance(value, bytes) else value.encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_epub_name(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(name) and not path.is_absolute() and ".." not in path.parts


def _read_epub_item(archive: zipfile.ZipFile, name: str) -> bytes:
    if not _safe_epub_name(name):
        raise ValueError("epub_path_traversal")
    info = archive.getinfo(name)
    if info.flag_bits & 0x1:
        raise ValueError("epub_encrypted")
    if info.file_size > MAX_EPUB_ITEM_BYTES:
        raise ValueError("epub_item_too_large")
    return archive.read(info)


def _parse_epub_xml(raw: bytes) -> ElementTree.Element:
    upper = raw.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValueError("epub_xml_dtd_forbidden")
    return ElementTree.fromstring(raw)


def _extract_epub(raw: bytes) -> tuple[str, str | None, str | None]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_EPUB_ENTRIES:
            raise ValueError("epub_too_many_entries")
        if len({info.filename for info in infos}) != len(infos):
            raise ValueError("epub_duplicate_entries")
        if any(not _safe_epub_name(info.filename) for info in infos):
            raise ValueError("epub_path_traversal")
        if any(info.flag_bits & 0x1 for info in infos):
            raise ValueError("epub_encrypted")
        if any(
            info.file_size > 0
            and info.file_size / max(info.compress_size, 1) > MAX_EPUB_COMPRESSION_RATIO
            for info in infos
        ):
            raise ValueError("epub_compression_ratio_exceeded")
        if sum(info.file_size for info in infos) > MAX_EPUB_TOTAL_BYTES:
            raise ValueError("epub_uncompressed_too_large")
        container = _parse_epub_xml(_read_epub_item(archive, "META-INF/container.xml"))
        rootfile = next(
            (
                node.attrib.get("full-path", "")
                for node in container.iter()
                if _local(node.tag) == "rootfile"
            ),
            "",
        )
        if not rootfile or not _safe_epub_name(rootfile):
            raise ValueError("epub_missing_package")
        package = _parse_epub_xml(_read_epub_item(archive, rootfile))
        manifest = {
            node.attrib.get("id", ""): (
                node.attrib.get("href", ""),
                node.attrib.get("media-type", ""),
            )
            for node in package.iter()
            if _local(node.tag) == "item"
        }
        spine = [
            node.attrib.get("idref", "") for node in package.iter() if _local(node.tag) == "itemref"
        ]
        metadata = {
            _local(node.tag): (node.text or "").strip()
            for node in package.iter()
            if _local(node.tag) in {"title", "creator"} and (node.text or "").strip()
        }
        base = posixpath.dirname(rootfile)
        chapters: list[str] = []
        for item_id in spine:
            href, media_type = manifest.get(item_id, ("", ""))
            if media_type not in {"application/xhtml+xml", "text/html"}:
                raise ValueError("epub_spine_not_html")
            name = posixpath.normpath(posixpath.join(base, href))
            if not href or not _safe_epub_name(name):
                raise ValueError("epub_invalid_spine")
            parser = _XhtmlText()
            parser.feed(_read_epub_item(archive, name).decode("utf-8", errors="replace"))
            parser.close()
            if parser.text():
                chapters.append(parser.text())
        if not chapters:
            raise ValueError("epub_empty_spine")
        return "\n\n".join(chapters), metadata.get("title"), metadata.get("creator")


def _finalize(
    *,
    source_format: str,
    raw: bytes,
    text: str,
    title: str | None = None,
    author: str | None = None,
    page_count: int | None = None,
    page_word_counts: tuple[int, ...] = (),
    toc: tuple[ExtractedTocEntry, ...] = (),
    failure_reason: str | None = None,
    minimum_viewable_words: int = MIN_VIEWABLE_WORDS,
) -> ExtractedDocument:
    truncated = len(text) > MAX_TEXT_CHARS
    bounded = text[:MAX_TEXT_CHARS]
    word_count = len(bounded.split())
    reason = failure_reason or ("low_word_count" if word_count < minimum_viewable_words else None)
    admitted_text = bounded if reason is None else ""
    return ExtractedDocument(
        source_format=source_format,
        source_byte_hash=_digest(raw),
        extracted_content_hash=_digest(bounded),
        canonical_content_hash=_digest(admitted_text),
        extractor_version=EXTRACTOR_VERSION,
        text=admitted_text,
        title=title,
        author=author,
        page_count=page_count,
        page_word_counts=page_word_counts,
        toc=toc,
        word_count=word_count,
        truncated=truncated,
        viewable=reason is None,
        non_viewable_reason=reason,
    )


def extract_document_bytes(
    raw: bytes,
    *,
    source_format: str,
    minimum_viewable_words: int = MIN_VIEWABLE_WORDS,
) -> ExtractedDocument:
    """Extract one bounded source; failures become explicit non-viewable receipts."""
    if minimum_viewable_words < 1:
        raise ValueError("minimum_viewable_words must be at least 1")
    fmt = source_format.strip().lower().lstrip(".")
    if not raw:
        return _finalize(
            source_format=fmt or "unknown",
            raw=raw,
            text="",
            failure_reason="empty_source",
            minimum_viewable_words=minimum_viewable_words,
        )
    if len(raw) > MAX_SOURCE_BYTES:
        return _finalize(
            source_format=fmt or "unknown",
            raw=raw,
            text="",
            failure_reason="source_too_large",
            minimum_viewable_words=minimum_viewable_words,
        )
    if raw.startswith(b"%PDF") and fmt != "pdf":
        return _finalize(
            source_format=fmt or "unknown",
            raw=raw,
            text="",
            failure_reason="source_format_mismatch",
            minimum_viewable_words=minimum_viewable_words,
        )
    if raw.startswith(b"PK\x03\x04") and fmt != "epub":
        return _finalize(
            source_format=fmt or "unknown",
            raw=raw,
            text="",
            failure_reason="source_format_mismatch",
            minimum_viewable_words=minimum_viewable_words,
        )
    try:
        if fmt == "pdf":
            from acquisition.books.reader import read_pdf

            result = read_pdf(raw)
            toc = tuple(
                ExtractedTocEntry(
                    title=str(entry.title),
                    page_index=entry.page_index,
                    level=int(entry.level),
                )
                for entry in getattr(result, "toc", ())
            )
            return _finalize(
                source_format=fmt,
                raw=raw,
                text=result.markdown,
                title=result.title,
                author=result.author,
                page_count=result.page_count,
                page_word_counts=tuple(
                    int(page.word_count) for page in getattr(result, "pages", ())
                ),
                toc=toc,
                minimum_viewable_words=minimum_viewable_words,
            )
        if fmt == "epub":
            text, title, author = _extract_epub(raw)
            return _finalize(
                source_format=fmt,
                raw=raw,
                text=text,
                title=title,
                author=author,
                minimum_viewable_words=minimum_viewable_words,
            )
        if fmt in {"html", "htm", "xhtml"}:
            parser = _XhtmlText()
            parser.feed(raw.decode("utf-8", errors="replace"))
            parser.close()
            return _finalize(
                source_format="html",
                raw=raw,
                text=parser.text(),
                minimum_viewable_words=minimum_viewable_words,
            )
        if fmt in {"text", "txt", "md", "markdown"}:
            return _finalize(
                source_format=fmt,
                raw=raw,
                text=raw.decode("utf-8", errors="replace"),
                minimum_viewable_words=minimum_viewable_words,
            )
        return _finalize(
            source_format=fmt or "unknown",
            raw=raw,
            text="",
            failure_reason="unsupported_format",
            minimum_viewable_words=minimum_viewable_words,
        )
    except Exception as exc:
        reason = str(exc) if str(exc).startswith("epub_") else "extraction_failed"
        return _finalize(
            source_format=fmt,
            raw=raw,
            text="",
            failure_reason=reason,
            minimum_viewable_words=minimum_viewable_words,
        )
