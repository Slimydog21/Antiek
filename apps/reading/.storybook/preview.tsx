import type { Preview } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

// Pull in the Tailwind base styles so Storybook renders components
// with the same typography + spacing scale as the production app.
import "../src/index.css";
// Antiek brand tokens — sun-yellow outlining, day/night surface ramps.
// Loaded here so every story has --sun, --ink, --ice-2 etc. available.
import "../src/design/tokens.css";
// U-05 motion system — the reduced-motion catch-all so stories honour the
// OS reduce-motion setting exactly as the app does.
import "../src/design/motion.css";
import { applyTheme, type ThemePreference } from "../src/design/theme";
import { DARK_SHOT } from "./visual-axes";

/**
 * Global Storybook preview config. Wraps every story in a
 * MemoryRouter (several components use react-router hooks like
 * useNavigate / NavLink) and applies the global Tailwind CSS layer.
 *
 * Backgrounds expose the semantic grounds (page, card, inset, fixed ink)
 * so authors can preview a story on each; they follow the theme.
 *
 * SPR-08 fix — opt-out for stories that own their router. A story that
 * needs a SPECIFIC initial route (Topbar mounts the chrome at a
 * representative path so its breadcrumbs resolve) must supply its own
 * `<MemoryRouter initialEntries={[…]}>`. Nesting that inside this global
 * router throws react-router's "You cannot render a <Router> inside
 * another <Router>" — which silently renders the Storybook "No Preview"
 * error screen instead of the story. So a story sets
 * `parameters: { router: false }` to tell this decorator to step aside
 * and let the story bring its own router.
 */
const preview: Preview = {
  parameters: {
    actions: { argTypesRegex: "^on[A-Z].*" },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    // Grounds are the semantic tokens, so each follows the Theme toolbar
    // (a static day hex here used to put night stories on a day page).
    backgrounds: {
      default: "page",
      values: [
        { name: "page", value: "var(--bg-page)" },
        { name: "card", value: "var(--bg-card)" },
        { name: "inset", value: "var(--bg-inset)" },
        { name: "ink (fixed)", value: "var(--fixed-ink)" },
      ],
    },
    layout: "fullscreen",
    // The dark visual axis. Every story inherits one lost-pixel extra shot,
    // `<kind>--<story>--dark__[wN].png`, which lostpixel.config.ts renders with
    // globals=theme:dark, so night mode has baselines of its own.
    lostpixel: {
      extraShots: [{ name: DARK_SHOT.name, suffix: DARK_SHOT.suffix }],
    },
  },
  // Theme toolbar: System follows the OS (and Playwright's colorScheme), so
  // the a11y and visual runs get night mode through the same <html
  // data-theme> the app's boot script sets.
  globalTypes: {
    theme: {
      description: "Theme",
      defaultValue: "system",
      toolbar: {
        title: "Theme",
        icon: "mirror",
        items: [
          { value: "system", title: "System" },
          { value: "light", title: "Light" },
          { value: "dark", title: "Dark" },
        ],
        dynamicTitle: true,
      },
    },
  },
  decorators: [
    (Story, context) => {
      applyTheme((context.globals.theme as ThemePreference | undefined) ?? "system");
      return <Story />;
    },
    (Story, context) => {
      // A story that brings its own router opts out so the two don't nest.
      if (context.parameters?.router === false) return <Story />;
      return (
        <MemoryRouter>
          <Story />
        </MemoryRouter>
      );
    },
  ],
};

export default preview;
