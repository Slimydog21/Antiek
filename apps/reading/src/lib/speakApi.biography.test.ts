import { afterEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "./api";
import {
  assembleDraft,
  createBiography,
  createPerson,
  getEconomics,
  getProject,
  inviteByEmail,
  listPeople,
  listPublicFeed,
  listVoices,
  makeShareLink,
  releasePayout,
  whatEveryoneAgreesOn,
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

  it("rejects non-object biography composition responses through field validation", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse(null));

    await expect(
      createBiography({
        investigationId: "inv-root",
        subjectName: "Maria",
      }),
    ).rejects.toThrow("investigation_id must be a non-empty string");
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

  it("rejects non-object create-person responses through field validation", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse("created"));

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
            subject_ref: "  Maria  ",
            publish_intent: "private_never_published",
            interview_count: "2",
          },
          {
            project_id: "proj-title",
            title: "  Fallback title  ",
            publish_intent: "will_be_public",
            interview_count: -1,
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
      {
        id: "proj-title",
        name: "Fallback title",
        willBePublic: true,
        voiceCount: 0,
      },
    ]);
  });

  it("dedupes duplicate private project ids after trimming", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        projects: [
          {
            project_id: " proj-dup ",
            subject_ref: "First Maria",
            publish_intent: "private_never_published",
            interview_count: 2,
          },
          {
            project_id: "proj-dup",
            subject_ref: "Duplicate Maria",
            publish_intent: "will_be_public",
            interview_count: 9,
          },
          {
            project_id: "proj-other",
            subject_ref: "Other person",
            publish_intent: "private_never_published",
            interview_count: 0,
          },
        ],
      }),
    );

    await expect(listPeople()).resolves.toEqual([
      {
        id: "proj-dup",
        name: "First Maria",
        willBePublic: false,
        voiceCount: 2,
      },
      {
        id: "proj-other",
        name: "Other person",
        willBePublic: false,
        voiceCount: 0,
      },
    ]);
  });

  it("treats malformed project list wrappers as empty", async () => {
    apiFetchMock.mockResolvedValueOnce(jsonResponse({ projects: { project_id: "proj-1" } }));

    await expect(listPeople()).resolves.toEqual([]);

    apiFetchMock.mockResolvedValueOnce(jsonResponse(null));

    await expect(listPublicFeed()).resolves.toEqual([]);
  });

  it("drops malformed project rows from the public feed", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        projects: [
          {
            project_id: " proj-public ",
            subject_ref: "  Rosa  ",
            interview_count: "3",
          },
          {
            project_id: "proj-title",
            title: "  Public title  ",
            interview_count: 1.5,
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
      {
        id: "proj-title",
        name: "Public title",
        voiceCount: 0,
      },
    ]);
  });

  it("dedupes duplicate public-feed project ids after trimming", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        projects: [
          {
            project_id: " proj-public ",
            subject_ref: "First Rosa",
            interview_count: 3,
          },
          {
            project_id: "proj-public",
            subject_ref: "Duplicate Rosa",
            interview_count: 9,
          },
          {
            project_id: "proj-other",
            subject_ref: "Other Rosa",
            interview_count: 1,
          },
        ],
      }),
    );

    await expect(listPublicFeed()).resolves.toEqual([
      {
        id: "proj-public",
        name: "First Rosa",
        voiceCount: 3,
      },
      {
        id: "proj-other",
        name: "Other Rosa",
        voiceCount: 1,
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

  it("rejects non-object project details through field validation", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse(["not", "a", "project"]));

    await expect(getProject("proj-bad")).rejects.toThrow(
      "project_id must be a non-empty string",
    );
  });

  it("sanitizes project detail and economics booleans without truthy-string activation", async () => {
    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        project_id: " proj-1 ",
        subject_ref: " ",
        title: "  Rosa's story  ",
        publish_intent: "will_be_public",
        subject_status: "living_subject",
      }),
    );

    await expect(getProject("proj-1")).resolves.toEqual({
      id: "proj-1",
      name: "Rosa's story",
      willBePublic: true,
      subjectStatusWord: "living subject",
    });

    apiFetchMock.mockResolvedValueOnce(
      jsonResponse({
        split_applies: "true",
        creator_carries_cost: true,
        public_publishing_allowed: "yes",
        public_publishing_reason: "  waits on counsel  ",
        disbursement_allowed: false,
        disbursement_reason: "  gated  ",
      }),
    );

    await expect(getEconomics("proj-1")).resolves.toEqual({
      splitApplies: false,
      creatorCarriesCost: true,
      publicPublishingAllowed: false,
      publicPublishingReason: "waits on counsel",
      disbursementAllowed: false,
      disbursementReason: "gated",
    });
  });
});

describe("Speak invites", () => {
  it("drops malformed invite rows from the voice list", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        invites: [
          {
            interview_id: " iv-valid ",
            informant_email: "  aunt@example.com  ",
            status: "completed",
            link: "  https://antiek.ai/speak/invite/ok  ",
          },
          {
            interview_id: "iv-handle",
            informant_handle: "  family friend  ",
            status: "nonsense",
            link: null,
          },
          {
            interview_id: " ",
            informant_email: "invisible@example.com",
            status: "completed",
            link: "https://antiek.ai/speak/invite/bad",
          },
        ],
      }),
    );

    await expect(listVoices("proj-1")).resolves.toEqual([
      {
        interviewId: "iv-valid",
        who: "aunt@example.com",
        state: "shared",
        link: "https://antiek.ai/speak/invite/ok",
      },
      {
        interviewId: "iv-handle",
        who: "family friend",
        state: "invited",
        link: "",
      },
    ]);
  });

  it("dedupes duplicate invite ids after trimming", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        invites: [
          {
            interview_id: " iv-dup ",
            informant_email: "first@example.com",
            status: "completed",
            link: "https://antiek.ai/speak/invite/first",
          },
          {
            interview_id: "iv-dup",
            informant_email: "duplicate@example.com",
            status: "in_progress",
            link: "https://antiek.ai/speak/invite/duplicate",
          },
          {
            interview_id: "iv-other",
            informant_handle: "family friend",
            status: "invited",
            link: "https://antiek.ai/speak/invite/other",
          },
        ],
      }),
    );

    await expect(listVoices("proj-1")).resolves.toEqual([
      {
        interviewId: "iv-dup",
        who: "first@example.com",
        state: "shared",
        link: "https://antiek.ai/speak/invite/first",
      },
      {
        interviewId: "iv-other",
        who: "family friend",
        state: "invited",
        link: "https://antiek.ai/speak/invite/other",
      },
    ]);
  });

  it("treats malformed invite wrappers as empty voice lists", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ invites: { interview_id: "iv-1" } }));

    await expect(listVoices("proj-1")).resolves.toEqual([]);
  });

  it("rejects malformed invite responses for direct email invites", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        interview_id: " ",
        informant_email: "aunt@example.com",
        status: "invited",
        link: "https://antiek.ai/speak/invite/bad",
      }),
    );

    await expect(inviteByEmail("proj-1", "aunt@example.com")).rejects.toThrow(
      "interview_id must be a non-empty string",
    );
  });

  it("rejects non-object invite responses through field validation", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse(null));

    await expect(inviteByEmail("proj-1", "aunt@example.com")).rejects.toThrow(
      "interview_id must be a non-empty string",
    );
  });

  it("rejects malformed share-link responses", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        interview_id: "iv-1",
        informant_handle: "a friend or family member",
        status: "invited",
        link: " ",
      }),
    );

    await expect(makeShareLink("proj-1")).rejects.toThrow(
      "link must be a non-empty string",
    );
  });
});

describe("Speak synthesis and payout boundaries", () => {
  it("sanitizes agreement clusters without saying malformed claims are proven", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        clusters: [
          {
            canonical_text: "  Everyone remembers the bakery.  ",
            label: "multiply_attested",
            independent_attesters: "2",
          },
          {
            canonical_text: "",
            label: "contradicted",
            independent_attesters: -1,
          },
          {
            label: "single_pass",
            independent_attesters: 1.5,
          },
          {
            canonical_text: "",
            label: "",
          },
        ],
      }),
    );

    await expect(whatEveryoneAgreesOn("proj-1")).resolves.toEqual([
      {
        text: "Everyone remembers the bakery.",
        kind: "corroborated",
        voices: 2,
      },
      {
        text: "contradicted",
        kind: "disagreement",
        voices: 1,
      },
      {
        text: "single pass",
        kind: "single",
        voices: 1,
      },
    ]);
  });

  it("treats malformed corroboration wrappers as empty agreement lists", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse({ clusters: { label: "multiply_attested" } }));

    await expect(whatEveryoneAgreesOn("proj-1")).resolves.toEqual([]);
  });

  it("sanitizes biography draft text and excluded claim counts", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        prose_text: "  Drafted life story.  ",
        excluded_claim_ids: [" c1 ", "", 7, "c2"],
      }),
    );

    await expect(assembleDraft("proj-1", true)).resolves.toEqual({
      prose: "Drafted life story.",
      excludedCount: 2,
    });
  });

  it("defaults malformed biography draft wrappers without fabricating prose", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse(["not", "a", "draft"]));

    await expect(assembleDraft("proj-1", true)).resolves.toEqual({
      prose: "",
      excludedCount: 0,
    });
  });

  it("sanitizes release payout figures without truthy-string budget exhaustion", async () => {
    apiFetchMock.mockResolvedValue(
      jsonResponse({
        spent_usd: " 3.25 ",
        budget_usd: "",
        budget_exhausted: "true",
        capped_interview_ids: [" iv-1 ", "", 9, "iv-2"],
      }),
    );

    await expect(
      releasePayout("proj-1", {
        informationGoal: "capture bakery story",
        budgetUsd: "5",
        perInterviewCapUsd: "1",
        adRevenueUsd: "0",
      }),
    ).resolves.toEqual({
      spentUsd: "3.25",
      budgetUsd: "0",
      budgetExhausted: false,
      cappedCount: 2,
    });
  });

  it("defaults malformed release payout wrappers to closed zero values", async () => {
    apiFetchMock.mockResolvedValue(jsonResponse("released"));

    await expect(
      releasePayout("proj-1", {
        informationGoal: "capture bakery story",
        budgetUsd: "5",
        perInterviewCapUsd: "1",
        adRevenueUsd: "0",
      }),
    ).resolves.toEqual({
      spentUsd: "0",
      budgetUsd: "0",
      budgetExhausted: false,
      cappedCount: 0,
    });
  });
});
