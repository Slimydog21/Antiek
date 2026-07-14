"""``substrate.seams`` — the cross-workflow seam layer (antiek-unified SPR-03).

Where the four products intersect. A *seam* is a typed, one-direction handoff
between two of the four workflows (Research / Read / Write / Speak) that carries
**the same graph entity by reference** — an id + a provenance ref — never a
copy of its content. The flywheel (research → read → write → speak → read) is a
cycle of these handoffs; each is an explicit, terminating event a human or an
explicit trigger fires. A seam that auto-chains its successor is a runaway-cost
bug (the no-auto-loop rule).

This package owns the **seam contracts** (the handoff shapes) and two seam-level
collision-fix adapters. It builds *on* the SPR-01 substrate contracts
(``substrate.contracts``) the seams carry; it does not redefine them, and it
builds no product's internals — each product spec implements its own side of a
seam against the contract here.

Seven committed seams:

* ``ResearchToReadSeam``  research → read
* ``ReadToResearchSeam``  read → research   (Read SPR-08)
* ``ReadToWriteSeam``     read → write       (Write SPR-03)
* ``WriteToReadSeam``     write → read       (Write SPR-07)
* ``SpeakToWriteSeam``    speak → write      (Speak SPR-08)
* ``SpeakToReadSeam``     speak → read       (Speak SPR-09)
* ``WriteToSpeakSeam``    write → speak

The seam-level collision adapter ``servability_gate`` resolves seam #4
(``platform_authored``-from-Speak gating) — the speak→read translation Read
calls so a ``speak_derived`` document passes Speak's publish gate before Read
serves full text, without coupling Read to Speak internals.

See ``inventory.md`` for the row-by-row map and ``README.md`` for the flywheel
diagram, the four collision resolutions, and seam implementation details. The
seam *events* (``seam.*`` action types) are typed in
``substrate/schemas/events.py`` and emitted through ``substrate/event_log`` →
``runtime/db_lock``.
"""

from __future__ import annotations

from .contracts import (
    ALL_SEAMS,
    COMMITTED_SEAMS,
    PROVISIONAL_SEAMS,
    EntityKind,
    ReadToResearchSeam,
    ReadToWriteSeam,
    ResearchToReadSeam,
    SeamStatus,
    SpeakToReadSeam,
    SpeakToWriteSeam,
    Workflow,
    WriteToReadSeam,
    WriteToSpeakSeam,
    seam_status,
)
from .servability_gate import (
    gate_speak_derived_entry,
    serves_full_text,
    speak_publish_gate_passed,
)
from .thread import (
    Thread,
    ThreadHop,
    ThreadStub,
    assert_single_canonical_entity,
    reconstruct_thread,
)

__all__ = [
    # the seven committed seams
    "ResearchToReadSeam",
    "ReadToResearchSeam",
    "ReadToWriteSeam",
    "WriteToReadSeam",
    "SpeakToWriteSeam",
    "SpeakToReadSeam",
    "WriteToSpeakSeam",
    # registries + status
    "COMMITTED_SEAMS",
    "PROVISIONAL_SEAMS",
    "ALL_SEAMS",
    "seam_status",
    "SeamStatus",
    "Workflow",
    "EntityKind",
    # seam #4 servability gate adapter
    "speak_publish_gate_passed",
    "gate_speak_derived_entry",
    "serves_full_text",
    # SPR-06 cross-workflow thread navigation (a VIEW over seam events + edges)
    "Thread",
    "ThreadHop",
    "ThreadStub",
    "reconstruct_thread",
    "assert_single_canonical_entity",
]
