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

  it("layers the authored sleeping pose without widening the mood API", () => {
    const sleeping = render(
      <WernerSleeping size={96} label="Werner is resting" />,
    );
    const root = sleeping.getByRole("img", { name: "Werner is resting" });
    const layers = root.querySelectorAll(
      'img[data-werner-authored-pose="sleeping"]',
    );
    expect(layers).toHaveLength(2);
    expect(layers[0]?.getAttribute("src")).toBe(layers[1]?.getAttribute("src"));
    expect(layers[0]?.className).toContain("werner-sleep-body");
    expect(layers[1]?.className).toContain("werner-sleep-zzz-layer");
    expect(root.querySelectorAll('[aria-hidden="true"]')).toHaveLength(2);

    const empty = render(<Werner mood="empty" size={96} />);
    expect(layers[0]?.getAttribute("src")).not.toBe(
      empty.container.querySelector("img")?.getAttribute("src"),
    );
    empty.unmount();
    sleeping.unmount();

    const still = render(<WernerSleeping size={96} reduced />);
    expect(still.getByRole("img").getAttribute("data-reduced")).toBe("true");
    expect(
      still.container.querySelectorAll(
        'img[data-werner-authored-pose="sleeping"]',
      ),
    ).toHaveLength(1);
    expect(still.container.querySelector(".werner-sleep-still")).toBeTruthy();
    expect(still.container.querySelector(".werner-sleep-body")).toBeNull();
    expect(still.container.querySelector(".werner-sleep-zzz-layer")).toBeNull();

    const css = fs.readFileSync(
      path.join(__dirname, "werner/animated/animations.css"),
      "utf8",
    );
    expect(css).toContain("clip-path: inset(38.6% 0 0 0)");
    expect(css).toContain("clip-path: inset(0 0 61.4% 0)");
    expect(css).toContain(".werner-sleep-zzz-layer");
  });

  it("keeps the Cycle 563 empty crop in the reduced dizzy still", () => {
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
