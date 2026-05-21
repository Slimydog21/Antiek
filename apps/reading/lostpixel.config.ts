import type { CustomProjectConfig } from "lost-pixel";

/**
 * Lost-Pixel — visual regression for Antiek's Storybook.
 *
 * S12 promotes to a CI blocker at 0.4% threshold (was 1% in S2). Runs
 * locally + in `.github/workflows/visualtest.yml`. Any intentional
 * visual change must include the .lostpixel/baseline/*.png updates
 * in the same PR.
 *
 *   npm run visualtest         # check current vs baseline
 *   npm run visualtest:update  # accept current as the new baseline
 *
 * Known flaky story `workspace-demo--scene` (framer-motion spring
 * timing) is skipped via `shotsExcludeList` — the spring physics
 * lands at slightly different stages on each Chromium run. The skip
 * is documented + the next time a workspace-demo refactor happens
 * the spring should be replaced with a deterministic transition.
 */
export const config: CustomProjectConfig = {
  storybookShots: {
    storybookUrl: "./storybook-static",
  },
  imagePathBaseline: ".lostpixel/baseline",
  imagePathCurrent: ".lostpixel/current",
  imagePathDifference: ".lostpixel/diff",
  generateOnly: false,
  // S12 ceiling: 0.4% per-shot delta. Tighter than S2's 1% advisory.
  threshold: 0.004,
  // Skip known-flaky stories. The framer-motion spring on workspace-demo
  // produces sub-1% inter-run diffs that aren't real regressions.
  filterShot: ({ shotName }: { shotName?: string }) => {
    return shotName !== "workspace-demo--scene";
  },
};
