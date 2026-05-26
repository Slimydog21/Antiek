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
  it("renders the penguin — role=img with a coat ellipse in the SVG", () => {
    const { getByRole, container } = render(<Werner />);
    expect(getByRole("img")).toBeTruthy();
    // The coat ellipse is the body silhouette; its presence means we drew the
    // penguin, not an empty wrapper.
    expect(container.querySelector("ellipse")).toBeTruthy();
  });

  it("throws in dev on a mood outside the four", () => {
    expect(() => render(<Werner mood={"party" as never} />)).toThrow();
  });
});
