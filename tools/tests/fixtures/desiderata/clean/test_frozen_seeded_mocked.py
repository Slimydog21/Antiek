"""Guard fixture: frozen clock, seeded RNG, mocked network — all correct shapes.

Must NOT flag any determinism sub-rule.
"""

from __future__ import annotations

import random
from datetime import datetime

import httpx
from freezegun import freeze_time


@freeze_time("2020-06-15 12:00:00")
def test_frozen_clock_assertion():
    assert datetime.now().year == 2020


def test_seeded_rng_assertion():
    random.seed(42)
    assert random.randint(1, 100) == 82


def test_mocked_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    response = client.get("https://example.test/health")
    assert response.json()["ok"] is True