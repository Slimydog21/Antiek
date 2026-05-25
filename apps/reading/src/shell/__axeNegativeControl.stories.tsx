import type { Meta, StoryObj } from "@storybook/react";

/**
 * Negative control for the axe a11y gate (SPR-08) — the gate's teeth, in-tree.
 *
 * Deliberately inaccessible: a button with no accessible name + an input with
 * no associated label — both `critical` axe violations. Tagged
 * `a11y-negative-control`, NOT `a11y-audit`, so the normal CI gate
 * (`--includeTags a11y-audit`) does NOT visit it and stays green.
 *
 * To PROVE the postVisit axe hook (.storybook/test-runner.ts) actually
 * asserts (i.e. is not a silent no-op), run on demand:
 *
 *   npm run build-storybook && \
 *   npx @storybook/test-runner@0.24.4 --index-json --includeTags a11y-negative-control
 *
 * It MUST fail with `button-name` + `label` critical violations. If it ever
 * passes, the gate has stopped asserting and the a11y CI is theater.
 */
const meta: Meta = {
  title: "Internal/Axe negative control",
  tags: ["a11y-negative-control"],
  parameters: { layout: "centered" },
};
export default meta;

export const DeliberatelyInaccessible: StoryObj = {
  render: () => (
    <div>
      {/* no accessible name → axe `button-name` (critical) */}
      <button type="button" />
      {/* no label → axe `label` (critical) */}
      <input type="text" />
    </div>
  ),
};
