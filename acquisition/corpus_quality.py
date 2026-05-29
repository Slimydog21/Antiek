"""Corpus-quality gate + cross-source dedup for the AKB ingest (SPR-08).

Two pure, deterministic, dependency-light layers that sit BETWEEN discovery
(the three rights-correct connectors) and the substrate ingest path:

- **M1 — corpus-quality gate** (`assess_corpus_quality`): decides whether a
  candidate document's extracted text + metadata is good enough to ingest.
  Three inspectable checks — real-word ratio, OCR-garbage rejection, and
  metadata completeness — each returning the substrate-shaped `CheckResult`
  (mirrors `substrate.quality_gate.gate.CheckResult`: name/kind/score/reasons)
  so the return shape is not a parallel invention. Aggregation
  (`aggregate_verdicts`) computes a run's rejection RATE so a run reports how
  many candidates it dropped and why (honesty rigor card) instead of hiding a
  high reject rate behind a green checkmark.

- **M2 — cross-source dedup** (`dedup_candidates`): collapses duplicate works
  discovered across the arXiv / public-domain / open-access connectors. Pure
  function over a normalized `CandidateRef` (NOT the heavyweight connector
  types) so the dedup logic does not depend on all three. Precedence, highest
  first: DOI > arXiv id > source id > (normalized title+author) hash. The
  `DedupResult` records which key caused each drop so a run can show its dedup
  decisions (defensibility).

No new heavy dependency: the heuristics use only the stdlib (`re`,
`unicodedata`). The §16 REJECT list forbids new heavy NLP/dictionary deps, so
the real-word heuristic is a deliberately simple shape check, not a lexicon
lookup — documented inline.

Every threshold is a NAMED module constant with a comment stating WHY that
number, so no magic number is unjustified (rigor card).
"""

from __future__ import annotations

import enum
import hashlib
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Shared verdict shape — MIRRORS substrate.quality_gate.gate.CheckResult.
# We do not import that type directly: its CheckResult is keyed to a
# CandidateNote (claims/evidence/tiers), a different domain. We reuse the
# SHAPE (name / kind / score / reasons) so the two gates read alike, without
# coupling the corpus gate to the public-notes gate's data model.
# ---------------------------------------------------------------------------


class CheckResultKind(str, enum.Enum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class CheckResult:
    """The verdict of one corpus-quality check.

    Same fields/semantics as ``substrate.quality_gate.gate.CheckResult``:
    a human-named check, a pass/fail kind, a ``score`` in [0, 1] (PASS does
    not require score == 1), and human-readable ``reasons``.
    """

    check_name: str
    kind: CheckResultKind
    score: float  # in [0, 1]
    reasons: tuple[str, ...]


# ---------------------------------------------------------------------------
# M1 thresholds — each a named constant with a WHY comment (rigor: no
# unjustified magic numbers).
# ---------------------------------------------------------------------------

# A token counts as a "real word" only when its length is within these bounds.
# Below MIN: page-number fragments, stray single letters, OCR speckle ("l",
# "rn"). Above MAX: no English/Latin word reaches 30 characters; a longer run
# of letters is almost always two words fused by lost whitespace or an OCR
# smear. 2..30 keeps legitimate long words (e.g. "internationalisation", 20)
# while rejecting the pathological tails.
MIN_WORD_LEN = 2
MAX_WORD_LEN = 30

# Fraction of whitespace-tokens that must look like real words for the text to
# pass the real-word check. Clean prose sits well above 0.90; scanned-PDF OCR
# garble and binary-noise husks fall far below. 0.60 is a deliberately
# forgiving floor: it admits text with numbers, punctuation tokens, and the
# occasional OCR slip, while still biting on text that is MOSTLY non-words.
MIN_REAL_WORD_RATIO = 0.60

# Below this many whitespace-tokens we cannot compute a stable ratio, so we
# reject for insufficient text rather than pass a husk on a lucky 1/1 ratio.
# 20 tokens ≈ one sentence — the minimum to judge "is this prose".
MIN_TOKEN_COUNT = 20

# OCR-garbage check: the fraction of all characters that are letters. Real
# prose is overwhelmingly alphabetic (+ spaces/punctuation); binary noise and
# heavy OCR garble are dominated by symbols/digits/control bytes. Below 0.50
# the text is more non-letter than letter — not prose.
MIN_ALPHA_CHAR_RATIO = 0.50

# OCR-garbage check: max share of tokens that are a single character. A page
# of " l l l rn cl " speckle blows past this; normal prose has very few
# single-char tokens ("a", "I"). 0.25 allows a quarter (generous for
# initialisms/list markers) before flagging speckle.
MAX_SINGLE_CHAR_TOKEN_RATIO = 0.25

# OCR-garbage check: average token length must fall in a sane prose band.
# Real running text averages ~4-6 chars/token. An average below MIN means
# speckle (many 1-char tokens); above MAX means whitespace was lost and tokens
# are fused smears. 2.0..18.0 is a wide, defensible band around natural prose.
MIN_AVG_TOKEN_LEN = 2.0
MAX_AVG_TOKEN_LEN = 18.0


# Vowel set used by the real-word heuristic. A genuine word almost always
# carries a vowel (incl. 'y'); long vowel-free letter runs ("zxcvbnm",
# "ttttt") are OCR/keyboard noise, not words.
_VOWELS = frozenset("aeiouyAEIOUY")

# A "word-shaped" token: purely alphabetic (incl. unicode letters), nothing
# else. Punctuation/digit-bearing tokens are not counted as real words but are
# not penalised either (numbers and citations are legitimate in prose).
_ALPHA_TOKEN_RE = re.compile(r"^[^\W\d_]+$", re.UNICODE)


def _is_real_word(token: str) -> bool:
    """Heuristic: does this whitespace-token look like a real word?

    DELIBERATELY simple (no dictionary — §16 forbids a heavy lexicon dep):
    a token is "real" when it is purely alphabetic, its length is in
    [MIN_WORD_LEN, MAX_WORD_LEN], AND it contains at least one vowel. The
    vowel rule is what separates "the"/"quality" from OCR runs like "rn"
    or "tttt". This catches OCR garble and binary noise without claiming to
    validate spelling.
    """
    if not (MIN_WORD_LEN <= len(token) <= MAX_WORD_LEN):
        return False
    if not _ALPHA_TOKEN_RE.match(token):
        return False
    return any(ch in _VOWELS for ch in token)


def _real_word_ratio(tokens: Sequence[str]) -> float:
    if not tokens:
        return 0.0
    real = sum(1 for t in tokens if _is_real_word(t))
    return real / len(tokens)


def check_real_word_ratio(text: str) -> CheckResult:
    """Fraction of whitespace-tokens that look like real words.

    FAILs when there is too little text to judge, or when the real-word
    ratio is below ``MIN_REAL_WORD_RATIO`` (OCR garble / binary noise).
    """
    tokens = text.split()
    if len(tokens) < MIN_TOKEN_COUNT:
        return CheckResult(
            check_name="real_word_ratio",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=(
                f"only {len(tokens)} token(s); need ≥ {MIN_TOKEN_COUNT} to "
                "judge real-word ratio",
            ),
        )
    ratio = _real_word_ratio(tokens)
    if ratio >= MIN_REAL_WORD_RATIO:
        return CheckResult(
            check_name="real_word_ratio",
            kind=CheckResultKind.PASS,
            score=ratio,
            reasons=(
                f"real-word ratio {ratio:.2f} ≥ {MIN_REAL_WORD_RATIO:.2f}",
            ),
        )
    return CheckResult(
        check_name="real_word_ratio",
        kind=CheckResultKind.FAIL,
        score=ratio,
        reasons=(
            f"real-word ratio {ratio:.2f} below {MIN_REAL_WORD_RATIO:.2f} — "
            "looks like OCR garble or binary noise",
        ),
    )


def check_ocr_garbage(text: str) -> CheckResult:
    """Reject text dominated by non-alphabetic noise, single-char runs, or an
    absurd average token length.

    Three independent sub-signals (alpha-char ratio, single-char-token share,
    average token length); FAIL if ANY trips. Each sub-signal's threshold is a
    named constant above.
    """
    tokens = text.split()
    if len(tokens) < MIN_TOKEN_COUNT:
        return CheckResult(
            check_name="ocr_garbage",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=(
                f"only {len(tokens)} token(s); need ≥ {MIN_TOKEN_COUNT} to "
                "judge OCR quality",
            ),
        )

    letters = sum(1 for ch in text if ch.isalpha())
    non_space = sum(1 for ch in text if not ch.isspace())
    alpha_ratio = (letters / non_space) if non_space else 0.0

    single_char = sum(1 for t in tokens if len(t) == 1)
    single_char_ratio = single_char / len(tokens)

    avg_token_len = sum(len(t) for t in tokens) / len(tokens)

    failures: list[str] = []
    if alpha_ratio < MIN_ALPHA_CHAR_RATIO:
        failures.append(
            f"alphabetic-char ratio {alpha_ratio:.2f} below "
            f"{MIN_ALPHA_CHAR_RATIO:.2f} (non-letter noise)"
        )
    if single_char_ratio > MAX_SINGLE_CHAR_TOKEN_RATIO:
        failures.append(
            f"single-char-token share {single_char_ratio:.2f} above "
            f"{MAX_SINGLE_CHAR_TOKEN_RATIO:.2f} (speckle)"
        )
    if not (MIN_AVG_TOKEN_LEN <= avg_token_len <= MAX_AVG_TOKEN_LEN):
        failures.append(
            f"average token length {avg_token_len:.1f} outside sane band "
            f"[{MIN_AVG_TOKEN_LEN:.1f}, {MAX_AVG_TOKEN_LEN:.1f}]"
        )

    # score = the alpha-char ratio, a single intuitive [0,1] quality proxy.
    if failures:
        return CheckResult(
            check_name="ocr_garbage",
            kind=CheckResultKind.FAIL,
            score=alpha_ratio,
            reasons=tuple(failures),
        )
    return CheckResult(
        check_name="ocr_garbage",
        kind=CheckResultKind.PASS,
        score=alpha_ratio,
        reasons=(
            f"alpha-ratio {alpha_ratio:.2f}, single-char share "
            f"{single_char_ratio:.2f}, avg-token-len {avg_token_len:.1f} — "
            "all within prose bands",
        ),
    )


def check_metadata_completeness(
    *,
    title: Optional[str],
    author: Optional[str],
    source_id: Optional[str],
    allow_null_author_reason: Optional[str] = None,
) -> CheckResult:
    """Title present + non-empty, author present (or an explicit allowed-null
    reason), and a source identifier present.

    ``allow_null_author_reason`` is the explicit escape hatch for genuinely
    anonymous works (e.g. a public-domain text with no recorded author): a
    null author is only OK when the caller states WHY in writing, so the
    null is an auditable decision rather than a silent gap.
    """
    failures: list[str] = []

    if not (title and title.strip()):
        failures.append("title missing or empty")

    if not (author and author.strip()):
        if allow_null_author_reason and allow_null_author_reason.strip():
            # Explicitly allowed null — recorded, not a failure.
            pass
        else:
            failures.append(
                "author missing and no allow_null_author_reason given"
            )

    if not (source_id and source_id.strip()):
        failures.append("source identifier missing or empty")

    if failures:
        return CheckResult(
            check_name="metadata_completeness",
            kind=CheckResultKind.FAIL,
            score=0.0,
            reasons=tuple(failures),
        )
    note = "title + source id present"
    if not (author and author.strip()):
        note += f"; author null (allowed: {allow_null_author_reason})"
    else:
        note += " + author"
    return CheckResult(
        check_name="metadata_completeness",
        kind=CheckResultKind.PASS,
        score=1.0,
        reasons=(note,),
    )


@dataclass(frozen=True)
class QualityVerdict:
    """Structured corpus-quality verdict for one candidate.

    ``passed`` is the AND of every check. ``checks`` carries each
    inspectable per-check result; ``rejection_reason`` is a human-readable
    summary populated only when ``passed`` is False. ``body_assessed`` is
    False when the gate ran metadata-only because no pre-ingest body text was
    available (see ``assess_corpus_quality(assess_body=...)``) — so a passing
    metadata-only verdict is never mistaken for a full-text pass.
    """

    passed: bool
    checks: tuple[CheckResult, ...]
    body_assessed: bool = True
    rejection_reason: Optional[str] = None

    @property
    def failed_checks(self) -> tuple[CheckResult, ...]:
        return tuple(c for c in self.checks if c.kind == CheckResultKind.FAIL)


def assess_corpus_quality(
    text: str,
    *,
    title: Optional[str],
    author: Optional[str],
    source_id: Optional[str],
    allow_null_author_reason: Optional[str] = None,
    assess_body: bool = True,
) -> QualityVerdict:
    """Run the corpus-quality checks and compose a single verdict.

    The candidate passes only when EVERY run check passes (the gate bites —
    see the fairness rigor card: a garbled body or a missing title is a hard
    reject, it is not merely advisory). The per-check results stay attached so
    a run can report exactly why a candidate was dropped.

    ``assess_body`` controls the two text checks (real-word ratio +
    OCR-garbage). It MUST be False when no pre-ingest body text is available
    for the candidate — e.g. an open-access item whose only discovery-time
    text is its title, where the real body lives in a publisher PDF fetched
    only at ingest. Running the text checks on a title would spuriously reject
    a born-digital source for "too little text"; that is a false negative, not
    a quality signal. With ``assess_body=False`` only metadata-completeness
    runs and the verdict records ``body_assessed=False`` so the metadata-only
    pass is honestly distinguishable from a full-text pass — the run report
    surfaces it rather than hiding a body that was never inspected.
    """
    checks: tuple[CheckResult, ...]
    if assess_body:
        checks = (
            check_real_word_ratio(text),
            check_ocr_garbage(text),
            check_metadata_completeness(
                title=title,
                author=author,
                source_id=source_id,
                allow_null_author_reason=allow_null_author_reason,
            ),
        )
    else:
        checks = (
            check_metadata_completeness(
                title=title,
                author=author,
                source_id=source_id,
                allow_null_author_reason=allow_null_author_reason,
            ),
        )
    failed = tuple(c for c in checks if c.kind == CheckResultKind.FAIL)
    if not failed:
        return QualityVerdict(
            passed=True, checks=checks, body_assessed=assess_body,
            rejection_reason=None,
        )
    reason = "; ".join(
        f"{c.check_name}: {' / '.join(c.reasons)}" for c in failed
    )
    return QualityVerdict(
        passed=False, checks=checks, body_assessed=assess_body,
        rejection_reason=reason,
    )


@dataclass(frozen=True)
class QualityRunReport:
    """Aggregate over many ``QualityVerdict``s for one run.

    Surfaces the rejection RATE and a per-reason tally so a run reports how
    many candidates the gate dropped and why — the gate's reject rate is
    never hidden behind a green checkmark (honesty rigor card).
    """

    total: int
    passed: int
    rejected: int
    rejection_rate: float  # rejected / total, 0.0 when total == 0
    rejection_reasons: tuple[str, ...]  # one entry per rejected candidate

    def render(self) -> str:
        pct = self.rejection_rate * 100.0
        lines = [
            f"quality gate: {self.total} assessed, {self.passed} passed, "
            f"{self.rejected} rejected ({pct:.1f}% rejection rate)",
        ]
        for i, reason in enumerate(self.rejection_reasons, 1):
            lines.append(f"  reject #{i}: {reason}")
        return "\n".join(lines)


def aggregate_verdicts(verdicts: Iterable[QualityVerdict]) -> QualityRunReport:
    """Aggregate verdicts into a run-level report carrying the rejection rate.

    A run that calls the gate over its candidates and reports this object
    cannot hide a high reject rate: the rate + every rejection reason are
    first-class fields.
    """
    verdict_list = list(verdicts)
    total = len(verdict_list)
    passed = sum(1 for v in verdict_list if v.passed)
    rejected = total - passed
    rate = (rejected / total) if total else 0.0
    reasons = tuple(
        v.rejection_reason or "unspecified"
        for v in verdict_list
        if not v.passed
    )
    return QualityRunReport(
        total=total,
        passed=passed,
        rejected=rejected,
        rejection_rate=rate,
        rejection_reasons=reasons,
    )


# ---------------------------------------------------------------------------
# M2 — cross-source dedup.
# ---------------------------------------------------------------------------


class DedupKeyKind(str, enum.Enum):
    """Which identifier collapsed two candidates, highest precedence first."""

    DOI = "doi"
    ARXIV_ID = "arxiv_id"
    SOURCE_ID = "source_id"
    TITLE_AUTHOR = "title_author"


# Precedence order, HIGHEST first. Two candidates are "the same work" only if
# they share the highest-precedence identifier BOTH possess — so a candidate
# with a DOI never collides with a DOI-less candidate on a lower key.
_DEDUP_PRECEDENCE: tuple[DedupKeyKind, ...] = (
    DedupKeyKind.DOI,
    DedupKeyKind.ARXIV_ID,
    DedupKeyKind.SOURCE_ID,
    DedupKeyKind.TITLE_AUTHOR,
)


@dataclass(frozen=True)
class CandidateRef:
    """Normalized, connector-agnostic reference used for dedup.

    The orchestration maps each connector record (ArxivPaper /
    PublicDomainWork / OAIngestResult) into one of these. Dedup is a pure
    function over this ref, so it does not depend on the three heavyweight
    connector types. ``ref_id`` is an opaque caller handle echoed back in the
    result (e.g. the connector record's own id) so a drop can be traced to
    its origin.
    """

    ref_id: str
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    source_id: Optional[str] = None  # gutenberg/archive identifier
    title: Optional[str] = None
    author: Optional[str] = None


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def _normalize_text(value: Optional[str]) -> str:
    """Normalization-stable text key: NFKC, casefold, strip punctuation,
    collapse whitespace. Used for the title+author fallback so trivial
    formatting differences across sources do not defeat dedup."""
    if not value:
        return ""
    norm = unicodedata.normalize("NFKC", value)
    norm = norm.casefold()
    norm = _PUNCT_RE.sub(" ", norm)
    return _WS_RE.sub(" ", norm).strip()


def _title_author_hash(title: Optional[str], author: Optional[str]) -> Optional[str]:
    nt = _normalize_text(title)
    na = _normalize_text(author)
    if not nt:
        # No title → no stable fallback key; cannot dedup on title+author.
        return None
    digest = hashlib.sha256(f"{nt}\x00{na}".encode()).hexdigest()
    return digest[:16]


def _dedup_key(ref: CandidateRef, kind: DedupKeyKind) -> Optional[str]:
    """The candidate's value for one precedence level, or None when absent."""
    if kind is DedupKeyKind.DOI:
        d = (ref.doi or "").strip().casefold()
        return d or None
    if kind is DedupKeyKind.ARXIV_ID:
        a = (ref.arxiv_id or "").strip().casefold()
        return a or None
    if kind is DedupKeyKind.SOURCE_ID:
        s = (ref.source_id or "").strip().casefold()
        return s or None
    if kind is DedupKeyKind.TITLE_AUTHOR:
        return _title_author_hash(ref.title, ref.author)
    return None


@dataclass(frozen=True)
class DedupDrop:
    """One dropped duplicate + the canonical it collapsed into + why."""

    dropped_ref_id: str
    kept_ref_id: str
    key_kind: DedupKeyKind
    key_value: str


@dataclass(frozen=True)
class DedupResult:
    """The deduped corpus plan: the kept canonical set, the dropped
    duplicates, and which key caused each drop (defensibility — a run can
    show its dedup decisions)."""

    kept: tuple[CandidateRef, ...]
    dropped: tuple[DedupDrop, ...]
    drops_by_key: Mapping[DedupKeyKind, int] = field(default_factory=dict)

    def render(self) -> str:
        lines = [
            f"dedup: {len(self.kept)} kept, {len(self.dropped)} dropped",
        ]
        for drop in self.dropped:
            lines.append(
                f"  drop {drop.dropped_ref_id} → {drop.kept_ref_id} "
                f"(on {drop.key_kind.value}={drop.key_value})"
            )
        return "\n".join(lines)


def _shared_decision(
    a: CandidateRef, b: CandidateRef
) -> Optional[tuple[DedupKeyKind, str]]:
    """Decide whether two candidates are the SAME work, on the highest-
    precedence key BOTH possess.

    Walk precedence high→low. The first kind where BOTH carry a value is the
    decisive one — and ONLY that one:

    - equal values   → same work; return ``(kind, value)``.
    - unequal values → different works; return ``None``. We do NOT fall
      through to a lower key: two items with different DOIs are different
      works even if their titles coincide, so a lower-key title match must
      not resurrect them as duplicates.

    A kind only one side carries is not *shared*, so it is skipped — which is
    exactly what lets a cross-source pair collapse on title+author when one
    side has a DOI and the other an arXiv id (neither shares the other's
    high key, so title+author is the highest key both possess). When no key
    is shared at all, the pair is not dedupable → ``None``.
    """
    for kind in _DEDUP_PRECEDENCE:
        va = _dedup_key(a, kind)
        vb = _dedup_key(b, kind)
        if va is None or vb is None:
            continue  # not shared at this level — look lower
        return (kind, va) if va == vb else None  # highest shared key decides
    return None  # no shared key → cannot dedup


def dedup_candidates(candidates: Iterable[CandidateRef]) -> DedupResult:
    """Collapse duplicate candidate works across the three connectors.

    Walks candidates in input order; the FIRST candidate seen for a given
    work is the canonical one kept. A later candidate is dropped iff it is the
    same work as an already-kept candidate under ``_shared_decision`` — i.e.
    they agree on the highest-precedence key BOTH possess. Precedence:
    DOI > arXiv id > source id > (normalized title+author) hash.

    Decision rests on the highest key the two SHARE, not on either's own
    highest key — so the central cross-source case collapses correctly: the
    same paper discovered on arXiv (arxiv_id, no DOI) and via an OA aggregator
    (DOI, no arxiv_id) shares neither high key, falls through to the title+
    author hash they DO share, and dedups. Conversely two items with
    different DOIs never merge on a coincidental shared title. The check is
    pairwise (O(kept) per candidate) so it is order-insensitive in outcome;
    corpus-discovery batches are bounded (curated/limit-capped), so the
    quadratic worst case is not a concern at this layer.
    """
    kept: list[CandidateRef] = []
    dropped: list[DedupDrop] = []
    drops_by_key: dict[DedupKeyKind, int] = {}

    for cand in candidates:
        match: Optional[tuple[str, DedupKeyKind, str]] = None
        for canonical in kept:
            decision = _shared_decision(cand, canonical)
            if decision is not None:
                kind, value = decision
                match = (canonical.ref_id, kind, value)
                break  # first (earliest-kept) canonical wins

        if match is not None:
            kept_id, kind, value = match
            dropped.append(
                DedupDrop(
                    dropped_ref_id=cand.ref_id,
                    kept_ref_id=kept_id,
                    key_kind=kind,
                    key_value=value,
                )
            )
            drops_by_key[kind] = drops_by_key.get(kind, 0) + 1
            continue

        kept.append(cand)

    return DedupResult(
        kept=tuple(kept),
        dropped=tuple(dropped),
        drops_by_key=dict(drops_by_key),
    )
