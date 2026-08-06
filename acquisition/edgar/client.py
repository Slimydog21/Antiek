"""SEC EDGAR full-text search connector — the keyless degenerate paste-a-key.

The first BYO-tools connector (spec §5.7 row 1, sprint S1). EDGAR full-text
search is FREE and KEYLESS — no credential exists to paste — so this is the
degenerate case of the paste-a-key chassis: ``auth="none"``,
``key_shape=None``, and the request carries no credential material at all.

Two vendor-mandated disciplines, both fail-closed:

  * USER-AGENT. SEC requires every automated client to send a DESCRIPTIVE
    ``User-Agent`` with contact info (an undeclared/Generic UA gets the host
    throttled or blocked). The UA is ``f"Antiek/1 {contact}"`` where
    ``contact`` comes from the constructor or ``ANTIEK_EDGAR_CONTACT``
    (operator decision gate §4.1). Without a contact the client REFUSES to
    construct — there is no legitimate contact-less EDGAR fetch.
  * RATE. SEC's ceiling is 10 requests/second per host, enforced by a
    ~10-minute IP block. Every send routes through
    :class:`runtime.connectors.rate_governor.VendorRateGovernor` at
    ``RateSpec(8, 1.0)`` — one notch UNDER the ceiling so bursts never trip
    the block — with a 429 ``banned_until`` sentinel honored across processes.

ENDPOINT SHAPES — fixture-validated, live-unverified (the honesty bar of
``acquisition/twitter/api_client.py:21-25``). The request params
(``q`` / ``forms`` / ``startdt`` / ``enddt`` / ``from`` / ``size`` against
``https://efts.sec.gov/LATEST/search-index``) and the response envelope
(``hits.hits[*]._source.{adsh,form,file_date,ciks,display_names,...}``)
follow the public EDGAR full-text-search JSON shape from public
documentation/usage, not from a fresh live probe. The deterministic tests
drive this client with RECORDED fixture JSON over ``httpx.MockTransport`` (no
network), so the URL-building + mapping logic is proven; the live round-trip
is the operator's smoke test. There is no ``entity`` param: the endpoint
takes company/person constraints only inside the lucene-ish ``q`` — express
them there.

§16 BOX-BOUNDED: this client does NO DB writes and opens NO DB connection —
it only fetches + parses. Landing a filing as a ``personal_reading`` document
is the (separate) adapter's job.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

from runtime.connectors.base import (
    ConnectorDescriptor,
    ConnectorError,
    PasteKeyConnector,
    RateSpec,
)
from runtime.connectors.rate_governor import VendorRateGovernor

# The EDGAR full-text-search JSON endpoint (the modern lane behind
# sec.gov's full-text search UI; the legacy ``www.sec.gov/cgi-bin/`` browse
# pages are HTML and are not this connector's surface).
_FTS_URL = "https://efts.sec.gov/LATEST/search-index"

_ENV_CONTACT = "ANTIEK_EDGAR_CONTACT"

# EDGAR full-text search paginates 10 hits per page by default; ``size`` is
# only sent when the caller asks for a non-default page size.
_DEFAULT_PAGE_SIZE = 10
_MAX_PAGE_SIZE = 100

# One notch under SEC's 10 req/s host ceiling (spec §5.4) so a burst of
# connector sends can never trip the ~10-minute IP block.
EDGAR_RATE = RateSpec(max_calls=8, window_s=1.0)


class EdgarContactRequired(ConnectorError):
    """No EDGAR contact identity was supplied. Fail-closed (gate §4.1): SEC
    mandates a descriptive User-Agent with contact info, so a contact-less
    client is refused at construction. The message names the env var to set —
    it never echoes any value."""


class EdgarApiError(ConnectorError):
    """A non-200 or unparseable response from EDGAR. Carries the status code +
    the endpoint PATH only — never the query string (the chassis-wide
    redaction discipline; harmless here since EDGAR is keyless, consistent
    everywhere since FMP's key-in-query lane exists)."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True)
class EdgarHit:
    """One parsed full-text-search hit.

    ``hit_id`` is EDGAR's ``_id`` (``"{accession}:{primary_filename}"``);
    ``accession_no`` the ``adsh``; ``ciks`` / ``display_names`` keep EDGAR's
    own zero-padded string forms verbatim.
    """

    hit_id: str
    accession_no: str
    form: str
    file_date: str
    ciks: tuple[str, ...]
    display_names: tuple[str, ...]
    period_ending: str | None = None

    @property
    def entity_name(self) -> str:
        """The filer's primary display name ("" if EDGAR supplied none)."""
        return self.display_names[0] if self.display_names else ""

    @property
    def document_url(self) -> str | None:
        """The Archives URL of the hit's primary document, derived from
        ``hit_id`` (``{accession}:{filename}``) + the first CIK — or None when
        the id is not in the expected shape (never a guessed URL)."""
        accession, sep, filename = self.hit_id.partition(":")
        if not sep or not filename or not self.ciks:
            return None
        try:
            cik_int = int(self.ciks[0])
        except ValueError:
            return None
        accession_compact = accession.replace("-", "")
        return (
            f"https://www.sec.gov/Archives/edgar/data/{cik_int}/"
            f"{accession_compact}/{filename}"
        )


def parse_search_response(payload: dict[str, Any]) -> list[EdgarHit]:
    """Map the EDGAR full-text-search JSON envelope to structured hits.

    Lenient per-hit (a search result list, not a ledger): a hit whose
    ``_source`` is not a mapping is skipped rather than nuking the page, and
    scalar fields default to "" / empty tuples. The envelope itself must be a
    mapping — anything else is an :class:`EdgarApiError`.
    """
    if not isinstance(payload, dict):
        raise EdgarApiError("EDGAR search returned a non-object JSON body")
    hits_obj = payload.get("hits")
    raw_hits = hits_obj.get("hits") if isinstance(hits_obj, dict) else None
    if not isinstance(raw_hits, list):
        return []
    out: list[EdgarHit] = []
    for raw in raw_hits:
        if not isinstance(raw, dict):
            continue
        source = raw.get("_source")
        if not isinstance(source, dict):
            continue
        ciks = source.get("ciks")
        names = source.get("display_names")
        period = source.get("period_ending")
        out.append(
            EdgarHit(
                hit_id=str(raw.get("_id") or ""),
                accession_no=str(source.get("adsh") or ""),
                form=str(source.get("form") or ""),
                file_date=str(source.get("file_date") or ""),
                ciks=tuple(str(c) for c in ciks) if isinstance(ciks, list) else (),
                display_names=(
                    tuple(str(n) for n in names) if isinstance(names, list) else ()
                ),
                period_ending=str(period) if period else None,
            )
        )
    return out


class EdgarConnector(PasteKeyConnector):
    """SEC EDGAR full-text search — the keyless degenerate paste-a-key connector.

    ``descriptor`` declares ``auth="none"`` / ``key_shape=None``: there is no
    key to attach, store, or resolve (calling :meth:`attach_key` raises — the
    chassis's keyless refusal). Every request carries the SEC-mandated
    descriptive ``User-Agent`` and is sent through the host-global
    :class:`VendorRateGovernor` at :data:`EDGAR_RATE`.

    Injection seams (tests): ``client`` (an ``httpx.Client`` over
    ``MockTransport`` — no network), ``governor`` (a governor with a fake
    clock), or ``state_dir`` + ``clock`` + ``sleeper`` to build one. An
    injected client is NOT closed by :meth:`close` (we close only what we
    created).
    """

    descriptor = ConnectorDescriptor(
        vendor="edgar",
        chassis="paste_key",
        auth="none",
        key_shape=None,
        rate=EDGAR_RATE,
        docs_url="https://www.sec.gov/search-filings",
    )

    def __init__(
        self,
        *,
        contact: str | None = None,
        client: httpx.Client | None = None,
        governor: VendorRateGovernor | None = None,
        state_dir: str | None = None,
        clock: Any = None,
        sleeper: Any = None,
        timeout_s: float = 20.0,
    ) -> None:
        super().__init__(cred_id=None)  # keyless — always
        resolved = contact if contact is not None else os.environ.get(_ENV_CONTACT, "")
        if not resolved.strip():
            raise EdgarContactRequired(
                "SEC EDGAR requires a descriptive User-Agent with contact info. "
                f"Set {_ENV_CONTACT} (an email) or pass contact=... — refusing "
                "to send without one."
            )
        self._contact = resolved.strip()
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
                self.descriptor.vendor, EDGAR_RATE, **governor_kwargs
            )

    @property
    def user_agent(self) -> str:
        """The SEC-mandated descriptive UA — ``Antiek/1 {contact}`` (spec §5.7)."""
        return f"Antiek/1 {self._contact}"

    @property
    def governor(self) -> VendorRateGovernor:
        return self._governor

    def search(
        self,
        query: str,
        *,
        forms: list[str] | tuple[str, ...] | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        start: int = 0,
        size: int = _DEFAULT_PAGE_SIZE,
    ) -> list[EdgarHit]:
        """Full-text search EDGAR filings, returning structured hits.

        Builds ``GET {_FTS_URL}?q=...`` (plus ``forms`` / ``startdt`` /
        ``enddt`` / ``from`` / ``size`` when given — ``date_from`` /
        ``date_to`` are ISO ``YYYY-MM-DD`` strings, the endpoint's form),
        sends it with the SEC-mandated ``User-Agent`` through the host-global
        rate governor, and parses the JSON envelope. ``query`` is the
        endpoint's lucene-ish string verbatim (phrases double-quoted by the
        caller); company/person constraints belong inside it — the endpoint
        has no separate entity param.
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")
        if start < 0:
            raise ValueError("start must be >= 0")
        if not 1 <= size <= _MAX_PAGE_SIZE:
            raise ValueError(f"size must be 1-{_MAX_PAGE_SIZE}")

        params: dict[str, str] = {"q": query}
        if forms:
            params["forms"] = ",".join(forms)
        if date_from:
            params["startdt"] = date_from
        if date_to:
            params["enddt"] = date_to
        if start:
            params["from"] = str(start)
        if size != _DEFAULT_PAGE_SIZE:
            params["size"] = str(size)

        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}

        def _send() -> httpx.Response:
            return self._client.get(_FTS_URL, params=params, headers=headers)

        # HOST-GLOBAL arXiv GOVERNANCE (compliance boundary): every raw
        # external HTTP egress in the tree routes through the arXiv governor
        # so an arXiv host can never be hit un-spaced, REGARDLESS of module.
        # efts.sec.gov is never arXiv, so ``govern_if_arxiv`` calls ``_send``
        # directly with zero overhead — but the wrap is the sanctioned,
        # scanner-visible pattern (tools/lint/rate_governor_check), not an
        # allowlist exception, so a future URL change cannot silently re-open
        # the hole. The VendorRateGovernor flock wraps the whole send: window
        # wait -> governed fetch -> 429 note is one atomic critical section.
        from acquisition.arxiv.rate_governor import govern_if_arxiv

        resp = self._governor.governed_send(lambda: govern_if_arxiv(_FTS_URL, _send))
        if resp.status_code != 200:
            raise EdgarApiError(
                f"EDGAR search failed: HTTP {resp.status_code} from "
                f"{urlsplit(_FTS_URL).path}",
                status_code=resp.status_code,
            )
        try:
            payload = resp.json()
        except ValueError as exc:
            raise EdgarApiError("EDGAR search returned a non-JSON body") from exc
        return parse_search_response(payload)

    def close(self) -> None:
        """Close the held httpx client — only if this connector created it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> EdgarConnector:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


__all__ = [
    "EDGAR_RATE",
    "EdgarApiError",
    "EdgarConnector",
    "EdgarContactRequired",
    "EdgarHit",
    "parse_search_response",
]
