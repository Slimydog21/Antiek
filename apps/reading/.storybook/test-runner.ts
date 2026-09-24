import AxeBuilder from "@axe-core/playwright";

import {
  AXE_DISABLED_RULES,
  AXE_TAGS,
  expectTheme,
  freezeMotion,
  type AxisTheme,
} from "./visual-axes.ts";

// NOTE: this file is NOT in tsconfig's `include` (it runs in the
// test-runner's own jest+babel context, not the app's tsc -b), and
// `@storybook/test-runner` is installed at CI time via npx — not a
// project dependency. So we deliberately do NOT import its types
// (that would be a phantom type dependency); we type the config shape
// structurally instead. @axe-core/playwright IS installed (a11y_audit.ts
// uses it), so we derive the page type from AxeBuilder's own constructor —
// which sidesteps the playwright / playwright-core dual-Page-type drift.
type AxePage = ConstructorParameters<typeof AxeBuilder>[0]["page"];
type TestRunnerConfig = {
  preVisit?: (page: AxePage) => Promise<void> | void;
  postVisit?: (page: AxePage) => Promise<void> | void;
};

/**
 * SPR-08 — wire axe-core into @storybook/test-runner.
 *
 * The honest bug fixed here is two-fold:
 *
 *  1. The CI step invoked `@storybook/test-runner` with a `--include`
 *     flag that the runner removed (it now selects stories via
 *     `--includeTags` / index-json, never `--include`). The job failed
 *     on every run.
 *
 *  2. EVEN WITH the flag fixed, the test-runner does not run axe-core on
 *     its own. `@storybook/addon-a11y` only surfaces violations in the
 *     Storybook UI panel at author time; it does NOT make the runner
 *     assert on them. The CI comment that claimed "runs axe via the
 *     addon-a11y test hook" was false for test-runner 0.24.x. The
 *     assertion has to be wired by a `postVisit` hook — this file.
 *
 * So this hook is the actual a11y gate: after the runner visits each
 * audited story it runs axe-core (via @axe-core/playwright, with the rule
 * set scripts/a11y_audit.ts also imports from ./visual-axes) and FAILS the
 * test on any `serious` or `critical` violation.
 *
 * Theme. One run audits one theme: `A11Y_THEME=dark` audits night, anything
 * else audits day. `preVisit` emulates that colour scheme before the story
 * renders; the preview's theme global defaults to "system", so the story
 * renders under <html data-theme> of that theme, and `postVisit` checks the
 * attribute before axe runs, so a night run that rendered day fails instead
 * of passing. CI runs the hook once per theme (visualtest.yml).
 *
 * Motion. `preVisit` zeroes CSS animation and transition durations (the
 * PostHog runner's rule), so axe never reads a colour mid-transition and
 * entrance animations are already at rest. Unlike reduced motion, this keeps
 * the full-motion design (GlassSurface keeps its glass).
 *
 * Story selection: the CI step passes `--includeTags a11y-audit`, so the
 * runner only visits stories tagged `a11y-audit` (the shell chrome +
 * the Lemon primitives). The hook runs on whatever the runner visits;
 * the tag is the filter.
 */
const THEME: AxisTheme = process.env.A11Y_THEME === "dark" ? "dark" : "light";

const BLOCKING_IMPACTS = new Set(["serious", "critical"]);

const config: TestRunnerConfig = {
  async preVisit(page) {
    await page.emulateMedia({ colorScheme: THEME });
    await freezeMotion(page);
  },
  async postVisit(page) {
    // The story has rendered by now, so the attribute is either there or
    // wrong; 5 s keeps this message inside jest's 15 s test timeout.
    await expectTheme(page, THEME, 5_000);
    // The runner renders the story before postVisit; run axe against the
    // live story DOM exactly as a11y_audit.ts does.
    const results = await new AxeBuilder({ page })
      .withTags(AXE_TAGS)
      .disableRules(AXE_DISABLED_RULES)
      .analyze();

    const blocking = results.violations.filter(
      (v) => v.impact != null && BLOCKING_IMPACTS.has(v.impact),
    );

    if (blocking.length > 0) {
      const lines = blocking.map(
        (v) =>
          `  [${v.impact}] ${v.id} (${v.nodes.length} node(s)) — ${v.help}\n` +
          `      ${v.helpUrl}`,
      );
      throw new Error(
        `axe-core found ${blocking.length} serious/critical a11y ` +
          `violation(s) in the ${THEME} theme:\n${lines.join("\n")}`,
      );
    }
  },
};

export default config;
