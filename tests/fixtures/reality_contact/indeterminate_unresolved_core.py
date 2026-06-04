"""Fixture: an UNRESOLVED mock target on a test that imports a core subsystem.

The patch target is built dynamically (a runtime-composed string), so the
extractor cannot statically resolve it to a dotted path — it is `unresolved`.
Because this file imports a core subsystem (graph.ops) and we cannot prove the
unresolved patch did NOT mock that core, the verdict must be `indeterminate`,
NEVER `reality`. This is the honesty bar.
"""

from unittest.mock import patch

from substrate.graph import ops  # noqa: F401


def _target_name():
    return "substrate.graph." + "ops.insert_document"


def test_unresolved_dynamic_target():
    with patch(_target_name()):  # dynamically-built target → unresolved
        assert True
