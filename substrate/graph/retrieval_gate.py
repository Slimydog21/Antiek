"""Canonical retrieval-time chunk gate (master-spec §9.0 + Personal-Reading Lane).

This module is the **only** place that formats the non-privileged chunk-gate
SQL fragment. ``search()`` and later surfaces (VSS, HTTP) must import
``non_privileged_chunk_sql_clause`` — never hand-roll ``NOT IN
(RESTRICTED_CONTENT_CLASSES)`` alone.

**RESTRICTED_CONTENT_CLASSES alone is never sufficient** for chunk gates:
owner-only ``personal_reading`` must be excluded on the same non-privileged
branch as gated-but-public ``restricted_pending_opt_in``. The union is
``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES``.
"""

from __future__ import annotations

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
    "restricted_pending_opt_in",
})

# Content classes that are OWNER-ONLY: the owner reads them in full on a
# privileged path, but they NEVER surface on a non-privileged (public /
# attribution-eligible) retrieval. personal_reading (the Personal-Reading Lane
# SPR-01 fourth rights state) is the only member: it is the owner's private
# third-party reading (a fetched essay / transcript / tweet) with no rights basis
# to serve publicly and — unlike restricted_pending_opt_in — no escrow economics
# at all (it never earns). It is kept as a SEPARATE set from
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
    "personal_reading",
})

# The full set of content classes withheld from a non-privileged retrieval —
# the union of the gated-but-public class and the owner-only class. Both are
# excluded on the public branch; only the PRIVILEGED_POLICY_TAGS bypass.
_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES: frozenset[str] = (
    RESTRICTED_CONTENT_CLASSES | PERSONAL_ONLY_CONTENT_CLASSES
)


def non_privileged_chunk_sql_clause(
    *,
    table_alias: str = "d",
    policy_tag: str = "attribution_eligible",
) -> tuple[str, list[str]]:
    """SQL fragment + bind params for the non-privileged chunk gate.

    On a non-privileged ``policy_tag``, returns a WHERE clause that excludes
    every member of ``_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES`` while still
    allowing NULL ``content_class`` (legacy/grandfathered rows). On a privileged
    tag (``private_research`` / ``operator_only``), returns ``("", [])``.

    Args:
        table_alias: Alias of the ``documents`` row in the query (default ``d``).
        policy_tag: Retrieval policy; only PRIVILEGED_POLICY_TAGS bypass the gate.
    """
    if policy_tag in PRIVILEGED_POLICY_TAGS:
        return "", []
    excluded = sorted(_NON_PRIVILEGED_EXCLUDED_CONTENT_CLASSES)
    placeholders = ",".join("?" for _ in excluded)
    sql = (
        f" AND ({table_alias}.content_class IS NULL OR "
        f"{table_alias}.content_class NOT IN ({placeholders}))"
    )
    return sql, excluded