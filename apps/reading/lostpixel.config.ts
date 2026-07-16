import type { CustomProjectConfig } from "lost-pixel";

const BLOCKING_VISUAL_CONTRACT = new Set([
  "coordination-gatehouse-atlas--canonical-atlas",
  "coordination-gatehouse-atlas--both-failed",
  "coordination-gatehouse-atlas--narrow",
  "coordination-gatehouse-atlas--forced-night",
  "multimedia-production-bay--night",
]);

// LostPixel 3.22 derives baseline names with lodash.kebabcase(kind/story).
// Keep the equivalent word boundaries here so the discovery-time filter is
// keyed to the same durable identity without reaching into a transitive dep.
const toShotSegment = (value: string): string =>
  value
    .normalize("NFKD")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1-$2")
    .replace(/([a-z0-9])([A-Z])/g, "$1-$2")
    .replace(/([A-Za-z])(\d)/g, "$1-$2")
    .replace(/(\d)([A-Za-z])/g, "$1-$2")
    .replace(/[^A-Za-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .toLowerCase();

const shotIdentityFor = (kind: string, story: string): string =>
  `${toShotSegment(kind)}--${toShotSegment(story)}`;

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
 * `filterShot` is an explicit reviewed-contract allowlist. Historical
 * baselines remain in the repository for migration, but are not described as
 * blocking coverage until their Ubuntu renders have been reviewed and opted in.
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
  imagePathBaseline: ".lostpixel/baseline",
  imagePathCurrent: ".lostpixel/current",
  imagePathDifference: ".lostpixel/diff",
  // LostPixel 3.22's local comparison runner only propagates a failing diff
  // exit code in generate-only mode (the official self-hosted configuration).
  generateOnly: true,
  // A comparison job is a gate only when over-threshold diffs reach the exit
  // code. Without this, LostPixel prints red differences and still returns 0.
  failOnDifference: true,
  // New blocking contracts use one explicit viewport height. The legacy PNG
  // archive mixes historical heights and remains outside this honest gate.
  configureBrowser: () => ({ viewport: { width: 1280, height: 900 } }),
  // S12 ceiling: 0.4% per-shot delta. Tighter than S2's 1% advisory.
  threshold: 0.004,
  // Select only reviewed blocking stories at every breakpoint.
  filterShot: ({ kind, story }: { kind?: string; story?: string }) => {
    // Storybook's crawler invokes this hook before breakpoint shot names exist.
    // Reconstruct LostPixel's eventual shot name from the available CSF fields;
    // `id` is not interchangeable (acronyms and numeric word boundaries differ).
    if (!kind || !story) return false;
    const shotIdentity = shotIdentityFor(kind, story);
    // The previous broad matrix had 388 Ubuntu diffs hidden by a swallowed exit
    // code. Do not misrepresent those stale files as protected coverage: start
    // the real blocking contract with this cycle's four Gatehouse states and
    // the repaired Multimedia night state, then opt in reviewed surfaces only.
    return BLOCKING_VISUAL_CONTRACT.has(shotIdentity);
  },
};
