"""Cross-source identity: the content-stable key a real-world work resolves to
regardless of how many sources surfaced it (SPR-04).

A work's identity is its STRONGEST stable identifier — never a mutable
title+author string. The first prod corpus run surfaced exactly why the
title+author heuristic is dangerous in both directions:

  * **false merge** — generic titles ("History" by "Anonymous") collide into
    one document even though they are distinct works, because the normalized
    title+author string is identical;
  * **false split** — the same paper carrying the same DOI on arXiv +
    OpenAlex + PMC slips through as three documents because the title strings
    differ by whitespace, casing, a subtitle, or "vs." vs "versus".

Stable identifiers are the only thing that is BOTH collision-free on generic
titles AND complete across sources, so identity precedence is, highest first::

    DOI  >  ISBN-13  >  arXiv-id  >  source-id  >  content-hash  >  (title+author, LOW)

``source-id`` is a source-local identifier (a Gutenberg book id, an
archive.org identifier) — stable within its source, so the same Gutenberg work
re-fetched keys identically even when it carries no DOI/ISBN/arXiv-id and the
body was not extracted at discovery. The title+author hash survives only as an
explicitly LOW-confidence last resort: a record with no stable id of any kind
and no extractable body. The collapse pass refuses to silently merge two works
on a low-confidence key — admitting the coverage gap is better than polluting
the corpus with a wrong merge.

This module is the SINGLE home for what "identity" means. There is exactly one
precedence ladder (:class:`KeyType`) and one set of identifier normalizers; the
orchestrator's cross-source dedup (``acquisition.corpus_quality.dedup_candidates``)
keys its clusters through :func:`dedup_key` here rather than re-deriving a
second, divergent ladder. The output of :func:`identity_key` is therefore BOTH
the live dedup driver AND the basis SPR-01 turns into the content-stable
``document_id`` (see :func:`document_id_basis`): dedup and idempotency are the
same fact, computed once, in one place.

Collapse + canonical selection (:func:`collapse`) groups candidate records by
identity key and picks one canonical record by a deterministic policy, keeping
every contributing source's provenance and reconciling the license to the
most-permissive POSITIVELY-VERIFIED basis (:func:`reconcile_license`) — never
inventing servability the way the §9.0 deny-by-default invariant forbids.

§16 box-bounded: this is pure in-process logic over candidate records. It
introduces no store, no service, no index engine, and reaches no source.
"""

from __future__ import annotations

import enum
import hashlib
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

# CC / license semantics live in exactly ONE place (a legal determination). We
# read the resolution they already computed; we never re-encode "is CC-BY more
# permissive than CC-BY-NC" here. See licenses_core's module docstring.
from acquisition.licenses_core import (
    PUBLIC_DOMAIN_CONTENT_CLASS,
    LicenseResolution,
)
from substrate.constants import SERVABLE_CONTENT_CLASSES

# ---------------------------------------------------------------------------
# Identity-key contract (consumed by SPR-01 AND by the orchestrator's dedup).
#
#   identity_key(record) -> IdentityKey(key, key_type, confidence)
#
#   key_type  ∈ {doi, isbn, arxiv, source_id, content, title_author}
#              (precedence order)
#   confidence ∈ {high, low}
#       high  — a stable identifier (DOI / ISBN-13 / arXiv-id / source-id) OR a
#               content-hash over real extracted body text.
#       low   — the title+author fallback ONLY: no stable id AND no body.
#
#   dedup_key(record, key_type) -> Optional[str]
#       The single normalizer the orchestrator's cluster dedup keys through, so
#       there is ONE precedence ladder and ONE set of identifier normalizers,
#       not two divergent ones.
#
#   document_id_basis(IdentityKey) -> "<key_type>:<key>"
#       The deterministic, run-stable string SPR-01 derives the content-stable
#       document_id from. Same work -> same basis -> same document_id, so a
#       re-ingest is a no-op at BOTH the dedup layer (recognised as seen) and
#       the merge layer (on_conflict=ignore skips the existing id).
# ---------------------------------------------------------------------------


class KeyType(str, enum.Enum):
    """Which identifier established a record's identity, precedence-high first.

    This is the ONE identity-precedence enum. The orchestrator's cross-source
    dedup keys its clusters off these same levels (via :func:`dedup_key`); it
    does NOT carry a second, divergent ladder.
    """

    DOI = "doi"
    ISBN = "isbn"  # always the ISBN-13 form
    ARXIV = "arxiv"
    SOURCE_ID = "source_id"  # source-local id (gutenberg book id / archive id)
    CONTENT = "content"  # hash of normalized extracted body text
    TITLE_AUTHOR = "title_author"  # LOW-confidence fallback


# Precedence, HIGHEST first. The first type for which a record yields a value
# wins — a record with a DOI is identified by its DOI even if it also has a
# body, so two extractions of the same DOI'd paper never split on a content
# hash that differs by a stray ligature. source-id sits above content-hash:
# a Gutenberg work's id is more stable than a hash of a body that may not have
# been extracted at discovery, but below the global identifiers (DOI/ISBN/arXiv)
# because a source-local id is only unique within its source.
_PRECEDENCE: tuple[KeyType, ...] = (
    KeyType.DOI,
    KeyType.ISBN,
    KeyType.ARXIV,
    KeyType.SOURCE_ID,
    KeyType.CONTENT,
    KeyType.TITLE_AUTHOR,
)


class Confidence(str, enum.Enum):
    HIGH = "high"
    LOW = "low"


@dataclass(frozen=True)
class IdentityKey:
    """A work's resolved identity.

    ``key`` is the normalized identifier value; ``key_type`` names which
    identifier established it; ``confidence`` is HIGH for a stable id or a
    real-body content hash, LOW for the title+author fallback. The collapse
    pass refuses to silently merge two records on a LOW key.
    """

    key: str
    key_type: KeyType
    confidence: Confidence


@dataclass(frozen=True)
class IdentityRecord:
    """The connector-agnostic record identity + collapse + reconciliation read.

    Built from any connector's discovery output (the orchestrator maps each
    ArxivPaper / PublicDomainWork / OA Candidate into one). Pure data — no
    behaviour, no connector coupling.

    ``ref_id`` is an opaque caller handle echoed back so a collapse decision is
    traceable to its origin. ``source_id`` is the source-local identifier (a
    Gutenberg book id, an archive.org identifier) — the stable id a public-domain
    work carries when it has no DOI/ISBN/arXiv-id and no body was extracted at
    discovery. ``body`` is the extracted text used ONLY for the content-hash
    fallback and the canonical body-quality comparison; it is never fetched here.
    ``license`` is the per-source :class:`LicenseResolution` already computed by
    ``licenses_core`` (None when the source carried no license signal at
    discovery) — :func:`reconcile_license` reads it, never re-derives it.
    ``source`` names the contributing source for provenance.
    """

    ref_id: str
    source: str
    doi: str | None = None
    isbn: str | None = None  # ISBN-10 or ISBN-13, any hyphenation
    arxiv_id: str | None = None
    source_id: str | None = None  # source-local id (gutenberg/archive)
    title: str | None = None
    author: str | None = None
    body: str | None = None
    license: LicenseResolution | None = None


# ---------------------------------------------------------------------------
# Identifier normalization — where the bugs hide (rigor card #3). Each
# normalizer is deterministic and individually unit-tested with a fixture pair
# asserting the SAME key out of two surface forms.
# ---------------------------------------------------------------------------

# DOI prefixes sources prepend. Stripped before lowercasing so the bare DOI is
# the key. Ordered longest-first so "https://dx.doi.org/" is stripped whole
# rather than leaving a "dx.doi.org/" tail.
_DOI_PREFIXES: tuple[str, ...] = (
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
)


def normalize_doi(doi: str | None) -> str | None:
    """Bare, lowercased DOI, or None when absent.

    A DOI is case-insensitive (the registration is, by spec), so two sources
    emitting ``10.1/AB`` and ``https://doi.org/10.1/ab`` resolve to one key.
    Only the registrant-agnostic URL/scheme prefixes are stripped; the DOI's
    own ``10.<registrant>/<suffix>`` structure is preserved verbatim (lowered).
    """
    if not doi:
        return None
    d = doi.strip()
    low = d.lower()
    for prefix in _DOI_PREFIXES:
        if low.startswith(prefix):
            d = d[len(prefix):]
            break
    d = d.strip().lower()
    return d or None


_ISBN_STRIP_RE = re.compile(r"[\s-]")


def _isbn13_check_digit(twelve: str) -> str:
    """EAN-13 check digit over the first 12 digits (ISBN-13 algorithm)."""
    total = sum(
        (1 if i % 2 == 0 else 3) * int(ch) for i, ch in enumerate(twelve)
    )
    return str((10 - (total % 10)) % 10)


def normalize_isbn(isbn: str | None) -> str | None:
    """ISBN-13 form (13 digits, no hyphens), converting valid ISBN-10s, or
    None when the value is not a structurally valid ISBN.

    ISBN-10 and its ISBN-13 form (978-prefixed, recomputed check digit) name
    the SAME book, so both must produce one key. An ISBN that fails its check
    digit is NOT a usable identity — returning None makes the record fall
    through precedence rather than keying on a corrupt number.
    """
    if not isbn:
        return None
    raw = _ISBN_STRIP_RE.sub("", isbn.strip()).upper()
    if len(raw) == 13 and raw.isdigit():
        if _isbn13_check_digit(raw[:12]) != raw[12]:
            return None
        return raw
    if len(raw) == 10:
        body = raw[:9]
        if not body.isdigit():
            return None
        # Validate the ISBN-10 check (last char may be 'X' == 10).
        check = raw[9]
        if check == "X":
            check_val = 10
        elif check.isdigit():
            check_val = int(check)
        else:
            return None
        total = sum((10 - i) * int(ch) for i, ch in enumerate(body))
        if (total + check_val) % 11 != 0:
            return None
        twelve = "978" + body
        return twelve + _isbn13_check_digit(twelve)
    return None


# Old-style arXiv ids carry an archive/subject class: "math.GT/0309136" or
# "hep-th/9901001"; new-style are "2401.00001". Either may carry a version
# suffix "vN". The canonical form drops the version (a new version is the SAME
# work) and lowercases the archive class (case is not significant in it).
_ARXIV_VERSION_RE = re.compile(r"v\d+$", re.IGNORECASE)
_ARXIV_PREFIXES: tuple[str, ...] = ("arxiv:", "arxiv.org/abs/", "abs/")


def normalize_arxiv_id(arxiv_id: str | None) -> str | None:
    """Canonical arXiv id: scheme/prefix stripped, version suffix dropped,
    lowercased, or None when absent.

    ``2401.00001v2`` and ``2401.00001`` are the same work, so the version is
    dropped. Old-style ``math.GT/0309136`` keeps its archive-class/number
    structure (lowered); only the mutable bits (prefix, version, case) are
    normalized away.
    """
    if not arxiv_id:
        return None
    a = arxiv_id.strip().lower()
    for prefix in _ARXIV_PREFIXES:
        if a.startswith(prefix):
            a = a[len(prefix):]
            break
    a = _ARXIV_VERSION_RE.sub("", a)
    return a.strip() or None


def normalize_source_id(source_id: str | None) -> str | None:
    """Casefolded, stripped source-local id, or None when absent.

    A Gutenberg book id / archive.org identifier is already stable; we only
    fold case and strip surrounding whitespace so two surface forms of the same
    id resolve to one key. It is namespaced by ``KeyType.SOURCE_ID`` in the
    document_id basis, so a source-local id can never collide with a same-string
    DOI/arXiv-id across the global precedence levels.
    """
    if not source_id:
        return None
    s = source_id.strip().casefold()
    return s or None


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _normalize_prose(value: str) -> str:
    """NFKC, casefold, strip punctuation, collapse whitespace.

    Shared by the title+author fallback and the content-hash so two extractions
    of one body — differing only in whitespace, casing, line endings, or a
    smart-quote vs a straight quote — normalize to the same string and hash to
    the same key.
    """
    norm = unicodedata.normalize("NFKC", value)
    norm = norm.casefold()
    norm = _PUNCT_RE.sub(" ", norm)
    return _WS_RE.sub(" ", norm).strip()


# Below this many normalized characters a body is too thin to be a stable
# content fingerprint (a title echoed into the body field, an abstract stub).
# 200 chars ≈ a short paragraph — enough that two genuinely-different works do
# not collide on a coincidental opening sentence, while real article/book
# bodies clear it comfortably.
MIN_CONTENT_HASH_CHARS = 200


def normalize_content_hash(body: str | None) -> str | None:
    """Stable hash of normalized body text, or None when there is too little
    body to fingerprint.

    Whitespace/casing/line-ending/punctuation differences between two
    extractions of the same body are normalized away (:func:`_normalize_prose`)
    BEFORE hashing, so trivial extraction noise does not split one work into
    two. Returns None below :data:`MIN_CONTENT_HASH_CHARS` so a thin stub never
    becomes a confident identity.
    """
    if not body:
        return None
    norm = _normalize_prose(body)
    if len(norm) < MIN_CONTENT_HASH_CHARS:
        return None
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _title_author_key(title: str | None, author: str | None) -> str | None:
    """The LOW-confidence fallback: a hash of normalized title (+author), or
    None when there is no title to key on."""
    nt = _normalize_prose(title or "")
    if not nt:
        return None
    na = _normalize_prose(author or "")
    digest = hashlib.sha256(f"{nt}\x00{na}".encode()).hexdigest()
    return digest[:32]


def dedup_key(record: IdentityRecord, key_type: KeyType) -> str | None:
    """The record's normalized value for one precedence level, or None.

    This is the single per-level normalizer. ``identity_key`` walks the whole
    precedence ladder through it, and the orchestrator's cross-source cluster
    dedup keys its clusters off the SAME function — so there is exactly one
    definition of "what value does this record carry at the DOI / ISBN / arXiv /
    source-id / content / title+author level", never two divergent ones.
    """
    if key_type is KeyType.DOI:
        return normalize_doi(record.doi)
    if key_type is KeyType.ISBN:
        return normalize_isbn(record.isbn)
    if key_type is KeyType.ARXIV:
        return normalize_arxiv_id(record.arxiv_id)
    if key_type is KeyType.SOURCE_ID:
        return normalize_source_id(record.source_id)
    if key_type is KeyType.CONTENT:
        return normalize_content_hash(record.body)
    if key_type is KeyType.TITLE_AUTHOR:
        return _title_author_key(record.title, record.author)
    return None


def identity_key(record: IdentityRecord) -> IdentityKey:
    """Resolve a candidate record to its content-stable identity key.

    Walks precedence high→low (DOI > ISBN-13 > arXiv-id > source-id >
    content-hash > title+author) and returns the FIRST level that yields a
    value. A stable id or a real-body content hash is HIGH confidence; the
    title+author fallback — reached only when a record has neither a stable id
    nor enough body — is LOW confidence so the collapse pass refuses to merge on
    it silently.

    Pure: no I/O, no DB, no network. The returned key is BOTH the dedup
    decision and (via :func:`document_id_basis`) SPR-01's document_id basis.
    """
    for key_type in _PRECEDENCE:
        value = dedup_key(record, key_type)
        if value is None:
            continue
        confidence = (
            Confidence.LOW if key_type is KeyType.TITLE_AUTHOR else Confidence.HIGH
        )
        return IdentityKey(key=value, key_type=key_type, confidence=confidence)
    # No title either — there is nothing stable to key on. The empty-title hash
    # is still deterministic per ref, but it is its OWN identity (it can never
    # match another record), so identity falls back to the ref_id itself,
    # flagged LOW so it never collapses.
    return IdentityKey(
        key=hashlib.sha256(record.ref_id.encode("utf-8")).hexdigest()[:32],
        key_type=KeyType.TITLE_AUTHOR,
        confidence=Confidence.LOW,
    )


def document_id_basis(key: IdentityKey) -> str:
    """The deterministic, run-stable string SPR-01 derives the content-stable
    ``document_id`` from.

    Shape: ``"<key_type>:<key>"``. Namespacing by key_type means a DOI and an
    arXiv-id that happen to share a literal string can never collide, and the
    same work always yields the same basis across runs — so SPR-01's
    ``on_conflict=ignore`` insert makes a re-ingest a no-op at the merge layer
    exactly as the dedup layer recognises it as seen.

    This basis is NOT a side computation: it is the SAME key the orchestrator's
    cross-source dedup keyed the work on (``dedup_candidates`` keys its clusters
    through :func:`dedup_key`), so the identity that decided "this candidate is
    a duplicate, drop it" is the identity that decides "this candidate's
    document_id". Dedup and idempotency are one fact.

    Scope boundary (flagged, not a no-op): SPR-04 produces this basis and the
    orchestrator surfaces it per kept candidate as the contract SPR-01 consumes.
    The merge/insert that turns the basis into the row's ``document_id`` is
    SPR-01's write path (explicitly out of scope here — this sprint inserts no
    rows). On origin/main @ 4623fff SPR-01 is not yet merged, so the connectors
    still mint their own ids at insert; this is the documented seam SPR-01
    closes, not an inert value — the dedup decision already runs on this key.
    """
    return f"{key.key_type.value}:{key.key}"


def identity_basis(record: IdentityRecord) -> str:
    """Convenience: the document_id basis for a record in one call.

    Equivalent to ``document_id_basis(identity_key(record))`` — the single
    string the orchestrator stamps per kept candidate and SPR-01 consumes.
    """
    return document_id_basis(identity_key(record))


# ---------------------------------------------------------------------------
# Cross-source collapse + canonical selection (M3) + license reconciliation
# (M5).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalWork:
    """One real-world work after collapse.

    ``canonical`` is the chosen best record. ``identity`` is the key that
    collapsed the group. ``contributing_sources`` lists every source that
    described this work (canonical first), so an auditor can reconstruct which
    sources contributed (defensibility / SPR-10 rights audit).
    ``reconciled_license`` + ``license_basis`` carry the M5 reconciliation.
    """

    canonical: IdentityRecord
    identity: IdentityKey
    contributing_sources: tuple[str, ...]
    members: tuple[IdentityRecord, ...]
    reconciled_license: LicenseResolution | None = None
    license_basis: str | None = None


def _metadata_completeness(record: IdentityRecord) -> int:
    """How many of {title, author, body} are present + non-trivial. Higher is
    a more complete record — the first axis of canonical selection."""
    score = 0
    if record.title and record.title.strip():
        score += 1
    if record.author and record.author.strip():
        score += 1
    if record.body and record.body.strip():
        score += 1
    return score


def _body_len(record: IdentityRecord) -> int:
    """Length of the extracted body — the second canonical axis ("best body":
    the longest clean extraction). 0 when no body."""
    return len(record.body) if record.body else 0


def _select_canonical(
    members: Sequence[IdentityRecord],
) -> IdentityRecord:
    """Deterministic canonical selection.

    Policy, in order: (1) most-complete metadata; (2) longest body (the best
    extraction); (3) the lexicographically-greatest ``ref_id`` as the final
    tie-break, so the SAME input set always yields the SAME canonical record
    regardless of input order — a collapse decision an auditor can reproduce
    from the stored members alone. ``ref_id`` is unique per record, so the
    three keys form a strict total order and ``max`` is fully determined (no
    reliance on iteration order).
    """
    return max(
        members,
        key=lambda r: (_metadata_completeness(r), _body_len(r), r.ref_id),
    )


# Permissiveness rank for license reconciliation (M5). HIGHER is more
# permissive. The rank is DERIVED from the resolution ``licenses_core`` already
# computed — we do not re-encode CC ordering here. The ONLY thing that can
# raise a work above "gated" is a POSITIVELY-VERIFIED redistributable license;
# an unknown/unverified resolution (redistributable=False) can never win, which
# is the §9.0 deny-by-default invariant expressed as a comparison.


def _permissiveness(resolution: LicenseResolution | None) -> int:
    """A total order over license resolutions, more-permissive = higher.

    0  — no/unknown/unverified resolution: redistributable=False, OR None.
         NEVER wins a reconciliation; cannot raise a work to servable.
    1  — positively-verified redistributable, with a downstream obligation
         (attribution / share-alike): source_declared_open / opt_in_licensed.
    2  — positively-verified redistributable, NO obligation: public_domain
         (CC0 / PDM) — the most permissive.

    Ties (two sources with the same rank) keep the EARLIER source's resolution,
    so reconciliation is deterministic.
    """
    if resolution is None or not resolution.redistributable:
        return 0
    if resolution.content_class == PUBLIC_DOMAIN_CONTENT_CLASS:
        return 2
    if resolution.content_class in SERVABLE_CONTENT_CLASSES:
        return 1
    # redistributable=True but the class is not a known servable class — treat
    # as unverified rather than guessing servable (deny-by-default).
    return 0


def reconcile_license(
    members: Sequence[IdentityRecord],
) -> tuple[LicenseResolution | None, str | None]:
    """Pick the most-permissive POSITIVELY-VERIFIED license across collapsed
    members and compose the audit ``license_basis``.

    The winner is the highest :func:`_permissiveness` member (ties → earliest
    member, for determinism). The basis names the winning license AND the
    source it came from, plus every contributing source's license, so SPR-02 /
    SPR-10's audit ("every servable work has a basis") can see where the
    servability came from and what was overridden.

    The §9.0 catastrophe this guards: an unverified/unknown duplicate can NEVER
    raise a work to servable. If no member is positively verified, the winner is
    rank-0 (gated) and the basis records that the work stays gated — collapse
    never invents servability on the strength of another source merely claiming
    a license.
    """
    if not members:
        return None, None

    winner: IdentityRecord | None = None
    winner_rank = -1
    for record in members:
        rank = _permissiveness(record.license)
        if rank > winner_rank:
            winner_rank = rank
            winner = record

    if winner is None or winner.license is None:
        # No member carried any resolution at all — nothing to reconcile.
        return None, None

    parts: list[str] = []
    if winner_rank > 0:
        parts.append(
            f"{winner.license.license_name} via {winner.source} "
            f"(positively verified; most-permissive across "
            f"{len(members)} source(s))"
        )
    else:
        parts.append(
            f"GATED: no source positively verified a redistribution license "
            f"across {len(members)} source(s) -- {winner.license.rationale}"
        )

    # Record every contributing source's license so the override is auditable.
    contributions: list[str] = []
    for record in members:
        name = record.license.license_name if record.license else "(no license signal)"
        contributions.append(f"{record.source}={name}")
    parts.append("contributing: " + ", ".join(contributions))

    return winner.license, " | ".join(parts)


def collapse(records: Iterable[IdentityRecord]) -> tuple[CanonicalWork, ...]:
    """Collapse candidate records sharing an identity key into one work each.

    Records are grouped by ``(key_type, key)``, with one exception that is the
    whole point of the LOW-confidence flag: a LOW-confidence (title+author /
    ref-id) key NEVER merges two records — each LOW record stays its own work,
    so two distinct "History"/"Anonymous" works do not collapse. HIGH-confidence
    keys (DOI / ISBN / arXiv / content) group normally, so the same DOI across
    arXiv + OpenAlex + PMC collapses to one canonical work.

    For each HIGH group, :func:`_select_canonical` picks the canonical record
    deterministically and :func:`reconcile_license` resolves the license; both
    record-order-independent so the same input set always yields the same
    result. Output order follows first-appearance of each group, so a run's
    report is stable.

    Relationship to ``acquisition.corpus_quality.dedup_candidates``: NOT a second
    identity ladder — both key off this module's single ``dedup_key`` ladder, so
    they always agree on what value a record carries at each level and on the
    LOW-never-merges rule. They are two surfaces with different jobs over that
    one identity: ``dedup_candidates`` is the orchestrator's INTRA-RUN dedup
    driver (transitive cross-source clustering with conflict-veto; first-seen
    canonical; no license work — it decides what gets ingested this run).
    ``collapse`` is the MERGE-TIME surface SPR-01 consumes when staged records
    that share an identity key must pick a best-canonical record and reconcile a
    license across sources (M3 + M5). Same identity, two responsibilities — not
    a duplicated decision.

    Pure: no I/O, no DB. Cost is O(records) — a dict group-by — well within the
    bounded discovery batches the orchestrator feeds it.
    """
    # group_key -> list of members, preserving first-seen order of groups.
    groups: dict[tuple, list[IdentityRecord]] = {}
    order: list[tuple] = []
    key_cache: dict[str, IdentityKey] = {}

    for record in records:
        ikey = identity_key(record)
        key_cache[record.ref_id] = ikey
        if ikey.confidence is Confidence.LOW:
            # A LOW key never merges: give each LOW record a singleton group
            # keyed on its own ref_id so it can never absorb another work.
            group_key: tuple = ("__low__", record.ref_id)
        else:
            group_key = (ikey.key_type.value, ikey.key)
        if group_key not in groups:
            groups[group_key] = []
            order.append(group_key)
        groups[group_key].append(record)

    works: list[CanonicalWork] = []
    for group_key in order:
        members = tuple(groups[group_key])
        canonical = _select_canonical(members)
        ikey = key_cache[canonical.ref_id]
        # Canonical-first source list, then the remaining members in order.
        sources = [canonical.source] + [
            m.source for m in members if m.ref_id != canonical.ref_id
        ]
        resolution, basis = reconcile_license(members)
        works.append(
            CanonicalWork(
                canonical=canonical,
                identity=ikey,
                contributing_sources=tuple(sources),
                members=members,
                reconciled_license=resolution,
                license_basis=basis,
            )
        )
    return tuple(works)


@dataclass(frozen=True)
class CollapseReport:
    """Run-level collapse summary for the orchestrator's report.

    Surfaces the kept count, the dropped (collapsed-away) count, and the
    per-key-type distribution — including how many works resolved only on the
    LOW-confidence fallback, the coverage gap the honesty rigor card demands a
    run report rather than hide.
    """

    kept: int
    collapsed_away: int
    key_type_counts: dict[str, int]
    low_confidence: int

    def render(self) -> str:
        dist = ", ".join(
            f"{kt}={n}" for kt, n in sorted(self.key_type_counts.items())
        )
        return (
            f"dedup: {self.kept} works kept, {self.collapsed_away} duplicates "
            f"collapsed; key types: {dist or '(none)'}; "
            f"low-confidence fallback: {self.low_confidence}"
        )


def summarize(works: Sequence[CanonicalWork], *, total_records: int) -> CollapseReport:
    """Build the run-level collapse report from collapsed works.

    ``total_records`` is the count BEFORE collapse, so ``collapsed_away`` is
    the number of duplicates the identity layer removed.
    """
    counts: dict[str, int] = {}
    low = 0
    for work in works:
        kt = work.identity.key_type.value
        counts[kt] = counts.get(kt, 0) + 1
        if work.identity.confidence is Confidence.LOW:
            low += 1
    return CollapseReport(
        kept=len(works),
        collapsed_away=max(0, total_records - len(works)),
        key_type_counts=counts,
        low_confidence=low,
    )
