"""Conformance harness — makes "no product forks a contract" enforceable.

``verify_conformance(impl, contract)`` is the entry point SPR-08's CI gate
calls. Given a product's *actual* implementation (an instance, a class, or a
dict-shaped record) and a contract (a Pydantic model class from this package),
it checks the implementation structurally satisfies the contract — a
**duck-typed** check (does it carry the required fields?), not a nominal one
(it need not inherit the contract).

Why structural: the products implement their primitives as frozen dataclasses
(``ExtractedNote``, ``StepEvent``, ``AccrualLine``), not as subclasses of these
Pydantic contracts. Nominal checking would force an inheritance the
architecture deliberately avoids. Structural checking asks the only question
that matters: *can a consumer that expects the contract read this object?*

A divergence fails loudly with a field-level diff so the SPR-08 CI log says
exactly which field a product dropped or renamed — the difference between a
useful gate and an inscrutable one.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class ConformanceResult:
    """The outcome of one conformance check. ``ok`` is the gate signal;
    ``missing`` / ``extra`` drive the human-readable ``diff``."""

    ok: bool
    contract: str
    impl: str
    missing: tuple[str, ...]
    diff: str

    def __bool__(self) -> bool:
        return self.ok


def _required_fields(contract: type[BaseModel]) -> set[str]:
    """The field names a conforming implementation must carry. Fields with a
    default are still part of the shape a consumer may read, so we require all
    declared fields — a missing field means a consumer would get ``None`` or an
    ``AttributeError`` it did not expect."""
    return set(contract.model_fields.keys())


def _impl_fields(impl: Any) -> set[str]:
    """The field names an implementation exposes — supporting an instance
    (attributes / dataclass fields), a class (annotations), or a dict
    (keys)."""
    if isinstance(impl, dict):
        return set(impl.keys())
    # dataclass instance or class
    dc_fields = getattr(impl, "__dataclass_fields__", None)
    if dc_fields is not None:
        return set(dc_fields.keys())
    # pydantic model instance or class — read fields off the class (accessing
    # ``model_fields`` on an instance is deprecated in Pydantic 2.11+).
    cls = impl if isinstance(impl, type) else type(impl)
    mf = getattr(cls, "model_fields", None)
    if isinstance(mf, dict):
        return set(mf.keys())
    # plain object — annotations + public attributes
    ann = set(getattr(impl, "__annotations__", {}).keys())
    attrs = {a for a in dir(impl) if not a.startswith("_")}
    return ann | attrs


def _impl_name(impl: Any) -> str:
    if isinstance(impl, type):
        return impl.__name__
    if isinstance(impl, dict):
        return "dict"
    return type(impl).__name__


def verify_conformance(impl: Any, contract: type[BaseModel]) -> ConformanceResult:
    """Check ``impl`` structurally satisfies ``contract``. Returns a
    :class:`ConformanceResult` (falsy on failure). The implementation may carry
    *extra* fields — a superset conforms — but it may not be *missing* any
    contract field."""
    required = _required_fields(contract)
    present = _impl_fields(impl)
    missing = required - present
    extra = present - required

    if not missing:
        diff = f"OK: {_impl_name(impl)} satisfies {contract.__name__}"
        if extra:
            diff += f" (extra fields, allowed: {sorted(extra)})"
        return ConformanceResult(True, contract.__name__, _impl_name(impl), (), diff)

    lines = [
        f"FAIL: {_impl_name(impl)} does not satisfy {contract.__name__}",
        f"  missing fields: {sorted(missing)}",
        f"  contract requires: {sorted(required)}",
        f"  impl provides:     {sorted(present)}",
    ]
    return ConformanceResult(
        False, contract.__name__, _impl_name(impl), tuple(sorted(missing)), "\n".join(lines)
    )


def assert_conformance(impl: Any, contract: type[BaseModel]) -> None:
    """Raise ``ConformanceError`` with the diff if ``impl`` does not satisfy
    ``contract``. The form a CI gate or a test calls when divergence should be
    a hard failure."""
    result = verify_conformance(impl, contract)
    if not result.ok:
        raise ConformanceError(result.diff)


class ConformanceError(AssertionError):
    """Raised by :func:`assert_conformance` when an implementation diverges
    from its contract."""
