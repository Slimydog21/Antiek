/**
 * toast.err is the shell-wide failure path — drives notifyShellFailure →
 * emitWernerExperience("fail"). Tests the SHIPPED LemonToast.emit path.
 */
import { afterEach, describe, expect, it } from "vitest";

import { toast } from "./LemonToast";
import { WERNER_EXPERIENCE_EVENT } from "../../werner/reactionBus";

afterEach(() => {
  // dismiss any lingering toasts by id range (best-effort)
  for (let i = 0; i < 50; i++) toast.dismiss(i);
});

describe("toast.err product experience path", () => {
  it("toast.err dispatches fail experience on the real emit path", () => {
    const seen: string[] = [];
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, on);
    toast.err("substrate unreachable");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, on);
    expect(seen).toContain("fail");
  });

  it("toast.ok does not emit fail", () => {
    const seen: string[] = [];
    const on = (e: Event) => {
      const d = (e as CustomEvent).detail;
      if (d?.experience) seen.push(d.experience);
    };
    window.addEventListener(WERNER_EXPERIENCE_EVENT, on);
    toast.ok("saved");
    window.removeEventListener(WERNER_EXPERIENCE_EVENT, on);
    expect(seen).not.toContain("fail");
  });
});
