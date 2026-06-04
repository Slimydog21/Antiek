"""Fixture: near-miss negatives the extractor must NOT flag.

1. A LOCAL variable named `patch` that is just a dict/string — calling
   `patch(...)` on it is NOT unittest.mock.patch (no import of it), so the
   extractor's call-shape match must not treat a bare `patch(` as a mock when
   there is no mock-patch import. (We additionally guard: this file imports a
   core subsystem, so a false positive here would wrongly flag it theater.)

2. `orch` bound by a NON-mock import to a NON-core module
   (tools.run_corpus_ingest) — a `monkeypatch.setattr(orch, "discover_all", ...)`
   resolves to tools.run_corpus_ingest.discover_all, which is NOT core. This is
   the exact alias false-positive a substring match on "orch" would make.

So: imports a core subsystem (graph.ops) but mocks only a NON-core alias →
verdict `reality`.
"""

from substrate.graph import ops  # noqa: F401  (claims to cover graph.ops)


def test_local_patch_name_is_not_a_mock():
    # `patch` here is a local string, not unittest.mock.patch. The extractor
    # must not record a mock target from `patch(...)` calls in this file.
    patch = "/sections/1/prose"
    assert patch.startswith("/sections")


def test_alias_to_non_core_module(monkeypatch):
    from tools import run_corpus_ingest as orch

    monkeypatch.setattr(orch, "discover_all", lambda *a, **k: [])
    assert orch is not None
