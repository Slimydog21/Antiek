"""The speak→read servability gate adapter — collision #4 enforcement.

This is the thin seam that makes Read's ``platform_authored = clean and
auto-servable`` assumption safe for content that came from Speak, *without*
coupling Read to Speak's internals.

The collision (seam #4 in the master spec): Read's servability vocabulary
treats ``platform_authored`` as auto-servable. But a Speak biography assembled
from third-party interview claims is not automatically clean — it must clear
consent, cross-interviewee verification, defamation / right-of-publicity, and
takedown first. SPR-01 already put a ``provenance_class ∈
{operator_authored, speak_derived}`` on :class:`ServableEntryContract` and made
``serves_full_text`` gate a ``speak_derived`` entry on
``speak_publish_gate_passed``. What was missing — and what this module supplies
— is the **one direction-pinned translation** from "Speak's publish gate
passed" to that boolean, expressed as a contract Read calls rather than a
reach into ``substrate/speak/``.

Read's serving layer now exists in ``substrate/books/serve.py``. This module is
still the seam owner: it translates Speak's publish outcome into the
``ServableEntryContract`` vocabulary and projects live ``documents`` rows into
that same contract shape, so Read's SQL gate and the seam contract cannot drift.

The decoupling is the point: Read passes the *outcome* of Speak's gate (a
single boolean it received over the speak→read seam, or by calling
``publish_gate_passed``), never Speak's ``ClaimRecord`` / ``ConsentContract`` /
project rows. Read's servability check stays a pure function of the
:class:`ServableEntryContract` it already holds.
"""

from __future__ import annotations

import json
from typing import Any

from substrate.contracts.interviewer import ConsentContract
from substrate.contracts.servable import ServableEntryContract


_DOCUMENT_TO_CONTRACT_CONTENT_CLASS: dict[str, str] = {
    "public_domain": "public_domain",
    "source_declared_open": "source_declared_open",
    "opt_in_licensed": "publisher_opted_in",
    "user_owned": "platform_authored",
    "user_public_contribution": "platform_authored",
}


def _metadata_dict(metadata_raw: Any) -> dict[str, Any]:
    if isinstance(metadata_raw, dict):
        return metadata_raw
    if isinstance(metadata_raw, str) and metadata_raw.strip():
        try:
            loaded = json.loads(metadata_raw)
        except json.JSONDecodeError:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def document_servable_entry(
    document_id: str,
    *,
    content_class: str | None,
    metadata: Any = None,
    taken_down: bool = False,
) -> ServableEntryContract:
    """Project a live ``documents`` row into the seam servability contract.

    The documents table stores rights provenance classes such as
    ``user_public_contribution``; the seam contract stores Read's servability
    vocabulary such as ``platform_authored``. This function is the single
    reviewed bridge between those vocabularies.
    """
    if taken_down:
        return ServableEntryContract(
            document_id=document_id,
            content_class="taken_down",
            taken_down=True,
        )

    contract_class = _DOCUMENT_TO_CONTRACT_CONTENT_CLASS.get(
        content_class or "",
        "gated_metadata_only",
    )
    meta = _metadata_dict(metadata)
    provenance_class = None
    if contract_class == "platform_authored":
        provenance_class = (
            "speak_derived"
            if meta.get("provenance_class") == "speak_derived"
            else "operator_authored"
        )
    return ServableEntryContract(
        document_id=document_id,
        content_class=contract_class,  # type: ignore[arg-type]
        taken_down=False,
        provenance_class=provenance_class,  # type: ignore[arg-type]
        speak_publish_gate_passed=meta.get("speak_publish_gate_passed") is True,
    )


def speak_publish_gate_passed(consent: ConsentContract) -> bool:
    """Translate a Speak :class:`ConsentContract` into the single boolean Read
    consults. Deny-by-default: a Speak-derived document publishes full text
    only when its consent state is ``publishable`` — explicit publish scope,
    verified-before-publish, right-of-publicity cleared, and no takedown.

    This is the only Speak-shaped input the adapter accepts; Read never sees
    it. The producing (Speak) side computes this and rides it over the
    speak→read seam as ``publish_gate_passed``; Read reads the boolean."""
    return consent.publishable


def gate_speak_derived_entry(
    entry: ServableEntryContract,
    *,
    publish_gate_passed: bool,
) -> ServableEntryContract:
    """Stamp a ``speak_derived`` servable entry with the Speak publish-gate
    outcome and return the gated entry. The returned entry's
    ``serves_full_text`` then reflects deny-by-default: a ``speak_derived``
    entry serves full text only when ``publish_gate_passed`` is True.

    For ``operator_authored`` (or any non-``platform_authored``) entry the
    flag is irrelevant and the entry is returned unchanged — operator-authored
    stays auto-servable (no regression for Write output). The returned
    ``ServableEntryContract`` is the same frozen contract SPR-01 owns, with one
    field set."""
    if (
        entry.content_class != "platform_authored"
        or entry.provenance_class != "speak_derived"
    ):
        # operator_authored / public_domain / publisher_opted_in / gated /
        # taken_down — the speak publish gate does not apply.
        return entry
    return entry.model_copy(update={"speak_publish_gate_passed": publish_gate_passed})


def serves_full_text(
    entry: ServableEntryContract,
    *,
    publish_gate_passed: bool = False,
) -> bool:
    """The full servability decision a serving layer makes for one entry,
    consulting the Speak publish gate for ``speak_derived`` content. A pure
    function of the contract + the (already-computed) gate outcome — Read calls
    this, stays uncoupled from Speak, and cannot route around deny-by-default.

    * ``operator_authored`` platform content → auto-servable (gate ignored).
    * ``speak_derived`` platform content → servable only if
      ``publish_gate_passed``.
    * everything else → SPR-01's deny-by-default derivation
      (``ServableEntryContract.serves_full_text``)."""
    return gate_speak_derived_entry(
        entry, publish_gate_passed=publish_gate_passed
    ).serves_full_text
