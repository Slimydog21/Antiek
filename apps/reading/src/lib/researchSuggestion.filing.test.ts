/**
 * researchSuggestion.filing.test.ts — Read SPR-13 M3.
 *
 * The SUGGEST-NOT-AUTOSHIP filing path: a PURE suggest fn + an EXPLICIT-accept-
 * only mutator. The load-bearing invariants:
 *   • suggestFiling is pure — calling it NEVER files (no postTypedEvent);
 *   • suggestFiling returns null when nothing clears the threshold (decline-by-
 *     default — the surface shows no hollow suggestion);
 *   • acceptFiling emits EXACTLY ONE document.filed_into_investigation event,
 *     into the ONE chosen project (never auto, never double-files);
 *   • the emitted event rides the single-writer funnel (postTypedEvent).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ProjectMatch } from "../api/books";
import { acceptFiling, suggestFiling } from "./researchSuggestion";

const { postTypedEventMock } = vi.hoisted(() => ({ postTypedEventMock: vi.fn() }));

vi.mock("./api", async (orig) => {
  const actual = await orig<typeof import("./api")>();
  return { ...actual, postTypedEvent: postTypedEventMock };
});

afterEach(() => {
  vi.clearAllMocks();
});

const match = (over: Partial<ProjectMatch> = {}): ProjectMatch => ({
  investigation_id: "inv-1",
  question: "How did the stoics handle adversity?",
  score: 0.72,
  ...over,
});

describe("suggestFiling (pure)", () => {
  it("returns null with no matches — no hollow suggestion (decline-by-default)", () => {
    expect(suggestFiling({ matches: [] })).toBeNull();
  });

  it("names the top match and never files (pure)", () => {
    const s = suggestFiling({ matches: [match()] });
    expect(s).not.toBeNull();
    expect(s!.candidates).toHaveLength(1);
    expect(s!.rationale).toContain("stoics");
    // PURE: shaping a suggestion does not emit anything.
    expect(postTypedEventMock).not.toHaveBeenCalled();
  });

  it("surfaces >1 candidate on a multi-project match (rigor #3 d)", () => {
    const s = suggestFiling({
      matches: [match({ investigation_id: "inv-a" }), match({ investigation_id: "inv-b" })],
    });
    expect(s!.candidates).toHaveLength(2);
    // The rationale acknowledges there's more than one — the surface lets the
    // user pick ONE; the mutator files into the single chosen project.
    expect(s!.rationale).toMatch(/other project/);
  });
});

describe("acceptFiling (explicit-accept-only mutator)", () => {
  it("emits exactly one filing event into the chosen project, through the funnel", async () => {
    postTypedEventMock.mockResolvedValue({ event_id: "ev-1", action_type: "document.filed_into_investigation" });
    const res = await acceptFiling({
      documentId: "doc-9",
      investigationId: "inv-target",
      matchScore: 0.66,
      question: "the chosen question",
    });
    expect(res.investigation_id).toBe("inv-target");
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    const envelope = postTypedEventMock.mock.calls[0][0];
    expect(envelope.investigation_id).toBe("inv-target");
    expect(envelope.document_id).toBe("doc-9");
    expect(envelope.payload.action_type).toBe("document.filed_into_investigation");
    expect(envelope.payload.filed_document_id).toBe("doc-9");
    expect(envelope.payload.target_investigation_id).toBe("inv-target");
    expect(envelope.payload.match_score).toBe(0.66);
  });

  it("files into ONE project even when several matched (no double-file)", async () => {
    postTypedEventMock.mockResolvedValue({ event_id: "ev", action_type: "x" });
    // The caller passes the single chosen match — the mutator never iterates
    // over all candidates.
    await acceptFiling({
      documentId: "doc-1",
      investigationId: "inv-b",
      matchScore: 0.7,
      question: "q",
    });
    expect(postTypedEventMock).toHaveBeenCalledTimes(1);
    expect(postTypedEventMock.mock.calls[0][0].payload.target_investigation_id).toBe("inv-b");
  });
});
