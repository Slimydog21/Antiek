"""Jina Reader-shaped URL extraction with isolated configuration."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

from acquisition.web_layer.cost import estimate_cost
from acquisition.web_layer.interfaces import ExtractionResponse, ExtractionResult


class ExtractionConfigurationError(RuntimeError):
    """Extraction cannot run because its isolated configuration is invalid."""


class TextResponse(Protocol):
    @property
    def text(self) -> str: ...

    def raise_for_status(self) -> None: ...


class ExtractionHttpClient(Protocol):
    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout: float,
    ) -> TextResponse: ...


class JinaExtractor:
    """GET a selected URL through Jina's reader-prefix API."""

    __slots__ = ("_clock", "_http", "_reader_prefix", "_timeout")

    # SPR-08 uses the integration spec's HTTP-adapter timeout; re-read 2026-07-11.
    _DEFAULT_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        *,
        http: ExtractionHttpClient,
        clock: Callable[[], datetime],
        reader_prefix: str = "https://r.jina.ai/",
        timeout: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if timeout <= 0:
            raise ExtractionConfigurationError("timeout must be positive")
        self._http = http
        self._clock = clock
        self._reader_prefix = reader_prefix
        self._timeout = timeout

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(reader_prefix={self._reader_prefix!r}, "
            f"timeout={self._timeout!r})"
        )

    __str__ = __repr__

    def extract(self, url: str) -> ExtractionResponse:
        self._validate_source_url(url)
        response = self._http.get(
            f"{self._reader_prefix}{url}",
            headers={"accept": "text/markdown"},
            timeout=self._timeout,
        )
        response.raise_for_status()
        retrieved_at = self._clock()
        if not response.text.strip():
            raise ValueError("Jina extraction returned empty text")
        result = ExtractionResult(url, response.text, retrieved_at)
        return ExtractionResponse(result, estimate_cost("jina", "extract", 1))

    @staticmethod
    def _validate_source_url(url: str) -> None:
        if not url.startswith(("https://", "http://")):
            raise ValueError("source URL must use http or https")
