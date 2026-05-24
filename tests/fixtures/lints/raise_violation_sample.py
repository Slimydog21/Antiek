"""Fixture for no_raise_in_substrate_writers lint tests."""

from __future__ import annotations


class CustomDomainError(Exception):
    pass


class UnstableThing(Exception):
    pass


def writes_with_violation() -> None:
    raise CustomDomainError("forbidden")


def writes_with_other_violation(x: int) -> None:
    if x < 0:
        raise UnstableThing("bad input")


def system_failure_is_allowed() -> None:
    raise OSError("disk full")


def programmer_error_is_allowed(value: int) -> None:
    assert value > 0
    if value > 1000:
        raise NotImplementedError("not yet")


def bare_reraise_is_allowed() -> None:
    try:
        risky_call()
    except Exception:
        raise


def risky_call() -> None:
    pass
