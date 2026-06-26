"""Shared fixtures for services.html_projection tests (HPRJ SPR-02)."""

from __future__ import annotations

import os
import sys

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

import pytest

from services.html_projection import Provenance, RenderContext


@pytest.fixture
def ctx() -> RenderContext:
    """A deterministic render context with provenance for the footer.
    No resolver → ref-bearing blocks render missing-tombstones (M6 path).
    No wall-clock anywhere."""
    return RenderContext(
        provenance=Provenance(
            document_id="doc-test-1",
            notebook_id="nbk-test-1",
            title="Test Notebook",
            content_class="notebook",
            schema_version="1.0.0",
            creator_user_id="user-test",
            rendered_at="2026-05-21T12:00:00Z",
            signature_valid=True,
        )
    )


@pytest.fixture
def empty_ctx() -> RenderContext:
    """A context with no provenance — footer still renders (provenance
    footer present in every render, even when empty)."""
    return RenderContext()
