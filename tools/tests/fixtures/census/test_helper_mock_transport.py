"""Fixture: a test that mocks a BEHAVIORAL HTTP surface via a module-level
mock-FACTORY helper (the archetypal provider-adapter pattern).

``_make_client(handler)`` is a plain module-level helper (not a fixture, not a
test) that returns ``httpx.Client(transport=httpx.MockTransport(handler))`` —
it builds a behavioral mock (the HTTP transport / client surface). The test
body never names ``MockTransport`` itself; it only CALLS ``_make_client``.

This mirrors tests/test_provider_anthropic.py and test_provider_openai_compat.py
exactly — the files the whole spec is about. The census must:
  - flag the test ``uses_mock=True`` (it inherits the helper's mock usage), and
  - record the helper's target ``MockTransport`` so the file enters
    ``n_behavioral_mock_files`` (``transport``/``httpx`` are behavioral tokens).

This is the BLOCKER-2 regression fixture: round-1 ``visit_FunctionDef`` returned
early so module-level helpers were never analysed, and ``visit_Call`` did not
attribute a helper's mocks to its caller. On the old code this test was
``uses_mock=False`` with NO ``MockTransport`` target, so the file was invisible
to the behavioral-mock count. On the fix it is ``uses_mock=True`` with
``MockTransport`` in its targets.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

import httpx


def _make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


def test_adapter_parses_canned_response():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "hello back"})

    client = _make_client(handler)
    resp = client.post("https://api.example.com/v1/messages", json={"q": "hi"})
    assert resp.json()["text"] == "hello back"
