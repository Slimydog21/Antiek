/**
 * Automated axe-core a11y audit against the static Storybook build, in day
 * AND night.
 *
 * Spec acceptance (S11 WP-11.6 + S11 acceptance):
 *   "Axe-core finds zero 'serious' or 'critical' violations on the
 *   primitive stories."
 *
 * The Storybook addon-a11y surfaces violations inline at story-author
 * time. This script runs the same rule set (imported from
 * .storybook/visual-axes.ts, shared with the test-runner gate) and writes a
 * Markdown report so the operator can audit every primitive, panel and
 * brand asset in one pass. It is the automated proxy for the spec's
 * "VoiceOver pass" gate.
 *
 *   npm run a11y:audit                         # curated stories, both themes
 *   tsx scripts/a11y_audit.ts --all            # every story in index.json
 *   tsx scripts/a11y_audit.ts --themes dark    # one theme
 *
 * Every story is audited once per theme. The theme is forced the way the app
 * gets it (the preview's theme global plus the matching colour scheme) and
 * checked on <html data-theme> before axe runs; CSS motion is frozen at rest
 * (zero durations, not reduced motion, so the full-motion design is audited).
 *
 * Writes `docs/perf/a11y_audit.md` (or --out). Exits 1 if any story has a
 * serious or critical violation in either theme, or if any story could not
 * be audited: an id missing from the build, a load error, or a theme that did
 * not apply. A story that was never audited is not a pass.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { argv, exit } from "node:process";
import { pathToFileURL } from "node:url";

import {
  AXE_DISABLED_RULES,
  AXE_TAGS,
  AXIS_THEMES,
  expectTheme,
  freezeMotion,
  storyUrl,
  type AxisTheme,
} from "../.storybook/visual-axes";

type Args = {
  storybook: string;
  out: string;
  themes: AxisTheme[];
  all: boolean;
  concurrency: number;
};

const DEFAULTS: Args = {
  storybook: "http://localhost:6006",
  out: "../../docs/perf/a11y_audit.md",
  themes: [...AXIS_THEMES],
  all: false,
  concurrency: 4,
};

export function parseArgs(args: readonly string[]): Args {
  const out: Args = { ...DEFAULTS, themes: [...DEFAULTS.themes] };
  for (let i = 0; i < args.length; i++) {
    const a = args[i];
    if (a === "--storybook") out.storybook = args[++i];
    else if (a === "--out") out.out = args[++i];
    else if (a === "--all") out.all = true;
    else if (a === "--concurrency") out.concurrency = Math.max(1, Number(args[++i]) || 1);
    else if (a === "--themes") {
      const asked = args[++i].split(",").map((t) => t.trim());
      const bad = asked.filter((t) => !(AXIS_THEMES as readonly string[]).includes(t));
      if (bad.length) throw new Error(`--themes: unknown theme(s) ${bad.join(", ")}`);
      out.themes = asked as AxisTheme[];
    }
  }
  return out;
}

/** A curated set of stories worth auditing: primitives + key app
 *  surfaces. Every story tagged `a11y-audit` (the test-runner gate's set)
 *  is added from the build's index. Ids are checked against that index
 *  before anything runs: a typoed or renamed id renders Storybook's
 *  "No Preview" screen, which has zero violations and would be a
 *  vacuous PASS. (Four ids here had drifted that way: the moodboard
 *  stories were renamed and the SPR-06 igloo mark story was removed.) */
export const STORIES: string[] = [
  // S1 — every Lemon primitive.
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
  "design-moodboard--palette-day",
  "design-moodboard--palette-night",
  "design-moodboard--mascot-palette",
  "design-moodboard--shadows",
  "design-moodboard--typography",
  "design-moodboard--outlined-card",
  // Antiek brand
  "brand-mascot-animations--all-poses",
  // SPR-06 — the restructured shell (bottom nav) + the bottom rail itself.
  "navigation-appshell--empty",
  "shell-navrail-spr-04--bottom-rail",
  // S5 + S6 + S7 — mode panels
  "loop-1-notebookeditor--blank",
  "loop-1-notebookeditor--with-sample-content",
  // Workspace demo
  "workspace-demo--scene",
];

export type Impact = "minor" | "moderate" | "serious" | "critical";

export type AxeViolation = {
  id: string;
  impact: Impact | null;
  help: string;
  helpUrl: string;
  nodes: number;
};

export type AuditJob = { story: string; theme: AxisTheme };

export type AuditResult = AuditJob & {
  violations: AxeViolation[];
  error: string | null;
};

type IndexEntry = { id?: string; type?: string; tags?: string[] };

/** Story ids in a Storybook build's index.json, and those tagged a11y-audit. */
export function readIndex(index: unknown): { ids: Set<string>; tagged: string[] } {
  const entries = Object.values(
    ((index as { entries?: Record<string, IndexEntry> })?.entries ?? {}) as Record<
      string,
      IndexEntry
    >,
  ).filter((e) => e.type === "story" && typeof e.id === "string");
  return {
    ids: new Set(entries.map((e) => e.id as string)),
    tagged: entries.filter((e) => e.tags?.includes("a11y-audit")).map((e) => e.id as string),
  };
}

/**
 * One job per story per theme, and the ids the build does not contain.
 * Missing ids are reported, never silently skipped or audited.
 */
export function planAudit(
  stories: readonly string[],
  indexIds: ReadonlySet<string>,
  themes: readonly AxisTheme[],
): { jobs: AuditJob[]; missing: string[] } {
  const unique = [...new Set(stories)];
  const missing = unique.filter((s) => !indexIds.has(s));
  const jobs = unique
    .filter((s) => indexIds.has(s))
    .flatMap((story) => themes.map((theme) => ({ story, theme })));
  return { jobs, missing };
}

const isBlocking = (v: AxeViolation) => v.impact === "serious" || v.impact === "critical";

export function verdict(
  results: readonly AuditResult[],
  missing: readonly string[],
): { pass: boolean; blocking: { story: string; theme: AxisTheme; v: AxeViolation }[]; errors: AuditResult[] } {
  const blocking = results.flatMap((r) =>
    r.violations.filter(isBlocking).map((v) => ({ story: r.story, theme: r.theme, v })),
  );
  const errors = results.filter((r) => r.error !== null);
  return { pass: blocking.length === 0 && errors.length === 0 && missing.length === 0, blocking, errors };
}

const IMPACT_SCORE: Record<string, number> = { critical: 4, serious: 3, moderate: 2, minor: 1 };

function cell(r: AuditResult | undefined): string {
  if (!r) return "—";
  if (r.error) return "not audited";
  if (r.violations.length === 0) return "0";
  const top = r.violations.reduce((a, v) =>
    (IMPACT_SCORE[v.impact ?? ""] ?? 0) > (IMPACT_SCORE[a.impact ?? ""] ?? 0) ? v : a,
  );
  return `${r.violations.length} (${top.impact ?? "—"} · ${top.id})`;
}

export function renderReport(
  results: readonly AuditResult[],
  missing: readonly string[],
  themes: readonly AxisTheme[],
  runAt: string,
): string {
  const v = verdict(results, missing);
  const stories = [...new Set(results.map((r) => r.story))];
  const lines: string[] = [];
  lines.push("# axe-core a11y audit\n");
  lines.push(`**Run:** ${runAt}`);
  lines.push(`**Stories audited:** ${stories.length} × ${themes.length} theme(s) (${themes.join(", ")})`);
  lines.push(`**Serious / critical violations:** ${v.blocking.length}`);
  lines.push(`**Could not audit:** ${v.errors.length + missing.length}\n`);
  lines.push("**Rule set:** wcag2a + wcag2aa + wcag21a + wcag21aa + best-practice");
  lines.push("**Render:** theme forced via the preview's theme global and checked on <html data-theme>; CSS motion frozen at rest\n");

  lines.push("## Totals by theme\n");
  lines.push("| Theme | Stories | Serious / critical | Violations | Nodes | color-contrast nodes | Not audited |");
  lines.push("|---|---|---|---|---|---|---|");
  for (const theme of themes) {
    const rs = results.filter((r) => r.theme === theme);
    const all = rs.flatMap((r) => r.violations);
    lines.push(
      `| ${theme} | ${rs.length} | ${all.filter(isBlocking).length} | ${all.length} | ` +
        `${all.reduce((n, x) => n + x.nodes, 0)} | ` +
        `${all.filter((x) => x.id === "color-contrast").reduce((n, x) => n + x.nodes, 0)} | ` +
        `${rs.filter((r) => r.error).length} |`,
    );
  }

  lines.push("\n## Per-story summary\n");
  lines.push(`| Story | ${themes.join(" | ")} |`);
  lines.push(`|---|${themes.map(() => "---").join("|")}|`);
  for (const story of stories) {
    const row = themes.map((t) => cell(results.find((r) => r.story === story && r.theme === t)));
    lines.push(`| \`${story}\` | ${row.join(" | ")} |`);
  }

  if (v.blocking.length > 0) {
    lines.push("\n## Serious + critical violations (blocking)\n");
    lines.push("| Story | Theme | Rule | Impact | Nodes | More |");
    lines.push("|---|---|---|---|---|---|");
    for (const { story, theme, v: x } of v.blocking) {
      lines.push(`| \`${story}\` | ${theme} | \`${x.id}\` | ${x.impact} | ${x.nodes} | [docs](${x.helpUrl}) |`);
    }
  }
  if (v.errors.length + missing.length > 0) {
    lines.push("\n## Could not audit (blocking)\n");
    lines.push("| Story | Theme | Why |");
    lines.push("|---|---|---|");
    for (const s of missing) lines.push(`| \`${s}\` | all | not in this Storybook build's index.json |`);
    for (const r of v.errors) lines.push(`| \`${r.story}\` | ${r.theme} | ${(r.error ?? "").replace(/\|/g, "\\|")} |`);
  }
  return lines.join("\n") + "\n";
}

/** One audit's ceiling. Two stories hang axe outright
 *  (research-artifactfeedbackreview--ready-to-select, research-stylewheel--ready
 *  in the 2026-09-23 sweep); without a ceiling they stall every worker. */
export const AUDIT_TIMEOUT_MS = 60_000;

/** Reject with a named reason if `work` has not settled within `ms`. */
export async function raceTimeout<T>(work: Promise<T>, ms: number): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const late = new Promise<never>((_, reject) => {
    timer = setTimeout(() => reject(new Error(`timed out after ${ms / 1000}s (the story or axe never settled)`)), ms);
  });
  work.catch(() => undefined); // a late failure after the timeout is not news
  try {
    return await Promise.race([work, late]);
  } finally {
    clearTimeout(timer);
  }
}

async function pool<T, R>(items: readonly T[], size: number, fn: (item: T) => Promise<R>): Promise<R[]> {
  const out = new Array<R>(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const i = next++;
      out[i] = await fn(items[i]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(size, items.length) }, worker));
  return out;
}

async function main() {
  const args = parseArgs(argv.slice(2));
  console.log("== a11y audit ==");
  console.log(`  storybook : ${args.storybook}`);
  console.log(`  themes    : ${args.themes.join(", ")}`);

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

  const indexUrl = `${args.storybook.replace(/\/+$/, "")}/index.json`;
  let index: ReturnType<typeof readIndex>;
  try {
    const res = await fetch(indexUrl);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    index = readIndex(await res.json());
  } catch (e) {
    console.error(`[x] could not read ${indexUrl} (${e instanceof Error ? e.message : e}). Is Storybook served there?`);
    exit(2);
  }
  const wanted = args.all ? [...index.ids] : [...STORIES, ...index.tagged];
  const { jobs, missing } = planAudit(wanted, index.ids, args.themes);
  console.log(`  stories   : ${jobs.length / args.themes.length} (${jobs.length} audits)`);
  for (const s of missing) console.log(`  ${s}  ✗ not in this build`);

  const browser = await chromium.launch({ headless: true });

  // FRESH CONTEXT per audit: reusing one page lets portaled content
  // (modals, toasts, dropdowns) from the previous story linger under the
  // next story's URL.
  const results = await pool(jobs, args.concurrency, async (job): Promise<AuditResult> => {
    const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: job.theme });
    const page = await ctx.newPage();
    const audit = async () => {
      await page.goto(storyUrl(args.storybook, job.story, job.theme), {
        waitUntil: "domcontentloaded",
        timeout: 15_000,
      });
      if ((await expectTheme(page, job.theme)) === "storybook-error") {
        throw new Error("Storybook showed its error or no-preview screen");
      }
      await freezeMotion(page);
      await page.waitForTimeout(1500); // let lazy content settle
      return new AxeBuilder({ page }).withTags(AXE_TAGS).disableRules(AXE_DISABLED_RULES).analyze();
    };
    try {
      const r = await raceTimeout(audit(), AUDIT_TIMEOUT_MS);
      const violations: AxeViolation[] = r.violations.map((v) => ({
        id: v.id,
        impact: (v.impact as Impact | null | undefined) ?? null,
        help: v.help,
        helpUrl: v.helpUrl,
        nodes: v.nodes.length,
      }));
      console.log(`  ${job.story} [${job.theme}]  ${violations.length === 0 ? "✓" : "⚠ " + violations.length}`);
      if (process.env.A11Y_AUDIT_VERBOSE) {
        for (const v of violations.filter(isBlocking)) console.log("       ", v.id, v.impact);
      }
      return { ...job, violations, error: null };
    } catch (e: unknown) {
      console.log(`  ${job.story} [${job.theme}]  ✗ not audited`);
      return { ...job, violations: [], error: e instanceof Error ? e.message.split("\n")[0] : String(e) };
    } finally {
      await ctx.close();
    }
  });

  await browser.close();

  const outPath = join(process.cwd(), args.out);
  mkdirSync(dirname(outPath), { recursive: true });
  writeFileSync(outPath, renderReport(results, missing, args.themes, new Date().toISOString()));
  const v = verdict(results, missing);
  console.log("");
  console.log(`  report  : ${outPath}`);
  for (const theme of args.themes) {
    const n = v.blocking.filter((b) => b.theme === theme).length;
    console.log(`  ${theme.padEnd(5)}   : ${n} serious/critical`);
  }
  console.log(`  not audited : ${v.errors.length + missing.length}`);
  console.log(`  verdict : ${v.pass ? "PASS" : "FAIL"}`);
  exit(v.pass ? 0 : 1);
}

if (argv[1] && import.meta.url === pathToFileURL(resolve(argv[1])).href) void main();
