"""Visual role output parser.

The role returns JSON conforming to::

    {
      "frame_summary": "<one short declarative sentence>",
      "claims": [
        {
          "claim_text": "<declarative observation>",
          "confidence": "low" | "moderate" | "high",
          "region": {
            "page_or_frame_id": "<string>",
            "bbox": [x_min, y_min, x_max, y_max]
          }
        }
      ],
      "uncited_observations": [
        {"claim_text": "...", "confidence": "low"}
      ]
    }

Parser refuses anything else. The substrate's grounding discipline
makes the region mandatory for every confident claim; uncertain
observations may ride without a region but get marked "low".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .._json_decode import extract_json_object


_VALID_CONFIDENCE: frozenset[str] = frozenset({"low", "moderate", "high"})


class VisualValidationError(ValueError):
    """Raised when the role's output fails structural validation."""


@dataclass(frozen=True)
class VisualRegion:
    """A bounding box on a frame. Coordinates are normalized to [0, 1]
    so the substrate can render the region back onto any reproduction
    of the frame without knowing the source resolution."""

    page_or_frame_id: str
    bbox: tuple[float, float, float, float]


@dataclass(frozen=True)
class VisualClaim:
    claim_text: str
    confidence: str  # one of _VALID_CONFIDENCE
    region: VisualRegion


@dataclass(frozen=True)
class VisualResult:
    frame_summary: str
    claims: tuple[VisualClaim, ...]
    uncited_observations: tuple[tuple[str, str], ...]
    """Each entry is (claim_text, confidence)."""


def _parse_region(raw: object) -> VisualRegion:
    if not isinstance(raw, dict):
        raise VisualValidationError("region must be an object")
    pf_id = raw.get("page_or_frame_id")
    if not isinstance(pf_id, str) or not pf_id:
        raise VisualValidationError(
            "region.page_or_frame_id must be a non-empty string"
        )
    bbox = raw.get("bbox")
    if (
        not isinstance(bbox, (list, tuple))
        or len(bbox) != 4
        or not all(isinstance(v, (int, float)) for v in bbox)
    ):
        raise VisualValidationError(
            "region.bbox must be a 4-tuple of numbers"
        )
    x_min, y_min, x_max, y_max = (float(v) for v in bbox)
    for v in (x_min, y_min, x_max, y_max):
        if not (0.0 <= v <= 1.0):
            raise VisualValidationError(
                f"bbox value {v} outside normalized [0, 1] range"
            )
    if x_min >= x_max or y_min >= y_max:
        raise VisualValidationError(
            "bbox must have x_min < x_max and y_min < y_max"
        )
    return VisualRegion(
        page_or_frame_id=pf_id, bbox=(x_min, y_min, x_max, y_max),
    )


def _parse_claim(raw: object) -> VisualClaim:
    if not isinstance(raw, dict):
        raise VisualValidationError("claim must be an object")
    claim_text = raw.get("claim_text")
    if not isinstance(claim_text, str) or not claim_text.strip():
        raise VisualValidationError(
            "claim_text must be a non-empty string"
        )
    confidence = raw.get("confidence")
    if confidence not in _VALID_CONFIDENCE:
        raise VisualValidationError(
            f"confidence must be one of {sorted(_VALID_CONFIDENCE)!r}; "
            f"got {confidence!r}"
        )
    region = _parse_region(raw.get("region"))
    return VisualClaim(
        claim_text=claim_text.strip(),
        confidence=confidence,
        region=region,
    )


def _parse_uncited(raw: object) -> tuple[tuple[str, str], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise VisualValidationError(
            "uncited_observations must be a list (or omitted)"
        )
    out: list[tuple[str, str]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise VisualValidationError(
                "uncited_observations entry must be an object"
            )
        text = entry.get("claim_text")
        if not isinstance(text, str) or not text.strip():
            raise VisualValidationError(
                "uncited claim_text must be a non-empty string"
            )
        conf = entry.get("confidence", "low")
        if conf not in _VALID_CONFIDENCE:
            raise VisualValidationError(
                f"uncited confidence must be one of "
                f"{sorted(_VALID_CONFIDENCE)!r}; got {conf!r}"
            )
        out.append((text.strip(), conf))
    return tuple(out)


def parse_visual_response(raw: str) -> VisualResult:
    """Parse + validate the visual role's output."""
    data = extract_json_object(raw)
    if data is None:
        raise VisualValidationError("no JSON object in response")

    frame_summary = data.get("frame_summary")
    if not isinstance(frame_summary, str) or not frame_summary.strip():
        raise VisualValidationError(
            "frame_summary must be a non-empty string"
        )

    raw_claims = data.get("claims")
    if not isinstance(raw_claims, list):
        raise VisualValidationError("claims must be a list")
    claims = tuple(_parse_claim(c) for c in raw_claims)

    uncited = _parse_uncited(data.get("uncited_observations"))

    return VisualResult(
        frame_summary=frame_summary.strip(),
        claims=claims,
        uncited_observations=uncited,
    )


__all__ = [
    "VisualClaim",
    "VisualRegion",
    "VisualResult",
    "VisualValidationError",
    "parse_visual_response",
]
