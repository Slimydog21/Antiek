/**
 * EditCapture — the capture-not-train boundary for the Write loop
 * (Product Depth SPR-07 M4).
 *
 * The operator's Write thesis is a Cursor-like on-policy workflow: the first
 * draft is cheap, the real writing is the edit, and those last-mile edits are
 * the highest-value training signal. The seductive next step is to learn from
 * them. **This module does not.** It is the explicit, named seam where edits
 * are CAPTURED and nothing else happens.
 *
 *   capture  →  YES. The structured before/after edit-pairs flow into the
 *               graph as `edit.captured` events (the trajectory store).
 *   train    →  NO.  No SFT, no RL, no model update, no reward call, no
 *               fine-tune trigger fires from a captured edit. Training on the
 *               captured trajectories is gated behind G8 / Loop-3 (see
 *               `docs/loop_3_unlock_criteria.md` and the Loop-3 surface at
 *               `/loop-3`).
 *
 * GATE BOUNDARY — DO NOT "COMPLETE" THIS BY ADDING TRAINING. A future
 * maintainer who reads "edits captured to learn writing style" and wires a
 * training step here has crossed G8 without the operator gate. The capture is
 * the deliverable for this sprint; the learning is a separately-gated
 * capability. The `WriteEditor` emits `edit.captured` events via
 * `Editor/editCapture.ts` + `postTypedEvent` (the live capture path — a pure
 * event-log record). The real, ENFORCED gate is on the backend:
 * `substrate/edit/harvest_authoring.py` calls `check_unlocked()` before any
 * training harvest, which raises unless G8/Loop-3 is unlocked. This module is
 * NOT on the live emission path; it documents and asserts the capture-not-train
 * posture (the `EDIT_CAPTURE_POLICY` constant + its test) so the decision is
 * named in one obvious place — but the enforcement that holds regardless of the
 * front end is the backend gate above.
 *
 * Why this is a module and not just a comment in the editor: the editor is a
 * reusable component (also used by its Storybook). The routed Write surface
 * owns the *decision* that capture is on and training is off; pinning that
 * decision here — with a test that asserts capture-yes / train-no — keeps the
 * boundary defensible across turnover (rigor #1, #5).
 */

import type { CapturedEdit } from "./Editor/editCapture";

/** The capabilities this seam permits. Training is structurally absent. */
export interface EditCapturePolicy {
  /** Edits are recorded as `edit.captured` events. */
  readonly capture: true;
  /** Training on captured edits is gated (G8 / Loop-3) — never here. */
  readonly train: false;
  /** Where the gated training capability is tracked. */
  readonly trainingGate: "G8 / Loop-3 (docs/loop_3_unlock_criteria.md)";
}

/** The named, testable record of the capture-not-train posture; asserted by the
 * capture-not-train test. Enforcement lives on the backend harvest gate
 * (`substrate/edit/harvest_authoring.py` → `check_unlocked()`), not here. */
export const EDIT_CAPTURE_POLICY: EditCapturePolicy = {
  capture: true,
  train: false,
  trainingGate: "G8 / Loop-3 (docs/loop_3_unlock_criteria.md)",
};

/**
 * Observe captured edits on the routed surface — for surfacing a "captured"
 * acknowledgement to the writer (optional) and for nothing else. It receives
 * the same `CapturedEdit[]` the editor diffs and is forbidden, by contract,
 * from doing anything that updates a model. Reverted edits arrive with
 * `reverted: true` and are excluded from signal downstream.
 *
 * This is intentionally a no-op-by-default sink: the editor already ships the
 * events; a host that wants a UI acknowledgement passes an `onCaptured`. There
 * is no `onTrain` and there never should be — adding one is the gate crossing.
 */
export function makeEditCaptureSink(opts?: {
  onCaptured?: (edits: CapturedEdit[]) => void;
}): (edits: CapturedEdit[]) => void {
  return (edits: CapturedEdit[]) => {
    // CAPTURE side only. The editor has already emitted edit.captured events
    // (Editor/editCapture.ts → postTypedEvent). This sink may notify the UI;
    // it must never trigger training. If you are tempted to call a
    // train/fine-tune/reward path here: that is G8 — stop and route it
    // through the Loop-3 gate, not this function.
    opts?.onCaptured?.(edits);
  };
}
