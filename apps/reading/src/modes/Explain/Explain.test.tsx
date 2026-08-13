import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
  postTypedEvent: vi.fn().mockResolvedValue({}),
  ApiError: class ApiError extends Error {
    status: number;
    body: string;
    constructor(message: string, status: number, body: string) {
      super(message);
      this.status = status;
      this.body = body;
    }
  },
}));

vi.mock("../../api/ownYourMind", () => ({
  explainClaim: vi.fn(),
  explainSynthesis: vi.fn(),
  explainDocument: vi.fn(),
}));

vi.mock("../../api/tiers", () => ({
  getTierOverrides: vi.fn(),
  createTierOverride: vi.fn(),
}));

import { explainClaim } from "../../api/ownYourMind";
import { createTierOverride, getTierOverrides } from "../../api/tiers";
import Explain from "./index";

const chunk = {
  chunk_id: "chunk-1",
  document_id: "doc-1",
  section_path: "§2.1 Methods",
  text: "The quick brown fox jumps over the lazy dog.",
  chunk_index: 0,
};

const doc = {
  document_id: "doc-1",
  title: "Provenance Paper",
  author: "Ada Lovelace",
  source_tier: 2,
  acquired_at: "2026-08-01T00:00:00Z",
};

const priorOverride = {
  chunk_id: "chunk-1",
  original_tier: 2,
  override_tier: 1,
  set_by: "operator",
  reason: "operator re-tiered after source verification",
  set_at: "2026-08-02T10:00:00Z",
};

const freshOverride = {
  chunk_id: "chunk-1",
  original_tier: 2,
  override_tier: 5,
  set_by: "__operator__",
  reason: "source vanished; demoted to weakest tier",
  set_at: "2026-08-03T09:00:00Z",
};

function claimData(overrides: unknown[]) {
  return {
    claim_node: {
      node_id: "claim-1",
      canonical_label: "Quantum claims coherence",
      node_type: "claim",
      graph_scope: "depth",
      created_at: "2026-08-01T00:00:00Z",
    },
    supporting_edges: [],
    chunks: [chunk],
    documents: [doc],
    chunk_tier_overrides: overrides,
    generated_at: "2026-08-03T09:00:00Z",
  };
}

function renderExplain() {
  return render(
    <MemoryRouter initialEntries={["/explain/claim/claim-1"]}>
      <Routes>
        <Route path="/explain/:kind/:id" element={<Explain />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Explain tier control (OYM P1 §5 write half)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(explainClaim).mockResolvedValue(claimData([]));
    vi.mocked(getTierOverrides).mockResolvedValue({
      chunk_id: "chunk-1",
      current_original_tier: 2,
      overrides: [priorOverride],
    });
    vi.mocked(createTierOverride).mockResolvedValue(freshOverride);
  });

  afterEach(cleanup);

  it("renders a set-tier control on the chunk row and lists its override history", async () => {
    renderExplain();

    const chunkRow = await screen.findByText("The quick brown fox jumps over the lazy dog.");
    expect(chunkRow).toBeTruthy();
    // The chunk's tier chip is present (the row the control attaches to).
    expect(screen.getByText("tier 2")).toBeTruthy();

    const button = screen.getByRole("button", { name: "set tier" });
    expect(button.getAttribute("aria-expanded")).toBe("false");
    await userEvent.setup().click(button);

    // Form revealed: tier select + reason input + save.
    expect(screen.getByRole("combobox", { name: "override tier" })).toBeTruthy();
    expect(
      screen.getByRole("textbox", { name: "reason for tier override" }),
    ).toBeTruthy();

    // Existing overrides for THIS chunk listed from GET with set_by/reason/date.
    await waitFor(() =>
      expect(getTierOverrides).toHaveBeenCalledWith("chunk-1"),
    );
    expect(screen.getByText(/operator re-tiered after source verification/)).toBeTruthy();
    expect(screen.getByText(/set by operator/)).toBeTruthy();
    expect(screen.getByText("Override history (1)")).toBeTruthy();
  });

  it("POSTs the override and refreshes the explain chain so the badge appears", async () => {
    const user = userEvent.setup();
    // Second explain load carries the freshly recorded override.
    vi.mocked(explainClaim)
      .mockResolvedValueOnce(claimData([]))
      .mockResolvedValueOnce(claimData([freshOverride]));
    vi.mocked(getTierOverrides).mockResolvedValue({
      chunk_id: "chunk-1",
      current_original_tier: 2,
      overrides: [freshOverride],
    });

    renderExplain();
    await screen.findByText("The quick brown fox jumps over the lazy dog.");
    await user.click(screen.getByRole("button", { name: "set tier" }));

    await user.selectOptions(
      screen.getByRole("combobox", { name: "override tier" }),
      "5",
    );
    await user.type(
      screen.getByRole("textbox", { name: "reason for tier override" }),
      "source vanished; demoted to weakest tier",
    );
    await user.click(screen.getByRole("button", { name: "save override" }));

    await waitFor(() =>
      expect(createTierOverride).toHaveBeenCalledWith(
        "chunk-1",
        5,
        "source vanished; demoted to weakest tier",
      ),
    );
    // The explain chain reloaded after the POST (existing reload path).
    await waitFor(() => expect(explainClaim).toHaveBeenCalledTimes(2));
    // The new override badge (tier 2 → 5, with reason) renders after reload.
    await waitFor(() =>
      expect(screen.getAllByText(/source vanished; demoted to weakest tier/).length).toBeGreaterThan(0),
    );
    expect(screen.getByText("tier 2 → 5")).toBeTruthy();
  });

  it("surfaces a POST failure inline and does not reload", async () => {
    const user = userEvent.setup();
    vi.mocked(createTierOverride).mockRejectedValue(
      new Error("POST /settings/tier-overrides failed: HTTP 400"),
    );

    renderExplain();
    await screen.findByText("The quick brown fox jumps over the lazy dog.");
    await user.click(screen.getByRole("button", { name: "set tier" }));
    await user.selectOptions(
      screen.getByRole("combobox", { name: "override tier" }),
      "4",
    );
    await user.type(
      screen.getByRole("textbox", { name: "reason for tier override" }),
      "follow-up verification",
    );
    await user.click(screen.getByRole("button", { name: "save override" }));

    await waitFor(() =>
      expect(screen.getByText(/POST \/settings\/tier-overrides failed: HTTP 400/)).toBeTruthy(),
    );
    // No reload on failure: the explain chain was fetched exactly once.
    expect(explainClaim).toHaveBeenCalledTimes(1);
  });
});
