"""result_helpers — paved-path adapters for adopting Result at boundaries.

ARE-02 milestone 3 (canonical examples), of the Antiek Rust-Execution
Spec. These are NEW pure helpers that demonstrate AND enable the
raise→Result migration WITHOUT modifying any existing call site. A
substrate boundary migrating to ``Result[T, SubstrateError]`` imports
these instead of hand-rolling a try/except → Err translation each time.

The design principle (the PostHog "paved road"): make the safe path the
easy path. A caller that wants to stop raising and start returning Result
should reach for ``try_decode_json`` / ``try_parse_model`` /
``checked_budget_charge`` / ``try_call`` rather than reinventing the
translation — so every migrated boundary produces the same, richly-typed
``SubstrateError`` variants.

Why these four:

- ``try_decode_json`` — the single most common raise-on-failure stdlib
  call in the substrate (every LLM/API response that's parsed). Wraps
  ``json.loads`` → ``Err(SchemaMismatch)``.
- ``try_parse_model`` — every cross-module Pydantic hand-off. Wraps
  ``model_validate`` → ``Err(SchemaMismatch)`` with the first error's
  location + type extracted.
- ``checked_budget_charge`` — the canonical *pure-function* boundary:
  no I/O, no exception to catch, just an invariant (never overspend)
  expressed as Ok/Err. Demonstrates that Result isn't only for
  exception-wrapping.
- ``try_call`` — the general escape hatch: run any thunk, translate any
  Exception into a SubstrateError via a caller-supplied ``on_error``.
  Prefer the specific helpers where they fit; ``try_call`` is for the
  long tail.

All four are ``mypy --strict`` clean and pure (``checked_budget_charge``
is referentially transparent; the others are pure given their inputs +
the wrapped call's determinism).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from substrate.errors import (
    BudgetExceeded,
    SchemaMismatch,
    SubstrateError,
)
from substrate.results import Err, Ok, Result

__all__ = [
    "try_decode_json",
    "try_parse_model",
    "checked_budget_charge",
    "try_call",
]

T = TypeVar("T")
M = TypeVar("M", bound=BaseModel)

# Producers truncate repr fields to keep SchemaMismatch.actual_repr from
# carrying an unbounded payload into logs / event_log rows. 200 chars is
# the convention established in substrate/errors.py's docstring.
_REPR_TRUNCATE = 200


def try_decode_json(
    raw: str, *, schema_version: int = 0
) -> Result[Any, SubstrateError]:
    """Decode JSON, returning ``Err(SchemaMismatch)`` instead of raising
    ``json.JSONDecodeError``.

    The canonical example of wrapping a stdlib raise-on-failure call in
    a Result return. A boundary that currently does
    ``data = json.loads(raw)`` (and lets the decode error propagate)
    migrates to ``match try_decode_json(raw): case Ok(value=data): ...``.

    >>> from substrate.results import Ok, Err
    >>> isinstance(try_decode_json('{"a": 1}'), Ok)
    True
    >>> isinstance(try_decode_json('not json'), Err)
    True
    """
    try:
        return Ok(value=json.loads(raw))
    except json.JSONDecodeError:
        return Err(
            error=SchemaMismatch(
                field="<json-root>",
                expected_type="valid-json",
                actual_repr=raw[:_REPR_TRUNCATE],
                schema_version=schema_version,
            )
        )


def try_parse_model(
    model_cls: type[M], data: Any, *, schema_version: int = 0
) -> Result[M, SubstrateError]:
    """Validate ``data`` into a Pydantic model, returning
    ``Err(SchemaMismatch)`` on ``ValidationError`` instead of raising.

    The first validation error's location + type are extracted into the
    SchemaMismatch so the failure is debuggable without re-running. If
    the error list is empty (shouldn't happen, but Pydantic's API allows
    it), falls back to a root-level mismatch.
    """
    try:
        return Ok(value=model_cls.model_validate(data))
    except ValidationError as exc:
        errors = exc.errors()
        if errors:
            first = errors[0]
            loc_parts = first.get("loc", ())
            loc = ".".join(str(p) for p in loc_parts) if loc_parts else "<root>"
            expected_type = str(first.get("type", "unknown"))
            actual_repr = repr(first.get("input", ""))[:_REPR_TRUNCATE]
        else:
            # Pydantic's API allows an empty error list in principle;
            # fall back to a root-level mismatch rather than index [0].
            loc, expected_type, actual_repr = "<root>", "unknown", ""
        return Err(
            error=SchemaMismatch(
                field=loc,
                expected_type=expected_type,
                actual_repr=actual_repr,
                schema_version=schema_version,
            )
        )


def checked_budget_charge(
    current_spend: int, amount: int, cap: int, *, units: str = "tokens"
) -> Result[int, SubstrateError]:
    """Charge ``amount`` against a budget. Returns ``Ok(new_spend)`` or
    ``Err(BudgetExceeded)``.

    The canonical *pure-function* boundary — no I/O, no exception to
    catch, just an invariant (never overspend) expressed as Ok/Err. This
    is the shape an ARE-04 dispatch-budget handle would return from its
    ``write()`` path. Negative amounts (refunds/credits) are permitted;
    only the cap is enforced.

    >>> from substrate.results import Ok, Err
    >>> checked_budget_charge(50, 30, 100).unwrap()
    80
    >>> isinstance(checked_budget_charge(50, 60, 100), Err)
    True
    """
    new_spend = current_spend + amount
    if new_spend > cap:
        return Err(
            error=BudgetExceeded(cap=cap, attempted=new_spend, units=units)
        )
    return Ok(value=new_spend)


def try_call(
    fn: Callable[[], T],
    *,
    on_error: Callable[[Exception], SubstrateError],
) -> Result[T, SubstrateError]:
    """Run ``fn``; on any ``Exception``, translate it via ``on_error``
    into an ``Err``. The general escape hatch for the long tail of
    raise-on-failure calls that don't fit the specific helpers above.

    Prefer ``try_decode_json`` / ``try_parse_model`` where they fit —
    they produce richer typed errors. Reach for ``try_call`` when the
    wrapped operation is bespoke (a third-party SDK call, a subprocess)
    and you want to map its exceptions onto a SubstrateError variant.

    Note: this catches ``Exception`` (not ``BaseException``) — so
    ``KeyboardInterrupt`` / ``SystemExit`` propagate as they should.
    The blind-except is deliberate (it's the whole point of a boundary
    adapter) and is the one place in the substrate where catch-all is
    correct.
    """
    try:
        return Ok(value=fn())
    except Exception as exc:  # noqa: BLE001 — deliberate boundary adapter
        return Err(error=on_error(exc))
