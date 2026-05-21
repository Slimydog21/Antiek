import type { Meta, StoryObj } from "@storybook/react";
import { useEffect } from "react";

import CommandPalette, { rankEntries, type PaletteEntry } from "./CommandPalette";

/**
 * CommandPalette is the ⌘K/Ctrl+K palette mounted at the App root
 * (PostHog Wedge 3 — master-spec §5.6 + §4.5). It indexes routes,
 * investigations, documents, notebooks, and parked questions; the
 * operator types to fuzzy-search, arrow-keys to navigate, Enter to
 * dispatch.
 *
 * Stories use a tiny dispatcher that fires the keyboard shortcut on
 * mount so the palette renders open. Real interaction (typing, arrow
 * keys, Enter) works in the Storybook canvas without any extra wiring.
 *
 * Per master-spec §13.3 retrieval-time gates: the palette only sees
 * already-loaded substrate; cross-graph results are filtered server-
 * side before the palette ever indexes them.
 */
function AutoOpen() {
  useEffect(() => {
    const evt = new KeyboardEvent("keydown", {
      key: "k",
      metaKey: true,
      bubbles: true,
    });
    window.dispatchEvent(evt);
  }, []);
  return null;
}

function PaletteStoryHost() {
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
        Demo workstation backdrop
      </h1>
      <p style={{ color: "#57534e", fontSize: 14, marginBottom: 16 }}>
        Press ⌘K to open the palette. Arrow keys navigate; Enter selects;
        Esc closes.
      </p>
      <p style={{ color: "#78716c", fontSize: 12, fontFamily: "ui-monospace" }}>
        rankEntries() exposes the fuzzy-search algorithm; the unit
        tests below exercise it directly.
      </p>
      <AutoOpen />
      <CommandPalette />
    </div>
  );
}

const meta = {
  title: "PostHog Wedges / CommandPalette",
  component: PaletteStoryHost,
  parameters: {
    layout: "fullscreen",
  },
  tags: ["autodocs"],
} satisfies Meta<typeof PaletteStoryHost>;

export default meta;
type Story = StoryObj<typeof meta>;

/**
 * Default story — palette opens immediately on mount. The palette
 * fetches its substrate index from the API; in Storybook (no
 * backend) it gracefully degrades to showing the static ROUTE_INDEX
 * (Research, Wrestle, Sources, Create, Brainstorm, Privacy, Pricing,
 * Operator, Trust, Loop 3, Skill rules, Interviews).
 */
export const PaletteOpen: Story = {};

/**
 * Static example of the ranking algorithm — exercised in unit tests
 * but useful as visible documentation here.
 */
export const RankingExample: Story = {
  name: "Ranking algorithm preview",
  render: () => {
    const sample: PaletteEntry[] = [
      {
        kind: "route",
        id: "route:trust",
        title: "Trust Center",
        subtitle: "ε budgets · deletion SLA · unlock status",
        path: "/trust",
      },
      {
        kind: "route",
        id: "route:loop3",
        title: "Loop 3 checklist",
        subtitle: "RL unlock criteria + env gate",
        path: "/loop-3",
      },
      {
        kind: "route",
        id: "route:skill-rules",
        title: "Skill rules",
        subtitle: "Cross-user promoted rules",
        path: "/skill-rules",
      },
    ];
    const ranked = rankEntries(sample, "trust");
    return (
      <div style={{ padding: 32, fontFamily: "ui-serif, Georgia, serif" }}>
        <h2 style={{ marginBottom: 12 }}>Query: <code>"trust"</code></h2>
        <ol>
          {ranked.map((r) => (
            <li
              key={r.id}
              style={{
                padding: 8,
                borderBottom: "1px solid #e7e5e4",
                fontSize: 14,
              }}
            >
              <strong>{r.title}</strong>
              <span style={{ color: "#78716c", marginLeft: 8 }}>
                — {r.subtitle}
              </span>
            </li>
          ))}
        </ol>
      </div>
    );
  },
};
