import { cleanup, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import DerivedRevisionCompanion from "./DerivedRevisionCompanion";

const mocks = vi.hoisted(() => ({ conversation: vi.fn(), prepare: vi.fn() }));
vi.mock("../../api/research", async (importOriginal) => {
  const original = await importOriginal<typeof import("../../api/research")>();
  return {
    ...original,
    getDerivedCompanionConversation: (...args: unknown[]) => mocks.conversation(...args),
    prepareDerivedCompanionEvidence: (...args: unknown[]) => mocks.prepare(...args),
  };
});

const model = {
  derived_asset_id: `ast_${"a".repeat(32)}`,
  title: "Aircraft engines",
  asset_kind: "analysis" as const,
  revision_id: `rev_${"b".repeat(32)}`,
  content_sha256: "c".repeat(64),
  generation: 4,
  member_count: 1,
  is_current: true,
  canonical_html: "<p>Evidence</p>",
  stable_reader_path: "/read/derived/current",
  exact_reader_path: "/read/derived/exact",
};

const execution = {
  schema_version: "antiek.derived-companion-execution.v1" as const,
  scope: {
    derived_asset_id: model.derived_asset_id,
    revision_id: model.revision_id,
    content_sha256: model.content_sha256,
    generation: model.generation,
  },
  available: false as const,
  reservable: false as const,
  dispatch_authorized: false as const,
  reason: "no_provider_route_qualified" as const,
  pricing_status: "unavailable" as const,
  recommended_ceiling_cents: null,
  routes: ["exa", "openai", "perplexity", "tavily"].map((provider) => ({
    provider,
    model: "research",
    operation: "answer",
    checked_at: "2026-07-15",
    verdict: "refused" as const,
    blocking_dimensions: ["authoritative_reconciliation" as const],
  })),
};

describe("Cycle 61 companion execution qualification", () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it("renders checked refusal truth without an approval or answer control", async () => {
    mocks.conversation.mockResolvedValue({
      scope: { ...execution.scope, is_current: true, exact_reader_path: model.exact_reader_path },
      execution,
      turns: [],
    });
    render(<DerivedRevisionCompanion
      model={model}
      articleRef={createRef<HTMLElement>()}
      onFollowCitation={vi.fn()}
    />);
    expect(screen.getByText("Checking route evidence")).toBeTruthy();
    expect(screen.queryByText(/0 routes checked/)).toBeNull();
    expect(await screen.findByText("4 routes checked · none qualified")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /answer/i })).toBeNull();
    expect(screen.getByRole("button", { name: /find evidence/i })).toBeTruthy();
  });

  it("does not claim a route check when conversation loading fails", async () => {
    mocks.conversation.mockRejectedValue(new Error("offline"));
    render(<DerivedRevisionCompanion
      model={model}
      articleRef={createRef<HTMLElement>()}
      onFollowCitation={vi.fn()}
    />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByText("Checking route evidence")).toBeTruthy();
    expect(screen.queryByText(/routes checked/)).toBeNull();
  });

  it("renders only admitted structured claims and marks unsupported claims", async () => {
    const citation = {
      citation_id: `dchunk_${"d".repeat(64)}`,
      chunk_ordinal: 0,
      member_index: 0,
      section_anchor: "engines",
      section_path: "Engines",
      text: "A grounded passage.",
      text_sha256: "e".repeat(64),
    };
    mocks.conversation.mockResolvedValue({
      scope: { ...execution.scope, is_current: true, exact_reader_path: model.exact_reader_path },
      execution,
      turns: [{
        client_turn_id: "reader-turn-0001",
        question: "What changed?",
        state: "evidence_ready",
        failure_code: null,
        evidence_pack: { pack_sha256: "f".repeat(64), citations: [citation] },
        answer: {
          schema_version: "antiek.derived-companion-answer.v1",
          answer_id: `dans_${"1".repeat(64)}`,
          evidence_pack_sha256: "f".repeat(64),
          provider: "verified-provider",
          model: "grounded-model",
          claims: [
            { claim_id: "claim-1", ordinal: 0, text: "Grounded conclusion.", citation_ids: [citation.citation_id], supported: true },
            { claim_id: "claim-2", ordinal: 1, text: "Open hypothesis.", citation_ids: [], supported: false },
          ],
          cited_citation_ids: [citation.citation_id],
          unsupported_claim_count: 1,
          answer_html: "<script>must not be injected</script>",
          answer_html_sha256: "2".repeat(64),
          artifact_sha256: "3".repeat(64),
        },
      }],
    });
    const { container } = render(<DerivedRevisionCompanion
      model={model}
      articleRef={createRef<HTMLElement>()}
      onFollowCitation={vi.fn()}
    />);
    expect(await screen.findByText("Grounded conclusion.")).toBeTruthy();
    expect(screen.getByText("Open hypothesis.")).toBeTruthy();
    expect(screen.getByText("Unsupported by this evidence pack")).toBeTruthy();
    expect(screen.getByRole("button", { name: "[1] Engines" })).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.queryByRole("button", { name: /generate answer/i })).toBeNull();
  });
});
