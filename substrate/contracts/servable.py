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

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator

# The deny-by-default reading order: the first three serve full text, the last
# two do not. Mirrors ``constants.BOOK_SERVABILITY_STATUSES``.
ContentClass = Literal[
    "public_domain",
    "platform_authored",
    "publisher_opted_in",
    "gated_metadata_only",
    "taken_down",
]
FULL_TEXT_SERVABLE: frozenset[str] = frozenset(
    {"public_domain", "platform_authored", "publisher_opted_in"}
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
    ip_holder_id: Optional[str] = None
    taken_down: bool = False
    # meaningful only for platform_authored; None otherwise.
    provenance_class: Optional[ProvenanceClass] = None
    # set True by Speak's publish gate; Read serves a speak_derived doc full
    # text only when this is True. operator_authored is auto-servable.
    speak_publish_gate_passed: bool = False

    @model_validator(mode="after")
    def _provenance_scoped_to_platform_authored(self) -> "ServableEntryContract":
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
