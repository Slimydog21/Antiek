"""Jina Reader-shaped URL extraction with isolated configuration."""

from __future__ import annotations

import os
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

    __slots__ = ("_api_key", "_clock", "_http", "_reader_prefix", "_timeout")

    def __init__(
        self,
        *,
        http: ExtractionHttpClient,
        clock: Callable[[], datetime],
        api_key: str | None = None,
        environ: Mapping[str, str] | None = None,
        reader_prefix: str = "https://r.jina.ai/",
        timeout: float = 30.0,
    ) -> None:
        environment = os.environ if environ is None else environ
        resolved_key = api_key if api_key is not None else environment.get("JINA_API_KEY")
        if resolved_key is None or not resolved_key.strip():
            raise ExtractionConfigurationError("JINA_API_KEY is required")
        if timeout <= 0:
            raise ExtractionConfigurationError("timeout must be positive")
        self._http = http
        self._clock = clock
        self._api_key = resolved_key
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
            headers={
                "authorization": f"Bearer {self._api_key}",
                "accept": "text/markdown",
            },
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
