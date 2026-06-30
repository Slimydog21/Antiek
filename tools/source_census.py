"""Per-source corpus-value census + the wired onboarding kill-gate (reframe P3).

WHY THIS EXISTS (reframe finding #2): the arXiv spec NAMED the failure mode — "an
elaborate apparatus is built for a corpus that turns out to be ~1% useful" — but
wired NO stop-rule; "measure before build" lived only in prose and was ignored once
(the SPR-01 census was satisfied on mocked data). This module replaces the prose
stop-rule with a MACHINE-CHECKED gate: a per-source census of corpus VALUE, and a
predicate that BLOCKS onboarding any source AFTER arXiv whose census falls below the
bar. ``tools/lint/source_gate.py`` is the CLI that exits non-zero on a violation.

CORPUS-VALUE, NOT MONETIZATION (the reframe's whole point): the corpus's worth is
feeding Research/Read/Write/Speak — a legally-clean, metadata-complete, link-back-
resolvable, low-duplication corpus — NOT an ad %. So the GATING metrics are
completeness / link-back / dedup; ``t1_pct`` (redistributable-open share) and
``open_pct`` are REPORTED but ADVISORY (a source can be valuable to research while
mostly link-back-only — that is arXiv itself).

This module owns the CONTRACT (the JSON shape written to
``reports/source_census.json``) + the DB-backed producer
(``compute_source_census(con, source)`` over the real corpus, via the one
``substrate.dedup`` identity ladder) + the THRESHOLDS + the gate PREDICATE.

The producer is deliberately DB-only: no network, no live HTTP probing. The
linkback metric is therefore "has a persisted HTTP(S) origin URI" rather than
"origin was fetched during the gate." Live reachability belongs in an operator
audit, not in a deterministic source-onboarding stop-rule. The CLI is the explicit
operator-facing emission path for ``reports/source_census.json``.
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.dedup import Confidence, IdentityRecord, identity_key
from substrate.graph import default_db_path, ensure_initialized

# ---------------------------------------------------------------------------
# Thresholds — PROVISIONAL until calibrated against the first REAL arXiv census
# (the current values are reasoned defaults, not measured). They are corpus-VALUE
# bars, deliberately NOT monetization bars. Percentages are 0..100.
# ---------------------------------------------------------------------------

# A source's documents must be metadata-complete enough to be usable as research
# evidence (title + a source URI present). Below this the corpus is noise.
METADATA_COMPLETE_MIN = 95.0
# Every served/cited item must resolve back to its origin (arXiv ToU + every other
# source's attribution needs a working link-back). This is near-absolute.
LINKBACK_RESOLVABLE_MIN = 99.0
# A source that mostly re-imports what the corpus already holds adds cost, not
# value. EXCLUSIVE bound: dedup_overlap must be strictly below this.
DEDUP_OVERLAP_MAX = 20.0

# The reference source the gate EXEMPTS. arXiv is the calibration baseline the whole
# reframe is built on; the gate guards every source ADDED AFTER it, not arXiv itself
# (gating the baseline against thresholds derived from it is circular).
REFERENCE_SOURCE = "arxiv"

_REPO = Path(__file__).resolve().parent.parent
_ARXIV_METADATA_SOURCES = {"arxiv", "arxiv_oai_pmh", "arxiv_bulk"}
_T1_VALUES = {"T1", "T1_REDISTRIBUTABLE", "t1", "redistributable"}
_SOURCE_ID_KEYS = ("source_id", "guid", "id", "post_id", "external_id")
_URI_KEYS = (
    "source_uri",
    "canonical_url",
    "final_url",
    "requested_url",
    "url",
    "link",
    "href",
)


def _pct(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((float(numerator) / float(denominator)) * 100.0, 3)


def _metadata_obj(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, Mapping) else {}
    return {}


def _first_nonempty(*values: Any) -> str | None:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _metadata_first(meta: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _has_http_linkback(source_uri: str | None, meta: Mapping[str, Any]) -> bool:
    uri = _first_nonempty(source_uri, _metadata_first(meta, _URI_KEYS))
    if not uri:
        return False
    parsed = urlparse(uri)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _row_source(
    document_id: str, source_uri: str | None, meta: Mapping[str, Any]
) -> str | None:
    declared = _first_nonempty(meta.get("source"))
    if declared in _ARXIV_METADATA_SOURCES:
        return REFERENCE_SOURCE
    if _first_nonempty(meta.get("arxiv_id")) or document_id.startswith("doc-arxiv-"):
        return REFERENCE_SOURCE
    if source_uri:
        parsed = urlparse(source_uri)
        host = parsed.netloc.lower()
        if host.endswith("arxiv.org") and parsed.path.startswith(("/abs/", "/pdf/")):
            return REFERENCE_SOURCE
    return declared


def _rights_tier(meta: Mapping[str, Any]) -> str | None:
    return _first_nonempty(meta.get("rights_tier"), meta.get("tier"))


def _content_class(row_content_class: str | None, meta: Mapping[str, Any]) -> str | None:
    return _first_nonempty(row_content_class, meta.get("license_content_class"))


def _is_t1(meta: Mapping[str, Any], row_content_class: str | None) -> bool:
    tier = _rights_tier(meta)
    if tier in _T1_VALUES:
        return True
    return _content_class(row_content_class, meta) in SERVABLE_CONTENT_CLASSES


def _is_open(meta: Mapping[str, Any], row_content_class: str | None) -> bool:
    return _content_class(row_content_class, meta) in SERVABLE_CONTENT_CLASSES


def _identity_for_row(
    *,
    document_id: str,
    source: str,
    source_uri: str | None,
    title: str | None,
    author: str | None,
    raw_text: str | None,
    meta: Mapping[str, Any],
) -> IdentityRecord:
    source_id = _metadata_first(meta, _SOURCE_ID_KEYS)
    if source == REFERENCE_SOURCE:
        source_id = source_id or _first_nonempty(meta.get("arxiv_id"))
    return IdentityRecord(
        ref_id=document_id,
        source=source,
        doi=_first_nonempty(meta.get("doi")),
        isbn=_first_nonempty(meta.get("isbn"), meta.get("isbn13"), meta.get("isbn_13")),
        arxiv_id=_first_nonempty(meta.get("arxiv_id")),
        source_id=source_id,
        title=title,
        author=author,
        body=raw_text,
        license=None,
    )


def _finite_pct(name: str, value: Any, source: str) -> float:
    """Coerce a census percentage to a finite float in the 0..100 range."""
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(
            f"source census for {source!r}: {name}={value!r} is not finite — a "
            f"NaN/inf metric must never reach the gate (it would silently pass)."
        )
    if not 0.0 <= v <= 100.0:
        raise ValueError(
            f"source census for {source!r}: {name}={v} is outside 0..100."
        )
    return v


@dataclass(frozen=True)
class SourceCensus:
    """One source's measured corpus-value census. ``*_pct`` are 0..100.

    ``t1_pct`` / ``open_pct`` are REPORTED for visibility but are NOT gated — the
    corpus's value is feeding products, not ad share (see module docstring)."""

    source: str
    total: int
    t1_pct: float
    open_pct: float
    metadata_complete_pct: float
    dedup_overlap_pct: float
    linkback_resolvable_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceCensus:
        """Build from a parsed JSON object, failing on missing/malformed fields."""
        if not isinstance(d, dict):
            raise ValueError(
                f"source census entry must be a JSON object, got "
                f"{type(d).__name__}: {d!r}"
            )
        missing = {f for f in cls.__dataclass_fields__} - set(d)
        if missing:
            raise ValueError(
                f"source census for {d.get('source', '?')!r} is missing required "
                f"field(s) {sorted(missing)} — a partial census cannot be gated "
                f"(deny-by-default: no field may default to a passing value)."
            )
        source = str(d["source"])
        return cls(
            source=source,
            total=int(d["total"]),
            t1_pct=_finite_pct("t1_pct", d["t1_pct"], source),
            open_pct=_finite_pct("open_pct", d["open_pct"], source),
            metadata_complete_pct=_finite_pct(
                "metadata_complete_pct", d["metadata_complete_pct"], source
            ),
            dedup_overlap_pct=_finite_pct(
                "dedup_overlap_pct", d["dedup_overlap_pct"], source
            ),
            linkback_resolvable_pct=_finite_pct(
                "linkback_resolvable_pct", d["linkback_resolvable_pct"], source
            ),
        )


def compute_source_census(con: Any, source: str) -> SourceCensus:
    """Measure one source's corpus-value census from the persisted ``documents`` table.

    The source selector is intentionally conservative. arXiv rows are recognised
    from connector metadata, arXiv ids, ``doc-arxiv-*`` ids, or arxiv.org origin
    links. Other sources must declare ``metadata.source == source``.
    """
    requested_source = source.strip()
    if not requested_source:
        raise ValueError("source must be non-empty")

    rows = con.execute(
        """
        SELECT document_id, source_uri, title, author, raw_text, metadata, content_class
        FROM documents
        ORDER BY document_id
        """
    ).fetchall()

    measured: list[
        tuple[
            str,
            str | None,
            str | None,
            str | None,
            str | None,
            dict[str, Any],
            str | None,
        ]
    ] = []
    for row in rows:
        document_id, source_uri, title, author, raw_text, metadata_raw, content_class = row
        meta = _metadata_obj(metadata_raw)
        row_source = _row_source(str(document_id), source_uri, meta)
        if row_source == requested_source:
            measured.append(
                (
                    str(document_id),
                    source_uri,
                    title,
                    author,
                    raw_text,
                    meta,
                    content_class,
                )
            )

    total = len(measured)
    if total == 0:
        return SourceCensus(
            source=requested_source,
            total=0,
            t1_pct=0.0,
            open_pct=0.0,
            metadata_complete_pct=0.0,
            dedup_overlap_pct=0.0,
            linkback_resolvable_pct=0.0,
        )

    metadata_complete = 0
    linkback_resolvable = 0
    t1 = 0
    open_count = 0
    duplicate_high_conf = 0
    seen_high_conf: set[tuple[str, str]] = set()

    for document_id, source_uri, title, author, raw_text, meta, content_class in measured:
        if _first_nonempty(title) and _has_http_linkback(source_uri, meta):
            metadata_complete += 1
        if _has_http_linkback(source_uri, meta):
            linkback_resolvable += 1
        if _is_t1(meta, content_class):
            t1 += 1
        if _is_open(meta, content_class):
            open_count += 1

        key = identity_key(
            _identity_for_row(
                document_id=document_id,
                source=requested_source,
                source_uri=source_uri,
                title=title,
                author=author,
                raw_text=raw_text,
                meta=meta,
            )
        )
        if key.confidence is Confidence.HIGH:
            identity = (key.key_type.value, key.key)
            if identity in seen_high_conf:
                duplicate_high_conf += 1
            else:
                seen_high_conf.add(identity)

    return SourceCensus(
        source=requested_source,
        total=total,
        t1_pct=_pct(t1, total),
        open_pct=_pct(open_count, total),
        metadata_complete_pct=_pct(metadata_complete, total),
        dedup_overlap_pct=_pct(duplicate_high_conf, total),
        linkback_resolvable_pct=_pct(linkback_resolvable, total),
    )


def compute_source_censuses(con: Any, sources: list[str]) -> list[SourceCensus]:
    return [compute_source_census(con, source) for source in sources]


def gate_failures(c: SourceCensus, *, is_reference: bool = False) -> list[str]:
    """The gate violations for ONE source's census — empty list == passes."""
    fails: list[str] = []
    if c.total <= 0:
        fails.append(
            f"total={c.total}: no documents measured — a source must have a "
            f"measured corpus to be certified (deny-by-default, not a vacuous pass)."
        )
        return fails
    nonfinite = [
        name
        for name, val in (
            ("metadata_complete_pct", c.metadata_complete_pct),
            ("linkback_resolvable_pct", c.linkback_resolvable_pct),
            ("dedup_overlap_pct", c.dedup_overlap_pct),
        )
        if not math.isfinite(val)
    ]
    if nonfinite:
        fails.append(
            f"non-finite gating metric(s) {nonfinite}: NaN/inf must never pass "
            f"(every threshold comparison against NaN is False — deny-by-default)."
        )
        return fails
    if is_reference:
        return fails
    if c.metadata_complete_pct < METADATA_COMPLETE_MIN:
        fails.append(
            f"metadata_complete_pct={c.metadata_complete_pct:.1f} < "
            f"{METADATA_COMPLETE_MIN} (corpus too incomplete to be usable evidence)."
        )
    if c.linkback_resolvable_pct < LINKBACK_RESOLVABLE_MIN:
        fails.append(
            f"linkback_resolvable_pct={c.linkback_resolvable_pct:.1f} < "
            f"{LINKBACK_RESOLVABLE_MIN} (cited items must resolve back to origin)."
        )
    if c.dedup_overlap_pct >= DEDUP_OVERLAP_MAX:
        fails.append(
            f"dedup_overlap_pct={c.dedup_overlap_pct:.1f} >= {DEDUP_OVERLAP_MAX} "
            f"(source mostly re-imports corpus the graph already holds)."
        )
    return fails


def evaluate(censuses: list[SourceCensus]) -> dict[str, list[str]]:
    """Per-source gate result over ALL censuses."""
    refs = [c for c in censuses if c.source == REFERENCE_SOURCE]
    if len(refs) > 1:
        raise ValueError(
            f"{len(refs)} {REFERENCE_SOURCE!r} census rows — the reference source "
            f"must be unique; duplicate reference rows are a mislabel/evasion signal."
        )
    return {
        c.source: gate_failures(c, is_reference=(c.source == REFERENCE_SOURCE))
        for c in censuses
    }


def load_censuses(path: Path) -> list[SourceCensus]:
    """Parse ``reports/source_census.json`` (a JSON array of census objects)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            f"{path} must be a JSON array of source censuses, got {type(data).__name__}."
        )
    return [SourceCensus.from_dict(d) for d in data]


def save_censuses(censuses: list[SourceCensus], path: Path) -> None:
    """Write the census array deterministically so re-emits are clean diffs."""
    payload = [c.to_dict() for c in sorted(censuses, key=lambda c: c.source)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.source_census",
        description="Compute reports/source_census.json from the documents table.",
    )
    p.add_argument(
        "--source",
        action="append",
        required=True,
        help="Source label to compute; repeatable (for example: --source arxiv).",
    )
    p.add_argument(
        "--db-path",
        default=None,
        help="DuckDB graph path (default ANTIEK_DUCKDB_PATH or configured graph DB).",
    )
    p.add_argument(
        "--out",
        default=str(_REPO / "reports" / "source_census.json"),
        help="Output JSON path (default reports/source_census.json).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db_path = ensure_initialized(args.db_path or default_db_path())
    import duckdb

    con = duckdb.connect(db_path, read_only=True)
    try:
        censuses = compute_source_censuses(con, args.source)
    finally:
        con.close()
    save_censuses(censuses, Path(args.out))
    print(
        f"wrote {len(censuses)} source census row(s) to {args.out}: "
        f"{', '.join(c.source for c in censuses)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
