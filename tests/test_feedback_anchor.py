from __future__ import annotations

import hashlib

import pytest

from substrate.feedback.domain import NodeTextAnchor, validate_node_text_anchor


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_anchor_uses_nfc_and_unicode_scalar_offsets() -> None:
    canonical_text = "Cafe\N{COMBINING ACUTE ACCENT} 🧪 result"
    normalized = "Café 🧪 result"
    anchor = NodeTextAnchor(
        node_id="insight-1",
        node_text_sha256=_sha256(normalized),
        start_scalar=5,
        end_scalar=6,
        quote="🧪",
        prefix="Café ",
        suffix=" result",
    )

    validated = validate_node_text_anchor(canonical_text, anchor)

    assert validated.normalized_text == normalized
    assert validated.quote == "🧪"


def test_anchor_rejects_quote_that_does_not_match_offsets() -> None:
    text = "same same"
    anchor = NodeTextAnchor(
        node_id="insight-1",
        node_text_sha256=_sha256(text),
        start_scalar=0,
        end_scalar=4,
        quote="different",
        prefix="",
        suffix=" same",
    )

    with pytest.raises(ValueError, match="quote does not match"):
        validate_node_text_anchor(text, anchor)
