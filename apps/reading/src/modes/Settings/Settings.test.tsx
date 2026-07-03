import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ProviderKeysState } from "../../hooks/useProviderKeys";

const { apiFetchMock, providerKeysRef, refreshMock } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  providerKeysRef: {
    current: {
      status: "ready",
      providers: ["deepseek", "anthropic"],
      refresh: vi.fn(),
    } as ProviderKeysState & { refresh: () => void },
  },
  refreshMock: vi.fn(),
}));

vi.mock("../../hooks/useProviderKeys", () => ({
  useProviderKeys: () => providerKeysRef.current,
}));

vi.mock("../../lib/api", () => ({
  apiFetch: apiFetchMock,
}));

vi.mock("../../workspace/useViewportTier", () => ({
  useViewportTier: () => "desktop",
}));

import Settings from "./index";

function roadmapResponse(
  read_activation: Record<string, unknown> | null | undefined = {
    source_path: "reports/read-dogfood.jsonl",
    state: "incomplete",
    total_sessions: 2,
    valid_sessions: 1,
    invalid_session_count: 1,
    live_provider_sessions: 0,
    citation_trace_sessions: 1,
    non_library_sessions: 0,
    final_verdict: null,
    closure_ready: false,
    required_counts: {
      valid_sessions: 10,
      live_provider_sessions: 5,
      citation_trace_sessions: 3,
      non_library_sessions: 1,
    },
    remaining_requirements: {
      valid_sessions: 9,
      live_provider_sessions: 5,
      citation_trace_sessions: 2,
      non_library_sessions: 1,
    },
    failures: ["session-1: minutes_reading must be at least 20"],
    next_session: {
      next_action: "collect_session",
      recommended_template: "live-citation",
      append_command: "antiek read activation append-template --kind live-citation",
      rationale: "A real live-citation session advances coverage.",
      remaining_requirements: {
        valid_sessions: 9,
        live_provider_sessions: 5,
        citation_trace_sessions: 2,
        non_library_sessions: 1,
      },
    },
  },
  adrb_dogfood: Record<string, unknown> | null | undefined = {
    state: "incomplete",
    closure_ready: false,
    dogfood_root: "runs/adrb",
    operator_log_path: "runs/adrb/operator-log.md",
    metrics_path: "runs/adrb/dogfood_metrics.md",
    verdict_path: "docs/adrb_post_dogfood_verdict.md",
    expected_project_count: 5,
    complete_project_entries: 2,
    reconciled_sessions: 1,
    valid_wave4_candidates: 0,
    metrics_current: false,
    mode_a_verdict: null,
    mode_b_verdict: "ITERATE",
    missing_requirements: [
      "expected 5 complete project entries, found 2",
      "dogfood_metrics.md is stale; regenerate dogfood-report",
    ],
    error: null,
  },
  branch_health: Record<string, unknown> | null | undefined = {
    state: "stale",
    branch: "reader/integration",
    head_sha: "abc1234",
    origin_main_sha: "def5678",
    merge_base_distance: 238,
    max_behind: 25,
    message: "base is 238 commits behind origin/main (limit N=25)",
    remediation: "run `git rebase origin/main`",
    error: null,
  },
) {
  return {
    ok: true,
    status: 200,
    json: async () => ({ read_activation, adrb_dogfood, branch_health }),
  } as Response;
}

describe("Settings", () => {
  beforeEach(() => {
    refreshMock.mockReset();
    apiFetchMock.mockReset();
    apiFetchMock.mockResolvedValue(roadmapResponse());
    providerKeysRef.current = {
      status: "ready",
      providers: ["deepseek", "anthropic"],
      refresh: refreshMock,
    };
    window.matchMedia = vi.fn((query: string) => ({
      matches: query.includes("prefers-color-scheme"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the live environment and registered provider readout", () => {
    render(<Settings />);

    expect(screen.getByText("Workspace environment")).toBeTruthy();
    expect(screen.getByText("Agentic activation")).toBeTruthy();
    expect(screen.getByText("deepseek")).toBeTruthy();
    expect(screen.getByText("anthropic")).toBeTruthy();
    expect(screen.getByText(/Provider keys make live Dialogue/i)).toBeTruthy();
    expect(screen.getByText(/specs\/activation\/golden-path\.md/i)).toBeTruthy();
    expect(screen.queryByText(/Settings surface stub/i)).toBeNull();
    expect(screen.getByText("/coordination/cost-consent")).toBeTruthy();
  });

  it("surfaces Read activation dogfood counters from the coordination roadmap", async () => {
    render(<Settings />);

    expect(await screen.findByText("Read dogfood evidence")).toBeTruthy();
    expect(screen.getByText("Read activation dogfood")).toBeTruthy();
    expect(
      screen.getByText(
        "1/10 required valid (2 total) · 0 live-provider · 1 citation-traced · 0 non-library · verdict=missing",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/Remaining: 9 valid, 5 live-provider, 2 citation-traced, 1 non-library/i),
    ).toBeTruthy();
    expect(screen.getByText(/reports\/read-dogfood\.jsonl/i)).toBeTruthy();
    expect(screen.getByText("1 invalid session need repair.")).toBeTruthy();
    expect(
      screen.getByText(
        "Next: live-citation · antiek read activation append-template --kind live-citation",
      ),
    ).toBeTruthy();
    expect(apiFetchMock).toHaveBeenCalledWith("/coordination/roadmap");
  });

  it("surfaces Research Bridge dogfood counters from the coordination roadmap", async () => {
    render(<Settings />);

    expect(await screen.findByText("Research Bridge dogfood")).toBeTruthy();
    expect(screen.getByText("Deep Research Bridge dogfood")).toBeTruthy();
    expect(
      screen.getByText(
        "2/5 projects · 1 reconciled · metrics=stale/missing · verdict A=missing B=ITERATE",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(
        /Remaining: expected 5 complete project entries, found 2; dogfood_metrics\.md is stale/i,
      ),
    ).toBeTruthy();
    expect(screen.getByText(/runs\/adrb/i)).toBeTruthy();
    expect(screen.getByText(/docs\/adrb_post_dogfood_verdict\.md/i)).toBeTruthy();
  });

  it("surfaces stale branch freshness from the coordination roadmap", async () => {
    render(<Settings />);

    expect(await screen.findByText("Branch freshness")).toBeTruthy();
    expect(screen.getByText("Merge-age gate")).toBeTruthy();
    expect(
      screen.getByText(
        "reader/integration · HEAD=abc1234 · origin/main=def5678 · behind=238/25",
      ),
    ).toBeTruthy();
    expect(
      screen.getByText(/base is 238 commits behind origin\/main/i),
    ).toBeTruthy();
    expect(screen.getByText("run `git rebase origin/main`")).toBeTruthy();
  });

  it("handles missing Read activation status without inventing evidence", async () => {
    apiFetchMock.mockResolvedValue(roadmapResponse(null));

    render(<Settings />);

    expect(await screen.findByText("unavailable")).toBeTruthy();
    expect(
      screen.getByText(/Coordination did not return Read activation evidence status/i),
    ).toBeTruthy();
  });

  it("handles missing Research Bridge dogfood status without inventing evidence", async () => {
    apiFetchMock.mockResolvedValue(roadmapResponse(undefined, null));

    render(<Settings />);

    expect(await screen.findByText("unavailable")).toBeTruthy();
    expect(
      screen.getByText(
        /Coordination did not return Research Bridge dogfood evidence status/i,
      ),
    ).toBeTruthy();
  });

  it("handles missing branch freshness without inventing evidence", async () => {
    apiFetchMock.mockResolvedValue(roadmapResponse(undefined, undefined, null));

    render(<Settings />);

    expect(await screen.findByText("Branch freshness")).toBeTruthy();
    expect(
      screen.getByText(/Coordination did not return branch freshness status/i),
    ).toBeTruthy();
  });

  it("reports roadmap fetch failures on the activation readout", async () => {
    apiFetchMock.mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    } as Response);

    render(<Settings />);

    await waitFor(() => {
      expect(
        screen.getAllByText("GET /coordination/roadmap failed: HTTP 503"),
      ).toHaveLength(3);
    });
  });

  it("links to trust and privacy controls with plain copy", () => {
    render(<Settings />);

    expect(screen.getByText("Published privacy, deletion, and training commitments")).toBeTruthy();
    expect(screen.getByText("Privacy budgets and deletion controls")).toBeTruthy();
    expect(screen.queryByText(/ε exposure/i)).toBeNull();
    expect(screen.queryByText(/DP budget/i)).toBeNull();
    expect(screen.queryByText(/Substrate-level/i)).toBeNull();
  });

  it("surfaces the no-provider state without pretending agentic work is available", () => {
    providerKeysRef.current = { status: "absent", refresh: refreshMock };

    render(<Settings />);

    expect(screen.getByText("not configured")).toBeTruthy();
    expect(
      screen.getByText(/No model providers are registered/i),
    ).toBeTruthy();
    expect(screen.getByText(/activation SPR-03/i)).toBeTruthy();
  });

  it("refreshes provider status through the shared health hook", () => {
    render(<Settings />);

    fireEvent.click(screen.getByRole("button", { name: /refresh provider status/i }));

    expect(refreshMock).toHaveBeenCalledTimes(1);
  });
});
