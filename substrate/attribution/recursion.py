"""Attribution recursion — splitting one metered attention-second across the
people whose work is actually in front of the reader.

The operator's thesis is that attention is metered per second and distributed
"to the core data owners of who created the asset being viewed, that is mostly
the writers whose data was sourced, combined with the contributions of the
writer themselves who added new ideas." Until this module existed a synthesis
was attributed as a single asset: a second spent reading it landed wholly on
the synthesis, and the writers it sourced saw none of it.

This is a graph walk over provenance that already exists. The substrate
invariant is that every claim cites chunks, every chunk cites a document, and
every document carries an ``ip_holder_id``; ``substrate/attribution/compute.py``
already resolves that chain into a per-document share vector under master-spec
§9.3. All this module adds is the recursion on top of it — the author leg, the
depth cap, the explicit remainder, and integer conservation. No new store.

WHAT THIS MODULE IS NOT
-----------------------
It does not move money and cannot be made to. It computes a split and (option-
ally) writes one telemetry event. §9.0 is open, so accrual is not disbursement
and this is not even accrual. ``tests/test_attribution_recursion.py`` asserts
the boundary rather than trusting the convention: no escrow writer is reachable
from here, and a split leaves every balance untouched.

CONSERVATION
------------
Shares are integer *units*, not floats. A float split of a second across a
dozen holders across three depths does not sum back to one second, and "sums to
1.0 modulo rounding" is not a property you can defend in a payout dispute. So a
second is ``UNITS_PER_ATTENTION_SECOND`` integer sub-units, every apportionment
uses largest-remainder, and the lines sum to the total exactly. The unattributed
remainder is a line like any other: units that could not be placed are recorded
with the reason they could not be placed, never dropped.

Why a second implementation of largest-remainder when
``ad_inventory/attribution_explain._largest_remainder_cents`` exists: that one
apportions *cents* and breaks ties in the caller's dict-insertion order (its
``sorted`` is stable over ``weights.keys()``), which is fine inside a replay
that rebuilds the dict from canonical JSON but is not a property this contract
can rely on, because a split here must be byte-reproducible from the event log
no matter how the caller built its inputs. :func:`apportion_units` sorts keys
and breaks ties on the key itself. The two should be unified the day the cents
twin is made key-deterministic; that is a money-path change and not this lane's
to make.

THE THREE DECISIONS
-------------------
Recorded in full, with what was rejected, in
``docs/decisions/attribution-recursion-author-share.md``. In brief:

* **Author share** — a fixed, versioned constant is live
  (:data:`AUTHOR_SHARE_FIXED`). The principled alternative, a share
  proportional to non-quoted-span length, needs the five-way epistemic typing
  (quotation / paraphrase / measurement / inference / synthesis) on each claim.
  That typing is not merely unpopulated: ``ThesisComponent`` in
  ``substrate/schemas/events.py`` declares ``extra="forbid"`` and has no field
  for it, so no synthesis in the tree can carry it. The split records
  ``author_share_policy`` so the day it lands, rows priced under each policy
  stay distinguishable.

* **Depth** — :data:`MAX_RECURSION_DEPTH`. Past the cap, and on any cycle, the
  units go to the unattributed bucket with an explicit reason.

* **Versioning** — :data:`ATTRIBUTION_RECURSION_VERSION` versions this walk.
  It is deliberately NOT a bump of ``ATTRIBUTION_ALGORITHM_VERSION``: that
  constant versions the §9.3 A/B/C share math, which this change does not
  touch, and the open Option-C unification
  (``docs/decisions/afa-synthesis-attribution-canonical.md``) reserves its next
  bump for the math-identity change the operator has still to ratify. Spending
  it here would destroy that signal. A split stamps both versions, so every row
  names what priced it and historical rows are never recomputed under new ones.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Literal, Protocol

# ---------------------------------------------------------------------------
# Versioned constants — the public math contract
# ---------------------------------------------------------------------------

# The recursion walk's own version. Bump on ANY change that can move a split:
# the author/source ordering, the depth-cap semantics, the remainder rules, the
# apportionment tie-break. Distinct from ATTRIBUTION_ALGORITHM_VERSION (the
# §9.3 share math) and from FRAME_WEIGHTING_VERSION (which seconds count at
# all), so a dispute isolates which of the three moved.
ATTRIBUTION_RECURSION_VERSION = "attr-recursion-v1"

# Which author-share policy priced a row. The live policy is the fixed
# constant below; the name carries the number so a row stamped v1 can never be
# re-read under a different constant.
AUTHOR_SHARE_POLICY = "author-share-fixed-30-v1"

# The fraction of a second credited to the writer of the synthesis rather than
# to the writers it sourced. This is a CONVENTION, not a measurement, and it is
# the single most contestable number in this module — which is exactly why it
# is one named constant behind one version rather than an expression scattered
# through the walk.
#
# It is bounded above by the operator's own framing: a second is distributed to
# the data owners "mostly" — so the author's leg is a minority, under 0.5. It is
# bounded below by the fact that a synthesis whose author earns a rounding error
# is not a product anyone writes for. 0.30 sits where those two bounds leave
# room, and coincides in shape with the 70/30 platform split already in
# ``ad_inventory/payout.py`` — a coincidence of shape, noted because it makes
# the number easier to argue about, NOT a derivation of it.
AUTHOR_SHARE_FIXED = 0.30

# How deep a synthesis-citing-a-synthesis chain is walked before the remaining
# units are parked in the unattributed bucket. Three levels covers a synthesis
# built on syntheses built on sources; past that the provenance is too diluted
# for a per-second credit to mean anything, and an uncapped walk over a graph
# that can contain a cycle is an outage, not a feature.
MAX_RECURSION_DEPTH = 3

# Integer sub-units per metered attention-second. One part per million is far
# finer than any plausible split (a second across a few dozen subjects over
# three depths) while staying comfortably inside int arithmetic, so the floor
# of a legitimate share is never zero for lack of resolution.
UNITS_PER_ATTENTION_SECOND = 1_000_000

# Which rights gate produced the document share vector a split consumed.
#
# "display" is the §9.0 retrieval-time gate: it withholds BOTH
# ``restricted_pending_opt_in`` and ``personal_reading``. That is correct for a
# surface and WRONG for an earn path, where ``restricted_pending_opt_in`` must
# keep accruing to its pre-onboarded holder's escrow — that mechanism is the
# whole point of §9.10, and
# ``docs/decisions/afa-synthesis-attribution-canonical.md`` records the verified
# finding that collapsing the two gates would zero out escrow for exactly the
# rights holders §9.10 exists to serve.
#
# Only "display" exists today because only the display-gated producer exists.
# A row stamped "display" is telemetry and must never be settled as money.
GATE_DISPLAY = "display"

# Reasons a line of units could not be placed on a subject. Every one of these
# is a line in the split, never a silent loss.
REASON_AUTHOR_UNRESOLVED = "author_unresolved"
REASON_OWNER_UNKNOWN = "owner_unknown"
REASON_DEPTH_CAP = "depth_cap"
REASON_CYCLE = "cycle_detected"
REASON_UNRESOLVED_SYNTHESIS = "synthesis_unresolved"

SubjectKind = Literal["ip_holder", "author", "unattributed"]

SUBJECT_IP_HOLDER: Final = "ip_holder"
SUBJECT_AUTHOR: Final = "author"
SUBJECT_UNATTRIBUTED: Final = "unattributed"


# ---------------------------------------------------------------------------
# Apportionment
# ---------------------------------------------------------------------------


def apportion_units(weights: Mapping[str, float], total_units: int) -> dict[str, int]:
    """Split ``total_units`` across ``weights`` so the parts sum EXACTLY to
    ``total_units`` (largest remainder), deterministically.

    Determinism is the point. Keys are visited in sorted order and ties on the
    fractional remainder break on the key, so two callers that assembled the
    same weights in different orders get the same split, and a replay from the
    event log reproduces it without depending on how the original caller built
    its dict.

    Negative weights are clamped to zero rather than rejected: a weight vector
    reaching here has already been normalized upstream, and a split is not the
    place to raise on data that would simply earn nothing.
    """
    keys = sorted(weights)
    clamped = {k: max(0.0, float(weights[k])) for k in keys}
    total_w = sum(clamped.values())
    if total_units <= 0 or total_w <= 0.0:
        return dict.fromkeys(keys, 0)
    exact = {k: (clamped[k] / total_w) * total_units for k in keys}
    floored = {k: int(exact[k]) for k in keys}
    remainder = total_units - sum(floored.values())
    order = sorted(keys, key=lambda k: (-(exact[k] - floored[k]), k))
    for k in order[:remainder]:
        floored[k] += 1
    return floored


# ---------------------------------------------------------------------------
# The provenance a walk consumes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SynthesisProvenance:
    """Everything the walk needs about ONE synthesis, already gated.

    ``document_shares`` is the §9.3 share vector over the documents this
    synthesis sourced — whatever the canonical producer returned, already
    rights-gated. ``document_ip_holders`` is the last link of the provenance
    chain; ``None`` is an honest "this document has no resolved owner", never
    an invented one.

    ``nested_syntheses`` maps a document id to the synthesis id it IS, for the
    synthesis-citing-a-synthesis case. Empty for every document in the tree
    today, because nothing deposits a synthesis back into ``documents`` — see
    :class:`DisplayGatedProvenanceResolver`.

    ``author_user_id`` is the writer of this synthesis. ``None`` is common and
    is handled honestly: the author's units become an explicit unattributed
    line rather than being quietly redistributed to the sources.

    The two claim counts are carried but do not price anything. They are the
    measurement that makes the author-share decision cheap to revisit: a
    claim grounded in ``supporting_path_indices`` alone cites no chunk, which
    is the closest structural evidence of "new ideas" the substrate holds
    today. Recording the ratio now means the operator can see whether a
    principled author share is viable on real syntheses before anyone rewrites
    the constant.
    """

    synthesis_id: str
    author_user_id: str | None = None
    document_shares: Mapping[str, float] = field(default_factory=dict)
    document_ip_holders: Mapping[str, str | None] = field(default_factory=dict)
    nested_syntheses: Mapping[str, str] = field(default_factory=dict)
    claim_count: int = 0
    path_only_claim_count: int = 0

    def to_snapshot(self) -> dict[str, Any]:
        """The canonical, JSON-safe form persisted in the event's inputs."""
        return {
            "synthesis_id": self.synthesis_id,
            "author_user_id": self.author_user_id,
            "document_shares": {
                k: float(v) for k, v in sorted(self.document_shares.items())
            },
            "document_ip_holders": dict(sorted(self.document_ip_holders.items())),
            "nested_syntheses": dict(sorted(self.nested_syntheses.items())),
            "claim_count": int(self.claim_count),
            "path_only_claim_count": int(self.path_only_claim_count),
        }

    @classmethod
    def from_snapshot(cls, raw: Mapping[str, Any]) -> SynthesisProvenance:
        return cls(
            synthesis_id=str(raw["synthesis_id"]),
            author_user_id=raw.get("author_user_id"),
            document_shares={
                str(k): float(v)
                for k, v in (raw.get("document_shares") or {}).items()
            },
            document_ip_holders={
                str(k): (None if v is None else str(v))
                for k, v in (raw.get("document_ip_holders") or {}).items()
            },
            nested_syntheses={
                str(k): str(v) for k, v in (raw.get("nested_syntheses") or {}).items()
            },
            claim_count=int(raw.get("claim_count") or 0),
            path_only_claim_count=int(raw.get("path_only_claim_count") or 0),
        )


class ProvenanceResolver(Protocol):
    """Resolves a synthesis id to its gated provenance, or ``None`` when the
    synthesis cannot be read. Returning ``None`` is not an error — it produces
    an explicit ``synthesis_unresolved`` remainder line, which is the honest
    outcome for a synthesis that was deleted or was never archived."""

    def resolve(self, synthesis_id: str) -> SynthesisProvenance | None: ...


@dataclass(frozen=True)
class StaticProvenanceResolver:
    """A resolver over an in-memory map. Used by :func:`replay` to reproduce a
    split from an event's inputs snapshot, and by tests to exercise depths the
    live tree cannot reach yet."""

    provenance: Mapping[str, SynthesisProvenance]

    def resolve(self, synthesis_id: str) -> SynthesisProvenance | None:
        return self.provenance.get(synthesis_id)


# ---------------------------------------------------------------------------
# The split
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AttributionShare:
    """One conserved line of a split. See
    ``substrate/schemas/events.py::AttributionRecursionLine`` for the wire
    twin."""

    subject_kind: SubjectKind
    subject_id: str | None
    units: int
    depth: int
    via_synthesis_id: str
    reason: str | None = None

    def key(self) -> tuple[str, str, str, int, str]:
        """Merge key. Two documents owned by the same holder, credited at the
        same depth through the same synthesis, are one line — the split is a
        statement about subjects, not about documents."""
        return (
            self.subject_kind,
            self.subject_id or "",
            self.reason or "",
            self.depth,
            self.via_synthesis_id,
        )


@dataclass(frozen=True)
class SynthesisAttributionSplit:
    """The full result of splitting metered attention on one synthesis."""

    synthesis_id: str
    units_per_second: int
    seconds: int
    total_units: int
    shares: tuple[AttributionShare, ...]
    recursion_version: str
    author_share_policy: str
    author_share: float
    share_algorithm: str
    share_algorithm_version: str
    gate: str
    max_depth: int
    inputs_json: str
    inputs_digest: str

    def conserves(self) -> bool:
        """Σ line units == total units. The contract."""
        return sum(s.units for s in self.shares) == self.total_units

    def unattributed_units(self) -> int:
        return sum(s.units for s in self.shares if s.subject_kind == SUBJECT_UNATTRIBUTED)

    def by_subject(self) -> dict[tuple[str, str | None], int]:
        """Units per (kind, subject), collapsed across depths — what a payout
        would consume if §9.0 ever opens and someone builds one."""
        out: dict[tuple[str, str | None], int] = {}
        for s in self.shares:
            k = (s.subject_kind, s.subject_id)
            out[k] = out.get(k, 0) + s.units
        return out


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _merge(shares: Sequence[AttributionShare]) -> tuple[AttributionShare, ...]:
    merged: dict[tuple[str, str, str, int, str], AttributionShare] = {}
    for s in shares:
        k = s.key()
        prior = merged.get(k)
        if prior is None:
            merged[k] = s
        else:
            merged[k] = AttributionShare(
                subject_kind=s.subject_kind,
                subject_id=s.subject_id,
                units=prior.units + s.units,
                depth=s.depth,
                via_synthesis_id=s.via_synthesis_id,
                reason=s.reason,
            )
    return tuple(merged[k] for k in sorted(merged))


def _walk(
    synthesis_id: str,
    units: int,
    depth: int,
    path: tuple[str, ...],
    resolver: ProvenanceResolver,
    author_share: float,
    max_depth: int,
    out: list[AttributionShare],
    seen: dict[str, SynthesisProvenance],
) -> None:
    """Split ``units`` measured on ``synthesis_id`` and append the lines.

    Every early return emits a line for the whole budget. That is the property
    that makes conservation hold by construction rather than by a final
    reconciliation step: units enter the walk once and leave it exactly once.
    """
    if units <= 0:
        return

    prov = resolver.resolve(synthesis_id)
    if prov is None:
        out.append(AttributionShare(
            subject_kind=SUBJECT_UNATTRIBUTED,
            subject_id=None,
            units=units,
            depth=depth,
            via_synthesis_id=synthesis_id,
            reason=REASON_UNRESOLVED_SYNTHESIS,
        ))
        return
    seen[synthesis_id] = prov

    sourced_weight = sum(max(0.0, float(w)) for w in prov.document_shares.values())

    if sourced_weight <= 0.0:
        # Nothing sourced. A synthesis that cites no document is entirely its
        # author's new ideas — the whole budget is the author's leg, not a
        # remainder, because there is no sourced material for it to compete
        # with. An unresolved author still parks it honestly.
        _emit_author(prov, units, depth, out)
        return

    legs = apportion_units(
        {SUBJECT_AUTHOR: author_share, "sourced": 1.0 - author_share},
        units,
    )
    _emit_author(prov, legs[SUBJECT_AUTHOR], depth, out)

    per_document = apportion_units(prov.document_shares, legs["sourced"])
    next_path = (*path, synthesis_id)
    for document_id in sorted(per_document):
        doc_units = per_document[document_id]
        if doc_units <= 0:
            continue
        nested = prov.nested_syntheses.get(document_id)
        if nested is not None:
            if nested in next_path:
                out.append(AttributionShare(
                    subject_kind=SUBJECT_UNATTRIBUTED,
                    subject_id=None,
                    units=doc_units,
                    depth=depth + 1,
                    via_synthesis_id=synthesis_id,
                    reason=REASON_CYCLE,
                ))
                continue
            if depth + 1 > max_depth:
                out.append(AttributionShare(
                    subject_kind=SUBJECT_UNATTRIBUTED,
                    subject_id=None,
                    units=doc_units,
                    depth=depth + 1,
                    via_synthesis_id=synthesis_id,
                    reason=REASON_DEPTH_CAP,
                ))
                continue
            _walk(
                nested, doc_units, depth + 1, next_path, resolver,
                author_share, max_depth, out, seen,
            )
            continue

        holder = prov.document_ip_holders.get(document_id)
        if holder:
            out.append(AttributionShare(
                subject_kind=SUBJECT_IP_HOLDER,
                subject_id=holder,
                units=doc_units,
                depth=depth,
                via_synthesis_id=synthesis_id,
            ))
        else:
            out.append(AttributionShare(
                subject_kind=SUBJECT_UNATTRIBUTED,
                subject_id=None,
                units=doc_units,
                depth=depth,
                via_synthesis_id=synthesis_id,
                reason=REASON_OWNER_UNKNOWN,
            ))


def _emit_author(
    prov: SynthesisProvenance,
    units: int,
    depth: int,
    out: list[AttributionShare],
) -> None:
    if units <= 0:
        return
    if prov.author_user_id:
        out.append(AttributionShare(
            subject_kind=SUBJECT_AUTHOR,
            subject_id=prov.author_user_id,
            units=units,
            depth=depth,
            via_synthesis_id=prov.synthesis_id,
        ))
    else:
        # The substrate has no owner on a `syntheses` row and no owner on the
        # event envelope, so for most syntheses the author is genuinely not
        # resolvable. Parking the units under a named reason is the honest
        # answer; redistributing them to the sources would silently overstate
        # what the sourced writers are owed.
        out.append(AttributionShare(
            subject_kind=SUBJECT_UNATTRIBUTED,
            subject_id=None,
            units=units,
            depth=depth,
            via_synthesis_id=prov.synthesis_id,
            reason=REASON_AUTHOR_UNRESOLVED,
        ))


def split_attention(
    synthesis_id: str,
    *,
    resolver: ProvenanceResolver,
    seconds: int = 1,
    units_per_second: int = UNITS_PER_ATTENTION_SECOND,
    author_share: float = AUTHOR_SHARE_FIXED,
    author_share_policy: str = AUTHOR_SHARE_POLICY,
    max_depth: int = MAX_RECURSION_DEPTH,
    share_algorithm: str = "A",
    share_algorithm_version: str = "",
    gate: str = GATE_DISPLAY,
) -> SynthesisAttributionSplit:
    """Split ``seconds`` of metered attention on ``synthesis_id``.

    Pure: the only thing that touches storage is ``resolver``, and it only
    reads. The returned split conserves — ``split.conserves()`` is true for
    every input, including a synthesis that resolves to nothing.
    """
    if seconds < 0:
        raise ValueError("seconds must be >= 0")
    if units_per_second < 1:
        raise ValueError("units_per_second must be >= 1")
    if not 0.0 <= author_share <= 1.0:
        raise ValueError("author_share must be in [0, 1]")
    if max_depth < 1:
        raise ValueError("max_depth must be >= 1")

    total_units = seconds * units_per_second
    lines: list[AttributionShare] = []
    seen: dict[str, SynthesisProvenance] = {}
    _walk(
        synthesis_id, total_units, 0, (), resolver,
        author_share, max_depth, lines, seen,
    )
    merged = _merge(lines)

    inputs = {
        "synthesis_id": synthesis_id,
        "seconds": int(seconds),
        "units_per_second": int(units_per_second),
        "author_share": float(author_share),
        "author_share_policy": author_share_policy,
        "max_depth": int(max_depth),
        "recursion_version": ATTRIBUTION_RECURSION_VERSION,
        "share_algorithm": share_algorithm,
        "share_algorithm_version": share_algorithm_version,
        "gate": gate,
        "provenance": [seen[k].to_snapshot() for k in sorted(seen)],
    }
    inputs_json = _canonical_json(inputs)

    return SynthesisAttributionSplit(
        synthesis_id=synthesis_id,
        units_per_second=units_per_second,
        seconds=seconds,
        total_units=total_units,
        shares=merged,
        recursion_version=ATTRIBUTION_RECURSION_VERSION,
        author_share_policy=author_share_policy,
        author_share=author_share,
        share_algorithm=share_algorithm,
        share_algorithm_version=share_algorithm_version,
        gate=gate,
        max_depth=max_depth,
        inputs_json=inputs_json,
        inputs_digest=hashlib.sha256(inputs_json.encode()).hexdigest(),
    )


def replay(inputs_json: str) -> SynthesisAttributionSplit:
    """Reproduce a split from the ``inputs_json`` carried on its event.

    This is what makes the done-bar's "reproducible from the event log alone"
    a fact rather than an aspiration: the event carries every input the walk
    consumed, including the resolved provenance of every synthesis it visited,
    so a replay needs no database and no network — and a replay that does not
    reproduce the recorded lines is a defect, not a tolerance.
    """
    raw = json.loads(inputs_json)
    provenance = {
        str(p["synthesis_id"]): SynthesisProvenance.from_snapshot(p)
        for p in raw.get("provenance") or []
    }
    return split_attention(
        str(raw["synthesis_id"]),
        resolver=StaticProvenanceResolver(provenance),
        seconds=int(raw["seconds"]),
        units_per_second=int(raw["units_per_second"]),
        author_share=float(raw["author_share"]),
        author_share_policy=str(raw["author_share_policy"]),
        max_depth=int(raw["max_depth"]),
        share_algorithm=str(raw.get("share_algorithm") or "A"),
        share_algorithm_version=str(raw.get("share_algorithm_version") or ""),
        gate=str(raw.get("gate") or GATE_DISPLAY),
    )


# ---------------------------------------------------------------------------
# The live resolver
# ---------------------------------------------------------------------------


class DisplayGatedProvenanceResolver:
    """Resolves provenance from the substrate, through the §9.0 DISPLAY gate.

    The gate is in the name on purpose. This resolver's share vector comes from
    ``compute_attribution_for_synthesis``, which zeroes both
    ``restricted_pending_opt_in`` and ``personal_reading``. That is right for a
    surface and wrong for money: on an earn path
    ``restricted_pending_opt_in`` must keep accruing to its pre-onboarded
    holder (§9.10). Anyone wiring a settlement path needs an
    ``EarnGatedProvenanceResolver`` that excludes only ``personal_reading``;
    reaching for this one would silently zero the escrow §9.10 exists to build.

    AUTHOR RESOLUTION is best-effort and frequently fails, honestly. A
    ``syntheses`` row carries no owner and neither does the event envelope, so
    the only signal available is the owner of the documents ingested under the
    same investigation — unambiguous only when they agree. ``author_overrides``
    lets a caller that does know (a metering surface knows whose window it is)
    supply the answer; anything unresolved becomes an ``author_unresolved``
    line rather than a guess.

    NESTED SYNTHESES are detected by a cited document id that is also a
    ``syntheses`` primary key. Nothing in the tree deposits a synthesis back
    into ``documents`` today, so this returns empty in production and the live
    depth is 1 — the cap and the cycle guard are exercised by tests, and arm
    themselves the moment a depositor exists. Recursion was built rather than
    deferred because the cap has to be in the versioned contract from the first
    priced row, not bolted on after rows exist.

    Both queries are read-only, and ``compute_attribution_for_synthesis`` opens
    its own read-only handle. The single-writer invariant is untouched: this
    module never opens a writable connection.
    """

    def __init__(
        self,
        *,
        db_path: str | None = None,
        algorithm: str = "A",
        author_overrides: Mapping[str, str] | None = None,
    ) -> None:
        if algorithm not in ("A", "B", "C"):
            raise ValueError(f"algorithm must be one of A/B/C, got {algorithm!r}")
        self.db_path = db_path
        self.algorithm = algorithm
        self.author_overrides = dict(author_overrides or {})

    def resolve(self, synthesis_id: str) -> SynthesisProvenance | None:
        import duckdb

        from substrate.graph import default_db_path

        from .compute import compute_attribution_for_synthesis

        resolved_path = self.db_path or default_db_path()
        try:
            computed = compute_attribution_for_synthesis(
                synthesis_id, db_path=resolved_path, emit_event=False,
            )
        except ValueError:
            # The synthesis is not in the table. An explicit unresolved
            # remainder is the right answer; inventing an empty provenance
            # would credit the whole second to an author who does not exist.
            return None

        per_algorithm = {
            "A": computed.option_a,
            "B": computed.option_b,
            "C": computed.option_c,
        }
        result = per_algorithm[self.algorithm]

        con = duckdb.connect(resolved_path, read_only=True)
        try:
            author = self.author_overrides.get(synthesis_id)
            if author is None:
                author = _resolve_author_user_id(con, synthesis_id)
            nested = _resolve_nested_syntheses(con, list(result.shares))
            claim_count, path_only = _count_claims(con, synthesis_id)
        finally:
            con.close()

        return SynthesisProvenance(
            synthesis_id=synthesis_id,
            author_user_id=author,
            document_shares=dict(result.shares),
            document_ip_holders=dict(result.document_ip_holders),
            nested_syntheses=nested,
            claim_count=claim_count,
            path_only_claim_count=path_only,
        )


def _resolve_author_user_id(con: Any, synthesis_id: str) -> str | None:
    """The one owner of the documents ingested under this synthesis's
    investigation, or ``None`` when there is no such document or they disagree.

    Ambiguity resolves to ``None`` deliberately. Picking the first of several
    owners would attribute a writer's second to whoever happens to sort first,
    which is worse than admitting the substrate cannot say.
    """
    rows = con.execute(
        "SELECT DISTINCT d.owner_user_id FROM documents d "
        "JOIN syntheses s ON s.investigation_id = d.investigation_id "
        "WHERE s.synthesis_id = ? AND d.owner_user_id IS NOT NULL",
        [synthesis_id],
    ).fetchall()
    if len(rows) != 1:
        return None
    return str(rows[0][0])


def _resolve_nested_syntheses(con: Any, document_ids: list[str]) -> dict[str, str]:
    """Cited documents that are themselves archived syntheses."""
    if not document_ids:
        return {}
    placeholders = ",".join("?" for _ in document_ids)
    rows = con.execute(
        f"SELECT synthesis_id FROM syntheses WHERE synthesis_id IN ({placeholders})",
        list(document_ids),
    ).fetchall()
    return {str(r[0]): str(r[0]) for r in rows}


def _count_claims(con: Any, synthesis_id: str) -> tuple[int, int]:
    """(total claims, claims grounded only in connector paths).

    The second number is the measurement the author-share decision needs: a
    claim citing no chunk is the substrate's closest structural evidence of a
    contribution that is not sourced material. It prices nothing today.
    """
    row = con.execute(
        "SELECT thesis FROM syntheses WHERE synthesis_id = ?", [synthesis_id],
    ).fetchone()
    if row is None or not row[0]:
        return (0, 0)
    try:
        thesis = json.loads(row[0])
    except (TypeError, ValueError):
        return (0, 0)
    components = thesis.get("thesis_components") or []
    total = len(components)
    path_only = sum(
        1 for c in components
        if not (c.get("supporting_chunk_ids") or []) and (c.get("supporting_path_indices") or [])
    )
    return (total, path_only)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def compute_recursive_attribution(
    synthesis_id: str,
    *,
    seconds: int = 1,
    db_path: str | None = None,
    algorithm: str = "A",
    author_overrides: Mapping[str, str] | None = None,
    emit_event: bool = False,
    investigation_id: str | None = None,
) -> SynthesisAttributionSplit:
    """Split ``seconds`` of metered attention on an archived synthesis.

    Reads the substrate through the §9.0 display gate and, with
    ``emit_event=True``, writes one ``SYNTHESIS_ATTRIBUTION_RECURSED`` event
    carrying the inputs the split consumed so it replays from the log alone.

    Nothing here moves money. The event is telemetry and the split is a
    statement of who is owed attention, not cents — §9.0 is open, and accrual
    is not disbursement.
    """
    from .algorithms import ATTRIBUTION_SHARE_MATH_VERSION

    resolver = DisplayGatedProvenanceResolver(
        db_path=db_path, algorithm=algorithm, author_overrides=author_overrides,
    )
    split = split_attention(
        synthesis_id,
        resolver=resolver,
        seconds=seconds,
        share_algorithm=algorithm,
        share_algorithm_version=ATTRIBUTION_SHARE_MATH_VERSION,
        gate=GATE_DISPLAY,
    )

    if emit_event:
        from substrate.event_log import emit_typed
        from substrate.schemas import (
            AttributionRecursionLine,
            SynthesisAttributionRecursedPayload,
        )

        payload = SynthesisAttributionRecursedPayload(
            synthesis_id=synthesis_id,
            recursion_version=split.recursion_version,
            author_share_policy=split.author_share_policy,
            author_share=split.author_share,
            share_algorithm=split.share_algorithm,
            share_algorithm_version=split.share_algorithm_version,
            gate=split.gate,
            units_per_second=split.units_per_second,
            seconds=split.seconds,
            total_units=split.total_units,
            max_depth=split.max_depth,
            lines=[
                AttributionRecursionLine(
                    subject_kind=s.subject_kind,
                    subject_id=s.subject_id,
                    units=s.units,
                    depth=s.depth,
                    via_synthesis_id=s.via_synthesis_id,
                    reason=s.reason,
                )
                for s in split.shares
            ],
            inputs_json=split.inputs_json,
            inputs_digest=split.inputs_digest,
        )
        emit_typed(
            investigation_id or "__operator__",
            payload,
            synthesis_id=synthesis_id,
            role="attribution",
            policy_id="attribution/recursion",
        )

    return split


__all__ = [
    "ATTRIBUTION_RECURSION_VERSION",
    "AUTHOR_SHARE_FIXED",
    "AUTHOR_SHARE_POLICY",
    "GATE_DISPLAY",
    "MAX_RECURSION_DEPTH",
    "UNITS_PER_ATTENTION_SECOND",
    "AttributionShare",
    "DisplayGatedProvenanceResolver",
    "ProvenanceResolver",
    "StaticProvenanceResolver",
    "SynthesisAttributionSplit",
    "SynthesisProvenance",
    "apportion_units",
    "compute_recursive_attribution",
    "replay",
    "split_attention",
]
