import type { Meta, StoryObj } from "@storybook/react";

import { AGENT_STATUSES } from "./agentStatus";
import { StatusDot } from "./StatusDot";

const meta = {
  title: "Workspace / Agents / StatusDot",
  component: StatusDot,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof StatusDot>;

export default meta;
type Story = StoryObj<typeof meta>;

/** Dots on paper: every state differs by shape, and the word is visible. */
export const DotsOnPaper: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-4 p-6">
      {AGENT_STATUSES.map((s) => (
        <StatusDot key={s} status={s} variant="dot" word="visible" />
      ))}
    </div>
  ),
};

/** Symbols on paper (herdr's × ◐ ✓ ○ ·). */
export const SymbolsOnPaper: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-4 p-6">
      {AGENT_STATUSES.map((s) => (
        <StatusDot key={s} status={s} variant="symbol" word="visible" />
      ))}
    </div>
  ),
};

/** On an island (fixed ink ground) the dot wears the --fixed-paper ring. */
export const DotsOnIsland: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-4 p-6 rounded bg-[var(--fixed-ink)] text-[var(--fixed-paper)]">
      {AGENT_STATUSES.map((s) => (
        <StatusDot key={s} status={s} variant="dot" ground="island" word="visible" />
      ))}
    </div>
  ),
};

/** The word hidden (sr-only) as the tab strip uses it; shape carries the state. */
export const WordHidden: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-4 p-6">
      {AGENT_STATUSES.map((s) => (
        <StatusDot key={s} status={s} variant="symbol" word="sr" reason={s === "idle" ? "stopped" : undefined} />
      ))}
    </div>
  ),
};
