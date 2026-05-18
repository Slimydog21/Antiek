"""Creative writer output parser.

The role returns JSON: ``{prose_text, prose_provenance, uncited_blocks}``.
Parser enforces:

- ``prose_text`` is non-empty
- ``prose_provenance`` maps paragraph_index → list of block_ids
- ``uncited_blocks`` is a list of block_ids
- Every block_id referenced in either provenance or uncited_blocks
  must have appeared in the input ``CreativeWriterContext.blocks``
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from .._json_decode import extract_json_object


class CreativeWriterValidationError(ValueError):
    """Raised when the role's output fails structural validation."""


@dataclass(frozen=True)
class CreativeWriterResult:
    prose_text: str
    prose_provenance: Dict[int, List[str]]
    uncited_blocks: List[str]


def parse_creative_writer_response(
    raw: str, *, known_block_ids: set[str],
) -> CreativeWriterResult:
    """Parse + validate the role's output."""
    data = extract_json_object(raw)
    if data is None:
        raise CreativeWriterValidationError("no JSON object in response")

    prose_text = data.get("prose_text")
    if not isinstance(prose_text, str) or not prose_text.strip():
        raise CreativeWriterValidationError("prose_text must be a non-empty string")

    raw_prov = data.get("prose_provenance") or {}
    if not isinstance(raw_prov, dict):
        raise CreativeWriterValidationError(
            "prose_provenance must be an object"
        )
    provenance: Dict[int, List[str]] = {}
    for k, v in raw_prov.items():
        try:
            idx = int(k)
        except (TypeError, ValueError):
            raise CreativeWriterValidationError(
                f"prose_provenance keys must be integer paragraph "
                f"indices, got {k!r}"
            )
        if not isinstance(v, list) or not all(isinstance(b, str) for b in v):
            raise CreativeWriterValidationError(
                f"prose_provenance[{idx}] must be list of block_id strings"
            )
        for bid in v:
            if bid not in known_block_ids:
                raise CreativeWriterValidationError(
                    f"prose_provenance references unknown block_id {bid!r}"
                )
        provenance[idx] = list(v)

    uncited = data.get("uncited_blocks") or []
    if not isinstance(uncited, list) or not all(isinstance(b, str) for b in uncited):
        raise CreativeWriterValidationError(
            "uncited_blocks must be list of block_id strings"
        )
    for bid in uncited:
        if bid not in known_block_ids:
            raise CreativeWriterValidationError(
                f"uncited_blocks references unknown block_id {bid!r}"
            )

    return CreativeWriterResult(
        prose_text=prose_text.strip(),
        prose_provenance=provenance,
        uncited_blocks=list(uncited),
    )
