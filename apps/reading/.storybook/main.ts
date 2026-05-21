import type { StorybookConfig } from "@storybook/react-vite";

/**
 * Storybook config for Antiek reading UI.
 *
 * Sprint 17 INTEGRATE NOW item (master-spec §5.6 + PostHog Wedge 1a):
 * Storybook is the design-system source of truth for Antiek's UI in
 * lieu of a separate Figma library. Per master-spec §5.6, PostHog's
 * design and UI philosophy is Antiek's design philosophy; Storybook
 * is one of the load-bearing PostHog patterns we transfer.
 *
 * Visual regression on Storybook catches structural breakage during
 * the Sprint 18-19 notebook surface work (PostHog Wedge 2) and during
 * the Sprint 19-20 brainstorming-workstation Sprint 18 polish.
 */
const config: StorybookConfig = {
  stories: [
    "../src/**/*.stories.@(ts|tsx|mdx)",
  ],
  addons: [
    "@storybook/addon-links",
    "@storybook/addon-essentials",
  ],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  docs: {
    autodocs: "tag",
  },
  typescript: {
    check: false,
    reactDocgen: "react-docgen-typescript",
  },
};

export default config;
