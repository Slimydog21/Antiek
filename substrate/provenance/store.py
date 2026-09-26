"""Connection-taking persistence for bite-level provenance (SPR-01).

Row CRUD under LockedConnection, the unit-1 conventions: frozen dataclasses,
every write through one method, the idempotent schema ensured on write entry
points. The ONE writer is the reformat pipeline (substrate/reformat/
pipeline.py) — provenance is captured AT WRITE TIME, never reconstructed.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from dataclasses import dataclass
from typing import Any

from runtime.db_lock import LockedConnection
from substrate.provenance.schema import (
    SqlExecutor,
    init_provenance_schema,
    provenance_tables_exist,
)


def mint_generation_id() -> str:
    return f"gen-{secrets.token_hex(8)}"


def make_bite_id(
    generation_id: str,
    ordinal: int,
    normalized_text: str,
    contribution_class: str,
    source_refs: list[str],
) -> str:
    """The content-derived bite id (unit 6's stable-id discipline, scoped to
    its generation): sha over generation · ordinal · normalized text · class
    · sorted refs. Stable across a re-run of the SAME generation's write;
    distinct generations never share a row (a re-run is a lawful NEW
    generation, never an in-place overwrite)."""
    material = "\x1f".join(
        [generation_id, str(ordinal), normalized_text, contribution_class, *sorted(source_refs)]
    )
    return "bite-" + hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]


def text_sha256(normalized_text: str) -> str:
    """The byte-verification hash over the unit-1 normalized scalar space."""
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GenerationRecordRow:
    generation_id: str
    owner_user_id: str
    source_document_id: str
    derived_document_id: str
    prompt: str
    model: str
    params_json: str
    mostly_generated: bool
    created_at: str


@dataclass(frozen=True, slots=True)
class BiteRow:
    """One derived bite's contribution account — hashes and refs, never text."""

    bite_id: str
    generation_id: str
    ordinal: int
    contribution_class: str
    source_refs: tuple[str, ...] | None
    investigation_id: str | None
    derived_text_sha256: str
    source_span_sha256: str | None


def _to_generation(r: Any) -> GenerationRecordRow:
    return GenerationRecordRow(
        generation_id=str(r[0]),
        owner_user_id=str(r[1]),
        source_document_id=str(r[2]),
        derived_document_id=str(r[3]),
        prompt=str(r[4]),
        model=str(r[5]),
        params_json=str(r[6]),
        mostly_generated=bool(r[7]),
        created_at=str(r[8]),
    )


def _to_bite(r: Any) -> BiteRow:
    refs = None if r[4] is None else json.loads(str(r[4]))
    return BiteRow(
        bite_id=str(r[0]),
        generation_id=str(r[1]),
        ordinal=int(r[2]),
        contribution_class=str(r[3]),
        source_refs=None if refs is None else tuple(str(x) for x in refs),
        investigation_id=None if r[5] is None else str(r[5]),
        derived_text_sha256=str(r[6]),
        source_span_sha256=None if r[7] is None else str(r[7]),
    )


class ProvenanceStore:
    """Persist and read generation records + bite provenance."""

    def record_generation(
        self,
        con: LockedConnection,
        *,
        record: GenerationRecordRow,
        bites: list[BiteRow],
    ) -> None:
        """The generation record + its bite rows in ONE call — the caller
        (the pipeline) wraps it in its bounded write scope/transaction. The
        author-verbatim CHECK is the DB backstop; the pipeline verifies
        BEFORE this (a mismatch is reclassed upstream, never written)."""
        init_provenance_schema(con)
        con.execute(
            "INSERT INTO generation_records (generation_id, owner_user_id, "
            "source_document_id, derived_document_id, prompt, model, "
            "params_json, mostly_generated) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.generation_id,
                record.owner_user_id,
                record.source_document_id,
                record.derived_document_id,
                record.prompt,
                record.model,
                record.params_json,
                record.mostly_generated,
            ],
        )
        if bites:
            con.executemany(
                "INSERT INTO bite_provenance (bite_id, generation_id, ordinal, "
                "contribution_class, source_refs_json, investigation_id, "
                "derived_text_sha256, source_span_sha256) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        b.bite_id,
                        b.generation_id,
                        b.ordinal,
                        b.contribution_class,
                        None
                        if b.source_refs is None
                        else json.dumps(sorted(b.source_refs)),
                        b.investigation_id,
                        b.derived_text_sha256,
                        b.source_span_sha256,
                    )
                    for b in bites
                ],
            )

    def get_generation(
        self, con: SqlExecutor, generation_id: str
    ) -> GenerationRecordRow | None:
        if not provenance_tables_exist(con):
            return None
        row = con.execute(
            "SELECT generation_id, owner_user_id, source_document_id, "
            "derived_document_id, prompt, model, params_json, mostly_generated, "
            "created_at FROM generation_records WHERE generation_id = ? LIMIT 1",
            [generation_id],
        ).fetchone()
        return None if row is None else _to_generation(row)

    def bites_for_generation(self, con: SqlExecutor, generation_id: str) -> list[BiteRow]:
        """A generation's bites in ordinal order (the derived document's
        reading order)."""
        if not provenance_tables_exist(con):
            return []
        rows = con.execute(
            "SELECT bite_id, generation_id, ordinal, contribution_class, "
            "source_refs_json, investigation_id, derived_text_sha256, "
            "source_span_sha256 FROM bite_provenance WHERE generation_id = ? "
            "ORDER BY ordinal ASC",
            [generation_id],
        ).fetchall()
        return [_to_bite(r) for r in rows]
