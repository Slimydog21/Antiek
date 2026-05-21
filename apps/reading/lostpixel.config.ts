import type { CustomProjectConfig } from "lost-pixel";

/**
 * Lost-Pixel — visual regression for Antiek's Storybook.
 *
 * S2 lands this as advisory; S12 promotes to a CI blocker at a tighter
 * threshold (0.4%). Run locally:
 *
 *   npm run visualtest         # checks current vs baseline
 *   npm run visualtest:update  # accepts current as the new baseline
 *
 * Baselines live in .lostpixel/baseline/ and are checked into git. Any
 * intentional visual change must include an explicit baseline-update
 * commit alongside the source change.
 */
export const config: CustomProjectConfig = {
  storybookShots: {
    storybookUrl: "./storybook-static",
  },
  imagePathBaseline: ".lostpixel/baseline",
  imagePathCurrent: ".lostpixel/current",
  imagePathDifference: ".lostpixel/diff",
  generateOnly: false,
  // 1% tolerance for type anti-aliasing slop between Chromium runs.
  // S12 ratchets this to 0.4%.
  threshold: 0.01,
  // Note on filtering: lost-pixel's filter callback signature shifts
  // between versions; keep that out of v1 baseline so initial setup
  // is friction-free. Add filters in S12 when we promote to CI-blocking.
};
