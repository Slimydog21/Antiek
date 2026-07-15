from __future__ import annotations

import hashlib

import pytest

from services.html_projection import RenderContext, render
from services.html_projection.canonical_merge import (
    CanonicalMember,
    CanonicalMergeError,
    canonicalize_members,
)


def member(body: bytes, projection_id: str = "projection-a") -> CanonicalMember:
    digest = hashlib.sha256(body).hexdigest()
    return CanonicalMember(projection_id, "asset-a", "document-a", "a" * 64, digest, body)


def test_canonical_bytes_are_deterministic_sorted_and_provenanced() -> None:
    source = b'<h2 title="T" class="lead" id="same">A &amp; B</h2><a href="#same">jump</a>'
    first = canonicalize_members((member(source),))
    second = canonicalize_members((member(source),))
    assert first == second
    assert hashlib.sha256(first.html.encode()).hexdigest() == first.sha256
    assert '<h2 class="lead" id="m0-' in first.html
    assert ' title="T">A &amp; B</h2>' in first.html
    assert 'data-projection-id="projection-a"' in first.html
    assert 'href="#m0-' in first.html


@pytest.mark.parametrize(
    "body",
    [
        b"<script>alert(1)</script>",
        b'<p onclick="x()">x</p>',
        b"<form><input></form>",
        b"<iframe></iframe>",
        b"<svg><script>x</script></svg>",
        b'<meta http-equiv="refresh" content="0;url=x">',
        b'<p style="background:url(x)">x</p>',
        b'<a href="javascript:alert(1)">x</a>',
        b'<a href="data:text/html,x">x</a>',
        b'<a href="file:///tmp/x">x</a>',
        b'<a href="http://exa mple.com">x</a>',
        b'<a href="https://user@example.com">x</a>',
        b'<a href="https://example.com\\@evil.com">x</a>',
        b'<a href="http://[">x</a>',
        b'<a href="#missing">x</a>',
        b'<p id="x"></p><p id="x"></p>',
        b"<p><strong>x</p></strong>",
    ],
)
def test_hostile_active_or_ambiguous_html_is_rejected(body: bytes) -> None:
    with pytest.raises(CanonicalMergeError):
        canonicalize_members((member(body),))


def test_invalid_utf8_and_ceiling_are_rejected() -> None:
    with pytest.raises(CanonicalMergeError, match="UTF-8"):
        canonicalize_members((member(b"\xff"),))
    with pytest.raises(CanonicalMergeError, match="member byte"):
        canonicalize_members((member(b"x" * (2 * 1024 * 1024 + 1)),))


def test_member_anchor_namespaces_cannot_collide() -> None:
    merged = canonicalize_members(
        (member(b'<p id="x">a</p>', "one"), member(b'<p id="x">b</p>', "two"))
    )
    assert merged.html.count(' id="m0-') == 1
    assert merged.html.count(' id="m1-') == 1


def test_accepts_real_projection_renderer_document_and_drops_shell_and_island() -> None:
    source = render(
        {
            "title": "Rendered",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "Body"}]}
            ],
        },
        RenderContext(),
    ).encode()
    merged = canonicalize_members((member(source),))
    assert "Rendered" in merged.html
    assert "Body" in merged.html
    assert "<!DOCTYPE" not in merged.html
    assert "<style" not in merged.html
    assert "<template" not in merged.html
