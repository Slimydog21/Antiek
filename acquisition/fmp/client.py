"""Financial Modeling Prep connector — key-in-query, redaction-critical
(spec §5.7 row 3a, sprint S3).

The third BYO-tools connector: the user's own FMP plan on the paste-a-key
chassis, ``auth="api_key_query"`` — FMP authenticates via ``?apikey=...`` on
every URL, so the plaintext key lives in the QUERY STRING at send time. That
makes this the redaction-critical lane of the whole chassis (spec §10 risk
2): the key is revealed AT CALL TIME only into the params dict a send
builds, and every error / logged surface carries status + PATH only — never
the query string, never the key. ``redact_query`` is the one public
conversion a caller may use to render a URL safely.

GUARDS:

  * KEY. Attached via the chassis (``attach_key`` → encrypted byok store →
    non-secret ``cred_id``); ``_require_key()`` refuses a keyless send.
  * RATE. Spec §5.4 assigns FMP "vendor-429 via governor": sends route
    through :class:`VendorRateGovernor` so a 429 writes the cross-process
    ``banned_until`` sentinel (the governor's real job here) — with a
    documented NO-WINDOW rate (:data:`FMP_RATE_NO_WINDOW`): FMP gets no
    client-side pacing window per the spec, only the 429 pause. The
    descriptor's ``rate`` stays ``None`` (no window spec exists).

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/edgar/client.py:22-33``). ``GET /api/v3/profile/{symbol}``
returns an ARRAY with one object (``{symbol, companyName, exchange, sector,
industry, website, description, mktCap, price, currency, ...}``) or ``[]``
for an unknown symbol; ``GET /api/v3/earning_call_transcript/{symbol}``
takes ``year`` + ``quarter`` and returns an ARRAY with one object
(``{symbol, date, quarter, year, content}``). Both shapes follow the public
FMP docs, not a fresh live probe; the deterministic tests drive this client
with RECORDED fixture JSON over ``httpx.MockTransport`` (no network).

§16 BOX-BOUNDED: this client does NO DB writes and opens NO DB connection —
it only fetches + parses. Landing a transcript as a ``personal_reading``
document is the (separate) adapter's job; no connector output is servable
(spec §5.0 rights invariant).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from runtime.connectors.base import (
    KEY_MAX_LEN,
    ConnectorDescriptor,
    ConnectorError,
    KeyShape,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

# FMP API v3 root — every endpoint hangs off ``/api/v3/...``.
_API_BASE = "https://financialmodelingprep.com/api/v3"
_PROFILE_PATH = "/profile"
_TRANSCRIPT_PATH = "/earning_call_transcript"

# The spec's §5.4 rule for FMP: "governed only by vendor 429s" — NO
# client-side pacing window. The governor still needs a RateSpec to
# construct; a budget far beyond any single-host burst rate means the
# sliding window NEVER waits, so the governor's only effective behavior
# here is its 429 ``banned_until`` sentinel. (The descriptor's ``rate``
# stays None — there is no window spec; this is the stand-in.)
FMP_RATE_NO_WINDOW = RateSpec(max_calls=1_000_000, window_s=60.0)


def redact_query(url: str) -> str:
    """Render a URL WITHOUT its query string — the one safe way to log a
    key-in-query vendor URL (the ``apikey`` param and every sibling param
    are dropped, not masked: FMP URLs carry nothing but the key + request
    params, so path-only is both safe and sufficient)."""
    parts = urlsplit(url)
    return parts._replace(query="").geturl()


class FmpKeyRequired(ConnectorError):
    """No key is attached to the connector. An FMP call without a key is
    refused BEFORE any request is built (fail closed — never a keyless
    send). The message never carries key material (there is none)."""


class FmpApiError(ConnectorError):
    """A non-200 or unparseable response from FMP.

    Carries the status code + the endpoint PATH only — NEVER the query
    string, which holds the user's ``apikey`` (the redaction rule, spec §10
    risk 2). ``path`` is the exact redacted form a caller may log.
    """

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class FmpProfile:
    """One parsed company-profile record (the subset a research workstation
    uses; the vendor's payload carries more, unmapped on purpose — bounded
    mapping beats dump-everything). Scalar numbers default to None when the
    vendor omits or strings them oddly."""

    symbol: str
    company_name: str
    exchange: str
    sector: str
    industry: str
    website: str
    description: str
    currency: str
    market_cap: int | None = None
    price: float | None = None


@dataclass(frozen=True)
class FmpTranscript:
    """One parsed earnings-call transcript record (the vendor returns at
    most one per symbol/year/quarter). ``content`` is the raw call text —
    it lands ``personal_reading`` at the adapter, never servable."""

    symbol: str
    date: str
    quarter: int
    year: int
    content: str


def _parse_single_record[RecordT: (FmpProfile, FmpTranscript)](
    payload: Any,
    *,
    what: str,
    build: Callable[[dict[str, Any]], RecordT],
) -> RecordT | None:
    """The shared FMP envelope rule: a list of at most one mapping.

    An EMPTY array is the vendor's "no record" signal (unknown symbol /
    no transcript) → ``None``. A non-list body or a non-mapping entry is an
    envelope shape change and must surface as :class:`FmpApiError`, never
    silently read as "no record".
    """
    if not isinstance(payload, list):
        raise FmpApiError(f"FMP {what} returned a non-array JSON body")
    if not payload:
        return None
    if not isinstance(payload[0], dict):
        raise FmpApiError(f"FMP {what} returned a malformed record")
    return build(payload[0])


def parse_profile_response(payload: Any) -> FmpProfile | None:
    """Map the FMP profile ARRAY to one structured record.

    FMP returns ``[{...}]`` for a known symbol and ``[]`` for an unknown
    one; ``None`` means "no record" (the caller's unknown-symbol signal).
    A non-list payload or a malformed entry is an :class:`FmpApiError` — an
    envelope shape change must surface, not silently return None.
    """
    return _parse_single_record(
        payload, what="profile", build=lambda rec: _build_profile(rec)
    )


def _build_profile(rec: dict[str, Any]) -> FmpProfile:
    return FmpProfile(
        symbol=str(rec.get("symbol") or ""),
        company_name=str(rec.get("companyName") or ""),
        exchange=str(rec.get("exchange") or ""),
        sector=str(rec.get("sector") or ""),
        industry=str(rec.get("industry") or ""),
        website=str(rec.get("website") or ""),
        description=str(rec.get("description") or ""),
        currency=str(rec.get("currency") or ""),
        market_cap=_to_int(rec.get("mktCap")),
        price=_to_float(rec.get("price")),
    )


def parse_transcript_response(payload: Any) -> FmpTranscript | None:
    """Map the FMP earnings-transcript ARRAY to one structured record.

    Same envelope shape as the profile endpoint: ``[{...}]`` for a known
    (symbol, year, quarter) triple, ``[]`` when the vendor has no
    transcript — ``None`` is the no-record signal.
    """
    return _parse_single_record(
        payload, what="transcript", build=lambda rec: _build_transcript(rec)
    )


def _build_transcript(rec: dict[str, Any]) -> FmpTranscript:
    return FmpTranscript(
        symbol=str(rec.get("symbol") or ""),
        date=str(rec.get("date") or ""),
        quarter=_to_int(rec.get("quarter")) or 0,
        year=_to_int(rec.get("year")) or 0,
        content=str(rec.get("content") or ""),
    )


def _to_int(value: object) -> int | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> float | None:
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FmpConnector(PasteKeyConnector):
    """Financial Modeling Prep — profile + earnings transcripts on the
    paste-a-key chassis, ``api_key_query`` auth.

    ``descriptor`` declares ``rate=None`` (no client-side window — spec
    §5.4); every send still routes through a
    :class:`VendorRateGovernor` at :data:`FMP_RATE_NO_WINDOW` so a vendor
    429 writes the cross-process ``banned_until`` sentinel. The key is
    revealed at call time only into the params dict the send builds; every
    error path carries status + PATH only (``redact_query`` is the one safe
    URL renderer).

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport`` — no network), ``governor`` (a governor with a fake
    clock), or ``state_dir`` + ``clock`` + ``sleeper`` to build one. An
    injected client is NOT closed by :meth:`close`.
    """

    descriptor = ConnectorDescriptor(
        vendor="fmp",
        chassis="paste_key",
        auth="api_key_query",
        key_shape=KeyShape(min_len=10, max_len=KEY_MAX_LEN, prefix=None),
        rate=None,  # no window spec — vendor-429 via the governor's sentinel
        docs_url="https://site.financialmodelingprep.com/developer/docs",
    )

    def __init__(
        self,
        *,
        cred_id: str | None = None,
        artifact_path: str | None = None,
        key_bytes: bytes | None = None,
        key_file: str | None = None,
        client: httpx.Client | None = None,
        governor: VendorRateGovernor | None = None,
        state_dir: str | None = None,
        clock: Any = None,
        sleeper: Any = None,
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
            governor_kwargs: dict[str, Any] = {"state_dir": state_dir}
            if clock is not None:
                governor_kwargs["clock"] = clock
            if sleeper is not None:
                governor_kwargs["sleeper"] = sleeper
            self._governor = VendorRateGovernor(
                self.descriptor.vendor, FMP_RATE_NO_WINDOW, **governor_kwargs
            )

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def _require_key(self) -> str:
        """The attached key, revealed HERE and only here, scoped to the
        params dict a send builds. None keyless → refuse (fail closed)."""
        secret = self._resolve_key()
        if secret is None:
            raise FmpKeyRequired(
                f"{self.descriptor.vendor} connector has no key attached — "
                "attach_key() before a fetch (or a cred_id at construction)"
            )
        return secret.reveal()

    def profile(self, symbol: str) -> FmpProfile | None:
        """Company profile for ``symbol`` — ``GET /api/v3/profile/{symbol}``.

        Returns ``None`` for an unknown symbol (the vendor's empty-array
        signal), the structured :class:`FmpProfile` otherwise. ``symbol`` is
        the vendor's ticker verbatim (upper-cased by FMP, case-insensitive;
        unvalidated here).
        """
        return self._get(_PROFILE_PATH, symbol, extra_params=None, parse=parse_profile_response)

    def transcripts(self, symbol: str, *, year: int, quarter: int) -> FmpTranscript | None:
        """Earnings-call transcript for ``symbol`` / ``year`` / ``quarter``.

        ``GET /api/v3/earning_call_transcript/{symbol}?year=..&quarter=..``.
        Returns ``None`` when the vendor has no transcript for the triple.
        ``year`` / ``quarter`` are the vendor's integer params (a
        ``quarter`` of 1-4; out-of-range values are the vendor's problem —
        it answers empty, which surfaces as ``None``).
        """
        return self._get(
            _TRANSCRIPT_PATH,
            symbol,
            extra_params={"year": str(year), "quarter": str(quarter)},
            parse=parse_transcript_response,
        )

    def _get[RecordT: (FmpProfile, FmpTranscript)](
        self,
        path: str,
        symbol: str,
        *,
        extra_params: dict[str, str] | None,
        parse: Callable[[Any], RecordT | None],
    ) -> RecordT | None:
        """The one send path for every endpoint: key → params → governed
        send → error discipline (status + path only, never the query)."""
        if not symbol or not symbol.strip():
            raise ValueError("symbol must be a non-empty string")
        key = self._require_key()
        params: dict[str, str] = {"apikey": key}
        if extra_params:
            params.update(extra_params)
        url = f"{_API_BASE}{path}/{symbol}"

        headers = {"Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(url, params=params, headers=headers)

        # HOST-GLOBAL ARXIV GOVERNANCE (compliance boundary): every raw
        # external HTTP egress in the tree routes through the arXiv governor
        # so an arXiv host can never be hit un-spaced, REGARDLESS of module.
        # financialmodelingprep.com is never arXiv, so ``govern_if_arxiv``
        # calls ``_send`` directly — the wrap is the sanctioned,
        # scanner-visible pattern (tools/lint/rate_governor_check).
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        resp = self._governor.governed_send(lambda: govern_if_arxiv(url, _send))
        if resp.status_code != 200:
            # Path-only, always: the query string holds the user's key.
            raise FmpApiError(
                f"FMP {path} failed: HTTP {resp.status_code} from "
                f"{urlsplit(url).path}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise FmpApiError(f"FMP {path} returned a non-JSON body") from exc
        return parse(payload)

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> FmpConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "FMP_RATE_NO_WINDOW",
    "FmpApiError",
    "FmpConnector",
    "FmpKeyRequired",
    "FmpProfile",
    "FmpTranscript",
    "parse_profile_response",
    "parse_transcript_response",
    "redact_query",
]
