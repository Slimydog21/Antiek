"""Enrich arXiv records with OpenAlex citation graph + ORCID author identity,
keeping rights STRICTLY OAI-PMH-authoritative (SPR-03).

The OAI-PMH harvest (SPR-01) lands one ``documents`` row per arXiv paper, with
the AUTHORITATIVE rights anchor — the ``<license>`` URI, the resolved tier — in
``documents.metadata``. OpenAlex adds value that arXiv metadata lacks: the
citation / reference graph, author disambiguation, and per-author ORCIDs (which
SPR-07's claim flow needs). This module JOINS that enrichment onto the
already-landed row, keyed by arXiv id (primary) or the DataCite arXiv DOI
(fallback).

THE HARD RULE (rigor #3, the load-bearing invariant of this sprint):
enrichment is ADDITIVE and PROVENANCE-TAGGED. It writes exactly one NEW
top-level metadata key, ``openalex_enrichment``, and NEVER touches
``license_uri`` / ``license_basis`` / ``rights_tier`` / ``license_content_class``
(or any other existing key). S2 / OpenAlex omit arXiv's ``<license>`` element;
letting them touch rights would mis-grant. OAI-PMH stays authoritative for
identity + rights; OpenAlex is enrichment only. The reviewer tells the two
apart because every enriched field rides under one tagged key
(``source="openalex"``, ``fetched_at=<iso8601>``).

REUSE, not a fork (M1 acceptance): the OpenAlex fetch goes through
``acquisition.openaccess.openalex.fetch_work_record`` — the existing connector's
``_build_url`` / ``_http_get`` / ``OAThrottle`` plumbing. There is NO second
HTTP client here. The metadata read/merge/write reuses the single-writer path
(``runtime.db_lock.connect_write``) and the ``_maybe_json`` convention
``oai_persist`` uses.

Coverage honesty (rigor #1): a paper that does not match in OpenAlex is left
UN-enriched and counted as a MISS — never fabricated. OpenAlex lags recent
arXiv papers, so a window of just-posted preprints will report LOW coverage; the
report SAYS SO rather than implying full enrichment.

Edge cases handled (named per the prime directive):
  * no OpenAlex match (0 results) -> miss, row left untouched.
  * the work has no ``authorships`` / no ``referenced_works`` / no
    ``cited_by_count`` -> those parse to ``[]`` / ``0``; the row is still a match
    (we found the work, it just has sparse enrichment).
  * an author with no ORCID -> stored with ``orcid=None`` (never invented).
  * a row whose ``metadata`` is malformed JSON -> the row is SKIPPED as a
    malformed-metadata miss (we never blind-overwrite a row we cannot safely
    read + merge).
  * a non-arXiv document id passed in -> skipped (we only enrich rows whose
    metadata names ``source == "arxiv_oai_pmh"`` / carries an ``arxiv_id``).

Out of scope (explicitly NOT done here): minting graph nodes for cited works,
writing to the ``edges`` table (that needs investigation-scoped graph nodes —
this is the in-scope "just store the edges in metadata"), PDF fetching, and any
write to a rights field.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional

import httpx

from acquisition.openaccess.openalex import fetch_work_record
from acquisition.openaccess.throttle import POLITE_POOL_MAILTO, OAThrottle
from runtime.db_lock import LockedConnection, connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import _maybe_json

from .adapter import arxiv_doc_id
from .authors import parse_authorships

# The single metadata key enrichment owns. Everything OpenAlex contributes lives
# under here, tagged with its provenance — so the rights keys at the top level
# are visibly untouched.
ENRICHMENT_KEY = "openalex_enrichment"

# The rights keys this module is FORBIDDEN to touch. Named here so the
# immutability discipline is explicit in code (the load-bearing test asserts on
# the same set). The merge reads the existing metadata and re-writes it with ONLY
# the enrichment key added, so these are preserved by construction; this tuple
# documents the contract and powers the in-module assertion guard.
PROTECTED_RIGHTS_KEYS = (
    "license_uri",
    "license_basis",
    "rights_tier",
    "license_content_class",
)


# ---------------------------------------------------------------------------
# Result shapes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichmentCoverage:
    """The measured join coverage of one enrichment pass.

    ``matched / attempted`` is THE number the report leads with (rigor #1). A
    ``miss`` is an arXiv row with no OpenAlex match (or one we declined to merge
    because its metadata was malformed). ``coverage`` is COMPUTED, never asserted.
    """

    attempted: int = 0
    matched: int = 0
    missed: int = 0
    malformed: int = 0

    def __post_init__(self) -> None:
        # The partition must close: every attempted row is matched or missed.
        if self.matched + self.missed != self.attempted:
            raise ValueError(
                f"coverage partition not exhaustive: matched({self.matched}) + "
                f"missed({self.missed}) != attempted({self.attempted})"
            )
        if not 0 <= self.malformed <= self.missed:
            raise ValueError(
                f"malformed({self.malformed}) must be within [0, missed({self.missed})]"
            )

    @property
    def coverage(self) -> float:
        """Matched fraction of attempted rows — computed, never hand-rounded.
        0.0 for an empty pass rather than dividing by zero."""
        return self.matched / self.attempted if self.attempted else 0.0


@dataclass
class _CoverageTally:
    """Mutable accumulator folded into the frozen ``EnrichmentCoverage``."""

    attempted: int = 0
    matched: int = 0
    missed: int = 0
    malformed: int = 0

    def freeze(self) -> EnrichmentCoverage:
        return EnrichmentCoverage(
            attempted=self.attempted,
            matched=self.matched,
            missed=self.missed,
            malformed=self.malformed,
        )


# ---------------------------------------------------------------------------
# The enrichment payload (pure; recorded-fixture tests target this)
# ---------------------------------------------------------------------------


def build_enrichment(raw_work: dict, *, fetched_at: Optional[datetime] = None) -> dict:
    """Build the ``openalex_enrichment`` metadata payload from a raw work dict.

    PURE: no network, no DB. ``raw_work`` is the full OpenAlex work JSON (as
    ``fetch_work_record`` returns). Every field is provenance-tagged
    (``source="openalex"`` + ``fetched_at``) so a reviewer separates this from
    the arXiv-authoritative data. ``referenced_works`` is stored as the in-scope
    "just store the edges in metadata" — id + DOI per reference, NOT minted as
    graph nodes.
    """
    when = (fetched_at or datetime.now(timezone.utc)).isoformat()

    authors = [
        {
            "orcid": a.orcid,
            "author_position": a.author_position,
            "display_name": a.display_name,
        }
        for a in parse_authorships(raw_work)
    ]

    # referenced_works on a raw work is a list of OpenAlex work URLs (ids); the
    # per-reference DOI is not inlined by OpenAlex, so we store the id and a null
    # doi placeholder (resolving each id to its DOI would be a fan-out fetch that
    # is out of scope — "just store the edges"). The shape stays uniform so a
    # later pass can backfill the doi without a schema change.
    referenced = [
        {"openalex_id": str(ref), "doi": None}
        for ref in (raw_work.get("referenced_works") or [])
        if ref
    ]

    cited_by = raw_work.get("cited_by_count")
    cited_by_count = int(cited_by) if isinstance(cited_by, (int, float)) else 0

    return {
        "source": "openalex",
        "fetched_at": when,
        "openalex_id": str(raw_work.get("id") or "") or None,
        "authors": authors,
        "referenced_works": referenced,
        "cited_by_count": cited_by_count,
    }


def merge_enrichment(existing_metadata: dict, enrichment: dict) -> dict:
    """Return a NEW metadata dict = existing + the single enrichment key.

    ADDITIVE MERGE ONLY (the load-bearing invariant): the existing metadata is
    copied and the one ``openalex_enrichment`` key is added/replaced. No existing
    key is removed or overwritten. An in-function assertion re-checks that every
    protected rights key is byte-identical before and after — a defensive guard
    so a future edit to this function cannot silently start mutating rights.
    """
    merged = dict(existing_metadata)
    merged[ENRICHMENT_KEY] = enrichment

    # Defensive guard: rights keys must be untouched by the merge. They are, by
    # construction (we only added one new key), but assert it so a regression is
    # caught here, not only in the dedicated immutability test.
    for key in PROTECTED_RIGHTS_KEYS:
        if existing_metadata.get(key) != merged.get(key):
            raise AssertionError(
                f"enrichment merge mutated protected rights key {key!r} "
                f"({existing_metadata.get(key)!r} -> {merged.get(key)!r})"
            )
    return merged


# ---------------------------------------------------------------------------
# DB-touching enrichment of a single row (single-writer path)
# ---------------------------------------------------------------------------


def _load_metadata(con: LockedConnection, document_id: str) -> Optional[dict]:
    """Read + parse the existing ``documents.metadata`` JSON for a row.

    Returns the parsed dict, or ``None`` when the row is absent. Raises
    ``ValueError`` on malformed JSON (the caller treats that as a malformed
    miss — we never blind-overwrite a row we cannot safely read)."""
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ? LIMIT 1",
        [document_id],
    ).fetchone()
    if row is None:
        return None
    raw = row[0]
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"malformed metadata JSON for {document_id}") from exc


def enrich_one(
    con: LockedConnection,
    *,
    arxiv_id: str,
    doi: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    throttle: Optional[OAThrottle] = None,
    base_url: Optional[str] = None,
    mailto: str = POLITE_POOL_MAILTO,
    fetched_at: Optional[datetime] = None,
) -> bool:
    """Enrich ONE arXiv row in place. Returns ``True`` on a match (row updated),
    ``False`` on a miss (no OpenAlex result; row left UNTOUCHED).

    The merge is additive (``merge_enrichment``): the row's existing metadata —
    including every rights key — is preserved verbatim, with only the
    ``openalex_enrichment`` key added. A row with no existing metadata row is a
    miss (nothing to enrich). Malformed existing metadata raises ``ValueError``
    so the batch caller can record a malformed miss rather than overwrite it.
    """
    document_id = arxiv_doc_id(arxiv_id)
    existing = _load_metadata(con, document_id)
    if existing is None:
        # No such row to enrich. Treat as a miss at the caller.
        return False

    raw_work = fetch_work_record(
        arxiv_id=arxiv_id,
        doi=doi,
        client=client,
        throttle=throttle,
        base_url=base_url,
        mailto=mailto,
    )
    if raw_work is None:
        return False  # genuine no-match; never fabricate one.

    enrichment = build_enrichment(raw_work, fetched_at=fetched_at)
    merged = merge_enrichment(existing, enrichment)
    con.execute(
        "UPDATE documents SET metadata = ? WHERE document_id = ?",
        [_maybe_json(merged), document_id],
    )
    return True


# ---------------------------------------------------------------------------
# Batch enrichment over a corpus (single write lock)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _ArxivRow:
    """An arXiv row to enrich, read off the documents table."""

    arxiv_id: str
    doi: Optional[str] = None


def _arxiv_rows_to_enrich(con: LockedConnection) -> List[_ArxivRow]:
    """Find the arXiv OAI rows in the corpus that are candidates for enrichment.

    Selects rows whose metadata names ``source == "arxiv_oai_pmh"`` and carries an
    ``arxiv_id`` — i.e. the SPR-01 harvest rows. A row that already has an
    ``openalex_enrichment`` key is still re-attempted (re-running refreshes it);
    idempotency is at the metadata-merge level (the key is replaced, not
    duplicated)."""
    rows = con.execute("SELECT document_id, metadata FROM documents").fetchall()
    out: List[_ArxivRow] = []
    for _doc_id, raw in rows:
        if raw is None:
            continue
        try:
            meta = raw if isinstance(raw, dict) else json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue
        if meta.get("source") != "arxiv_oai_pmh":
            continue
        arxiv_id = meta.get("arxiv_id")
        if not arxiv_id:
            continue
        out.append(_ArxivRow(arxiv_id=str(arxiv_id)))
    return out


def enrich_corpus(
    *,
    arxiv_ids: Optional[List[str]] = None,
    db_path: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    throttle: Optional[OAThrottle] = None,
    base_url: Optional[str] = None,
    mailto: str = POLITE_POOL_MAILTO,
    fetched_at: Optional[datetime] = None,
) -> EnrichmentCoverage:
    """Enrich a corpus of arXiv rows with OpenAlex, under ONE write lock.

    ``arxiv_ids`` scopes the pass to specific ids; when omitted, every SPR-01
    arXiv OAI row in the DB is attempted. The entire pass runs inside a single
    ``connect_write`` critical section (the single-writer invariant) so a batch
    serializes against any other writer exactly once.

    Returns the measured ``EnrichmentCoverage`` — matched / attempted, with the
    miss + malformed split so the report can state the honesty number.
    """
    resolved = ensure_initialized(db_path or default_db_path())
    tally = _CoverageTally()

    with connect_write(resolved, purpose="acquisition/arxiv_enrich") as con:
        if arxiv_ids is not None:
            targets = [_ArxivRow(arxiv_id=str(a)) for a in arxiv_ids]
        else:
            targets = _arxiv_rows_to_enrich(con)

        for target in targets:
            tally.attempted += 1
            try:
                matched = enrich_one(
                    con,
                    arxiv_id=target.arxiv_id,
                    doi=target.doi,
                    client=client,
                    throttle=throttle,
                    base_url=base_url,
                    mailto=mailto,
                    fetched_at=fetched_at,
                )
            except ValueError:
                # Malformed existing metadata: a miss we do NOT overwrite.
                tally.missed += 1
                tally.malformed += 1
                continue
            if matched:
                tally.matched += 1
            else:
                tally.missed += 1

    return tally.freeze()


# ---------------------------------------------------------------------------
# Coverage report (matches reports/arxiv_census.md style)
# ---------------------------------------------------------------------------


def render_coverage_report(
    coverage: EnrichmentCoverage,
    *,
    db_path: Optional[str] = None,
    generated_at: Optional[datetime] = None,
    provisional_note: Optional[str] = None,
) -> str:
    """Render the markdown coverage report (matches ``reports/arxiv_census.md``
    style). Every % is COMPUTED from the counts via ``EnrichmentCoverage.coverage``,
    not hand-edited. The low-coverage honesty caveat (rigor #1) is always present.

    When ``provisional_note`` is set, a prominent PROVISIONAL banner is rendered
    NEAR THE TOP (mirroring ``reports/arxiv_census.md``) so a reader skimming the
    headline cannot mistake a seeded/fixture pass for live-corpus coverage. A live
    operator run passes ``provisional_note=None`` and gets no banner. The note
    never alters any count — the %'s stay computed from the tally.
    """
    when = (generated_at or datetime.now(timezone.utc)).isoformat()
    pct = coverage.coverage * 100.0
    miss_pct = (coverage.missed / coverage.attempted * 100.0) if coverage.attempted else 0.0

    lines: List[str] = []
    lines.append("# arXiv → OpenAlex enrichment coverage")
    lines.append("")
    if provisional_note:
        lines.append(f"> **PROVISIONAL:** {provisional_note}")
        lines.append("")
    lines.append(
        "Generated by `acquisition.arxiv.enrich_openalex` over the harvested arXiv "
        "OAI rows. Do not hand-edit — re-run the enrichment to regenerate."
    )
    lines.append("")
    lines.append("## What this measures")
    lines.append("")
    lines.append(
        "The share of arXiv records (SPR-01 OAI-PMH rows) that JOINED to an "
        "OpenAlex work — keyed on arXiv id (primary) then the DataCite arXiv DOI "
        "`10.48550/arXiv.<id>` (fallback). Enrichment is ADDITIVE: it adds an "
        "`openalex_enrichment` metadata key (citation graph + ORCID author "
        "identity) and never touches the OAI-PMH-authoritative `license_uri` or "
        "rights tier. A paper with no OpenAlex match is left un-enriched and "
        "counted as a MISS — never fabricated."
    )
    lines.append("")
    lines.append("## Coverage")
    lines.append("")
    lines.append("| metric | count | share |")
    lines.append("| --- | ---: | ---: |")
    lines.append(f"| matched in OpenAlex | {coverage.matched} | {pct:.1f}% |")
    lines.append(f"| missed (no match) | {coverage.missed} | {miss_pct:.1f}% |")
    lines.append(
        f"| **attempted (arXiv rows)** | **{coverage.attempted}** | 100.0% |"
    )
    lines.append("")
    lines.append(
        f"- **of which malformed-metadata misses (skipped, not overwritten):** "
        f"{coverage.malformed}."
    )
    lines.append(
        f"- **partition self-check:** matched + missed = "
        f"{coverage.matched + coverage.missed} == attempted "
        f"({coverage.attempted}). (Enforced by `EnrichmentCoverage.__post_init__`.)"
    )
    lines.append("")
    lines.append("## Match coverage")
    lines.append("")
    lines.append(
        f"**{coverage.matched} / {coverage.attempted} = {pct:.1f}% of arXiv rows "
        f"matched an OpenAlex work.** This % is computed from the counts above, "
        f"not asserted."
    )
    lines.append("")
    lines.append("## Honesty caveat (OpenAlex lag)")
    lines.append("")
    if coverage.attempted == 0:
        lines.append(
            "No arXiv rows were attempted (empty corpus), so there is no coverage "
            "to report. Run the SPR-01 harvest first, then re-run enrichment."
        )
    elif pct < 80.0:
        lines.append(
            f"Coverage is **{pct:.1f}%** — below full. OpenAlex LAGS recent arXiv "
            f"postings (it ingests works on a delay), so a window of just-posted "
            f"preprints will not yet be in OpenAlex and is correctly counted as a "
            f"miss. This number does NOT imply full enrichment; the un-matched "
            f"{coverage.missed} rows keep only their OAI-PMH-authoritative "
            f"metadata (which is sufficient for rights + identity — OpenAlex is "
            f"enrichment, not the source of truth)."
        )
    else:
        lines.append(
            f"Coverage is **{pct:.1f}%**. The un-matched {coverage.missed} rows "
            f"keep only their OAI-PMH-authoritative metadata; OpenAlex lags recent "
            f"postings, so a freshly-harvested window will show lower coverage "
            f"than an older one. OAI-PMH stays authoritative for rights + identity "
            f"regardless."
        )
    lines.append("")
    if db_path:
        lines.append(f"_Source DB: `{db_path}`. Generated at {when} (UTC)._")
    else:
        lines.append(f"_Generated at {when} (UTC)._")
    lines.append("")
    return "\n".join(lines)


def write_coverage_report(
    coverage: EnrichmentCoverage,
    out_path: str,
    *,
    db_path: Optional[str] = None,
    generated_at: Optional[datetime] = None,
    provisional_note: Optional[str] = None,
) -> None:
    """Write the coverage report to ``out_path``. ``provisional_note`` (when set)
    renders the PROVISIONAL banner — pass it for a seeded/fixture pass, leave it
    ``None`` for a live operator run."""
    text = render_coverage_report(
        coverage,
        db_path=db_path,
        generated_at=generated_at,
        provisional_note=provisional_note,
    )
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)
