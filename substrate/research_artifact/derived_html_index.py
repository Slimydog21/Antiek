"""Deterministic retrieval projection for canonical derived HTML revisions."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final

from services.html_projection.canonical_merge import POLICY, VERSION

CHUNKER_POLICY: Final = "antiek-derived-html-sections"
CHUNKER_VERSION: Final = "1"
MAX_HTML_BYTES: Final = 8 * 1024 * 1024
MAX_NODES: Final = 100_000
MAX_DEPTH: Final = 128
MAX_HEADINGS: Final = 4_000
MAX_BLOCKS: Final = 20_000
MAX_CHUNKS: Final = 4_000
MAX_CHUNK_TOKENS: Final = 600
MAX_CHUNK_TEXT_BYTES: Final = 128 * 1024
MAX_SECTION_PATH_BYTES: Final = 2 * 1024

_HEADING_LEVEL = {f"h{level}": level for level in range(1, 7)}
_BLOCK_TAGS = frozenset({
    "p", "pre", "figcaption", "dt", "dd", "caption", "th", "td", "li", "blockquote"
})
_INLINE_TEXT_TAGS = frozenset({
    "a", "abbr", "b", "cite", "code", "del", "dfn", "em", "i", "ins", "kbd", "mark",
    "q", "s", "samp", "small", "span", "strong", "sub", "sup", "time", "u", "var",
})
_ALLOWED_TAGS = frozenset({
    "a", "abbr", "article", "aside", "b", "blockquote", "br", "caption", "cite",
    "code", "dd", "del", "details", "dfn", "div", "dl", "dt", "em", "figcaption",
    "figure", "footer", "h1", "h2", "h3", "h4", "h5", "h6", "header", "hr", "i",
    "ins", "kbd", "li", "main", "mark", "nav", "ol", "p", "pre", "q", "s",
    "samp", "section", "small", "span", "strong", "sub", "summary", "sup", "table",
    "tbody", "td", "tfoot", "th", "thead", "time", "tr", "u", "ul", "var",
})
_SPACE = re.compile(r"\s+")


class DerivedHtmlIndexError(ValueError):
    """Canonical HTML cannot produce a complete bounded retrieval projection."""


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    children: list[_Node | str] = field(default_factory=list)


@dataclass(frozen=True)
class DerivedHtmlChunk:
    ordinal: int
    member_index: int
    section_anchor: str
    section_path: str
    text: str
    text_sha256: str
    token_count: int


class _TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node("__root__", {})
        self.stack = [self.root]
        self.node_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _ALLOWED_TAGS:
            raise DerivedHtmlIndexError(f"canonical HTML element is forbidden: {tag}")
        clean: dict[str, str] = {}
        for name, value in attrs:
            if value is None or name in clean:
                raise DerivedHtmlIndexError("canonical HTML has malformed attributes")
            clean[name.lower()] = value
        self.node_count += 1
        if self.node_count > MAX_NODES:
            raise DerivedHtmlIndexError("canonical HTML node ceiling exceeded")
        if len(self.stack) > MAX_DEPTH:
            raise DerivedHtmlIndexError("canonical HTML depth ceiling exceeded")
        node = _Node(tag, clean)
        self.stack[-1].children.append(node)
        if tag not in {"br", "hr"}:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in {"br", "hr"}:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if len(self.stack) == 1 or self.stack[-1].tag != tag.lower():
            raise DerivedHtmlIndexError("canonical HTML has mismatched elements")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        raise DerivedHtmlIndexError("canonical HTML declarations are forbidden")

    def close_checked(self) -> _Node:
        super().close()
        if len(self.stack) != 1:
            raise DerivedHtmlIndexError("canonical HTML has unclosed elements")
        if len(self.root.children) != 1 or not isinstance(self.root.children[0], _Node):
            raise DerivedHtmlIndexError("canonical HTML wrapper is missing")
        wrapper = self.root.children[0]
        if wrapper.tag != "article" or wrapper.attrs != {
            "data-antiek-canonical-policy": POLICY,
            "data-antiek-canonical-version": VERSION,
        }:
            raise DerivedHtmlIndexError("canonical HTML wrapper identity is invalid")
        return wrapper


def _text(node: _Node) -> str:
    values: list[str] = []
    todo: list[_Node | str] = list(reversed(node.children))
    while todo:
        value = todo.pop()
        if isinstance(value, str):
            values.append(value)
        elif value.tag == "br":
            values.append(" ")
        else:
            todo.extend(reversed(value.children))
    return _SPACE.sub(" ", "".join(values)).strip()


def _contains_nested_block(node: _Node) -> bool:
    todo = [child for child in node.children if isinstance(child, _Node)]
    while todo:
        child = todo.pop()
        if child.tag in _BLOCK_TAGS:
            return True
        todo.extend(grandchild for grandchild in child.children if isinstance(grandchild, _Node))
    return False


def _anchor(path: tuple[str, ...], occurrence: int) -> str:
    source = json.dumps([*path, occurrence], ensure_ascii=False, separators=(",", ":"))
    return "sec_" + hashlib.sha256(source.encode()).hexdigest()[:24]


def chunk_canonical_html(canonical_html: str) -> tuple[DerivedHtmlChunk, ...]:
    if not isinstance(canonical_html, str) or not canonical_html:
        raise DerivedHtmlIndexError("canonical HTML is empty")
    if len(canonical_html.encode("utf-8")) > MAX_HTML_BYTES:
        raise DerivedHtmlIndexError("canonical HTML byte ceiling exceeded")
    parser = _TreeParser()
    parser.feed(canonical_html)
    wrapper = parser.close_checked()

    projected: list[tuple[int, str, str, str]] = []
    heading_count = 0
    block_count = 0
    member_nodes = [child for child in wrapper.children if isinstance(child, _Node)]
    if len(member_nodes) != len(wrapper.children):
        raise DerivedHtmlIndexError("canonical HTML has text outside member sections")
    for expected_member_index, member in enumerate(member_nodes):
        if member.tag != "section" or member.attrs.get("data-member-index") != str(
            expected_member_index
        ):
            raise DerivedHtmlIndexError("canonical HTML member order is invalid")
        headings: list[str] = []
        active_anchor = f"member-{expected_member_index}"
        anchor_occurrences: dict[tuple[str, ...], int] = {}

        def walk(
            node: _Node,
            *,
            member_index: int = expected_member_index,
            member_headings: list[str] = headings,
            occurrences: dict[tuple[str, ...], int] = anchor_occurrences,
        ) -> None:
            nonlocal active_anchor, heading_count, block_count
            level = _HEADING_LEVEL.get(node.tag)
            if level is not None:
                heading_count += 1
                if heading_count > MAX_HEADINGS:
                    raise DerivedHtmlIndexError("canonical HTML heading ceiling exceeded")
                heading_text = _text(node)
                if heading_text:
                    del member_headings[level - 1:]
                    while len(member_headings) < level - 1:
                        member_headings.append("Untitled")
                    member_headings.append(heading_text)
                    path = tuple(member_headings)
                    occurrence = occurrences.get(path, 0)
                    occurrences[path] = occurrence + 1
                    active_anchor = node.attrs.get("id") or _anchor(path, occurrence)
                    projected.append((
                        member_index, active_anchor, " > ".join(path), heading_text
                    ))
                    return
            elif node.tag in _BLOCK_TAGS and not _contains_nested_block(node):
                block_count += 1
                if block_count > MAX_BLOCKS:
                    raise DerivedHtmlIndexError("canonical HTML block ceiling exceeded")
                value = _text(node)
                if value:
                    projected.append((
                        member_index, active_anchor, " > ".join(member_headings), value
                    ))
                    return
            inline_run: list[_Node | str] = []

            def flush_inline_run() -> None:
                nonlocal block_count
                if not inline_run:
                    return
                value = _text(_Node("__inline__", {}, list(inline_run)))
                inline_run.clear()
                if not value:
                    return
                block_count += 1
                if block_count > MAX_BLOCKS:
                    raise DerivedHtmlIndexError("canonical HTML block ceiling exceeded")
                projected.append((
                    member_index, active_anchor, " > ".join(member_headings), value
                ))

            for child in node.children:
                if isinstance(child, str) or child.tag in _INLINE_TEXT_TAGS or child.tag == "br":
                    inline_run.append(child)
                elif child.tag != "hr":
                    flush_inline_run()
                    walk(child)
            flush_inline_run()

        walk(member)
    packed: list[tuple[int, str, str, list[str]]] = []
    for member_index, section_anchor, section_path, value in projected:
        words = value.split()
        if not words:
            continue
        for start in range(0, len(words), MAX_CHUNK_TOKENS):
            segment = " ".join(words[start:start + MAX_CHUNK_TOKENS])
            if (packed and packed[-1][0] == member_index
                    and packed[-1][1] == section_anchor
                    and sum(len(part.split()) for part in packed[-1][3]) + len(segment.split())
                    <= MAX_CHUNK_TOKENS):
                packed[-1][3].append(segment)
            else:
                packed.append((member_index, section_anchor, section_path, [segment]))
            if len(packed) > MAX_CHUNKS:
                raise DerivedHtmlIndexError("derived HTML chunk ceiling exceeded")

    chunks: list[DerivedHtmlChunk] = []
    for ordinal, (member_index, section_anchor, section_path, parts) in enumerate(packed):
        text = "\n\n".join(parts)
        if len(text.encode("utf-8")) > MAX_CHUNK_TEXT_BYTES:
            raise DerivedHtmlIndexError("derived HTML chunk byte ceiling exceeded")
        if len(section_path.encode("utf-8")) > MAX_SECTION_PATH_BYTES:
            raise DerivedHtmlIndexError("derived HTML section path ceiling exceeded")
        chunks.append(DerivedHtmlChunk(
            ordinal=ordinal,
            member_index=member_index,
            section_anchor=section_anchor,
            section_path=section_path,
            text=text,
            text_sha256=hashlib.sha256(text.encode()).hexdigest(),
            token_count=len(text.split()),
        ))
    return tuple(chunks)


def revision_chunk_id(
    *,
    asset_id: str,
    revision_id: str,
    content_sha256: str,
    chunker_policy: str,
    chunker_version: str,
    chunk: DerivedHtmlChunk,
) -> str:
    identity = json.dumps({
        "asset_id": asset_id,
        "chunker_policy": chunker_policy,
        "chunker_version": chunker_version,
        "content_sha256": content_sha256,
        "ordinal": chunk.ordinal,
        "member_index": chunk.member_index,
        "revision_id": revision_id,
        "section_anchor": chunk.section_anchor,
        "text_sha256": chunk.text_sha256,
    }, sort_keys=True, separators=(",", ":"))
    return "dchunk_" + hashlib.sha256(identity.encode()).hexdigest()


def index_sha256(chunks: tuple[DerivedHtmlChunk, ...]) -> str:
    value = json.dumps([
        {
            "ordinal": chunk.ordinal,
            "member_index": chunk.member_index,
            "section_anchor": chunk.section_anchor,
            "section_path": chunk.section_path,
            "text_sha256": chunk.text_sha256,
            "token_count": chunk.token_count,
        }
        for chunk in chunks
    ], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode()).hexdigest()


def chunks_for_policy(
    policy: str, version: str, canonical_html: str
) -> tuple[DerivedHtmlChunk, ...]:
    """Dispatch immutable persisted chunker identities without reinterpretation."""
    if (policy, version) != ("antiek-derived-html-sections", "1"):
        raise DerivedHtmlIndexError("derived HTML chunker identity is unsupported")
    return chunk_canonical_html(canonical_html)


def publish_revision_index(
    con: object,
    *,
    asset_id: str,
    revision_id: str,
    content_sha256: str,
    canonical_html: str,
) -> tuple[DerivedHtmlChunk, ...]:
    """Publish a complete lexical projection inside the caller's revision transaction."""
    chunks = chunk_canonical_html(canonical_html)
    for chunk in chunks:
        con.execute(
            "INSERT INTO derived_asset_revision_chunks "
            "(derived_asset_id,revision_id,revision_content_sha256,chunk_ordinal,citation_id,"
            "member_index,section_anchor,section_path,chunk_text,chunk_text_sha256,token_count,"
            "chunker_policy,chunker_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                asset_id,
                revision_id,
                content_sha256,
                chunk.ordinal,
                revision_chunk_id(
                    asset_id=asset_id,
                    revision_id=revision_id,
                    content_sha256=content_sha256,
                    chunker_policy=CHUNKER_POLICY,
                    chunker_version=CHUNKER_VERSION,
                    chunk=chunk,
                ),
                chunk.member_index,
                chunk.section_anchor,
                chunk.section_path,
                chunk.text,
                chunk.text_sha256,
                chunk.token_count,
                CHUNKER_POLICY,
                CHUNKER_VERSION,
            ],
        )
    con.execute(
        "INSERT INTO derived_asset_revision_indexes "
        "(derived_asset_id,revision_id,revision_content_sha256,chunk_count,index_sha256,"
        "chunker_policy,chunker_version) VALUES (?,?,?,?,?,?,?)",
        [
            asset_id,
            revision_id,
            content_sha256,
            len(chunks),
            index_sha256(chunks),
            CHUNKER_POLICY,
            CHUNKER_VERSION,
        ],
    )
    return chunks


def backfill_missing_revision_indexes(con: object) -> int:
    """Index pre-projection revisions during the one-time schema upgrade path."""
    rows = con.execute(
        "SELECT r.derived_asset_id,r.revision_id,r.content_sha256,r.canonical_html "
        "FROM derived_asset_revisions r LEFT JOIN derived_asset_revision_indexes i "
        "ON i.derived_asset_id=r.derived_asset_id AND i.revision_id=r.revision_id "
        "WHERE i.revision_id IS NULL ORDER BY r.derived_asset_id,r.created_at,r.revision_id"
    ).fetchall()
    for asset_id, revision_id, content_sha256, canonical_html in rows:
        publish_revision_index(
            con,
            asset_id=str(asset_id),
            revision_id=str(revision_id),
            content_sha256=str(content_sha256),
            canonical_html=str(canonical_html),
        )
    return len(rows)
