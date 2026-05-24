/**
 * Vitest coverage for the research-bridge frontend kit + page.
 * A single StubClient simulates the substrate without network.
 */

import { afterEach, beforeEach, describe, it, expect, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { BlockShelf } from "./BlockShelf";
import { GapFinderPage } from "./GapFinderPage";
import { PromptCard } from "./PromptCard";
import { ResearchBlock } from "./ResearchBlock";
import { usePastes } from "./hooks";
import { MOCK_BLOCKS } from "./mock_blocks";
import {
  DRAG_MIME, DRAG_TEXT_MIME, beginBlockDrag, dragHasBlock, readBlockDrop,
} from "./drag";
import type { FindGapsResponse, GapPromptPayload, ResearchBridgeClient } from "./api_client";

afterEach(() => { cleanup(); });


function makeClient(overrides: Partial<ResearchBridgeClient> = {}) {
  const calls = { findGaps: 0 };
  const signals: { prompt_id: string; signal_type: "would_run" | "skip" }[] = [];
  const pasted: { document_id: string; text: string }[] = [];
  const extracted: string[] = [];
  const answers: { prompt_id: string; answer_document_id: string }[] = [];
  let docSeq = 100;

  const defaultRun: FindGapsResponse = {
    run: {
      run_id: "rgrun-stubbed", operator_label: null, session_id: null,
      scope_block_ids: [], scope_question_ids: [],
      cluster_model_id: "fake/cluster",
      total_input_tokens: 100, total_output_tokens: 50, total_cost_usd: 0.003,
      created_at: "2026-05-24T18:00:00",
    },
    clusters: [{ cluster_id: "rgcl-aaa", label: "Verifier productisation timeline",
                 priority_rank: 0, rationale: null }],
    prompts: [{
      prompt_id: "rgpr-aaa", cluster_id: "rgcl-aaa", order_index: 0,
      prompt_text: "Investigate the verifier productisation timeline.",
      target_provider: "anthropic", expected_output_shape: null,
      depends_on_prior_order_index: null, rationale: null,
      input_tokens: 50, output_tokens: 20, cost_usd: 0.0015,
    }],
    grounding_drops: 0,
  };

  const client: ResearchBridgeClient = {
    async listPastes() { return { count: MOCK_BLOCKS.length, pastes: MOCK_BLOCKS }; },
    async postFindGaps(req) {
      calls.findGaps++;
      return { ...defaultRun, run: { ...defaultRun.run,
        scope_block_ids: req.scope_block_ids,
        operator_label: req.operator_label ?? null,
        session_id: req.session_id ?? null } };
    },
    async postSignal(promptId, signalType) {
      signals.push({ prompt_id: promptId, signal_type: signalType });
      return { signal_id: `rgs-${signals.length}` };
    },
    async postPaste(req) {
      const docId = `doc-stub-${docSeq++}`;
      pasted.push({ document_id: docId, text: req.raw_text });
      return { document_id: docId, source: req.source_override ?? "other",
        source_confidence: 0.9, raw_sha256: "sha-stub",
        paste_byte_length: req.raw_text.length, parser_version: 1,
        chunk_count: 1, per_source_scores: {} };
    },
    async postAnswer(promptId, answerDocumentId) {
      answers.push({ prompt_id: promptId, answer_document_id: answerDocumentId });
      return { answer_id: `rga-${answers.length}` };
    },
    async postExtract(documentId) {
      extracted.push(documentId);
      return { extraction_id: `rpex-${extracted.length}`, document_id: documentId,
        extractor_version: 1, model_id: "fake/extractor", status: "ok",
        insights: [], open_questions: [], quote_drops: 0,
        input_tokens: 100, output_tokens: 30, cost_usd: 0.001 };
    },
    async getGapRun(runId) { return { ...defaultRun, run: { ...defaultRun.run, run_id: runId } }; },
    async listItems(documentId) { return { document_id: documentId, insights: [], open_questions: [] }; },
    async getWouldRunPercentage() { return { would_run_count: 0, total_signalled: 0, percentage: 0, run_id: null }; },
    ...overrides,
  };
  return { client, signals, pasted, extracted, answers, calls };
}


describe("drag.ts", () => {
  function fakeDataTransfer() {
    const store: Record<string, string> = {};
    const types: string[] = [];
    return {
      setData(t: string, v: string) { if (!(t in store)) types.push(t); store[t] = v; },
      getData(t: string) { return store[t] ?? ""; },
      types,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any;
  }

  it("beginBlockDrag sets bespoke + text payloads", () => {
    const dt = fakeDataTransfer();
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    beginBlockDrag(event, { document_id: "doc-1", source: "anthropic" });
    expect(dt.getData(DRAG_MIME)).toContain("doc-1");
    expect(dt.getData(DRAG_TEXT_MIME)).toContain("doc-1");
  });

  it("readBlockDrop parses bespoke payload", () => {
    const dt = fakeDataTransfer();
    dt.setData(DRAG_MIME, JSON.stringify({ block_id: "doc-2", source: "grok" }));
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    expect(readBlockDrop(event)).toEqual({ block_id: "doc-2", source: "grok" });
  });

  it("readBlockDrop returns null for missing payload", () => {
    const dt = fakeDataTransfer();
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    expect(readBlockDrop(event)).toBeNull();
  });

  it("readBlockDrop returns null for malformed JSON", () => {
    const dt = fakeDataTransfer();
    dt.setData(DRAG_MIME, "not json");
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    expect(readBlockDrop(event)).toBeNull();
  });

  it("dragHasBlock recognises our MIME", () => {
    const dt = fakeDataTransfer();
    dt.setData(DRAG_MIME, JSON.stringify({ block_id: "x", source: "anthropic" }));
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    expect(dragHasBlock(event)).toBe(true);
  });

  it("dragHasBlock false for foreign drags", () => {
    const dt = fakeDataTransfer();
    dt.setData("text/html", "<p>hi</p>");
    const event = { dataTransfer: dt } as unknown as React.DragEvent<HTMLElement>;
    expect(dragHasBlock(event)).toBe(false);
  });
});


describe("ResearchBlock", () => {
  it("renders title at standard size", () => {
    render(<ResearchBlock block={MOCK_BLOCKS[0]} />);
    expect(screen.getByText(MOCK_BLOCKS[0].title as string)).toBeTruthy();
  });
  it("fires onActivate on Enter", () => {
    const onActivate = vi.fn();
    render(<ResearchBlock block={MOCK_BLOCKS[0]} onActivate={onActivate} />);
    fireEvent.keyDown(screen.getByRole("button"), { key: "Enter" });
    expect(onActivate).toHaveBeenCalledWith(MOCK_BLOCKS[0]);
  });
  it("fires onActivate on Space", () => {
    const onActivate = vi.fn();
    render(<ResearchBlock block={MOCK_BLOCKS[0]} onActivate={onActivate} />);
    fireEvent.keyDown(screen.getByRole("button"), { key: " " });
    expect(onActivate).toHaveBeenCalledTimes(1);
  });
});


describe("BlockShelf", () => {
  it("filters by source toggle chip", () => {
    render(<BlockShelf blocks={MOCK_BLOCKS} />);
    fireEvent.click(screen.getByRole("button", { name: "AlphaSense" }));
    expect(screen.getByText("1 of 5 blocks")).toBeTruthy();
  });
  it("filters by search", () => {
    render(<BlockShelf blocks={MOCK_BLOCKS} />);
    fireEvent.change(screen.getByLabelText("Search blocks"), { target: { value: "X-platform" } });
    expect(screen.getByText("1 of 5 blocks")).toBeTruthy();
  });
  it("multiSelect fires onSelectionChange", () => {
    const onSelectionChange = vi.fn<(s: Set<string>) => void>();
    render(<BlockShelf blocks={MOCK_BLOCKS} multiSelect onSelectionChange={onSelectionChange} />);
    fireEvent.click(screen.getAllByRole("button", { name: /AlphaSense/i })[1]);
    expect(onSelectionChange).toHaveBeenCalled();
    expect(onSelectionChange.mock.calls.at(-1)![0].size).toBe(1);
  });
  it("shows empty-state", () => {
    render(<BlockShelf blocks={MOCK_BLOCKS} />);
    fireEvent.change(screen.getByLabelText("Search blocks"), { target: { value: "zzzzzz" } });
    expect(screen.getByText(/No pastes match/i)).toBeTruthy();
  });
});


describe("PromptCard", () => {
  function basePrompt(): GapPromptPayload {
    return {
      prompt_id: "rgpr-test", cluster_id: "rgcl-test", order_index: 0,
      prompt_text: "Investigate verifier productisation timeline.",
      target_provider: "anthropic", expected_output_shape: "list of dates",
      depends_on_prior_order_index: null, rationale: "Anthropic relevant.",
      input_tokens: 50, output_tokens: 20, cost_usd: 0.0015,
    };
  }
  it("collapsed shows Expand + Copy", () => {
    render(<PromptCard prompt={basePrompt()} onSignal={vi.fn()} onPasteBack={vi.fn() as never} />);
    expect(screen.getByRole("button", { name: "Expand" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Copy prompt" })).toBeTruthy();
  });
  it("expanding reveals paste-back", () => {
    render(<PromptCard prompt={basePrompt()} onSignal={vi.fn()} onPasteBack={vi.fn() as never} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    expect(screen.getByRole("button", { name: "Paste answer back" })).toBeTruthy();
  });
  it("👍 calls onSignal would_run", async () => {
    const onSignal = vi.fn().mockResolvedValue(undefined);
    render(<PromptCard prompt={basePrompt()} onSignal={onSignal} onPasteBack={vi.fn() as never} />);
    fireEvent.click(screen.getByRole("button", { name: /would run/i }));
    await waitFor(() => expect(onSignal).toHaveBeenCalledWith("rgpr-test", "would_run"));
  });
  it("paste-back submits + transitions to answered", async () => {
    const onPasteBack = vi.fn().mockResolvedValue({
      document_id: "doc-back-1", insights_count: 2, open_questions_count: 1, was_new: true,
    });
    render(<PromptCard prompt={basePrompt()} onSignal={vi.fn()} onPasteBack={onPasteBack} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    fireEvent.click(screen.getByRole("button", { name: "Paste answer back" }));
    fireEvent.change(screen.getByLabelText("Paste-back textarea"), { target: { value: "Some answer text" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
    await waitFor(() => expect(screen.getByText("Answer recorded.")).toBeTruthy());
    expect(onPasteBack).toHaveBeenCalledWith(
      expect.objectContaining({ prompt_id: "rgpr-test" }), "Some answer text",
    );
  });
  it("rejects empty paste-back", () => {
    const onPasteBack = vi.fn();
    render(<PromptCard prompt={basePrompt()} onSignal={vi.fn()} onPasteBack={onPasteBack} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    fireEvent.click(screen.getByRole("button", { name: "Paste answer back" }));
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
    expect(onPasteBack).not.toHaveBeenCalled();
    expect(screen.getByText(/Paste the answer text/i)).toBeTruthy();
  });
  it("surfaces inline error on paste-back rejection", async () => {
    const onPasteBack = vi.fn().mockRejectedValue(new Error("503 from server"));
    render(<PromptCard prompt={basePrompt()} onSignal={vi.fn()} onPasteBack={onPasteBack} />);
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    fireEvent.click(screen.getByRole("button", { name: "Paste answer back" }));
    fireEvent.change(screen.getByLabelText("Paste-back textarea"), { target: { value: "some answer" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
    await waitFor(() => expect(screen.getByText("503 from server")).toBeTruthy());
  });
});


describe("GapFinderPage", () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  });

  it("renders idle initially", async () => {
    const { client } = makeClient();
    render(<GapFinderPage client={client} />);
    await waitFor(() => expect(screen.getByText(/No gap-finder run yet/i)).toBeTruthy());
  });

  it("scope picker → find gaps → viewing", async () => {
    const stub = makeClient();
    render(<GapFinderPage client={stub.client}
      initialScope={[MOCK_BLOCKS[0].document_id, MOCK_BLOCKS[1].document_id]} />);
    await waitFor(() => expect(screen.getByText("2 selected")).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Find gaps" }));
    await waitFor(() => expect(screen.getByText("Verifier productisation timeline")).toBeTruthy());
    expect(stub.calls.findGaps).toBe(1);
  });

  it("disables Find Gaps when scope empty", async () => {
    const { client } = makeClient();
    render(<GapFinderPage client={client} />);
    await waitFor(() => expect(screen.getByText("0 selected")).toBeTruthy());
    expect((screen.getByRole("button", { name: "Find gaps" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("paste-back closes the loop", async () => {
    const stub = makeClient();
    render(<GapFinderPage client={stub.client}
      initialScope={[MOCK_BLOCKS[0].document_id, MOCK_BLOCKS[1].document_id]} />);
    await waitFor(() => screen.getByText("2 selected"));
    fireEvent.click(screen.getByRole("button", { name: "Find gaps" }));
    await waitFor(() => screen.getByText("Verifier productisation timeline"));
    fireEvent.click(screen.getByRole("button", { name: "Expand" }));
    fireEvent.click(screen.getByRole("button", { name: "Paste answer back" }));
    fireEvent.change(screen.getByLabelText("Paste-back textarea"),
      { target: { value: "Anthropic released VerifyKit on 2025-01-15." } });
    fireEvent.click(screen.getByRole("button", { name: "Submit answer" }));
    await waitFor(() => screen.getByText("Answer recorded."));
    expect(stub.pasted).toHaveLength(1);
    expect(stub.answers).toHaveLength(1);
    expect(stub.answers[0].prompt_id).toBe("rgpr-aaa");
    expect(stub.extracted).toHaveLength(1);
  });

  it("re-find-gaps reuses prior scope", async () => {
    const stub = makeClient();
    render(<GapFinderPage client={stub.client} initialScope={[MOCK_BLOCKS[0].document_id]} />);
    await waitFor(() => screen.getByText("1 selected"));
    fireEvent.click(screen.getByRole("button", { name: "Find gaps" }));
    await waitFor(() => screen.getByText("Verifier productisation timeline"));
    fireEvent.click(screen.getByRole("button", { name: /Re-find gaps/i }));
    await waitFor(() => expect(stub.calls.findGaps).toBe(2));
  });

  it("surfaces find-gaps error + retry", async () => {
    const stub = makeClient({
      async postFindGaps(): Promise<FindGapsResponse> { throw new Error("502 cascade LLM failed"); },
    });
    render(<GapFinderPage client={stub.client} initialScope={[MOCK_BLOCKS[0].document_id]} />);
    await waitFor(() => screen.getByText("1 selected"));
    fireEvent.click(screen.getByRole("button", { name: "Find gaps" }));
    await waitFor(() => screen.getByText(/502 cascade LLM failed/i));
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("rolls back optimistic signal on server error", async () => {
    const stub = makeClient({
      async postSignal(): Promise<{ signal_id: string }> { throw new Error("forbidden"); },
    });
    render(<GapFinderPage client={stub.client} initialScope={[MOCK_BLOCKS[0].document_id]} />);
    await waitFor(() => screen.getByText("1 selected"));
    fireEvent.click(screen.getByRole("button", { name: "Find gaps" }));
    await waitFor(() => screen.getByText("Verifier productisation timeline"));
    fireEvent.click(screen.getByRole("button", { name: /would run/i }));
    await waitFor(() => expect(screen.getByText(/Signal save failed/i)).toBeTruthy());
  });
});


describe("usePastes hook", () => {
  function PastesConsumer({ client }: { client: ResearchBridgeClient }) {
    const { state } = usePastes({ client });
    return <div data-testid="state">{state.kind}</div>;
  }
  it("transitions loading → ok on mount", async () => {
    const stub = makeClient();
    render(<PastesConsumer client={stub.client} />);
    expect(screen.getByTestId("state").textContent).toBe("loading");
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("ok"));
  });
  it("transitions to error when listPastes rejects", async () => {
    const stub = makeClient({
      async listPastes() { throw new Error("substrate offline"); },
    });
    render(<PastesConsumer client={stub.client} />);
    await waitFor(() => expect(screen.getByTestId("state").textContent).toBe("error"));
  });
});
