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
          live_request_max_budget_usd: 22,
          live_request_route_policy: "highest_quality",
          live_request_dry_run_revision_id: "rev-1",
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
          live_request_max_budget_usd: 12,
          live_request_route_policy: "cheapest",
          live_request_dry_run_revision_id: "rev-1",
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
    expect(within(persistedAssets).queryByText("Queued job")).toBeNull();
    expect(within(persistedAssets).getByText("job-mm-1-0004 / Balanced / 30 min")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(within(persistedAssets).getByText("Queued job")).toBeTruthy();
    expect(within(persistedAssets).getByText("Route")).toBeTruthy();
    expect(within(persistedAssets).getByText("Requested media")).toBeTruthy();
    expect(within(persistedAssets).getByText("Balanced")).toBeTruthy();
    expect(within(persistedAssets).getByText("30 min documentary video")).toBeTruthy();
    expect(within(persistedAssets).getByText("Provider")).toBeTruthy();
    expect(within(persistedAssets).getByText("Execution mode")).toBeTruthy();
    expect(within(persistedAssets).getByText("Budget cap")).toBeTruthy();
    expect(within(persistedAssets).getByText("Dry-run revision")).toBeTruthy();
    expect(within(persistedAssets).getAllByText("job-mm-1-0004").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("No paid worker consumed this job")).toBeTruthy();
    expect(within(persistedAssets).getByText("Activation boundary")).toBeTruthy();
    expect(within(persistedAssets).getByText("Separate worker activation required")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Hide details" }));
    expect(within(persistedAssets).queryByText("Queued job")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Copy queue audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Asset: mm-1",
          "Queued job: job-mm-1-0004",
          "Status: manual_attach_ready",
          "Route: Balanced",
          "Requested media: 30 min documentary video",
          "Provider: unavailable",
          "Execution mode: unavailable",
          "Budget cap: unavailable",
          "Dry-run revision: unavailable",
          "Worker state: No paid worker consumed this job",
          "Activation boundary: Separate worker activation required",
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

  it("copies provider metadata when a persisted manual-ready queue summary includes it", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText },
    });
    mockList.mockResolvedValueOnce({
      assets: [
        {
          asset_id: "mm-4",
          revision_id: "rev-1",
          title: "Manual-ready live audio",
          kind: "audio_experience",
          status: "planned",
          requested_duration_minutes: 15,
          route_policy: "cheapest",
          estimated_cost_usd: 6,
          hardening_status: null,
          latest_job_status: "queued",
          latest_job_kind: "provider_execution",
          provider_readiness: {
            status: "manual_attach_ready",
            label: "Manual attach ready",
            source_job_id: "job-mm-4-0001",
            execution_mode: "live",
            provider_family: "krea",
            live_request_max_budget_usd: 18,
            live_request_route_policy: "highest_quality",
            live_request_dry_run_revision_id: "rev-1",
            error_code: null,
            message: null,
            artifact_uri: null,
            artifact_checksum: null,
            artifact_media_type: null,
          },
        },
      ],
      count: 1,
    });
    render(<Multimedia />);

    expect(await screen.findByText(/Persisted assets/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Manual attach 1" }));
    const persistedAssets = screen.getByTestId("multimedia-persisted-assets");
    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(within(persistedAssets).getByText("Highest quality")).toBeTruthy();
    expect(within(persistedAssets).getByText("15 min audio experience")).toBeTruthy();
    expect(within(persistedAssets).getByText("$18.00 cap")).toBeTruthy();
    expect(within(persistedAssets).getByText("rev-1")).toBeTruthy();
    expect(within(persistedAssets).getAllByText("krea").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("live").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("Activation boundary")).toBeTruthy();
    expect(within(persistedAssets).getByText("Separate worker activation required")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy queue audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Asset: mm-4",
          "Queued job: job-mm-4-0001",
          "Status: manual_attach_ready",
          "Route: Highest quality",
          "Requested media: 15 min audio experience",
          "Provider: krea",
          "Execution mode: live",
          "Budget cap: $18.00 cap",
          "Dry-run revision: rev-1",
          "Worker state: No paid worker consumed this job",
          "Activation boundary: Separate worker activation required",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Queue audit copied" })).toBeTruthy();

    mockList.mockResolvedValueOnce({
      assets: [
        {
          asset_id: "mm-4",
          revision_id: "rev-2",
          title: "Manual-ready live audio",
          kind: "audio_experience",
          status: "planned",
          requested_duration_minutes: 15,
          route_policy: "cheapest",
          estimated_cost_usd: 6,
          hardening_status: null,
          latest_job_status: "queued",
          latest_job_kind: "provider_execution",
          provider_readiness: {
            status: "manual_attach_ready",
            label: "Manual attach ready",
            source_job_id: "job-mm-4-0002",
            execution_mode: "live",
            provider_family: "krea",
            live_request_max_budget_usd: 20,
            live_request_route_policy: "balanced",
            live_request_dry_run_revision_id: "rev-2",
            error_code: null,
            message: null,
            artifact_uri: null,
            artifact_checksum: null,
            artifact_media_type: null,
          },
        },
      ],
      count: 1,
    });
    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
    await waitFor(() => expect(within(persistedAssets).getByText("job-mm-4-0002 / Balanced / 15 min")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Copy queue audit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Queue audit copied" })).toBeNull();
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
    expect(within(persistedAssets).getAllByText("video/mp4").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("live")).toBeTruthy();
    expect(within(persistedAssets).getByText("krea")).toBeTruthy();
    expect(within(persistedAssets).getAllByText("sha256:2222abcd").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("Artifact attached and ready")).toBeTruthy();
    expect(
      within(persistedAssets).getByText("Review the attached video/mp4 from job-mm-2-0004 before publishing or exporting."),
    ).toBeTruthy();
    expect(
      within(persistedAssets).getByText("Open, download, copy link, and copy audit are read-only actions; no provider worker is triggered."),
    ).toBeTruthy();
    expect(within(persistedAssets).getByText("Export review ready")).toBeTruthy();
    expect(within(persistedAssets).getByText("Manual review required before publish/export")).toBeTruthy();
    expect(within(persistedAssets).getByText("No public export or publish action has run")).toBeTruthy();
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

    fireEvent.click(screen.getByRole("button", { name: "Copy audit" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Asset: mm-2",
          "Status: artifact_attached",
          "Artifact URI: https://cdn.example.test/mm-2.mp4",
          "Artifact checksum: sha256:2222abcd",
          "Artifact media type: video/mp4",
          "Provider: krea",
          "Execution mode: live",
          "Source job: job-mm-2-0004",
          "Request route: Highest quality",
          "Budget cap: $22.00 cap",
          "Dry-run revision: rev-1",
          "Activation boundary: Separate worker activation required",
          "Copy action: Read-only; no provider worker triggered",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Audit copied" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Copy export review" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Artifact: video/mp4",
          "Source job: job-mm-2-0004",
          "Review gate: Manual review required before publish/export",
          "Artifact URI: https://cdn.example.test/mm-2.mp4",
          "Checksum: sha256:2222abcd",
          "Request route: Highest quality",
          "Budget cap: $22.00 cap",
          "Dry-run revision: rev-1",
          "Activation boundary: Separate worker activation required",
          "Publish boundary: No public export or publish action has run",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Export review copied" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Details" }));

    expect(within(persistedAssets).getAllByText("Artifact URI").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("https://cdn.example.test/mm-2.mp4").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("Source job").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getByText("krea / live / video/mp4")).toBeTruthy();
    expect(within(persistedAssets).getAllByText("Request route").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("Highest quality").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("$22.00 cap").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("rev-1").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("Activation boundary").length).toBeGreaterThan(0);
    expect(within(persistedAssets).getAllByText("Separate worker activation required").length).toBeGreaterThan(0);

    mockList.mockResolvedValueOnce({
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
            live_request_max_budget_usd: 24,
            live_request_route_policy: "highest_quality",
            live_request_dry_run_revision_id: "rev-2",
            error_code: null,
            message: null,
            artifact_uri: "https://cdn.example.test/mm-2-v2.mp4",
            artifact_checksum: "sha256:3333abcd",
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
            live_request_max_budget_usd: 12,
            live_request_route_policy: "cheapest",
            live_request_dry_run_revision_id: "rev-1",
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
    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
    await waitFor(() => expect(screen.getAllByText("sha256:3333abcd").length).toBeGreaterThan(0));
    expect(screen.getByRole("button", { name: "Copy link" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Copied" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy audit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Audit copied" })).toBeNull();
    expect(screen.getByRole("button", { name: "Copy export review" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Export review copied" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Rejected 1" }));
    expect(within(persistedAssets).getAllByText("artifact_validation_failed")).toHaveLength(2);
    expect(
      within(persistedAssets).getByText("Provider artifact validation failed: artifact_uri must be an http(s) URL with a host."),
    ).toBeTruthy();
    expect(within(persistedAssets).getByText("krea / live / job-mm-3-0005")).toBeTruthy();
    expect(within(persistedAssets).getByText("Cheapest / $12.00 cap / rev-1 / Separate worker activation required")).toBeTruthy();

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
          "Request route: Cheapest",
          "Budget cap: $12.00 cap",
          "Dry-run revision: rev-1",
          "Activation boundary: Separate worker activation required",
        ].join("\n"),
      ),
    );
    expect(screen.getByRole("button", { name: "Audit copied" })).toBeTruthy();

    mockList.mockResolvedValueOnce({
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
            live_request_max_budget_usd: 24,
            live_request_route_policy: "highest_quality",
            live_request_dry_run_revision_id: "rev-2",
            error_code: null,
            message: null,
            artifact_uri: "https://cdn.example.test/mm-2-v2.mp4",
            artifact_checksum: "sha256:3333abcd",
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
            live_request_max_budget_usd: 14,
            live_request_route_policy: "cheapest",
            live_request_dry_run_revision_id: "rev-2",
            error_code: "artifact_validation_failed",
            message: "Provider artifact validation failed: artifact_checksum must be sha256-prefixed.",
            artifact_uri: null,
            artifact_checksum: null,
            artifact_media_type: null,
          },
        },
      ],
      count: 3,
    });
    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
    await waitFor(() =>
      expect(
        within(persistedAssets).getByText("Provider artifact validation failed: artifact_checksum must be sha256-prefixed."),
      ).toBeTruthy(),
    );
    expect(within(persistedAssets).getByText("Cheapest / $14.00 cap / rev-2 / Separate worker activation required")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy audit" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Audit copied" })).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Copy job" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("job-mm-3-0005"));
    expect(screen.getByRole("button", { name: "Job copied" })).toBeTruthy();

    mockList.mockResolvedValueOnce({
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
            live_request_max_budget_usd: 24,
            live_request_route_policy: "highest_quality",
            live_request_dry_run_revision_id: "rev-2",
            error_code: null,
            message: null,
            artifact_uri: "https://cdn.example.test/mm-2-v2.mp4",
            artifact_checksum: "sha256:3333abcd",
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
            source_job_id: "job-mm-3-0006",
            execution_mode: "live",
            provider_family: "krea",
            live_request_max_budget_usd: 14,
            live_request_route_policy: "cheapest",
            live_request_dry_run_revision_id: "rev-2",
            error_code: "artifact_validation_failed",
            message: "Provider artifact validation failed: artifact_checksum must be sha256-prefixed.",
            artifact_uri: null,
            artifact_checksum: null,
            artifact_media_type: null,
          },
        },
      ],
      count: 3,
    });
    fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
    await waitFor(() => expect(within(persistedAssets).getByText("krea / live / job-mm-3-0006")).toBeTruthy());
    expect(screen.getByRole("button", { name: "Copy job" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Job copied" })).toBeNull();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "https://cdn.example.test/stale.mp4" } });
    fireEvent.change(screen.getByLabelText("Checksum"), { target: { value: "sha256:stale" } });
    fireEvent.change(screen.getByLabelText("Media type"), { target: { value: "audio/mpeg" } });

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mockGet).toHaveBeenCalledWith("mm-3"));
    expect((screen.getByLabelText("Artifact job id") as HTMLInputElement).value).toBe("job-mm-3-0006");
    expect((screen.getByLabelText("Artifact URL") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Checksum") as HTMLInputElement).value).toBe("");
    expect((screen.getByLabelText("Media type") as HTMLInputElement).value).toBe("video/mp4");
    expect(screen.getByText("Checksum: sha256 digest")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Artifact URL"), { target: { value: "https://cdn.example.test/retry.mp4" } });

    expect(screen.queryByText("Checksum: sha256 digest")).toBeNull();
    expect(mockAttachArtifact).not.toHaveBeenCalled();
    expect(mockRunWorker).not.toHaveBeenCalled();
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
    const activationChecklist = screen.getByTestId("multimedia-live-activation-checklist");
    expect(within(activationChecklist).getByText("Budget gate")).toBeTruthy();
    expect(within(activationChecklist).getByText("$50.00 cap")).toBeTruthy();
    expect(within(activationChecklist).getByText("Operator acknowledgement")).toBeTruthy();
    expect(within(activationChecklist).getByText("Acknowledgement required")).toBeTruthy();
    expect(within(activationChecklist).getByText("Dry-run revision")).toBeTruthy();
    expect(within(activationChecklist).getByText("rev-1")).toBeTruthy();
    expect(within(activationChecklist).getByText("Provider route")).toBeTruthy();
    expect(within(activationChecklist).getByText("Balanced / krea")).toBeTruthy();
    expect(within(activationChecklist).getByText("Execution boundary")).toBeTruthy();
    expect(within(activationChecklist).getByText("Live worker disabled")).toBeTruthy();
    expect(
      within(activationChecklist).getByText("This checklist is evidence only; provider execution still requires a separate worker activation."),
    ).toBeTruthy();
    fireEvent.click(within(activationChecklist).getByRole("button", { name: "Copy checklist" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Budget gate: $50.00 cap",
          "Operator acknowledgement: Acknowledgement required",
          "Dry-run revision: rev-1",
          "Provider route: Balanced / krea",
          "Execution boundary: Live worker disabled",
          "Activation state: Evidence only; provider execution still requires a separate worker activation.",
        ].join("\n"),
      ),
    );
    expect(within(activationChecklist).getByRole("button", { name: "Checklist copied" })).toBeTruthy();
    const activationHandoff = screen.getByTestId("multimedia-live-activation-handoff");
    expect(within(activationHandoff).getByText("Operator next step")).toBeTruthy();
    expect(within(activationHandoff).getByText("Review before worker activation")).toBeTruthy();
    expect(within(activationHandoff).getByText("Spend boundary")).toBeTruthy();
    expect(within(activationHandoff).getByText("Queue records intent only")).toBeTruthy();
    fireEvent.click(within(activationHandoff).getByRole("button", { name: "Copy handoff" }));
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Activation handoff",
          "Budget gate: $50.00 cap",
          "Operator acknowledgement: Acknowledgement required",
          "Dry-run revision: rev-1",
          "Provider route: Balanced / krea",
          "Execution boundary: Live worker disabled",
          "Activation state: Evidence only; provider execution still requires a separate worker activation.",
          "Operator next step: Review this bundle before enabling a live provider worker.",
          "Spend boundary: Queue live job records intent only; it does not call Krea/TTS/video providers.",
        ].join("\n"),
      ),
    );
    expect(within(activationHandoff).getByRole("button", { name: "Handoff copied" })).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "0" } });
    expect(within(liveSpendReview).getByText("Enter positive budget")).toBeTruthy();
    await waitFor(() => expect(within(activationChecklist).getByRole("button", { name: "Copy checklist" })).toBeTruthy());
    expect(within(activationHandoff).getByRole("button", { name: "Copy handoff" })).toBeTruthy();
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

    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "76" } });
    expect(within(liveSpendReview).getByText("$76.00 cap")).toBeTruthy();
    await waitFor(() => expect(within(liveSpendReview).getByRole("button", { name: "Copy review" })).toBeTruthy());
    expect(within(liveSpendReview).queryByRole("button", { name: "Review copied" })).toBeNull();
    fireEvent.change(screen.getByLabelText("Budget"), { target: { value: "75" } });
    expect(within(liveSpendReview).getByText("$75.00 cap")).toBeTruthy();

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
    expect(within(readiness).getByText("Activation boundary")).toBeTruthy();
    expect(within(readiness).getByText("Separate worker activation required")).toBeTruthy();
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
    expect(within(queueAudit).getByText("Activation boundary")).toBeTruthy();
    expect(within(queueAudit).getByText("Separate worker activation required")).toBeTruthy();

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
          "Activation boundary: Separate worker activation required",
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
    expect(within(jobPanel).getAllByText("video/mp4").length).toBeGreaterThan(0);
    const readiness = screen.getByTestId("multimedia-provider-readiness");
    expect(within(readiness).getByText("Live worker disabled")).toBeTruthy();
    expect(within(readiness).getByText("Activation boundary")).toBeTruthy();
    expect(within(readiness).getByText("Separate worker activation required")).toBeTruthy();
    expect(within(readiness).getByText("Attached")).toBeTruthy();
    expect(within(jobPanel).getAllByText("sha256:abcdef123456").length).toBeGreaterThan(0);
    expect(within(jobPanel).getAllByText("https://cdn.example.test/mm-1.mp4").length).toBeGreaterThan(0);
    expect(within(jobPanel).getByText("Export review ready")).toBeTruthy();
    expect(within(jobPanel).getByText("Manual review required before publish/export")).toBeTruthy();
    expect(within(jobPanel).getByText("No public export or publish action has run")).toBeTruthy();
    expect(within(jobPanel).getByRole("link", { name: "Open artifact" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-1.mp4",
    );
    expect(within(jobPanel).getByRole("link", { name: "Download" }).getAttribute("href")).toBe(
      "https://cdn.example.test/mm-1.mp4",
    );

    fireEvent.click(within(jobPanel).getByRole("button", { name: "Copy link" }));

    await waitFor(() => expect(writeText).toHaveBeenCalledWith("https://cdn.example.test/mm-1.mp4"));
    expect(within(jobPanel).getByRole("button", { name: "Copied" })).toBeTruthy();

    mockListJobs.mockResolvedValueOnce({
      jobs: artifactProviderRecord.jobs.map((job) =>
        job.job_id === "job-mm-1-0004"
          ? {
              ...job,
              artifact_uri: "https://cdn.example.test/mm-1-v2.mp4",
              artifact_checksum: "sha256:fedcba654321",
            }
          : job,
      ),
      count: artifactProviderRecord.jobs.length,
    });
    fireEvent.click(within(jobPanel).getByRole("button", { name: "Refresh jobs" }));
    await waitFor(() => expect(within(jobPanel).getAllByText("https://cdn.example.test/mm-1-v2.mp4").length).toBeGreaterThan(0));
    expect(within(jobPanel).getByRole("button", { name: "Copy link" })).toBeTruthy();
    expect(within(jobPanel).queryByRole("button", { name: "Copied" })).toBeNull();

    fireEvent.click(within(jobPanel).getByRole("button", { name: "Copy export review" }));

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        [
          "Artifact: video/mp4",
          "Source job: job-mm-1-0004",
          "Review gate: Manual review required before publish/export",
          "Artifact URI: https://cdn.example.test/mm-1-v2.mp4",
          "Checksum: sha256:fedcba654321",
          "Budget gate: $50.00 cap",
          "Provider route: Balanced / krea",
          "Dry-run revision: rev-1",
          "Activation boundary: Separate worker activation required",
          "Publish boundary: No public export or publish action has run",
        ].join("\n"),
      ),
    );
    expect(within(jobPanel).getByRole("button", { name: "Export review copied" })).toBeTruthy();
    expect(mockAttachArtifact).not.toHaveBeenCalled();
    expect(mockRunWorker).not.toHaveBeenCalled();
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
    await waitFor(() => expect(screen.getAllByText("https://cdn.example.test/mm-1.mp4").length).toBeGreaterThan(0));
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
    const readiness = screen.getByTestId("multimedia-provider-readiness");
    expect(within(readiness).getByText("Separate worker activation required")).toBeTruthy();
    expect(within(readiness).getByText("Rejected")).toBeTruthy();
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
