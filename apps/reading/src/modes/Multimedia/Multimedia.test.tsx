import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import Multimedia from "./index";
import {
  attachMultimediaProviderArtifact,
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
  attachMultimediaProviderArtifact: vi.fn(),
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

const mockAttachArtifact = vi.mocked(attachMultimediaProviderArtifact);
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
      execution_mode: "live_requested",
      provider_family: "krea",
      artifact_uri: null,
      artifact_checksum: null,
      artifact_media_type: null,
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
      execution_mode: "dry_run",
      provider_family: "krea",
      artifact_uri: null,
      artifact_checksum: null,
      artifact_media_type: null,
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
      execution_mode: "dry_run",
      provider_family: "krea",
      artifact_uri: null,
      artifact_checksum: null,
      artifact_media_type: null,
      progress_percent: 100,
      message: "Dry-run worker completed provider execution without Krea/TTS/video spend.",
      error_code: null,
      retryable: false,
    },
  ],
};

const artifactProviderRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  jobs: [
    ...queuedProviderRecord.jobs,
    {
      job_id: "job-mm-1-0004",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 4,
      kind: "provider_execution",
      status: "succeeded",
      execution_mode: "live",
      provider_family: "krea",
      artifact_uri: "https://cdn.example.test/mm-1.mp4",
      artifact_checksum: "sha256:abcdef123456",
      artifact_media_type: "video/mp4",
      progress_percent: 100,
      message: "Provider artifact attached for job-mm-1-0001.",
      error_code: null,
      retryable: false,
    },
  ],
};

const rejectedArtifactRecord: MultimediaAssetRecord = {
  ...approvedRecord,
  jobs: [
    ...queuedProviderRecord.jobs,
    {
      job_id: "job-mm-1-0005",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 5,
      kind: "provider_execution",
      status: "failed",
      execution_mode: "live",
      provider_family: "krea",
      artifact_uri: null,
      artifact_checksum: null,
      artifact_media_type: null,
      progress_percent: 0,
      message: "Provider artifact validation failed: artifact_uri must be an http(s) URL with a host.",
      error_code: "artifact_validation_failed",
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
        provider_readiness: {
          status: "manual_attach_ready",
          label: "Manual attach ready",
          source_job_id: "job-mm-1-0004",
          execution_mode: null,
          provider_family: null,
          error_code: null,
          message: null,
          artifact_uri: null,
          artifact_checksum: null,
          artifact_media_type: null,
        },
      },
      {
        asset_id: "mm-2",
        revision_id: "rev-1",
        title: "Attached artifact documentary",
        kind: "documentary_video",
        status: "ready",
        requested_duration_minutes: 20,
        route_policy: "balanced",
        estimated_cost_usd: 12,
        hardening_status: null,
        latest_job_status: "succeeded",
        latest_job_kind: "provider_execution",
        provider_readiness: {
          status: "artifact_attached",
          label: "Artifact attached",
          source_job_id: "job-mm-2-0004",
          execution_mode: "live",
          provider_family: "krea",
          error_code: null,
          message: null,
          artifact_uri: "https://cdn.example.test/mm-2.mp4",
          artifact_checksum: "sha256:2222abcd",
          artifact_media_type: "video/mp4",
        },
      },
      {
        asset_id: "mm-3",
        revision_id: "rev-1",
        title: "Rejected artifact documentary",
        kind: "documentary_video",
        status: "ready",
        requested_duration_minutes: 20,
        route_policy: "balanced",
        estimated_cost_usd: 12,
        hardening_status: null,
        latest_job_status: "failed",
        latest_job_kind: "provider_execution",
        provider_readiness: {
          status: "artifact_rejected",
          label: "Artifact rejected",
          source_job_id: "job-mm-3-0005",
          execution_mode: "live",
          provider_family: "krea",
          error_code: "artifact_validation_failed",
          message: "Provider artifact validation failed: artifact_uri must be an http(s) URL with a host.",
          artifact_uri: null,
          artifact_checksum: null,
          artifact_media_type: null,
        },
      },
    ],
    count: 3,
  });
  mockCreate.mockResolvedValue(draftRecord);
  mockGet.mockResolvedValue(draftRecord);
  mockListJobs.mockResolvedValue({ jobs: queuedProviderRecord.jobs, count: 1 });
  mockApprove.mockResolvedValue(approvedRecord);
  mockPrepare.mockResolvedValue(queuedProviderRecord);
  mockRunWorker.mockResolvedValue(completedProviderRecord);
  mockAttachArtifact.mockResolvedValue(artifactProviderRecord);
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
    expect(screen.getByText("Manual attach ready")).toBeTruthy();
    expect(screen.getAllByText("job-mm-1-0004").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: /The aircraft program/ }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-1"));
    expect(await screen.findByText(/mm-1 \/ rev-1/)).toBeTruthy();
  });

  it("filters persisted assets by provider readiness", async () => {
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    const persistedAssets = screen.getByTestId("multimedia-persisted-assets");
    expect(within(persistedAssets).getByText("Attached artifact documentary")).toBeTruthy();
    expect(within(persistedAssets).getByText("Rejected artifact documentary")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Manual attach 1" }));

    expect(within(persistedAssets).getByText(/The aircraft program/)).toBeTruthy();
    expect(within(persistedAssets).queryByText("Attached artifact documentary")).toBeNull();
    expect(within(persistedAssets).queryByText("Rejected artifact documentary")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Rejected 1" }));

    expect(within(persistedAssets).queryByText(/The aircraft program/)).toBeNull();
    expect(within(persistedAssets).queryByText("Attached artifact documentary")).toBeNull();
    expect(within(persistedAssets).getByText("Rejected artifact documentary")).toBeTruthy();
  });

  it("prefills manual artifact attachment from a manual-ready asset row", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Manual attach 1" }));
    const persistedAssets = screen.getByTestId("multimedia-persisted-assets");
    expect(within(persistedAssets).getByText("Queued live request")).toBeTruthy();
    expect(within(persistedAssets).getByText("Queued job")).toBeTruthy();
    expect(within(persistedAssets).getByText("Provider")).toBeTruthy();
    expect(within(persistedAssets).getByText("Execution mode")).toBeTruthy();
    expect(within(persistedAssets).getAllByText("job-mm-1-0004").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("No paid worker consumed this job")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy queue audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Asset: mm-1",
          "Queued job: job-mm-1-0004",
          "Status: manual_attach_ready",
          "Provider: unavailable",
          "Execution mode: unavailable",
          "Worker state: No paid worker consumed this job",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Queue audit copied" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Attach" }));

    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-1"));
    expect((screen.getByLabelText("Artifact job id") as HTMLInputElement).value).toBe("job-mm-1-0004");
    expect(mockAttachArtifact).not.toHaveBeenCalled();
    expect(mockRunWorker).not.toHaveBeenCalled();
  });

  it("surfaces attached artifact previews and rejected retry actions in persisted rows", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Attached 1" }));
    const persistedAssets = screen.getByTestId("multimedia-persisted-assets");
    expect(within(persistedAssets).getByText("video/mp4")).toBeTruthy();
    expect(within(persistedAssets).getByText("live")).toBeTruthy();
    expect(within(persistedAssets).getByText("krea")).toBeTruthy();
    expect(within(persistedAssets).getByText("sha256:2222abcd")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-2.mp4",
    );
    expect(screen.getByRole("link", { name: "Download" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-2.mp4",
    );

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("https://cdn.example.test/mm-2.mp4"));
    expect(screen.getByRole("button", { name: "Copied" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy job" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("job-mm-2-0004"));
    expect(screen.getByRole("button", { name: "Job copied" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(within(persistedAssets).getByText("Artifact URI")).toBeTruthy();
    expect(within(persistedAssets).getByText("https://cdn.example.test/mm-2.mp4")).toBeTruthy();
    expect(within(persistedAssets).getByText("Source job")).toBeTruthy();
    expect(within(persistedAssets).getByText("krea / live / video/mp4")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Rejected 1" }));
    expect(within(persistedAssets).getAllByText("artifact_validation_failed")).toHaveLength(2);
    expect(
      within(persistedAssets).getByText("Provider artifact validation failed: artifact_uri must be an http(s) URL with a host."),
    ).toBeTruthy();
    expect(within(persistedAssets).getByText("krea / live / job-mm-3-0005")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "asset_id: mm-3",
          "status: artifact_rejected",
          "error_code: artifact_validation_failed",
          "message: Provider artifact validation failed: artifact_uri must be an http(s) URL with a host.",
          "provider_family: krea",
          "execution_mode: live",
          "source_job_id: job-mm-3-0005",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Audit copied" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "https://cdn.example.test/stale.mp4" } });
    fireEvent.change(screen.getByLabelText("Checksum"), { target: { value: "sha256:stale" } });
    fireEvent.change(screen.getByLabelText("Media type"), { target: { value: "audio/mpeg" } });

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-3"));
    expect((screen.getByLabelText("Artifact job id") as HTMLInputElement).value).toBe("job-mm-3-0005");
    expect((screen.getByLabelText("Artifact URL") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Checksum") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Media type") as HTMLInputElement).value).toBe("video/mp4");
    expect(screen.getByText("Artifact URL: http(s) URL with host")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "https://cdn.example.test/retry.mp4" } });

    expect(screen.queryByText("Artifact URL: http(s) URL with host")).toBeNull();
    expect(mockAttachArtifact).not.toHaveBeenCalled();
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
    expect(screen.getAllByText("dry_run").length).toBeGreaterThan(0);
    expect(screen.getAllByText("No artifact attached").length).toBeGreaterThan(0);
  });

  it("queues live provider execution only through explicit budget controls", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    await reviewPlan();

    const liveSpendReview = screen.getByTestId("multimedia-live-spend-review");
    expect(within(liveSpendReview).getByText("No paid worker runs from Queue live job")).toBeTruthy();
    expect(within(liveSpendReview).getByText("$50.00 cap")).toBeTruthy();
    expect(within(liveSpendReview).getByText("Acknowledgement required")).toBeTruthy();
    expect(within(liveSpendReview).getByText("rev-1")).toBeTruthy();
    expect(within(liveSpendReview).getByText("Balanced / krea")).toBeTruthy();
    expect(within(liveSpendReview).getByText("30 min video")).toBeTruthy();
    expect(within(liveSpendReview).getByText("Live worker disabled")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "0" } });
    expect(within(liveSpendReview).getByText("Enter positive budget")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Queue live job" }));
    expect(mockPrepare).not.toHaveBeenCalled();
    expect(screen.getByText("Enter a positive live provider budget before queueing.")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("Spend acknowledged"));
    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "75" } });

    expect(within(liveSpendReview).getByText("$75.00 cap")).toBeTruthy();
    expect(within(liveSpendReview).getByText("Spend acknowledged")).toBeTruthy();

    fireEvent.click(within(liveSpendReview).getByRole("button", { name: "Copy review" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Spend boundary: No paid worker runs from Queue live job",
          "Budget cap: $75.00 cap",
          "Acknowledgement: Spend acknowledged",
          "Dry-run revision: rev-1",
          "Provider route: Balanced / krea",
          "Requested media: 30 min video",
          "Worker state: Live worker disabled",
        ].join("\n"),
      ),
    );
    expect(within(liveSpendReview).getByRole("button", { name: "Review copied" })).toBeTruthy();

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
    expect(mockRunWorker).not.toHaveBeenCalled();
    expect(await screen.findByText(/Live execution queued for krea/)).toBeTruthy();
    expect(screen.getByText("live_requested")).toBeTruthy();
    expect(screen.getByText("Artifact pending")).toBeTruthy();
    const readiness = screen.getByTestId("multimedia-provider-readiness");
    expect(within(readiness).getByText("Live worker disabled")).toBeTruthy();
    expect(within(readiness).getByText("Queued job-mm-1-0001")).toBeTruthy();
    expect(within(readiness).getByText("Ready for job-mm-1-0001")).toBeTruthy();
    expect(within(readiness).getByText("Pending")).toBeTruthy();
    const queueAudit = screen.getByTestId("multimedia-live-queue-audit");
    expect(within(queueAudit).getByText("job-mm-1-0001")).toBeTruthy();
    expect(within(queueAudit).getByText("$75.00 cap")).toBeTruthy();
    expect(within(queueAudit).getByText("rev-1")).toBeTruthy();
    expect(within(queueAudit).getByText("Balanced / krea")).toBeTruthy();
    expect(within(queueAudit).getByText("30 min video")).toBeTruthy();
    expect(within(queueAudit).getByText("No paid worker consumed this job")).toBeTruthy();

    fireEvent.click(within(queueAudit).getByRole("button", { name: "Copy queued audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Queued job: job-mm-1-0001",
          "Budget cap: $75.00 cap",
          "Dry-run revision: rev-1",
          "Provider route: Balanced / krea",
          "Requested media: 30 min video",
          "Worker state: No paid worker consumed this job",
        ].join("\n"),
      ),
    );
    expect(within(queueAudit).getByRole("button", { name: "Queued audit copied" })).toBeTruthy();
  });

  it("surfaces attached provider artifacts with open, download, and copy actions", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    mockCreate.mockResolvedValueOnce(artifactProviderRecord);

    await reviewPlan();

    const jobPanel = await screen.findByTestId("multimedia-job-panel");
    expect(within(jobPanel).getByText("video/mp4")).toBeTruthy();
    const readiness = screen.getByTestId("multimedia-provider-readiness");
    expect(within(readiness).getByText("Live worker disabled")).toBeTruthy();
    expect(within(readiness).getByText("Attached")).toBeTruthy();
    expect(within(jobPanel).getByText("sha256:abcdef123456")).toBeTruthy();
    expect(within(jobPanel).getByText("https://cdn.example.test/mm-1.mp4")).toBeTruthy();
    expect(within(jobPanel).getByRole("link", { name: "Open artifact" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-1.mp4",
    );
    expect(within(jobPanel).getByRole("link", { name: "Download" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-1.mp4",
    );

    fireEvent.click(within(jobPanel).getByRole("button", { name: "Copy link" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("https://cdn.example.test/mm-1.mp4"));
    expect(within(jobPanel).getByRole("button", { name: "Copied" })).toBeTruthy();
  });

  it("attaches a pasted provider artifact without running a paid provider worker", async () => {
    mockCreate.mockResolvedValueOnce(queuedProviderRecord);
    await reviewPlan();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "https://cdn.example.test/mm-1.mp4" } });
    fireEvent.change(screen.getByLabelText("Checksum"), { target: { value: "sha256:abcdef123456" } });
    fireEvent.change(screen.getByLabelText("Media type"), { target: { value: "video/mp4" } });
    fireEvent.click(screen.getByRole("button", { name: "Attach artifact" }));

    await waitFor(() =>
      expect(mockAttachArtifact).toHaveBeenCalledWith("mm-1", {
        job_id: "job-mm-1-0001",
        artifact_uri: "https://cdn.example.test/mm-1.mp4",
        artifact_checksum: "sha256:abcdef123456",
        artifact_media_type: "video/mp4",
      }),
    );
    expect(mockRunWorker).not.toHaveBeenCalled();
    expect(await screen.findByText("https://cdn.example.test/mm-1.mp4")).toBeTruthy();
    expect(screen.getByText("Attachment saved for job-mm-1-0004 (video/mp4).")).toBeTruthy();
    expect(screen.getByText("Attachment saved")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Attach" })).toBeNull();
  });

  it("shows backend validation feedback for manually attached artifacts", async () => {
    mockCreate.mockResolvedValueOnce(queuedProviderRecord);
    mockAttachArtifact.mockResolvedValueOnce(rejectedArtifactRecord);
    await reviewPlan();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "file:///tmp/mm-1.mp4" } });
    fireEvent.change(screen.getByLabelText("Checksum"), { target: { value: "sha256:not-hex" } });
    fireEvent.change(screen.getByLabelText("Media type"), { target: { value: "video/mp4" } });
    fireEvent.click(screen.getByRole("button", { name: "Attach artifact" }));

    await waitFor(() => expect(mockAttachArtifact).toHaveBeenCalled());
    await waitFor(() => expect(screen.getAllByText("Artifact rejected").length).toBeGreaterThan(0));
    expect(within(screen.getByTestId("multimedia-provider-readiness")).getByText("Rejected")).toBeTruthy();
    expect(screen.getByText(/Check the artifact URL, sha256 checksum, and media type/)).toBeTruthy();
    expect(screen.queryByText(/Attachment saved for/)).toBeNull();
  });

  it("distinguishes artifact validation failures from missing artifacts", async () => {
    mockCreate.mockResolvedValueOnce(rejectedArtifactRecord);

    await reviewPlan();

    await waitFor(() => expect(screen.getAllByText("Artifact rejected").length).toBeGreaterThan(0));
    expect(screen.getByText(/Check the artifact URL, sha256 checksum, and media type/)).toBeTruthy();
    expect(screen.getAllByText("artifact_validation_failed").length).toBeGreaterThan(0);
    expect(screen.queryByText("No artifact attached")).toBeNull();
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
