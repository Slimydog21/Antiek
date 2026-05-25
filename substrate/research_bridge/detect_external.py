"""DRW SPR-08 M2 — recognize external deep-research reports.

Builds on the existing ``source_detection.detect_source`` (which scores a
paste against known vendors). A document is tagged ``external_deep_research``
only when the detected source is a *consumer deep-research vendor* AND the
confidence clears ``EXTERNAL_CONFIDENCE_THRESHOLD`` — so a normal document
(a blog post, a paper) is not mis-tagged.

Heuristic + false-positive risk (documented, rigor #5): ``detect_source``
keys on structural + citation signals characteristic of ChatGPT / Claude /
Grok deep-research output. The false-positive risk is a heavily-cited,
sectioned analytical document that merely *resembles* a vendor report; the
confidence threshold is the guard, and the both-ways test pins it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

try:
    from .source_detection import detect_source
except ImportError:  # pragma: no cover
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.research_bridge.source_detection import detect_source  # type: ignore[no-redef]


# The consumer deep-research vendors (subset of KNOWN_SOURCES). "other" and
# "alphasense" are NOT consumer deep-research, so they never tag external.
EXTERNAL_VENDORS = ("chatgpt", "anthropic", "grok")
# Apparent-vendor display names.
_VENDOR_LABEL = {"chatgpt": "ChatGPT", "anthropic": "Claude", "grok": "Grok"}
EXTERNAL_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True)
class ExternalDetection:
    is_external: bool
    vendor: str            # normalized vendor key, or "" when not external
    vendor_label: str      # display name, or ""
    confidence: float


def detect_external_research(text: str) -> ExternalDetection:
    det = detect_source(text)
    if det.source in EXTERNAL_VENDORS and det.confidence >= EXTERNAL_CONFIDENCE_THRESHOLD:
        return ExternalDetection(
            is_external=True, vendor=det.source,
            vendor_label=_VENDOR_LABEL.get(det.source, det.source),
            confidence=det.confidence,
        )
    return ExternalDetection(is_external=False, vendor="", vendor_label="",
                             confidence=det.confidence)
