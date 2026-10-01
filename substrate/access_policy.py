"""Small, shared retrieval policy values without graph or rights imports."""

from __future__ import annotations

from substrate.constants import (
    FORBIDDEN_OWNERS,
    PERSONAL_READING_CONTENT_CLASS,
    USER_AUTHORED_PRIVATE_CONTENT_CLASS,
)


def _usable_owner_id(owner_user_id: str | None) -> str | None:
    if (
        isinstance(owner_user_id, str)
        and owner_user_id.strip()
        and owner_user_id == owner_user_id.strip()
        and owner_user_id.casefold() not in FORBIDDEN_OWNERS
    ):
        return owner_user_id
    return None


PERSONAL_ONLY_CONTENT_CLASSES: frozenset[str] = frozenset({
    PERSONAL_READING_CONTENT_CLASS,
    USER_AUTHORED_PRIVATE_CONTENT_CLASS,
})


def taken_down_chunk_exclusion_sql(*, table_alias: str = "d") -> str:
    """Parameter-free exclusion of a document whose book asset is taken down.

    ``table_alias`` is a static identifier from the caller, never a request
    field. A missing ``book_assets`` row, ``FALSE``, or NULL does not match.
    Callers AND this outside the content-class/owner OR.
    """
    if not table_alias.isidentifier():
        raise ValueError("document alias must be a static identifier")
    return (
        "NOT EXISTS (SELECT 1 FROM book_assets td "
        f"WHERE td.document_id = {table_alias}.document_id "
        "AND td.taken_down IS TRUE)"
    )
