"""Canonical retrieval-time chunk gate (master-spec §9.0 + Personal-Reading Lane).

This module is the **only** place that formats the non-privileged chunk-gate
SQL fragment. ``search()``, VSS (RG-02), and HTTP (RG-03) must import
``non_privileged_chunk_sql_clause`` — never hand-roll ``NOT IN
(RESTRICTED_CONTENT_CLASSES)`` alone.

**RESTRICTED_CONTENT_CLASSES alone is never sufficient** for chunk gates:
owner-only ``personal_reading`` / ``user_authored_private`` and agent-only
``research_only`` must be excluded alongside gated-but-public
``restricted_pending_opt_in``. The union is
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

from substrate.access_policy import (
    PERSONAL_ONLY_CONTENT_CLASSES as PERSONAL_ONLY_CONTENT_CLASSES,
)
from substrate.access_policy import (
    _usable_owner_id as _usable_owner_id,
)
from substrate.access_policy import (
    taken_down_chunk_exclusion_sql as taken_down_chunk_exclusion_sql,
)
from substrate.constants import (
    GATED_DEFAULT_CONTENT_CLASS,
    RESEARCH_ONLY_CONTENT_CLASS,
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
RESEARCH_AGENT_POLICY_TAG = "private_research"
OWNER_SCOPED_POLICY_TAG = "owner_scoped"
assert RESEARCH_AGENT_POLICY_TAG in PRIVILEGED_POLICY_TAGS
assert OWNER_SCOPED_POLICY_TAG not in PRIVILEGED_POLICY_TAGS


def research_policy_tag_from_env(value: str | None) -> str:
    """Validate the research principal before retrieval or event emission."""
    tag = (value or "").strip() or "attribution_eligible"
    if tag not in {"attribution_eligible", RESEARCH_AGENT_POLICY_TAG}:
        raise ValueError(
            "ANTIEK_RESEARCH_POLICY_TAG must be attribution_eligible or private_research"
        )
    return tag

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
# the same non-privileged branch below. Both owner-only classes require exact
# owner identity on a privileged path. What would reverse this choice:
# if personal_reading ever needed distinct policy_tag gating from
# restricted_pending_opt_in (e.g. a tag privileged for one but not the other),
# the separate set already supports it; folding them together would not.
RESEARCH_ONLY_CONTENT_CLASSES: frozenset[str] = frozenset({
    RESEARCH_ONLY_CONTENT_CLASS,
})

# The full public-exclusion set. Research-only stays agent-only even when an
# owner identity is present; operator_only cannot read it.
_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES: frozenset[str] = (
    RESTRICTED_CONTENT_CLASSES
    | PERSONAL_ONLY_CONTENT_CLASSES
    | RESEARCH_ONLY_CONTENT_CLASSES
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
    owner_user_id: str | None = None,
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
    # Import after package initialization: rights.register imports graph.ops,
    # whose package imports search -> this module. A top-level import cycles.
    from substrate.rights.register import VALID_CONTENT_CLASSES

    known = sorted(VALID_CONTENT_CLASSES)
    known_ph = ",".join("?" for _ in known)
    known_sql = (
        f" AND ({table_alias}.content_class IS NULL OR "
        f"{table_alias}.content_class IN ({known_ph}))"
    )
    takedown = " AND " + taken_down_chunk_exclusion_sql(table_alias=table_alias)
    if policy_tag == OWNER_SCOPED_POLICY_TAG:
        excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
        excluded_ph = ",".join("?" for _ in excluded)
        personal = sorted(PERSONAL_ONLY_CONTENT_CLASSES)
        personal_ph = ",".join("?" for _ in personal)
        owner_id = _usable_owner_id(owner_user_id)
        owner_arm = (
            f" OR ({table_alias}.content_class IN ({personal_ph}) "
            f"AND {table_alias}.owner_user_id = ?)"
            if owner_id is not None else ""
        )
        sql = (
            f" AND ({table_alias}.content_class IS NULL OR "
            f"{table_alias}.content_class NOT IN ({excluded_ph})"
            f"{owner_arm})"
        )
        params = [*excluded]
        if owner_id is not None:
            params.extend([*personal, owner_id])
        return known_sql + sql + takedown, [*known, *params]
    if policy_tag in PRIVILEGED_POLICY_TAGS:
        owner_only = sorted(PERSONAL_ONLY_CONTENT_CLASSES)
        placeholders = ",".join("?" for _ in owner_only)
        owner_id = _usable_owner_id(owner_user_id)
        owner_clause = f" OR {table_alias}.owner_user_id = ?" if owner_id is not None else ""
        sql = (
            f" AND ({table_alias}.content_class IS NULL OR "
            f"{table_alias}.content_class NOT IN ({placeholders}){owner_clause})"
        )
        params = [*owner_only, *([owner_id] if owner_id is not None else [])]
        if policy_tag != RESEARCH_AGENT_POLICY_TAG:
            research_only = sorted(RESEARCH_ONLY_CONTENT_CLASSES)
            research_ph = ",".join("?" for _ in research_only)
            sql = (
                f" AND ({table_alias}.content_class IS NULL OR "
                f"{table_alias}.content_class NOT IN ({research_ph}))"
                + sql
            )
            params = [*research_only, *params]
        return known_sql + sql + takedown, [*known, *params]
    excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
    placeholders = ",".join("?" for _ in excluded)
    sql = (
        f" AND ({table_alias}.content_class IS NULL OR "
        f"{table_alias}.content_class NOT IN ({placeholders}))"
        + takedown
    )
    return known_sql + sql, [*known, *excluded]


def _provenance_alias(alias: str) -> str:
    """Validate an SQL identifier supplied by source code, never request text."""
    if not alias.isidentifier():
        raise ValueError("provenance alias must be a static identifier")
    return alias


def _outer_provenance_alias(alias: str) -> str:
    """Keep caller aliases distinct from every private subquery alias."""
    _provenance_alias(alias)
    if alias.lower() == "td" or alias.lower().startswith("pa04_"):
        raise ValueError("provenance alias collides with an internal alias")
    return alias


def _node_source_references_sql(node_alias: str) -> str:
    """All declared links, including invalid declarations, as (kind, id) rows."""
    na = _provenance_alias(node_alias)
    meta = f"TRY_CAST({na}.metadata AS JSON)"
    return (
        "SELECT 'invalid' AS kind, NULL::TEXT AS ref_id "
        f"WHERE {na}.metadata IS NOT NULL "
        f"AND ({meta} IS NULL OR json_type({meta}) != 'OBJECT') "
        "UNION ALL "
        "SELECT CASE WHEN json_type(json_extract(" + meta + ", '$.chunk_id')) = 'VARCHAR' "
        "THEN 'chunk' ELSE 'invalid' END, "
        f"json_extract_string({meta}, '$.chunk_id') "
        f"WHERE json_extract({meta}, '$.chunk_id') IS NOT NULL "
        "UNION ALL "
        "SELECT CASE WHEN json_type(json_extract(" + meta + ", '$.source_document_id')) = 'VARCHAR' "
        "THEN 'doc' ELSE 'invalid' END, "
        f"json_extract_string({meta}, '$.source_document_id') "
        f"WHERE json_extract({meta}, '$.source_document_id') IS NOT NULL "
        "UNION ALL "
        "SELECT 'invalid', NULL::TEXT "
        f"WHERE json_extract({meta}, '$.source_chunk_ids') IS NOT NULL "
        f"AND json_type(json_extract({meta}, '$.source_chunk_ids')) != 'ARRAY' "
        "UNION ALL "
        "SELECT CASE WHEN json_type(pa04_item.value) = 'VARCHAR' "
        "THEN 'chunk' ELSE 'invalid' END, "
        "json_extract_string(pa04_item.value, '$') "
        f"FROM json_each({meta}, '$.source_chunk_ids') pa04_item "
        "UNION ALL "
        "SELECT 'doc', pa04_edge.source_document_id "
        "FROM edges pa04_edge "
        f"WHERE (pa04_edge.source_node_id = {na}.node_id "
        f"OR pa04_edge.target_node_id = {na}.node_id) "
        "AND pa04_edge.source_document_id IS NOT NULL "
        "UNION ALL "
        "SELECT 'chunk', pa04_edge2.chunk_id "
        "FROM edges pa04_edge2 "
        f"WHERE (pa04_edge2.source_node_id = {na}.node_id "
        f"OR pa04_edge2.target_node_id = {na}.node_id) "
        "AND pa04_edge2.chunk_id IS NOT NULL"
    )


def _source_policy_sql(
    *, document_alias: str, policy_tag: str, owner_user_id: str | None
) -> tuple[str, list[str]]:
    """Derived-label policy for a resolved source document, not raw body rights."""
    from substrate.rights.register import VALID_CONTENT_CLASSES

    da = _provenance_alias(document_alias)
    known = sorted(VALID_CONTENT_CLASSES)
    private = sorted(PERSONAL_ONLY_CONTENT_CLASSES)
    denied = sorted(PERSONAL_ONLY_CONTENT_CLASSES | RESTRICTED_CONTENT_CLASSES | RESEARCH_ONLY_CONTENT_CLASSES)
    owner = _usable_owner_id(owner_user_id)
    known_sql = f"({da}.content_class IS NULL OR {da}.content_class IN ({','.join('?' for _ in known)}))"
    withheld = private if policy_tag in PRIVILEGED_POLICY_TAGS else denied
    # A verified owner can see their own private derived node on every
    # private/owner-scoped policy, but public/unknown tags never use identity.
    include_owner = owner is not None and (
        policy_tag in PRIVILEGED_POLICY_TAGS or policy_tag == OWNER_SCOPED_POLICY_TAG
    )
    owner_arm = (
        f" OR ({da}.content_class IN ({','.join('?' for _ in private)}) "
        f"AND {da}.owner_user_id = ?)"
        if include_owner
        else ""
    )
    base = f"{da}.content_class NOT IN ({','.join('?' for _ in withheld)})"
    sql = (
        f"{known_sql} AND {taken_down_chunk_exclusion_sql(table_alias=da)} "
        f"AND ({da}.content_class IS NULL OR {base}{owner_arm})"
    )
    params = [*known, *withheld]
    if include_owner and owner is not None:
        params.extend([*private, owner])
    return sql, params


def _references_valid_sql(
    references: str, *, policy_tag: str, owner_user_id: str | None
) -> tuple[str, list[str]]:
    """Require a resolved source and reject any malformed, missing or denied one."""
    policy, params = _source_policy_sql(
        document_alias="pa04_doc", policy_tag=policy_tag, owner_user_id=owner_user_id
    )
    relation = (
        f"FROM ({references}) pa04_ref "
        "LEFT JOIN chunks pa04_chunk ON pa04_ref.kind = 'chunk' "
        "AND pa04_chunk.chunk_id = pa04_ref.ref_id "
        "LEFT JOIN documents pa04_doc ON pa04_doc.document_id = "
        "CASE WHEN pa04_ref.kind = 'doc' THEN pa04_ref.ref_id "
        "ELSE pa04_chunk.document_id END"
    )
    return (
        f" AND EXISTS (SELECT 1 {relation} WHERE pa04_doc.document_id IS NOT NULL)"
        f" AND NOT EXISTS (SELECT 1 {relation} WHERE "
        "pa04_ref.kind = 'invalid' OR pa04_ref.ref_id IS NULL "
        "OR trim(pa04_ref.ref_id) = '' OR pa04_doc.document_id IS NULL "
        f"OR ({policy}) IS NOT TRUE)",
        params,
    )


def _node_provenance_clause(
    *, node_alias: str = "n", policy_tag: str = "attribution_eligible",
    owner_user_id: str | None,
) -> tuple[str, list[str]]:
    """Require node ownership and every declared source's derived-label rights."""
    na = _provenance_alias(node_alias)
    owner = _usable_owner_id(owner_user_id)
    owner_sql = f" AND {na}.owner_user_id IS NULL"
    owner_params: list[str] = []
    if owner is not None:
        owner_sql = f" AND ({na}.owner_user_id IS NULL OR {na}.owner_user_id = ?)"
        owner_params = [owner]
    source_sql, source_params = _references_valid_sql(
        _node_source_references_sql(na),
        policy_tag=policy_tag,
        owner_user_id=owner,
    )
    return owner_sql + source_sql, [*owner_params, *source_params]


def non_privileged_node_provenance_clause(
    *, node_alias: str = "n", policy_tag: str = "attribution_eligible",
    owner_user_id: str | None,
) -> tuple[str, list[str]]:
    """Require node ownership and every declared source's derived-label rights."""
    return _node_provenance_clause(
        node_alias=_outer_provenance_alias(node_alias),
        policy_tag=policy_tag,
        owner_user_id=owner_user_id,
    )


def non_privileged_edge_provenance_clause(
    *, edge_alias: str = "e", policy_tag: str = "attribution_eligible",
    owner_user_id: str | None,
) -> tuple[str, list[str]]:
    """Require edge owner, both endpoints and all of the edge's own sources."""
    ea = _outer_provenance_alias(edge_alias)
    owner = _usable_owner_id(owner_user_id)
    owner_sql = f" AND {ea}.owner_user_id IS NULL"
    owner_params: list[str] = []
    if owner is not None:
        owner_sql = f" AND ({ea}.owner_user_id IS NULL OR {ea}.owner_user_id = ?)"
        owner_params = [owner]
    source_node_sql, source_node_params = _node_provenance_clause(
        node_alias="pa04_source_node", policy_tag=policy_tag, owner_user_id=owner
    )
    target_node_sql, target_node_params = _node_provenance_clause(
        node_alias="pa04_target_node", policy_tag=policy_tag, owner_user_id=owner
    )
    edge_refs = (
        f"SELECT 'doc' AS kind, {ea}.source_document_id AS ref_id "
        f"WHERE {ea}.source_document_id IS NOT NULL "
        "UNION ALL "
        f"SELECT 'chunk', {ea}.chunk_id WHERE {ea}.chunk_id IS NOT NULL"
    )
    # An edge can inherit resolved provenance from its endpoints when it has
    # no own pointer. Any declared own pointer must nevertheless be checked.
    policy, policy_params = _source_policy_sql(
        document_alias="pa04_edge_doc", policy_tag=policy_tag, owner_user_id=owner
    )
    edge_relation = (
        f"FROM ({edge_refs}) pa04_edge_ref "
        "LEFT JOIN chunks pa04_edge_chunk ON pa04_edge_ref.kind = 'chunk' "
        "AND pa04_edge_chunk.chunk_id = pa04_edge_ref.ref_id "
        "LEFT JOIN documents pa04_edge_doc ON pa04_edge_doc.document_id = "
        "CASE WHEN pa04_edge_ref.kind = 'doc' THEN pa04_edge_ref.ref_id "
        "ELSE pa04_edge_chunk.document_id END"
    )
    edge_invalid = (
        f" AND NOT EXISTS (SELECT 1 {edge_relation} WHERE "
        "pa04_edge_ref.ref_id IS NULL OR trim(pa04_edge_ref.ref_id) = '' "
        "OR pa04_edge_doc.document_id IS NULL "
        f"OR ({policy}) IS NOT TRUE)"
    )
    sql = (
        owner_sql
        + f" AND EXISTS (SELECT 1 FROM nodes pa04_source_node WHERE "
        f"pa04_source_node.node_id = {ea}.source_node_id{source_node_sql})"
        + f" AND EXISTS (SELECT 1 FROM nodes pa04_target_node WHERE "
        f"pa04_target_node.node_id = {ea}.target_node_id{target_node_sql})"
        + edge_invalid
    )
    return sql, [*owner_params, *source_node_params, *target_node_params, *policy_params]


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
