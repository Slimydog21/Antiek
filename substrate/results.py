"""Result[T, E] — explicit success/failure return for substrate boundaries.

Antiek's analog to Rust's ``Result<T, E>``. Functions that may fail return a
``Result`` rather than raising; callers handle both arms explicitly via
structural ``match``. System failures (OOM, KeyboardInterrupt, programmer-error
invariants) keep exception flow — that distinction is the substrate
``error-channel rule`` documented in
``docs/decisions/are-wave-1-substrate-additive.md``.

The encoding is a Pydantic-v2 discriminated union over two classes — ``Ok``
and ``Err`` — discriminated on a ``tag`` literal. This was chosen over the
``returns`` library because Pydantic serialization is already the wire format
on every cross-module hand-off in the substrate; introducing a parallel
serialization surface would have multiplied the round-trip cost without
buying anything mypy didn't already give us.

Why a Pydantic pair instead of a frozen dataclass:

1. Cross-module flows (event_log rows, dispatch envelopes) already
   round-trip through Pydantic; an Ok/Err pair fits without a custom
   encoder.
2. ``__match_args__`` is generated automatically from the field set, so
   ``case Ok(value=v):`` and ``case Err(error=e):`` work out of the box.
3. The ``tag`` literal gives mypy structural narrowing inside a ``match``
   block, the same way the existing ``ActionType``-discriminated ``Event``
   union narrows.

Example::

    from substrate.results import Ok, Err, Result
    from substrate.errors import SubstrateError, BudgetExceeded

    def charge(amount: int, budget: int) -> Result[int, SubstrateError]:
        if amount > budget:
            return Err(error=BudgetExceeded(cap=budget, attempted=amount))
        return Ok(value=budget - amount)

    match charge(150, 100):
        case Ok(value=remaining):
            ...  # remaining is int
        case Err(error=e):
            ...  # e is SubstrateError

The module is fully ``mypy --strict`` clean and depends only on stdlib +
``pydantic>=2.7`` (already in core deps).
"""

from __future__ import annotations

from typing import Any, Callable, Generic, Literal, TypeVar, Union

from pydantic import BaseModel, ConfigDict

__all__ = [
    "Ok",
    "Err",
    "Result",
    "ResultUnwrapError",
    "is_ok",
    "is_err",
]


T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


class ResultUnwrapError(RuntimeError):
    """Raised when ``.unwrap()`` is called on an ``Err``.

    This is a *programmer-error* signal, not a runtime-error path. If a
    caller reaches ``.unwrap()`` on an ``Err``, they have skipped handling
    the failure arm — that is a bug in the caller, not a recoverable
    condition. Use ``.unwrap_or(default)`` or pattern-match instead.

    Carries the original ``error`` payload as ``.inner`` so debuggers don't
    lose the failure context.
    """

    def __init__(self, error: Any) -> None:
        super().__init__(
            f"unwrap() called on Err — caller did not handle the failure arm. "
            f"Inner error: {error!r}. Use .unwrap_or(default) or pattern-match."
        )
        self.inner = error


class Ok(BaseModel, Generic[T]):
    """The success arm of a ``Result``. Construct as ``Ok(value=...)`` or
    ``Ok(<positional>)`` (Pydantic accepts both)."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    tag: Literal["ok"] = "ok"
    value: T

    # ------------------------------------------------------------------ #
    # Predicates                                                         #
    # ------------------------------------------------------------------ #

    def is_ok(self) -> bool:
        return True

    def is_err(self) -> bool:
        return False

    # ------------------------------------------------------------------ #
    # Extractors                                                         #
    # ------------------------------------------------------------------ #

    def unwrap(self) -> T:
        """Return the inner value. Safe on Ok; raises on Err."""
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value

    def unwrap_or_else(self, fn: Callable[[Any], T]) -> T:
        return self.value

    # ------------------------------------------------------------------ #
    # Combinators                                                        #
    # ------------------------------------------------------------------ #

    def map(self, fn: Callable[[T], U]) -> "Ok[U]":
        """Apply ``fn`` to the inner value; return a new Ok wrapping the
        result. Err passes through unchanged via the sibling method."""
        return Ok(value=fn(self.value))

    def map_err(self, fn: Callable[[Any], Any]) -> "Ok[T]":
        """No-op on Ok — Err carries the error and Ok doesn't."""
        return self

    def and_then(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        """Monadic bind — chain a fallible operation onto a successful result.
        ``fn`` returns a Result; we delegate to it. The classic ``?`` operator
        in Rust collapses to nested ``and_then`` calls in this idiom."""
        return fn(self.value)


class Err(BaseModel, Generic[E]):
    """The failure arm of a ``Result``. Construct as ``Err(error=...)`` or
    ``Err(<positional>)``."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    tag: Literal["err"] = "err"
    error: E

    # ------------------------------------------------------------------ #
    # Predicates                                                         #
    # ------------------------------------------------------------------ #

    def is_ok(self) -> bool:
        return False

    def is_err(self) -> bool:
        return True

    # ------------------------------------------------------------------ #
    # Extractors                                                         #
    # ------------------------------------------------------------------ #

    def unwrap(self) -> Any:
        """Always raises. Calling ``.unwrap()`` on an Err is a programmer
        error — handle the failure arm instead."""
        raise ResultUnwrapError(self.error)

    def unwrap_or(self, default: T) -> T:
        return default

    def unwrap_or_else(self, fn: Callable[[E], T]) -> T:
        return fn(self.error)

    # ------------------------------------------------------------------ #
    # Combinators                                                        #
    # ------------------------------------------------------------------ #

    def map(self, fn: Callable[[Any], Any]) -> "Err[E]":
        """No-op on Err — the value isn't there to map."""
        return self

    def map_err(self, fn: Callable[[E], F]) -> "Err[F]":
        """Apply ``fn`` to the inner error; return a new Err. Useful for
        translating error variants (e.g., adapter error → SubstrateError)."""
        return Err(error=fn(self.error))

    def and_then(self, fn: Callable[[Any], "Result[U, E]"]) -> "Err[E]":
        """Short-circuit — the chain stops at the first Err."""
        return self


# The Result alias. mypy reads the ``tag`` literal as the discriminator and
# narrows correctly inside ``match`` blocks.
Result = Union[Ok[T], Err[E]]


# ---------------------------------------------------------------------- #
# Free-function predicates                                               #
#                                                                        #
# Methods on Ok/Err cover the common case, but free functions are easier #
# to compose with ``filter`` / ``map`` over heterogeneous sequences.     #
# ---------------------------------------------------------------------- #


def is_ok(result: "Result[T, E]") -> bool:
    return isinstance(result, Ok)


def is_err(result: "Result[T, E]") -> bool:
    return isinstance(result, Err)
