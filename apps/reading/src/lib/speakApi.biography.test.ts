import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";
import { createBiography, createPerson } from "./speakApi";

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

describe("createPerson", () => {
  it("trims returned project ids", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ project_id: " proj-created " }));

    await expect(createPerson("  Maria  ")).resolves.toBe("proj-created");
    expect(apiFetchMock).toHaveBeenCalledWith("/speak/projects", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        title: "Maria's story",
        subject_ref: "Maria",
        subject_status: "unknown",
        publish_intent: "private_never_published",
      }),
    });
  });

  it("rejects malformed returned project ids", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ project_id: " " }));

    await expect(createPerson("Maria")).rejects.toThrow(
      "project_id must be a non-empty string",
    );
  });
});
