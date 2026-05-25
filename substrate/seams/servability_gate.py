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

Why a seam adapter and not an edit to Read's ``serve.py``: at this sprint
``substrate/books/serve.py`` does not exist yet (Read SPR-01's serving layer is
unbuilt — verified: no ``substrate/books`` package in the tree). Read SPR-01
owns ``serve.py`` and will call this adapter; building ``serve.py`` here would
be implementing Read's internals, which is exactly the duplication this whole
spec forbids. So the load-bearing artifact is the *gate decision* and the
*flag-stamping* — the seam — and the test proves the deny-by-default behavior
on the contract.

The decoupling is the point: Read passes the *outcome* of Speak's gate (a
single boolean it received over the speak→read seam, or by calling
``publish_gate_passed``), never Speak's ``ClaimRecord`` / ``ConsentContract`` /
project rows. Read's servability check stays a pure function of the
:class:`ServableEntryContract` it already holds.
"""

from __future__ import annotations

from substrate.contracts.interviewer import ConsentContract
from substrate.contracts.servable import ServableEntryContract


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
    stays auto-servable (no regression for Write output). This is the function
    Read's future ``serve.py`` calls; the returned ``ServableEntryContract`` is
    the same frozen contract SPR-01 owns, with one field set."""
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
