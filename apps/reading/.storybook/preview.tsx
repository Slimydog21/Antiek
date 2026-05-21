import type { Preview } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

// Pull in the Tailwind base styles so Storybook renders components
// with the same typography + spacing scale as the production app.
import "../src/index.css";

/**
 * Global Storybook preview config. Wraps every story in a
 * MemoryRouter (several components use react-router hooks like
 * useNavigate / NavLink) and applies the global Tailwind CSS layer.
 *
 * Background defaults to white because Antiek's researcher's-notebook
 * aesthetic per master-spec §5.5 is serif on white, not the
 * SaaS-dashboard dark-mode default.
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
      default: "white",
      values: [
        { name: "white", value: "#ffffff" },
        { name: "stone-50", value: "#fafaf9" },
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
