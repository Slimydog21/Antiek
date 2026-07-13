r"""Book acquisition provenance-chain verifier — is the end-to-end chain complete
and tamper-evident? (book-purchase-transport spec, invariant #7.)

Operator vision (ask #5): *"I want to read books, and I am okay with buying a digital
book if there is no pdf online so build the marketplace functionality and also the
seamless port so that book gets hosted in my account on Antiek."* The book-purchase-
transport decision spec lists seven falsifiable invariants. Invariant #7 is the
integrity keystone: *"The acquired book's provenance chain (source -> authorization ->
ingest -> sanitize -> host) is complete and tamper-evident end-to-end."* This module
is that invariant as code — the decision-independent atom that verifies a single book's
acquisition chain, regardless of which transport channel (1A operator-external checkout,
1B store-API, 1C PCI) produced it. It answers: given the recorded receipts for one
book's five acquisition stages, is the chain *complete*, *ordered*, *linked*, and
*untampered* — i.e. **intact**?

**Genuinely distinct from the sibling integrity surface (load-bearing):**

* ``substrate/rights_audit``: a SERVE-TIME cross-check (does a servable work carry a
  license basis? does the public serve path leak a gated body?). It cross-checks the
  stored content_class against served BYTES at read time. THIS is CHAIN-LEVEL integrity
  of the acquisition RECEIPTS themselves — did the five stages happen, in order, with
  unbroken hash-links and unaltered evidence? A book can pass the rights audit (it is
  licensed + not leaking) yet have a broken provenance chain (a stage receipt was
  altered after the fact), and vice versa. Different layer, different question.
* ``substrate/ingest_checkpoint``: RESUME STATE (a sidecar JSON of cursors + seen-id
  sets so a killed continuous ingest restarts without re-ingesting). THIS is the
  integrity of the per-book RECEIPT CHAIN — not where the ingest loop resumed.
* ``substrate/ingest_budget``: a RESOURCE CEILING governor (disk / DB / RSS headroom ->
  OK / PACE / HALT). THIS is cryptographic integrity, not box-safety pacing.
* ``substrate/book_acquisition_budget`` (#2033, off main): a pre-purchase AFFORDABILITY
  gate (can the operator's content budget absorb this batch?). THIS is post-acquisition
  INTEGRITY — was the chain that delivered the book tampered with?
* A single authorization receipt (#733 shape, HMAC-SHA256 for ONE acquisition): THAT is
  one receipt. THIS verifies the CHAIN of receipts across all five stages — that each
  links to the prior and none was altered. Single receipt vs end-to-end chain-of-receipts.

**The verification (hard to vary).**

An acquisition chain is a linear sequence of stage receipts, one per canonical stage, in
canonical order::

    source_resolution -> authorization -> ingest -> sanitize -> host

Each ``ChainStage`` carries: the ``document_id`` (the book), its ``stage`` name, the
``actor`` that performed it, a ``payload`` (stage-specific evidence: source URL /
authorization receipt id / dedup basis / sanitizer build / host path), an ISO-8601
``timestamp``, a ``parent_hash`` (the prior stage's receipt; ``None`` only for the
genesis ``source_resolution`` stage), and a ``claimed_hash`` — the HMAC-SHA256 receipt
recorded for THIS stage, computed over a canonical message of its own fields.

The verifier checks four independent properties and folds them into one end-to-end
verdict:

1. **complete** — every one of the five canonical stages is present.
2. **ordered** — the present stages occur in strictly-increasing canonical rank with no
   duplicate (catches both out-of-order and repeated stages).
3. **chained** — each stage's ``parent_hash`` equals the immediately-prior stage's
   ``claimed_hash`` (a positional hash-chain link), and the head stage is a proper
   genesis (``source_resolution`` with ``parent_hash`` None). A broken link is recorded
   with what was expected vs what was found.
4. **tamper_evident** — for every stage, recomputing the HMAC-SHA256 over the stage's
   canonical message reproduces the recorded ``claimed_hash``. If any field of any stage
   was altered after stamping, the recomputed digest will not match.

**intact** is the fold: definitively ``False`` if ANY structural property (complete /
ordered / chained / single-document) fails; ``None`` (unknown) if all structural
properties hold but the signing key was not supplied so tamper-evidence could not be
checked; ``True`` only when every property holds and every receipt recomputes clean.

**Key properties (load-bearing):**

* Unknowns surface as ``None``, never fabricated. ``tamper_evident`` is ``None`` (not
  ``False``) when the signing key is unknown — the verifier cannot distinguish an
  untampered chain it cannot check from a tampered one. ``intact`` inherits that
  ``None``: a structurally-perfect chain with an unverified signature is *unknown
  intact*, not *confirmed intact*. These are distinct honest states that never collapse.
* The structural checks (complete / ordered / chained / single-document) need NO key —
  they are pure comparisons of recorded values. Only tamper-evidence (the HMAC recompute)
  needs the key. So a caller can always confirm a chain is structurally sound even
  without the signing key; only the cryptographic confirmation is key-gated.
* The verifier PROVES, it does not assert. ``authority = "advisory"`` — it never
  re-stamps, never reorders, never dispatches. It reports the verdict; the transport /
  serve layer acts on it. Every broken link and every tampered stage is named with the
  expected-vs-actual evidence so the failure is actionable and re-running on the same
  chain reproduces the verdict (defensibility — the claim is checkable, not trusted).
* The canonical message uses a unit-separator (``\x1f``) between fields so a field value
  cannot be confused with a field boundary; the message is encoded UTF-8 and digested
  with HMAC-SHA256 over the operator's acquisition signing key.
"""

from __future__ import annotations

import hashlib
import hmac
from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "STAGES",
    "ChainStage",
    "BrokenLink",
    "ProvenanceChainReport",
    "ProvenanceChainError",
    "compute_stage_hash",
    "verify_provenance_chain",
]

# The five canonical acquisition stages, in the one valid order. Each stage's
# receipt is a link in the chain; missing or reordered stages break completeness
# or ordering respectively.
STAGES: tuple[str, ...] = (
    "source_resolution",
    "authorization",
    "ingest",
    "sanitize",
    "host",
)

# Canonical rank per stage (position in STAGES). Used for the strict-increase
# ordering check. Built once; looked up by name.
_STAGE_RANK: dict[str, int] = {name: index for index, name in enumerate(STAGES)}

# Stable reason tokens for broken chain links — one home so callers/tests can key
# off them without drift.
REASON_GENESIS_PARENTED = "genesis_must_be_unparented"
REASON_NON_GENESIS_AT_HEAD = "non_genesis_at_head"
REASON_PARENT_MISMATCH = "parent_hash_mismatch"

# Unit-separator field boundary inside the canonical HMAC message. Chosen because
# it is not a character that appears in normal evidence strings, so a field value
# cannot masquerade as a field boundary (the message is unambiguous to recompute).
_FIELD_SEP = "\x1f"


@dataclass(frozen=True)
class ChainStage:
    """One receipt in an acquisition chain — the record stamped at one stage.

    ``parent_hash`` is the prior stage's ``claimed_hash`` (the hash-chain link);
    it is ``None`` ONLY for the genesis ``source_resolution`` stage. ``claimed_hash``
    is the HMAC-SHA256 receipt recorded for THIS stage over its canonical message.
    """

    document_id: str
    stage: str
    actor: str
    parent_hash: str | None
    payload: str
    timestamp: str
    claimed_hash: str


@dataclass(frozen=True)
class BrokenLink:
    """One position in the chain where the hash-link is broken — named with the
    expected vs actual evidence so the failure is actionable and reproducible."""

    stage: str
    document_id: str
    reason: str
    expected: str
    actual: str


@dataclass(frozen=True)
class ProvenanceChainReport:
    """The reproducible integrity verdict over one book's acquisition chain.

    ``intact`` is the end-to-end fold (see module docstring): ``False`` if any
    structural property fails; ``None`` if structural holds but tamper-evidence is
    unverified (key unknown); ``True`` only when everything holds and every receipt
    recomputes clean.
    """

    document_id: str
    complete: bool
    ordered: bool
    chained: bool
    single_document: bool
    tamper_evident: bool | None
    intact: bool | None
    present_stages: tuple[str, ...]
    missing_stages: tuple[str, ...]
    broken_links: tuple[BrokenLink, ...]
    tampered_stages: tuple[str, ...]
    notes: tuple[str, ...] = ()
    authority: str = "advisory"


class ProvenanceChainError(ValueError):
    """Raised when a chain stage is malformed (unknown stage name or an empty
    required field) — a programming error in the input, distinct from an integrity
    finding reported in :class:`ProvenanceChainReport`."""


def _canonical_message(stage: ChainStage) -> str:
    """The deterministic message a stage's receipt is digested over. Fields are
    joined with a unit separator so boundaries are unambiguous; the genesis stage's
    absent parent hashes as the empty string."""
    return _FIELD_SEP.join(
        (
            stage.document_id,
            stage.stage,
            stage.actor,
            stage.parent_hash if stage.parent_hash is not None else "",
            stage.payload,
            stage.timestamp,
        )
    )


def compute_stage_hash(stage: ChainStage, key: bytes) -> str:
    """Recompute the HMAC-SHA256 receipt for one stage over its canonical message.

    Deterministic: identical stage fields + identical key produce the identical hex
    digest. The verifier calls this to detect tampering (a stage whose recorded
    ``claimed_hash`` no longer matches the recomputed digest was altered); a builder
    calls it to stamp a valid receipt when constructing a chain. One canonical
    message format lives in one place so the two sides can never drift.
    """
    return hmac.new(
        key, _canonical_message(stage).encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _validate_stage(stage: ChainStage) -> None:
    """Reject malformed stages before integrity is assessed. An unknown stage name
    or an empty required field is a programming error (raises), not an integrity
    finding (reported). The genesis stage's ``parent_hash`` is allowed to be None;
    every other stage must name its parent (format is checked by the chain logic)."""
    if not stage.document_id:
        raise ProvenanceChainError("ChainStage.document_id must be non-empty")
    if stage.stage not in _STAGE_RANK:
        raise ProvenanceChainError(
            f"ChainStage.stage {stage.stage!r} is not a canonical stage "
            f"(expected one of {STAGES})"
        )
    if not stage.actor:
        raise ProvenanceChainError("ChainStage.actor must be non-empty")
    if not stage.payload:
        raise ProvenanceChainError("ChainStage.payload must be non-empty")
    if not stage.timestamp:
        raise ProvenanceChainError("ChainStage.timestamp must be non-empty")
    if not stage.claimed_hash:
        raise ProvenanceChainError("ChainStage.claimed_hash must be non-empty")


def verify_provenance_chain(
    stages: Sequence[ChainStage],
    *,
    key: bytes | None = None,
) -> ProvenanceChainReport:
    """Verify one book's acquisition provenance chain (spec invariant #7).

    Assesses four independent structural + cryptographic properties and folds them
    into the end-to-end ``intact`` verdict. See the module docstring for the full
    semantics. The structural checks (complete / ordered / chained /
    single-document) are pure comparisons of recorded values and need no key;
    ``tamper_evident`` (the HMAC recompute) is ``None`` when ``key`` is ``None``.

    A malformed stage (unknown name or empty required field) raises
    :class:`ProvenanceChainError` — that is malformed input, not an integrity
    finding. An empty chain is a valid (if failed) chain: ``complete`` False,
    ``intact`` False, all five stages missing.
    """
    for stage in stages:
        _validate_stage(stage)

    document_id = stages[0].document_id if stages else ""
    present_stages = tuple(stage.stage for stage in stages)
    present_set = {stage.stage for stage in stages}

    # 1. completeness — every canonical stage present.
    missing_stages = tuple(s for s in STAGES if s not in present_set)
    complete = not missing_stages

    # 2. ordering — strictly-increasing canonical rank (no duplicates, no reversals).
    ordered = True
    for prior, current in zip(present_stages, present_stages[1:], strict=False):
        if _STAGE_RANK[current] <= _STAGE_RANK[prior]:
            ordered = False
            break

    # 3. chaining — positional hash-links + a proper genesis head.
    broken_links: list[BrokenLink] = []
    for index, stage in enumerate(stages):
        if index == 0:
            genesis_ok = stage.stage == STAGES[0] and stage.parent_hash is None
            if not genesis_ok:
                if stage.stage == STAGES[0]:
                    broken_links.append(
                        BrokenLink(
                            stage=stage.stage,
                            document_id=stage.document_id,
                            reason=REASON_GENESIS_PARENTED,
                            expected="(none)",
                            actual=stage.parent_hash or "",
                        )
                    )
                else:
                    broken_links.append(
                        BrokenLink(
                            stage=stage.stage,
                            document_id=stage.document_id,
                            reason=REASON_NON_GENESIS_AT_HEAD,
                            expected=f"{STAGES[0]}(unparented)",
                            actual=f"{stage.stage}(parent={stage.parent_hash})",
                        )
                    )
        else:
            prior_hash = stages[index - 1].claimed_hash
            if stage.parent_hash != prior_hash:
                broken_links.append(
                    BrokenLink(
                        stage=stage.stage,
                        document_id=stage.document_id,
                        reason=REASON_PARENT_MISMATCH,
                        expected=prior_hash,
                        actual=stage.parent_hash or "",
                    )
                )
    chained = not broken_links

    # 4. single document — the chain is for ONE book; mixing books is a defect.
    document_ids = {stage.document_id for stage in stages}
    single_document = len(document_ids) <= 1

    # 5. tamper-evidence — HMAC recompute; None (unknown) when the key is absent.
    tampered_stages: tuple[str, ...] = ()
    if key is None:
        tamper_evident: bool | None = None
    else:
        tampered_stages = tuple(
            stage.stage
            for stage in stages
            if stage.claimed_hash != compute_stage_hash(stage, key)
        )
        tamper_evident = not tampered_stages

    # fold into the end-to-end verdict.
    structural_ok = complete and ordered and chained and single_document
    if not structural_ok:
        intact: bool | None = False
    elif tamper_evident is None:
        intact = None
    else:
        intact = tamper_evident

    notes: list[str] = []
    if not stages:
        notes.append("empty chain: no stages recorded")
    if not single_document:
        notes.append(
            f"mixed-document chain: {len(document_ids)} distinct document_ids present"
        )
    if key is None and stages:
        notes.append(
            "signing key not supplied: structural properties assessed, "
            "tamper-evidence unknown"
        )

    return ProvenanceChainReport(
        document_id=document_id,
        complete=complete,
        ordered=ordered,
        chained=chained,
        single_document=single_document,
        tamper_evident=tamper_evident,
        intact=intact,
        present_stages=present_stages,
        missing_stages=missing_stages,
        broken_links=tuple(broken_links),
        tampered_stages=tampered_stages,
        notes=tuple(notes),
    )
