/**
 * Werner.test.tsx — the real mark renders, and the four-mood guard bites.
 * Closes the U-02 gap: nothing else proved the penguin (not an empty span)
 * actually draws, or that the dev runtime guard rejects a fifth mood.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";

import Werner from "./Werner";

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
});
