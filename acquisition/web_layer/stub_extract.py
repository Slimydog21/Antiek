"""Alternate extractor proving the interface can swap vendor shapes."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime

from acquisition.web_layer.cost import estimate_cost
from acquisition.web_layer.interfaces import ExtractionResponse, ExtractionResult


class SwapStubExtractor:
    """Resolve URLs from a vendor-neutral injected fixture corpus, with no key."""

    def __init__(
        self,
        *,
        documents: Mapping[str, str],
        clock: Callable[[], datetime],
    ) -> None:
        self._documents = dict(documents)
        self._clock = clock

    def extract(self, url: str) -> ExtractionResponse:
        try:
            text = self._documents[url]
        except KeyError as error:
            raise ValueError("swap stub has no document for source URL") from error
        if not text.strip():
            raise ValueError("swap stub extraction returned empty text")
        result = ExtractionResult(url, text, self._clock())
        return ExtractionResponse(result, estimate_cost("swap_stub", "extract", 1))
