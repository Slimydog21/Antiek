/**
 * Flipbook-feel invent strip class is load-bearing on SessionBrandChrome.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import SessionBrandChrome from "./SessionBrandChrome";

afterEach(cleanup);

describe("sessionLivingTv Flipbook-feel invent motion", () => {
  it("applies antiek-living-tv-invent class to the invent strip", () => {
    render(
      <SessionBrandChrome title="Test door" testIdPrefix="test-door" />,
    );
    const art = screen.getByTestId("test-door-living-tv-art");
    expect(art.className).toMatch(/antiek-living-tv-invent/);
  });
});
