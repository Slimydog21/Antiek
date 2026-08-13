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
import BrainMascot from "./BrainMascot";
import WernerSleeping from "./werner/animated/WernerSleeping";
import WernerThinking from "./werner/animated/WernerThinking";
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

  it("keeps the public thinking state semantically honest and accessible", () => {
    const thinking = render(
      <WernerThinking size={40} label="Tracing the evidence" />,
    );
    const status = thinking.getByRole("status", {
      name: "Tracing the evidence",
    });
    const thinkingSrc = status.querySelector("img")?.getAttribute("src");
    expect(thinkingSrc).toBeTruthy();
    expect(status.querySelectorAll('[aria-hidden="true"]')).toHaveLength(5);

    const idle = render(<Werner mood="idle" size={40} />);
    expect(thinkingSrc).not.toBe(
      idle.container.querySelector("img")?.getAttribute("src"),
    );
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

  it("rests the brain on the empty mood without widening the mood API", () => {
    const sleeping = render(
      <WernerSleeping size={96} label="The brain is resting" />,
    );
    const root = sleeping.getByRole("img", { name: "The brain is resting" });
    // The body layer delegates to the canonical empty pose (one img), the
    // zZz chrome is a decorative svg layer on the wrapper.
    const poseImg = root.querySelector("img");
    expect(poseImg?.getAttribute("src")).toBeTruthy();
    expect(root.querySelector(".werner-sleep-body")).toBeTruthy();
    expect(root.querySelector(".werner-sleep-zzz-layer")).toBeTruthy();
    expect(root.querySelectorAll('[aria-hidden="true"]').length).toBeGreaterThanOrEqual(1);

    const empty = render(<BrainMascot mood="empty" size={96} />);
    expect(poseImg?.getAttribute("src")).toBe(
      empty.container.querySelector("img")?.getAttribute("src"),
    );
    empty.unmount();
    sleeping.unmount();

    const still = render(<WernerSleeping size={96} reduced />);
    expect(still.getByRole("img").getAttribute("data-reduced")).toBe("true");
    expect(still.container.querySelector(".werner-sleep-still")).toBeTruthy();
    expect(still.container.querySelector(".werner-sleep-body")).toBeNull();
    expect(still.container.querySelector(".werner-sleep-zzz-layer")).toBeNull();
  });

  it("renders the brain in the reduced dizzy still", () => {
    const dizzy = render(<WernerDizzy size={88} reduced />);
    const reaction = dizzy.container.querySelector(
      '[data-werner-reaction="dizzy"][data-reduced="true"]',
    );
    expect(reaction?.querySelector("img")?.getAttribute("src")).toBeTruthy();
  });
});
