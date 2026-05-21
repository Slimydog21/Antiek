import type { Preview } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

// Pull in the Tailwind base styles so Storybook renders components
// with the same typography + spacing scale as the production app.
import "../src/index.css";
// Werner brand tokens — sun-yellow outlining, day/night surface ramps.
// Loaded here so every story has --sun, --ink, --ice-2 etc. available.
import "../src/design/tokens.css";

/**
 * Global Storybook preview config. Wraps every story in a
 * MemoryRouter (several components use react-router hooks like
 * useNavigate / NavLink) and applies the global Tailwind CSS layer.
 *
 * Backgrounds expose the Werner brand surface ramp so authors can
 * preview a story on a card, on the page, on a trough, or on the
 * deep ink. Default is `ice-2` (day page bg).
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
    backgrounds: {
      default: "ice-2",
      values: [
        { name: "ice-0", value: "#FFFFFF" },
        { name: "ice-1", value: "#FBFCFD" },
        { name: "ice-2", value: "#F4F7FA" },
        { name: "ice-3", value: "#EAEFF4" },
        { name: "ink", value: "#0F1419" },
        { name: "space-2 (night)", value: "#0D1019" },
        { name: "charcoal-2 (night card)", value: "#1B202A" },
      ],
    },
    layout: "fullscreen",
  },
  decorators: [
    (Story) => (
      <MemoryRouter>
        <Story />
      </MemoryRouter>
    ),
  ],
};

export default preview;
