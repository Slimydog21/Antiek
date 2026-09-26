"""Companions — the generated-never-authored narrative surfaces + the
agent-facing evidence base (project-companion + evidence base, SPR-01).

ONE projector pass over the lawful stores produces the rebuildable
evidence index (a cache with a stable-id contract, never a truth) AND the
companion renderings (per-document shipped; per-project honestly
unavailable until the unit-3 container lands). Nothing here is a store of
its own; hand edits are impossible by construction — there is no write
path into a companion except the projector.
"""

from .evidence_index import (
    EvidenceRow,
    evidence_index_table_exists,
    init_evidence_index_schema,
    make_evidence_id,
    query_claim_node_ids,
    read_scope,
    rebuild_scope,
    resolve,
)
from .projector import (
    ProjectScopeUnavailable,
    rebuild_document,
    rebuild_project,
)
from .render import (
    PROJECT_SCOPE_UNAVAILABLE_LINE,
    render_document_companion,
    render_project_companion,
)

__all__ = [
    "EvidenceRow",
    "PROJECT_SCOPE_UNAVAILABLE_LINE",
    "ProjectScopeUnavailable",
    "evidence_index_table_exists",
    "init_evidence_index_schema",
    "make_evidence_id",
    "query_claim_node_ids",
    "read_scope",
    "rebuild_document",
    "rebuild_project",
    "rebuild_scope",
    "render_document_companion",
    "render_project_companion",
    "resolve",
]
