/**
 * visualtest-update-guard — stops macOS local remints from contaminating the
 * lostpixel baselines (2026-10-08 lesson, PR #3765).
 *
 * Baselines are minted by CI on Ubuntu Chromium. A local `visualtest:update`
 * on macOS re-renders every story under a different text rasterizer, so
 * EVERY text-bearing baseline drifts past the diff threshold (observed: 589
 * PNGs of byte churn, text lines at 0.42–0.70% vs the 0.4% ceiling). The
 * result looks like a successful update and poisons every subsequent CI run.
 *
 * The supported flow for intentional visual changes:
 *   1. push the PR and let the lostpixel check run on Ubuntu;
 *   2. download the failing run's `lostpixel-diffs` artifact;
 *   3. copy the artifact's `current/` renders for EXACTLY the stories the PR
 *      intentionally changed into `.lostpixel/baseline/`;
 *   4. view the diff images and confirm the change matches intent;
 *   5. commit only those files.
 *
 * On Linux the guard passes silently (CI and Linux dev machines rasterize
 * identically to the baseline host). On Darwin it refuses unless the run is
 * a deliberate full remint acknowledged with ANTIK_VISUAL_REMINT_ACK=1 (the
 * PR must say so — CI will diff the whole tree until it remints).
 */

export interface GuardDecision {
  ok: boolean;
  message: string;
}

export const REMINT_ACK_ENV = "ANTIK_VISUAL_REMINT_ACK";

export function decide(platform: string, ack: string | undefined): GuardDecision {
  if (platform !== "darwin") return { ok: true, message: "" };
  if (ack) {
    return {
      ok: true,
      message:
        `visualtest:update — macOS override acknowledged (${REMINT_ACK_ENV}=${ack}). ` +
        "A full local remint produces macOS-rasterized baselines that CI (Ubuntu) " +
        "will diff against: expect the whole tree to fail until CI remints.",
    };
  }
  return {
    ok: false,
    message: [
      "visualtest:update refused on macOS.",
      "",
      "Baselines are Ubuntu-Chromium renders minted by CI; a local macOS run",
      "rewrites every baseline with rasterization churn (observed: 589 files,",
      "all false diffs). To land an intentional visual change, mint from the CI",
      "artifact instead:",
      "",
      "  gh run download <lostpixel-run-id> -n lostpixel-diffs",
      "  # copy current/<story>.png for the stories you changed into",
      "  # apps/reading/.lostpixel/baseline/ — nothing else — then commit.",
      "",
      `For a deliberate full remint (e.g. a Chromium bump), rerun with`,
      `${REMINT_ACK_ENV}=1 and say so in the PR.`,
    ].join("\n"),
  };
}

const isMain = process.argv[1]?.endsWith("visualtest_update_guard.ts");
if (isMain) {
  const d = decide(process.platform, process.env[REMINT_ACK_ENV]);
  if (!d.ok) {
    console.error(d.message);
    process.exit(1);
  }
  if (d.message) console.warn(d.message);
}
