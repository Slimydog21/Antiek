"""Edit + authoring-trajectory capture (specs/write/ SPR-02).

The operator's craft thesis: a first draft is cheap, but the real writing
is the edit — fixing flow, verifying data, perfecting sentences — and
those last-mile edits are the highest-value signal, both for learning a
writer's style (SPR-09, prompt-level now) and as on-policy RL data (the
gated Loop-3 track later), the way Cursor's accept/edit loop is a fertile
data source.

This package fills the previously-empty ``substrate/edit/``:

- ``edit_pair``          — the structured before/after edit-pair capture
                           (granular, locator-addressed) emitted as
                           ``edit.captured`` events. Replaces the coarse
                           whole-section ``original_text`` vs ``prose_text``.
- ``authoring_trajectory`` — reconstructs block-selection → draft → edits
                           → final from the event log, per deliverable,
                           stitching across sessions and dropping reverts.
- ``harvest_authoring``  — converts a trajectory to the existing
                           ``loop_3.HarvestedTrajectory`` prime-rl shape
                           (reward None). The storage-harvest is UNGATED;
                           the training-bound harvest is HARD-GATED by
                           ``unlock_gate`` (G8).

CAPTURE ≠ TRAINING. Nothing in this package trains, computes a reward, or
invokes ``sft_runner`` / ``rubric_verifier``. The reward stays ``None``
until the operator opens the Loop-3 gate; the training-harvest refuses to
run before then.
"""

from __future__ import annotations

from .authoring_trajectory import (  # noqa: F401
    AuthoringStep,
    AuthoringTrajectory,
    load_authoring_trajectory,
    reconstruct_from_events,
)
from .edit_pair import (  # noqa: F401
    EDIT_KINDS,
    GRANULARITIES,
    EditLocator,
    EditPair,
    capture_edit,
)
from .harvest_authoring import (  # noqa: F401
    AuthoringHarvestGated,
    harvest_authoring_for_training,
    harvest_authoring_trajectory,
)

__all__ = [
    "EDIT_KINDS",
    "GRANULARITIES",
    "EditLocator",
    "EditPair",
    "capture_edit",
    "AuthoringStep",
    "AuthoringTrajectory",
    "reconstruct_from_events",
    "load_authoring_trajectory",
    "harvest_authoring_trajectory",
    "harvest_authoring_for_training",
    "AuthoringHarvestGated",
]
