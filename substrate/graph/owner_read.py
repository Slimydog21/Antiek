"""Owner-facing body reads preserve provenance but never licensed agent inputs."""
from __future__ import annotations

from substrate.constants import RESEARCH_ONLY_CONTENT_CLASS


def owner_body_sql(*, document_alias: str = "d") -> tuple[str, list[str]]:
    """Predicate for direct body readers; NULL legacy classes stay readable.

    Aliases are static SQL identifiers supplied by code, never request fields.
    Retrieval callers additionally enforce their own scope and takedown gates.
    """
    return f"{document_alias}.content_class IS DISTINCT FROM ?", [RESEARCH_ONLY_CONTENT_CLASS]
