/**
 * SessionBrandChrome.test.tsx — shared densify chrome contract.
 */
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import SessionBrandChrome, {
  SESSION_LIVING_TV_ASSET_HINT,
} from "./SessionBrandChrome";

afterEach(cleanup);

describe("SessionBrandChrome", () => {
  it("renders thinking mark + living-TV invent with prefixed testids", () => {
    render(
      <SessionBrandChrome testIdPrefix="trust-center" title="Trust Center">
        <p>Standing commitments.</p>
      </SessionBrandChrome>,
    );
    expect(screen.getByText("Trust Center")).toBeTruthy();
    expect(screen.getByTestId("trust-center-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "trust-center-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      SESSION_LIVING_TV_ASSET_HINT,
    );
    expect(screen.getByText("Standing commitments.")).toBeTruthy();
  });
});
