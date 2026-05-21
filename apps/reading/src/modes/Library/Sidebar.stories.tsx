// SPR-06 / M6 — Storybook: Sidebar / Default
//
// Renders the library filter sidebar. Stories seed localStorage with
// a folder + tag before render so the chrome has something to show
// — otherwise the sidebar self-hides under the steelman threshold
// (rigor #2).

import { useEffect, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react";

import { Sidebar, type LibraryFilter } from "./Sidebar";
import { _resetFoldersForTests, createFolder } from "../../../api/library/folders";
import { _resetTagsForTests, getOrCreateTag } from "../../../api/library/tags";

const meta = {
  title: "Sidebar",
  component: Sidebar,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof Sidebar>;

export default meta;
type Story = StoryObj<typeof meta>;

function SidebarHarness({ documentCount }: { documentCount: number }) {
  const [filter, setFilter] = useState<LibraryFilter>({ kind: "all" });
  const [seeded, setSeeded] = useState(false);

  useEffect(() => {
    (async () => {
      _resetFoldersForTests();
      _resetTagsForTests();
      await createFolder("To Read");
      await createFolder("Investor decks");
      await getOrCreateTag("ml");
      await getOrCreateTag("strategy");
      setSeeded(true);
    })();
  }, []);

  if (!seeded) {
    return <p className="p-4 text-xs">Seeding stories…</p>;
  }

  return (
    <div style={{ display: "flex", height: 500 }}>
      <Sidebar
        active={filter}
        onFilterChange={setFilter}
        documentCount={documentCount}
      />
      <div className="flex-1 p-4 text-xs font-mono">
        Active filter: {JSON.stringify(filter)}
      </div>
    </div>
  );
}

export const Default: Story = {
  render: () => <SidebarHarness documentCount={12} />,
};

export const HiddenUnderThreshold: Story = {
  // Steelman: with no folders, no tags, and few docs, the sidebar
  // self-hides so the empty state can own the page.
  render: () => {
    _resetFoldersForTests();
    _resetTagsForTests();
    return (
      <div style={{ display: "flex", height: 200 }}>
        <Sidebar
          active={{ kind: "all" }}
          onFilterChange={() => undefined}
          documentCount={3}
        />
        <div className="flex-1 p-4 text-xs font-mono italic">
          Sidebar is intentionally hidden — too little content to
          justify the chrome (rigor #2 steelman).
        </div>
      </div>
    );
  },
};
