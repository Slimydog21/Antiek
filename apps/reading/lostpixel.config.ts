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
 * Animated composed shots are skipped in `filterShot` until each
 * story has a deterministic still. Mac remints do not match Ubuntu
 * Chromium at the 0.4% ceiling.
 */
export const config: CustomProjectConfig = {
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
    breakpoints: [1280, 1024, 768],
  },
  // Freeze the animated scene deterministically. The scene honours
  // prefers-reduced-motion end-to-end (Scene.tsx frozen flag → every layer
  // renders one static frame), so forcing the reduce preference in the
  // screenshot browser makes every shot reproducible instead of catching
  // the aurora/penguins/sketches at a random animation phase.
  browserLaunchOptions: {
    chromium: { args: ["--force-prefers-reduced-motion"] },
  },
  imagePathBaseline: ".lostpixel/baseline",
  imagePathCurrent: ".lostpixel/current",
  imagePathDifference: ".lostpixel/diff",
  generateOnly: false,
  // S12 ceiling: 0.4% per-shot delta. Tighter than S2's 1% advisory.
  threshold: 0.004,
  // filterShot receives the Storybook story (id like
  // 'navigation-app-shell--empty'), not the viewport-suffixed PNG name.
  // Skip composed shots whose scene art still animates; Mac-reminted
  // baselines do not match Ubuntu Chromium, and inter-run animation
  // phase exceeds the 0.4% ceiling. Re-include once each story has a
  // deterministic still (the preview-level reduced-motion freeze is
  // not enough on CI).
  filterShot: (story: { id?: string }) => {
    const id = story?.id ?? "";
    if (!id) return true;
    const animated = [
      "workspace-demo--scene",
      "navigation-app-shell--empty",
      "navigation-app-shell--with-project-tree",
      "home-unified-home-spr-12--default",
      "windows-workspace-windows--two-windows",
      "sketches-processing-seed-sketches--all-three-animated",
      "sketches-processing-seed-sketches--alternate-seed",
      "deep-research-research-wait-arcade--offer",
      "deep-research-research-wait-arcade--playing",
      "werner-station-instruments-complete-atlas--station-instrument-atlas",
      "werner-station-instruments-complete-atlas--knowledge-workflow-grammar",
    ];
    return !animated.some((prefix) => id.startsWith(prefix));
  },
};
