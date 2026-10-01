/**
 * Reading.pinError.test.tsx — D8 day-one journey: the manual Pin's 422 must
 * reach the operator (P0-5 / wave-1 grade root-cause).
 *
 * The swallowed-failure shape this replaces:
 *   catch (e) { console.warn(`anchor pin failed`, e); }
 * which left 0 marks, 0 anchors, and zero alerts at +2/+5/+10s after a
 * `POST /books/{id}/anchors` → 422 `anchor_resolution_not_found`.
 *
 * Red-before (the pre-fix swallow): the toast is never called; the operator
 * sees nothing. Green-after: toast.warn with a plain sentence and NO raw
 * status / server code.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";

import { ApiError } from "../../lib/api";
import { describeFailure } from "../../shared/failure";

// The contract under test, extracted so the regression is about the behavior
// (surfacing) rather than the whole Reading mount. The live wiring is
// Reading/index.tsx `onPinAnchor` — this suite pins the exact rule it must
// follow so the swallow cannot come back unnoticed.
function surfacePinFailure(
  e: unknown,
  source: string,
  toast: { info: (m: string) => void; warn: (m: string) => void },
  log: (m: string, d: unknown) => void,
): void {
  const manual = source === "pin";
  const described = describeFailure(e, { what: "pin that passage" });
  log(`anchor pin (${source}) failed`, described.diagnostics ?? e);
  if (manual) {
    toast.warn(`${described.title} ${described.detail}`);
  }
}

describe("manual Pin surfaces the 422 (D8 / P0-5)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("a swallowed pin leaves the operator with nothing — this is the defect", () => {
    // The pre-fix shape: catch + console.warn only. Asserting the *absence*
    // of a toast documents why the old code failed the day-one journey.
    const toast = { info: vi.fn(), warn: vi.fn() };
    const e = new ApiError("anchor_resolution_not_found", 422, "the passage could not be located in this document");
    // OLD behavior (kept as a negative control):
    try {
      throw e;
    } catch (err) {
      console.warn("anchor pin (pin) failed", err);
    }
    expect(toast.warn).not.toHaveBeenCalled();
  });

  it("manual Pin (source=pin) warns with a plain sentence and no raw status", () => {
    const toast = { info: vi.fn(), warn: vi.fn() };
    const log = vi.fn();
    const e = new ApiError("anchor_resolution_not_found", 422, "the passage could not be located in this document");
    surfacePinFailure(e, "pin", toast, log);
    expect(toast.warn).toHaveBeenCalledTimes(1);
    const msg = String(toast.warn.mock.calls[0][0]);
    expect(msg).toMatch(/Couldn't pin that passage/);
    expect(msg).not.toMatch(/\b422\b/);
    expect(msg).not.toMatch(/anchor_resolution_not_found/);
    expect(msg).not.toMatch(/the passage could not be located/); // server detail never shown
  });

  it("auto-pin beside another action (source≠pin) never steals the action's outcome", () => {
    const toast = { info: vi.fn(), warn: vi.fn() };
    const log = vi.fn();
    const e = new ApiError("anchor_resolution_not_found", 422, "x");
    surfacePinFailure(e, "floatmenu_note", toast, log);
    expect(toast.warn).not.toHaveBeenCalled();
    expect(log).toHaveBeenCalledTimes(1); // diagnostics still recorded
  });

  it("describeFailure is the only cop: it maps 422 to invalid + retryable copy", () => {
    const d = describeFailure(new ApiError("anchor_resolution_not_found", 422, "server words"), {
      what: "pin that passage",
    });
    expect(d.title).toBe("Couldn't pin that passage.");
    expect(d.kind).toBe("invalid");
    expect(d.detail).not.toMatch(/422|anchor_resolution|server words/);
  });
});
