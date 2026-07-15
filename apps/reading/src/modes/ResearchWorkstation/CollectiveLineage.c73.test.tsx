import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import type {
  Event,
  ResearchCompositionProvenance,
} from "../../generated/types";
import CollectiveLineage, { collectiveProvenance } from "./CollectiveLineage";

const A64 = "a".repeat(64);
const B64 = "b".repeat(64);

function provenance(): ResearchCompositionProvenance {
  return {
    composition_id: `cmp-${A64}`,
    ordered_set_digest: A64,
    composition_schema_version: 1,
    member_count: 2,
    members: [
      {
        investigation_id: "inv-b",
        content_hash: A64,
        rendered_sha256: B64,
        ordinal: 0,
      },
      {
        investigation_id: "inv-a",
        content_hash: B64,
        rendered_sha256: A64,
        ordinal: 1,
      },
    ],
  };
}

function start(
  researchComposition: ResearchCompositionProvenance | null = provenance(),
): Event {
  return {
    event_id: "evt-start",
    investigation_id: "inv-collective",
    action_type: "investigation.start_requested",
    payload: {
      action_type: "investigation.start_requested",
      question: "What connects these findings?",
      research_composition: researchComposition,
    },
    param_version: "0.2.0",
    schema_version: 37,
    emitted_at: "2026-07-16T00:00:00Z",
  };
}

describe("Cycle 73 collective lineage", () => {
  afterEach(cleanup);

  it("preserves authoritative member order and renders canonical navigation", () => {
    render(
      <MemoryRouter>
        <CollectiveLineage
          events={[start()]}
          investigationId="inv-collective"
        />
      </MemoryRouter>,
    );
    expect(screen.getByText("Collective sources")).toBeDefined();
    const members = screen
      .getAllByRole("link")
      .filter((link) => link.textContent?.match(/^\d/));
    expect(members.map((link) => link.textContent)).toEqual([
      "1. inv-b",
      "2. inv-a",
    ]);
    expect(members.map((link) => link.getAttribute("href"))).toEqual([
      "/inv/inv-b",
      "/inv/inv-a",
    ]);
    const html = screen.getByRole("link", { name: /Combined HTML/ });
    expect(html.getAttribute("href")).toContain(
      `/research/artifacts/compositions/cmp-${A64}`,
    );
    expect(html.getAttribute("target")).toBe("_blank");
    expect(html.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("rejects duplicate starts, malformed order, count mismatch, and duplicate members", () => {
    expect(
      collectiveProvenance(
        [start(), { ...start(), event_id: "evt-duplicate" }],
        "inv-collective",
      ),
    ).toBeNull();
    const malformed = provenance();
    malformed.members[1] = { ...malformed.members[1], ordinal: 0 };
    expect(
      collectiveProvenance([start(malformed)], "inv-collective"),
    ).toBeNull();
    const countMismatch = provenance();
    countMismatch.member_count = 3;
    expect(
      collectiveProvenance([start(countMismatch)], "inv-collective"),
    ).toBeNull();
    const duplicate = provenance();
    duplicate.members[1] = {
      ...duplicate.members[1],
      investigation_id: "inv-b",
    };
    expect(
      collectiveProvenance([start(duplicate)], "inv-collective"),
    ).toBeNull();
  });

  it("rejects malformed runtime frames, cross-investigation envelopes, and conflicting provenance", () => {
    const malformed = { ...start(), payload: null } as unknown as Event;
    expect(collectiveProvenance([malformed], "inv-collective")).toBeNull();
    const nullMembers = start();
    (
      nullMembers.payload as unknown as Record<string, unknown>
    ).research_composition = {
      ...provenance(),
      members: null,
    };
    expect(collectiveProvenance([nullMembers], "inv-collective")).toBeNull();
    expect(collectiveProvenance([start()], "inv-other")).toBeNull();
    const conflicting = start();
    (
      conflicting.payload as unknown as Record<string, unknown>
    ).evidence_manifest = {};
    expect(collectiveProvenance([conflicting], "inv-collective")).toBeNull();
    const mismatchedDigest = provenance();
    mismatchedDigest.ordered_set_digest = B64;
    expect(
      collectiveProvenance([start(mismatchedDigest)], "inv-collective"),
    ).toBeNull();
    const malformedSources = start();
    (
      malformedSources.payload as unknown as Record<string, unknown>
    ).derived_sources = "not-an-array";
    expect(
      collectiveProvenance([malformedSources], "inv-collective"),
    ).toBeNull();
  });

  it("renders nothing for ordinary investigations", () => {
    const { container } = render(
      <MemoryRouter>
        <CollectiveLineage
          events={[start(null)]}
          investigationId="inv-collective"
        />
      </MemoryRouter>,
    );
    expect(container.innerHTML).toBe("");
  });
});
