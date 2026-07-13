import { describe, expect, it } from "vitest";

import {
  activityIdForPathname,
  getActivityForPathname,
  researchLensActivity,
} from "./index";

describe("station activity route policy", () => {
  it.each([
    "/",
    "/inv/inv-7",
    "/deep-research",
    "/deep-research/session-4",
    "/my-research",
    "/read/book-9",
    "/read/meta-reading",
    "/read/meta-reading/asset-2",
    "/readings",
    "/meta-readings/",
  ])("selects research-lens for knowledge work: %s", (pathname) => {
    expect(activityIdForPathname(pathname)).toBe("research-lens");
    expect(getActivityForPathname(pathname)).toBe(researchLensActivity);
  });

  it.each([
    "/home",
    "/write",
    "/create/draft-3",
    "/settings",
    "/billing",
    "/operator",
    "/library",
    "/deep-researcher",
  ])("keeps ice-fishing on non-knowledge routes: %s", (pathname) => {
    expect(activityIdForPathname(pathname)).toBe("ice-fishing");
  });
});
