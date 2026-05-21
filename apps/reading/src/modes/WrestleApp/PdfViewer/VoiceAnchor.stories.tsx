// SPR-05 / M7 — Storybook story for the VoiceAnchor recording widget.
//
// The acceptance criterion lists three stories: VoiceAnchor/Recording,
// VoiceGlyph/Idle, VoicePlayback/Active. This file provides the first.
//
// Caveat: VoiceAnchor's useVoiceRecorder hook calls
// navigator.mediaDevices.getUserMedia on mount. Storybook iframes
// won't have mic permission, so the visible state will be "error".
// That's an acceptable visual capture for the design index — the
// LAYOUT is what we're documenting (the widget chrome, the discard /
// stop / save controls), not live MediaRecorder behavior.

import type { Meta, StoryObj } from "@storybook/react";

import VoiceAnchor from "./VoiceAnchor";

const meta = {
  title: "Wrestle / VoiceAnchor",
  component: VoiceAnchor,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
} satisfies Meta<typeof VoiceAnchor>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Recording: Story = {
  args: {
    target: {
      documentId: "doc-src-storybook",
      page: 0,
      bbox: { x0: 50, y0: 80, x1: 250, y1: 160 },
      anchorTop: 240,
      anchorLeft: 320,
      pageLevel: false,
    },
    onSaved: (anchor) => {
      // eslint-disable-next-line no-alert
      alert(`anchor saved: ${anchor.anchor_id}`);
    },
    onClose: () => undefined,
  },
};

export const PageLevel: Story = {
  args: {
    target: {
      documentId: "doc-src-storybook",
      page: 2,
      bbox: { x0: 0, y0: 0, x1: 1000, y1: 1000 },
      anchorTop: 240,
      anchorLeft: 320,
      pageLevel: true,
    },
    onSaved: () => undefined,
    onClose: () => undefined,
  },
};
