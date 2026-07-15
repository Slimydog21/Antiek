import { afterEach, describe, expect, it, vi } from "vitest";

import { WERNER_EXPERIENCE_EVENT } from "../../werner";
import { toast } from "./LemonToast";

afterEach(() => {
  vi.useRealTimers();
});

describe("LemonToast failure experience", () => {
  it("emits one Werner failure for an error toast", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    toast.err("Could not save", 1);

    expect(listener).toHaveBeenCalledTimes(1);
    expect((listener.mock.calls[0]?.[0] as CustomEvent).detail).toEqual({
      experience: "fail",
    });
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });

  it("does not treat successful feedback as failure", () => {
    vi.useFakeTimers();
    const listener = vi.fn();
    window.addEventListener(WERNER_EXPERIENCE_EVENT, listener);

    toast.ok("Saved", 1);

    expect(listener).not.toHaveBeenCalled();
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, listener);
  });
});
