"""The canonical Write revision snapshot: renderer, block inventory and members (W3-2).

``snapshot_deliverable`` reads one Write deliverable through the caller's
connection and returns what a Write revision stores: the canonical HTML bytes,
the ordered block inventory, one member row per block and the manifest. It is
pure. It issues SELECT statements only, on the connection it is given, and
never opens a connection, starts a transaction or touches the filesystem, so
the W3-3 writer can call it inside its own write transaction.

The canonical body (spec W3 §2, co-sign W3-C4) is the deliverable title,
section headings, section prose (``deliverable_sections.prose_text``) and
``outline_blocks``, in ``build_outline_tree`` order: sections by
``(section_index, section_id)`` in pre-order, with a section whose parent lies
outside the deliverable surfaced at the root; blocks by
``(block_index, outline_block_id)``. A section's prose is one block,
``sprose:<section_id>``, present only when it has a non-empty paragraph.
Headings and the title are structural text, not blocks.

Main's deliverable HTML path is not reused: it reads ``section_blocks``, drops
unresolvable refs, opens its own connections, orders sections by index alone,
bakes cite-only rights into the bytes and emits no block ids. The bytes here
are the owner's pre-gate text; rights apply at serve time (THREAD-CONTRACT
§1.11 serve-time gate).

Members follow the PR W3-2 table and the signed §1.11 rules. Every row is a
recorded ``user`` or ``unresolved`` member. An unresolved member records what
is known or null, never a guess: a graph node's document comes only from the
node's own ``metadata.chunk_id``, never from an edge, and ``investigation_id``
comes only from an ``outline_block_attribution`` row when that table exists.
A null ``investigation_id`` means "no thread recorded". An unknown provenance
kind fails closed to ``unresolved/no_provenance``.

The HTML grammar below is sanitizer ``antiek-write-revision-escape`` version
``1``. Changing a single emitted byte is a new sanitizer version.

    article := '<article data-antiek-write="1" data-deliverable-id="'E(did)'">' LF
               '<h1>'E(title)'</h1>' LF section* '</article>' LF
    section := '<section data-section-id="'E(sid)'" data-depth="'d'">' LF
               '<h'h'>'E(title or "")'</h'h'>' LF [prose] block* '</section>' LF
               ; h = min(2 + d, 6)
    prose   := '<div data-block-id="sprose:'E(sid)'" data-block-role="prose">'
               ('<p>'E(p)'</p>')+ '</div>' LF
    block   := '<div data-block-id="'E(obid)'" data-block-kind="'k'"'
               ' data-provenance-kind="'pk'">' ['<p>'E(text)'</p>'] '</div>' LF

``E`` is ``html.escape(s, quote=True)``. ``k`` and ``pk`` are also passed
through ``E``; for every value the schema admits that is the identity, so the
bytes match the grammar, and a value outside the schema still cannot break out
of its attribute.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Final, Literal, NoReturn, Protocol

WRITE_SANITIZER_POLICY: Final[str] = "antiek-write-revision-escape"
WRITE_SANITIZER_VERSION: Final[str] = "1"
MANIFEST_SCHEMA: Final[str] = "antiek.write_revision.v1"
PROSE_BLOCK_PREFIX: Final[str] = "sprose:"

SourceKind = Literal["user", "unresolved"]
UnresolvedReason = Literal["no_provenance", "projection_missing", "source_missing"]

_PARAGRAPH_BREAK: Final[re.Pattern[str]] = re.compile(r"\n[ \t]*\n")
# The operator sentinel names no investigation, so it is never a recorded thread.
_NOT_A_THREAD: Final[frozenset[str]] = frozenset({"__operator__"})
_ATTRIBUTION_TABLE: Final[str] = "outline_block_attribution"


class DeliverableNotFound(LookupError):
    """No deliverable has the requested id."""


class CanonicalHtmlError(ValueError):
    """The HTML is not canonical Write revision HTML for the given inventory."""


class SqlReader(Protocol):
    """The one connection method the snapshot uses. DuckDB connections,
    ``LockedConnection`` and the read-only fallback all satisfy it."""

    def execute(self, sql: str, parameters: Sequence[Any] | None = None, /) -> Any: ...


@dataclass(frozen=True)
class SnapshotBlock:
    block_id: str
    section_id: str
    role: Literal["prose", "outline"]
    block_kind: str | None
    provenance_kind: str | None
    text: str


@dataclass(frozen=True)
class MemberRow:
    member_index: int
    member_key: str
    source_kind: SourceKind
    block_id: str
    unresolved_reason: str | None
    source_document_id: str | None
    investigation_id: str | None


@dataclass(frozen=True)
class WriteSnapshot:
    deliverable_id: str
    title: str
    canonical_html: str
    manifest_json: str
    blocks: tuple[SnapshotBlock, ...]
    members: tuple[MemberRow, ...]
    content_sha256: str
    manifest_sha256: str


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _e(value: str) -> str:
    return html.escape(value, quote=True)


def _nfc(value: str | None) -> str:
    return unicodedata.normalize("NFC", value) if value else ""


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def member_key(parts: Sequence[str | None]) -> str:
    """Lowercase-hex sha256 of the compact JSON array of ``parts`` as UTF-8
    (THREAD-CONTRACT §1.11: ``[source_kind, block_id]`` for user and
    unresolved members)."""
    encoded = json.dumps(list(parts), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _paragraphs(prose: str) -> list[str]:
    """Paragraphs of already-NFC prose: split on a blank line, stripped,
    empties dropped."""
    return [p.strip() for p in _PARAGRAPH_BREAK.split(prose) if p.strip()]


# ---------------------------------------------------------------------------
# Reads (SELECT only, on the caller's connection)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Section:
    section_id: str
    parent_section_id: str | None
    section_index: int
    title: str | None
    prose_text: str | None
    prose_generated: bool


@dataclass(frozen=True)
class _OutlineRow:
    outline_block_id: str
    section_id: str
    block_kind: str
    provenance_kind: str
    node_id: str | None
    content: str | None
    metadata: str | None
    block_index: int


@dataclass(frozen=True)
class _Node:
    label: str
    own_chunk_id: str | None


def _section_key(section: _Section) -> tuple[int, str]:
    return (section.section_index, section.section_id)


def _block_key(row: _OutlineRow) -> tuple[int, str]:
    return (row.block_index, row.outline_block_id)


def _read_sections(con: SqlReader, deliverable_id: str) -> list[tuple[_Section, int]]:
    """Sections in ``build_outline_tree`` pre-order, each with its depth."""
    rows = con.execute(
        "SELECT section_id, parent_section_id, section_index, title, prose_text, "
        "prose_provenance IS NOT NULL "
        "FROM deliverable_sections WHERE deliverable_id = ?",
        [deliverable_id],
    ).fetchall()
    sections = {
        str(r[0]): _Section(
            section_id=str(r[0]),
            parent_section_id=r[1],
            section_index=int(r[2]),
            title=r[3],
            prose_text=r[4],
            prose_generated=bool(r[5]),
        )
        for r in rows
    }
    roots: list[_Section] = []
    children: dict[str, list[_Section]] = {}
    for section in sections.values():
        parent = section.parent_section_id
        if parent and parent in sections:
            children.setdefault(parent, []).append(section)
        else:
            roots.append(section)

    ordered: list[tuple[_Section, int]] = []
    stack: list[tuple[_Section, int]] = [
        (s, 0) for s in sorted(roots, key=_section_key, reverse=True)
    ]
    while stack:
        section, depth = stack.pop()
        ordered.append((section, depth))
        kids = sorted(children.get(section.section_id, []), key=_section_key, reverse=True)
        stack.extend((kid, depth + 1) for kid in kids)
    return ordered


def _read_outline_blocks(con: SqlReader, deliverable_id: str) -> dict[str, list[_OutlineRow]]:
    rows = con.execute(
        "SELECT outline_block_id, section_id, block_kind, provenance_kind, node_id, "
        "content, metadata, block_index FROM outline_blocks "
        "WHERE section_id IN (SELECT section_id FROM deliverable_sections "
        "WHERE deliverable_id = ?)",
        [deliverable_id],
    ).fetchall()
    by_section: dict[str, list[_OutlineRow]] = {}
    for r in rows:
        row = _OutlineRow(
            outline_block_id=str(r[0]),
            section_id=str(r[1]),
            block_kind=str(r[2]),
            provenance_kind=str(r[3]),
            node_id=r[4],
            content=r[5],
            metadata=r[6],
            block_index=int(r[7]),
        )
        by_section.setdefault(row.section_id, []).append(row)
    for blocks in by_section.values():
        blocks.sort(key=_block_key)
    return by_section


def _own_chunk_id(metadata_text: str | None) -> str | None:
    """The chunk a node names in its OWN metadata, or None."""
    if not metadata_text:
        return None
    try:
        meta = json.loads(metadata_text)
    except (json.JSONDecodeError, TypeError):
        return None
    chunk_id = meta.get("chunk_id") if isinstance(meta, dict) else None
    return chunk_id if isinstance(chunk_id, str) and chunk_id else None


def _read_nodes(con: SqlReader, node_ids: Sequence[str]) -> dict[str, _Node]:
    if not node_ids:
        return {}
    rows = con.execute(
        "SELECT node_id, canonical_label, metadata FROM nodes "
        "WHERE node_id IN (SELECT UNNEST(?::VARCHAR[]))",
        [list(node_ids)],
    ).fetchall()
    return {
        str(r[0]): _Node(label=_nfc(r[1]), own_chunk_id=_own_chunk_id(r[2]))
        for r in rows
    }


def _read_chunk_documents(con: SqlReader, chunk_ids: Sequence[str]) -> dict[str, str]:
    if not chunk_ids:
        return {}
    rows = con.execute(
        "SELECT chunk_id, document_id FROM chunks "
        "WHERE chunk_id IN (SELECT UNNEST(?::VARCHAR[]))",
        [list(chunk_ids)],
    ).fetchall()
    return {str(r[0]): str(r[1]) for r in rows if r[1]}


def _read_attribution(con: SqlReader, outline_block_ids: Sequence[str]) -> dict[str, str]:
    """Recorded threads from ``outline_block_attribution`` (added by W3-1).

    Absent table → no thread for any block. Presence is probed through the
    catalog rather than by querying the table, because a failing statement
    inside the W3-3 write transaction would abort that transaction."""
    if not outline_block_ids:
        return {}
    columns = {
        str(r[0])
        for r in con.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_catalog = current_database() "
            "AND table_schema = current_schema() AND table_name = ?",
            [_ATTRIBUTION_TABLE],
        ).fetchall()
    }
    if not {"outline_block_id", "investigation_id"} <= columns:
        return {}
    rows = con.execute(
        f"SELECT outline_block_id, investigation_id FROM {_ATTRIBUTION_TABLE} "
        "WHERE outline_block_id IN (SELECT UNNEST(?::VARCHAR[]))",
        [list(outline_block_ids)],
    ).fetchall()
    return {
        str(r[0]): str(r[1])
        for r in rows
        if isinstance(r[1], str) and r[1] and r[1] not in _NOT_A_THREAD
    }


# ---------------------------------------------------------------------------
# Classification (PR W3-2 table)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Classification:
    source_kind: SourceKind
    unresolved_reason: UnresolvedReason | None = None
    source_document_id: str | None = None


_USER: Final[_Classification] = _Classification("user")
_NO_PROVENANCE: Final[_Classification] = _Classification("unresolved", "no_provenance")


def _is_migrated_or_unreadable(metadata_text: str | None) -> bool:
    """True for a migrated placeholder (``metadata.migrated_from`` present) and,
    failing closed, for metadata that cannot be read."""
    if not metadata_text:
        return False
    try:
        meta = json.loads(metadata_text)
    except (json.JSONDecodeError, TypeError):
        return True
    return isinstance(meta, dict) and "migrated_from" in meta


def _classify_outline(
    row: _OutlineRow, nodes: Mapping[str, _Node], chunk_documents: Mapping[str, str],
) -> _Classification:
    if row.provenance_kind == "graph_node":
        if not row.node_id:
            return _NO_PROVENANCE
        node = nodes.get(row.node_id)
        if node is None:
            return _Classification("unresolved", "source_missing")
        document_id = chunk_documents.get(node.own_chunk_id) if node.own_chunk_id else None
        if document_id is None:
            return _NO_PROVENANCE
        return _Classification("unresolved", "projection_missing", document_id)
    if row.provenance_kind == "user_authored" and not _is_migrated_or_unreadable(row.metadata):
        return _USER
    # synthesized, brainstorm, migrated placeholders and any unknown kind.
    return _NO_PROVENANCE


def _classify_prose(section: _Section) -> _Classification:
    return _NO_PROVENANCE if section.prose_generated else _USER


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


def snapshot_deliverable(con: SqlReader, deliverable_id: str) -> WriteSnapshot:
    """Render and classify the current canonical body of ``deliverable_id``.

    SELECT-only on ``con``. Deterministic: equal database content yields equal
    bytes in any process. The output is re-parsed by ``verify_canonical_html``
    before it is returned. Raises ``DeliverableNotFound`` for an unknown id."""
    row = con.execute(
        "SELECT title FROM deliverables WHERE deliverable_id = ?", [deliverable_id],
    ).fetchone()
    if row is None:
        raise DeliverableNotFound(deliverable_id)
    title = _nfc(row[0])

    sections = _read_sections(con, deliverable_id)
    blocks_by_section = _read_outline_blocks(con, deliverable_id)
    placed = [
        b for section, _ in sections for b in blocks_by_section.get(section.section_id, [])
    ]
    nodes = _read_nodes(
        con,
        sorted({b.node_id for b in placed if b.provenance_kind == "graph_node" and b.node_id}),
    )
    chunk_documents = _read_chunk_documents(
        con, sorted({n.own_chunk_id for n in nodes.values() if n.own_chunk_id}),
    )
    attribution = _read_attribution(con, [b.outline_block_id for b in placed])

    parts: list[str] = [
        f'<article data-antiek-write="1" data-deliverable-id="{_e(deliverable_id)}">\n',
        f"<h1>{_e(title)}</h1>\n",
    ]
    blocks: list[SnapshotBlock] = []
    classified: list[tuple[str, _Classification, str | None]] = []

    for section, depth in sections:
        sid = section.section_id
        level = min(2 + depth, 6)
        parts.append(f'<section data-section-id="{_e(sid)}" data-depth="{depth}">\n')
        parts.append(f"<h{level}>{_e(_nfc(section.title))}</h{level}>\n")

        prose = _nfc(section.prose_text)
        paragraphs = _paragraphs(prose)
        if paragraphs:
            block_id = PROSE_BLOCK_PREFIX + sid
            parts.append(
                f'<div data-block-id="{_e(block_id)}" data-block-role="prose">'
                + "".join(f"<p>{_e(p)}</p>" for p in paragraphs)
                + "</div>\n"
            )
            blocks.append(SnapshotBlock(block_id, sid, "prose", None, None, prose))
            classified.append((block_id, _classify_prose(section), None))

        for b in blocks_by_section.get(sid, []):
            if b.provenance_kind == "graph_node":
                node = nodes.get(b.node_id) if b.node_id else None
                text = node.label if node is not None else ""
            else:
                text = _nfc(b.content)
            parts.append(
                f'<div data-block-id="{_e(b.outline_block_id)}" '
                f'data-block-kind="{_e(b.block_kind)}" '
                f'data-provenance-kind="{_e(b.provenance_kind)}">'
                + (f"<p>{_e(text)}</p>" if text else "")
                + "</div>\n"
            )
            blocks.append(
                SnapshotBlock(b.outline_block_id, sid, "outline", b.block_kind,
                              b.provenance_kind, text)
            )
            classification = _classify_outline(b, nodes, chunk_documents)
            classified.append(
                (b.outline_block_id, classification, attribution.get(b.outline_block_id))
            )

        parts.append("</section>\n")
    parts.append("</article>\n")
    canonical_html = "".join(parts)

    members = tuple(
        MemberRow(
            member_index=index,
            member_key=member_key([c.source_kind, block_id]),
            source_kind=c.source_kind,
            block_id=block_id,
            unresolved_reason=c.unresolved_reason,
            source_document_id=c.source_document_id,
            # A user member never carries a thread (§1.11 user CHECK).
            investigation_id=(recorded if c.source_kind == "unresolved" else None),
        )
        for index, (block_id, c, recorded) in enumerate(classified)
    )
    manifest_json = _canonical_json(
        {
            "schema": MANIFEST_SCHEMA,
            "deliverable_id": deliverable_id,
            "blocks": [
                {
                    "block_id": b.block_id,
                    "section_id": b.section_id,
                    "role": b.role,
                    "block_kind": b.block_kind,
                    "provenance_kind": b.provenance_kind,
                    "text_sha256": _sha256_text(b.text),
                }
                for b in blocks
            ],
            "members": [
                {
                    "member_index": m.member_index,
                    "member_key": m.member_key,
                    "source_kind": m.source_kind,
                    "block_id": m.block_id,
                    "unresolved_reason": m.unresolved_reason,
                    "source_document_id": m.source_document_id,
                    "investigation_id": m.investigation_id,
                }
                for m in members
            ],
        }
    )
    verify_canonical_html(canonical_html, [b.block_id for b in blocks])
    return WriteSnapshot(
        deliverable_id=deliverable_id,
        title=title,
        canonical_html=canonical_html,
        manifest_json=manifest_json,
        blocks=tuple(blocks),
        members=members,
        content_sha256=_sha256_text(canonical_html),
        manifest_sha256=_sha256_text(manifest_json),
    )


# ---------------------------------------------------------------------------
# Allowlist verifier
# ---------------------------------------------------------------------------

_HEADINGS: Final[frozenset[str]] = frozenset({"h2", "h3", "h4", "h5", "h6"})
_TEXT_ELEMENTS: Final[frozenset[str]] = _HEADINGS | {"h1", "p"}
_ARTICLE_ATTRS: Final[frozenset[str]] = frozenset({"data-antiek-write", "data-deliverable-id"})
_SECTION_ATTRS: Final[frozenset[str]] = frozenset({"data-section-id", "data-depth"})
_PROSE_ATTRS: Final[frozenset[str]] = frozenset({"data-block-id", "data-block-role"})
_OUTLINE_ATTRS: Final[frozenset[str]] = frozenset(
    {"data-block-id", "data-block-kind", "data-provenance-kind"}
)
_DEPTH: Final[re.Pattern[str]] = re.compile(r"0|[1-9][0-9]*")


@dataclass
class _Open:
    tag: str
    children: int = 0
    text: str = ""
    section_id: str = ""
    depth: int = 0
    prose: bool = False


class _CanonicalParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_Open] = []
        self.block_ids: list[str] = []
        self.seen_article = False
        self.last_depth: int | None = None

    def _fail(self, reason: str) -> NoReturn:
        raise CanonicalHtmlError(f"{reason} (line {self.getpos()[0]})")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        names = [name for name, _ in attrs]
        if len(set(names)) != len(names):
            self._fail(f"duplicate attribute on <{tag}>")
        values: dict[str, str] = {}
        for name, value in attrs:
            if value is None:
                self._fail(f"attribute {name!r} on <{tag}> has no value")
            values[name] = value
        parent = self.stack[-1] if self.stack else None
        node = _Open(tag)

        if tag == "article":
            if parent is not None or self.seen_article:
                self._fail("<article> must be the single root")
            if set(values) != _ARTICLE_ATTRS or values["data-antiek-write"] != "1":
                self._fail("<article> attributes are not canonical")
            self.seen_article = True
        elif tag == "h1":
            if parent is None or parent.tag != "article" or parent.children != 0 or values:
                self._fail("<h1> must be the article's first child, without attributes")
        elif tag == "section":
            if parent is None or parent.tag != "article" or parent.children == 0:
                self._fail("<section> must follow the article title")
            if set(values) != _SECTION_ATTRS or not _DEPTH.fullmatch(values["data-depth"]):
                self._fail("<section> attributes are not canonical")
            node.section_id = values["data-section-id"]
            node.depth = int(values["data-depth"])
            limit = 0 if self.last_depth is None else self.last_depth + 1
            if node.depth > limit:
                self._fail("section depth skips a level")
            self.last_depth = node.depth
        elif tag in _HEADINGS:
            if parent is None or parent.tag != "section" or parent.children != 0 or values:
                self._fail(f"<{tag}> must be the section's first child, without attributes")
            elif tag != f"h{min(2 + parent.depth, 6)}":
                self._fail(f"<{tag}> does not match data-depth={parent.depth}")
        elif tag == "div":
            if parent is None or parent.tag != "section" or parent.children == 0:
                self._fail("<div> must follow its section heading")
            elif set(values) == _PROSE_ATTRS:
                if values["data-block-role"] != "prose" or parent.children != 1:
                    self._fail("the prose block must be the section's first block")
                if values["data-block-id"] != PROSE_BLOCK_PREFIX + parent.section_id:
                    self._fail("the prose block id does not name its section")
                node.prose = True
            elif set(values) != _OUTLINE_ATTRS:
                self._fail("<div> attributes are not canonical")
            self.block_ids.append(values["data-block-id"])
        elif tag == "p":
            if parent is None or parent.tag != "div" or (not parent.prose and parent.children):
                self._fail("<p> must sit in a block (one per outline block)")
            if values:
                self._fail("<p> takes no attributes")
        else:
            self._fail(f"tag <{tag}> is not allowed")

        if parent is not None:
            parent.children += 1
        self.stack.append(node)

    def handle_endtag(self, tag: str) -> None:
        if not self.stack or self.stack[-1].tag != tag:
            self._fail(f"unexpected </{tag}>")
        node = self.stack.pop()
        if tag == "p" and not node.text:
            self._fail("empty paragraph")
        if node.prose and node.children == 0:
            self._fail("prose block without a paragraph")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._fail(f"self-closing <{tag}/> is not allowed")

    def handle_data(self, data: str) -> None:
        top = self.stack[-1] if self.stack else None
        if top is not None and top.tag in _TEXT_ELEMENTS:
            top.text += data
        elif data.strip("\n"):
            self._fail("text outside a heading or paragraph")

    def handle_comment(self, data: str) -> None:
        self._fail("comments are not allowed")

    def handle_decl(self, decl: str) -> None:
        self._fail("declarations are not allowed")

    def handle_pi(self, data: str) -> None:
        self._fail("processing instructions are not allowed")

    def unknown_decl(self, data: str) -> None:
        self._fail("declarations are not allowed")


def verify_canonical_html(html: str, block_ids: Sequence[str]) -> None:
    """Re-parse ``html`` against the Write revision grammar's allowlist.

    Allows only ``article``, ``h1``-``h6``, ``section``, ``div`` and ``p``,
    each only where the grammar puts it and only with its listed ``data-*``
    attributes; no comments, declarations or self-closing tags; text only in
    headings and paragraphs. The ``data-block-id`` sequence must equal
    ``block_ids`` exactly, with no duplicates. Raises ``CanonicalHtmlError``."""
    if not html.startswith("<article "):
        raise CanonicalHtmlError("document must start with <article>")
    parser = _CanonicalParser()
    parser.feed(html)
    parser.close()
    if not parser.seen_article or parser.stack:
        raise CanonicalHtmlError("document is not one closed <article>")
    if not html.endswith("</article>\n"):
        raise CanonicalHtmlError("document must end with </article> and a line feed")
    if len(set(parser.block_ids)) != len(parser.block_ids):
        raise CanonicalHtmlError("duplicate data-block-id")
    if parser.block_ids != list(block_ids):
        raise CanonicalHtmlError("data-block-id sequence does not equal the inventory")


__all__ = [
    "MANIFEST_SCHEMA",
    "PROSE_BLOCK_PREFIX",
    "WRITE_SANITIZER_POLICY",
    "WRITE_SANITIZER_VERSION",
    "CanonicalHtmlError",
    "DeliverableNotFound",
    "MemberRow",
    "SnapshotBlock",
    "SqlReader",
    "WriteSnapshot",
    "member_key",
    "snapshot_deliverable",
    "verify_canonical_html",
]
