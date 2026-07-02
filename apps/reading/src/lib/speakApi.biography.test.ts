import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";
import { createBiography } from "./speakApi";

vi.mock("./api", () => ({
  apiFetch: vi.fn(),
}));

const apiFetchMock = vi.mocked(apiFetch);

afterEach(() => {
  vi.clearAllMocks();
});

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 500): Response {
  return {
    ok,
    status,
    json: async () => body,
  } as Response;
}

describe("createBiography", () => {
  it("posts the shared research root and trims returned composition ids", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        investigation_id: " inv-bio ",
        deliverable_id: " dlv-bio ",
        project_id: " proj-bio ",
      }),
    );

    const composition = await createBiography({
      investigationId: "inv-root",
      subjectName: "  Maria  ",
      title: "Maria's story",
    });

    expect(apiFetchMock).toHaveBeenCalledWith("/speak/biography", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        investigation_id: "inv-root",
        subject_name: "Maria",
        title: "Maria's story",
      }),
    });
    expect(composition).toEqual({
      investigationId: "inv-bio",
      deliverableId: "dlv-bio",
      projectId: "proj-bio",
    });
  });

  it("rejects malformed returned composition ids", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        investigation_id: "inv-bio",
        deliverable_id: " ",
        project_id: "proj-bio",
      }),
    );

    await expect(
      createBiography({
        investigationId: "inv-root",
        subjectName: "Maria",
      }),
    ).rejects.toThrow("deliverable_id must be a non-empty string");
  });

  it("rejects malformed returned investigation ids", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        investigation_id: " ",
        deliverable_id: "dlv-bio",
        project_id: "proj-bio",
      }),
    );

    await expect(
      createBiography({
        investigationId: "inv-root",
        subjectName: "Maria",
      }),
    ).rejects.toThrow("investigation_id must be a non-empty string");
  });
});
