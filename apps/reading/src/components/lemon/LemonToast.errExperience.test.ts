import { afterEach, describe, expect, it, vi } from "vitest";

import { MASCOT_EXPERIENCE_EVENT } from "../../mascot";
import { toast } from "./LemonToast";

afterEach(() => {
  vi.useRealTimers();
});

describe("LemonToast failure experience", () => {
  it("emits one Brain failure for an error toast", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    window.addEventListener(MASCOT_EXPERIENCE_EVENT, listener);

    toast.err("Could not save", 1);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({
      experience: "fail",
    });
    window.removeEventListener(MASCOT_EXPERIENCE_EVENT, listener);
  });

  it("does not treat successful feedback as failure", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    window.addEventListener(MASCOT_EXPERIENCE_EVENT, listener);

    toast.ok("Saved", 1);

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(MASCOT_EXPERIENCE_EVENT, listener);
  });
});
