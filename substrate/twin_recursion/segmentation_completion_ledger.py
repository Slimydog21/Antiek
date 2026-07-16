"""Durable exact bindings for signed segment and parent aggregate completions."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from substrate.research_artifact.schema import ResearchArtifactBody
from substrate.twin_note_taker import (
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinProposal,
    proposal_receipt_hash,
)

from .segmentation import TwinSegmentationManifest, verify_segmentation_manifest
from .segmentation_completion import (
    PAID_COMPLETION_SCHEMA,
    AggregateCompletionReceipt,
    AggregateCompletionReceiptV2,
    SegmentationCompletionError,
    SegmentCompletionReceipt,
    SegmentCompletionReceiptV2,
    canonical_json,
    completion_digest,
    proposal_hash,
    sha256,
    verify_receipt,
)
from .segmentation_ledger import TwinSegmentationLedger

SCHEMA_VERSION = "twin-segmentation-completion-v1"


class SegmentationCompletionIntegrityError(RuntimeError):
    """Persisted completion authority is missing, changed, or contradictory."""


@dataclass(frozen=True)
class CompletionSnapshot:
    account_id: str
    asset_id: str
    parent_source_hash: str
    segment_count: int
    completed_segments: int
    parent_binding_id: str | None
    body_json: str | None

    @property
    def parent_ready(self) -> bool:
        return self.parent_binding_id is not None


TABLES = {
    "completion_meta": """CREATE TABLE completion_meta (
      singleton INTEGER PRIMARY KEY CHECK(singleton=1), schema_version TEXT NOT NULL,
      schema_digest TEXT NOT NULL)""",
    "completion_manifests": """CREATE TABLE completion_manifests (
      account_id TEXT NOT NULL, asset_id TEXT NOT NULL, parent_source_hash TEXT NOT NULL,
      manifest_hash TEXT NOT NULL, manifest_json TEXT NOT NULL,
      PRIMARY KEY(account_id,asset_id,parent_source_hash))""",
    "segment_completion_bindings": """CREATE TABLE segment_completion_bindings (
      account_id TEXT NOT NULL, asset_id TEXT NOT NULL, parent_source_hash TEXT NOT NULL,
      segment_index INTEGER NOT NULL, binding_id TEXT NOT NULL UNIQUE,
      completion_digest TEXT NOT NULL, proposal_json TEXT NOT NULL, receipt_json TEXT NOT NULL,
      PRIMARY KEY(account_id,asset_id,parent_source_hash,segment_index),
      FOREIGN KEY(account_id,asset_id,parent_source_hash)
        REFERENCES completion_manifests(account_id,asset_id,parent_source_hash))""",
    "aggregate_completion_bindings": """CREATE TABLE aggregate_completion_bindings (
      binding_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, asset_id TEXT NOT NULL,
      parent_source_hash TEXT NOT NULL, ordered_segment_bindings_hash TEXT NOT NULL,
      completion_digest TEXT NOT NULL, proposal_json TEXT NOT NULL, receipt_json TEXT NOT NULL,
      body_json TEXT NOT NULL, body_hash TEXT NOT NULL,
      UNIQUE(account_id,asset_id,parent_source_hash),
      FOREIGN KEY(account_id,asset_id,parent_source_hash)
        REFERENCES completion_manifests(account_id,asset_id,parent_source_hash))""",
}

TRIGGERS = {
    name
    + "_immutable": f"CREATE TRIGGER {name}_immutable BEFORE UPDATE ON {table} BEGIN SELECT RAISE(ABORT,'immutable completion authority'); END"
    for name, table in {
        "completion_meta": "completion_meta",
        "completion_manifest": "completion_manifests",
        "segment_completion": "segment_completion_bindings",
        "aggregate_completion": "aggregate_completion_bindings",
    }.items()
}
TRIGGERS.update(
    {
        name
        + "_no_delete": f"CREATE TRIGGER {name}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT,'durable completion authority'); END"
        for name, table in {
            "completion_meta": "completion_meta",
            "completion_manifest": "completion_manifests",
            "segment_completion": "segment_completion_bindings",
            "aggregate_completion": "aggregate_completion_bindings",
        }.items()
    }
)


def _schema_digest() -> str:
    return sha256(canonical_json({**TABLES, **TRIGGERS}))


def _normalize_sql(value: str) -> str:
    return " ".join(value.split()).lower()


def _segment_asset(
    asset: AssetContent, manifest: TwinSegmentationManifest, index: int
) -> AssetContent:
    segment = manifest.segments[index]
    return AssetContent(
        asset_id=f"{asset.asset_id}#segment-{index}",
        title=f"{asset.title} (segment {index + 1} of {len(manifest.segments)})",
        content_text=asset.content_text[segment.start_char : segment.end_char],
        content_class=asset.content_class,
        source_event_ids=asset.source_event_ids,
    )


def _aggregate_source(manifest: TwinSegmentationManifest, ordered_hash: str) -> AssetContent:
    return AssetContent(
        asset_id=manifest.asset_id,
        title="Aggregate twin source",
        content_text=f"manifest:{manifest.manifest_hash}\nordered-segment-bindings:{ordered_hash}",
        content_class="segmented_aggregate",
        source_event_ids=("evt-segment-aggregate-" + manifest.manifest_hash[:32],),
    )


def _body(asset_id: str, proposal: TwinProposal) -> ResearchArtifactBody:
    notes = [
        "Authority: advisory_twin_v1. Proposals are ungrounded until evidence-backed promotion.",
        f"Source asset: {asset_id}",
        *(
            f"Proposed insight: {item.text.strip()}"
            for item in proposal.insights
            if item.text.strip()
        ),
        *(
            f"Proposed question: {item.text.strip()}"
            for item in proposal.questions
            if item.text.strip()
        ),
    ]
    if proposal.synthesis_excerpt.strip():
        notes.append(f"Proposed synthesis: {proposal.synthesis_excerpt.strip()}")
    return ResearchArtifactBody(
        investigation_id=f"twin-{asset_id}",
        problem_question=f"Advisory twin notes: {asset_id}",
        synthesis_withheld=True,
        agent_notes=notes,
    )


def _proposal_from_json(value: str) -> TwinProposal:
    try:
        raw = json.loads(value)
        proposal = TwinProposal(
            tuple(ProposedInsight(**item) for item in raw["insights"]),
            tuple(ProposedQuestion(**item) for item in raw["questions"]),
            raw["synthesis_excerpt"],
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SegmentationCompletionIntegrityError("persisted proposal is malformed") from exc
    if canonical_json(asdict(proposal)) != value:
        raise SegmentationCompletionIntegrityError("persisted proposal is not canonical")
    return proposal


def _receipt_from_json(
    value: str,
    receipt_type: type[SegmentCompletionReceipt] | type[AggregateCompletionReceipt],
) -> SegmentCompletionReceipt | AggregateCompletionReceipt | SegmentCompletionReceiptV2 | AggregateCompletionReceiptV2:
    try:
        raw = json.loads(value)
        actual_type = receipt_type
        if raw.get("schema") == PAID_COMPLETION_SCHEMA:
            actual_type = (
                SegmentCompletionReceiptV2
                if receipt_type is SegmentCompletionReceipt
                else AggregateCompletionReceiptV2
            )
        receipt = actual_type(**raw)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SegmentationCompletionIntegrityError("persisted receipt is malformed") from exc
    if canonical_json(asdict(receipt)) != value:
        raise SegmentationCompletionIntegrityError("persisted receipt is not canonical")
    verify_receipt(receipt, now_unix=0, require_configured_key=False)
    return receipt


class SegmentationCompletionLedger:
    def __init__(self, path: str | Path, *, timeout: float = 30.0) -> None:
        self.path = str(path)
        self.timeout = timeout
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=self.timeout)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        return con

    def _initialize(self) -> None:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            exists = con.execute(
                "SELECT 1 FROM sqlite_master WHERE name='completion_meta'"
            ).fetchone()
            if exists is None:
                for statement in TABLES.values():
                    con.execute(statement)
                for statement in TRIGGERS.values():
                    con.execute(statement)
                con.execute(
                    "INSERT INTO completion_meta VALUES(1,?,?)", (SCHEMA_VERSION, _schema_digest())
                )
            self._verify_schema(con)

    def _verify_schema(self, con: sqlite3.Connection) -> None:
        meta = con.execute("SELECT schema_version,schema_digest FROM completion_meta").fetchone()
        if meta is None or tuple(meta) != (SCHEMA_VERSION, _schema_digest()):
            raise SegmentationCompletionIntegrityError("completion schema metadata changed")
        expected = {**TABLES, **TRIGGERS}
        rows = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
        ).fetchall()
        actual = {str(row["name"]): _normalize_sql(str(row["sql"])) for row in rows}
        if set(actual) != set(expected):
            raise SegmentationCompletionIntegrityError("completion schema object set changed")
        for name, statement in expected.items():
            if actual.get(name) != _normalize_sql(statement):
                raise SegmentationCompletionIntegrityError(
                    f"completion schema object changed: {name}"
                )

    def register_manifest(
        self,
        manifest: TwinSegmentationManifest,
        *,
        asset: AssetContent,
        registry: TwinSegmentationLedger,
    ) -> CompletionSnapshot:
        verify_segmentation_manifest(manifest, account_id=manifest.account_id, asset=asset)
        registered = registry.get(
            manifest.account_id, manifest.asset_id, manifest.parent_source_hash
        )
        if registered.manifest_hash != manifest.manifest_hash:
            raise SegmentationCompletionIntegrityError(
                "segmentation registry conflicts with manifest"
            )
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify_schema(con)
            key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
            row = con.execute(
                "SELECT manifest_json FROM completion_manifests WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                key,
            ).fetchone()
            if row is None:
                con.execute(
                    "INSERT INTO completion_manifests VALUES(?,?,?,?,?)",
                    (*key, manifest.manifest_hash, manifest.to_json()),
                )
            elif row["manifest_json"] != manifest.to_json():
                raise SegmentationCompletionIntegrityError("completion manifest substitution")
        return self.get(*key, asset=asset, registry=registry)

    def apply_segment(
        self,
        manifest: TwinSegmentationManifest,
        *,
        asset: AssetContent,
        segment_index: int,
        proposal: TwinProposal,
        receipt: SegmentCompletionReceipt | SegmentCompletionReceiptV2,
        registry: TwinSegmentationLedger,
    ) -> CompletionSnapshot:
        verify_segmentation_manifest(manifest, account_id=manifest.account_id, asset=asset)
        if segment_index < 0 or segment_index >= len(manifest.segments):
            raise SegmentationCompletionError("segment index is outside the manifest")
        segment = manifest.segments[segment_index]
        segment_asset = _segment_asset(asset, manifest, segment_index)
        proposal_receipt_hash(segment_asset, proposal)
        expected_proposal_hash = proposal_hash(proposal)
        expected = (
            manifest.account_id,
            manifest.manifest_hash,
            manifest.parent_source_hash,
            segment_index,
            segment.start_char,
            segment.end_char,
            segment.content_sha256,
            expected_proposal_hash,
        )
        actual = (
            receipt.account_id,
            receipt.manifest_hash,
            receipt.parent_source_hash,
            receipt.segment_index,
            receipt.start_char,
            receipt.end_char,
            receipt.content_sha256,
            receipt.proposal_hash,
        )
        digest = completion_digest(proposal, receipt)
        key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify_schema(con)
            self._require_manifest(con, manifest)
            row = con.execute(
                "SELECT completion_digest FROM segment_completion_bindings WHERE account_id=? AND asset_id=? AND parent_source_hash=? AND segment_index=?",
                (*key, segment_index),
            ).fetchone()
            if row is not None:
                verify_receipt(receipt, now_unix=0, require_configured_key=False)
                if row["completion_digest"] != digest:
                    raise SegmentationCompletionIntegrityError("segment completion substitution")
            else:
                verify_receipt(receipt)
                if actual != expected:
                    raise SegmentationCompletionError(
                        "segment receipt conflicts with exact obligation"
                    )
                binding_id = "segment_binding_" + sha256(
                    canonical_json([*key, segment_index, digest])
                )
                con.execute(
                    "INSERT INTO segment_completion_bindings VALUES(?,?,?,?,?,?,?,?)",
                    (
                        *key,
                        segment_index,
                        binding_id,
                        digest,
                        canonical_json(asdict(proposal)),
                        canonical_json(asdict(receipt)),
                    ),
                )
        return self.get(*key, asset=asset, registry=registry)

    def apply_aggregate(
        self,
        manifest: TwinSegmentationManifest,
        *,
        asset: AssetContent,
        proposal: TwinProposal,
        receipt: AggregateCompletionReceipt | AggregateCompletionReceiptV2,
        registry: TwinSegmentationLedger,
    ) -> CompletionSnapshot:
        verify_segmentation_manifest(manifest, account_id=manifest.account_id, asset=asset)
        key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            self._verify_schema(con)
            self._require_manifest(con, manifest)
            rows = con.execute(
                "SELECT segment_index,binding_id,completion_digest,receipt_json "
                "FROM segment_completion_bindings WHERE account_id=? AND asset_id=? "
                "AND parent_source_hash=? ORDER BY segment_index",
                key,
            ).fetchall()
            if [int(row["segment_index"]) for row in rows] != list(range(len(manifest.segments))):
                raise SegmentationCompletionError("all ordered segment completions are required")
            ordered_bindings = [
                (row["segment_index"], row["binding_id"], row["completion_digest"])
                for row in rows
            ]
            if isinstance(receipt, AggregateCompletionReceiptV2):
                for row in rows:
                    segment_receipt = _receipt_from_json(
                        str(row["receipt_json"]), SegmentCompletionReceipt
                    )
                    if not isinstance(segment_receipt, SegmentCompletionReceiptV2):
                        raise SegmentationCompletionError(
                            "paid aggregate requires paid segment dispatch proof"
                        )
                    verify_receipt(
                        segment_receipt, now_unix=0, require_configured_key=False
                    )
            ordered_hash = sha256(canonical_json(ordered_bindings))
            aggregate_source = _aggregate_source(manifest, ordered_hash)
            proposal_receipt_hash(aggregate_source, proposal)
            expected_proposal_hash = proposal_hash(proposal)
            digest = completion_digest(proposal, receipt)
            existing = con.execute(
                "SELECT completion_digest FROM aggregate_completion_bindings WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                key,
            ).fetchone()
            if existing is not None:
                verify_receipt(receipt, now_unix=0, require_configured_key=False)
                if existing["completion_digest"] != digest:
                    raise SegmentationCompletionIntegrityError("aggregate completion substitution")
            else:
                verify_receipt(receipt)
                if (
                    receipt.account_id,
                    receipt.manifest_hash,
                    receipt.parent_source_hash,
                    receipt.ordered_segment_bindings_hash,
                    receipt.proposal_hash,
                ) != (
                    manifest.account_id,
                    manifest.manifest_hash,
                    manifest.parent_source_hash,
                    ordered_hash,
                    expected_proposal_hash,
                ):
                    raise SegmentationCompletionError(
                        "aggregate receipt conflicts with complete ordered set"
                    )
                body_json = canonical_json(_body(asset.asset_id, proposal).model_dump(mode="json"))
                binding_id = "aggregate_binding_" + sha256(
                    canonical_json([*key, ordered_hash, digest])
                )
                con.execute(
                    "INSERT INTO aggregate_completion_bindings VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        binding_id,
                        *key,
                        ordered_hash,
                        digest,
                        canonical_json(asdict(proposal)),
                        canonical_json(asdict(receipt)),
                        body_json,
                        sha256(body_json),
                    ),
                )
        return self.get(*key, asset=asset, registry=registry)

    def aggregate_inputs(
        self, manifest: TwinSegmentationManifest
    ) -> tuple[str, tuple[TwinProposal, ...]]:
        """Return the exact ordered bindings and proposals for paid aggregation."""
        with self._connect() as con:
            con.execute("BEGIN")
            self._verify_schema(con)
            self._require_manifest(con, manifest)
            rows = con.execute(
                "SELECT segment_index,binding_id,completion_digest,proposal_json,receipt_json "
                "FROM segment_completion_bindings WHERE account_id=? AND asset_id=? "
                "AND parent_source_hash=? ORDER BY segment_index",
                (manifest.account_id, manifest.asset_id, manifest.parent_source_hash),
            ).fetchall()
            if [int(row["segment_index"]) for row in rows] != list(range(len(manifest.segments))):
                raise SegmentationCompletionError("all ordered segment completions are required")
            ordered_hash = sha256(
                canonical_json(
                    [
                        (row["segment_index"], row["binding_id"], row["completion_digest"])
                        for row in rows
                    ]
                )
            )
            proposals: list[TwinProposal] = []
            for row in rows:
                receipt = _receipt_from_json(
                    str(row["receipt_json"]), SegmentCompletionReceipt
                )
                if not isinstance(receipt, SegmentCompletionReceiptV2):
                    raise SegmentationCompletionError(
                        "aggregate inputs require paid segment dispatch proof"
                    )
                verify_receipt(receipt, now_unix=0, require_configured_key=False)
                proposals.append(_proposal_from_json(str(row["proposal_json"])))
            return ordered_hash, tuple(proposals)

    def segment_is_complete(
        self,
        manifest: TwinSegmentationManifest,
        segment_index: int,
        *,
        asset: AssetContent,
        registry: TwinSegmentationLedger,
    ) -> bool:
        self.get(
            manifest.account_id, manifest.asset_id, manifest.parent_source_hash,
            asset=asset, registry=registry,
        )
        with self._connect() as con:
            con.execute("BEGIN")
            self._verify_schema(con)
            return con.execute(
                "SELECT 1 FROM segment_completion_bindings WHERE account_id=? "
                "AND asset_id=? AND parent_source_hash=? AND segment_index=?",
                (
                    manifest.account_id, manifest.asset_id,
                    manifest.parent_source_hash, segment_index,
                ),
            ).fetchone() is not None

    def paid_segment_completion(
        self,
        manifest: TwinSegmentationManifest,
        segment_index: int,
        *,
        asset: AssetContent,
        registry: TwinSegmentationLedger,
    ) -> tuple[TwinProposal, SegmentCompletionReceiptV2] | None:
        if not self.segment_is_complete(
            manifest, segment_index, asset=asset, registry=registry
        ):
            return None
        with self._connect() as con:
            con.execute("BEGIN")
            self._verify_schema(con)
            row = con.execute(
                "SELECT proposal_json,receipt_json FROM segment_completion_bindings "
                "WHERE account_id=? AND asset_id=? AND parent_source_hash=? "
                "AND segment_index=?",
                (
                    manifest.account_id, manifest.asset_id,
                    manifest.parent_source_hash, segment_index,
                ),
            ).fetchone()
            assert row is not None
            proposal = _proposal_from_json(str(row["proposal_json"]))
            receipt = _receipt_from_json(
                str(row["receipt_json"]), SegmentCompletionReceipt
            )
            if not isinstance(receipt, SegmentCompletionReceiptV2):
                raise SegmentationCompletionError(
                    "legacy completion has no paid dispatch proof"
                )
            verify_receipt(receipt, now_unix=0, require_configured_key=False)
            return proposal, receipt

    def paid_aggregate_completion(
        self,
        manifest: TwinSegmentationManifest,
        *,
        asset: AssetContent,
        registry: TwinSegmentationLedger,
    ) -> tuple[TwinProposal, AggregateCompletionReceiptV2] | None:
        snapshot = self.get(
            manifest.account_id, manifest.asset_id, manifest.parent_source_hash,
            asset=asset, registry=registry,
        )
        if not snapshot.parent_ready:
            return None
        with self._connect() as con:
            con.execute("BEGIN")
            self._verify_schema(con)
            row = con.execute(
                "SELECT proposal_json,receipt_json FROM aggregate_completion_bindings "
                "WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                (manifest.account_id, manifest.asset_id, manifest.parent_source_hash),
            ).fetchone()
            assert row is not None
            proposal = _proposal_from_json(str(row["proposal_json"]))
            receipt = _receipt_from_json(
                str(row["receipt_json"]), AggregateCompletionReceipt
            )
            if not isinstance(receipt, AggregateCompletionReceiptV2):
                raise SegmentationCompletionError(
                    "legacy completion has no paid dispatch proof"
                )
            verify_receipt(receipt, now_unix=0, require_configured_key=False)
            return proposal, receipt

    def _require_manifest(
        self, con: sqlite3.Connection, manifest: TwinSegmentationManifest
    ) -> None:
        row = con.execute(
            "SELECT manifest_hash,manifest_json FROM completion_manifests WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
            (manifest.account_id, manifest.asset_id, manifest.parent_source_hash),
        ).fetchone()
        if row is None or tuple(row) != (manifest.manifest_hash, manifest.to_json()):
            raise SegmentationCompletionIntegrityError("completion manifest is absent or changed")

    def get(
        self,
        account_id: str,
        asset_id: str,
        parent_source_hash: str,
        *,
        asset: AssetContent,
        registry: TwinSegmentationLedger,
    ) -> CompletionSnapshot:
        with self._connect() as con:
            con.execute("BEGIN")
            self._verify_schema(con)
            key = (account_id, asset_id, parent_source_hash)
            manifest = con.execute(
                "SELECT manifest_json FROM completion_manifests WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                key,
            ).fetchone()
            if manifest is None:
                raise KeyError(key)
            manifest_value = TwinSegmentationManifest.from_json(str(manifest["manifest_json"]))
            verify_segmentation_manifest(manifest_value, account_id=account_id, asset=asset)
            registered = registry.get(account_id, asset_id, parent_source_hash)
            if registered.manifest_hash != manifest_value.manifest_hash:
                raise SegmentationCompletionIntegrityError(
                    "current segmentation registry conflicts with completion authority"
                )
            segment_rows = con.execute(
                "SELECT * FROM segment_completion_bindings WHERE account_id=? AND asset_id=? "
                "AND parent_source_hash=? ORDER BY segment_index",
                key,
            ).fetchall()
            self._verify_segment_rows(manifest_value, segment_rows)
            expected_count = len(manifest_value.segments)
            count = len(segment_rows)
            aggregate = con.execute(
                "SELECT * FROM aggregate_completion_bindings WHERE account_id=? AND asset_id=? AND parent_source_hash=?",
                key,
            ).fetchone()
            if aggregate is not None:
                self._verify_aggregate_row(manifest_value, segment_rows, aggregate)
            return CompletionSnapshot(
                account_id,
                asset_id,
                parent_source_hash,
                expected_count,
                count,
                None if aggregate is None else str(aggregate["binding_id"]),
                None if aggregate is None else str(aggregate["body_json"]),
            )

    def _verify_segment_rows(
        self, manifest: TwinSegmentationManifest, rows: list[sqlite3.Row]
    ) -> None:
        seen: set[int] = set()
        key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
        for row in rows:
            index = int(row["segment_index"])
            if index in seen or index < 0 or index >= len(manifest.segments):
                raise SegmentationCompletionIntegrityError("persisted segment index is invalid")
            seen.add(index)
            proposal = _proposal_from_json(str(row["proposal_json"]))
            receipt = _receipt_from_json(str(row["receipt_json"]), SegmentCompletionReceipt)
            assert isinstance(receipt, (SegmentCompletionReceipt, SegmentCompletionReceiptV2))
            verify_receipt(receipt, now_unix=0, require_configured_key=False)
            digest = completion_digest(proposal, receipt)
            segment = manifest.segments[index]
            expected_binding = "segment_binding_" + sha256(canonical_json([*key, index, digest]))
            if (
                row["completion_digest"] != digest
                or row["binding_id"] != expected_binding
                or receipt.account_id != manifest.account_id
                or receipt.manifest_hash != manifest.manifest_hash
                or receipt.parent_source_hash != manifest.parent_source_hash
                or receipt.segment_index != index
                or receipt.start_char != segment.start_char
                or receipt.end_char != segment.end_char
                or receipt.content_sha256 != segment.content_sha256
                or receipt.proposal_hash != proposal_hash(proposal)
            ):
                raise SegmentationCompletionIntegrityError("persisted segment binding conflicts")

    def _verify_aggregate_row(
        self,
        manifest: TwinSegmentationManifest,
        segment_rows: list[sqlite3.Row],
        row: sqlite3.Row,
    ) -> None:
        if [int(item["segment_index"]) for item in segment_rows] != list(
            range(len(manifest.segments))
        ):
            raise SegmentationCompletionIntegrityError("aggregate binding lacks ordered segments")
        ordered_hash = sha256(
            canonical_json(
                [
                    (item["segment_index"], item["binding_id"], item["completion_digest"])
                    for item in segment_rows
                ]
            )
        )
        proposal = _proposal_from_json(str(row["proposal_json"]))
        receipt = _receipt_from_json(str(row["receipt_json"]), AggregateCompletionReceipt)
        assert isinstance(receipt, (AggregateCompletionReceipt, AggregateCompletionReceiptV2))
        verify_receipt(receipt, now_unix=0, require_configured_key=False)
        digest = completion_digest(proposal, receipt)
        key = (manifest.account_id, manifest.asset_id, manifest.parent_source_hash)
        expected_binding = "aggregate_binding_" + sha256(
            canonical_json([*key, ordered_hash, digest])
        )
        if (
            row["binding_id"] != expected_binding
            or row["ordered_segment_bindings_hash"] != ordered_hash
            or row["completion_digest"] != digest
            or receipt.account_id != manifest.account_id
            or receipt.manifest_hash != manifest.manifest_hash
            or receipt.parent_source_hash != manifest.parent_source_hash
            or receipt.ordered_segment_bindings_hash != ordered_hash
            or receipt.proposal_hash != proposal_hash(proposal)
            or sha256(str(row["body_json"])) != row["body_hash"]
            or str(row["body_json"])
            != canonical_json(_body(manifest.asset_id, proposal).model_dump(mode="json"))
        ):
            raise SegmentationCompletionIntegrityError("persisted aggregate binding conflicts")


__all__ = [
    "CompletionSnapshot",
    "SegmentationCompletionIntegrityError",
    "SegmentationCompletionLedger",
]
