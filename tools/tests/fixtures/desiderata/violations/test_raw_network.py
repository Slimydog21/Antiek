"""Fixture: real network call without mock or @pytest.mark.integration.

The lint must flag: the test depends on a live service.
"""

from __future__ import annotations

import httpx


def test_fetches_live_page():
    httpx.get("https://example.com/status")