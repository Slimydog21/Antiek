"""Deterministic, inert canonicalization for reviewed HTML projections."""

from __future__ import annotations

import hashlib
import html
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Final
from urllib.parse import urlsplit

POLICY: Final = "antiek-derived-asset-merge"
VERSION: Final = "1"
MAX_MEMBER_BYTES: Final = 2 * 1024 * 1024
MAX_TOTAL_BYTES: Final = 8 * 1024 * 1024
MAX_NODES: Final = 100_000
MAX_DEPTH: Final = 128
MAX_MEMBERS: Final = 64

_VOID = frozenset({"br", "hr"})
_SHELL_VOID = frozenset({"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"})
_TAGS = frozenset(
    {
        "article",
        "aside",
        "blockquote",
        "br",
        "caption",
        "code",
        "dd",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "li",
        "main",
        "mark",
        "nav",
        "ol",
        "p",
        "pre",
        "section",
        "small",
        "span",
        "strong",
        "sub",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "tr",
        "ul",
        "a",
    }
)
_ATTRS = frozenset({"class", "id", "title", "lang", "dir", "colspan", "rowspan", "scope"})


class CanonicalMergeError(ValueError):
    """Input cannot be represented by the closed canonical policy."""


@dataclass
class _Node:
    tag: str | None
    attrs: dict[str, str] = field(default_factory=dict)
    children: list[_Node | str] = field(default_factory=list)


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = _Node(None)
        self.stack = [self.root]
        self.nodes = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag not in _TAGS:
            raise CanonicalMergeError(f"element is not allowed: {tag}")
        self.nodes += 1
        if self.nodes > MAX_NODES:
            raise CanonicalMergeError("node ceiling exceeded")
        if len(self.stack) > MAX_DEPTH:
            raise CanonicalMergeError("depth ceiling exceeded")
        clean: dict[str, str] = {}
        for raw_name, raw_value in attrs:
            name = raw_name.lower()
            if raw_value is None or name in clean or name.startswith("on") or name == "style":
                raise CanonicalMergeError("attribute is not allowed")
            if name not in _ATTRS and not (tag == "a" and name in {"href", "rel"}):
                raise CanonicalMergeError(f"attribute is not allowed: {name}")
            if any(ord(character) < 32 or ord(character) == 127 for character in raw_value):
                raise CanonicalMergeError("attribute contains a control character")
            clean[name] = raw_value
        node = _Node(tag, clean)
        self.stack[-1].children.append(node)
        if tag not in _VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag.lower() not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _VOID or len(self.stack) == 1 or self.stack[-1].tag != tag:
            raise CanonicalMergeError("malformed or mismatched HTML")
        self.stack.pop()

    def handle_data(self, data: str) -> None:
        self.stack[-1].children.append(data)

    def handle_comment(self, data: str) -> None:
        return

    def handle_decl(self, decl: str) -> None:
        raise CanonicalMergeError("document declarations are not allowed")

    def handle_entityref(self, name: str) -> None:  # pragma: no cover - converted by parser
        raise AssertionError(name)

    def unknown_decl(self, data: str) -> None:
        raise CanonicalMergeError("unknown declaration")

    def close_checked(self) -> _Node:
        try:
            super().close()
        except (AssertionError, EOFError) as exc:
            raise CanonicalMergeError("malformed HTML") from exc
        if len(self.stack) != 1:
            raise CanonicalMergeError("unclosed HTML element")
        return self.root


class _ProjectionBodyExtractor(HTMLParser):
    """Remove the renderer-owned document shell and inert model island."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.state = "start"
        self.head_stack: list[str] = []
        self.body_stack: list[str] = []
        self.skip_template = 0
        self.output: list[str] = []

    def handle_decl(self, decl: str) -> None:
        if self.state != "start" or decl.strip().lower() != "doctype html":
            raise CanonicalMergeError("invalid projection document declaration")
        self.state = "doctype"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if self.state == "doctype":
            if tag != "html":
                raise CanonicalMergeError("projection document is missing html shell")
            self.state = "html"
            return
        if self.state == "html":
            if tag != "head":
                raise CanonicalMergeError("projection document is missing head")
            self.state = "head"
            return
        if self.state == "head":
            if tag in {"html", "head", "body"}:
                raise CanonicalMergeError("malformed projection head")
            if tag not in _SHELL_VOID:
                self.head_stack.append(tag)
            return
        if self.state == "after_head":
            if tag != "body":
                raise CanonicalMergeError("projection document is missing body")
            self.state = "body"
            return
        if self.state != "body" or tag in {"html", "head", "body"}:
            raise CanonicalMergeError("malformed projection document shell")
        if self.skip_template:
            if tag == "template":
                self.skip_template += 1
            return
        if tag == "template":
            self.skip_template = 1
            return
        self.output.append(f"<{tag}{_raw_attrs(attrs)}>")
        if tag not in _SHELL_VOID:
            self.body_stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if self.state == "body" and not self.skip_template and tag.lower() not in _SHELL_VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self.state == "head":
            if tag == "head" and not self.head_stack:
                self.state = "after_head"
                return
            if not self.head_stack or self.head_stack.pop() != tag:
                raise CanonicalMergeError("malformed projection head")
            return
        if self.state == "body":
            if self.skip_template:
                if tag == "template":
                    self.skip_template -= 1
                return
            if tag == "body" and not self.body_stack:
                self.state = "after_body"
                return
            if not self.body_stack or self.body_stack.pop() != tag:
                raise CanonicalMergeError("malformed projection body")
            self.output.append(f"</{tag}>")
            return
        if self.state == "after_body" and tag == "html":
            self.state = "done"
            return
        raise CanonicalMergeError("malformed projection document shell")

    def handle_data(self, data: str) -> None:
        if self.state in {"start", "doctype", "html", "after_head", "after_body", "done"}:
            if data.strip():
                raise CanonicalMergeError("text outside projection body")
        elif self.state == "body" and not self.skip_template:
            self.output.append(html.escape(data, quote=False))

    def handle_entityref(self, name: str) -> None:
        if self.state == "body" and not self.skip_template:
            self.output.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self.state == "body" and not self.skip_template:
            self.output.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        return

    def unknown_decl(self, data: str) -> None:
        raise CanonicalMergeError("unknown projection declaration")

    def close_checked(self) -> str:
        super().close()
        if self.state != "done" or self.head_stack or self.body_stack or self.skip_template:
            raise CanonicalMergeError("unclosed projection document shell")
        return "".join(self.output)


@dataclass(frozen=True)
class CanonicalMember:
    projection_id: str
    source_asset_id: str
    source_document_id: str
    source_sha256: str
    hosted_html_sha256: str
    html_bytes: bytes


@dataclass(frozen=True)
class CanonicalMerge:
    html: str
    sha256: str
    byte_count: int
    policy: str = POLICY
    version: str = VERSION


def canonicalize_members(members: tuple[CanonicalMember, ...]) -> CanonicalMerge:
    if not members or len(members) > MAX_MEMBERS:
        raise CanonicalMergeError("member count is outside the allowed range")
    if len({member.projection_id for member in members}) != len(members):
        raise CanonicalMergeError("projection IDs must be unique")
    if sum(len(member.html_bytes) for member in members) > MAX_TOTAL_BYTES:
        raise CanonicalMergeError("total byte ceiling exceeded")
    rendered: list[str] = []
    for index, member in enumerate(members):
        if len(member.html_bytes) > MAX_MEMBER_BYTES:
            raise CanonicalMergeError("member byte ceiling exceeded")
        try:
            source = member.html_bytes.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CanonicalMergeError("member is not valid UTF-8") from exc
        parser = _Parser()
        try:
            parser.feed(_projection_fragment(source))
            root = parser.close_checked()
        except (CanonicalMergeError, UnicodeError) as exc:
            raise CanonicalMergeError(str(exc)) from exc
        prefix = f"m{index}-{hashlib.sha256(member.projection_id.encode()).hexdigest()[:16]}-"
        _rewrite_and_validate(root, prefix)
        attrs = {
            "data-member-index": str(index),
            "data-projection-id": member.projection_id,
            "data-source-asset-id": member.source_asset_id,
            "data-source-document-id": member.source_document_id,
            "data-source-sha256": member.source_sha256,
            "data-hosted-html-sha256": member.hosted_html_sha256,
        }
        rendered.append(f"<section{_attrs(attrs)}>{_serialize_children(root)}</section>")
    body = "".join(rendered)
    result = (
        '<article data-antiek-canonical-policy="'
        + POLICY
        + '" data-antiek-canonical-version="'
        + VERSION
        + '">'
        + body
        + "</article>"
    )
    encoded = result.encode("utf-8")
    return CanonicalMerge(result, hashlib.sha256(encoded).hexdigest(), len(encoded))


def _rewrite_and_validate(root: _Node, prefix: str) -> None:
    ids: set[str] = set()
    nodes: list[_Node] = []
    todo = [child for child in reversed(root.children) if isinstance(child, _Node)]
    while todo:
        node = todo.pop()
        nodes.append(node)
        raw_id = node.attrs.get("id")
        if raw_id is not None:
            if not raw_id or raw_id in ids:
                raise CanonicalMergeError("empty or duplicate anchor ID")
            ids.add(raw_id)
            node.attrs["id"] = prefix + hashlib.sha256(raw_id.encode()).hexdigest()
        todo.extend(child for child in reversed(node.children) if isinstance(child, _Node))
    for node in nodes:
        href = node.attrs.get("href")
        if href is None:
            continue
        if href.startswith("#"):
            target = href[1:]
            if not target or target not in ids:
                raise CanonicalMergeError("fragment link has no local target")
            node.attrs["href"] = "#" + prefix + hashlib.sha256(target.encode()).hexdigest()
        else:
            if "\\" in href or any(character.isspace() for character in href):
                raise CanonicalMergeError("URL contains an unsafe character")
            try:
                split = urlsplit(href)
                _ = split.port
            except ValueError as exc:
                raise CanonicalMergeError("URL is malformed") from exc
            if split.scheme.lower() not in {"http", "https", "mailto"}:
                raise CanonicalMergeError("URL scheme is not allowed")
            if split.scheme.lower() in {"http", "https"}:
                if not split.netloc or split.hostname is None:
                    raise CanonicalMergeError("absolute HTTP(S) URL required")
                if split.username is not None or split.password is not None:
                    raise CanonicalMergeError("URL user information is not allowed")
            if split.scheme.lower() == "mailto" and not split.path:
                raise CanonicalMergeError("mailto URL requires a recipient")
        node.attrs["rel"] = "noreferrer noopener"


def _attrs(attrs: dict[str, str]) -> str:
    return "".join(
        f' {name}="{html.escape(value, quote=True)}"' for name, value in sorted(attrs.items())
    )


def _raw_attrs(attrs: list[tuple[str, str | None]]) -> str:
    rendered: list[str] = []
    seen: set[str] = set()
    for raw_name, raw_value in attrs:
        name = raw_name.lower()
        if raw_value is None or name in seen:
            raise CanonicalMergeError("malformed projection attribute")
        seen.add(name)
        rendered.append(f' {name}="{html.escape(raw_value, quote=True)}"')
    return "".join(rendered)


def _projection_fragment(source: str) -> str:
    if not source.lstrip().lower().startswith("<!doctype html>"):
        return source
    extractor = _ProjectionBodyExtractor()
    extractor.feed(source)
    return extractor.close_checked()


def _serialize_children(node: _Node) -> str:
    output: list[str] = []
    for child in node.children:
        if isinstance(child, str):
            output.append(html.escape(child, quote=False))
        else:
            output.append(f"<{child.tag}{_attrs(child.attrs)}>")
            if child.tag not in _VOID:
                output.append(_serialize_children(child))
                output.append(f"</{child.tag}>")
    return "".join(output)


__all__ = [
    "CanonicalMember",
    "CanonicalMerge",
    "CanonicalMergeError",
    "POLICY",
    "VERSION",
    "canonicalize_members",
]
