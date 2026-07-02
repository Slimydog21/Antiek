"""FAKE mock-only test (negative control). It never calls the real guard with a
value whose output it checks — it asserts only that a logger collaborator was
invoked (call shape), the canonical fake-gate pattern. Inverting the members-only
guard in product.discount_price does NOT change whether the logger is called, so
this test PASSES whether or not the guard works. The detector should report
``survived`` — this is the kind of test the whole sprint exists to catch."""

from __future__ import annotations

from unittest.mock import MagicMock

import product


def test_discount_calls_logger():
    logger = MagicMock()
    # We "exercise" the unit but assert only the mock's call shape — never the
    # returned price. A green here proves nothing about the guard.
    logger.info("computing discount")
    _ = product.discount_price(100.0, is_member=True)
    logger.info.assert_called_once()
    assert logger.info.call_count == 1
