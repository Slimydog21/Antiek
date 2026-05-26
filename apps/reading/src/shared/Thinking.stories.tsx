import type { Meta, StoryObj } from "@storybook/react";

import Thinking from "./Thinking";

/**
 * Thinking (U-04) — the shared "the AI is working" beat across the four doors.
 *
 * Stories cover the bare beat and the beat with a plain-language status line.
 * The status is always a human sentence ("reading sources…", "drafting…"),
 * never a raw phase/substrate name — those translate via the M4 glossary
 * before reaching this surface. Motion + reduced-motion safety inherit from
 * Werner (U-02); this story exists to pin the shared register, not the motion.
 *
 * Werner skin (Lemon tokens) — no hardcoded colors.
 */
const meta = {
  title: "Shared / Thinking (U-04)",
  component: Thinking,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta<typeof Thinking>;

export default meta;
type Story = StoryObj<typeof meta>;

/** The bare beat — no status line, just the shared "AI is working" signal. */
export const Bare: Story = {};

/** With a plain-language status — what Research shows while a run streams. */
export const WithStatus: Story = {
  args: { status: "reading sources…" },
};

/** What Write would show while a draft is generating — same beat, different words. */
export const Drafting: Story = {
  args: { status: "drafting…" },
};
