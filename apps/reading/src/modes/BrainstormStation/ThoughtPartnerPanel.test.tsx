/**
 * Surface E thought-partner pane — /thought-partner + seed + Lego slotting.
 * Cite: master-spec §4.5.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DRAG_MIME } from "../CreationStudio/BlockPalette";
import ThoughtPartnerPanel, {
  THOUGHT_PARTNER_SEED_EVENT,
} from "./ThoughtPartnerPanel";

const apiFetch = vi.fn();
const composeContext = vi.fn();
const searchBlocks = vi.fn();

vi.mock("../../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  composeContext: (...args: unknown[]) => composeContext(...args),
  searchBlocks: (...args: unknown[]) => searchBlocks(...args),
}));

vi.mock("../../brand/werner/animated", () => ({
  WernerThinking: () => <span data-testid="thinking" />,
}));

vi.mock("../../components/ai/ContextPicker", () => ({
  default: ({ onContextChange }: { onContextChange: (s: string) => void }) => (
    <button type="button" onClick={() => onContextChange("ctx")}>
      mock-compose
    </button>
  ),
}));

vi.mock("../../components/ai/aiActions", () => ({
  workspaceContextPrompt: () => "workspace-ctx",
  parseAssistantReply: (raw: string) => ({ prose: raw, actions: [] }),
  dispatchAiAction: () => null,
}));

vi.mock("../../components/ai/thoughtPartnerSeed", async () => {
  const actual = await vi.importActual<
    typeof import("../../components/ai/thoughtPartnerSeed")
  >("../../components/ai/thoughtPartnerSeed");
  return {
    ...actual,
    composeThoughtPartnerSystemContext: (base: string | null) =>
      base ? `WRAP:${base}` : "WRAP:none",
  };
});

describe("ThoughtPartnerPanel (Surface E)", () => {
  beforeEach(() => {
    cleanup();
    apiFetch.mockReset();
    composeContext.mockReset();
    searchBlocks.mockReset();
    searchBlocks.mockResolvedValue({
      count: 1,
      hits: [
        {
          block_id: "insight-42",
          block_kind: "insight",
          label: "Photonic flywheel compounds",
          body: "…",
          source_tier: 2,
          document_title: "notes",
        },
      ],
    });
  });

  it("posts to /thought-partner and shows shape + text", async () => {
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        shape: "CHALLENGE",
        text: "What would falsify this at p<0.01?",
      }),
    });
    render(<ThoughtPartnerPanel />);
    fireEvent.change(screen.getByLabelText("Thought partner prompt"), {
      target: { value: "Challenge these notes" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => {
      expect(screen.getByTestId("thought-partner-reply").textContent).toContain(
        "CHALLENGE",
      );
    });
    expect(apiFetch).toHaveBeenCalled();
    expect(String(apiFetch.mock.calls[0][0])).toContain("/thought-partner");
    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.prompt).toBe("Challenge these notes");
  });

  it("seeds the composer from antiek:thought-partner:seed", async () => {
    render(<ThoughtPartnerPanel />);
    window.dispatchEvent(
      new CustomEvent(THOUGHT_PARTNER_SEED_EVENT, {
        detail: {
          prompt: "Discuss parked Q",
          source_label: "parked · q-1",
        },
      }),
    );
    await waitFor(() => {
      expect(screen.getByTestId("thought-partner-seed-label").textContent).toContain(
        "parked · q-1",
      );
    });
    const prompt = screen.getByTestId("thought-partner-panel").querySelector(
      "textarea",
    ) as HTMLTextAreaElement;
    expect(prompt.value).toBe("Discuss parked Q");
  });

  it("slots an insight Lego via shelf + and merges compose-context on send", async () => {
    composeContext.mockResolvedValue({
      system_context: "@insight[insight-42] Photonic flywheel compounds",
      withheld: [],
      missing: [],
    });
    apiFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ shape: "SYNTHESIS", text: "Compounding holds." }),
    });
    render(<ThoughtPartnerPanel />);
    await waitFor(() => {
      expect(screen.getByLabelText("Slot Photonic flywheel compounds")).toBeTruthy();
    });
    fireEvent.click(screen.getByLabelText("Slot Photonic flywheel compounds"));
    expect(screen.getByTestId("slotted-insight-chip").textContent).toContain(
      "Photonic flywheel",
    );

    fireEvent.change(screen.getByLabelText("Thought partner prompt"), {
      target: { value: "Challenge the slotted insight" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(composeContext).toHaveBeenCalledWith({
        items: [{ kind: "insight", id: "insight-42" }],
      });
    });
    await waitFor(() => {
      expect(apiFetch).toHaveBeenCalled();
    });
    const body = JSON.parse(apiFetch.mock.calls[0][1].body);
    expect(body.system_context).toContain("Photonic flywheel");
  });

  it("accepts PaletteDragPayload drops on the focus tray", async () => {
    render(<ThoughtPartnerPanel />);
    const tray = screen.getByTestId("thought-partner-focus-tray");
    const payload = {
      from: "palette",
      block_kind: "insight",
      block_id: "drop-9",
      label: "Dropped lego",
    };
    fireEvent.drop(tray, {
      dataTransfer: {
        getData: (mime: string) =>
          mime === DRAG_MIME ? JSON.stringify(payload) : "",
        types: [DRAG_MIME],
        dropEffect: "copy",
      },
    });
    await waitFor(() => {
      expect(screen.getByTestId("slotted-insight-chip").textContent).toContain(
        "Dropped lego",
      );
    });
  });
});
