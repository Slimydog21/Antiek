/**
 * BrainMascot.test.tsx — the real mark renders, and the four-mood guard bites.
 * Mirror of Werner.test.tsx: proves the brain (not an empty span) draws, and
 * the dev runtime guard rejects a fifth mood.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import BrainMascot from "./BrainMascot";

afterEach(cleanup);

describe("BrainMascot mark", () => {
  it("renders the brain — role=img wrapping the Krea pose <img>", () => {
    const { getByRole, container } = render(<BrainMascot />);
    expect(getByRole("img")).toBeTruthy();
    const img = container.querySelector("img");
    expect(img).toBeTruthy();
    expect(img?.getAttribute("src")).toBeTruthy();
  });

  it("renders the closed-eyes blink frame in idle", () => {
    const { container } = render(<BrainMascot mood="idle" />);
    const imgs = container.querySelectorAll("img");
    expect(imgs.length).toBe(2);
  });

  it("does not render the blink frame outside idle", () => {
    const { container } = render(<BrainMascot mood="thinking" />);
    const imgs = container.querySelectorAll("img");
    expect(imgs.length).toBe(1);
  });

  it("throws in dev on a mood outside the four", () => {
    expect(() => render(<BrainMascot mood={"party" as never} />)).toThrow();
  });
});
