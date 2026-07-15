import type { CustomProjectConfig } from "lost-pixel";

const scopedStoryId = process.env.LOSTPIXEL_STORY_ID;
const scopedStoryIds = scopedStoryId?.split(",").filter(Boolean) ?? [];
const includesNarrowIceHoleProof = scopedStoryIds.some((id) =>
  id.startsWith("read-werner-ice-hole--"),
);
const includesNarrowFjordSkipProof = scopedStoryIds.some((id) =>
  id.startsWith("brainstorm-fjord-skip--"),
);

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
  configureBrowser: ({ id }) =>
    id === "loop-1-researchrouteinstrument--dark"
      ? { colorScheme: "dark" }
      : {},
  storybookShots: {
    storybookUrl: "./storybook-static",
    /**
     * S11 acceptance — multi-breakpoint screenshot matrix.
     *
     * Spec wording: "Lost-Pixel baselines updated for breakpoint
     * screenshots (≥ 1280, 1024, 768)."
     *
     * lost-pixel takes a `breakpoints: number[]` array under
     * storybookShots; each entry is a viewport WIDTH in pixels. The
     * tool re-renders every story at every width + writes baselines
     * to `.lostpixel/baseline/<story>--<width>.png` (the width is
     * suffixed automatically). The default 1280 stays as the primary
     * baseline; 1024 + 768 catch the lg / md tier breakpoints from
     * `useViewportTier`. We exclude < 768 from the matrix — the sm
     * tier renders the "open a larger screen" splash, not the
     * workspace shell, so a screenshot at 600px would only show the
     * splash.
     */
    breakpoints:
      includesNarrowIceHoleProof || includesNarrowFjordSkipProof
        ? [1280, 1024, 768, 375]
        : [1280, 1024, 768],
  },
  imagePathBaseline: ".lostpixel/baseline",
  imagePathCurrent: ".lostpixel/current",
  imagePathDifference: ".lostpixel/diff",
  generateOnly: false,
  // Normal legacy sweep remains advisory; an explicitly scoped story is a
  // blocking evidence gate and must surface its current/diff artifacts.
  failOnDifference: scopedStoryIds.length > 0,
  // The scoped authored plate permits only microscopic Chromium raster jitter
  // (roughly 6–10 pixels across the configured viewports). The legacy sweep
  // retains its established 0.4% advisory ceiling.
  threshold: scopedStoryIds.length > 0 ? 0.00001 : 0.004,
  // Skip known-flaky stories at every breakpoint. The framer-motion
  // spring on workspace-demo produces sub-1% inter-run diffs that
  // aren't real regressions.
  filterShot: ({ id }: { id?: string }) => {
    if (scopedStoryIds.length > 0) return scopedStoryIds.includes(id ?? "");
    if (!id) return true;
    return !id.startsWith("workspace-demo--scene");
  },
};
