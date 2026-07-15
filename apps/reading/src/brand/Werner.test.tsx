/**
 * Werner.test.tsx — the real mark renders, and the four-mood guard bites.
 * Closes the U-02 gap: nothing else proved the penguin (not an empty span)
 * actually draws, or that the dev runtime guard rejects a fifth mood.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import fs from "node:fs";
import path from "node:path";

import Werner from "./Werner";
import WernerSleeping from "./werner/animated/WernerSleeping";
import { WernerDizzy } from "./werner/reactions";

afterEach(cleanup);

describe("Werner mark", () => {
  it("renders the penguin — role=img wrapping the Krea pose <img>", () => {
    const { getByRole, container } = render(<Werner />);
    expect(getByRole("img")).toBeTruthy();
    // The pose <img> with a real src is what proves we drew the cute
    // penguin art, not an empty wrapper or the retired SVG geometry.
    const img = container.querySelector("img");
    expect(img).toBeTruthy();
    expect(img?.getAttribute("src")).toBeTruthy();
  });

  it("throws in dev on a mood outside the four", () => {
    expect(() => render(<Werner mood={"party" as never} />)).toThrow();
  });

  it("corrects only the radically small-in-frame empty pose", () => {
    const empty = render(<Werner mood="empty" size={88} />);
    expect(empty.getByRole("img").className).toContain(
      "werner-pose-viewport--empty",
    );
    expect(empty.container.querySelector("img")?.className).toBe(
      "werner-pose--empty",
    );
    empty.unmount();

    for (const mood of ["idle", "thinking", "celebrate"] as const) {
      const pose = render(<Werner mood={mood} size={88} />);
      expect(pose.getByRole("img").className).not.toContain(
        "werner-pose-viewport--empty",
      );
      expect(pose.container.querySelector("img")?.className).toBe(
        mood === "idle" ? "werner-idle" : "",
      );
      pose.unmount();
    }

    const css = fs.readFileSync(
      path.join(__dirname, "werner/animated/animations.css"),
      "utf8",
    );
    expect(css).toContain(".werner-pose-viewport--empty");
    expect(css).toContain("overflow: hidden");
    expect(css).toContain(".werner-pose--empty");
    expect(css).toContain("transform: scale(4.6)");
    expect(css).toContain("transform-origin: 50% 53%");
  });

  it("composes the crop inside sleeping motion and the dizzy reduced still", () => {
    const sleeping = render(<WernerSleeping size={96} />);
    const sleepViewport = sleeping.container.querySelector(
      ".werner-sleep-body.werner-pose-viewport--empty",
    );
    expect(sleepViewport).toBeTruthy();
    expect(sleepViewport?.querySelector("img")?.className).toBe(
      "werner-pose--empty",
    );
    sleeping.unmount();

    const dizzy = render(<WernerDizzy size={88} reduced />);
    const reaction = dizzy.container.querySelector(
      '[data-werner-reaction="dizzy"][data-reduced="true"]',
    );
    expect(
      reaction?.querySelector(".werner-pose-viewport--empty"),
    ).toBeTruthy();
    expect(reaction?.querySelector("img")?.className).toBe(
      "werner-pose--empty",
    );
  });
});
