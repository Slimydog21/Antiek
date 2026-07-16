import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import type { ReactNode } from "react";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Outcomes from "./index";
import type { OutcomeRow } from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: ReactNode }) => <>{children}</>,
}));

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "outcomes-verdict-chamber.css"),
  "utf8",
);
const emptyResponse = {
  ok: true,
  json: async () => ({ outcomes: [] }),
} as Response;
const empty = async (): Promise<OutcomeRow[]> => [];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

beforeEach(() => {
  vi.mocked(apiFetch).mockReset();
});

function renderFixture(props: React.ComponentProps<typeof Outcomes>) {
  return render(
    <MemoryRouter>
      <Outcomes {...props} />
    </MemoryRouter>,
  );
}

describe("Outcomes verdict chamber", () => {
  it("renders one landmark and a real inert decorative environment", async () => {
    renderFixture({ synthesisIdOverride: "syn_fixture", loadOutcomes: empty });
    expect(screen.getAllByRole("main")).toHaveLength(1);
    const environment = document.querySelector<HTMLImageElement>(
      ".outcomes-verdict-chamber__environment",
    );
    expect(environment?.alt).toBe("");
    expect(environment?.getAttribute("aria-hidden")).toBe("true");
    expect(environment?.draggable).toBe(false);
    expect(css).toMatch(
      /outcomes-verdict-chamber__environment,[\s\S]*pointer-events:\s*none/,
    );
  });

  it("gives all pending choices identical neutral structure and classes", async () => {
    renderFixture({ synthesisIdOverride: "syn_fixture", loadOutcomes: empty });
    const choices = document.querySelectorAll(
      ".outcomes-verdict-chamber__choice",
    );
    expect(choices).toHaveLength(3);
    expect(
      new Set(Array.from(choices, (choice) => choice.className)).size,
    ).toBe(1);
    const actions = [
      "Record validated",
      "Record falsified",
      "Record indeterminate",
    ].map((name) => screen.getByRole("button", { name }));
    expect(new Set(actions.map((action) => action.className)).size).toBe(1);
    expect(css).not.toMatch(
      /outcomes-verdict-chamber__choice[^}]*\b(?:red|green|emperor|aurora)/,
    );
  });

  it("hard-disables execution fixtures and emits no fetch on click", async () => {
    const recordOutcome = vi.fn(async () => undefined);
    renderFixture({
      synthesisIdOverride: "syn_fixture",
      loadOutcomes: empty,
      recordOutcome,
      executionEnabled: false,
    });
    const action = screen.getByRole("button", {
      name: "Record validated",
    }) as HTMLButtonElement;
    expect(action.disabled).toBe(true);
    fireEvent.click(action);
    expect(recordOutcome).not.toHaveBeenCalled();
    expect(apiFetch).not.toHaveBeenCalled();
  });

  it("preserves the production GET and POST request authority", async () => {
    vi.mocked(apiFetch)
      .mockResolvedValueOnce(emptyResponse)
      .mockResolvedValueOnce({ ok: true } as Response)
      .mockResolvedValueOnce(emptyResponse);
    render(
      <MemoryRouter initialEntries={["/outcomes/syn%20one"]}>
        <Routes>
          <Route path="/outcomes/:synthesisId" element={<Outcomes />} />
        </Routes>
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith("/outcomes/syn%20one"),
    );
    fireEvent.change(screen.getByLabelText("Outcome rationale"), {
      target: { value: "Bounded rationale" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record falsified" }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(3));
    const [, init] = vi.mocked(apiFetch).mock.calls[1];
    expect(apiFetch).toHaveBeenNthCalledWith(
      2,
      "/outcomes",
      expect.objectContaining({ method: "POST" }),
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      synthesis_id: "syn one",
      observer: "__operator__",
      thesis_outcomes: [],
      falsification_outcomes: [
        { kind: "falsified", note: "Bounded rationale" },
      ],
      execution_risk_outcomes: [],
      notes: "Bounded rationale",
    });
  });

  it("keeps failure and missing-identity states explicit and safe", async () => {
    const { rerender } = renderFixture({
      synthesisIdOverride: "syn_fixture",
      loadOutcomes: async () => {
        throw new Error("Outcome archive unavailable");
      },
    });
    expect((await screen.findByRole("alert")).textContent).toContain(
      "Outcome archive unavailable",
    );
    rerender(
      <MemoryRouter>
        <Outcomes synthesisIdOverride={null} loadOutcomes={empty} />
      </MemoryRouter>,
    );
    expect(
      await screen.findByText(
        "No synthesis is selected. Open this chamber from a synthesis outcome record.",
      ),
    ).toBeTruthy();
  });

  it("ignores a stale load after the active synthesis changes", async () => {
    const resolvers = new Map<string, (rows: OutcomeRow[]) => void>();
    const loadOutcomes = vi.fn(
      (id: string) =>
        new Promise<OutcomeRow[]>((resolve) => resolvers.set(id, resolve)),
    );
    const { rerender } = renderFixture({
      synthesisIdOverride: "syn_a",
      loadOutcomes,
    });
    rerender(
      <MemoryRouter>
        <Outcomes synthesisIdOverride="syn_b" loadOutcomes={loadOutcomes} />
      </MemoryRouter>,
    );
    const row = (id: string, note: string): OutcomeRow => ({
      outcome_id: id,
      observer: "__operator__",
      observed_at: "2026-07-16T12:00:00Z",
      thesis_outcomes: [{ kind: "validated", note }],
      falsification_outcomes: [],
      execution_risk_outcomes: [],
      notes: null,
    });
    resolvers.get("syn_b")?.([row("out_b", "Current synthesis")]);
    expect(
      await screen.findByText(
        (_, element) =>
          element?.tagName === "P" &&
          element.textContent?.includes("Current synthesis") === true,
      ),
    ).toBeTruthy();
    resolvers.get("syn_a")?.([row("out_a", "Stale synthesis")]);
    await Promise.resolve();
    expect(document.body.textContent).not.toContain("Stale synthesis");
    expect(document.body.textContent).toContain("Current synthesis");
  });

  it("declares narrow and reduced-motion containment without hiding content", () => {
    expect(css).toMatch(/@media \(max-width:\s*720px\)/);
    expect(css).toMatch(/grid-template-columns:\s*minmax\(0, 1fr\)/);
    expect(css).toMatch(/@media \(prefers-reduced-motion:\s*reduce\)/);
    expect(css).not.toMatch(/display:\s*none/);
  });
});
