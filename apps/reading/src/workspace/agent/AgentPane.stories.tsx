import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";
import { MemoryRouter } from "react-router-dom";

import { useCompanion } from "../companionStore";
import { AgentPane } from "./AgentPane";
import { useAgentThreads } from "./agentThreadStore";
import type { AgentTransport } from "./agentTransport";
import type { AgentPaneTab } from "./agentTypes";

/**
 * The agent second pane (SPR-07) at the inset's 320 px, day and night: the
 * Phase A host that proves the Surface mounts anywhere (no registry entry
 * mounts it until F1 lands). The transport is scripted, so the story is a
 * deterministic still for the pixel gate; the status row shows the
 * "simulated stream" label the whole-reply transport carries.
 */
const TAB: AgentPaneTab = { id: "agent:thread:story-pane", title: "project agent", scope: "project", projectId: "finches", agentId: "p:finches" };

const scripted: AgentTransport = {
  kind: "whole",
  send: async () => ({ text: "Read the drought chapter next; the 1977 cohort is where the beak-depth claim is tested.", shape: "SYNTHESIS" }),
};

function StoryPane({ width, seeded }: { width: number; seeded: boolean }) {
  useState(() => {
    useCompanion.getState().reset();
    useCompanion.getState().openAgentTab({ kind: "research-thread", investigationId: "story-pane", title: TAB.title });
    useAgentThreads.getState().reset();
    if (seeded) {
      const id = useAgentThreads.getState().startTurn(TAB.id, "What should I read next in this project?");
      useAgentThreads.getState().completeTurn(TAB.id, id, { answer: "Read the drought chapter next; the 1977 cohort is where the beak-depth claim is tested.", shape: "SYNTHESIS", actions: [] });
    }
    return null;
  });
  return (
    <MemoryRouter>
      <div className="p-4" style={{ background: "var(--bg-page)" }}>
        <div data-pane="left" tabIndex={-1} className="sr-only" />
        <div
          data-pane="right"
          className="flex h-[480px] flex-col overflow-hidden rounded-lg border border-hairline bg-ice-1 dark:bg-charcoal-1"
          style={{ width }}
        >
          <AgentPane tab={TAB} transport={scripted} />
        </div>
      </div>
    </MemoryRouter>
  );
}

const meta = {
  title: "Workspace/AgentPane",
  component: StoryPane,
  args: { width: 320, seeded: true },
} satisfies Meta<typeof StoryPane>;
export default meta;

type Story = StoryObj<typeof meta>;

const day = { theme: "light" } as const;
const night = { theme: "dark" } as const;

export const EmptyDay: Story = { args: { seeded: false }, globals: day };
export const EmptyNight: Story = { args: { seeded: false }, globals: night };
export const AnsweredDay: Story = { args: { seeded: true }, globals: day };
export const AnsweredNight: Story = { args: { seeded: true }, globals: night };
