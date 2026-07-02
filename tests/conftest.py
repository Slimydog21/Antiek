"""Process-wide test isolation for the dispatch circuit breaker.

``substrate.dispatch.breaker.default_breaker`` is a process-wide singleton the
router consults on every dispatch (nygard SPR-04). Without isolation, any test
that exercises real provider failures (e.g. the chaos paths in
``tests/test_dispatch_fallback_chain.py``) records failures that trip a
provider's breaker for every LATER test in the same process — the exact
cross-test leak that made
``test_synthesis_falls_through_to_hermes_when_openrouter_dies`` red on CI
(hermes breaker OPEN from a sibling test) while passing solo. Tests that need
their own breaker semantics construct a private ``CircuitBreaker`` and
monkeypatch it in (see ``tests/test_dispatch_breaker_integration.py``); this
fixture only guarantees the shared default starts every test CLOSED.
"""

import pytest

from substrate.dispatch.breaker import default_breaker


@pytest.fixture(autouse=True)
def _isolate_default_breaker():
    default_breaker.reset()
    yield
    default_breaker.reset()
