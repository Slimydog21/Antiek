"""Skill manifest contract (kernel-skills packaging).

A skill = one typed callable + machine-readable metadata. The manifest is
the SKILL.md-shaped handoff a research agent reads to decide *when* and
*how* to call the skill: parameters, return contract, and — load-bearing
for Antiek — the safety/invariant notes each skill carries (ephemeral
store, read-only wrt the corpus, script-free output). The registry in
``registry.py`` is just a tuple of these manifests; nothing here imports
any skill module, so manifests are introspection-safe.

WHY DATACLASSES AND NOT STRINGS: the manifest is consumed by a registry
test (``list_skills`` returns typed objects) and by any future agent-side
schema checker. A plain docstring is prose; the manifest keeps the
machine-readable contract (names, arity, defaults) in one place, typed.
The docstring of each skill module remains the prose authority.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class SkillParameter:
    """One parameter of a skill function.

    Attributes
    ----------
    name:
        Parameter name as it appears in the function signature.
    annotation:
        The declared type, as a readable string (e.g. ``"Sequence[float]"``).
    description:
        What the parameter means and any bounds (e.g. ``seed`` must be
        finite; values outside bounds raise ``ValueError``).
    required:
        Whether the parameter has no default.
    default:
        The default value as a string, or None when ``required``.
    """

    name: str
    annotation: str
    description: str
    required: bool = True
    default: str | None = None


@dataclass(frozen=True)
class SkillManifest:
    """SKILL.md-style metadata for one kernel skill.

    Attributes
    ----------
    name:
        Registry key, snake_case, equal to the module's ``MANIFEST.name``.
    summary:
        One line: what the skill does.
    description:
        Longer prose: when to use it, what it guarantees.
    entrypoint:
        The typed function a caller invokes first. Heterogeneous signatures
        are why this is ``Callable[..., object]``; the typed signature lives
        in the module docstring + ``parameters``.
    functions:
        The full public function family (``entrypoint`` first). A skill is
        usually a small family — ``("create_store", "run_sql", "close")`` —
        and the family is what the manifest advertises.
    parameters:
        Declared parameters of the entrypoint, in signature order.
    returns:
        The return contract, as prose.
    safety:
        The invariant notes — the reason an agent (and the operator's
        gate) can trust the skill on the Antiek substrate. Empty only for
        skills with no substrate-facing surface; every skill here carries
        at least one.
    examples:
        Short usage snippets, one string each, in Python.
    """

    name: str
    summary: str
    description: str
    entrypoint: Callable[..., object]
    returns: str
    functions: tuple[str, ...] = ()
    parameters: tuple[SkillParameter, ...] = ()
    safety: tuple[str, ...] = ()
    examples: tuple[str, ...] = ()


__all__ = ["SkillManifest", "SkillParameter"]
