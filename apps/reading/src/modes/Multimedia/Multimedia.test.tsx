import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Multimedia from "./index";
import {
  approveMultimediaDryRun,
  createMultimediaDraft,
  getMultimediaAsset,
  listMultimediaJobs,
  listMultimediaAssets,
  prepareMultimediaLiveExecution,
  runMultimediaProviderWorker,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "../../api/multimedia";
import type { MultimediaAssetRecord } from "../../api/multimedia";

vi.mock("../../api/multimedia", () => ({
  approveMultimediaDryRun: vi.fn(),
  createMultimediaDraft: vi.fn(),
  getMultimediaAsset: vi.fn(),
  listMultimediaJobs: vi.fn(),
  listMultimediaAssets: vi.fn(),
  prepareMultimediaLiveExecution: vi.fn(),
  runMultimediaProviderWorker: vi.fn(),
  runMultimediaHardening: vi.fn(),
  steerMultimediaAsset: vi.fn(),
}));

const mockApprove = vi.mocked(approveMultimediaDryRun);
const mockCreate = vi.mocked(createMultimediaDraft);
const mockGet = vi.mocked(getMultimediaAsset);
const mockListJobs = vi.mocked(listMultimediaJobs);
const mockList = vi.mocked(listMultimediaAssets);
const mockPrepare = vi.mocked(prepareMultimediaLiveExecution);
const mockRunWorker = vi.mocked(runMultimediaProviderWorker);
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
    ship_status: "manual_review",
    failed_gate_ids: [],
    manual_gate_ids: ["rights_and_publication"],
  },
};

const queuedProviderRecord: MultimediaAssetRecord = {
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
      message: "Live execution queued for krea.",
      error_code: null,
      retryable: true,
    },
  ],
};

const completedProviderRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  jobs: [
    ...queuedProviderRecord.jobs,
    {
      job_id: "job-mm-1-0002",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 2,
      kind: "provider_execution",
      status: "running",
      progress_percent: 45,
      message: "Dry-run worker claimed job-mm-1-0001; no provider call has been made.",
      error_code: null,
      retryable: true,
    },
    {
      job_id: "job-mm-1-0003",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 3,
      kind: "provider_execution",
      status: "succeeded",
      progress_percent: 100,
      message: "Dry-run worker completed provider execution without Krea/TTS/video spend.",
      error_code: null,
      retryable: false,
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
  mockListJobs.mockResolvedValue({ jobs: queuedProviderRecord.jobs, count: 1 });
  mockApprove.mockResolvedValue(approvedRecord);
  mockPrepare.mockResolvedValue(queuedProviderRecord);
  mockRunWorker.mockResolvedValue(completedProviderRecord);
  mockSteer.mockResolvedValue(steeredRecord);
  mockHarden.mockResolvedValue(hardenedRecord);
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

  it("refreshes provider jobs and runs the dry-run worker", async () => {
    mockCreate.mockResolvedValueOnce(queuedProviderRecord);
    await reviewPlan();

    expect(await screen.findByTestId("multimedia-job-panel")).toBeTruthy();
    expect(screen.getByText(/Live execution queued for krea/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Run dry-run worker" }));

    await waitFor(() => expect(mockRunWorker).toHaveBeenCalledWith("mm-1", { dry_run: true }));
    expect(await screen.findByText(/without Krea\/TTS\/video spend/)).toBeTruthy();
  });

  it("queues live provider execution only through explicit budget controls", async () => {
    await reviewPlan();

    fireEvent.click(screen.getByLabelText("Spend acknowledged"));
    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Queue live job" }));

    await waitFor(() =>
      expect(mockPrepare).toHaveBeenCalledWith("mm-1", {
        max_budget_usd: 75,
        route_policy: "balanced",
        operator_acknowledged_spend: true,
        provider_families: ["krea"],
        dry_run_revision_id: "rev-1",
      }),
    );
    expect(await screen.findByText(/Live execution queued for krea/)).toBeTruthy();
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
