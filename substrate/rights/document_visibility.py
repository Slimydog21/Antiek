"""Safe document-metadata discovery; independent of body serving rights."""

from __future__ import annotations

from substrate.access_policy import (
    PERSONAL_ONLY_CONTENT_CLASSES,
    _usable_owner_id,
    taken_down_chunk_exclusion_sql,
)


def document_discoverable(
    *,
    content_class: str | None,
    stored_owner_user_id: str | None,
    taken_down: bool,
    owner_user_id: str | None,
) -> bool:
    """Decide whether a document's safe metadata may be discovered."""
    from substrate.rights.register import VALID_CONTENT_CLASSES

    if taken_down or (content_class is not None and content_class not in VALID_CONTENT_CLASSES):
        return False
    if content_class in PERSONAL_ONLY_CONTENT_CLASSES:
        owner = _usable_owner_id(owner_user_id)
        return owner is not None and stored_owner_user_id == owner
    return True


def document_discoverability_sql(
    *, owner_user_id: str | None, document_alias: str = "d"
) -> tuple[str, list[str]]:
    """Return a parenthesized SQL predicate and ordered binds, without leading AND."""
    from substrate.rights.register import VALID_CONTENT_CLASSES

    if (
        not document_alias.isidentifier()
        or document_alias.lower() == "td"
        or document_alias.lower().startswith("pa04_")
    ):
        raise ValueError("document alias must be a static identifier")
    known = sorted(VALID_CONTENT_CLASSES)
    private = sorted(PERSONAL_ONLY_CONTENT_CLASSES)
    known_ph = ",".join("?" for _ in known)
    private_ph = ",".join("?" for _ in private)
    owner = _usable_owner_id(owner_user_id)
    private_clause = (
        f"({document_alias}.content_class NOT IN ({private_ph}) "
        f"OR {document_alias}.owner_user_id = ?)"
        if owner is not None else
        f"{document_alias}.content_class NOT IN ({private_ph})"
    )
    sql = (
        f"(({document_alias}.content_class IS NULL OR "
        f"{document_alias}.content_class IN ({known_ph})) AND "
        f"{taken_down_chunk_exclusion_sql(table_alias=document_alias)} AND "
        f"({document_alias}.content_class IS NULL OR {private_clause}))"
    )
    return sql, [*known, *private, *([owner] if owner is not None else [])]
