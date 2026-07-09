import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Multimedia from "./index";
import {
  approveMultimediaDryRun,
  createMultimediaDraft,
  getMultimediaAsset,
  listMultimediaAssets,
  prepareMultimediaLiveExecution,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type { MultimediaAssetRecord } from "../../api/multimedia";

vi.mock("../../api/multimedia", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/multimedia")>();
  // Keep the real pure helpers (failedGateIds/manualGateIds derive from the
  // serialized `gates` array) and types; mock only the async fetch functions
  // so tests exercise the real derivation against a faithful hardening shape.
  return {
    ...actual,
    approveMultimediaDryRun: vi.fn(),
    createMultimediaDraft: vi.fn(),
    getMultimediaAsset: vi.fn(),
    listMultimediaAssets: vi.fn(),
    prepareMultimediaLiveExecution: vi.fn(),
    runMultimediaHardening: vi.fn(),
    steerMultimediaAsset: vi.fn(),
  };
});

const mockApprove = vi.mocked(approveMultimediaDryRun);
const mockCreate = vi.mocked(createMultimediaDraft);
const mockGet = vi.mocked(getMultimediaAsset);
const mockList = vi.mocked(listMultimediaAssets);
const mockPrepareLive = vi.mocked(prepareMultimediaLiveExecution);
const mockHarden = vi.mocked(runMultimediaHardening);
const mockSteer = vi.mocked(steerMultimediaAsset);

const draftRecord: MultimediaAssetRecord = {
  asset: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    status: "planned",
    kind: "documentary_video",
    title: "The aircraft program that made cheap long-haul travel possible",
    route_policy: "balanced",
    requested_duration_minutes: 30,
    manifest: {
      cost_rows: [{ cost_usd: 40.5 }],
    },
  },
  plan: {},
  mode: "video",
  style: "Asianometry-style explainer with restrained Ken Burns motion",
  hardening_report: null,
  latest_steering_intent: null,
  jobs: [],
};

const approvedRecord: MultimediaAssetRecord = {
  ...draftRecord,
  asset: {
    ...draftRecord.asset,
    status: "ready",
    manifest: {
      cost_rows: [{ cost_usd: 40.5 }],
    },
  },
};

const steeredRecord: MultimediaAssetRecord = {
  ...draftRecord,
  asset: {
    ...draftRecord.asset,
    revision_id: "rev-2",
    parent_revision_id: "rev-1",
    steering_event_id: "steer-1",
  },
  latest_steering_intent: { prompt: "go deeper" },
};

const hardenedRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  hardening_report: {
    asset_id: "mm-test-001",
    revision_id: "rev-1",
    ship_status: "manual_review",
    gates: [{ gate_id: "rights_and_publication", status: "manual", findings: [] }],
    residual_risks: [],
  },
};

const liveQueuedRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  jobs: [
    {
      job_id: "job-mm-1-0001",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 1,
      kind: "provider_execution",
      status: "queued",
      progress_percent: 0,
      message: "Live execution queued for krea with route balanced and max budget $60.00.",
      error_code: null,
      retryable: true,
    },
  ],
};

beforeEach(() => {
  mockList.mockResolvedValue({
    assets: [
      {
        asset_id: "mm-1",
        revision_id: "rev-1",
        title: draftRecord.asset.title,
        kind: "documentary_video",
        status: "planned",
        requested_duration_minutes: 30,
        route_policy: "balanced",
        estimated_cost_usd: 40.5,
        hardening_status: null,
        latest_job_status: null,
        latest_job_kind: null,
      },
    ],
    count: 1,
  });
  mockCreate.mockResolvedValue(draftRecord);
  mockGet.mockResolvedValue(draftRecord);
  mockApprove.mockResolvedValue(approvedRecord);
  mockSteer.mockResolvedValue(steeredRecord);
  mockHarden.mockResolvedValue(hardenedRecord);
  mockPrepareLive.mockResolvedValue(liveQueuedRecord);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

async function waitForApiReady() {
  await waitFor(() => expect(screen.getByRole("button", { name: "Review plan" }).getAttribute("disabled")).toBeNull());
}

async function reviewPlan() {
  render(<Multimedia />);
  await waitForApiReady();
  fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
  await screen.findByTestId("multimedia-suggestions");
}

describe("Multimedia workstation", () => {
  it("updates the estimated cost when the operator selects the cheapest route", async () => {
    render(<Multimedia />);
    await waitForApiReady();
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$40.50");

    fireEvent.click(screen.getByRole("button", { name: /Cheapest/ }));

    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$22.28");
    expect(screen.getByText(/Local placeholders first/)).toBeTruthy();
  });

  it("reviews a plan before render approval and then opens playback", async () => {
    await reviewPlan();

    expect(screen.getByTestId("multimedia-suggestions")).toBeTruthy();
    expect(screen.getByText(/Unsourced claim guard/)).toBeTruthy();
    expect(screen.queryByTestId("multimedia-player")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    expect(await screen.findByTestId("multimedia-player")).toBeTruthy();
    expect(mockApprove).toHaveBeenCalledWith("mm-1");
    expect(screen.getByRole("status").textContent).toContain("Partial render available");
  });

  it("surfaces provider unavailable and lets the operator downgrade safely", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: "Sim provider down" }));

    expect(screen.getByRole("status").textContent).toContain("Krea provider unavailable");

    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));

    expect(screen.getByRole("status").textContent).toContain("Partial render available");
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$22.28");
  });

  it("surfaces an over-budget state with the same downgrade path", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: "Sim over budget" }));

    expect(screen.getByRole("status").textContent).toContain("Over budget");
    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));
    expect(screen.getByRole("status").textContent).toContain("Partial render available");
  });

  it("highlights the current transcript segment and source card when a chapter is inspected", async () => {
    await reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");

    fireEvent.click(screen.getByRole("button", { name: /The engineering constraint stack/ }));

    const transcript = screen.getByTestId("multimedia-transcript");
    expect(within(transcript).getByText(/engines, wing structure, and fatigue testing/)).toBeTruthy();
    expect(screen.getByTestId("multimedia-source-detail").textContent).toContain(
      "engine and fatigue-testing sequence",
    );
  });

  it("lists and reopens persisted multimedia assets", async () => {
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /The aircraft program/ }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-1"));
    expect(await screen.findByText(/mm-1 \/ rev-1/)).toBeTruthy();
  });

  it("applies steering and runs hardening through the API client", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByRole("button", { name: "Apply steer" }));
    await waitFor(() => expect(mockSteer).toHaveBeenCalledWith("mm-1", expect.objectContaining({ prompt: expect.any(String) })));
    expect(await screen.findByText(/mm-1 \/ rev-2/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Run hardening" }));
    await waitFor(() => expect(mockHarden).toHaveBeenCalledWith("mm-1"));
    expect(await screen.findByText(/Hardening: manual_review/)).toBeTruthy();
    expect(screen.getByText(/rights_and_publication/)).toBeTruthy();
  });

  it("prepares live provider execution only after dry-run approval and spend acknowledgement", async () => {
    await reviewPlan();

    const prepare = screen.getByRole("button", { name: "Prepare live execution" });
    expect(prepare.getAttribute("disabled")).not.toBeNull();
    expect(screen.getByText(/Approve the dry-run package/i)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));
    await screen.findByTestId("multimedia-player");
    expect(prepare.getAttribute("disabled")).not.toBeNull();

    fireEvent.click(screen.getByLabelText(/I acknowledge this route may spend provider budget/i));
    await waitFor(() => expect(prepare.getAttribute("disabled")).toBeNull());
    fireEvent.click(prepare);

    await waitFor(() =>
      expect(mockPrepareLive).toHaveBeenCalledWith(
        "mm-1",
        expect.objectContaining({
          max_budget_usd: 60,
          route_policy: "balanced",
          operator_acknowledged_spend: true,
          provider_families: ["krea"],
          dry_run_revision_id: "rev-1",
        }),
      ),
    );
    expect(await screen.findByText(/Provider job: queued/)).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Provider calls are queued behind budget approval");
  });

  it("keeps the fixture preview visible when the API is unavailable", async () => {
    mockCreate.mockRejectedValueOnce(new Error("offline"));
    render(<Multimedia />);
    await waitForApiReady();

    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Could not create");
    expect(screen.getByTestId("multimedia-suggestions")).toBeTruthy();
  });
});
