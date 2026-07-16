import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import CrossGraphCitations from "./index";
import type { RecordedCitation } from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), "citation-attribution-switchyard.css"), "utf8");
const created: RecordedCitation = {
  reference_id: "ref-1", referencing_user_id: "operator", referencing_investigation_id: "inv-1",
  referenced_user_id: "author", referenced_note_id: "note-1", federated_substrate_id: null,
  cited_at: "2026-07-16T12:00:00Z",
};

afterEach(cleanup);
beforeEach(() => vi.mocked(apiFetch).mockReset());
const renderFixture = (props: React.ComponentProps<typeof CrossGraphCitations> = {}) => render(<MemoryRouter><CrossGraphCitations {...props} /></MemoryRouter>);
const fill = () => {
  fireEvent.change(screen.getByLabelText("Operator identity"), { target: { value: " operator " } });
  fireEvent.change(screen.getByLabelText("Investigation"), { target: { value: " inv-1 " } });
  fireEvent.change(screen.getByLabelText("Referenced contributor"), { target: { value: " author " } });
  fireEvent.change(screen.getByLabelText("Public note"), { target: { value: " note-1 " } });
};

describe("Citation attribution switchyard", () => {
  it("renders one landmark and an inert decorative environment", () => {
    renderFixture();
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const image = document.querySelector<HTMLImageElement>(".citation-switchyard__environment");
    expect(image?.alt).toBe(""); expect(image?.getAttribute("aria-hidden")).toBe("true"); expect(image?.draggable).toBe(false);
    expect(css).toMatch(/citation-switchyard__environment,[\s\S]*pointer-events:\s*none/);
  });

  it("preserves the exact same-substrate POST contract with trimmed values", async () => {
    vi.mocked(apiFetch).mockResolvedValue({ ok: true, json: async () => created } as Response);
    renderFixture(); fill(); fireEvent.click(screen.getByRole("button", { name: "Record reference" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledOnce());
    expect(apiFetch).toHaveBeenCalledWith("/cross-graph/citations", expect.objectContaining({ method: "POST" }));
    expect(JSON.parse(String(vi.mocked(apiFetch).mock.calls[0][1]?.body))).toEqual({
      referencing_user_id: "operator", referencing_investigation_id: "inv-1", referenced_user_id: "author", referenced_note_id: "note-1",
    });
  });

  it("adds the partner substrate key only for a federation reference", async () => {
    const recordCitation = vi.fn(async (draft) => ({ ...created, ...draft, federated_substrate_id: draft.federated_substrate_id ?? null }));
    renderFixture({ recordCitation }); fill();
    fireEvent.click(screen.getByRole("checkbox", { name: /Partner substrate reference/ }));
    fireEvent.change(screen.getByLabelText("Partner substrate identifier"), { target: { value: " coop-one " } });
    fireEvent.click(screen.getByRole("button", { name: "Record reference" }));
    await waitFor(() => expect(recordCitation).toHaveBeenCalledWith(expect.objectContaining({ federated_substrate_id: "coop-one" })));
  });

  it("hard-locks execution fixtures", () => {
    const recordCitation = vi.fn(); renderFixture({ recordCitation, executionEnabled: false, initialFederation: true });
    const button = screen.getByRole("button", { name: "Record reference" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true); fireEvent.click(button); expect(recordCitation).not.toHaveBeenCalled(); expect(apiFetch).not.toHaveBeenCalled();
  });

  it("redacts an upstream failure and announces a safe error", async () => {
    renderFixture({ recordCitation: async () => { throw new Error("private response and token"); } }); fill();
    fireEvent.click(screen.getByRole("button", { name: "Record reference" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Could not record the citation reference. No reference was added.");
    expect(document.body.textContent).not.toContain("private response"); expect(document.body.textContent).not.toContain("token");
  });

  it("adds a session receipt and clears only the cited-work fields", async () => {
    renderFixture({ recordCitation: async (draft) => ({ ...created, ...draft, federated_substrate_id: null }) }); fill();
    fireEvent.click(screen.getByRole("button", { name: "Record reference" }));
    expect(await screen.findByText("ref-1 · same substrate · 2026-07-16T12:00:00Z")).toBeTruthy();
    expect((screen.getByLabelText("Referenced contributor") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Public note") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Investigation") as HTMLInputElement).value.trim()).toBe("inv-1");
  });

  it("states the authority and session boundaries without payout promises", () => {
    renderFixture();
    expect(screen.getByText(/does not verify partner trust or consent and does not execute a payout/)).toBeTruthy();
    expect(screen.getByText(/Attribution and any revenue handling happen downstream under separate policy/)).toBeTruthy();
    expect(screen.getByText("Receipts shown here last for this session only.")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/routes 70%/i);
  });
});
