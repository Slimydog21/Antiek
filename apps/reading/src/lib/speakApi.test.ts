import { afterEach, describe, expect, it, vi } from "vitest";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  apiFetch: apiFetchMock,
}));

import { listPublicFeed, toPerson, toVoice } from "./speakApi";

afterEach(() => apiFetchMock.mockReset());

describe("Speak contribution counts at the API boundary", () => {
  it("uses contributed_voice_count instead of total interview rows for private cards", () => {
    expect(toPerson({
      project_id: "p1",
      subject_ref: "Grandma Rosa",
      interview_count: 1,
      contributed_voice_count: 0,
    })).toMatchObject({
      id: "p1",
      name: "Grandma Rosa",
      contributedVoiceCount: 0,
    });

    expect(toPerson({
      project_id: "p2",
      title: "Dad's story",
      interview_count: 1,
      contributed_voice_count: 1,
    }).contributedVoiceCount).toBe(1);
  });

  it("treats only explicit has_contribution true as a contributor", () => {
    const invited = toVoice({ interview_id: "invited", status: "invited" });
    const answered = toVoice({
      interview_id: "answered",
      status: "in_progress",
      has_contribution: true,
    });

    expect(invited.hasContribution).toBe(false);
    expect(answered.hasContribution).toBe(true);
  });

  it("omits private interview totals from public feed items", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      json: async () => ({
        projects: [{
          project_id: "public-1",
          subject_ref: "Grandma Rosa",
          interview_count: 4,
        }],
      }),
    });

    await expect(listPublicFeed()).resolves.toEqual([
      { id: "public-1", name: "Grandma Rosa" },
    ]);
  });
});
