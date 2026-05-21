import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import AISidecar from "./AISidecar";

/**
 * AISidecar is the right-rail surface mounted at the App root
 * (PostHog Wedge 4 — master-spec §5.6 + §4.6). Always present;
 * collapses to 32px when not in use, expands to 320px on demand.
 * Surfaces free-tier usage, recent dispatch decisions, and a one-
 * shot thought-partner input.
 *
 * Stories auto-fire ⌘J on mount so the sidecar opens. Backend
 * fetches (/billing/summary, /trajectory, /thought-partner) degrade
 * silently in Storybook to last-loaded / empty state — the sidecar
 * is non-blocking by design.
 */
function AutoOpen() {
  useEffect(() => {
    const evt = new KeyboardEvent("keydown", {
      key: "j",
      metaKey: true,
      bubbles: true,
    });
    window.dispatchEvent(evt);
  }, []);
  return null;
}

function SidecarStoryHost() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "#fafaf9",
        padding: "32px",
        fontFamily: "ui-serif, Georgia, serif",
      }}
    >
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>
        Workstation backdrop
      </h1>
      <p style={{ color: "#57534e", fontSize: 14, marginBottom: 4 }}>
        The AI sidecar attaches to the right edge. Press ⌘J to toggle.
      </p>
      <p style={{ color: "#78716c", fontSize: 12, fontFamily: "ui-monospace" }}>
        Per master-spec §13.3: the sidecar never displays cross-user
        content — everything shown sources from the calling user's
        own session.
      </p>
      <AutoOpen />
      <AISidecar />
    </div>
  );
}

const meta = {
  title: "PostHog Wedges / AISidecar",
  component: SidecarStoryHost,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof SidecarStoryHost>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default story — sidecar opens automatically. Backend fetches fail
 * silently in Storybook; the sidecar renders its empty state
 * (zero free-tier usage, no recent dispatch calls).
 */
export const SidecarOpen: Story = {};

/**
 * Collapsed state — the sidecar starts closed if the user dismisses
 * it. Toggle by clicking the chevron or pressing ⌘J.
 */
export const SidecarCollapsed: Story = {
  render: () => (
    <div
      style={{
        minHeight: "100vh",
        background: "#fafaf9",
        padding: "32px",
        fontFamily: "ui-serif, Georgia, serif",
      }}
    >
      <h1 style={{ fontSize: 28, marginBottom: 8 }}>
        Workstation backdrop (sidecar collapsed)
      </h1>
      <p style={{ color: "#57534e", fontSize: 14, marginBottom: 4 }}>
        The 32px rail on the right is the collapsed sidecar. Click
        the chevron or press ⌘J to expand.
      </p>
      <AISidecar />
    </div>
  ),
};
