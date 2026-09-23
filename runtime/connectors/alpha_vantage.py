"""Alpha Vantage connector — a paste-key tool vendor (BYO-tools).

A user pastes their own Alpha Vantage key; this connector holds it the way
every ``PasteKeyConnector`` does. Nothing in the product searches or ingests
Alpha Vantage yet, so the registry marks it ``searchable=False`` and the
settings panel says "connected, not yet used".

WHAT validate_key CAN AND CANNOT PROVE. Alpha Vantage does not authenticate
keys on its free endpoints. Observed 2026-09-23: a fabricated key
(``apikey=ZZZZINVALID00000``) on ``function=GLOBAL_QUOTE&symbol=MSFT``
answered HTTP 200 with a full ``{"Global Quote": {...}}`` object, identical to
the documented ``demo`` key. Only a MISSING key drew
``{"Error Message": "the parameter apikey is invalid or missing. ..."}``. So
a passing :meth:`AlphaVantageConnector.validate_key` means "reachable, and the
key is well formed", never "this key is registered to you". The settings
surface must not present it as more than that.

RATE — the vendor's own rate-limit body asks free keys to spread requests to
"1 request per second", and its support page lists the free tier as "25 API
requests per day" (https://www.alphavantage.co/support/, read 2026-09-23). The
governor brakes at one request per second, per owner. The daily cap is the
vendor's to enforce: it answers HTTP 200 with an ``Information`` body, which
this connector maps to a 429 so callers treat it as clearing on its own.

SECRETS — the key is revealed ONLY into the ``apikey`` query param at send
time; errors carry the status code and endpoint path only.

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

_API_URL = "https://www.alphavantage.co/query"
_AV_KEY = re.compile(r"^[A-Za-z0-9]{8,64}$")
# The vendor's own "1 request per second" spacing (module docstring).
ALPHA_VANTAGE_RATE = RateSpec(max_calls=1, window_s=1.0)
ALPHA_VANTAGE_DESCRIPTOR = ConnectorDescriptor(
    vendor="alpha_vantage",
    chassis="paste_key",
    auth="api_key_query",
    key_shape=KeyShape(min_len=8, max_len=64),
    rate=ALPHA_VANTAGE_RATE,
    docs_url="https://www.alphavantage.co/support/#api-key",
)


class AlphaVantageError(ConnectorError):
    """A non-200, rate-limited or unreadable response. Never carries the key."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


class AlphaVantageKeyRejected(AlphaVantageError):
    """The key is malformed, or the vendor answered with an ``Error Message``."""


class AlphaVantageConnector(PasteKeyConnector):
    """BYO Alpha Vantage connector: one owner's key, one owner's rate window."""

    descriptor = ALPHA_VANTAGE_DESCRIPTOR

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
            self._governor = VendorRateGovernor("alpha_vantage", ALPHA_VANTAGE_RATE, **kwargs)

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def _require_key(self) -> str:
        secret = self._resolve_key()
        if secret is None:
            raise AlphaVantageKeyRejected("Alpha Vantage connector has no key attached")
        key = secret.reveal()
        if not _AV_KEY.match(key):
            raise AlphaVantageKeyRejected(
                "Alpha Vantage keys are 8-64 letters and digits", status_code=400
            )
        return key

    def validate_key(self) -> dict[str, Any]:
        """Check the key reaches Alpha Vantage: ``GLOBAL_QUOTE`` for IBM.

        Proves reachability and a well-formed key, NOT ownership: the vendor
        serves free data to unregistered keys (module docstring). A malformed
        key is refused before any request. An ``Error Message`` body raises
        :class:`AlphaVantageKeyRejected`; an ``Information`` or ``Note`` body
        (the vendor's rate limit, sent as HTTP 200) raises
        :class:`AlphaVantageError` with ``status_code=429``. Returns the
        payload when it carries a ``Global Quote`` object.
        """
        key = self._require_key()
        params = {"function": "GLOBAL_QUOTE", "symbol": "IBM", "apikey": key}

        def _send() -> httpx.Response:
            return self._client.get(_API_URL, params=params)

        resp = self._governor.governed_send(_send)
        if resp.status_code != 200:
            raise AlphaVantageError(
                f"Alpha Vantage request failed: HTTP {resp.status_code}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise AlphaVantageError("Alpha Vantage returned a non-JSON body") from exc
        if not isinstance(payload, dict):
            raise AlphaVantageError("Alpha Vantage returned a non-object body")
        if "Error Message" in payload:
            raise AlphaVantageKeyRejected("Alpha Vantage rejected the request", status_code=400)
        if "Information" in payload or "Note" in payload:
            raise AlphaVantageError("Alpha Vantage rate limit reached", status_code=429)
        if not isinstance(payload.get("Global Quote"), dict):
            raise AlphaVantageError("Alpha Vantage returned no quote")
        return payload

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> AlphaVantageConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "ALPHA_VANTAGE_DESCRIPTOR",
    "ALPHA_VANTAGE_RATE",
    "AlphaVantageConnector",
    "AlphaVantageError",
    "AlphaVantageKeyRejected",
]
