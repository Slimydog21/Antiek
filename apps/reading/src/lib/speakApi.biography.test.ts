import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";
import {
  createBiography,
  createPerson,
  getProject,
  listPeople,
  listPublicFeed,
} from "./speakApi";

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

describe("Speak project lists", () => {
  it("drops malformed project rows from the private dashboard list", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        projects: [
          {
            project_id: " proj-private ",
            subject_ref: "Maria",
            publish_intent: "private_never_published",
            interview_count: 2,
          },
          {
            project_id: " ",
            subject_ref: "Invisible",
            publish_intent: "will_be_public",
            interview_count: 5,
          },
        ],
      }),
    );

    await expect(listPeople()).resolves.toEqual([
      {
        id: "proj-private",
        name: "Maria",
        willBePublic: false,
        voiceCount: 2,
      },
    ]);
  });

  it("drops malformed project rows from the public feed", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        projects: [
          {
            project_id: " proj-public ",
            subject_ref: "Rosa",
            interview_count: 3,
          },
          {
            project_id: "",
            subject_ref: "Invisible",
            interview_count: 4,
          },
        ],
      }),
    );

    await expect(listPublicFeed()).resolves.toEqual([
      {
        id: "proj-public",
        name: "Rosa",
        voiceCount: 3,
      },
    ]);
  });

  it("rejects malformed project detail ids", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        project_id: " ",
        subject_ref: "Rosa",
        publish_intent: "private_never_published",
      }),
    );

    await expect(getProject("proj-bad")).rejects.toThrow(
      "project_id must be a non-empty string",
    );
  });
});
