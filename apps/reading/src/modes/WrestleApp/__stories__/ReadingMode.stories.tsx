// SPR-04 M6 — Storybook stories for the three reading-mode states.
//
// Stories are intentionally light: they mount WrestleApp inside a
// MemoryRouter so the route resolves, with the user-settings store
// pre-seeded to the relevant mode. The third story dispatches a
// Cmd+K keydown on mount so the AI palette appears open in the
// snapshot.
//
// Note: real PdfViewer needs PDF bytes; in Storybook (no backend)
// the EmptyState renders, which is the canonical "load a doc"
// snapshot for the design system.

import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";
import { MemoryRouter } from "react-router-dom";

import WrestleApp from "../index";
import {
  __resetUserSettingsForTests,
  __seedExistingUserPreSpr04ForTests,
  updateUserSettings,
} from "../../../settings/readingModeSettings";

function ResearcherHost() {
  useEffect(() => {
    __resetUserSettingsForTests();
    __seedExistingUserPreSpr04ForTests();
    // Force-load through the migration path so reading_mode = 'researcher'.
    updateUserSettings({ reading_mode: "researcher" });
  }, []);
  return (
    <MemoryRouter initialEntries={["/wrestle"]}>
      <WrestleApp />
    </MemoryRouter>
  );
}

function ReaderHost() {
  useEffect(() => {
    __resetUserSettingsForTests();
    // New-user default is 'reader'.
  }, []);
  return (
    <MemoryRouter initialEntries={["/wrestle"]}>
      <WrestleApp />
    </MemoryRouter>
  );
}

function CmdKHost() {
  useEffect(() => {
    __resetUserSettingsForTests();
    // Dispatch Cmd+K after the WrestleApp mounts so the listener is
    // attached before the synthetic event lands.
    const t = setTimeout(() => {
      window.dispatchEvent(
        new KeyboardEvent("keydown", { key: "k", metaKey: true, bubbles: true }),
      );
    }, 50);
    return () => clearTimeout(t);
  }, []);
  return (
    <MemoryRouter initialEntries={["/wrestle"]}>
      <WrestleApp />
    </MemoryRouter>
  );
}

const meta = {
  title: "WrestleApp / Reading mode",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

/** Three-column UI: PDF · Notes · CrossDoc rail. Existing-user default. */
export const ResearcherMode: Story = {
  name: "Researcher mode",
  render: () => <ResearcherHost />,
};

/** Single-pane PDF, side panels hidden. New-user default. */
export const ReaderMode: Story = {
  name: "Reader mode",
  render: () => <ReaderHost />,
};

/** Reader mode with the ⌘K AI palette open over it. */
export const CmdKOpen: Story = {
  name: "Cmd+K open",
  render: () => <CmdKHost />,
};
