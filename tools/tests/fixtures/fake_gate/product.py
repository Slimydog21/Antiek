"""A tiny product module for the fake-gate-detector fixture mini-repo.

``discount_price`` carries ONE genuinely load-bearing line: the members-only
guard. If that guard is inverted, a non-member gets the member discount (and a
member is charged full price) — a user-visible behavior change. A REAL behavior
test asserts the returned price; a FAKE mock-only test asserts only that a
collaborator was called, so it passes whether or not the guard works. The
detector must KILL the mutation under the real test and let it SURVIVE under the
fake one. This is the detector's whole reason to exist, in miniature.
"""

from __future__ import annotations


def discount_price(base: float, *, is_member: bool) -> float:
    """Members pay 80% of base; everyone else pays full price. The guard is the
    load-bearing line: inverting it flips who gets the discount."""
    if is_member:
        return base * 0.8
    return base
