"""Skill registry: the discoverable catalog of kernel skills.

The registry is the answer to "what can an agent do here?" — a typed,
introspection-safe tuple of manifests, one per skill, in a stable order
(``duckdb_store``, ``py_analysis``, ``sketch_svg``). It imports the three
skill modules (which import only stdlib + duckdb + the zero-script gate),
so importing the registry never touches a binary, a network, or a GPU —
the dark-import discipline the kernel-skills packaging requires.

The manifests are the SKILL.md: prose description, declared parameter
contract, return contract, and the invariant notes each skill carries.
``list_skills`` returns them as typed objects, not strings, so a caller
can pattern-match on ``manifest.name`` or render the catalog as prose
without re-parsing anything.
"""

from __future__ import annotations

from collections.abc import Sequence

from substrate.agent_skills import duckdb_store, py_analysis, sketch_svg
from substrate.agent_skills.manifest import SkillManifest

__all__ = ["SKILLS", "get_skill", "list_skills"]

# Stable registration order; the tuple is the source of truth. Adding a
# skill is one line here + one MANIFEST in its module.
SKILLS: tuple[SkillManifest, ...] = (
    duckdb_store.MANIFEST,
    py_analysis.MANIFEST,
    sketch_svg.MANIFEST,
)


def list_skills() -> Sequence[SkillManifest]:
    """All registered skill manifests, in registration order."""
    return SKILLS


def get_skill(name: str) -> SkillManifest | None:
    """The manifest for ``name``, or None when no such skill exists."""
    for manifest in SKILLS:
        if manifest.name == name:
            return manifest
    return None
