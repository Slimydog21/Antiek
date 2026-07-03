import type { Meta, StoryObj } from "@storybook/react";

import { SceneStatusBadge } from "./SceneStatusBadge";
import type { KreaStatusSnapshot } from "../api/krea";

const REASONS = [
  "no_key",
  "kill_switch",
  "over_daily_budget",
  "rate_limited",
  "upstream_error",
  "upstream_timeout",
  "upstream_bad_response",
  "job_failed",
  "job_timeout",
  "job_cancelled",
  "no_api_balance",
];

function statusFor(reason: string | null): KreaStatusSnapshot {
  return {
    enabled: reason == null,
    key_present: reason !== "no_key",
    kill_switch: reason === "kill_switch",
    gate_verdict: reason && ["no_key", "kill_switch", "over_daily_budget", "rate_limited"].includes(reason)
      ? reason
      : null,
    reasons: REASONS,
    budget: { spent_today: 0, cap: 50, remaining: 50 },
    rate_window: { occupancy: 0, max: 6, window_s: 60 },
    cache: { entries: 0, max_entries: 256 },
    last_success_at: null,
    failure_counts: reason ? { [reason]: 1 } : {},
    failures: reason && !["no_key", "kill_switch", "over_daily_budget", "rate_limited"].includes(reason)
      ? [{ timestamp: "2026-07-02T00:00:00Z", reason, scene_key: "calm|day|summer", upstream_status: 500 }]
      : [],
  };
}

const meta = {
  title: "Scene / SceneStatusBadge",
  component: SceneStatusBadge,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof SceneStatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

const Stage = ({ reason }: { reason: string | null }) => (
  <div className="relative min-h-64 bg-shadow-1">
    <SceneStatusBadge status={statusFor(reason)} />
  </div>
);

export const Healthy: Story = {
  render: () => <Stage reason={null} />,
};

export const NoKey: Story = {
  render: () => <Stage reason="no_key" />,
};

export const EveryReason: Story = {
  render: () => (
    <div className="grid gap-3 bg-shadow-1 p-4">
      {REASONS.map((reason) => (
        <div key={reason} className="relative h-16 overflow-hidden rounded bg-space-2">
          <SceneStatusBadge status={statusFor(reason)} />
        </div>
      ))}
    </div>
  ),
};
