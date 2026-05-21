import type { Meta, StoryObj } from "@storybook/react";

import LemonTable from "./LemonTable";
import LemonTag from "./LemonTag";

const meta = {
  title: "Lemon / Table",
  component: LemonTable,
  parameters: { layout: "padded" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

type Investigation = {
  id: string;
  title: string;
  status: "running" | "done" | "failed";
  documents: number;
  updated: string;
};

const rows: Investigation[] = [
  { id: "inv-001", title: "NVDA Q4 risk model", status: "running", documents: 36, updated: "12m ago" },
  { id: "inv-002", title: "Web gaming 2026 — Nilo vs Roblox", status: "done", documents: 84, updated: "3h ago" },
  { id: "inv-003", title: "Kalshi liquidity gate", status: "done", documents: 21, updated: "1d ago" },
  { id: "inv-004", title: "Antiek-RLM round-3 readiness", status: "failed", documents: 7, updated: "2d ago" },
];

export const InvestigationsList: Story = {
  render: () => (
    <div className="p-6 max-w-3xl">
      <LemonTable<Investigation>
        rows={rows}
        rowKey={(r) => r.id}
        onRowClick={(r) => alert(`Open ${r.id}`)}
        columns={[
          { key: "title", header: "Investigation", render: (r) => r.title, width: "50%" },
          {
            key: "status",
            header: "Status",
            render: (r) => (
              <LemonTag
                dot
                colour={
                  r.status === "done" ? "aurora" : r.status === "failed" ? "danger" : "sun"
                }
              >
                {r.status}
              </LemonTag>
            ),
            width: "20%",
          },
          {
            key: "documents",
            header: "Docs",
            render: (r) => r.documents,
            align: "right",
            width: "12%",
          },
          { key: "updated", header: "Updated", render: (r) => r.updated, align: "right" },
        ]}
      />
    </div>
  ),
};

export const Empty: Story = {
  render: () => (
    <div className="p-6 max-w-3xl">
      <LemonTable<Investigation>
        rows={[]}
        rowKey={(r) => r.id}
        columns={[
          { key: "title", header: "Investigation", render: (r) => r.title },
          { key: "status", header: "Status", render: (r) => r.status },
        ]}
        emptyState={
          <>No investigations yet. <span className="font-mono">⌘K</span> to start one.</>
        }
      />
    </div>
  ),
};
