"""arXiv per-paper license URI → Antiek servable-class mapping.

THE LOAD-BEARING INVARIANT (hard-to-vary): *no paper is ever served on a
license Antiek does not actually hold.* arXiv hosting a paper is NOT a
redistribution right — the right comes from the paper's declared license.
Unknown / unmatched / missing license → GATED, never servable.

The Creative-Commons semantics (5 of the 6 rows below) are NOT arXiv-specific
— they live in ``acquisition.licenses_core`` so every source (arXiv, the
open-access aggregators) resolves CC the same way; a CC license is a legal
determination with exactly one home. This module adds ONLY the one
arXiv-specific row (the ``arxiv.org/licenses/nonexclusive-distrib`` default
terms) and composes the arXiv table from it + the shared CC rows.

The mapping is a DATA TABLE, not scattered conditionals, so a reviewer reads
ONE table and sees which licenses are servable and why.

The set of license URIs arXiv actually emits (the
``{http://arxiv.org/schemas/atom}license`` element):
https://info.arxiv.org/help/license/index.html
"""

from __future__ import annotations

from typing import Optional

from substrate.constants import GATED_DEFAULT_CONTENT_CLASS

# Re-export the generic primitives so existing arXiv importers
# (``acquisition.arxiv.adapter`` imports ``license_basis_string`` +
# ``resolve_license`` from here; ``acquisition.arxiv.__init__`` re-exports
# ``LicenseResolution``) keep working unchanged after the extraction.
from acquisition.licenses_core import (  # noqa: F401
    CC_LICENSE_ROWS,
    LicenseResolution,
    LicenseRow,
    license_basis_string,
    resolve_against_table,
)

# arXiv's default "non-exclusive license to distribute". This lets arXiv host
# the paper; the AUTHOR retains copyright. NO grant to Antiek. This is the
# most common arXiv license and the one most likely to be mistaken for "free
# to serve" — the one row that is genuinely arXiv-specific.
ARXIV_NONEXCLUSIVE_ROW: LicenseRow = LicenseRow(
    match="arxiv.org/licenses/nonexclusive-distrib",
    content_class=GATED_DEFAULT_CONTENT_CLASS,
    redistributable=False,
    license_name="arXiv non-exclusive license to distribute",
    rationale=(
        "Grants arXiv hosting only; author retains copyright; no "
        "redistribution grant to Antiek -> gated."
    ),
)

# The arXiv table: the one source-specific row + the shared CC rows. The CC
# rows carry their own NC/ND-before-BY safety ordering; the arXiv row's
# fragment doesn't collide with any CC fragment, so it sits first harmlessly.
_LICENSE_TABLE: tuple[LicenseRow, ...] = (ARXIV_NONEXCLUSIVE_ROW,) + CC_LICENSE_ROWS


def resolve_license(license_uri: Optional[str]) -> LicenseResolution:
    """Map an arXiv license URI to a servable-class resolution.

    Deny-by-default: a ``None`` / empty / unmatched URI resolves to
    ``GATED_DEFAULT_CONTENT_CLASS`` with ``redistributable=False`` — an
    unknown license is NEVER guessed servable.
    """
    return resolve_against_table(license_uri, _LICENSE_TABLE)
