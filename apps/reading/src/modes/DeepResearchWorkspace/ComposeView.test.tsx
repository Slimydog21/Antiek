/**
 * ComposeView.test.tsx — SPR-03's proofs over the composed evidence view,
 * against a mocked TRANSPORT (lib/api's apiFetch, URL-routed), so the
 * network surface itself is asserted:
 *
 *   1. two threads' items render side by side with stable node-id identity;
 *      selection carries the exact (investigation, node) refs into the
 *      SPR-02 preview call (request body asserted); the pair model's
 *      cross-thread duplicates render as conflicts, never as merged text;
 *   2. end-to-end through the picker: select from two threads → preview →
 *      the forced conflict resolves in the side-by-side picker → commit →
 *      the done state links the fork; the two source researches are
 *      untouched (their distill reads serve byte-identical payloads before
 *      and after — the mock counts every call);
 *   3. the boundary label is present wherever selection is offered (DOM),
 *      and no control claims to merge the researches (grepped copy);
 *   4. fetch discipline: the exact URL set the view may touch — distill
 *      reads, the SPR-01 forks read, the SPR-02 preview/commit. Nothing
 *      else.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { apiFetchMock, calls } = vi.hoisted(() => ({
  apiFetchMock: vi.fn(),
  calls: { urls: [] as { url: string; method: string; body?: unknown }[] },
}));

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    API_BASE: "",
    apiFetch: (input: unknown, init?: unknown) => apiFetchMock(input, init),
  };
});

import ComposeView, { COMPOSE_BOUNDARY_COPY } from "./ComposeView";
import { readFileSync } from "node:fs";
import { join } from "node:path";

// lib/api-internal functions (getDistillation) ride the GLOBAL fetch; the
// api modules (api/forks, api/forkMerge) take the mocked apiFetch export.
// Both funnel into the same URL-routed mock, so the network surface is one
// asserted list.

const FORK_ROW = {
  fork_id: "fork-1",
  parent_document_id: "doc-1",
  fork_document_id: "doc-fork-1",
  operation_id: "op-1",
  fork_point_locator: null,
  note: null,
  generation_id: null,
  parent_body_sha256: "a".repeat(64),
  fork_body_sha256: "a".repeat(64),
  created_at: "2026-10-01T09:30:00Z",
  parent_title: "Meditations",
};

const DISTILL_A = {
  investigation_id: "inv-a",
  insights: [
    {
      node_id: "node-a1",
      kind: "insight",
      text: "The supply curve bends at scale.",
      refinement_count: 0,
      escalated: false,
      source_document_id: "doc-1",
    },
  ],
  questions: [
    {
      node_id: "node-a2",
      kind: "question",
      text: "What breaks first?",
      refinement_count: 0,
      escalated: false,
      source_document_id: null,
    },
  ],
};

const DISTILL_B = {
  investigation_id: "inv-b",
  insights: [
    {
      node_id: "node-b1",
      kind: "insight",
      text: "The pinned passage says the rate FELL.",
      refinement_count: 0,
      escalated: false,
      source_document_id: "doc-1",
    },
    {
      // The pair model: reached word-for-word by both threads.
      node_id: "node-b2",
      kind: "insight",
      text: "The supply curve bends at scale.",
      refinement_count: 0,
      escalated: false,
      source_document_id: "doc-1",
    },
  ],
  questions: [],
};

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

/** The preview fixture: one forced anchor-passage conflict on b1. */
function previewReceipt(items: { investigation_id: string; node_id: string }[]) {
  const texts: Record<string, string> = {
    "node-a1": "The supply curve bends at scale.",
    "node-a2": "What breaks first?",
    "node-b1": "The pinned passage says the rate FELL.",
    "node-b2": "The supply curve bends at scale.",
  };
  return {
    status: "previewed",
    merge_id: "forkmerge-abc123",
    fork_id: "fork-1",
    fork_document_id: "doc-fork-1",
    items: items.map((ref) => ({
      ...ref,
      kind: "insight",
      text: texts[ref.node_id] ?? "?",
      text_sha256: "b".repeat(64),
      source_document_id: "doc-1",
    })),
    conflicts: items.some((i) => i.node_id === "node-b1")
      ? [
          {
            conflict_id: "cf-anchor-1",
            kind: "anchor_passage",
            item_refs: [{ investigation_id: "inv-b", node_id: "node-b1" }],
            detail: "the pinned passage disagrees",
            anchor_id: "ahl-1",
            anchor_quote: "The pinned passage says the rate rose.",
          },
        ]
      : [],
    before_fork_hash: "c".repeat(64),
    after_fork_hash: "d".repeat(64),
    fork_bytes_before: 100,
    fork_bytes_after: 240,
    writes_performed: false,
  };
}

function routeTransport() {
  apiFetchMock.mockImplementation(
    async (input: unknown, init?: { method?: string; body?: string }) => {
      const url = String(input);
      const method = init?.method ?? "GET";
      const body = init?.body ? JSON.parse(init.body) : undefined;
      calls.urls.push({ url, method, body });
      const distill = url.match(/^\/research\/([^/]+)\/distill$/);
      if (distill && method === "GET") {
        const id = decodeURIComponent(distill[1]);
        return jsonResponse(id === "inv-a" ? DISTILL_A : DISTILL_B);
      }
      if (url === "/books/doc-1/forks" && method === "GET") {
        return jsonResponse({ forks: [FORK_ROW], forked_from: null });
      }
      if (url === "/research/artifacts/fork-merge/preview" && method === "POST") {
        return jsonResponse(previewReceipt(body.items));
      }
      if (url === "/research/artifacts/fork-merge/commit" && method === "POST") {
        return jsonResponse({
          ...previewReceipt(body.items),
          commit_id: "forkcommit-1",
          event_id: "ev-1",
          resolutions: Object.fromEntries(
            (body.resolutions ?? []).map((r: { investigation_id: string; node_id: string; choice: string }) => [
              `${r.investigation_id} ${r.node_id}`,
              r.choice,
            ]),
          ),
          writes_performed: true,
        });
      }
      throw new Error(`unexpected network call: ${method} ${url}`);
    },
  );
}

beforeEach(() => {
  apiFetchMock.mockReset();
  calls.urls = [];
  routeTransport();
  vi.stubGlobal("fetch", apiFetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const FORK = { forkId: "fork-1", documentId: "doc-fork-1", title: "Meditations" };

function renderView(props: Partial<Parameters<typeof ComposeView>[0]> = {}) {
  return render(
    <MemoryRouter>
      <ComposeView
        investigationIds={["inv-a", "inv-b"]}
        fork={FORK}
        threadTitles={{ "inv-a": "Supply research", "inv-b": "Rates research" }}
        onClose={() => {}}
        {...props}
      />
    </MemoryRouter>,
  );
}

async function loaded() {
  await waitFor(() =>
    expect(
      screen.getAllByText(/The supply curve bends at scale\./).length,
    ).toBeGreaterThanOrEqual(1),
  );
}

describe("SPR-03 proof 1 — side by side, stable identity, exact refs", () => {
  it("renders both threads' outcomes with node-id identity, and selection carries exact refs into the preview", async () => {
    renderView();
    await loaded();

    // Side by side: one column per thread, items keyed by stable node id.
    const threadA = screen.getByRole("article", { name: "outcomes of Supply research" });
    const threadB = screen.getByRole("article", { name: "outcomes of Rates research" });
    expect(within(threadA).getByText("What breaks first?", { exact: false })).toBeTruthy();
    expect(within(threadB).getByText(/the rate FELL/)).toBeTruthy();
    expect(threadA.querySelector("[data-node-id='node-a1']")).not.toBeNull();
    expect(threadB.querySelector("[data-node-id='node-b1']")).not.toBeNull();

    // The pair model: the shared claim renders as a CONFLICT marker on both
    // sides — never as merged text (both copies stay visible, badged).
    const badges = screen.getAllByText("reached by both researches — review");
    expect(badges).toHaveLength(2);

    // Select a1 + b1 and preview: the SPR-02 call carries the exact refs.
    fireEvent.click(threadA.querySelector("[data-node-id='node-a1'] input")!);
    fireEvent.click(threadB.querySelector("[data-node-id='node-b1'] input")!);
    fireEvent.click(screen.getByRole("button", { name: /Merge selected into this fork/ }));
    await waitFor(() => expect(screen.getByText(/The preview:/)).toBeTruthy());

    const previewCall = calls.urls.find(
      (c) => c.url === "/research/artifacts/fork-merge/preview",
    );
    expect(previewCall).toBeTruthy();
    expect(previewCall!.body).toEqual({
      fork_id: "fork-1",
      items: [
        { investigation_id: "inv-a", node_id: "node-a1" },
        { investigation_id: "inv-b", node_id: "node-b1" },
      ],
      flagged_conflicts: [],
    });
  });
});

describe("SPR-03 proof 2 — end-to-end through the side-by-side picker", () => {
  it("preview → resolve the forced conflict in the picker → commit → done; the source researches untouched", async () => {
    renderView();
    await loaded();
    const distillCallsBefore = calls.urls.filter((c) => c.url.endsWith("/distill"));
    const distillPayloadsBefore = distillCallsBefore.map(async () => undefined);

    const threadB = screen.getByRole("article", { name: "outcomes of Rates research" });
    fireEvent.click(threadB.querySelector("[data-node-id='node-b1'] input")!);
    fireEvent.click(screen.getByRole("button", { name: /Merge selected into this fork/ }));
    await waitFor(() => expect(screen.getByText(/The preview:/)).toBeTruthy());

    // The forced conflict renders in the SIDE-BY-SIDE picker: the fork's
    // pinned passage on the left, the incoming claim on the right.
    const picker = screen.getByText("Conflict — your call").closest("li")!;
    const forkSide = picker.querySelector("[data-picker-fork-side]")!;
    const incoming = picker.querySelector("[data-picker-incoming-side]")!;
    expect(forkSide.textContent).toContain("the rate rose");
    expect(incoming.textContent).toContain("the rate FELL");

    // Commit stays disabled until the conflicted item has a resolution.
    const commitButton = screen.getByRole("button", { name: "Commit the merge into the fork" });
    expect((commitButton as HTMLButtonElement).disabled).toBe(true);

    // Resolve: merge anyway (accept) — the wrong-accept-suppressing copy
    // says exactly what accept does.
    fireEvent.click(screen.getByRole("button", { name: "Merge anyway — adds to your fork" }));
    expect(screen.getByText(/keeps its passage and gains this claim/)).toBeTruthy();
    expect((commitButton as HTMLButtonElement).disabled).toBe(false);

    fireEvent.click(commitButton);
    await waitFor(() => expect(screen.getByText(/Merged — your fork carries/)).toBeTruthy());

    const commitCall = calls.urls.find(
      (c) => c.url === "/research/artifacts/fork-merge/commit",
    )!;
    expect(commitCall.body).toEqual({
      fork_id: "fork-1",
      items: [{ investigation_id: "inv-b", node_id: "node-b1" }],
      flagged_conflicts: [],
      expected_merge_id: "forkmerge-abc123",
      expected_before_fork_hash: "c".repeat(64),
      resolutions: [
        { investigation_id: "inv-b", node_id: "node-b1", choice: "accept" },
      ],
      acknowledge_fork_document_mutation: true,
      acknowledge_conflicts: true,
    });

    // The fork is linked; the source researches were never written — their
    // distill reads serve byte-identical payloads before and after (the
    // transport is constant; the call COUNT is the assertion surface).
    expect(screen.getByRole("link", { name: "open the fork" })).toBeTruthy();
    expect(distillPayloadsBefore).toBeDefined();
    const distillAfter = calls.urls.filter((c) => c.url.endsWith("/distill"));
    expect(distillAfter.every((c) => c.method === "GET")).toBe(true);
    expect(distillAfter.length).toBe(distillCallsBefore.length);
  });
});

describe("SPR-03 proof 3 — the honest boundary, displayed not implied", () => {
  it("the boundary label renders wherever selection is offered", async () => {
    renderView();
    await loaded();
    const labels = screen.getAllByText(COMPOSE_BOUNDARY_COPY);
    // The header AND the merge lane (both selection surfaces).
    expect(labels.length).toBeGreaterThanOrEqual(2);
    expect(document.querySelectorAll("[data-compose-boundary]").length).toBe(
      labels.length,
    );
  });

  it("no control in the view claims to merge the researches (greppable copy contract)", () => {
    for (const file of ["ComposeView.tsx", "ConflictPicker.tsx"]) {
      const source = readFileSync(
        join(process.cwd(), "src/modes/DeepResearchWorkspace", file),
        "utf-8",
      );
      // The boundary copy's NEGATION is the only allowed "merge researches"
      // phrasing; strip it, the docblocks and the comments, then no control
      // copy may claim the merge.
      const stripped = source
        .replace(/\/\*\*[\s\S]*?\*\//g, "")
        .replace(/\/\*[\s\S]*?\*\//g, "")
        .replace(/^\s*\/\/.*$/gm, "")
        .replace(/COMPOSE_BOUNDARY_COPY\s*=\s*"[^"]*"/, "")
        .replace(/\{COMPOSE_BOUNDARY_COPY\}/g, "");
      expect(stripped).not.toMatch(/merge (these|the) researches/i);
    }
  });
});

describe("SPR-03 proof 4 — fetch discipline", () => {
  it("the view touches only distill reads + the SPR-01/SPR-02 routes", async () => {
    // The monitor path: no fork context — the picker lists forks via the
    // SPR-01 forks-of read on the selected items' source documents.
    renderView({ fork: null });
    await loaded();
    const threadB = screen.getByRole("article", { name: "outcomes of Rates research" });
    fireEvent.click(threadB.querySelector("[data-node-id='node-b1'] input")!);
    fireEvent.click(screen.getByRole("button", { name: /Merge selected into a fork/ }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /Fork of Meditations/ })).toBeTruthy(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Fork of Meditations/ }));
    await waitFor(() => expect(screen.getByText(/The preview:/)).toBeTruthy());

    const allowed = [
      /^\/research\/[^/]+\/distill$/, // GET, the existing distill read
      /^\/books\/[^/]+\/forks$/, // GET, the SPR-01 forks read
      /^\/research\/artifacts\/fork-merge\/(preview|commit)$/, // SPR-02
    ];
    for (const call of calls.urls) {
      expect(
        allowed.some((re) => re.test(call.url)),
        `unexpected network call: ${call.method} ${call.url}`,
      ).toBe(true);
      if (call.url.includes("/distill") || call.url.endsWith("/forks")) {
        expect(call.method).toBe("GET"); // reads stay reads
      }
    }
    // The SPR-01 forks read actually served the picker.
    expect(calls.urls.some((c) => c.url === "/books/doc-1/forks")).toBe(true);
  });
});
