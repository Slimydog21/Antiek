"""Fixture: an ALIASED monkeypatch receiver (`mp`, not `monkeypatch`) doing a
setattr on a core symbol → still theater.

pytest's monkeypatch fixture can be bound to any parameter name. `mp.setattr(
ops, "insert_document", ...)` resolves to substrate.graph.ops.insert_document —
a core symbol — and is exactly as much a core-mock as the conventionally-named
`monkeypatch.setattr(...)`. The classifier must not be fooled by the receiver's
NAME.

Regression guard for the SPR-01 round-2 hardening: before it, the extractor keyed
on `"monkeypatch" in <receiver>`, so this aliased receiver was silently dropped —
producing a false `reality` for a file that genuinely stubs the graph core.
"""

from substrate.graph import ops


def test_aliased_receiver(mp):
    mp.setattr(ops, "insert_document", lambda *a, **k: None)
    assert True
