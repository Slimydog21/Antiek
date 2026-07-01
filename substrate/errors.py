"""SubstrateError — the typed error variants returned across substrate
boundaries.

Companion to ``substrate/results.py``. Every variant is a Pydantic model
discriminated on a ``kind`` field; the union ``SubstrateError`` is the
``E`` parameter in ``Result[T, SubstrateError]`` for substrate-boundary
functions.

The seed set covers the failure modes that already exist in the codebase
and have been hand-rolled as exception types or ad-hoc ``(value, error)``
tuples. Adding a new variant is intentionally cheap: define a Pydantic
model with ``kind: Literal["new_kind"]`` and add it to the ``SubstrateError``
union below. Every site that ``match``-es on ``SubstrateError`` will then
either handle it or be flagged exhaustively by ``mypy --strict`` (via
``typing.assert_never``).

Variants are alphabetical by ``kind`` to make the union readable. New
variants extend the union; do not reorder for "logical grouping" — the
alphabetical convention is the schelling point that prevents merge
conflicts when two sessions add variants in parallel.

Examples (run as doctests via ``pytest --doctest-modules substrate/errors.py``):

    >>> from substrate.errors import BudgetExceeded, WriterContended
    >>> err = BudgetExceeded(cap=100, attempted=150)
    >>> err.kind
    'budget_exceeded'
    >>> err.cap, err.attempted, err.units
    (100, 150, 'tokens')
    >>> WriterContended(resource='syntheses', timeout_s=300.0).kind
    'writer_contended'
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SubstrateError",
    "BudgetExceeded",
    "SchemaMismatch",
    "UpstreamUnavailable",
    "VerifierTimeout",
    "WriterContended",
    "RetrieverInfraError",
    "is_expected_degradation",
]


class _ErrorBase(BaseModel):
    """Shared config — frozen (errors are values; never mutate after
    creation) and arbitrary types allowed so payload fields can be plain
    dataclasses if needed."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)


class BudgetExceeded(_ErrorBase):
    """A spend exceeded the configured budget cap.

    Returned by dispatch budget operations when an attempted call would
    push the running total past the allotted cap. Includes the cap and
    the attempted amount so the caller can decide whether to back off,
    retry with a smaller scope, or surface to the operator.
    """

    kind: Literal["budget_exceeded"] = "budget_exceeded"
    cap: int
    attempted: int
    units: str = "tokens"


class SchemaMismatch(_ErrorBase):
    """A value did not conform to the expected schema.

    Returned by substrate writers when the input does not match the
    schema_version they expect. Carries the field name, the expected
    type, and the actual type/value so debugging does not require
    re-running with prints. ``actual_repr`` is a ``repr()`` of the
    offending value (truncated to 200 chars in producers).
    """

    kind: Literal["schema_mismatch"] = "schema_mismatch"
    field: str
    expected_type: str
    actual_repr: str
    schema_version: int


class UpstreamUnavailable(_ErrorBase):
    """An external upstream (LLM API, search API, ingestion source) was
    unavailable.

    Distinguishes a *contract-level* failure (the upstream is unreachable
    or returned an explicit error) from a *substrate-internal* failure
    (writer contention, schema drift). Carries the upstream name + an
    optional HTTP status code or reason string.
    """

    kind: Literal["upstream_unavailable"] = "upstream_unavailable"
    upstream: str
    status_code: int | None = None
    reason: str | None = None


class VerifierTimeout(_ErrorBase):
    """A verifier did not return within its deadline.

    Returned by the verifier dispatch path when a verifier exceeds its
    configured timeout. Carries the verifier name and the elapsed seconds
    so the operator can decide whether to extend the timeout, change the
    verifier, or treat the timeout as a soft-fail outcome.
    """

    kind: Literal["verifier_timeout"] = "verifier_timeout"
    verifier: str
    elapsed_s: float
    timeout_s: float


class WriterContended(_ErrorBase):
    """A writer could not acquire the resource lock within the timeout.

    The substrate's single-writer invariant means writes are serialized.
    When acquire-timeouts happen, the substrate distinguishes
    "legitimately busy" from "abandoned lock" via the PID stamp on the
    sidecar lock (see ``runtime/db_lock.py``). This variant carries the
    resource name, the holder PID (if known), and the timeout that
    elapsed.
    """

    kind: Literal["writer_contended"] = "writer_contended"
    resource: str
    holder_pid: int | None = None
    timeout_s: float = 0.0


SubstrateError = (
    BudgetExceeded
    | SchemaMismatch
    | UpstreamUnavailable
    | VerifierTimeout
    | WriterContended
)


# ---------------------------------------------------------------------------
# Raisable infra error (nygard SPR-02, I-LOUD)
# ---------------------------------------------------------------------------
#
# Design note (reconciling the spec with the code): the ``SubstrateError`` union
# above is a set of Pydantic *value* types — the ``E`` in ``Result[T, E]``, used
# as ``Err(SchemaMismatch(...))`` — not exceptions. The nygard SPR-02 spec asks
# for a typed error that is BOTH added to "the SubstrateError hierarchy" AND
# "caught by ``except SubstrateError``" and chained via ``raise ... from``. Those
# are exception semantics, which the value-union cannot carry (a Pydantic model
# is not a ``BaseException``). Rather than break every ``Result[T, SubstrateError]``
# consumer by turning the union into an exception hierarchy, we add a *raisable*
# error here, following the codebase's own idiom for raisable errors
# (``ProviderError(Exception)``, ``AIActionError(Exception)``, ...). It composes
# with ``Result`` via ``Err(error=RetrieverInfraError(...))`` (``Err.error`` is an
# unconstrained ``E``) and is caught with ``except RetrieverInfraError``.


class RetrieverInfraError(Exception):
    """A typed, raisable INFRASTRUCTURE fault at a retrieval/retriever seam.

    This is the fail-loud carrier for I-LOUD: an *unexpected infra fault* — an
    ``OSError`` writing a cache/index, a locked-DB timeout, a disk-full, a
    missing-extension hard fail — surfaces as this typed error instead of being
    silently masked into a benign degradation (a brute-force fallback, an
    ``insufficient_evidence`` Delivered, etc.). It is explicitly NOT for
    *expected* degradations (a missing provider key, a model-side parse failure,
    a model-asserted "insufficient evidence", or a genuinely unavailable optional
    feature) — those keep their existing benign behavior. See
    :func:`is_expected_degradation`.

    Carries enough context to debug without a re-run: the ``seam`` name, the
    original exception (``cause`` — also set as ``__cause__`` when raised via
    ``raise RetrieverInfraError(...) from exc``), and its ``errno`` when the
    cause was an ``OSError`` (so ``EROFS`` is visible in the message).

    Examples (doctests via ``pytest --doctest-modules substrate/errors.py``):

        >>> import errno as _e
        >>> try:
        ...     raise OSError(_e.EROFS, "Read-only file system", "/x")
        ... except OSError as exc:
        ...     err = RetrieverInfraError("vss index copy failed",
        ...                               seam="retrieval_substrate.vss_copy",
        ...                               cause=exc)
        >>> err.seam
        'retrieval_substrate.vss_copy'
        >>> err.errno == _e.EROFS
        True
        >>> isinstance(err, Exception)
        True
    """

    def __init__(
        self,
        message: str,
        *,
        seam: str,
        cause: BaseException | None = None,
    ) -> None:
        self.seam = seam
        self.cause = cause
        # Surface the errno when the underlying fault was an OSError, so EROFS /
        # ENOSPC / EACCES are visible without unwrapping the chain.
        self.errno = getattr(cause, "errno", None) if cause is not None else None
        detail = f" [errno={self.errno}]" if self.errno is not None else ""
        super().__init__(f"{seam}: {message}{detail}")


def is_expected_degradation(exc: BaseException) -> bool:
    """Is ``exc`` an EXPECTED, named degradation (keep benign) or an infra fault
    (surface as :class:`RetrieverInfraError`)?

    The closed list of expected conditions is deliberately small and explicit —
    extend it with a code change + comment, never by silently broadening a catch.
    Everything NOT on this list (notably ``OSError``) is an infra fault.

    Expected (benign) today:
    - ``substrate.dispatch.base.ProviderError`` — a named upstream/provider
      condition (missing key, upstream error) the dispatch fallback already owns.
    - ``KeyError`` — an unregistered provider (route-override with no key), a
      recoverable fallback trigger.
    - ``roles.evidence_retriever.EvidenceValidationError`` — a model-side parse /
      validation failure (the response, not the infra).

    A :class:`RetrieverInfraError` itself is already typed infra — not "expected".
    """
    if isinstance(exc, RetrieverInfraError):
        return False
    # Named expected conditions, imported lazily to avoid import cycles.
    try:
        from substrate.dispatch.base import ProviderError

        if isinstance(exc, ProviderError):
            return True
    except Exception:  # pragma: no cover - dispatch always importable in practice
        pass
    try:
        from roles.evidence_retriever import EvidenceValidationError

        if isinstance(exc, EvidenceValidationError):
            return True
    except Exception:  # pragma: no cover
        pass
    return isinstance(exc, KeyError)
