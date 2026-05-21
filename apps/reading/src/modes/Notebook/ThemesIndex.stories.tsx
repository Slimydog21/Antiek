import type { Meta, StoryObj } from "@storybook/react";
import { MemoryRouter } from "react-router-dom";

import ThemesIndex from "./ThemesIndex";

/**
 * SPR-11 M7 — Storybook stories for the themes index page.
 *
 * Two states matter:
 *   - Default: a populated grid of theme cards (operator's mid-corpus
 *     state)
 *   - Empty: zero themes; copy explains "Promote blocks from any
 *     document to start a theme."
 *
 * Stories MUST mock the listThemes API via fetch interceptor; we
 * use a Storybook decorator + parameters to short-circuit. The
 * actual fetch is to /api/themes which 404s in Storybook (no
 * backend), so the index falls through to the "unimplemented"
 * banner — that's the rendered story.
 *
 * For the populated case we'd ideally MSW-mock; until MSW is
 * integrated into Storybook (a near-term operator task tracked in
 * the SPR-11 handoff), the Default story IS the unimplemented
 * banner state — the most-frequent dev-loop state today.
 */
const meta = {
  title: "Loop 2 / Theme Notebook / ThemesIndex",
  component: ThemesIndex,
  decorators: [
    (Story) => (
      <MemoryRouter initialEntries={["/wrestle/themes"]}>
        <Story />
      </MemoryRouter>
    ),
  ],
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ThemesIndex>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};
export const Empty: Story = {};
