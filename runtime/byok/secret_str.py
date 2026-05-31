"""A redacting secret wrapper (Personal-Reading Lane / BYOK SPR-08).

``SecretStr`` holds a sensitive string (a BYOK X API key / bearer token) and
makes it *hard to leak by accident*. Its ``__repr__`` / ``__str__`` redact, so an
f-string, a ``print(...)``, a logger call, a traceback, or a ``%`` format that
includes the wrapper renders ``<SecretStr ***>`` instead of the plaintext. The
real value is reachable ONLY through the explicit :meth:`reveal` accessor — so a
leak requires a *deliberate* ``.reveal()`` at a call site a reviewer can grep
for, never an incidental string interpolation.

THREAT MODEL (stated plainly, per rigor #1 — what this defends and what it does
NOT):
  * DEFENDS — accidental log / event-log leakage. ``str()``/``repr()``/``format``
    of a ``SecretStr`` never yields the plaintext, so a stray log line or an
    ``emit_typed(...)`` payload that happens to carry the wrapper cannot print the
    key. (The byte-at-rest defense lives in ``store.py``.)
  * DOES NOT DEFEND — a process that already holds the revealed key in memory.
    Once ``.reveal()`` is called the plaintext is an ordinary ``str`` and root on
    the live box can read process memory. This wrapper raises the bar against
    *accidents*, not against an in-process adversary; do not overclaim it.

This is intentionally tiny and dependency-free: a leak-resistant container, not a
crypto primitive (encryption-at-rest is ``store.py``'s job).
"""

from __future__ import annotations

from typing import Any

_REDACTED = "<SecretStr ***>"


class SecretStr:
    """A string that refuses to print itself.

    ``str(SecretStr("abc")) == "<SecretStr ***>"`` (NOT ``"abc"``). The plaintext
    is reachable only via :meth:`reveal`. Equality compares the underlying
    secrets (so a round-trip can be asserted in a test) but the comparison never
    materialises the plaintext into a repr.
    """

    __slots__ = ("_secret",)

    def __init__(self, secret: str) -> None:
        if not isinstance(secret, str):
            raise TypeError("SecretStr wraps a str")
        object.__setattr__(self, "_secret", secret)

    def reveal(self) -> str:
        """Return the underlying plaintext. The ONE intentional egress — a
        reviewer greps for ``.reveal()`` to find every place the key is read."""
        return self._secret

    # ── leak-resistance: every stringification redacts ──────────────────────
    def __repr__(self) -> str:  # used by logging, tracebacks, %r, containers
        return _REDACTED

    def __str__(self) -> str:  # used by str(), f"{x}", print()
        return _REDACTED

    def __format__(self, spec: str) -> str:  # used by f"{x:...}"
        return _REDACTED

    # ── equality / hashing over the secret (so round-trips can be asserted) ──
    def __eq__(self, other: Any) -> bool:
        if isinstance(other, SecretStr):
            return self._secret == other._secret
        if isinstance(other, str):
            return self._secret == other
        return NotImplemented

    def __ne__(self, other: Any) -> bool:
        result = self.__eq__(other)
        if result is NotImplemented:
            return result
        return not result

    def __hash__(self) -> int:
        return hash(("SecretStr", self._secret))

    def __len__(self) -> int:
        return len(self._secret)

    def __bool__(self) -> bool:
        return bool(self._secret)

    def __setattr__(self, name: str, value: Any) -> None:  # pragma: no cover
        raise AttributeError("SecretStr is immutable")


__all__ = ["SecretStr"]
