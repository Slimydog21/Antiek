"""Style Extractor JSON response parser.

Sprint 11. Parses + validates the Style Extractor's raw text response
into a typed ``StyleGuide`` dataclass, matching the fail-loud discipline
of ``synthesizer`` / ``evidence_retriever``.

Structural rules (mirroring the prompt's "Field rules"):

- Top-level keys EXACTLY ``vocabulary``, ``argumentation_pattern``,
  ``sentence_rhythm``, ``forbidden_in_this_register``, ``voice_summary``.
- ``vocabulary`` — list of 8-15 non-empty strings (terms as written).
- ``forbidden_in_this_register`` — list of 2-4 non-empty strings.
- ``argumentation_pattern`` / ``sentence_rhythm`` / ``voice_summary`` —
  non-empty strings.

Count floors/ceilings are taken from the design doc
(``docs/strategy/voice-and-style-discipline.md`` §"Change 3").

A validation failure raises ``StyleExtractorValidationError``. The
context-pack wiring (``substrate/context_pack/style_guide.py``) catches
this so a malformed model response degrades gracefully: the style_guide
layer is simply NOT injected and the synthesis path proceeds as if the
extractor had been skipped. The malformed response never crashes
assembly.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, List

try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import extract_json_object as _extract_json_object  # type: ignore[no-redef]


# Count bounds from the design doc.
VOCABULARY_MIN_TERMS = 8
VOCABULARY_MAX_TERMS = 15
FORBIDDEN_MIN_PATTERNS = 2
FORBIDDEN_MAX_PATTERNS = 4

# The five required top-level keys (closed set — extras are rejected so
# the role's contract cannot silently drift).
REQUIRED_KEYS: frozenset[str] = frozenset({
    "vocabulary",
    "argumentation_pattern",
    "sentence_rhythm",
    "forbidden_in_this_register",
    "voice_summary",
})


class StyleExtractorValidationError(ValueError):
    """Raised on any structural / count / vocabulary failure. The
    context-pack wiring catches this and SKIPS injection (the synthesis
    path proceeds as if the extractor had been skipped) rather than
    propagating the failure into assembly."""


@dataclass(frozen=True)
class StyleGuide:
    """A parsed, validated style guide. ``as_layer_content`` renders the
    operationally load-bearing fields (``voice_summary`` + ``vocabulary``,
    per the design doc's injection note) into the text that becomes the
    ``kind="style_guide"`` context-pack layer body."""

    vocabulary: tuple[str, ...]
    argumentation_pattern: str
    sentence_rhythm: str
    forbidden_in_this_register: tuple[str, ...]
    voice_summary: str
    raw: dict

    def as_layer_content(self) -> str:
        """Render the guide into the context-pack layer body.

        The design doc says to inject ``voice_summary`` + ``vocabulary``;
        we additionally carry the argumentation/rhythm/forbidden cues
        because they cost few tokens and sharpen the conditioning. The
        rendering is deterministic so two runs of the same guide produce
        byte-identical layer content."""
        vocab = ", ".join(self.vocabulary)
        forbidden = "; ".join(self.forbidden_in_this_register)
        return (
            f"{self.voice_summary}\n\n"
            f"Sector vocabulary (use these terms as written): {vocab}\n"
            f"Argumentation pattern: {self.argumentation_pattern}\n"
            f"Sentence rhythm: {self.sentence_rhythm}\n"
            f"Out of register for this corpus: {forbidden}"
        )


def _require_str(obj: Any, field_name: str) -> str:
    if not isinstance(obj, str) or not obj.strip():
        raise StyleExtractorValidationError(
            f"{field_name!r} must be a non-empty string "
            f"(got {type(obj).__name__})"
        )
    return obj.strip()


def _require_str_list(
    obj: Any,
    field_name: str,
    *,
    min_len: int,
    max_len: int,
) -> List[str]:
    if not isinstance(obj, list):
        raise StyleExtractorValidationError(
            f"{field_name!r} must be a list (got {type(obj).__name__})"
        )
    out: List[str] = []
    for i, v in enumerate(obj):
        if not isinstance(v, str) or not v.strip():
            raise StyleExtractorValidationError(
                f"{field_name}[{i}]: must be a non-empty string"
            )
        out.append(v.strip())
    if not (min_len <= len(out) <= max_len):
        raise StyleExtractorValidationError(
            f"{field_name!r} must contain {min_len}-{max_len} entries "
            f"(got {len(out)})"
        )
    return out


def parse_style_extractor_response(text: str) -> StyleGuide:
    """Parse + validate a Style Extractor raw response.

    Raises ``StyleExtractorValidationError`` on any structural problem
    (unparseable JSON, missing/extra keys, count violations, empty
    strings). Callers in the assembly path catch this and skip
    injection — assembly never crashes on a malformed guide."""
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise StyleExtractorValidationError(
            "response did not contain a parseable JSON object"
        )

    keys = set(obj.keys())
    missing = REQUIRED_KEYS - keys
    if missing:
        raise StyleExtractorValidationError(
            f"missing required keys: {sorted(missing)}"
        )
    extra = keys - REQUIRED_KEYS
    if extra:
        raise StyleExtractorValidationError(
            f"unexpected keys (closed set is {sorted(REQUIRED_KEYS)}): "
            f"{sorted(extra)}"
        )

    vocabulary = tuple(_require_str_list(
        obj.get("vocabulary"), "vocabulary",
        min_len=VOCABULARY_MIN_TERMS, max_len=VOCABULARY_MAX_TERMS,
    ))
    forbidden = tuple(_require_str_list(
        obj.get("forbidden_in_this_register"), "forbidden_in_this_register",
        min_len=FORBIDDEN_MIN_PATTERNS, max_len=FORBIDDEN_MAX_PATTERNS,
    ))
    argumentation = _require_str(
        obj.get("argumentation_pattern"), "argumentation_pattern",
    )
    rhythm = _require_str(obj.get("sentence_rhythm"), "sentence_rhythm")
    voice_summary = _require_str(obj.get("voice_summary"), "voice_summary")

    return StyleGuide(
        vocabulary=vocabulary,
        argumentation_pattern=argumentation,
        sentence_rhythm=rhythm,
        forbidden_in_this_register=forbidden,
        voice_summary=voice_summary,
        raw=obj,
    )
