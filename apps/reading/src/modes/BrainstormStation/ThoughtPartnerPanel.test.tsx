/**
 * Surface E thought-partner pane — real /thought-partner round-trip + seed.
 * Cite: master-spec §4.5; replaces Sprint-17 CTA placeholder.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ThoughtPartnerPanel, {
  THOUGHT_PARTNER_SEED_EVENT,
} from "./ThoughtPartnerPanel";

const apiFetch = vi.fn();

vi.mock("../../lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
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

describe("ThoughtPartnerPanel (Surface E)", () => {
  beforeEach(() => {
    cleanup();
    apiFetch.mockReset();
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
    expect(screen.getByTestId("thought-partner-reply").textContent).toContain(
      "falsify",
    );
    expect(apiFetch).toHaveBeenCalled();
    const [, init] = apiFetch.mock.calls[0];
    expect(String(apiFetch.mock.calls[0][0])).toContain("/thought-partner");
    const body = JSON.parse(init.body);
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
});
