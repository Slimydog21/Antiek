"""Publisher §9.10 opt-in intake — the one LEGITIMATE servable-by-grant lane.

A publisher submits their OWN catalog with an explicit, dated serving grant;
the granted works ingest as ``opt_in_licensed`` (servable) with the grant
recorded as ``license_basis`` and escrow accruing to the publisher's
``ip_holder``. A manifest entry WITHOUT a valid grant (absent / empty /
out-of-scope / withdrawn / expired) stays ``restricted_pending_opt_in``
(gated) by §9.0 deny-by-default — its body is still chunked + embedded for
private search but is NEVER served. This lane is categorically distinct from
the scraped, gated-only intake (SPR-02); the GRANT is the single field that
flips a work servable.

THE BINDING (load-bearing): every content_class decision in this lane routes
through ``acquisition.licenses_core.classify(...)`` — the one chokepoint. The
grant becomes ``source_declaration['publisher_grant']`` -> classify() branch 1
-> ``opt_in_licensed``; an entry whose grant fails validation is handed to
classify() WITHOUT a ``publisher_grant`` (only the ``rights_holder`` name) so
it lands on the deny-by-default gated branch. No content_class is ever
hardcoded or assigned by any other route.
"""

from __future__ import annotations

from .intake import (
    IntakeResult,
    OptInIntakeSummary,
    WorkOutcome,
    ingest_entry,
    intake_manifest,
    intake_manifest_file,
    resolve_publisher_holder,
)
from .manifest import (
    GrantValidation,
    Manifest,
    ManifestEntry,
    PublisherIdentity,
    load_manifest,
    parse_manifest,
    validate_grant,
)

__all__ = [
    "IntakeResult",
    "OptInIntakeSummary",
    "WorkOutcome",
    "ingest_entry",
    "intake_manifest",
    "intake_manifest_file",
    "resolve_publisher_holder",
    "GrantValidation",
    "Manifest",
    "ManifestEntry",
    "PublisherIdentity",
    "load_manifest",
    "parse_manifest",
    "validate_grant",
]
