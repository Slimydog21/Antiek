"""
Role-shape metadata for Antiek's package-shaped roles.

Yegge's claim (December 2025 interview): there are only two natural role
shapes — *polecats* (min-context, typed I/O, single-turn, ephemeral) and
*crew* (max-context, free-form I/O, multi-turn, cross-module). Anything
else is a hack that today's models support and tomorrow's will collapse.

Antiek's roles are not classes; they are Python packages under
``roles/<name>/`` exporting domain-specific helpers. There is no Role
base class to subclass and no decorator point that applies to every
role. The shape declaration therefore lives at the *package* level: each
role's ``__init__.py`` defines a module-level ``__role_metadata__``
constant of type :class:`RoleMetadata`. ``tools/role_audit.py`` walks
``roles/`` and refuses to pass if any role lacks the constant or has an
empty ``spawn_pattern_doc``.

Why module-level rather than per-function decorators? Because Antiek's
roles are *bundles* (a prompt + a parser + a set of helpers, each
spread across multiple files). A decorator on one entrypoint would lie
to readers of the other files. The module-level constant is visible
from any file in the package via ``roles.<name>.__role_metadata__``.

Spec: ~/specs/antiek-yegge-execute/sprint-03-role-decorators.html
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

# Stable, narrow value set. Hybrids are forbidden by construction — if
# a role is genuinely both, it should be split into two roles, not
# annotated with a vague label that future readers will rationalize.
RoleShape = Literal["polecat", "crew"]

# Minimum length of the spawn_pattern_doc, enforced at construction
# time. Set to 30 chars (about one short sentence). Shorter strings are
# almost always rationalization; the audit script flags any role whose
# doc passes the construction check but reads as filler.
_SPAWN_DOC_MIN_CHARS: Final[int] = 30


@dataclass(frozen=True)
class RoleMetadata:
    """Per-role shape declaration. One instance per role package.

    Attributes
    ----------
    shape
        Either ``"polecat"`` or ``"crew"``. See module docstring.
    expected_input_tokens, expected_output_tokens
        Rough order-of-magnitude budgets used by the spawner to pick
        context windows and by token-burn telemetry (SPR-05) to detect
        runaway calls. Numbers are intentionally approximate; the
        audit script only checks that they are positive.
    multi_turn
        True if the role expects multiple back-and-forth turns with the
        caller (conventionally only ``"crew"`` roles).
    idempotent
        True if calling the role twice with the same inputs returns
        equivalent outputs. Sets the default for SPR-09 idempotency-key
        handling on routes that wrap this role.
    spawn_pattern_doc
        2-3 sentences explaining what to pass to the role and what to
        expect back. The artifact that replaces tribal knowledge.
    """

    shape: RoleShape
    expected_input_tokens: int
    expected_output_tokens: int
    multi_turn: bool
    idempotent: bool
    spawn_pattern_doc: str

    def __post_init__(self) -> None:
        # frozen=True means we can't reassign; use object.__setattr__ if
        # ever needed for canonicalization. For validation we only
        # raise — no mutation required.
        if self.shape not in ("polecat", "crew"):
            raise ValueError(
                f"RoleMetadata.shape must be 'polecat' or 'crew', got {self.shape!r}. "
                "Hybrids are forbidden by construction; split the role instead."
            )
        if self.expected_input_tokens <= 0 or self.expected_output_tokens <= 0:
            raise ValueError(
                "RoleMetadata: expected_input_tokens and expected_output_tokens "
                "must be positive (rough estimate is fine — order-of-magnitude only)."
            )
        if len(self.spawn_pattern_doc.strip()) < _SPAWN_DOC_MIN_CHARS:
            raise ValueError(
                f"RoleMetadata.spawn_pattern_doc must be at least "
                f"{_SPAWN_DOC_MIN_CHARS} chars (got "
                f"{len(self.spawn_pattern_doc.strip())}). Forces a real "
                "sentence rather than a placeholder."
            )
        # polecat/crew default expectation: multi_turn ↔ crew. Not
        # enforced strictly (some polecats might be in iterative tools),
        # but we surface the mismatch in the audit so the operator can
        # confirm or fix.

    # Convenience constructors keep call sites tidy and document the
    # default conventions. Annotating a role becomes one line in its
    # ``__init__.py``.

    @classmethod
    def polecat(
        cls,
        *,
        expected_input_tokens: int,
        expected_output_tokens: int,
        spawn_pattern_doc: str,
        idempotent: bool = True,
    ) -> "RoleMetadata":
        return cls(
            shape="polecat",
            expected_input_tokens=expected_input_tokens,
            expected_output_tokens=expected_output_tokens,
            multi_turn=False,
            idempotent=idempotent,
            spawn_pattern_doc=spawn_pattern_doc,
        )

    @classmethod
    def crew(
        cls,
        *,
        expected_input_tokens: int,
        expected_output_tokens: int,
        spawn_pattern_doc: str,
        idempotent: bool = False,
    ) -> "RoleMetadata":
        return cls(
            shape="crew",
            expected_input_tokens=expected_input_tokens,
            expected_output_tokens=expected_output_tokens,
            multi_turn=True,
            idempotent=idempotent,
            spawn_pattern_doc=spawn_pattern_doc,
        )


__all__ = ["RoleMetadata", "RoleShape"]
