"""Reference-only persisted lineage for the HTML-native document workflow.

The registry deliberately stores identities, never document, research, note, or
output bodies.  HTML projections and document regions are authoritative in
their existing stores; the other references name entities owned by their
respective systems.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal

from runtime.db_lock import connect_read, connect_write
from substrate.event_log.events import trajectory
from substrate.reading.projection.store import ProjectionStore
from substrate.reading.regions import RegionStore

NodeKind = Literal[
    "source_asset",
    "html_projection",
    "document_region",
    "investigation",
    "twin_note",
    "notebook",
    "write_output",
]
TerminalKind = Literal["notebook", "write_output"]

REQUIRED_HOPS: Final[tuple[tuple[str, str], ...]] = (
    ("source_asset", "html_projection"),
    ("html_projection", "document_region"),
    ("document_region", "investigation"),
    ("investigation", "twin_note"),
    ("twin_note", "notebook/write_output"),
)
METADATA_KEYS: Final[frozenset[str]] = frozenset(
    {"actor_id", "created_at", "reason_code", "workflow_version"}
)
_BODY_KEY = re.compile(
    r"(?:body|content|text|html|markdown|source|highlight|research|note|output|prompt|response)",
    re.IGNORECASE,
)
_MAX_ID = 512
_MAX_METADATA_VALUE = 256
_MAX_METADATA_BYTES = 1024


class LineageConflict(ValueError):
    """A replay disagrees with already persisted identity or structure."""


class LineageValidationError(ValueError):
    """A request is unsafe, malformed, or lacks an authoritative entity."""


@dataclass(frozen=True)
class WorkflowLineage:
    lineage_id: str
    source_asset_id: str
    projection_id: str
    document_id: str
    region_id: str
    investigation_id: str
    twin_note_id: str
    terminal_kind: TerminalKind
    terminal_output_id: str
    metadata: Mapping[str, str]
    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    complete: bool
    missing_hops: tuple[str, ...] = ()

    @property
    def representation(self) -> Literal["html"]:
        return "html"


@dataclass(frozen=True)
class IncompleteWorkflowLineage:
    source_asset_id: str | None
    projection_id: str | None
    document_id: str | None
    region_id: str | None
    complete: Literal[False] = False
    missing_hops: tuple[str, ...] = tuple(f"{a}->{b}" for a, b in REQUIRED_HOPS)

    @property
    def representation(self) -> Literal["html"]:
        return "html"


class WorkflowLineageRegistry:
    """Single-writer DuckDB registry with read-only reopen-safe queries."""

    def __init__(self, db_path: str | Path, *, events_dir: str | Path) -> None:
        self._db_path = str(db_path)
        self._events_dir = str(events_dir)

    def register(
        self,
        *,
        source_asset_id: str,
        projection_id: str,
        document_id: str,
        region_id: str,
        investigation_id: str,
        twin_note_id: str,
        terminal_kind: TerminalKind,
        terminal_output_id: str,
        metadata: Mapping[str, str] | None = None,
    ) -> WorkflowLineage:
        values = {
            "source_asset_id": source_asset_id,
            "projection_id": projection_id,
            "document_id": document_id,
            "region_id": region_id,
            "investigation_id": investigation_id,
            "twin_note_id": twin_note_id,
            "terminal_output_id": terminal_output_id,
        }
        for name, value in values.items():
            _validate_id(name, value)
        if terminal_kind not in {"notebook", "write_output"}:
            raise LineageValidationError("terminal_kind must be notebook or write_output")
        safe_metadata = _validate_metadata(metadata or {})
        with connect_read(self._db_path) as con:
            _validate_authorities(con, source_asset_id, projection_id, document_id, region_id)
        _validate_trajectory(
            self._events_dir, investigation_id, document_id, region_id, twin_note_id
        )
        lineage_id = derive_lineage_id(
            source_asset_id,
            projection_id,
            region_id,
            investigation_id,
            twin_note_id,
            terminal_kind,
            terminal_output_id,
        )
        kinds: tuple[NodeKind, ...] = (
            "source_asset",
            "html_projection",
            "document_region",
            "investigation",
            "twin_note",
            terminal_kind,
        )
        references = (
            source_asset_id,
            projection_id,
            region_id,
            investigation_id,
            twin_note_id,
            terminal_output_id,
        )
        node_ids = tuple(
            derive_node_id(kind, reference)
            for kind, reference in zip(kinds, references, strict=True)
        )
        edge_ids = tuple(
            derive_edge_id(
                lineage_id,
                position,
                kinds[position],
                node_ids[position],
                kinds[position + 1],
                node_ids[position + 1],
            )
            for position in range(5)
        )
        record = WorkflowLineage(
            lineage_id,
            source_asset_id,
            projection_id,
            document_id,
            region_id,
            investigation_id,
            twin_note_id,
            terminal_kind,
            terminal_output_id,
            safe_metadata,
            node_ids,
            edge_ids,
            True,
        )

        with connect_write(self._db_path, purpose="reading/workflow_lineage.register") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                _ensure_tables(con)
                _validate_authorities(con, source_asset_id, projection_id, document_id, region_id)
                _validate_terminal(
                    con,
                    terminal_kind,
                    terminal_output_id,
                    investigation_id,
                    document_id,
                    region_id,
                    twin_note_id,
                )
                payload = _record_json(record)
                rows = con.execute(
                    "SELECT record_json FROM workflow_lineages "
                    "WHERE lineage_id = ? OR (terminal_kind = ? AND terminal_output_id = ?)",
                    [lineage_id, terminal_kind, terminal_output_id],
                ).fetchall()
                if rows:
                    if len(rows) == 1 and str(rows[0][0]) == payload:
                        con.execute("COMMIT")
                        return record
                    raise LineageConflict(
                        "lineage identity or terminal output conflicts with stored record"
                    )
                con.execute(
                    "INSERT INTO workflow_lineages VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        lineage_id,
                        source_asset_id,
                        projection_id,
                        document_id,
                        region_id,
                        investigation_id,
                        twin_note_id,
                        terminal_kind,
                        terminal_output_id,
                        payload,
                    ],
                )
                for position, (node_id, kind, reference) in enumerate(
                    zip(node_ids, kinds, references, strict=True)
                ):
                    con.execute(
                        "INSERT INTO workflow_lineage_nodes VALUES (?, ?, ?, ?, ?)",
                        [lineage_id, position, node_id, kind, reference],
                    )
                for position, edge_id in enumerate(edge_ids):
                    con.execute(
                        "INSERT INTO workflow_lineage_edges VALUES (?, ?, ?, ?, ?, ?, ?)",
                        [
                            lineage_id,
                            position,
                            edge_id,
                            node_ids[position],
                            node_ids[position + 1],
                            kinds[position],
                            kinds[position + 1],
                        ],
                    )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return record

    def lookup(
        self,
        *,
        source_asset_id: str | None = None,
        document_id: str | None = None,
        terminal_output_id: str | None = None,
    ) -> tuple[WorkflowLineage | IncompleteWorkflowLineage, ...]:
        supplied = [
            source_asset_id is not None,
            document_id is not None,
            terminal_output_id is not None,
        ]
        if sum(supplied) != 1:
            raise LineageValidationError("supply exactly one lookup identity")
        column, value = next(
            (name, candidate)
            for name, candidate in (
                ("source_asset_id", source_asset_id),
                ("document_id", document_id),
                ("terminal_output_id", terminal_output_id),
            )
            if candidate is not None
        )
        assert value is not None
        _validate_id(column, value)
        try:
            con = connect_read(self._db_path)
        except Exception:
            return ()
        try:
            if not _table_exists(con, "workflow_lineages"):
                return _authoritative_incomplete(con, column, value)
            rows = con.execute(
                f"SELECT lineage_id, source_asset_id, projection_id, document_id, "
                f"region_id, investigation_id, twin_note_id, terminal_kind, "
                f"terminal_output_id, record_json FROM workflow_lineages "
                f"WHERE {column} = ? ORDER BY lineage_id",
                [value],
            ).fetchall()
            results = tuple(_load_and_check(con, row, self._events_dir) for row in rows)
            if results:
                return results
            return _authoritative_incomplete(con, column, value)
        finally:
            con.close()

    def by_source_asset(self, source_asset_id: str):
        return self.lookup(source_asset_id=source_asset_id)

    def by_document(self, document_id: str):
        return self.lookup(document_id=document_id)

    def by_terminal_output(self, terminal_output_id: str):
        return self.lookup(terminal_output_id=terminal_output_id)


def derive_node_id(kind: NodeKind, reference_id: str) -> str:
    material = f"{kind}\0{reference_id}"
    return f"wlnode-{hashlib.sha256(material.encode()).hexdigest()}"


def derive_lineage_id(
    source_asset_id: str,
    projection_id: str,
    region_id: str,
    investigation_id: str,
    twin_note_id: str,
    terminal_kind: TerminalKind,
    terminal_output_id: str,
) -> str:
    material = "\0".join(
        (
            source_asset_id,
            projection_id,
            region_id,
            investigation_id,
            twin_note_id,
            terminal_kind,
            terminal_output_id,
        )
    )
    return f"wflow-{hashlib.sha256(material.encode()).hexdigest()}"


def derive_edge_id(
    lineage_id: str,
    position: int,
    from_kind: str,
    from_id: str,
    to_kind: str,
    to_id: str,
) -> str:
    material = f"{lineage_id}\0{position}\0{from_kind}\0{from_id}\0{to_kind}\0{to_id}"
    return f"wledge-{hashlib.sha256(material.encode()).hexdigest()}"


def _ensure_tables(con: object) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS workflow_lineages (
            lineage_id TEXT PRIMARY KEY, source_asset_id TEXT NOT NULL,
            projection_id TEXT NOT NULL, document_id TEXT NOT NULL, region_id TEXT NOT NULL,
            investigation_id TEXT NOT NULL, twin_note_id TEXT NOT NULL,
            terminal_kind TEXT NOT NULL, terminal_output_id TEXT NOT NULL,
            record_json JSON NOT NULL, UNIQUE(terminal_kind, terminal_output_id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS workflow_lineage_nodes (
            lineage_id TEXT NOT NULL, position INTEGER NOT NULL, node_id TEXT NOT NULL,
            node_kind TEXT NOT NULL, reference_id TEXT NOT NULL,
            PRIMARY KEY(lineage_id, position), UNIQUE(lineage_id, node_id)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS workflow_lineage_edges (
            lineage_id TEXT NOT NULL, position INTEGER NOT NULL, edge_id TEXT NOT NULL UNIQUE,
            from_node_id TEXT NOT NULL, to_node_id TEXT NOT NULL,
            from_kind TEXT NOT NULL, to_kind TEXT NOT NULL,
            PRIMARY KEY(lineage_id, position)
        )
    """)


def _validate_authorities(
    con: object, source: str, projection_id: str, document: str, region_id: str
) -> None:
    try:
        projection = ProjectionStore(con).load(projection_id)
    except KeyError as exc:
        raise LineageValidationError("authoritative HTML projection does not exist") from exc
    if projection.status != "ready":
        raise LineageValidationError("authoritative HTML projection is not ready")
    if projection.source_asset_id != source or projection.source_document_id != document:
        raise LineageValidationError("source/document does not match authoritative projection")
    try:
        region = RegionStore(con).load(region_id)
    except KeyError as exc:
        raise LineageValidationError("authoritative document region does not exist") from exc
    if region.projection_id != projection_id or region.document_id != document:
        raise LineageValidationError("region does not match authoritative projection/document")


def _validate_trajectory(
    events_dir: str,
    investigation_id: str,
    document_id: str,
    region_id: str,
    twin_note_id: str,
) -> None:
    events = trajectory(investigation_id, events_dir=events_dir)
    if not any(event.get("action_type") == "investigation.start_requested" for event in events):
        raise LineageValidationError("authoritative investigation does not exist")
    if not any(
        event.get("action_type") == "seam.read_to_research"
        and event.get("document_id") == document_id
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("entity_kind") == "document_region"
        and event["payload"].get("entity_id") == region_id
        and event["payload"].get("document_id") == document_id
        and event["payload"].get("launched_investigation_id") == investigation_id
        for event in events
    ):
        raise LineageValidationError("authoritative region-to-research seam does not exist")
    if not any(
        event.get("action_type") == "note.emerged"
        and event.get("document_id") == document_id
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("note_id") == twin_note_id
        for event in events
    ):
        raise LineageValidationError("authoritative twin note does not exist")


def _validate_terminal(
    con: object,
    terminal_kind: TerminalKind,
    terminal_output_id: str,
    investigation_id: str,
    document_id: str,
    region_id: str,
    twin_note_id: str,
) -> None:
    if terminal_kind == "notebook":
        notebook = con.execute(
            "SELECT 1 FROM notebooks WHERE notebook_id = ? AND investigation_id = ? "
            "AND document_id = ?",
            [terminal_output_id, investigation_id, document_id],
        ).fetchone()
        if notebook is None:
            raise LineageValidationError(
                "authoritative notebook does not match investigation/document"
            )
        links = con.execute(
            "SELECT block_type, ref_id FROM notebook_blocks WHERE notebook_id = ? "
            "AND ((block_type = 'region_embed' AND ref_id = ?) "
            "OR (block_type = 'note' AND ref_id = ?))",
            [terminal_output_id, region_id, twin_note_id],
        ).fetchall()
        if sorted(tuple(row) for row in links) != sorted(
            (("region_embed", region_id), ("note", twin_note_id))
        ):
            raise LineageValidationError("notebook is missing exact region/note reference links")
        return
    output = con.execute(
        "SELECT 1 FROM outline_blocks ob "
        "JOIN deliverable_sections ds ON ds.section_id = ob.section_id "
        "JOIN deliverables d ON d.deliverable_id = ds.deliverable_id "
        "WHERE ob.outline_block_id = ? AND d.investigation_root_id = ? "
        "AND (ob.node_id = ? OR ob.source_block_id = ?)",
        [terminal_output_id, investigation_id, twin_note_id, twin_note_id],
    ).fetchone()
    if output is None:
        raise LineageValidationError(
            "authoritative write output does not reference twin note or lacks its parent"
        )


def _validate_id(name: str, value: object) -> None:
    if not isinstance(value, str) or not value or len(value.encode()) > _MAX_ID or "\x00" in value:
        raise LineageValidationError(f"{name} must be a non-empty bounded string")


def _validate_metadata(metadata: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(metadata, Mapping):
        raise LineageValidationError("metadata must be a mapping")
    result: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or _BODY_KEY.search(key):
            raise LineageValidationError("body-like metadata keys are forbidden")
        if key not in METADATA_KEYS:
            raise LineageValidationError(f"metadata key is not allowlisted: {key}")
        if not isinstance(value, str) or len(value.encode()) > _MAX_METADATA_VALUE:
            raise LineageValidationError(f"metadata value is not a bounded string: {key}")
        result[key] = value
    if len(_json(result).encode()) > _MAX_METADATA_BYTES:
        raise LineageValidationError("metadata is oversized")
    return dict(sorted(result.items()))


def _record_json(record: WorkflowLineage) -> str:
    return _json(
        {
            "lineage_id": record.lineage_id,
            "source_asset_id": record.source_asset_id,
            "projection_id": record.projection_id,
            "document_id": record.document_id,
            "region_id": record.region_id,
            "investigation_id": record.investigation_id,
            "twin_note_id": record.twin_note_id,
            "terminal_kind": record.terminal_kind,
            "terminal_output_id": record.terminal_output_id,
            "metadata": dict(record.metadata),
            "node_ids": record.node_ids,
            "edge_ids": record.edge_ids,
        }
    )


def _load_and_check(con: object, row: tuple[object, ...], events_dir: str) -> WorkflowLineage:
    (
        stored_lineage_id,
        source_asset_id,
        projection_id,
        document_id,
        region_id,
        investigation_id,
        twin_note_id,
        terminal_kind,
        terminal_output_id,
        payload,
    ) = map(str, row)
    valid_terminal_kind = terminal_kind in {"notebook", "write_output"}
    if valid_terminal_kind:
        lineage_id = derive_lineage_id(
            source_asset_id,
            projection_id,
            region_id,
            investigation_id,
            twin_note_id,
            terminal_kind,  # type: ignore[arg-type]
            terminal_output_id,
        )
    else:
        lineage_id = ""
    expected_kinds = (
        "source_asset",
        "html_projection",
        "document_region",
        "investigation",
        "twin_note",
        terminal_kind,
    )
    expected_references = (
        source_asset_id,
        projection_id,
        region_id,
        investigation_id,
        twin_note_id,
        terminal_output_id,
    )
    node_ids = tuple(
        derive_node_id(kind, reference)  # type: ignore[arg-type]
        for kind, reference in zip(expected_kinds, expected_references, strict=True)
    )
    edge_ids = tuple(
        derive_edge_id(
            lineage_id,
            position,
            expected_kinds[position],
            node_ids[position],
            expected_kinds[position + 1],
            node_ids[position + 1],
        )
        for position in range(5)
    )
    node_rows = con.execute(
        "SELECT position, node_id, node_kind, reference_id FROM workflow_lineage_nodes "
        "WHERE lineage_id = ? ORDER BY position",
        [stored_lineage_id],
    ).fetchall()
    edge_rows = con.execute(
        "SELECT position, edge_id, from_node_id, to_node_id, from_kind, to_kind "
        "FROM workflow_lineage_edges WHERE lineage_id = ? ORDER BY position",
        [stored_lineage_id],
    ).fetchall()
    missing: list[str] = []
    if stored_lineage_id != lineage_id or not valid_terminal_kind:
        missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    if len(node_rows) != 6 or tuple(row[0] for row in node_rows) != tuple(range(6)):
        missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    for position, (left, right) in enumerate(zip(expected_kinds, expected_kinds[1:], strict=False)):
        if (
            position >= len(edge_rows)
            or edge_rows[position][0] != position
            or (edge_rows[position][4], edge_rows[position][5]) != (left, right)
        ):
            missing.append(f"{REQUIRED_HOPS[position][0]}->{REQUIRED_HOPS[position][1]}")
    complete = (
        not missing
        and len(edge_rows) == 5
        and tuple((row[1], row[2], row[3]) for row in node_rows)
        == tuple(zip(node_ids, expected_kinds, expected_references, strict=True))
        and tuple(row[1] for row in edge_rows) == edge_ids
        and all(
            (row[2], row[3]) == (node_ids[position], node_ids[position + 1])
            for position, row in enumerate(edge_rows)
        )
    )
    try:
        record_data = json.loads(payload)
        metadata = record_data.get("metadata", {}) if isinstance(record_data, dict) else {}
        if (
            _record_json(
                WorkflowLineage(
                    lineage_id,
                    source_asset_id,
                    projection_id,
                    document_id,
                    region_id,
                    investigation_id,
                    twin_note_id,
                    terminal_kind,
                    terminal_output_id,
                    metadata,
                    node_ids,
                    edge_ids,
                    True,
                )
            )
            != payload
        ):
            complete = False
            missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    except TypeError:
        metadata = {}
        complete = False
        missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    except ValueError:
        metadata = {}
        complete = False
        missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    if complete:
        try:
            _validate_authorities(con, source_asset_id, projection_id, document_id, region_id)
            _validate_trajectory(
                events_dir,
                investigation_id,
                document_id,
                region_id,
                twin_note_id,
            )
            _validate_terminal(
                con,
                terminal_kind,  # type: ignore[arg-type]
                terminal_output_id,
                investigation_id,
                document_id,
                region_id,
                twin_note_id,
            )
        except LineageValidationError:
            complete = False
            missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
        except KeyError:
            complete = False
            missing.extend(f"{a}->{b}" for a, b in REQUIRED_HOPS)
    return WorkflowLineage(
        lineage_id,
        source_asset_id,
        projection_id,
        document_id,
        region_id,
        investigation_id,
        twin_note_id,
        terminal_kind,
        terminal_output_id,  # type: ignore[arg-type]
        metadata,
        node_ids,
        edge_ids,
        complete,
        tuple(dict.fromkeys(missing)) if not complete else (),
    )


def _authoritative_incomplete(con: object, column: str, value: str):
    if column == "terminal_output_id" or not _table_exists(con, "html_projections"):
        return ()
    projection_column = "source_asset_id" if column == "source_asset_id" else "source_document_id"
    rows = con.execute(
        "SELECT projection_json FROM html_projections ORDER BY projection_id"
    ).fetchall()
    projections = [json.loads(str(row[0])) for row in rows]
    projections = [p for p in projections if p.get(projection_column) == value]
    result = []
    for projection in projections:
        region_rows = []
        if _table_exists(con, "document_regions"):
            region_rows = con.execute(
                "SELECT region_id, document_id FROM document_regions WHERE projection_id = ? "
                "ORDER BY region_id",
                [projection["projection_id"]],
            ).fetchall()
        if region_rows:
            result.extend(
                IncompleteWorkflowLineage(
                    projection["source_asset_id"],
                    projection["projection_id"],
                    document_id,
                    region_id,
                    missing_hops=tuple(f"{a}->{b}" for a, b in REQUIRED_HOPS[2:]),
                )
                for region_id, document_id in region_rows
            )
        else:
            result.append(
                IncompleteWorkflowLineage(
                    projection["source_asset_id"],
                    projection["projection_id"],
                    projection["source_document_id"],
                    None,
                    missing_hops=tuple(f"{a}->{b}" for a, b in REQUIRED_HOPS[1:]),
                )
            )
    return tuple(result)


def _table_exists(con: object, table: str) -> bool:
    return (
        con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [table]
        ).fetchone()[0]
        == 1
    )


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


__all__ = [
    "IncompleteWorkflowLineage",
    "LineageConflict",
    "LineageValidationError",
    "METADATA_KEYS",
    "REQUIRED_HOPS",
    "WorkflowLineage",
    "WorkflowLineageRegistry",
    "derive_edge_id",
    "derive_lineage_id",
    "derive_node_id",
]
