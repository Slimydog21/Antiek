"""Servable-corpus entry contract — and the seam-#4 resolution.

Owned by **Read SPR-01** (servability) with the ``provenance_class`` field
added here to resolve **seam #4** (``platform_authored``-from-Speak gating).

Read's servability vocabulary is derived from ``(content_class, taken_down)``
by ``substrate.books.servability`` — verified against
``substrate.constants.BOOK_SERVABILITY_STATUSES`` (L545-551). Deny-by-default:
only the first three classes serve full text. The legal spine is *Hachette v.
Internet Archive* (2024, enjoined full-text serving of in-copyright books) vs
*Authors Guild v. Google* (2015, bounded snippet view upheld).

**The seam #4 problem:** Read assumes ``platform_authored = clean and
auto-servable``. But a Speak biography assembled from third-party interview
claims is *not* automatically clean — it must clear consent, verification,
defamation, and right-of-publicity first. So ``platform_authored`` carries a
``provenance_class``:

* ``operator_authored`` — the operator/Write workflow wrote it; auto-servable.
* ``speak_derived`` — produced from interviews; Read's servability check must
  consult Speak's publish gate (``substrate/speak/publish_gate.py``) *before*
  serving full text.

The validator keeps ``provenance_class`` meaningful only when
``content_class == 'platform_authored'`` — for every other class the field is
``None`` (provenance is irrelevant to a public-domain or publisher-opted-in
work). This is the field that makes Read's assumption safe without coupling
Read to Speak internals.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from substrate.books.servability import (
    _SERVABLE_STATUSES as _CLASSIFIER_SERVABLE_STATUSES,
)

# The deny-by-default reading order: the servable classes serve full text, the
# gated/taken-down ones do not. Mirrors ``constants.BOOK_SERVABILITY_STATUSES``
# and ``substrate.books.servability.ServabilityStatus`` (the §9.0 classifier's
# status vocabulary — this Literal is the same vocabulary, not content_class).
# ``source_declared_open`` (CC-BY / CC-BY-SA) is servable but is deliberately
# NOT a §9.10 publisher opt-in — it was opened at the source, not claimed.
ContentClass = Literal[
    "public_domain",
    "platform_authored",
    "publisher_opted_in",
    "source_declared_open",
    "gated_metadata_only",
    "taken_down",
]
# The full-text-servable allowlist. DERIVED from the §9.0 classifier's servable
# status set (``substrate.books.servability._SERVABLE_STATUSES``) so the two
# can never silently diverge — see the drift-guard assertion below. The
# classifier (``books/servability.py``) is the single owner of *which* statuses
# serve full text; this contract MIRRORS that decision, it does not re-make it.
FULL_TEXT_SERVABLE: frozenset[str] = frozenset(
    s.value for s in _CLASSIFIER_SERVABLE_STATUSES
)

# ---------------------------------------------------------------------------
# Drift-guard — the contract allowlist and the §9.0 classifier share one owner.
# ---------------------------------------------------------------------------
#
# This is the EXACT defect SPR-04 came back on: a second owner (this contract)
# carried its own servable allowlist that silently drifted from the §9.0
# classifier's set, crashing on ``source_declared_open``. Deriving
# FULL_TEXT_SERVABLE from the classifier's set (above) makes the contract a
# mirror, not a fork. These two assertions make the mirror enforced at import
# time: (1) every servable status the classifier recognises is a member of the
# ContentClass Literal (so a value the classifier serves can always be recorded
# on a ServabilityTag), and (2) the derived allowlist equals the classifier's
# set exactly (a redundant identity now, kept as a tripwire so a future hand-
# edit that breaks the derivation reds loudly rather than silently).
_CONTENT_CLASS_MEMBERS: frozenset[str] = frozenset(ContentClass.__args__)  # type: ignore[attr-defined]
assert FULL_TEXT_SERVABLE <= _CONTENT_CLASS_MEMBERS, (
    "FULL_TEXT_SERVABLE contains a status the ContentClass Literal cannot "
    f"represent: {FULL_TEXT_SERVABLE - _CONTENT_CLASS_MEMBERS!r}. A servable "
    "class the §9.0 classifier recognises MUST be recordable on a "
    "ServabilityTag — add it to the ContentClass Literal."
)
assert frozenset(
    s.value for s in _CLASSIFIER_SERVABLE_STATUSES
) == FULL_TEXT_SERVABLE, (
    "servable allowlist drifted from the §9.0 classifier: "
    f"contract={set(FULL_TEXT_SERVABLE)!r} "
    f"classifier={set(s.value for s in _CLASSIFIER_SERVABLE_STATUSES)!r}. "
    "FULL_TEXT_SERVABLE MUST equal substrate.books.servability._SERVABLE_STATUSES "
    "— the classifier is the single owner; this contract mirrors it."
)

# Sub-discriminator for platform_authored only (seam #4).
ProvenanceClass = Literal["operator_authored", "speak_derived"]


class ServableEntryContract(BaseModel):
    """A corpus entry as Read's serving layer sees it. ``servable`` (whether
    full text is returned) is *derived* from ``content_class``; the contract
    states the derivation so a consumer cannot route around deny-by-default.
    ``speak_derived`` entries are servable only after Speak's publish gate
    passes — Read must check, not assume."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str
    content_class: ContentClass
    # every document carries an ip_holder_id, even null (provenance chain).
    ip_holder_id: str | None = None
    taken_down: bool = False
    # meaningful only for platform_authored; None otherwise.
    provenance_class: ProvenanceClass | None = None
    # set True by Speak's publish gate; Read serves a speak_derived doc full
    # text only when this is True. operator_authored is auto-servable.
    speak_publish_gate_passed: bool = False

    @model_validator(mode="after")
    def _provenance_scoped_to_platform_authored(self) -> ServableEntryContract:
        if self.content_class != "platform_authored" and self.provenance_class is not None:
            raise ValueError(
                "provenance_class is meaningful only for content_class="
                "'platform_authored' (seam #4)"
            )
        if self.content_class == "platform_authored" and self.provenance_class is None:
            raise ValueError(
                "platform_authored entries must declare a provenance_class "
                "{operator_authored | speak_derived} (seam #4)"
            )
        return self

    @property
    def serves_full_text(self) -> bool:
        """Deny-by-default derivation. A taken-down or gated entry never serves
        full text; a speak_derived entry serves only after the publish gate."""
        if self.taken_down or self.content_class not in FULL_TEXT_SERVABLE:
            return False
        if self.content_class == "platform_authored" and self.provenance_class == "speak_derived":
            return self.speak_publish_gate_passed
        return True
