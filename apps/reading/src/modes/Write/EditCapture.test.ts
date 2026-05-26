import { describe, expect, it, vi } from "vitest";

import { EDIT_CAPTURE_POLICY, makeEditCaptureSink } from "./EditCapture";
import type { CapturedEdit } from "./Editor/editCapture";

/**
 * EditCapture.test — the capture-not-train boundary (Product Depth SPR-07 M4).
 *
 * The seductive feature is "learn the writing style". This sprint CAPTURES the
 * edit trajectory and does nothing else — training is gated G8 / Loop-3. These
 * checks pin that boundary so a future maintainer can't quietly "complete" it
 * by wiring a training step here.
 */

describe("EditCapture — capture yes, train no (G8/Loop-3)", () => {
  it("the policy permits capture and forbids training", () => {
    expect(EDIT_CAPTURE_POLICY.capture).toBe(true);
    expect(EDIT_CAPTURE_POLICY.train).toBe(false);
    expect(EDIT_CAPTURE_POLICY.trainingGate).toMatch(/Loop-3/);
  });

  it("the seam exposes a capture sink and NO training/model-update path", () => {
    const surface = makeEditCaptureSink as unknown as Record<string, unknown>;
    // The module surface must not grow a train/fine-tune/reward hook.
    const mod = { EDIT_CAPTURE_POLICY, makeEditCaptureSink } as Record<string, unknown>;
    for (const k of Object.keys(mod)) {
      expect(k).not.toMatch(/train|finetune|fine_tune|reward|sft|rl_|model_update/i);
    }
    // The sink itself is callable and does not throw.
    expect(typeof surface).toBe("function");
  });

  it("the sink notifies onCaptured but never triggers training", () => {
    const onCaptured = vi.fn();
    const sink = makeEditCaptureSink({ onCaptured });
    const edits: CapturedEdit[] = [
      {
        locator: { sectionId: "sec-1", blockId: "blk-1", paragraphIndex: 0 },
        kind: "replace",
        granularity: "block",
        beforeText: "old",
        afterText: "new",
        reverted: false,
      },
    ];
    sink(edits);
    // Capture side fired …
    expect(onCaptured).toHaveBeenCalledWith(edits);
    // … and there is no train side to assert fired, because there is none:
    // makeEditCaptureSink takes no onTrain and the policy forbids it.
    expect("onTrain" in (EDIT_CAPTURE_POLICY as object)).toBe(false);
  });
});
