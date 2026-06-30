import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";

const masterViewerMock = vi.hoisted(() =>
  vi.fn((_props: unknown) => <div data-testid="master-viewer" />),
);

vi.mock("./MasterMdViewer", () => ({
  default: (props: unknown) => masterViewerMock(props),
}));
vi.mock("./DistillView", () => ({
  default: () => <div data-testid="distill-view" />,
}));
vi.mock("./SuggestedResearch", () => ({
  default: () => <div data-testid="suggested-research" />,
}));
vi.mock("./PasteIngest", () => ({
  default: () => <div data-testid="paste-ingest" />,
}));

import { CompletedInvestigationContent } from "./index";
import { writeReviewDuePolicy } from "./reviewDuePolicy";

const originalLocalStorage = window.localStorage;

function installLocalStorageStub() {
  const values = new Map<string, string>();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: {
      get length() {
        return values.size;
      },
      clear: vi.fn(() => values.clear()),
      getItem: vi.fn((key: string) => values.get(key) ?? null),
      key: vi.fn((index: number) => Array.from(values.keys())[index] ?? null),
      removeItem: vi.fn((key: string) => {
        values.delete(key);
      }),
      setItem: vi.fn((key: string, value: string) => {
        values.set(key, value);
      }),
    } as Storage,
  });
}

beforeEach(() => {
  installLocalStorageStub();
});

afterEach(() => {
  cleanup();
  masterViewerMock.mockClear();
  Object.defineProperty(window, "localStorage", {
    configurable: true,
    value: originalLocalStorage,
  });
});

function ev(
  id: string,
  actionType: string,
  payload: Record<string, unknown>,
  at: string,
  synthesisId: string | null = "syn-1",
): Event {
  return {
    event_id: id,
    investigation_id: "inv-review-policy",
    action_type: actionType as Event["action_type"],
    payload: payload as unknown as Event["payload"],
    param_version: "v1",
    emitted_at: at,
    synthesis_id: synthesisId,
  };
}

function completedInvestigation(): InvestigationState {
  return {
    id: "inv-review-policy",
    status: "completed",
    question: "What should be remembered?",
    streamStatus: "closed",
    reconnects: 0,
    terminalPayload: null,
    costTotal: 0,
    completedAt: "2026-06-30T10:05:00Z",
    events: [
      ev(
        "start",
        "investigation.start_requested",
        { question: "What should be remembered?" },
        "2026-06-30T10:00:00Z",
        null,
      ),
      ev(
        "syn",
        "synthesize.delivered",
        {
          thesis_summary: "Memory needs substrate truth.",
          thesis_components: [
            {
              claim: "Review cues should be operator controlled.",
              confidence: "high",
              effective_source_tier: 1,
              hedging_required: false,
              supporting_chunk_ids: ["chunk-1"],
              supporting_path_indices: [],
            },
          ],
          falsification_conditions: [],
          execution_risks: [],
          implicit_recommendation: "proceed",
        },
        "2026-06-30T10:01:00Z",
      ),
      ev(
        "review-old",
        "claim.reviewed",
        {
          action_type: "claim.reviewed",
          claim_id: "1",
          reviewed_at: "2026-06-29T10:00:00Z",
          next_due_at: "2026-06-30T09:00:00Z",
          due_label: "Due today",
        },
        "2026-06-29T10:00:01Z",
      ),
      ev(
        "done",
        "investigation.completed",
        { thesis_summary: "Memory needs substrate truth." },
        "2026-06-30T10:05:00Z",
        null,
      ),
    ],
  };
}

function lastMasterProps<T>(): T {
  const call = masterViewerMock.mock.calls.at(-1);
  expect(call).toBeDefined();
  return call![0] as T;
}

describe("CompletedInvestigationContent — review-due policy gate", () => {
  it("defaults review cues on and passes due claims plus the review handler", async () => {
    render(
      <CompletedInvestigationContent
        investigation={completedInvestigation()}
        onChaseQuestion={() => {}}
      />,
    );

    await waitFor(() => expect(masterViewerMock).toHaveBeenCalled());
    const props = lastMasterProps<{
      reviewDueEnabled: boolean;
      reviewDueClaims: Array<{ claimId: string; dueLabel: string }>;
      onReviewClaim?: unknown;
    }>();
    expect(props.reviewDueEnabled).toBe(true);
    expect(props.reviewDueClaims).toEqual([{ claimId: "1", dueLabel: "Due today" }]);
    expect(typeof props.onReviewClaim).toBe("function");
    expect(screen.getByRole("checkbox", { name: "Review cues" })).toBeTruthy();
  });

  it("turns policy off and removes both due claims and the review handler", async () => {
    render(
      <CompletedInvestigationContent
        investigation={completedInvestigation()}
        onChaseQuestion={() => {}}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Review cues" }));

    await waitFor(() => {
      const props = lastMasterProps<{
        reviewDueEnabled: boolean;
        reviewDueClaims: unknown[];
        onReviewClaim?: unknown;
      }>();
      expect(props.reviewDueEnabled).toBe(false);
      expect(props.reviewDueClaims).toEqual([]);
      expect(props.onReviewClaim).toBeUndefined();
    });
  });

  it("honors a persisted off policy on first render", async () => {
    writeReviewDuePolicy(false);

    render(
      <CompletedInvestigationContent
        investigation={completedInvestigation()}
        onChaseQuestion={() => {}}
      />,
    );

    await waitFor(() => {
      const props = lastMasterProps<{
        reviewDueEnabled: boolean;
        reviewDueClaims: unknown[];
        onReviewClaim?: unknown;
      }>();
      expect(props.reviewDueEnabled).toBe(false);
      expect(props.reviewDueClaims).toEqual([]);
      expect(props.onReviewClaim).toBeUndefined();
    });
  });
});
