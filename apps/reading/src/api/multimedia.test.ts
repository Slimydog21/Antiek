import { afterEach, describe, expect, it, vi } from "vitest";

import {
  approveMultimediaDryRun,
  createMultimediaDraft,
  getMultimediaAsset,
  listMultimediaJobs,
  listMultimediaAssets,
  prepareMultimediaLiveExecution,
  runMultimediaHardening,
  steerMultimediaAsset,
} from "./multimedia";
import { apiFetch } from "../lib/api";

vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch: vi.fn(),
}));

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

const record = {
  asset: {
    asset_id: "mm-1",
    revision_id: "rev-1",
    status: "planned",
    kind: "audio_experience",
    title: "Audio",
    route_policy: "cheapest",
    requested_duration_minutes: 20,
    manifest: {},
  },
  plan: {},
  mode: "audio",
  style: null,
  hardening_report: null,
  latest_steering_intent: null,
  jobs: [],
};

const jobs = {
  jobs: [
    {
      job_id: "job-mm-1-0001",
      asset_id: "mm-1",
      revision_id: "rev-1",
      sequence: 1,
      kind: "render",
      status: "succeeded",
      progress_percent: 100,
      message: "Dry-run render manifest assembled without live provider spend.",
      error_code: null,
      retryable: null,
    },
  ],
  count: 1,
};

afterEach(() => {
  mockFetch.mockReset();
});

describe("multimedia API client", () => {
  it("creates a draft with the typed request body", async () => {
    mockFetch.mockResolvedValue(jsonResponse(record, 201));

    await createMultimediaDraft({
      topic: "widebody aircraft",
      target_minutes: 20,
      mode: "audio",
      route_policy: "cheapest",
      sources: ["source"],
    });

    expect(mockFetch).toHaveBeenCalledWith("/api/multimedia/assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: "widebody aircraft",
        target_minutes: 20,
        mode: "audio",
        route_policy: "cheapest",
        sources: ["source"],
      }),
    });
  });

  it("lists, reopens, approves, steers, and hardens through stable endpoints", async () => {
    mockFetch.mockResolvedValueOnce(jsonResponse({ assets: [], count: 0 }));
    await listMultimediaAssets();
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets");

    mockFetch.mockResolvedValueOnce(jsonResponse(record));
    await getMultimediaAsset("mm 1");
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm%201");

    mockFetch.mockResolvedValueOnce(jsonResponse(jobs));
    await listMultimediaJobs("mm-1");
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm-1/jobs");

    mockFetch.mockResolvedValueOnce(jsonResponse(record));
    await approveMultimediaDryRun("mm-1");
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm-1/approve-dry-run", {
      method: "POST",
    });

    mockFetch.mockResolvedValueOnce(jsonResponse(record));
    await steerMultimediaAsset("mm-1", { prompt: "go deeper" });
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm-1/steer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt: "go deeper" }),
    });

    mockFetch.mockResolvedValueOnce(jsonResponse(record));
    await runMultimediaHardening("mm-1");
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm-1/hardening", {
      method: "POST",
    });

    mockFetch.mockResolvedValueOnce(jsonResponse(record));
    await prepareMultimediaLiveExecution("mm-1", {
      max_budget_usd: 12,
      route_policy: "balanced",
      operator_acknowledged_spend: true,
      provider_families: ["krea"],
      dry_run_revision_id: "rev-1",
    });
    expect(mockFetch).toHaveBeenLastCalledWith("/api/multimedia/assets/mm-1/prepare-live-execution", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        max_budget_usd: 12,
        route_policy: "balanced",
        operator_acknowledged_spend: true,
        provider_families: ["krea"],
        dry_run_revision_id: "rev-1",
      }),
    });
  });
});
