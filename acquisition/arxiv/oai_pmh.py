"""OAI-PMH incremental harvester for arXiv — the authoritative metadata +
license channel.

WHY this and not the export SEARCH API: the search API got the box IP-banned
(project_researchmaxx_arxiv.md, 2026-05-17). OAI-PMH at
``oaipmh.arxiv.org/oai`` is arXiv's DESIGNATED bulk channel (moved from
``export.arxiv.org/oai2``, which 301s, in 2026-08)
(https://info.arxiv.org/help/oa/index.html) and, with ``metadataPrefix=arXiv``,
the only interface carrying the per-paper ``<license>`` element — the rights
source of truth for the census.

The harvester:

  * issues ``ListRecords`` with a ``from``/``until`` incremental window;
  * pages through ``resumptionToken``s to completion;
  * routes EVERY HTTP GET through the host-global rate governor
    (``acquisition.arxiv.rate_governor.governed_request``, SPR-09 M1), which wraps
    the PR#23 persisted ``ArxivThrottle`` (>=3s spacing, single connection,
    ``banned_until`` honored) under an exclusive ``fcntl.flock`` so the gate holds
    across ALL arXiv jobs on this box, not merely per-process. Rate-limiting is
    NOT re-implemented here — re-implementing it is the bug that banned the box;
  * persists the resumption token + last datestamp + progress bookkeeping
    (skip counter, last-completed-page timestamp) in a VERSIONED schema
    (``schema_version: 2``) after each page, so a crash mid-harvest resumes
    from the last completed page rather than restarting, and an operator can
    read how far a multi-night backfill has gotten.

NO live network in this module's tests: the ``httpx.Client`` is injectable, so a
``MockTransport`` serves a multi-page resumption-token sequence. The live full
backfill (M5) is an OPERATOR step run with a real client; the code path is the
same one the mocked sequence exercises.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import httpx

from acquisition.arxiv.client import default_user_agent
from acquisition.arxiv.oai_records import parse_records
from acquisition.arxiv.rate_governor import arxiv_governed_client
from acquisition.arxiv.throttle import ArxivThrottle
from substrate.schemas.documents import (
    ArxivOaiRecord,
    RightsCensus,
    _TierTally,  # package-internal accumulator
)

# Canonical endpoint since 2026-08: arXiv moved the OAI-PMH service from
# export.arxiv.org/oai2 (now a 301) to oaipmh.arxiv.org/oai. The harvester
# ALSO follows redirects defensively (a stale env override or a future move
# must not silently kill the nightly sync), but this is the endpoint the
# production client targets directly.
DEFAULT_OAI_BASE_URL = "https://oaipmh.arxiv.org/oai"
DEFAULT_METADATA_PREFIX = "arXiv"
# Contact-carrying User-Agent per arXiv policy (the skill standard): derived
# from the shared ``acquisition.arxiv.client`` seam so a deployment can
# advertise ``ANTIEK_ARXIV_CONTACT`` (mailto:) on the OAI channel too — the
# busiest and most ban-prone egress. The previous static string carried NO
# contact (audit 2026-08-12, docs/arxiv-skill-compliance-2026-08-12.md §6).
DEFAULT_USER_AGENT = default_user_agent()
DEFAULT_TIMEOUT_S = 30.0

# HarvestState file schema. v1 (pre-2026-08-12): {"resumption_token",
# "last_datestamp"}. v2 adds the progress bookkeeping (skip_count,
# last_page_at) + the version key itself. Loads are versioned: v1 files
# migrate transparently, an unknown FUTURE version reads as fresh (degrade,
# don't crash — the repo's state-file discipline) with a warning.
SCHEMA_VERSION = 2

logger = logging.getLogger("antiek.acquisition.arxiv.oai_pmh")


def _now_iso() -> str:
    """Wall-clock of the last completed page (UTC, ISO-8601): lets an operator
    see how stale a mid-harvest cursor is. Module-level so tests can pin it
    (the harvester has no clock param — timing is the throttle's job)."""
    return datetime.now(UTC).isoformat()

_OAI_NS = "{http://www.openarchives.org/OAI/2.0/}"

# arXiv's OAI set for the e-print repository. ``from``/``until`` windows scope a
# harvest to a date range without it.
_LIST_RECORDS_VERB = "ListRecords"


def default_harvest_state_path() -> str:
    """Crash-resumption cursor file. Honors ``ANTIEK_ARXIV_OAI_STATE_PATH`` for
    tests / alternate homes; defaults alongside the throttle state under
    ~/.antiek/."""
    env = os.environ.get("ANTIEK_ARXIV_OAI_STATE_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_oai_harvest.json")


@dataclass
class HarvestState:
    """The minimal cursor needed to resume an interrupted harvest.

    ``resumption_token`` is arXiv's opaque continuation handle for the NEXT
    page; ``None`` means "start a fresh ListRecords from the window" and the
    sentinel ``""`` after a completed harvest is never persisted (we clear the
    file instead). ``last_datestamp`` is the running MAX OAI datestamp consumed
    so far in this harvest (monotonic — it never retreats across pages),
    recorded for defensibility (which slice has been consumed) and, crucially,
    as the across-crash seed for the sync's high-water mark: after a crash
    mid-harvest the sync resumes from the cursor and only sees the REMAINING
    (often older) pages, so it seeds its high-water tracker from this persisted
    max to stay monotonic with what was actually consumed pre-crash. It is also
    the fallback incremental ``from`` if a token ever expires.

    Schema v2 adds operator observability: ``skip_count`` is the cumulative
    number of records consumed so far in this harvest (across crash
    boundaries — it never resets on resume), and ``last_page_at`` is the
    wall-clock (UTC ISO-8601) of the last COMPLETED page, so an operator can
    tell how far a multi-night backfill has gotten and how stale the cursor is.
    Neither drives resume logic (OAI-PMH tokens cannot skip records), they are
    progress bookkeeping + defensibility. ``schema_version`` is the state-file
    schema version (v1 files load without it and migrate in place on the next
    write; an unknown FUTURE version reads as fresh — see ``_read_state``).
    """

    resumption_token: str | None = None
    last_datestamp: str | None = None
    skip_count: int = 0
    last_page_at: str | None = None
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "schema_version": self.schema_version,
            "resumption_token": self.resumption_token,
            "last_datestamp": self.last_datestamp,
            "skip_count": self.skip_count,
            "last_page_at": self.last_page_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> HarvestState:
        """Tolerant load: a v1 file (no ``schema_version``) reads as version 1
        with zeroed bookkeeping; malformed cells degrade to their defaults
        rather than crashing the nightly (the repo's state-file discipline)."""
        resumption_token = d.get("resumption_token")
        last_datestamp = d.get("last_datestamp")
        schema_version = d.get("schema_version")
        skip_count = d.get("skip_count")
        last_page_at = d.get("last_page_at")
        return cls(
            resumption_token=resumption_token
            if isinstance(resumption_token, str)
            else None,
            last_datestamp=last_datestamp
            if isinstance(last_datestamp, str)
            else None,
            schema_version=schema_version
            if isinstance(schema_version, int) and not isinstance(schema_version, bool)
            else 1,
            skip_count=skip_count
            if isinstance(skip_count, int) and not isinstance(skip_count, bool)
            else 0,
            last_page_at=last_page_at if isinstance(last_page_at, str) else None,
        )


@dataclass(frozen=True)
class _Page:
    """One ListRecords page: its parsed records + the token for the next page
    (``None`` when the cursor is exhausted)."""

    records: list[ArxivOaiRecord]
    resumption_token: str | None


class OaiPmhHarvester:
    """Incremental OAI-PMH ListRecords harvester.

    The throttle is REQUIRED, not optional — there is no un-throttled path to
    the endpoint, by construction. ``client`` is injectable for tests
    (``MockTransport``); production passes ``None`` and a short-lived client is
    built per page (single connection, matching the throttle's single-stream
    assumption).
    """

    def __init__(
        self,
        *,
        throttle: ArxivThrottle,
        base_url: str | None = None,
        metadata_prefix: str = DEFAULT_METADATA_PREFIX,
        client: httpx.Client | None = None,
        state_path: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
    ) -> None:
        self._throttle = throttle
        self._base_url = base_url or os.environ.get(
            "ANTIEK_ARXIV_OAI_BASE_URL", DEFAULT_OAI_BASE_URL
        )
        self._metadata_prefix = metadata_prefix
        self._client = client
        self._state_path = Path(state_path or default_harvest_state_path())
        self._timeout_s = timeout_s

    # -- state file I/O (atomic write; matches the throttle's discipline) ----

    def _read_state(self) -> HarvestState:
        try:
            raw = self._state_path.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            return HarvestState()
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, ValueError, TypeError):
            return HarvestState()
        if not isinstance(parsed, dict):
            # A JSON array / string / number is not a state object — a torn or
            # hand-edited file must read as fresh, not crash the nightly.
            logger.warning(
                "arxiv OAI harvest state %s is not a JSON object; starting fresh",
                self._state_path,
            )
            return HarvestState()
        version = parsed.get("schema_version")
        if isinstance(version, int) and not isinstance(version, bool) and version > SCHEMA_VERSION:
            # A NEWER schema than this binary understands: do not guess at its
            # fields (resuming on a misread cursor is worse than re-walking the
            # window). Degrade to fresh like a corrupt file; the operator can
            # decide whether to --reset-state.
            logger.warning(
                "arxiv OAI harvest state %s is schema v%s (this build reads "
                "<= v%s); starting fresh",
                self._state_path,
                version,
                SCHEMA_VERSION,
            )
            return HarvestState()
        return HarvestState.from_dict(parsed)

    def _write_state(self, state: HarvestState) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._state_path.with_suffix(self._state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state.to_dict()), encoding="utf-8")
        os.replace(tmp, self._state_path)

    def _clear_state(self) -> None:
        with contextlib.suppress(FileNotFoundError):
            self._state_path.unlink()

    # -- across-crash high-water seed ----------------------------------------

    def persisted_max_datestamp(self) -> str | None:
        """The running MAX datestamp persisted by an INTERRUPTED harvest, or
        ``None`` if there is no mid-harvest cursor (a clean prior run cleared
        the state file, or this is a fresh harvest).

        The sync calls this on a ``resume=True`` run to seed its high-water
        tracker: after a crash mid-harvest the resumed harvest only re-streams
        the remaining (often older) pages, so without this seed the high-water
        mark could be set BELOW the max datestamp already consumed pre-crash.
        Seeding from the persisted max keeps the across-run mark monotonic with
        what was actually consumed. Read-only — it does not mutate the cursor.
        """
        return self._read_state().last_datestamp

    # -- URL construction ----------------------------------------------------

    def _page_url(
        self,
        *,
        resumption_token: str | None,
        from_date: str | None,
        until_date: str | None,
    ) -> str:
        """Compose a ListRecords URL.

        OAI-PMH is strict: once a ``resumptionToken`` is in play it is the SOLE
        argument (``verb`` + ``resumptionToken``, no ``metadataPrefix`` / window
        — sending them is a protocol error). The first page instead carries
        ``metadataPrefix`` + the optional ``from``/``until`` window.
        """
        params: list[tuple[str, str]] = [("verb", _LIST_RECORDS_VERB)]
        if resumption_token:
            params.append(("resumptionToken", resumption_token))
        else:
            params.append(("metadataPrefix", self._metadata_prefix))
            if from_date:
                params.append(("from", from_date))
            if until_date:
                params.append(("until", until_date))
        # httpx.URL percent-encodes the params (the resumption token can carry
        # ``|``/``:``/``=``); we do not hand-encode.
        return str(httpx.URL(self._base_url, params=params))

    # -- one page ------------------------------------------------------------

    def _fetch_page(self, url: str) -> _Page:
        """GET one ListRecords page through the host-global rate governor, parse it.

        SPR-09 M1: the send is routed through
        ``acquisition.arxiv.rate_governor.governed_request`` (passing the
        harvester's OWN ``self._throttle`` so the >=3s spacing + the 429
        ``banned_until`` engine are reused verbatim, never re-implemented) so the
        whole ``wait_if_needed -> send -> note_response`` critical section is held
        under the host-global ``fcntl.flock``. This is the busiest egress path; a
        BARE ``self._throttle.request(send)`` here was the exact hole that let a
        concurrent harvest + PDF fetch (or two harvests) both fire inside one 3s
        window and IP-ban the box. ``governed_request`` builds a one-shot governor
        over this throttle pointed at the CANONICAL default lock + state, so every
        arXiv job on the host contends on the same flock. An active ban surfaces
        as ``ArxivBanned`` from inside the governed call (the harvest PAUSES —
        re-hitting a banned endpoint is what extends the ban); it propagates
        unchanged.
        """
        from acquisition.arxiv.rate_governor import governed_request

        headers = {"User-Agent": DEFAULT_USER_AGENT}

        def send() -> httpx.Response:
            if self._client is not None:
                return self._client.get(
                    url, headers=headers, timeout=self._timeout_s
                )
            # Redirect-safe governed client: follows 301s (export.arxiv.org/oai2
            # → oaipmh.arxiv.org/oai, 2026-08) AND applies the host-global
            # per-hop arXiv gate to every hop — the initial hop is claimed by the
            # outer governed_request below, the redirect hop(s) by the hook.
            with arxiv_governed_client(
                throttle=self._throttle, follow_redirects=True, timeout=self._timeout_s
            ) as c:
                return c.get(url, headers=headers)

        resp = governed_request(send, throttle=self._throttle)
        resp.raise_for_status()

        records = parse_records(resp.content)
        token = _extract_resumption_token(resp.content)
        return _Page(records=records, resumption_token=token)

    # -- public harvest ------------------------------------------------------

    def harvest(
        self,
        *,
        from_date: str | None = None,
        until_date: str | None = None,
        resume: bool = True,
    ) -> Iterator[ArxivOaiRecord]:
        """Yield every record across all resumption-token pages.

        When ``resume`` and a persisted cursor exists, the harvest continues
        from the saved ``resumption_token`` rather than re-issuing the first
        page — so a crash mid-harvest does not re-fetch (and re-throttle) pages
        already consumed. After each page the cursor is persisted; on clean
        completion (no further token) the cursor file is cleared so the next
        invocation starts fresh.

        The ``from``/``until`` window applies only to the FIRST page; once a
        resumption token is in play arXiv carries the window internally.
        """
        state = self._read_state() if resume else HarvestState()
        token = state.resumption_token
        # Cumulative progress across crash boundaries: a resumed harvest keeps
        # counting from where the interrupted one stopped, so an operator can
        # always read "records consumed so far" off the state file.
        skip_count = state.skip_count

        while True:
            url = self._page_url(
                resumption_token=token,
                from_date=from_date,
                until_date=until_date,
            )
            page = self._fetch_page(url)

            # Track the running MAX datestamp consumed (monotonic — an
            # out-of-order or older page never lowers it). This is what the
            # sync seeds its high-water mark from on a post-crash resume, so
            # the mark can't fall below what was consumed before the crash.
            max_datestamp = state.last_datestamp
            for record in page.records:
                if record.datestamp and (
                    max_datestamp is None or record.datestamp > max_datestamp
                ):
                    max_datestamp = record.datestamp
                skip_count += 1
                yield record

            token = page.resumption_token
            if token:
                state = HarvestState(
                    resumption_token=token,
                    last_datestamp=max_datestamp,
                    skip_count=skip_count,
                    last_page_at=_now_iso(),
                )
                self._write_state(state)
            else:
                # Cursor exhausted — harvest complete. Clear so a re-run starts
                # a fresh window rather than resuming a finished one.
                self._clear_state()
                return

    def harvest_census(
        self,
        *,
        from_date: str | None = None,
        until_date: str | None = None,
        resume: bool = True,
        harvested_at: datetime | None = None,
    ) -> RightsCensus:
        """Page through a full harvest and fold it into a ``RightsCensus``.

        This is the one committed query the census is reproducible from: the
        prefix + window are stamped onto the returned census. It streams (folds
        record-by-record) so the full backfill never holds the whole corpus in
        memory.
        """
        tally = _TierTally()
        for record in self.harvest(
            from_date=from_date, until_date=until_date, resume=resume
        ):
            tally.add(record)
        return tally.freeze(
            metadata_prefix=self._metadata_prefix,
            from_date=from_date,
            until_date=until_date,
            harvested_at=harvested_at or datetime.now(UTC),
        )


def _extract_resumption_token(xml_bytes: bytes) -> str | None:
    """The ``<resumptionToken>`` text for the next page, or ``None``.

    An EMPTY ``<resumptionToken/>`` is the OAI signal for "last page" and must
    read as ``None`` (not ``""``), otherwise the loop would issue one more
    pointless request with an empty token. Returns ``None`` when the element is
    absent (a single-page response).
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    el = root.find(f".//{_OAI_NS}resumptionToken")
    if el is None or el.text is None:
        return None
    token = el.text.strip()
    return token or None
