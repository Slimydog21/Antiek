"""Canonical retrieval-time chunk gate (master-spec §9.0 + Personal-Reading Lane).

This module is the **only** place that formats the non-privileged chunk-gate
SQL fragment. ``search()``, VSS (RG-02), and HTTP (RG-03) must import
``non_privileged_chunk_sql_clause`` — never hand-roll ``NOT IN
(RESTRICTED_CONTENT_CLASSES)`` alone.

**RESTRICTED_CONTENT_CLASSES alone is never sufficient** for chunk gates:
owner-only ``personal_reading`` must be excluded on the same non-privileged
branch as gated-but-public ``restricted_pending_opt_in``. The union is
``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``.

Chunk search uses a **denylist** (exclude withheld classes on public paths).
Book public serve uses an **allowlist** (``SERVABLE_CONTENT_CLASSES`` in
``substrate/books/serve.py``). Different polarity; the withheld classes must
not intersect the servable allowlist — see ``tests/test_retrieval_gate_polarity``.

NULL ``content_class`` is **grandfathered** (served/searchable) on every path:
new ingest always writes an explicit class via ``register_source_document``, so
NULL denotes only legacy pre-migration rows, which the codebase serves by
contract. ASR SR-07's NULL-fail-closed flip was rejected for #65 (it hid legacy
content from search with no backfill); reconsider only with a legacy migration.
"""

from __future__ import annotations

from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    PERSONAL_READING_CONTENT_CLASS,
)

# Policy tags privileged to bypass the restricted-content gate.
# Per master-spec §9.0 retrieval-time gating: restricted content (i.e.
# content_class='restricted_pending_opt_in') is retrievable only on
# private-research or operator-only paths where fair use is robust.
# The default policy_tag for any ad-attributable surface is
# 'attribution_eligible' — which explicitly does NOT bypass the gate.
PRIVILEGED_POLICY_TAGS: frozenset[str] = frozenset({
    "private_research",
    "operator_only",
})

# Content classes that the substrate may withhold from retrieval
# depending on policy_tag. Per master-spec §9.0 §9.10.
#
# RESTRICTED_CONTENT_CLASSES is the GATED-BUT-PUBLIC class
# (restricted_pending_opt_in): a copyrighted-but-public work whose body is
# withheld pending a rights-holder opt-in, but which DOES accrue ad revenue to
# escrow. It is the exact mirror of constants.GATED_DEFAULT_CONTENT_CLASS (the
# write side names the same gate state) — do NOT add personal_reading here.
RESTRICTED_CONTENT_CLASSES: frozenset[str] = frozenset({
    GATED_DEFAULT_CONTENT_CLASS,
})

# Content classes that are OWNER-ONLY: the owner reads them in full on a
# privileged path, but they NEVER surface on a non-privileged (public /
# attribution-eligible) retrieval. personal_reading (the Personal-Reading Lane
# SPR-01 fourth rights state) is the owner's private
# third-party reading (a fetched essay / transcript / tweet) with no rights basis
# to serve publicly and — unlike restricted_pending_opt_in — no escrow economics
# at all (it never earns). It stays separate from
# RESTRICTED_CONTENT_CLASSES on purpose: the two gate states have OPPOSITE
# monetization semantics (restricted EARNS to escrow; personal_reading earns
# nothing), and RESTRICTED_CONTENT_CLASSES carries the documented contract that
# it equals the write-side GATED_DEFAULT_CONTENT_CLASS. Both sets are excluded on
# the same non-privileged branch below, so personal_reading is filtered out of
# the public chunk-search gate while remaining retrievable on the privileged
# (private_research / operator_only) owner path. What would reverse this choice:
# if personal_reading ever needed distinct policy_tag gating from
# restricted_pending_opt_in (e.g. a tag privileged for one but not the other),
# the separate set already supports it; folding them together would not.
PERSONAL_ONLY_CONTENT_CLASSES: frozenset[str] = frozenset({
    PERSONAL_READING_CONTENT_CLASS,
})

# The full set of content classes withheld from a non-privileged retrieval —
# the union of the gated-but-public class and the owner-only class. Both are
# excluded on the public branch; only the PRIVILEGED_POLICY_TAGS bypass.
_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES: frozenset[str] = (
    RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
)


def node_owner_sql_clause(
    *, node_alias: str = "n", owner_user_id: str | None = None
) -> tuple[str, list[str]]:
    """Deny private graph nodes unless the accessing owner matches exactly.

    NULL-owned rows are shared/legacy knowledge. This gate is independent of
    rights policy: a privileged policy tag never grants access to another
    account's private graph.
    """
    if owner_user_id is None:
        return f" AND {node_alias}.owner_user_id IS NULL", []
    return (
        f" AND ({node_alias}.owner_user_id IS NULL OR {node_alias}.owner_user_id = ?)",
        [owner_user_id],
    )


def non_privileged_chunk_sql_clause(
    *,
    table_alias: str = "d",
    policy_tag: str = "attribution_eligible",
    owner_user_id: str = "__operator__",
) -> tuple[str, list[str]]:
    """SQL fragment + bind params for the non-privileged chunk gate.

    On a non-privileged ``policy_tag``, returns a WHERE clause that excludes
    every member of ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`` while
    GRANDFATHERING NULL ``content_class`` (legacy rows remain searchable). New
    ingest always writes an explicit class via ``register_source_document``, so
    NULL denotes only pre-migration legacy content, which the codebase serves by
    contract (``test_sprint11_api::test_get_chunk_null_content_class_grandfathered``,
    ``test_graph``, ``test_grounding``). A privileged tag bypasses rights
    withholding but still requires exact ownership for owner-only classes.

    NOTE: ASR SR-07 proposed flipping NULL fail-closed here; that was rejected for
    #65 because it hides legacy content from search/grounding with no backfill.
    Reconsider only paired with a legacy-NULL → explicit-class migration.

    Args:
        table_alias: Alias of the ``documents`` row in the query (default ``d``).
        policy_tag: Retrieval policy; privileged tags bypass rights withholding.
        owner_user_id: Account allowed to retrieve owner-only classes.
    """
    if policy_tag in PRIVILEGED_POLICY_TAGS:
        owner_only = sorted(PERSONAL_ONLY_CONTENT_CLASSES)
        placeholders = ",".join("?" for _ in owner_only)
        return (
            f" AND ({table_alias}.content_class IS NULL OR "
            f"{table_alias}.content_class NOT IN ({placeholders}) OR "
            f"{table_alias}.owner_user_id = ?)",
            [*owner_only, owner_user_id],
        )
    excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
    placeholders = ",".join("?" for _ in excluded)
    sql = (
        f" AND ({table_alias}.content_class IS NULL OR "
        f"{table_alias}.content_class NOT IN ({placeholders}))"
    )
    return sql, excluded


def non_privileged_node_provenance_clause(
    *,
    node_alias: str = "n",
    policy_tag: str = "attribution_eligible",
) -> tuple[str, list[str]]:
    """SQL fragment + bind params for the non-privileged **node** gate (SPR-01).

    A node has no ``content_class`` column of its own — its rights class is
    inherited from the document(s) it was extracted from (master-spec Open
    Question A, the *provenance join*, chosen over the rejected denormalized
    stamp: the join is authoritative and the node path is not a measured
    hot-path). Provenance is resolved along **both** links the substrate
    actually records:

      * ``node.metadata ->> 'chunk_id'`` → ``chunks.document_id`` →
        ``documents.content_class`` — the inbox / substack ingest link, which
        stashes the grounding chunk in node metadata and writes **no** edge
        (``acquisition/inbox/ingest.py``, ``acquisition/substack/adapter.py``).
        This is the link the §9.0 leak actually travels.
      * ``edges`` where the node is source or target → the edge's own
        ``source_document_id`` (direct) or ``chunk_id`` →
        ``chunks.document_id`` → ``documents.content_class`` — the grounding
        link ``promote_insight`` records (see ``insight_question.py``).

    **Most-restrictive wins:** a node is withheld on a non-privileged path if
    *any* resolved provenance document is in
    ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``. A §9.0 under-exclusion is a
    legal leak; an over-exclusion only hides owner value on the non-owner path.

    **Fail-closed on unresolved provenance:** a node with *no* resolvable
    provenance document at all (no metadata chunk_id, no edge) is withheld on
    the non-privileged path — its rights class cannot be established, so it is
    treated as non-servable. This is DISTINCT from the NULL-``content_class``
    grandfathering contract: a node that resolves to a real document whose
    class is NULL is still served (legacy rows remain searchable, mirroring
    ``non_privileged_chunk_sql_clause``); only a node that resolves to *nothing*
    fails closed.

    On a privileged tag (``private_research`` / ``operator_only``) returns
    ``("", [])`` — the owner path returns every labeled node unchanged.

    Args:
        node_alias: Alias of the ``nodes`` row in the outer query (default ``n``).
        policy_tag: Retrieval policy; only PRIVILEGED_POLICY_TAGS bypass the gate.
    """
    if policy_tag in PRIVILEGED_POLICY_TAGS:
        return "", []
    excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
    ph = ",".join("?" for _ in excluded)
    na = node_alias
    # (1) Does this node resolve to ANY provenance document? (metadata chunk_id
    #     OR an edge's source_document_id OR an edge's chunk_id). Each branch is
    #     a flat subquery correlated only to the outer node row.
    prov_any = (
        "SELECT 1 FROM chunks c "
        f"WHERE c.chunk_id = json_extract_string({na}.metadata, '$.chunk_id') "
        "UNION ALL "
        "SELECT 1 FROM edges e "
        f"WHERE (e.source_node_id = {na}.node_id OR e.target_node_id = {na}.node_id) "
        "AND e.source_document_id IS NOT NULL "
        "UNION ALL "
        "SELECT 1 FROM edges e2 JOIN chunks c2 ON c2.chunk_id = e2.chunk_id "
        f"WHERE (e2.source_node_id = {na}.node_id OR e2.target_node_id = {na}.node_id)"
    )
    # (2) Does ANY resolved provenance document sit in the withheld set?
    #     Same three links, each JOINed to documents with the excluded filter.
    #     NULL content_class is grandfathered: `content_class IN (...)` is
    #     UNKNOWN for NULL, so a NULL-class provenance doc never trips this.
    prov_excluded = (
        "SELECT 1 FROM chunks c JOIN documents d ON d.document_id = c.document_id "
        f"WHERE c.chunk_id = json_extract_string({na}.metadata, '$.chunk_id') "
        f"AND d.content_class IN ({ph}) "
        "UNION ALL "
        "SELECT 1 FROM edges e JOIN documents d ON d.document_id = e.source_document_id "
        f"WHERE (e.source_node_id = {na}.node_id OR e.target_node_id = {na}.node_id) "
        f"AND d.content_class IN ({ph}) "
        "UNION ALL "
        "SELECT 1 FROM edges e2 JOIN chunks c2 ON c2.chunk_id = e2.chunk_id "
        "JOIN documents d ON d.document_id = c2.document_id "
        f"WHERE (e2.source_node_id = {na}.node_id OR e2.target_node_id = {na}.node_id) "
        f"AND d.content_class IN ({ph})"
    )
    sql = (
        # fail-closed: at least one resolvable provenance document …
        f" AND EXISTS ({prov_any})"
        # … and none of them in the withheld set.
        f" AND NOT EXISTS ({prov_excluded})"
    )
    # prov_any carries no binds; prov_excluded binds the excluded set 3×.
    params = [*excluded, *excluded, *excluded]
    return sql, params


def is_chunk_body_withheld(
    content_class: str | None,
    *,
    taken_down: bool = False,
) -> tuple[bool, str | None]:
    """Whether a chunk body must be withheld on the non-privileged HTTP path.

    Mirrors the chunk-gate frozensets without duplicating SQL. Takedown wins
    over content_class. NULL / legacy classes are GRANDFATHERED (not withheld
    here) — the explicit contract pinned by
    ``tests/test_sprint11_api::test_get_chunk_null_content_class_grandfathered``;
    both #53 and ASR serve NULL bodies on the HTTP path.

    Returns:
        ``(withheld, label)`` — label is ``"taken_down"``, ``"personal_readable"``,
        ``"restricted"``, or ``None`` when the body may be served.
        (``personal_readable`` is the ASR SR-09 API contract label for the
        owner-only personal_reading class — pinned by
        ``tests/test_get_chunk_personal_reading`` + ``test_retrieval_gate_matrix``.)
    """
    if taken_down:
        return True, "taken_down"
    if content_class in PERSONAL_ONLY_CONTENT_CLASSES:
        return True, "personal_readable"
    if content_class in RESTRICTED_CONTENT_CLASSES:
        return True, "restricted"
    return False, None
