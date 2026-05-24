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
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, ConfigDict

__all__ = [
    "SubstrateError",
    "BudgetExceeded",
    "SchemaMismatch",
    "UpstreamUnavailable",
    "VerifierTimeout",
    "WriterContended",
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


SubstrateError = Union[
    BudgetExceeded,
    SchemaMismatch,
    UpstreamUnavailable,
    VerifierTimeout,
    WriterContended,
]
