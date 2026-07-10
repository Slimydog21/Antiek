"""Fail-closed epub (OCF zip) reader — the acquisition half of SPR-02.

An epub is a zip of XHTML plus two XML manifests (``META-INF/container.xml``
→ the OPF package document → spine order). This module opens that container
with a hostile-input posture and returns the spine chapters in reading order.
Everything here is stdlib (``zipfile`` + ``xml.etree``): no new dependency.

Security boundaries enforced BEFORE any content is trusted:

- **Local file only.** The reader takes bytes or a local path; it never
  fetches a URL. (That boundary is why the legacy #490 preflight was
  "no-upload" — preserve it at every future call site.)
- **Archive hygiene.** Member names are refused on traversal (``..``),
  absolute paths, drive letters, backslashes, or NULs; entry count, per-entry
  and total uncompressed budgets, and compression ratio are capped
  (:class:`EpubLimits`) — a zip-bomb-ish archive raises
  ``ZipBombSuspectedError`` instead of exhausting the host.
- **No XML entity resolution, ever.** Any ``<!DOCTYPE``/``<!ENTITY`` in the
  container/OPF XML — or an ``<!ENTITY`` in a chapter — raises
  ``ExternalEntityBlockedError``. (``xml.etree`` does not fetch external
  entities, but we refuse the construct outright rather than relying on
  parser defaults.)
- **DRM is refused, never bypassed.** ``META-INF/encryption.xml`` present →
  ``DrmLockedError``.
"""

from __future__ import annotations

import io
import posixpath
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree as ET

from .errors import (
    DrmLockedError,
    ExternalEntityBlockedError,
    MalformedEpubError,
    NotAnEpubError,
    NoTextContentError,
    UnsafeArchivePathError,
    ZipBombSuspectedError,
)

_CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"
_OPF_NS = "http://www.idpf.org/2007/opf"
_DC_NS = "http://purl.org/dc/elements/1.1/"

_CHAPTER_MEDIA_TYPES = frozenset({"application/xhtml+xml", "text/html"})

_DOCTYPE_RE = re.compile(r"<!\s*DOCTYPE", re.IGNORECASE)
_ENTITY_RE = re.compile(r"<!\s*ENTITY", re.IGNORECASE)
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


@dataclass(frozen=True)
class EpubLimits:
    """Resource budgets for reading one epub. Defaults are generous for real
    books and hostile to bombs; tests pass tighter limits to prove each cap
    actually fires."""

    max_entries: int = 512
    max_entry_bytes: int = 10 * 1024 * 1024
    max_total_bytes: int = 64 * 1024 * 1024
    # Ratio guard: entries larger than ratio_floor_bytes (uncompressed) whose
    # uncompressed/compressed ratio exceeds this are treated as bombs.
    max_compression_ratio: int = 250
    ratio_floor_bytes: int = 1024 * 1024


DEFAULT_LIMITS = EpubLimits()


@dataclass(frozen=True)
class EpubChapter:
    """One spine document, in reading order. ``xhtml`` is the raw (untrusted)
    chapter markup — it has NOT been sanitized yet."""

    href: str
    xhtml: str


@dataclass(frozen=True)
class EpubBook:
    """The parsed container: OPF metadata + spine chapters in order."""

    title: str | None
    author: str | None
    chapters: tuple[EpubChapter, ...]


EpubSource = str | Path | bytes


def _load_bytes(source: EpubSource) -> bytes:
    if isinstance(source, bytes):
        if not source:
            raise NotAnEpubError("empty byte input")
        return source
    path = Path(source)
    if not path.is_file():
        raise NotAnEpubError(f"no such file: {path}")
    return path.read_bytes()


def _check_member_name(name: str) -> None:
    if "\x00" in name:
        raise UnsafeArchivePathError(f"NUL byte in member name {name!r}")
    if "\\" in name:
        raise UnsafeArchivePathError(f"backslash path in member name {name!r}")
    if name.startswith("/"):
        raise UnsafeArchivePathError(f"absolute member path {name!r}")
    if _DRIVE_RE.match(name):
        raise UnsafeArchivePathError(f"drive-letter member path {name!r}")
    normalized = posixpath.normpath(name)
    if normalized == ".." or normalized.startswith("../"):
        raise UnsafeArchivePathError(f"traversal in member name {name!r}")


def _check_archive(zf: zipfile.ZipFile, limits: EpubLimits) -> set[str]:
    infos = zf.infolist()
    if len(infos) > limits.max_entries:
        raise ZipBombSuspectedError(
            f"{len(infos)} entries exceeds max_entries={limits.max_entries}"
        )
    total = 0
    names: set[str] = set()
    for info in infos:
        _check_member_name(info.filename)
        if info.file_size > limits.max_entry_bytes:
            raise ZipBombSuspectedError(
                f"entry {info.filename!r} declares {info.file_size} bytes "
                f"(max_entry_bytes={limits.max_entry_bytes})"
            )
        total += info.file_size
        if total > limits.max_total_bytes:
            raise ZipBombSuspectedError(
                f"archive declares more than max_total_bytes={limits.max_total_bytes} "
                "uncompressed"
            )
        if (
            info.compress_size > 0
            and info.file_size > limits.ratio_floor_bytes
            and info.file_size / info.compress_size > limits.max_compression_ratio
        ):
            raise ZipBombSuspectedError(
                f"entry {info.filename!r} compression ratio "
                f"{info.file_size / info.compress_size:.0f} exceeds "
                f"max_compression_ratio={limits.max_compression_ratio}"
            )
        names.add(info.filename)
    return names


def _read_member(zf: zipfile.ZipFile, name: str, limits: EpubLimits) -> bytes:
    """Read one member with the byte budget enforced on the ACTUAL stream,
    not just the (forgeable) header size."""
    try:
        with zf.open(name) as fh:
            data = fh.read(limits.max_entry_bytes + 1)
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise MalformedEpubError(f"unreadable member {name!r}: {exc}") from exc
    if len(data) > limits.max_entry_bytes:
        raise ZipBombSuspectedError(
            f"entry {name!r} inflates past max_entry_bytes={limits.max_entry_bytes}"
        )
    return data


def _read_text(zf: zipfile.ZipFile, name: str, limits: EpubLimits) -> str:
    return _read_member(zf, name, limits).decode("utf-8", errors="replace")


def _parse_xml_no_entities(text: str, *, what: str) -> ET.Element:
    """Parse manifest XML with the entity surface refused outright."""
    if _DOCTYPE_RE.search(text) or _ENTITY_RE.search(text):
        raise ExternalEntityBlockedError(
            f"{what} declares a DOCTYPE/ENTITY — entity resolution is refused"
        )
    try:
        return ET.fromstring(text)
    except ET.ParseError as exc:
        raise MalformedEpubError(f"unparseable {what}: {exc}") from exc


def _opf_path_from_container(container_xml: str) -> str:
    root = _parse_xml_no_entities(container_xml, what="META-INF/container.xml")
    rootfile = root.find(f".//{{{_CONTAINER_NS}}}rootfile")
    if rootfile is None:
        # Some producers omit the namespace; tolerate that one laxity.
        rootfile = root.find(".//rootfile")
    if rootfile is None:
        raise MalformedEpubError("container.xml has no <rootfile> element")
    full_path = rootfile.get("full-path")
    if not full_path:
        raise MalformedEpubError("container.xml <rootfile> has no full-path")
    _check_member_name(full_path)
    return full_path


def _first_text(root: ET.Element, tag: str) -> str | None:
    el = root.find(f".//{{{_DC_NS}}}{tag}")
    if el is None or el.text is None:
        return None
    text = el.text.strip()
    return text or None


def _spine_hrefs(root: ET.Element, opf_dir: str) -> list[str]:
    manifest: dict[str, tuple[str, str]] = {}
    for item in root.findall(f".//{{{_OPF_NS}}}manifest/{{{_OPF_NS}}}item"):
        item_id = item.get("id")
        href = item.get("href")
        media_type = item.get("media-type", "")
        if item_id and href:
            manifest[item_id] = (href, media_type)
    hrefs: list[str] = []
    for itemref in root.findall(f".//{{{_OPF_NS}}}spine/{{{_OPF_NS}}}itemref"):
        idref = itemref.get("idref")
        if not idref:
            continue
        if idref not in manifest:
            raise MalformedEpubError(f"spine idref {idref!r} not in manifest")
        href, media_type = manifest[idref]
        if media_type not in _CHAPTER_MEDIA_TYPES:
            # A non-document spine item (image spread, etc.) — skip, honestly.
            continue
        resolved = posixpath.normpath(posixpath.join(opf_dir, unquote(href)))
        _check_member_name(resolved)
        hrefs.append(resolved)
    return hrefs


def read_epub(source: EpubSource, *, limits: EpubLimits | None = None) -> EpubBook:
    """Open an epub from bytes or a LOCAL path and return its spine chapters
    in reading order, with every hostile-input check applied fail-closed.

    Raises the typed :mod:`substrate.book_import.errors` vocabulary; never
    returns a partially-trusted or silently-empty book.
    """
    limits = limits or DEFAULT_LIMITS
    data = _load_bytes(source)
    buffer = io.BytesIO(data)
    if not zipfile.is_zipfile(buffer):
        raise NotAnEpubError("input is not a zip container")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise NotAnEpubError(f"unreadable zip container: {exc}") from exc
    with zf:
        names = _check_archive(zf, limits)
        if "mimetype" in names:
            declared = _read_text(zf, "mimetype", limits).strip()
            if declared != "application/epub+zip":
                raise NotAnEpubError(f"mimetype declares {declared!r}")
        if "META-INF/encryption.xml" in names:
            raise DrmLockedError(
                "META-INF/encryption.xml present — DRM/encrypted epubs are "
                "refused, never bypassed"
            )
        if "META-INF/container.xml" not in names:
            raise MalformedEpubError("META-INF/container.xml missing")
        opf_path = _opf_path_from_container(
            _read_text(zf, "META-INF/container.xml", limits)
        )
        if opf_path not in names:
            raise MalformedEpubError(f"container points at missing OPF {opf_path!r}")
        opf_root = _parse_xml_no_entities(
            _read_text(zf, opf_path, limits), what=f"OPF {opf_path!r}"
        )
        title = _first_text(opf_root, "title")
        author = _first_text(opf_root, "creator")
        chapters: list[EpubChapter] = []
        for href in _spine_hrefs(opf_root, posixpath.dirname(opf_path)):
            if href not in names:
                raise MalformedEpubError(f"spine references missing member {href!r}")
            xhtml = _read_text(zf, href, limits)
            if _ENTITY_RE.search(xhtml):
                raise ExternalEntityBlockedError(
                    f"chapter {href!r} declares an ENTITY — refused"
                )
            chapters.append(EpubChapter(href=href, xhtml=xhtml))
    if not chapters:
        raise NoTextContentError("epub spine contains no XHTML chapters")
    return EpubBook(title=title, author=author, chapters=tuple(chapters))


__all__ = [
    "DEFAULT_LIMITS",
    "EpubBook",
    "EpubChapter",
    "EpubLimits",
    "EpubSource",
    "read_epub",
]
