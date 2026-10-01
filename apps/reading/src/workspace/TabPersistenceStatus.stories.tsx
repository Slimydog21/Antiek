import type { Meta, StoryObj } from "@storybook/react";
import { TabPersistenceStatusView } from "./TabPersistenceStatus";

const meta = {
  title: "Workspace/TabPersistenceStatus",
  component: TabPersistenceStatusView,
  args: { status: "saved", onRetryLoad: () => {}, onRetrySave: () => {} },
} satisfies Meta<typeof TabPersistenceStatusView>;
export default meta;
type Story = StoryObj<typeof meta>;
const day = { theme: "light" } as const;
const night = { theme: "dark" } as const;

export const SessionDay: Story = { args: { status: "session" }, globals: day };
export const SessionNight: Story = { args: { status: "session" }, globals: night };
export const PausedDay: Story = { args: { status: "paused" }, globals: day };
export const PausedNight: Story = { args: { status: "paused" }, globals: night };
export const UnavailableDay: Story = { args: { status: "unavailable" }, globals: day };
export const UnavailableNight: Story = { args: { status: "unavailable" }, globals: night };
export const LoadingDay: Story = { args: { status: "loading" }, globals: day };
export const LoadingNight: Story = { args: { status: "loading" }, globals: night };
export const UnsavedDay: Story = { args: { status: "unsaved" }, globals: day };
export const UnsavedNight: Story = { args: { status: "unsaved" }, globals: night };
export const SavingRetryDay: Story = { args: { status: "unsaved", saving: true }, globals: day };
export const SavingRetryNight: Story = { args: { status: "unsaved", saving: true }, globals: night };
export const PendingDay: Story = { args: { status: "pending" }, globals: day };
export const PendingNight: Story = { args: { status: "pending" }, globals: night };
export const SavedDay: Story = { args: { status: "saved" }, globals: day };
export const SavedNight: Story = { args: { status: "saved" }, globals: night };
