"""Per-batch rights audit — the reproducible artifact behind the §9.0 claim
(SPR-02 M5).

The orchestrator runs this over every ingested batch (and SPR-10 runs the
same logic standing) to PROVE, not assert, two zero-tolerance properties:

  (a) **No servable work without a license basis.** Every work the §9.0 gate
      would serve full text MUST carry a non-empty ``license_basis`` — the
      defensible record a lawyer reads months later ("public_domain: US
      pre-1929", "CC BY (…)"). A servable row with an empty basis is a
      ``missing_license_basis`` violation.

  (b) **No gated body reachable through the public serve path.** A work whose
      ``content_class`` is GATED (``restricted_pending_opt_in`` / taken-down /
      unknown — i.e. NOT in SERVABLE_CONTENT_CLASSES) MUST NOT have its full
      body come back from the public full-text serve path. A gated-by-class row
      whose body the serve path returns is a ``gated_body_reachable`` violation.

This module VERIFIES; it does not re-classify. It derives the EXPECTED gated /
servable status from ``content_class`` through the SAME projection the gate
uses (``substrate.books.servability.servability_of``), then cross-checks it
against what the public serve path actually returns. A row whose CLASS says
gated but whose BODY the serve path nonetheless hands back is the exact drift
the audit exists to catch — the cross-check is genuine precisely because the
two sides come from different places (the stored class vs the served bytes).

A SINGLE violation of either property fails the whole batch (``passed=False``).
The result carries the counts + the list of violating ids + per-id reasons so
the failure is actionable, and re-running the audit on the same batch
reproduces the verdict (defensibility — the claim is checkable, not trusted).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from substrate.books.servability import is_servable_full_text, servability_of
from substrate.books.serve import ServeResult, serve_full_text

# Violation reason tokens. Stable strings the orchestrator + SPR-10 + the test
# suite key off — named here so they have one home and can't drift per-caller.
REASON_MISSING_LICENSE_BASIS = "missing_license_basis"
REASON_GATED_BODY_REACHABLE = "gated_body_reachable"

# The probe that fetches what the public serve path returns for a document.
# Defaults to the real serve path; injectable so a test can model a leaky serve
# (and so SPR-10 can point it at the live path) without re-implementing the gate.
ServeProbe = Callable[[Any, str], ServeResult]


@dataclass(frozen=True)
class RightsViolation:
    """One audited row that violated a zero-tolerance property."""

    document_id: str
    reason: str
    detail: str


@dataclass(frozen=True)
class RightsAuditResult:
    """The reproducible verdict over one batch. ``passed`` is True iff there
    are zero violations of either property; a single violation fails the
    batch. The counts let the operator state the batch's shape; ``violations``
    makes the failure actionable."""

    passed: bool
    audited: int
    servable: int
    gated: int
    violations: list[RightsViolation] = field(default_factory=list)

    def violation_ids(self, reason: str | None = None) -> list[str]:
        """Document ids that violated, optionally filtered to one reason."""
        return [
            v.document_id
            for v in self.violations
            if reason is None or v.reason == reason
        ]


def audit_batch(
    con: Any,
    document_ids: Iterable[str],
    *,
    serve_probe: ServeProbe = serve_full_text,
) -> RightsAuditResult:
    """Audit a batch of document ids against the two §9.0 zero-tolerance
    properties.

    For each document:
      - Read its stored ``content_class`` and derive the EXPECTED status via
        ``servability_of`` (the authoritative projection).
      - Probe the public serve path (``serve_probe``) for what body it returns.
      - If the class is SERVABLE, require a non-empty ``license_basis`` on the
        ``book_assets`` row, else flag ``missing_license_basis``.
      - If the class is GATED yet the serve path returned the full body, flag
        ``gated_body_reachable`` — the class and the served bytes disagree, and
        the gated body leaked.

    A document id with no ``documents`` row is skipped from the counts (the
    batch's membership is the caller's concern; the audit verifies what exists).
    """
    violations: list[RightsViolation] = []
    audited = servable = gated = 0

    for document_id in document_ids:
        row = con.execute(
            """
            SELECT d.content_class, COALESCE(b.taken_down, FALSE)
            FROM documents d
            LEFT JOIN book_assets b ON d.document_id = b.document_id
            WHERE d.document_id = ?
            """,
            [document_id],
        ).fetchone()
        if row is None:
            continue
        audited += 1
        content_class, taken_down = row[0], bool(row[1])
        status = servability_of(content_class, taken_down=taken_down)
        class_is_servable = is_servable_full_text(status)

        served = serve_probe(con, document_id)

        if class_is_servable:
            servable += 1
            basis = _license_basis_of(con, document_id)
            if not (basis and basis.strip()):
                violations.append(
                    RightsViolation(
                        document_id=document_id,
                        reason=REASON_MISSING_LICENSE_BASIS,
                        detail=(
                            f"servable work (content_class={content_class!r}, "
                            f"servability={status.value}) has no license_basis -- "
                            "a servable work must carry a basis a reviewer can read"
                        ),
                    )
                )
            continue

        # Gated by class: the serve path must NOT have returned the full body.
        gated += 1
        if served.full_text is not None:
            violations.append(
                RightsViolation(
                    document_id=document_id,
                    reason=REASON_GATED_BODY_REACHABLE,
                    detail=(
                        f"gated work (content_class={content_class!r}, "
                        f"servability={status.value}) returned full_text through "
                        "the public serve path -- the gated body leaked"
                    ),
                )
            )

    return RightsAuditResult(
        passed=not violations,
        audited=audited,
        servable=servable,
        gated=gated,
        violations=violations,
    )


def _license_basis_of(con: Any, document_id: str) -> Any:
    """Read the ``book_assets.license_basis`` for a document. None when the
    work has no book_assets row (it is then a servable work with no recorded
    basis -> a violation, which is the honest verdict)."""
    row = con.execute(
        "SELECT license_basis FROM book_assets WHERE document_id = ?",
        [document_id],
    ).fetchone()
    return row[0] if row is not None else None
