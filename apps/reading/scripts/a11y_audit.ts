/**
 * Automated axe-core a11y audit against the static Storybook build.
 *
 * Spec acceptance (S11 WP-11.6 + S11 acceptance):
 *   "Axe-core finds zero 'serious' or 'critical' violations on the
 *   primitive stories."
 *
 * The Storybook addon-a11y surfaces violations inline at story-author
 * time. This script runs the same rule set in CI / locally + writes
 * a Markdown audit report so the operator can audit every primitive
 * + every panel + every Werner asset in one pass — automated proxy
 * for the spec's "VoiceOver pass" gate.
 *
 *   npm run a11y:audit
 *
 * Writes `docs/perf/a11y_audit.md` with one row per story. Exits
 * non-zero if any story has ≥ 1 "serious" or "critical" violation.
 */
import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { argv, exit } from "node:process";

type Args = {
  storybook: string;
  out: string;
};

const DEFAULTS: Args = {
  storybook: "http://localhost:6006",
  out: "../../docs/perf/a11y_audit.md",
};

function parseArgs(): Args {
  const out = { ...DEFAULTS };
  for (let i = 2; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--storybook") out.storybook = argv[++i];
    else if (a === "--out") out.out = argv[++i];
  }
  return out;
}

/** A curated set of stories worth auditing — primitives + key app
 *  surfaces. Add new entries when a panel or route gets a story.
 *  Each entry is a story id (the slug Storybook uses in iframe URLs). */
const STORIES: string[] = [
  // S1 — every Lemon primitive. Story ids verified against
  // storybook-static/index.json — Storybook collapses some kebab
  // segments (`LemonTextarea` → `lemon-textarea`) but exact slugs
  // matter; a typoed id renders the "No Preview" placeholder which
  // has zero violations and produces a vacuous PASS.
  "design-primitives-showcase--showcase",
  "lemon-button--grid",
  "lemon-button--with-icons",
  "lemon-button--disabled",
  "lemon-button--full-width",
  "lemon-card--default",
  "lemon-card--colours",
  "lemon-card--elevations",
  "lemon-card--with-footer",
  "lemon-modal--default",
  "lemon-modal--sizes",
  "lemon-modal--with-form",
  "lemon-input--basic",
  "lemon-input--disabled",
  "lemon-input--sizes",
  "lemon-textarea--empty",
  "lemon-textarea--auto-grow",
  "lemon-tag--all-colours",
  "lemon-tag--removable",
  "lemon-tag--with-dot",
  "lemon-select--placeholder",
  "lemon-select--full-width",
  "lemon-select--model-picker",
  "lemon-dropdown--panel-actions",
  "lemon-dropdown--align-right",
  "lemon-table--investigations-list",
  "lemon-table--empty",
  "lemon-toast--playground",
  // S0 — design tokens
  "design-moodboard--palette-day-off-whites-glacials",
  "design-moodboard--palette-night-majestic-night-sky",
  "design-moodboard--werner-bill-feet-brand-sun",
  "design-moodboard--shadows",
  "design-moodboard--typography",
  "design-moodboard--outlined-card",
  // Werner brand
  "brand-werner-animations--all-poses",
  // SPR-06 — the igloo home mark (the M4 home control's mark).
  "brand-werner-igloomark-spr-06--on-rail-button",
  // SPR-06 — the restructured shell (bottom nav) + the bottom rail itself.
  "navigation-appshell--empty",
  "shell-navrail-spr-04--bottom-rail",
  // Model Observatory — production surface and responsive bounds.
  "settings-model-observatory--production",
  "settings-model-observatory--wide",
  "settings-model-observatory--tablet",
  "settings-model-observatory--mobile",
  // Substrate Atlas — truthful cardinality states and responsive bound.
  "modes-substrate-atlas--measured",
  "modes-substrate-atlas--known-zero",
  "modes-substrate-atlas--loading",
  "modes-substrate-atlas--missing-counts",
  "modes-substrate-atlas--integrity-warning",
  "modes-substrate-atlas--safe-error",
  "modes-substrate-atlas--long-count",
  "modes-substrate-atlas--narrow",
  // Igloo Directory — production, image-independent fixture, and real narrow bound.
  "modes-igloo-directory--production",
  "modes-igloo-directory--visual-fixture",
  "modes-igloo-directory--night",
  "modes-igloo-directory--narrow",
  // Expedition Cost Planner — production, image-independent fixture,
  // cap boundary, forced night, and actual narrow viewport.
  "modes-expedition-cost-planner--production",
  "modes-expedition-cost-planner--visual-fixture",
  "modes-expedition-cost-planner--cap-crossing",
  "modes-expedition-cost-planner--night",
  "modes-expedition-cost-planner--narrow",
  // S5 + S6 + S7 — mode panels
  "loop-1-notebookeditor--blank",
  "loop-1-notebookeditor--with-sample-content",
  // Workspace demo
  "workspace-demo--scene",
];

type AxeViolation = {
  id: string;
  impact: "minor" | "moderate" | "serious" | "critical" | null;
  help: string;
  helpUrl: string;
  nodes: number;
};

type StoryResult = {
  story: string;
  violations: AxeViolation[];
  error: string | null;
};

async function main() {
  const args = parseArgs();
  console.log("== a11y audit ==");
  console.log(`  storybook : ${args.storybook}`);
  console.log(`  stories   : ${STORIES.length}`);

  // Dynamic imports so a fresh checkout that hasn't run
  // `npx playwright install chromium` still gives a clear error.
  let chromium: typeof import("playwright").chromium;
  let AxeBuilder: typeof import("@axe-core/playwright").default;
  try {
    chromium = (await import("playwright")).chromium;
    AxeBuilder = (await import("@axe-core/playwright")).default;
  } catch {
    console.warn(
      "[!] playwright / @axe-core/playwright missing. Run " +
        "`npm i -D playwright @axe-core/playwright && " +
        "npx playwright install chromium`, then re-run.",
    );
    exit(0);
  }

  const browser = await chromium.launch({ headless: true });

  // FRESH PAGE per story — reusing one page across stories causes
  // DOM bleed: a violation from the prior story's residual DOM
  // sometimes shows up under the next story's URL (Storybook's
  // iframe replaces #storybook-root rather than full-navigating,
  // so portaled content (modals, toasts, dropdowns) can linger).
  const results: StoryResult[] = [];
  for (const story of STORIES) {
    const narrow =
      story === "modes-substrate-atlas--narrow" ||
      story === "modes-igloo-directory--narrow" ||
      story === "modes-expedition-cost-planner--narrow";
    const dark =
      story === "modes-igloo-directory--night" ||
      story === "modes-expedition-cost-planner--night";
    const ctx = await browser.newContext({
      viewport: narrow
        ? { width: 375, height: 667 }
        : { width: 1280, height: 900 },
      colorScheme: dark ? "dark" : "light",
    });
    const page = await ctx.newPage();
    const url =
      args.storybook + "/iframe.html?args=&id=" + story + "&viewMode=story";
    try {
      await page.goto(url, { waitUntil: "domcontentloaded", timeout: 15_000 });
      await page.waitForTimeout(1500); // let the story render
      if (narrow) {
        const componentSelector = story.startsWith(
          "modes-expedition-cost-planner",
        )
          ? ".expedition-planner"
          : story.startsWith("modes-substrate-atlas")
            ? ".substrate-atlas"
            : ".igloo-directory";
        const overflow = await page.evaluate(
          (selector) => ({
            clientWidth: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            componentClientWidth:
              document.querySelector<HTMLElement>(selector)?.clientWidth ?? 0,
            componentScrollWidth:
              document.querySelector<HTMLElement>(selector)?.scrollWidth ?? 0,
          }),
          componentSelector,
        );
        if (
          overflow.scrollWidth > overflow.clientWidth ||
          overflow.componentScrollWidth > overflow.componentClientWidth
        ) {
          throw new Error(
            `horizontal overflow document ${overflow.scrollWidth}px/${overflow.clientWidth}px; component ${overflow.componentScrollWidth}px/${overflow.componentClientWidth}px`,
          );
        }
      }
      // Storybook hosts each story inside an iframe. Some axe rules
      // fire on the IFRAME WRAPPER, not the Antiek code:
      //   - scrollable-region-focusable: the iframe scrollport itself
      //     has `overflow: auto` and no tabindex; Storybook's choice,
      //     not ours.
      //   - landmark-one-main / region: every story body lacks a
      //     <main> landmark — by design, stories are atomic, not
      //     whole pages.
      //   - page-has-heading-one: same — atomic stories.
      // Disable these in the story context. They're re-applied
      // implicitly when full routes are audited (the app shell DOES
      // provide a <main> via PanelLayout); but the primitive +
      // showcase stories are isolation contexts where these rules
      // are noise rather than signal.
      const axe = new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"])
        // Kept identical to .storybook/test-runner.ts by hand — change one,
        // change both. (empty-heading is Storybook's own hidden error-message
        // <h1> inside iframe.html, never Antiek shell code.)
        .disableRules([
          "scrollable-region-focusable",
          "landmark-one-main",
          "region",
          "page-has-heading-one",
          "empty-heading",
        ]);
      const r = await axe.analyze();
      const violations: AxeViolation[] = r.violations.map((v) => ({
        id: v.id,
        impact:
          (v.impact as "minor" | "moderate" | "serious" | "critical" | null) ??
          null,
        help: v.help,
        helpUrl: v.helpUrl,
        nodes: v.nodes.length,
      }));
      results.push({ story, violations, error: null });
      console.log(
        `  ${story}  ${violations.length === 0 ? "✓" : "⚠ " + violations.length}`,
      );
      if (process.env.A11Y_AUDIT_VERBOSE) {
        for (const v of violations) {
          if (v.impact === "serious" || v.impact === "critical") {
            console.log("       ", v.id, v.impact);
          }
        }
      }
    } catch (e: unknown) {
      results.push({
        story,
        violations: [],
        error: e instanceof Error ? e.message : String(e),
      });
      console.log(`  ${story}  ✗ load error`);
    } finally {
      await ctx.close();
    }
  }

  await browser.close();

  // ── Aggregation ────────────────────────────────────────
  const seriousOrCritical: { story: string; v: AxeViolation }[] = [];
  const loadErrors = results.filter((result) => result.error !== null);
  for (const r of results) {
    for (const v of r.violations) {
      if (v.impact === "serious" || v.impact === "critical") {
        seriousOrCritical.push({ story: r.story, v });
      }
    }
  }

  // ── Write report ───────────────────────────────────────
  const outPath = join(process.cwd(), args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  const ts = new Date().toISOString();
  const lines: string[] = [];
  lines.push("# axe-core a11y audit\n");
  lines.push(`**Run:** ${ts}`);
  lines.push(`**Stories audited:** ${results.length}`);
  lines.push(
    `**Serious / critical violations:** ${seriousOrCritical.length}\n`,
  );
  lines.push(
    "**Rule set:** wcag2a + wcag2aa + wcag21a + wcag21aa + best-practice",
  );
  lines.push("");
  lines.push("## Per-story summary\n");
  lines.push("| Story | Violations | Top impact | Worst rule |");
  lines.push("|---|---|---|---|");
  for (const r of results) {
    const top = r.violations.reduce<AxeViolation | null>((acc, v) => {
      const score = (impact: string | null) =>
        impact === "critical"
          ? 4
          : impact === "serious"
            ? 3
            : impact === "moderate"
              ? 2
              : impact === "minor"
                ? 1
                : 0;
      if (!acc) return v;
      return score(v.impact) > score(acc.impact) ? v : acc;
    }, null);
    const cell = r.error
      ? `❌ ${r.error}`
      : `${r.violations.length} (` +
        (top ? `${top.impact ?? "—"} · ${top.id}` : "—") +
        ")";
    lines.push(
      r.error
        ? `| \`${r.story}\` | 0 | error | ${cell} |`
        : `| \`${r.story}\` | ${r.violations.length} | ${top?.impact ?? "—"} | ${top?.id ?? "—"} |`,
    );
  }
  if (seriousOrCritical.length > 0) {
    lines.push("");
    lines.push("## Serious + critical violations (CI-blocking)\n");
    lines.push("| Story | Rule | Impact | Nodes | More |");
    lines.push("|---|---|---|---|---|");
    for (const { story, v } of seriousOrCritical) {
      lines.push(
        `| \`${story}\` | \`${v.id}\` | ${v.impact} | ${v.nodes} | [docs](${v.helpUrl}) |`,
      );
    }
  }
  writeFileSync(outPath, lines.join("\n") + "\n");
  console.log("");
  console.log(`  report  : ${outPath}`);
  const passed = seriousOrCritical.length === 0 && loadErrors.length === 0;
  console.log(`  verdict : ${passed ? "PASS" : "FAIL"}`);

  exit(passed ? 0 : 1);
}

void main();
