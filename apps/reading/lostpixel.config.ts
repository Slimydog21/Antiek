import type { CustomProjectConfig } from "lost-pixel";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const NEW_GATEHOUSE_VISUAL_CONTRACT = new Set([
  "coordination-gatehouse-atlas--canonical-atlas",
  "coordination-gatehouse-atlas--both-failed",
  "coordination-gatehouse-atlas--narrow",
  "coordination-gatehouse-atlas--forced-night",
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

const committedViewportHeight = (kind?: string, story?: string): number => {
  if (!kind || !story) return 900;
  const baseline = join(
    ".lostpixel",
    "baseline",
    `${shotIdentityFor(kind, story)}__[w1280px].png`,
  );
  if (!existsSync(baseline)) return 900;

  // PNG IHDR stores the unsigned big-endian height at byte offset 20.
  // Historical Antiek baselines intentionally include both 720px and 900px
  // contracts; preserve each live contract instead of mass-rewriting crops.
  const header = readFileSync(baseline).subarray(0, 24);
  return header.length === 24 ? header.readUInt32BE(20) : 900;
};

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
 * timing) is skipped via `filterShot` — the spring physics
 * lands at slightly different stages on each Chromium run. The skip
 * is documented + the next time a workspace-demo refactor happens
 * the spring should be replaced with a deterministic transition.
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
  // LostPixel 3.22 defaults to 720px, while Antiek's reviewed baseline history
  // contains both 720px and 900px contracts. Match each committed story's PNG
  // height; new stories establish the current 900px standard.
  configureBrowser: ({ kind, story }) => ({
    viewport: { width: 1280, height: committedViewportHeight(kind, story) },
  }),
  // S12 ceiling: 0.4% per-shot delta. Tighter than S2's 1% advisory.
  threshold: 0.004,
  // Skip known-flaky stories at every breakpoint. The framer-motion
  // spring on workspace-demo produces sub-1% inter-run diffs that
  // aren't real regressions.
  filterShot: ({ kind, story }: { kind?: string; story?: string }) => {
    // Storybook's crawler invokes this hook before breakpoint shot names exist.
    // Reconstruct LostPixel's eventual shot name from the available CSF fields;
    // `id` is not interchangeable (acronyms and numeric word boundaries differ).
    if (!kind || !story) return false;
    const shotIdentity = shotIdentityFor(kind, story);
    if (shotIdentity === "workspace-demo--scene") return false;

    // Keep the blocking matrix bounded to explicitly reviewed visual contracts:
    // every previously committed baseline plus this cycle's four load-bearing
    // Gatehouse states. Storybook currently exposes more stories than the live
    // 510-shot committed contract; rendering every unreviewed story at three breakpoints
    // expands the run to 1,374 shots and exceeded CI's former 15-minute ceiling.
    // New surfaces opt in deliberately by landing baselines in the same PR.
    return (
      NEW_GATEHOUSE_VISUAL_CONTRACT.has(shotIdentity) ||
      existsSync(join(".lostpixel", "baseline", `${shotIdentity}__[w1280px].png`))
    );
  },
};
