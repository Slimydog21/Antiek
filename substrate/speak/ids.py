"""Speak — id generators.

Reuses the graph substrate's ``<prefix>-<16hex>`` convention
(``content_addressed_id`` for stable identity, ``new_random_id`` for
fresh ids). Claims are content-addressed on (project, interviewee,
text) so the same statement from the same interviewee dedupes rather
than double-counting in the corroboration + economics layers.
"""

from __future__ import annotations

from substrate.graph.ops import content_addressed_id, new_random_id


def new_claim_id(project_id: str, text: str, interview_id: str | None) -> str:
    seed = f"{project_id}|{interview_id or '__operator__'}|{text.strip()}"
    return content_addressed_id("clm", seed)


def new_cluster_id(project_id: str, canonical_text: str) -> str:
    return content_addressed_id("clstr", f"{project_id}|{canonical_text.strip()}")


def new_invite_id() -> str:
    return new_random_id("inv")


def new_publication_id() -> str:
    return new_random_id("pub")


def new_takedown_id() -> str:
    return new_random_id("tkd")


def new_accrual_id() -> str:
    return new_random_id("acr")


def new_order_id() -> str:
    return new_random_id("ord")
