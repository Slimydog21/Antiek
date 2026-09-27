"""The rights switch, the rights reads and the owner overlay (LB-9a; LB-9
spec D4 and D8).

The switch. Signed TC §1.12 says nothing of the companion document ships
until the wave-5 export branch and ``fix/w5-mcp-hardening-20260923`` merge.
``RIGHTS_BRANCHES_LANDED`` is that fact as a reviewed constant, never an
environment variable, and ``bound()`` answers None while it is off, so every
route answers ``unavailable_until_rights``. LB-9d is the one change that sets
it and returns a real ``RightsBinding``.

The overlay. The signed servable allowlist includes ``user_owned``, and the
wave-5 resolver reads a document by id with no owner check, so a pin into
another owner's private upload would come back served. A resolved document
is withheld and opaque when its owner is not one of the requester's
identities and its class is not in ``PUBLIC_GRAPH_CONTENT_CLASSES``. NULL and
unknown classes fail closed: they are neither servable nor public.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol

from substrate.ad_inventory.attribution import PUBLIC_GRAPH_CONTENT_CLASSES
from substrate.companion_document.store import SourcePin, table_exists
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.research_artifact.schema import ResearchArtifactBody

#: Off until both rights branches have merged. Only LB-9d flips it.
RIGHTS_BRANCHES_LANDED: Final[bool] = False


@dataclass(frozen=True, slots=True)
class DocumentRights:
    """A document's live rights: its class, its owner, and whether a
    takedown overrides the class. ``owner_user_id`` None is nobody's."""

    document_id: str
    content_class: str | None
    owner_user_id: str | None
    taken_down: bool = False


@dataclass(frozen=True, slots=True)
class ThreadLog:
    """One thread's events as a full read saw them (the ``trajectory_read``
    shape): ``complete`` is False when any stored record could not be read."""

    rows: tuple[Mapping[str, Any], ...]
    complete: bool
    stored: bool


@dataclass(frozen=True, slots=True)
class ThreadSources:
    """A thread's excerpt-source set: every pointer its synthesis stands on,
    and whether any walk in it was unreadable."""

    sources: tuple[SourcePin, ...]
    unreadable: bool


class RightsBinding(Protocol):
    """The reads the companion document needs from the rights branches.
    LB-9d binds them to ``trajectory_read``, ``build_body``,
    ``excerpt_sources`` and ``resolve_pin_sources``."""

    def read_log(self, thread_id: str) -> ThreadLog: ...

    def body(self, thread_id: str) -> ResearchArtifactBody | None: ...

    def thread_sources(self, thread_id: str) -> ThreadSources: ...

    def node_pins(self, node_ids: Sequence[str]) -> Mapping[str, tuple[SourcePin, ...]]: ...


def bound() -> RightsBinding | None:
    """The live binding, or None while the rights branches have not landed.
    A caller that gets None answers ``unavailable_until_rights`` and writes
    nothing. There is no binding to return until LB-9d, which sets
    ``RIGHTS_BRANCHES_LANDED`` and returns the real one here."""
    return None


def is_servable(rights: DocumentRights) -> bool:
    """Whether the document's text may be served: an allowlisted class and
    no takedown. NULL, unknown and ``personal_reading`` are not servable."""
    return not rights.taken_down and rights.content_class in SERVABLE_CONTENT_CLASSES


def owner_overlay_withholds(rights: DocumentRights, admitted_owners: frozenset[str]) -> bool:
    """Whether the owner overlay makes this document withheld and opaque for
    a requester holding ``admitted_owners``: someone else's document whose
    class is not on the public graph."""
    return (
        rights.owner_user_id not in admitted_owners
        and rights.content_class not in PUBLIC_GRAPH_CONTENT_CLASSES
    )


def document_rights(con: Any, document_ids: Sequence[str]) -> dict[str, DocumentRights | None]:
    """The live rights of each requested document, None for a document that
    does not exist. ``con`` is any read connection; nothing is written."""
    wanted = list(dict.fromkeys(document_ids))
    out: dict[str, DocumentRights | None] = dict.fromkeys(wanted)
    if not wanted or not table_exists(con, "documents"):
        return out
    has_class = con.execute(
        "SELECT 1 FROM duckdb_columns() WHERE table_name = 'documents' AND column_name = 'content_class'"
    ).fetchone()
    content_class = "d.content_class" if has_class else "NULL"
    taken_down = "FALSE"
    join = ""
    if table_exists(con, "book_assets"):
        taken_down = "COALESCE(b.taken_down, FALSE)"
        join = " LEFT JOIN book_assets b ON b.document_id = d.document_id"
    rows = con.execute(
        f"SELECT d.document_id, {content_class}, d.owner_user_id, {taken_down} FROM documents d{join} "
        f"WHERE d.document_id IN ({', '.join('?' * len(wanted))})",
        wanted,
    ).fetchall()
    for doc_id, cls, owner, down in rows:
        out[str(doc_id)] = DocumentRights(
            document_id=str(doc_id),
            content_class=None if cls is None else str(cls),
            owner_user_id=None if owner is None else str(owner),
            taken_down=bool(down),
        )
    return out


__all__ = [
    "PUBLIC_GRAPH_CONTENT_CLASSES",
    "RIGHTS_BRANCHES_LANDED",
    "SERVABLE_CONTENT_CLASSES",
    "DocumentRights",
    "RightsBinding",
    "ThreadLog",
    "ThreadSources",
    "bound",
    "document_rights",
    "is_servable",
    "owner_overlay_withholds",
]
