import AxeBuilder from "@axe-core/playwright";

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
 * audited story it runs axe-core (via @axe-core/playwright, the same
 * engine + the same rule set scripts/a11y_audit.ts uses) and FAILS the
 * test on any `serious` or `critical` violation. The two paths
 * (test-runner gate + the a11y_audit.ts report) use the same rule set
 * (tags + disabled rules), kept in sync BY HAND — change one, change both.
 *
 * Story selection: the CI step passes `--includeTags a11y-audit`, so the
 * runner only visits stories tagged `a11y-audit` (the shell chrome +
 * the Lemon primitives). The hook runs on whatever the runner visits;
 * the tag is the filter.
 */

/**
 * The shared axe rule set + disabled-rule list. Kept identical to
 * scripts/a11y_audit.ts so the CI gate and the local report agree.
 *
 * The disabled rules are all Storybook-iframe-wrapper noise, never
 * Antiek shell code:
 *   - scrollable-region-focusable / landmark-one-main / region /
 *     page-has-heading-one: a story body is an atomic isolation
 *     context, not a whole page with a <main> landmark.
 *   - empty-heading: Storybook's own hidden `<h1 id="error-message">`
 *     inside iframe.html — confirmed in SPR-08 to be Storybook chrome,
 *     not shell code (the shell stories render zero violations of any
 *     impact from Antiek elements).
 */
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"];
const AXE_DISABLED_RULES = [
  "scrollable-region-focusable",
  "landmark-one-main",
  "region",
  "page-has-heading-one",
  "empty-heading",
];

const BLOCKING_IMPACTS = new Set(["serious", "critical"]);

const config: TestRunnerConfig = {
  async postVisit(page) {
    // The runner navigates the page to the story before postVisit; run
    // axe against the live story DOM exactly as a11y_audit.ts does.
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
          `violation(s):\n${lines.join("\n")}`,
      );
    }
  },
};

export default config;
