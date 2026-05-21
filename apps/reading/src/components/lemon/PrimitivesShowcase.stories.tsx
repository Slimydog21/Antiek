import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import {
  LemonButton,
  LemonCard,
  LemonDropdown,
  LemonInput,
  LemonMenuItem,
  LemonModal,
  LemonSelect,
  LemonTable,
  LemonTag,
  LemonTextarea,
  LemonToastViewport,
  toast,
} from ".";

/**
 * S1 acceptance gate — one page that renders every Lemon primitive together
 * so the operator can sign off the visual system as coherent before any
 * mode is ported onto it (S5+).
 */
const meta = {
  title: "Design / Primitives Showcase",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

type Project = { id: string; name: string; status: "running" | "done"; weight: number };
const PROJECTS: Project[] = [
  { id: "nvda", name: "NVDA Q4 risk model", status: "running", weight: 0.72 },
  { id: "gaming", name: "Web gaming 2026", status: "done", weight: 0.91 },
  { id: "kalshi", name: "Kalshi liquidity gate", status: "done", weight: 0.64 },
];

export const Showcase: Story = {
  render: () => {
    const Inner = () => {
      const [modal, setModal] = useState(false);
      const [model, setModel] = useState<string>("nano-banana");
      const [query, setQuery] = useState("");
      const [draft, setDraft] = useState(
        "Hi Werner. Type Cmd+Enter to submit. The textarea auto-grows.",
      );
      return (
        <div className="min-h-screen bg-ice-2 dark:bg-space-2 text-ink dark:text-bright">
          <LemonToastViewport />

          {/* Header */}
          <header className="border-b-edge border-sun bg-ink dark:bg-void px-6 py-3 flex items-center justify-between">
            <div className="font-mono font-bold text-sun text-sm tracking-wider">
              ANTIEK / LEMON SHOWCASE
            </div>
            <div className="flex items-center gap-3">
              <LemonInput
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="search · ⌘K"
                kbdHint="⌘K"
                sizing="sm"
                wrapperClassName="w-72"
              />
              <LemonDropdown trigger={<LemonButton variant="tertiary">👤</LemonButton>} align="below-right">
                {({ close }) => (
                  <>
                    <LemonMenuItem onClick={close}>Profile</LemonMenuItem>
                    <LemonMenuItem onClick={close}>Settings</LemonMenuItem>
                    <div className="my-1 border-t border-rule dark:border-charcoal-1" />
                    <LemonMenuItem onClick={close}>Sign out</LemonMenuItem>
                  </>
                )}
              </LemonDropdown>
            </div>
          </header>

          <div className="p-8 space-y-8 max-w-6xl mx-auto">
            {/* Tags */}
            <LemonCard title="Tags · chips for state + filter">
              <div className="flex flex-wrap gap-2">
                <LemonTag>default</LemonTag>
                <LemonTag colour="sun">sun</LemonTag>
                <LemonTag colour="aurora">aurora</LemonTag>
                <LemonTag colour="danger">danger</LemonTag>
                <LemonTag colour="muted">muted</LemonTag>
                <LemonTag dot colour="sun">running</LemonTag>
                <LemonTag dot colour="aurora">done</LemonTag>
                <LemonTag dot colour="danger">failed</LemonTag>
                <LemonTag onRemove={() => toast.info("Tag removed")}>kalshi</LemonTag>
              </div>
            </LemonCard>

            {/* Buttons */}
            <LemonCard title="Buttons · 4 variants × 3 sizes">
              <div className="space-y-3">
                {(["primary", "secondary", "tertiary", "danger"] as const).map((v) => (
                  <div key={v} className="flex gap-3 items-end">
                    {(["sm", "md", "lg"] as const).map((s) => (
                      <LemonButton key={s} variant={v} size={s} onClick={() => toast.ok(`${v} · ${s}`)}>
                        {v} · {s}
                      </LemonButton>
                    ))}
                  </div>
                ))}
              </div>
            </LemonCard>

            {/* Input + textarea */}
            <div className="grid grid-cols-2 gap-6">
              <LemonCard title="Input">
                <div className="space-y-3">
                  <LemonInput placeholder="basic input" />
                  <LemonInput placeholder="with icon" iconLeft={<span>⌕</span>} />
                  <LemonInput placeholder="with kbd hint" kbdHint="⌘K" iconLeft={<span>⌕</span>} />
                </div>
              </LemonCard>
              <LemonCard title="Textarea · Cmd+Enter to submit">
                <LemonTextarea
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onSubmit={(v) => toast.ok(`Submitted ${v.length} chars`)}
                  placeholder="Ask anything…"
                />
              </LemonCard>
            </div>

            {/* Select + Modal trigger */}
            <div className="grid grid-cols-2 gap-6">
              <LemonCard title="Select · model picker">
                <LemonSelect<string>
                  value={model}
                  onChange={setModel}
                  fullWidth
                  options={[
                    { value: "flux-1-dev", label: "FLUX 1 dev" },
                    { value: "imagen-4", label: "Imagen 4" },
                    { value: "imagen-4-ultra", label: "Imagen 4 Ultra" },
                    { value: "nano-banana", label: "Nano Banana (Gemini)" },
                  ]}
                />
                <p className="mt-3 text-sm text-shadow-1 dark:text-moonlight">
                  Current pick: <span className="font-mono">{model}</span>
                </p>
              </LemonCard>
              <LemonCard title="Modal">
                <LemonButton variant="primary" onClick={() => setModal(true)}>
                  Open modal
                </LemonButton>
                <LemonModal
                  open={modal}
                  onClose={() => setModal(false)}
                  title="Confirm shutdown"
                  footer={
                    <div className="flex justify-end gap-2">
                      <LemonButton variant="tertiary" onClick={() => setModal(false)}>
                        Cancel
                      </LemonButton>
                      <LemonButton
                        variant="danger"
                        onClick={() => {
                          setModal(false);
                          toast.err("Shutdown cancelled — investigation still streaming.");
                        }}
                      >
                        Shut down
                      </LemonButton>
                    </div>
                  }
                >
                  <p className="text-sm">
                    The investigation is still streaming events. Shutting down
                    now will cancel the in-flight chain.
                  </p>
                </LemonModal>
              </LemonCard>
            </div>

            {/* Table */}
            <LemonCard title="Table · investigations">
              <LemonTable<Project>
                rows={PROJECTS}
                rowKey={(r) => r.id}
                onRowClick={(r) => toast.info(`Open ${r.name}`)}
                columns={[
                  { key: "name", header: "Investigation", render: (r) => r.name, width: "55%" },
                  {
                    key: "status",
                    header: "Status",
                    render: (r) => (
                      <LemonTag dot colour={r.status === "done" ? "aurora" : "sun"}>
                        {r.status}
                      </LemonTag>
                    ),
                    width: "20%",
                  },
                  {
                    key: "weight",
                    header: "Weight",
                    render: (r) => <span className="font-mono">{r.weight.toFixed(2)}</span>,
                    align: "right",
                  },
                ]}
              />
            </LemonCard>

            {/* Toast launchers */}
            <LemonCard title="Toasts">
              <div className="flex flex-wrap gap-3">
                <LemonButton variant="primary" onClick={() => toast.ok("Saved.")}>
                  ok
                </LemonButton>
                <LemonButton onClick={() => toast.warn("Heads up.")}>warn</LemonButton>
                <LemonButton variant="danger" onClick={() => toast.err("Something broke.")}>err</LemonButton>
                <LemonButton variant="tertiary" onClick={() => toast.info("FYI.")}>info</LemonButton>
              </div>
            </LemonCard>
          </div>
        </div>
      );
    };
    return <Inner />;
  },
};
