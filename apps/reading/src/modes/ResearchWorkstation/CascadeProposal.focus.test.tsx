/**
 * FFX SPR-04 M7 (F-17): the cascade's spend-limit input shows a focus
 * indicator. Same method as Library/CorpusSearch.focus.test.tsx: compile the
 * input's real classes with the project's Tailwind config, Tab to it, read
 * getComputedStyle.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import postcss from "postcss";
import tailwind from "tailwindcss";
import { afterEach, describe, expect, it, vi } from "vitest";

const { createPlanMock, getBudgetDefaultsMock, getSpendPreviewMock } = vi.hoisted(() => ({
  createPlanMock: vi.fn(),
  getBudgetDefaultsMock: vi.fn(),
  getSpendPreviewMock: vi.fn(),
}));

vi.mock("../../api/research", async (orig) => ({
  ...(await orig<typeof import("../../api/research")>()),
  createPlan: createPlanMock,
  getBudgetDefaults: getBudgetDefaultsMock,
  getSpendPreview: getSpendPreviewMock,
}));

import CascadeProposal from "./CascadeProposal";

const APP = join(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const rawConfig = createRequire(import.meta.url)(join(APP, "tailwind.config.js"));

async function injectTailwindFor(el: Element) {
  const result = await postcss([
    tailwind({
      ...(rawConfig.default ?? rawConfig),
      content: [{ raw: el.outerHTML, extension: "html" }],
      corePlugins: { preflight: false },
    }),
  ]).process("@tailwind utilities;", { from: undefined });
  const style = document.createElement("style");
  style.setAttribute("data-test-tailwind", "");
  style.textContent = result.css;
  document.head.appendChild(style);
}

function hasVisibleFocus(el: HTMLElement): boolean {
  const cs = getComputedStyle(el);
  const shadow = cs.boxShadow.trim();
  const shadowShown =
    shadow !== "" && shadow !== "none" && (!shadow.includes("var(") || cs.getPropertyValue("--tw-shadow").trim() !== "");
  const outlineShown = cs.outlineStyle !== "none" && cs.outline !== "" && !/transparent/.test(cs.outline);
  return shadowShown || outlineShown;
}

const leaf = (local_id: string, question: string) => ({
  local_id,
  question,
  rationale: "",
  focus_boundary: "",
  budget_usd: null,
  max_depth: null,
  graph_node_id: `q-${local_id}`,
  children: [],
});

afterEach(() => {
  cleanup();
  document.head.querySelectorAll("style[data-test-tailwind]").forEach((s) => s.remove());
});

describe("CascadeProposal focus (F-17)", () => {
  it("the aggregate stop-limit input shows a focus indicator after Tab reaches it", async () => {
    getBudgetDefaultsMock.mockResolvedValue({ per_research_cost_usd: 0.5, per_research_max_steps: 50 });
    getSpendPreviewMock.mockResolvedValue({
      spend_mode: "hard_ceiling",
      currency: "USD",
      amount_cents: 150,
      eligible: false,
      reasons: ["stop-limit only"],
      authority_digest: null,
      approval_revision: 1,
      assumptions: [],
    });
    createPlanMock.mockResolvedValue({
      root_node_id: "q-pn-root",
      tree: {
        root: { ...leaf("pn-root", "Root problem?"), children: [leaf("pn-1", "First?"), leaf("pn-2", "Second?")] },
        seed_kind: "problem",
        seed_provenance: {},
        approval: { state: "draft", approved_at: null, approved_by: null, plan_version: 1 },
        root_investigation_id: "__operator__",
      },
      capped_nodes: [],
      over_broad_leaves: [],
    });
    render(<CascadeProposal problem="Root problem?" onLaunched={vi.fn()} onFallBackToAsk={vi.fn()} />);

    const input = await screen.findByRole("spinbutton", { name: "Aggregate stop limit" });
    await injectTailwindFor(input);
    const user = userEvent.setup();
    for (let i = 0; i < 100 && document.activeElement !== input; i++) await user.tab();
    expect(document.activeElement).toBe(input);
    expect(hasVisibleFocus(input)).toBe(true);
  });
});
