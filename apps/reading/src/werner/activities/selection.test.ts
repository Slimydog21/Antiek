import { describe, expect, it } from "vitest";

import { MODE_TAXONOMY } from "../../shell/workflowTaxonomy";
import {
  activityIdForPathname,
  getActivityForPathname,
  researchLensActivity,
  writingNibActivity,
} from "./index";

const concretePath = (route: string) => route.replace(/:[^/]+/g, "fixture");

const KNOWLEDGE_WORK_ROUTES = MODE_TAXONOMY.filter(
  (mode) =>
    Boolean(mode.route) &&
    (mode.workflow === "research" || mode.workflow === "read"),
).map((mode) => concretePath(mode.route!));

const NON_KNOWLEDGE_WORK_ROUTES = MODE_TAXONOMY.filter(
  (mode) =>
    Boolean(mode.route) &&
    mode.workflow !== "research" &&
    mode.workflow !== "read" &&
    mode.workflow !== "write",
).map((mode) => concretePath(mode.route!));

const WRITING_WORK_ROUTES = MODE_TAXONOMY.filter(
  (mode) => Boolean(mode.route) && mode.workflow === "write",
).map((mode) => concretePath(mode.route!));

describe("station activity route policy", () => {
  it.each(KNOWLEDGE_WORK_ROUTES)(
    "selects research-lens for taxonomy knowledge work: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("research-lens");
      expect(getActivityForPathname(pathname)).toBe(researchLensActivity);
    },
  );

  it.each([
    "/inv/inv-7",
    "/readings",
    "/meta-readings/",
    "/read/meta-reading",
    "/read/meta-reading/asset-2",
  ])("selects research-lens for routed sub-surfaces: %s", (pathname) => {
    expect(activityIdForPathname(pathname)).toBe("research-lens");
    expect(getActivityForPathname(pathname)).toBe(researchLensActivity);
  });

  it.each(NON_KNOWLEDGE_WORK_ROUTES)(
    "keeps ice-fishing on taxonomy non-knowledge work: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("ice-fishing");
    },
  );

  it.each(WRITING_WORK_ROUTES)(
    "selects writing-nib for taxonomy writing work: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("writing-nib");
      expect(getActivityForPathname(pathname)).toBe(writingNibActivity);
    },
  );

  it.each(["/write", "/write/draft-7", "/create", "/create/"])(
    "keeps the nib across writing route boundaries: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("writing-nib");
    },
  );

  it.each(["/home", "/deep-researcher", "/not-a-route"])(
    "does not leak the lens onto unknown route lookalikes: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("ice-fishing");
    },
  );

  it.each([
    "/library",
    "/wrestle/document-4",
    "/notebooks",
    "/notebook/notebook-2",
    "/brainstorm",
    "/outcomes/synthesis-5",
    "/replay/inv-3",
    "/backtest/synthesis-8",
  ])(
    "keeps the lens across flagship Research + Read surfaces: %s",
    (pathname) => {
      expect(activityIdForPathname(pathname)).toBe("research-lens");
    },
  );

  it("keeps brainstorm in Research rather than treating ideation as Write", () => {
    expect(activityIdForPathname("/brainstorm")).toBe("research-lens");
  });
});
