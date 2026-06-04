"""Fixture: an ORDINARY method call that COLLIDES with a unittest.mock symbol.

``test_provider_call_is_not_mock_construction`` calls ``p.call(...)`` on a real
product object (a provider) and ``client.seal()`` / reads ``x.ANY`` — none of
these constructs ``unittest.mock``'s ``call`` / ``seal`` / ``ANY``. They are
ordinary attribute calls that merely share the spelling. The census must NOT
flag this test ``uses_mock`` and must NOT record ``call`` / ``seal`` / ``ANY``
as mock targets.

This is the BLOCKER-1 regression fixture: the round-1 code read ``func.attr``
and matched it against ``MOCK_SYMBOLS``, so ``p.call(...)`` was misread as
constructing ``unittest.mock.call`` and the archetypal provider-adapter tests
(test_provider_anthropic.py, test_provider_openai_compat.py, ...) were falsely
flagged mock with ``mock_targets=('call',)`` — inflating the suite mock-ratio.
On the old code this fixture would be ``uses_mock=True`` with targets
``('ANY', 'call', 'seal')``; on the fix it is ``uses_mock=False`` with no
targets and a clean ``behavior`` flag.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations


class Provider:
    """A real product object whose method happens to be named ``call``."""

    def call(self, model: str) -> str:
        return f"called:{model}"

    def seal(self) -> bool:
        return True


class Box:
    ANY = object()


def test_provider_call_is_not_mock_construction():
    p = Provider()
    result = p.call(model="m")
    client = Provider()
    sealed = client.seal()
    marker = Box.ANY
    # All three are ordinary product reads/calls — NOT unittest.mock symbols.
    assert result == "called:m"
    assert sealed is True
    assert marker is Box.ANY
