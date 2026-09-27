"""FRED (St. Louis Fed) connector — a paste-key tool vendor (BYO-tools).

A user pastes their own FRED API key; this connector holds it the way every
``PasteKeyConnector`` does and validates it live against one cheap series
read. It exists to prove the connector chassis takes a new vendor without an
OAuth app. Nothing in the product searches or ingests FRED yet, so the
registry marks it ``searchable=False`` and the settings panel says "connected,
not yet used" rather than "configured".

KEY SHAPE — FRED documents the key as "a 32 character lower-cased
alpha-numeric string" (https://fred.stlouisfed.org/docs/api/api_key.html,
read 2026-09-23). The registry's ``KeyShape`` enforces the length on paste;
:meth:`FredConnector.validate_key` also refuses any other character set before
a request is built.

RATE — FRED allows "Up to 120 requests per minute" before answering 429
(https://fred.stlouisfed.org/docs/api/fred/errors.html, read 2026-09-23). The
governor brakes at 100 per minute, one notch under, the same reasoning as
EDGAR's 8 under SEC's 10. It is keyed per owner like every keyed connector
the registry resolves, so one user's calls never make another wait.

RECORDED RESPONSE — an unregistered key on ``/fred/series`` answers HTTP 400
with ``{"error_code":400,"error_message":"Bad Request.  The value for variable
api_key is not registered. ..."}`` (observed 2026-09-23).

SECRETS — the key lives only in the encrypted byok store and is revealed ONLY
into the ``api_key`` query param at send time. Because it rides in the query
string, errors carry the status code and endpoint PATH only, never the URL.

§16 BOX-BOUNDED: no DB writes, no DB connection.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from runtime.connectors.base import (
    ConnectorDescriptor,
    ConnectorError,
    KeyShape,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

_API_BASE = "https://api.stlouisfed.org/fred"
_FRED_KEY = re.compile(r"^[a-z0-9]{32}$")
# One notch under the documented 120 requests per minute (module docstring).
FRED_RATE = RateSpec(max_calls=100, window_s=60.0)
FRED_DESCRIPTOR = ConnectorDescriptor(
    vendor="fred",
    chassis="paste_key",
    auth="api_key_query",
    key_shape=KeyShape(min_len=32, max_len=32),
    rate=FRED_RATE,
    docs_url="https://fred.stlouisfed.org/docs/api/api_key.html",
)
# The series validate_key reads: annual real GNP, a long-lived public series.
_VALIDATION_SERIES = "GNPCA"


class FredError(ConnectorError):
    """A non-200 or unreadable FRED response. Never carries the key or URL."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class FredKeyRejected(FredError):
    """FRED answered that the key is not registered, or it is malformed."""


class FredConnector(PasteKeyConnector):
    """BYO FRED connector: one owner's key, one owner's rate window."""

    descriptor = FRED_DESCRIPTOR

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
        client: httpx.Client | None = None,
        governor: VendorRateGovernor | None = None,
        owner: str | None = None,
        state_dir: str | None = None,
        timeout_s: float = 20.0,
    ) -> None:
        super().__init__(
            cred_id=cred_id,
            artifact_path=artifact_path,
            key_bytes=key_bytes,
            key_file=key_file,
        )
        self._owns_client = client is None
        self._client = client if client is not None else httpx.Client(timeout=timeout_s)
        if governor is not None:
            self._governor = governor
        else:
            kwargs: dict[str, Any] = {"owner": owner}
            if state_dir is not None:
                kwargs["state_dir"] = state_dir
            self._governor = VendorRateGovernor("fred", FRED_RATE, **kwargs)

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def _require_key(self) -> str:
        secret = self._resolve_key()
        if secret is None:
            raise FredKeyRejected("FRED connector has no key attached")
        key = secret.reveal()
        if not _FRED_KEY.match(key):
            raise FredKeyRejected(
                "FRED keys are 32 lower-case letters and digits", status_code=400
            )
        return key

    def validate_key(self) -> dict[str, Any]:
        """Validate the attached key: ``GET /fred/series?series_id=GNPCA``.

        A key that is not 32 lower-case letters and digits is refused before
        any request. A 400 naming ``api_key`` raises :class:`FredKeyRejected`;
        any other non-200, or a 200 without a ``seriess`` list, raises
        :class:`FredError`. Returns the parsed payload.
        """
        key = self._require_key()
        params = {"series_id": _VALIDATION_SERIES, "file_type": "json", "api_key": key}

        def _send() -> httpx.Response:
            return self._client.get(f"{_API_BASE}/series", params=params)

        resp = self._governor.governed_send(_send)
        if resp.status_code == 400 and "api_key" in _error_message(resp):
            raise FredKeyRejected("FRED rejected the API key", status_code=400)
        if resp.status_code != 200:
            raise FredError(
                f"FRED request to /series failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FredError("FRED returned a non-JSON body") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("seriess"), list):
            raise FredError("FRED returned no series list")
        return payload

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FredConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _error_message(resp: httpx.Response) -> str:
    try:
        payload = resp.json()
    except ValueError:
        return ""
    if isinstance(payload, dict):
        return str(payload.get("error_message") or "")
    return ""


__all__ = [
    "FRED_DESCRIPTOR",
    "FRED_RATE",
    "FredConnector",
    "FredError",
    "FredKeyRejected",
]
