"""Pure value objects and validation for artifact feedback anchors."""

from __future__ import annotations

import hashlib
import unicodedata
from dataclasses import dataclass


def normalize_node_text(value: str) -> str:
    """Apply the cross-runtime ``unicode-nfc-v1`` normalization contract."""
    return unicodedata.normalize("NFC", value.replace("\r\n", "\n").replace("\r", "\n"))


@dataclass(frozen=True, slots=True)
class NodeTextAnchor:
    node_id: str
    node_text_sha256: str
    start_scalar: int
    end_scalar: int
    quote: str
    prefix: str
    suffix: str
    normalization: str = "unicode-nfc-v1"


@dataclass(frozen=True, slots=True)
class ValidatedNodeTextAnchor:
    anchor: NodeTextAnchor
    normalized_text: str
    quote: str


def validate_node_text_anchor(
    canonical_node_text: str, anchor: NodeTextAnchor
) -> ValidatedNodeTextAnchor:
    """Validate a browser anchor against canonical immutable node text."""
    if anchor.normalization != "unicode-nfc-v1":
        raise ValueError("unsupported anchor normalization")
    if not anchor.node_id:
        raise ValueError("node_id is required")

    normalized = normalize_node_text(canonical_node_text)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if anchor.node_text_sha256 != digest:
        raise ValueError("node text hash does not match")

    scalar_count = len(normalized)
    if not (0 <= anchor.start_scalar < anchor.end_scalar <= scalar_count):
        raise ValueError("anchor offsets are outside the node text")

    quote = normalize_node_text(anchor.quote)
    if normalized[anchor.start_scalar : anchor.end_scalar] != quote:
        raise ValueError("anchor quote does not match offsets")

    expected_prefix = normalized[max(0, anchor.start_scalar - 32) : anchor.start_scalar]
    expected_suffix = normalized[anchor.end_scalar : min(scalar_count, anchor.end_scalar + 32)]
    if normalize_node_text(anchor.prefix) != expected_prefix:
        raise ValueError("anchor prefix does not match")
    if normalize_node_text(anchor.suffix) != expected_suffix:
        raise ValueError("anchor suffix does not match")

    return ValidatedNodeTextAnchor(anchor=anchor, normalized_text=normalized, quote=quote)
