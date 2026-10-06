"""Selective thread-outcome merge into a FORK (thread-merge + document fork
SPR-02).

The shipped in-place source-merge shape — preview (no writes, a full
receipt with before/after hashes + the conflict list) → commit (write-lock
scope, body rewrite, ledger row), the snapshot discipline of
``SourceMergeCommitReceipt`` — retargeted at the FORK document, never the
source. Under T6 (THREAD-CONTRACT §1.11) a merge never writes the source;
the fork is the lawful divergent target. This module NEVER edits or
re-enters ``source_merge.py``: its contract, acks, receipts and restore
stand untouched.

The operator picks outcome items — stable ``DistilledNode`` identity:
(investigation id, node id) — and merges them INTO the fork. Every merged
item lands under an honest provenance marker naming its source
investigation (the source-merge marker pattern). Conflicts are detected on
a three-source honest ladder, and NEVER auto-resolve:

  (a) cross-member pairs — compose's pair model (compose.py): the same
      claim text surfacing in two different threads is listed for review
      (carrying both would duplicate);
  (b) anchor passage conflicts — where the item's thread is linked to an
      ACTIVE anchor on the fork document (unit 1) and the item's normalized
      text hash differs from the pinned passage's hash: the same thread
      asserting differently over the pinned passage. Where no anchor
      exists, this source simply does not fire — the degradation is
      asserted in the proofs, not assumed;
  (c) operator-flagged conflicts — the operator names a selected item as
      conflicted; the flag is a conflict, recorded like any other.

Commit REQUIRES a per-item resolution (accept | keep_fork | skip) for EVERY
conflicted item, and each resolution writes an audit row
(``fork_merge_resolutions``) in the same commit scope. A commit with
incomplete resolutions is refused atomically (the route maps it to 409) —
no partial write, the body hash unchanged. Commit is idempotent on its
canonical commit id (merge intent + resolutions): a replay returns the
recorded receipt with ``writes_performed=False``.

Gate discipline: an item merges ONLY its own text after the shared distill
reader checks node ownership and source readability. Source body bytes are
used only by that read gate, never copied into the fork.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.books.highlights.resolve import reanchor_document
from substrate.books.highlights.schema import highlights_table_exists
from substrate.books.serve_guard import LinkBackMissingError, serve_full_text_guarded
from substrate.documents.forks import DocumentForkRow, DocumentForkStore
from substrate.event_log import log_event
from substrate.rights import T3BodyServeError
from substrate.rights.ad_eligibility import licence_tier_of

FORK_MERGE_COMMITTED = "fork_merge.committed"

#: Resolution choices — the only ways a conflicted item may change state.
RESOLUTION_CHOICES: frozenset[str] = frozenset({"accept", "keep_fork", "skip"})

#: Conflict kinds on the honest ladder.
CONFLICT_CROSS_MEMBER = "cross_member_pair"
CONFLICT_ANCHOR_PASSAGE = "anchor_passage"
CONFLICT_OPERATOR_FLAG = "operator_flag"

MARKER_START = "<!-- antiek-fork-merge-start -->"
MARKER_END = "<!-- antiek-fork-merge-end -->"

DDL = """
CREATE TABLE IF NOT EXISTS fork_merge_commits (
  commit_id VARCHAR PRIMARY KEY,
  merge_id VARCHAR NOT NULL,
  fork_id VARCHAR NOT NULL,
  owner_user_id VARCHAR NOT NULL,
  fork_document_id VARCHAR NOT NULL,
  items_json VARCHAR NOT NULL,
  conflicts_json VARCHAR NOT NULL,
  resolutions_json VARCHAR NOT NULL,
  before_fork_body VARCHAR NOT NULL,
  before_fork_hash VARCHAR NOT NULL CHECK (length(before_fork_hash) = 64),
  after_fork_hash VARCHAR NOT NULL CHECK (length(after_fork_hash) = 64),
  fork_bytes_before INTEGER NOT NULL,
  fork_bytes_after INTEGER NOT NULL,
  operator_reviewer VARCHAR,
  event_id VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fork_merge_resolutions (
  resolution_id VARCHAR PRIMARY KEY,
  commit_id VARCHAR NOT NULL,
  fork_id VARCHAR NOT NULL,
  owner_user_id VARCHAR NOT NULL,
  investigation_id VARCHAR NOT NULL,
  node_id VARCHAR NOT NULL,
  choice VARCHAR NOT NULL CHECK (choice IN ('accept', 'keep_fork', 'skip')),
  conflict_refs_json VARCHAR NOT NULL,
  operator_reviewer VARCHAR,
  created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (commit_id, investigation_id, node_id)
);
"""


class ForkMergeBodyUnavailableError(ValueError):
    """The target body cannot pass the owner-read gate; refuse the whole merge."""

    def __init__(self, document_id: str, *, tier: str | None, reason: str) -> None:
        self.document_id = document_id
        self.tier = tier
        self.reason = reason
        super().__init__(
            f"fork_merge_body_unavailable: document={document_id}; "
            f"tier={tier or 'none'}; reason={reason}"
        )


class ForkMergeItemError(ValueError):
    """A selected item does not resolve to a distilled node of its thread."""


class ForkMergeUnresolvedConflictsError(ValueError):
    """Commit was asked without a resolution for every conflicted item.

    ``missing`` names the item refs still unresolved — the route's 409
    detail carries them, so the operator learns exactly what waits."""

    def __init__(self, missing: list[tuple[str, str]]):
        self.missing = missing
        super().__init__(
            "fork_merge_unresolved_conflicts: every conflicted item waits "
            "for a human choice — unresolved: "
            + ", ".join(f"{iid}/{nid}" for iid, nid in missing)
        )


def init_fork_merge_schema(con: LockedConnection) -> None:
    """Create the additive fork-merge schema on an existing writer
    connection (idempotent — CREATE TABLE IF NOT EXISTS throughout)."""
    con.execute(DDL)


def _require_locked(con: Any) -> None:
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"fork merge requires a LockedConnection (got "
            f"{type(con).__name__}). Use runtime.db_lock.connect_write(db_path)."
        )


def _hash_text(value: str | None) -> str:
    return hashlib.sha256((value or "").encode("utf-8")).hexdigest()


_ZERO_WIDTH = ("​", "‌", "‍", "﻿", "­")


def _bridge_norm(value: str) -> str:
    """The anchors stack's cross-runtime normalization (unicode-nfc-v1's
    bridge form: NFC + zero-width strip + whitespace collapse,
    highlights/resolve.py) — item hashes compare against the pinned
    passage's hash under the SAME normalization."""
    s = unicodedata.normalize("NFC", value)
    for ch in _ZERO_WIDTH:
        s = s.replace(ch, "")
    return re.sub(r"\s+", " ", s).strip()


def _item_hash(text: str) -> str:
    return hashlib.sha256(_bridge_norm(text).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class MergeItem:
    """One selected outcome item, resolved against the live distill read."""

    investigation_id: str
    node_id: str
    kind: str
    text: str
    text_sha256: str
    source_document_id: str | None


@dataclass(frozen=True, slots=True)
class MergeConflict:
    """One listed conflict — the review surface. Never auto-resolved."""

    conflict_id: str
    kind: str
    item_refs: tuple[tuple[str, str], ...]
    detail: str
    anchor_id: str | None


@dataclass(frozen=True, slots=True)
class ForkMergePreviewReceipt:
    status: str
    merge_id: str
    fork_id: str
    fork_document_id: str
    items: list[MergeItem]
    conflicts: list[MergeConflict]
    before_fork_hash: str
    """The hash if EVERY selected item lands (resolutions pending — the
    commit's receipt carries the actual after-hash)."""
    after_fork_hash: str
    fork_bytes_before: int
    fork_bytes_after: int
    writes_performed: bool


@dataclass(frozen=True, slots=True)
class ForkMergeCommitReceipt:
    status: str
    commit_id: str
    merge_id: str
    fork_id: str
    fork_document_id: str
    event_id: str | None
    items: list[MergeItem]
    conflicts: list[MergeConflict]
    resolutions: dict[str, str]
    before_fork_hash: str
    after_fork_hash: str
    fork_bytes_before: int
    fork_bytes_after: int
    writes_performed: bool


@dataclass(frozen=True, slots=True)
class Resolution:
    investigation_id: str
    node_id: str
    choice: str


def _item_ref_key(investigation_id: str, node_id: str) -> str:
    return f"{investigation_id}{node_id}"


def _marker_section(item: MergeItem) -> str:
    """The honest provenance marker naming the source investigation and
    node — the source-merge marker pattern, retargeted."""
    return "\n".join(
        [
            MARKER_START,
            f"<!-- from: investigation {item.investigation_id} · node {item.node_id} ({item.kind}) -->",
            item.text.strip(),
            MARKER_END,
        ]
    )


def _after_body(before: str, items: list[MergeItem]) -> str:
    return "\n\n".join(
        part
        for part in [before.rstrip(), *(_marker_section(i) for i in items)]
        if part
    )


def _resolve_items(
    con: Any,
    items: list[tuple[str, str]],
    *,
    owner_user_id: str,
    events_dir: str | None,
) -> list[MergeItem]:
    """Resolve only caller-readable outcomes on the caller's connection.

    Unknown and unreadable refs have the same refusal. The shared distill
    reader applies node ownership and the source body gate before any text
    enters a preview or a commit.
    """
    from roles.note_taker.distill_query import DistilledNode, readable_distillation_for

    resolved: list[MergeItem] = []
    seen: set[tuple[str, str]] = set()
    by_investigation: dict[str, dict[str, DistilledNode]] = {}
    for iid, nid in items:
        if (iid, nid) in seen:
            continue
        seen.add((iid, nid))
        if iid not in by_investigation:
            view = readable_distillation_for(
                iid, owner_user_id=owner_user_id, events_dir=events_dir, con=con
            )
            by_investigation[iid] = {
                node.node_id: node for node in [*view.insights, *view.questions]
            }
        node = by_investigation[iid].get(nid)
        if node is None:
            raise ForkMergeItemError(
                f"fork_merge_item_unknown: {nid} is not a readable distilled outcome of {iid}"
            )
        resolved.append(
            MergeItem(
                investigation_id=iid,
                node_id=nid,
                kind=node.kind,
                text=node.text,
                text_sha256=_item_hash(node.text),
                source_document_id=node.source_document_id,
            )
        )
    return resolved


def _detect_conflicts(
    con: Any,
    *,
    owner_user_id: str,
    fork_document_id: str,
    items: list[MergeItem],
    flagged: list[tuple[str, str]],
) -> list[MergeConflict]:
    """The three-source honest ladder. Detection only — NOTHING resolves."""
    conflicts: list[MergeConflict] = []

    # (a) cross-member pairs — compose's pair model: one claim text claimed
    # by two threads. Pair each later claimant with the first, per hash.
    by_hash: dict[str, MergeItem] = {}
    for item in items:
        prev = by_hash.get(item.text_sha256)
        if (
            prev is not None
            and prev.investigation_id != item.investigation_id
        ):
            refs: tuple[tuple[str, str], ...] = (
                (prev.investigation_id, prev.node_id),
                (item.investigation_id, item.node_id),
            )
            conflicts.append(
                MergeConflict(
                    conflict_id=_conflict_id(CONFLICT_CROSS_MEMBER, refs, None),
                    kind=CONFLICT_CROSS_MEMBER,
                    item_refs=refs,
                    detail=(
                        "the same claim surfaces in two threads — carrying "
                        "both would duplicate it"
                    ),
                    anchor_id=None,
                )
            )
        else:
            by_hash.setdefault(item.text_sha256, item)

    # (b) anchor passage conflicts — the item's thread is linked to an
    # active anchor ON THE FORK and asserts a differing hash over the
    # pinned passage. No anchor → this source does not fire (honest
    # degradation).
    if highlights_table_exists(con):
        anchors = con.execute(
            "SELECT anchor_id, investigation_id, anchor_node_text_sha256 "
            "FROM anchored_highlights "
            "WHERE document_id = ? AND owner_user_id = ? AND status = 'active' "
            "AND investigation_id IS NOT NULL",
            [fork_document_id, owner_user_id],
        ).fetchall()
        for anchor_id, anchor_inv, anchor_hash in anchors:
            for item in items:
                if item.investigation_id != str(anchor_inv):
                    continue
                if item.text_sha256 == str(anchor_hash):
                    continue  # a byte-consistent restatement is no conflict
                anchor_refs: tuple[tuple[str, str], ...] = (
                    (item.investigation_id, item.node_id),
                )
                conflicts.append(
                    MergeConflict(
                        conflict_id=_conflict_id(
                            CONFLICT_ANCHOR_PASSAGE, anchor_refs, str(anchor_id)
                        ),
                        kind=CONFLICT_ANCHOR_PASSAGE,
                        item_refs=anchor_refs,
                        detail=(
                            f"this thread's pinned passage on the fork "
                            f"(anchor {anchor_id}) asserts a different text "
                            "than this item"
                        ),
                        anchor_id=str(anchor_id),
                    )
                )

    # (c) operator flags — the operator names a selected item conflicted.
    selected = {(i.investigation_id, i.node_id) for i in items}
    for iid, nid in flagged:
        if (iid, nid) not in selected:
            raise ForkMergeItemError(
                f"fork_merge_flag_unknown: {iid}/{nid} flags an item that "
                "was not selected"
            )
        flag_refs: tuple[tuple[str, str], ...] = ((iid, nid),)
        conflicts.append(
            MergeConflict(
                conflict_id=_conflict_id(CONFLICT_OPERATOR_FLAG, flag_refs, None),
                kind=CONFLICT_OPERATOR_FLAG,
                item_refs=flag_refs,
                detail="the operator flagged this item as conflicted",
                anchor_id=None,
            )
        )
    return conflicts


def _conflict_id(
    kind: str, refs: tuple[tuple[str, str], ...], anchor_id: str | None
) -> str:
    payload = json.dumps(
        {"kind": kind, "refs": sorted(refs), "anchor_id": anchor_id},
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"cf-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]}"


def _merge_id(
    *,
    fork_id: str,
    items: list[MergeItem],
    conflicts: list[MergeConflict],
) -> str:
    """The canonical identity of the merge INTENT (fork + selection +
    detected conflicts). The commit binds to it, so a merge is committed
    exactly as previewed — never a stale or edited selection."""
    payload = json.dumps(
        {
            "kind": "antiek.fork_merge.merge_id",
            "fork_id": fork_id,
            "items": sorted((i.investigation_id, i.node_id) for i in items),
            "conflicts": sorted(c.conflict_id for c in conflicts),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"forkmerge-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _commit_id(merge_id: str, resolutions: list[Resolution]) -> str:
    payload = json.dumps(
        {
            "kind": "antiek.fork_merge.commit_id",
            "merge_id": merge_id,
            "resolutions": sorted(
                (r.investigation_id, r.node_id, r.choice) for r in resolutions
            ),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"forkcommit-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _fork_row(con: Any, owner_user_id: str, fork_id: str) -> DocumentForkRow | None:
    """The lineage row, owner-scoped — the merge target is a FORK, never an
    arbitrary document."""
    return DocumentForkStore().get(con, owner_user_id=owner_user_id, fork_id=fork_id)


def _fork_body(
    con: Any, *, fork_id: str, fork_document_id: str, owner_user_id: str
) -> str:
    """Require an owned, readable target even for storage-to-storage merges.

    Neither receipt returns the fork body. Gating still matters: a merge must
    not process content the owner-read gate withholds. Metadata here supplies
    refusal diagnostics only; the guard makes the entire body decision.
    """
    row = con.execute(
        "SELECT metadata FROM documents WHERE document_id = ? AND "
        "owner_user_id = ? LIMIT 1",
        [fork_document_id, owner_user_id],
    ).fetchone()
    if row is None:
        raise KeyError(fork_id)
    metadata = row[0]
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except ValueError:
            metadata = None
    tier = licence_tier_of(metadata) if isinstance(metadata, dict) else None
    tier_name = tier.value if tier is not None else None
    try:
        result = serve_full_text_guarded(con, fork_document_id, owner=True)
    except T3BodyServeError as refused:
        raise ForkMergeBodyUnavailableError(
            fork_document_id, tier=tier_name, reason="license_tier_blocked"
        ) from refused
    except LinkBackMissingError as refused:
        raise ForkMergeBodyUnavailableError(
            fork_document_id, tier=tier_name, reason="link_back_missing"
        ) from refused
    if result.full_text is None:
        reason = (
            "body_missing"
            if result.reason in {"servable", "owner_personal_reading"}
            else result.reason
        )
        raise ForkMergeBodyUnavailableError(
            fork_document_id, tier=result.tier, reason=reason
        )
    return result.full_text


def _preview(
    con: Any,
    *,
    owner_user_id: str,
    fork_id: str,
    item_refs: list[tuple[str, str]],
    flagged: list[tuple[str, str]],
    events_dir: str | None,
) -> ForkMergePreviewReceipt:
    fork = _fork_row(con, owner_user_id, fork_id)
    if fork is None:
        raise KeyError(fork_id)
    before = _fork_body(
        con,
        fork_id=fork_id,
        fork_document_id=fork.fork_document_id,
        owner_user_id=owner_user_id,
    )
    items = _resolve_items(
        con, item_refs, owner_user_id=owner_user_id, events_dir=events_dir
    )
    conflicts = _detect_conflicts(
        con,
        owner_user_id=owner_user_id,
        fork_document_id=fork.fork_document_id,
        items=items,
        flagged=flagged,
    )
    after = _after_body(before, items)
    return ForkMergePreviewReceipt(
        status="previewed",
        merge_id=_merge_id(fork_id=fork_id, items=items, conflicts=conflicts),
        fork_id=fork.fork_id,
        fork_document_id=fork.fork_document_id,
        items=items,
        conflicts=conflicts,
        before_fork_hash=_hash_text(before),
        after_fork_hash=_hash_text(after),
        fork_bytes_before=len(before.encode("utf-8")),
        fork_bytes_after=len(after.encode("utf-8")),
        writes_performed=False,
    )


def preview_fork_merge(
    con: Any,
    *,
    owner_user_id: str,
    fork_id: str,
    item_refs: list[tuple[str, str]],
    flagged: list[tuple[str, str]] | None = None,
    events_dir: str | None = None,
) -> ForkMergePreviewReceipt:
    """Compute the would-be merge — NO writes, the receipt is the contract.
    Read-safe: any connection (the route uses connect_read). A zero-conflict
    merge previews exactly the same way: the receipt, not the conflict, is
    the contract."""
    return _preview(
        con,
        owner_user_id=owner_user_id,
        fork_id=fork_id,
        item_refs=item_refs,
        flagged=flagged or [],
        events_dir=events_dir,
    )


def commit_fork_merge(
    con: LockedConnection,
    *,
    owner_user_id: str,
    fork_id: str,
    item_refs: list[tuple[str, str]],
    flagged: list[tuple[str, str]] | None = None,
    resolutions: list[Resolution],
    expected_merge_id: str,
    expected_before_fork_hash: str,
    operator_reviewer: str | None = None,
    events_dir: str | None = None,
) -> ForkMergeCommitReceipt:
    """Commit a bound, reviewed preview into the FORK — atomically.

    Refusals, all BEFORE any write: the target body must pass the owner-read
    serve gate (ForkMergeBodyUnavailableError), the fork/selection must recompute to the
    bound preview (``fork_merge_preview_binding_mismatch``), the fork body
    must not have moved since preview (``fork_merge_stale``), and EVERY
    conflicted item must carry a resolution
    (ForkMergeUnresolvedConflictsError). The body rewrite, the ledger row,
    every resolution audit row, and the fork's anchor re-resolution land in
    ONE transaction — a refusal or a failure is no partial write."""
    _require_locked(con)
    init_fork_merge_schema(con)
    for r in resolutions:
        if r.choice not in RESOLUTION_CHOICES:
            raise ValueError(
                f"fork_merge_resolution_invalid: {r.choice!r} — expected one "
                f"of {sorted(RESOLUTION_CHOICES)}"
            )
    cid = _commit_id(expected_merge_id, resolutions)
    existing = con.execute(
        "SELECT merge_id, fork_document_id, items_json, conflicts_json, "
        "resolutions_json, "
        "before_fork_hash, after_fork_hash, fork_bytes_before, "
        "fork_bytes_after, event_id FROM fork_merge_commits "
        "WHERE commit_id = ? AND owner_user_id = ? AND fork_id = ? LIMIT 1",
        [cid, owner_user_id, fork_id],
    ).fetchone()
    if existing is not None:
        # Idempotent replay — checked BEFORE the binding/staleness gates:
        # the fork legitimately moved on after the first commit, and a
        # replay of THAT commit returns its recorded receipt, never a
        # second write. The receipt rebuilds from the ledger, so a replay
        # survives even the items' nodes changing since.
        (
            stored_merge_id,
            stored_fork_doc,
            items_json,
            conflicts_json,
            _resolutions_json,
            before_hash,
            after_hash,
            bytes_before,
            bytes_after,
            event_id,
        ) = existing
        return ForkMergeCommitReceipt(
            status="committed",
            commit_id=cid,
            merge_id=str(stored_merge_id),
            fork_id=fork_id,
            fork_document_id=str(stored_fork_doc),
            event_id=None if event_id is None else str(event_id),
            items=[
                MergeItem(
                    investigation_id=str(i["investigation_id"]),
                    node_id=str(i["node_id"]),
                    kind=str(i["kind"]),
                    text=str(i["text"]),
                    text_sha256=str(i["text_sha256"]),
                    source_document_id=i.get("source_document_id"),
                )
                for i in json.loads(items_json)
            ],
            conflicts=[
                MergeConflict(
                    conflict_id=str(c["conflict_id"]),
                    kind=str(c["kind"]),
                    item_refs=tuple(tuple(ref) for ref in c["item_refs"]),
                    detail=str(c["detail"]),
                    anchor_id=c.get("anchor_id"),
                )
                for c in json.loads(conflicts_json)
            ],
            resolutions={
                _item_ref_key(r.investigation_id, r.node_id): r.choice
                for r in resolutions
            },
            before_fork_hash=str(before_hash),
            after_fork_hash=str(after_hash),
            fork_bytes_before=int(bytes_before),
            fork_bytes_after=int(bytes_after),
            writes_performed=False,
        )

    preview = _preview(
        con,
        owner_user_id=owner_user_id,
        fork_id=fork_id,
        item_refs=item_refs,
        flagged=flagged or [],
        events_dir=events_dir,
    )
    if preview.merge_id != expected_merge_id:
        raise ValueError(
            "fork_merge_preview_binding_mismatch: the selection or conflicts "
            "changed since preview — re-preview and commit that"
        )
    if preview.before_fork_hash != expected_before_fork_hash:
        raise ValueError(
            "fork_merge_stale: the fork moved since preview — re-read and "
            "re-preview (never a silent clobber)"
        )

    conflicted: dict[tuple[str, str], list[str]] = {}
    for conflict in preview.conflicts:
        for ref in conflict.item_refs:
            conflicted.setdefault(ref, []).append(conflict.conflict_id)
    by_ref = {(r.investigation_id, r.node_id): r for r in resolutions}
    selected = {(i.investigation_id, i.node_id) for i in preview.items}
    for ref in by_ref:
        if ref not in selected:
            raise ValueError(
                f"fork_merge_resolution_unknown: {ref[0]}/{ref[1]} is not a "
                "selected item"
            )
        if ref not in conflicted:
            raise ValueError(
                f"fork_merge_resolution_unneeded: {ref[0]}/{ref[1]} is not a "
                "conflicted item — resolutions belong to conflicts"
            )
    missing = [ref for ref in conflicted if ref not in by_ref]
    if missing:
        raise ForkMergeUnresolvedConflictsError(sorted(missing))

    # accept = the item lands; keep_fork = the fork's passage stands; skip =
    accepted = [
        item
        for item in preview.items
        if (item.investigation_id, item.node_id) not in conflicted
        or by_ref[(item.investigation_id, item.node_id)].choice == "accept"
    ]
    before = _fork_body(
        con,
        fork_id=fork_id,
        fork_document_id=preview.fork_document_id,
        owner_user_id=owner_user_id,
    )
    after = _after_body(before, accepted)
    after_hash = _hash_text(after)

    event_id = log_event(
        f"read-{preview.fork_document_id}",
        FORK_MERGE_COMMITTED,
        payload={
            "fork_id": preview.fork_id,
            "fork_document_id": preview.fork_document_id,
            "merge_id": preview.merge_id,
            "commit_id": cid,
            "item_refs": sorted(
                [i.investigation_id, i.node_id] for i in preview.items
            ),
            "conflict_ids": sorted(c.conflict_id for c in preview.conflicts),
            "resolutions": sorted(
                [r.investigation_id, r.node_id, r.choice] for r in resolutions
            ),
            "before_fork_hash": preview.before_fork_hash,
            "after_fork_hash": after_hash,
            "fork_bytes_before": preview.fork_bytes_before,
            "fork_bytes_after": len(after.encode("utf-8")),
            "operator_reviewer": operator_reviewer,
        },
        role="read/fork_merge_commit",
        policy_id="read/fork_merge/commit",
        document_id=preview.fork_document_id,
        events_dir=events_dir,
    )

    with con.transaction():
        con.execute(
            "UPDATE documents SET raw_text = ? WHERE document_id = ?",
            [after, preview.fork_document_id],
        )
        con.execute(
            "INSERT INTO fork_merge_commits (commit_id, merge_id, fork_id, "
            "owner_user_id, fork_document_id, items_json, conflicts_json, "
            "resolutions_json, before_fork_body, before_fork_hash, "
            "after_fork_hash, fork_bytes_before, fork_bytes_after, "
            "operator_reviewer, event_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                cid,
                preview.merge_id,
                preview.fork_id,
                owner_user_id,
                preview.fork_document_id,
                json.dumps(
                    [
                        {
                            "investigation_id": i.investigation_id,
                            "node_id": i.node_id,
                            "kind": i.kind,
                            "text": i.text,
                            "text_sha256": i.text_sha256,
                            "source_document_id": i.source_document_id,
                        }
                        for i in preview.items
                    ],
                    sort_keys=True,
                ),
                json.dumps(
                    [
                        {
                            "conflict_id": c.conflict_id,
                            "kind": c.kind,
                            "item_refs": [list(ref) for ref in c.item_refs],
                            "detail": c.detail,
                            "anchor_id": c.anchor_id,
                        }
                        for c in preview.conflicts
                    ],
                    sort_keys=True,
                ),
                json.dumps(
                    [
                        {
                            "investigation_id": r.investigation_id,
                            "node_id": r.node_id,
                            "choice": r.choice,
                        }
                        for r in resolutions
                    ],
                    sort_keys=True,
                ),
                before,
                preview.before_fork_hash,
                after_hash,
                preview.fork_bytes_before,
                len(after.encode("utf-8")),
                operator_reviewer,
                event_id,
            ],
        )
        for r in resolutions:
            ref = (r.investigation_id, r.node_id)
            con.execute(
                "INSERT INTO fork_merge_resolutions (resolution_id, "
                "commit_id, fork_id, owner_user_id, investigation_id, "
                "node_id, choice, conflict_refs_json, operator_reviewer) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    f"res-{hashlib.sha256(json.dumps([cid, *ref], sort_keys=True).encode('utf-8')).hexdigest()[:16]}",
                    cid,
                    preview.fork_id,
                    owner_user_id,
                    r.investigation_id,
                    r.node_id,
                    r.choice,
                    json.dumps(sorted(conflicted[ref])),
                    operator_reviewer,
                ],
            )
        # The source-merge post-commit hook, retargeted: the fork's own
        # anchors re-resolve inside the same write scope — active | migrated
        # | drifted | orphaned, never silently stale.
        reanchor_document(con, document_id=preview.fork_document_id, events_dir=events_dir)

    return ForkMergeCommitReceipt(
        status="committed",
        commit_id=cid,
        merge_id=preview.merge_id,
        fork_id=preview.fork_id,
        fork_document_id=preview.fork_document_id,
        event_id=event_id,
        items=preview.items,
        conflicts=preview.conflicts,
        resolutions={
            _item_ref_key(r.investigation_id, r.node_id): r.choice
            for r in resolutions
        },
        before_fork_hash=preview.before_fork_hash,
        after_fork_hash=after_hash,
        fork_bytes_before=preview.fork_bytes_before,
        fork_bytes_after=len(after.encode("utf-8")),
        writes_performed=True,
    )
