/**
 * TalkToBook.test.tsx — Read SPR-08 M2 (+ M3 wiring).
 *
 * The floating bookmark's MULTI-TURN conversation: answers cite pages, a
 * citation click JUMPS the reader to that page, the conversation CONTINUES
 * (multi-turn) and BRANCHES, and it PERSISTS across a re-mount (the bookmark
 * carries it via sessionStorage — the usePosition precedent). An unresolved
 * page is shown honestly, never a fabricated page. The answer mounts a read-
 * aloud control (M3 wiring).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import {
  BookModelOperationNotFoundError,
  DeepBookOperationPendingError,
  SelectedBookModelUnavailableError,
} from "../../api/books";
import type { AskBookResponse, BookCitation } from "../../api/books";
import TalkToBook from "./TalkToBook";

const {
  askBookMock,
  askBookDeepMock,
  judgeBookAnswerMock,
  fetchUserModelsMock,
  getBookModelOperationMock,
  reconcileBookModelOperationMock,
  cancelBookModelOperationMock,
  getPrimeOperationMock,
  reconcilePrimeOperationMock,
  cancelPrimeOperationMock,
  getDeepBookOperationMock,
} = vi.hoisted(() => ({
  askBookMock: vi.fn(),
  askBookDeepMock: vi.fn(),
  judgeBookAnswerMock: vi.fn(),
  fetchUserModelsMock: vi.fn(),
  getBookModelOperationMock: vi.fn(),
  reconcileBookModelOperationMock: vi.fn(),
  cancelBookModelOperationMock: vi.fn(),
  getPrimeOperationMock: vi.fn(),
  reconcilePrimeOperationMock: vi.fn(),
  cancelPrimeOperationMock: vi.fn(),
  getDeepBookOperationMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => {
  const actual = await orig<typeof import("../../api/books")>();
  return {
    ...actual,
    askBook: askBookMock,
    askBookDeep: askBookDeepMock,
    judgeBookAnswer: judgeBookAnswerMock,
    getBookModelOperation: getBookModelOperationMock,
    reconcileBookModelOperation: reconcileBookModelOperationMock,
    cancelBookModelOperation: cancelBookModelOperationMock,
    getPrimeOperation: getPrimeOperationMock,
    reconcilePrimeOperation: reconcilePrimeOperationMock,
    cancelPrimeOperation: cancelPrimeOperationMock,
    getDeepBookOperation: getDeepBookOperationMock,
  };
});

vi.mock("../../api/settingsModels", () => ({ fetchUserModels: fetchUserModelsMock }));

// Stub ReadAloud so the TTS network path isn't coupled into this test (the real
// control is covered by ReadAloud.test.tsx); we only assert it is MOUNTED with
// the answer text (M3 wiring).
vi.mock("../../components/voice/ReadAloud", () => ({
  default: ({ text, label }: { text: string; label?: string }) => (
    <button type="button" data-testid="read-aloud" data-text={text}>
      {label ?? "Read aloud"}
    </button>
  ),
}));

const cite = (over: Partial<BookCitation> = {}): BookCitation => ({
  chunk_id: "c1",
  document_id: "doc-x",
  page_index: 6,
  page_resolved: true,
  snippet: "the cited passage",
  ...over,
});

const eligibleModel = {
  id: "user-reconcile",
  provider_kind: "openai_compat" as const,
  model_id: "reconcile-model",
  display_name: "Reconcile model",
  base_url: null,
  enabled: true,
  key_present: true,
  registered: true,
  route_eligible: true,
};

function answer(over: Partial<AskBookResponse> = {}): AskBookResponse {
  return {
    answer_id: "evt-answer-1",
    capture_status: "captured",
    answer: "Page seven discusses entanglement.",
    citations: [cite()],
    grounded: true,
    context_chunk_count: 1,
    model_receipt: {
      authority: "legacy_tier",
      requested_provider_id: null,
      requested_model_id: null,
      actual_provider_id: "system-provider",
      actual_model_id: "system-model",
      authority_digest: null,
    },
    ...over,
  };
}

const primeReceipt = (state: "authorized" | "started" | "usage_observed" | "succeeded" | "failed" | "cancelled" | "unknown") => ({
  operation_id: "prime-op",
  state,
  held_micro_usd: state === "cancelled" ? 0 : 5_000_000,
  charged_micro_usd: state === "succeeded" ? 1_250_000 : 0,
  input_tokens: null,
  output_tokens: null,
  observed_cost_micro_usd: null,
  provider_id: "prime",
  model_id: "p-1",
  prime_version: "1.2.3",
  updated_at_ms: 1,
});

beforeEach(() => {
  askBookMock.mockReset();
  askBookDeepMock.mockReset();
  judgeBookAnswerMock.mockReset();
  fetchUserModelsMock.mockReset();
  getBookModelOperationMock.mockReset();
  reconcileBookModelOperationMock.mockReset();
  cancelBookModelOperationMock.mockReset();
  getPrimeOperationMock.mockReset();
  reconcilePrimeOperationMock.mockReset();
  cancelPrimeOperationMock.mockReset();
  getDeepBookOperationMock.mockReset();
  getBookModelOperationMock.mockResolvedValue({ state: "unknown" });
  reconcileBookModelOperationMock.mockResolvedValue({ state: "unknown" });
  cancelBookModelOperationMock.mockResolvedValue({ state: "cancelled" });
  getPrimeOperationMock.mockResolvedValue({ state: "unknown" });
  reconcilePrimeOperationMock.mockResolvedValue({ state: "unknown" });
  cancelPrimeOperationMock.mockResolvedValue({ state: "cancelled" });
  getDeepBookOperationMock.mockResolvedValue({
    operation_id: "prime-op", state: "claimed", checkpoint_phase: null,
    lease_expires_at_ms: Date.now() + 60_000, resumable: false,
    created_at_ms: 1, updated_at_ms: 1,
  });
  fetchUserModelsMock.mockResolvedValue({ models: [], count: 0, stale_registered: [], source: "test" });
  judgeBookAnswerMock.mockResolvedValue({
    answer_id: "evt-answer-1",
    judgment_id: "evt-judgment-1",
    verdict: "good",
    note: null,
  });
  window.sessionStorage.clear();
});
afterEach(cleanup);

async function openAndAsk(
  jump = vi.fn(),
  question = "what is on page seven?",
  expectAnswer = "Page seven discusses entanglement.",
) {
  const utils = render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={jump} />);
  fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
  fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
    target: { value: question },
  });
  fireEvent.click(screen.getByRole("button", { name: "Ask" }));
  await screen.findByText(expectAnswer);
  return utils;
}

describe("TalkToBook (M2)", () => {
  async function startPrimeWithKeyboard(question: string) {
    const user = userEvent.setup();
    await user.click(screen.getByTestId("talk-to-book-bookmark"));
    await user.click(screen.getByRole("button", { name: "Use Deep mode" }));
    await user.click(screen.getByLabelText(/Add metered Prime/));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    const comboButton = screen.getByRole("combobox").querySelector("button") as HTMLButtonElement;
    comboButton.focus();
    await user.keyboard("{Enter}{ArrowDown}{Enter}");
    await user.click(screen.getByLabelText(/I approve this separate metered call/));
    await user.type(screen.getByRole("textbox", { name: "Question for this book" }), question);
    await user.keyboard("{Enter}");
    return user;
  }

  it.each(["authorized", "started", "usage_observed", "unknown"] as const)(
    "holds, polls, and blocks reset/new paid work for Prime %s",
    async (state) => {
      fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
      askBookDeepMock.mockResolvedValue(answer({ mode: "deep", prime_receipt: primeReceipt(state) }));
      getPrimeOperationMock.mockResolvedValue(primeReceipt(state));
      render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
      await startPrimeWithKeyboard(`state ${state}`);
      expect(await screen.findByText(/Prime is still unresolved/)).toBeTruthy();
      await waitFor(() => expect(getPrimeOperationMock).toHaveBeenCalled());
      expect(screen.getByText("clear").hasAttribute("disabled")).toBe(true);
      expect(screen.getByRole("button", { name: "Run Deep" }).hasAttribute("disabled")).toBe(true);
      const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
      expect(stored.branches[0].messages[0].operation_id).toMatch(/^talk-/);
      expect(stored.branches[0].messages[0].answer).toBeNull();
      expect(askBookDeepMock).toHaveBeenCalledTimes(1);
    },
  );

  it("reloads an unresolved paid turn and recovers the stored response without another provider call", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock.mockRejectedValue(new DeepBookOperationPendingError("prime_unresolved"));
    getPrimeOperationMock.mockResolvedValue(primeReceipt("unknown"));
    const first = render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    await startPrimeWithKeyboard("reload me");
    await screen.findByText(/Prime operation is unresolved/i);
    first.unmount();

    getPrimeOperationMock.mockResolvedValue(primeReceipt("succeeded"));
    getDeepBookOperationMock.mockResolvedValue({
      operation_id: "prime-op", state: "completed", checkpoint_phase: "canonical_complete",
      lease_expires_at_ms: null, resumable: false, created_at_ms: 1, updated_at_ms: 2,
      response: answer({ mode: "deep", prime_receipt: primeReceipt("succeeded") }),
    });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    await userEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(await screen.findByText("Page seven discusses entanglement.")).toBeTruthy();
    expect(askBookDeepMock).toHaveBeenCalledTimes(1);
    expect(getDeepBookOperationMock).toHaveBeenCalled();
  });

  it("waits for the real lease checkpoint before resuming with the exact persisted payload", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock
      .mockRejectedValueOnce(new DeepBookOperationPendingError("prime_unknown"))
      .mockResolvedValueOnce(answer({ mode: "deep", prime_receipt: primeReceipt("succeeded") }));
    getPrimeOperationMock.mockResolvedValue(primeReceipt("unknown"));
    reconcilePrimeOperationMock.mockResolvedValue(primeReceipt("succeeded"));
    getDeepBookOperationMock.mockResolvedValue({
      operation_id: "prime-op", state: "canonical_complete", checkpoint_phase: "canonical_complete",
      lease_expires_at_ms: Date.now() - 1, resumable: true, created_at_ms: 1, updated_at_ms: 2,
    });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    const user = await startPrimeWithKeyboard("exact replay");
    await screen.findByText(/Prime operation is unresolved/i);
    await user.click(screen.getByRole("button", { name: "Refresh reconciliation" }));
    expect(askBookDeepMock).toHaveBeenCalledTimes(1);
    await user.click(await screen.findByRole("button", { name: "Resume Deep safely" }));
    await screen.findByText("Page seven discusses entanglement.");
    expect(askBookDeepMock).toHaveBeenCalledTimes(2);
    expect(askBookDeepMock.mock.calls[1][1]).toBe(askBookDeepMock.mock.calls[0][1]);
    expect(askBookDeepMock.mock.calls[1][2]).toEqual(askBookDeepMock.mock.calls[0][2]);
  });

  it("never offers takeover for ambiguous Deep unknown without server approval", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock
      .mockRejectedValueOnce(new DeepBookOperationPendingError("deep_unknown"))
      .mockResolvedValueOnce(answer({ mode: "deep", prime_receipt: primeReceipt("succeeded") }));
    getPrimeOperationMock.mockResolvedValue(primeReceipt("unknown"));
    getDeepBookOperationMock.mockResolvedValue({
      operation_id: "prime-op", state: "unknown", checkpoint_phase: "canonical_complete",
      lease_expires_at_ms: null, resumable: false, created_at_ms: 1, updated_at_ms: 2, response: null,
    });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    await startPrimeWithKeyboard("unknown takeover");
    await waitFor(() => expect(getDeepBookOperationMock).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Resume Deep safely" })).toBeNull();
    expect(askBookDeepMock).toHaveBeenCalledTimes(1);
  });

  it("allows keyboard cancellation only for an authorized Prime hold", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock.mockRejectedValue(new DeepBookOperationPendingError("prime_unresolved"));
    getPrimeOperationMock.mockResolvedValue(primeReceipt("authorized"));
    cancelPrimeOperationMock.mockResolvedValue(primeReceipt("cancelled"));
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    const user = await startPrimeWithKeyboard("cancel me");
    const release = await screen.findByRole("button", { name: "Release reservation" });
    release.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.queryByText("cancel me")).toBeNull());
    expect(cancelPrimeOperationMock).toHaveBeenCalledTimes(1);
  });

  it("offers explicit Deep RLM while leaving ordinary Ask on the original request", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    expect(askBookMock).toHaveBeenCalledTimes(1);
    expect(askBookDeepMock).not.toHaveBeenCalled();

    cleanup();
    window.sessionStorage.clear();
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock.mockResolvedValue(answer({ mode: "deep" }));
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    fireEvent.click(screen.getByRole("button", { name: "Use Deep mode" }));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), { target: { value: "inspect deeply" } });
    fireEvent.click(screen.getByRole("button", { name: "Run Deep" }));
    await screen.findByText("Page seven discusses entanglement.");
    const deepOptions = askBookDeepMock.mock.calls[0][2];
    expect(deepOptions.history).toEqual([]);
    expect(deepOptions.operationId).toMatch(/^talk-/);
    expect(deepOptions.modelChoice).toEqual({
      authority: "user_model", provider_id: "user-reconcile", model_id: "reconcile-model",
    });
  });

  it("requires separate Prime consent and persists its stable paid-operation identity", async () => {
    fetchUserModelsMock.mockResolvedValue({ models: [eligibleModel], count: 1, stale_registered: [], source: "test" });
    askBookDeepMock.mockResolvedValue(answer({ mode: "deep", prime_receipt: {
      operation_id: "server-operation",
      state: "succeeded",
      held_micro_usd: 5_000_000,
      charged_micro_usd: 1_250_000,
      input_tokens: 100,
      output_tokens: 20,
      observed_cost_micro_usd: 1_250_000,
      provider_id: "prime",
      model_id: "p-1",
      updated_at_ms: 1,
    } }));
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    fireEvent.click(screen.getByRole("button", { name: "Use Deep mode" }));
    fireEvent.click(screen.getByLabelText(/Add metered Prime/));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), { target: { value: "prime evidence" } });
    expect(screen.getByRole("button", { name: "Run Deep" }).hasAttribute("disabled")).toBe(true);
    fireEvent.click(screen.getByLabelText(/I approve this separate metered call/));
    fireEvent.click(screen.getByRole("button", { name: "Run Deep" }));
    await screen.findByTestId("talk-prime-receipt");
    const prime = askBookDeepMock.mock.calls[0][2].prime;
    const canonicalOperation = askBookDeepMock.mock.calls[0][2].operationId;
    expect(prime.operationId).toMatch(/^prime-/);
    expect(canonicalOperation).toMatch(/^talk-/);
    expect(prime.operationId).not.toBe(canonicalOperation);
    expect(prime.maxCostMicroUsd).toBe(5_000_000);
    const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
    expect(stored.branches[0].messages[0].operation_id).toBe(canonicalOperation);
    expect(stored.branches[0].messages[0].deep_request.prime_operation_id).toBe(prime.operationId);
    expect(screen.getByTestId("talk-prime-receipt").textContent).toContain("supplemental evidence");
  });

  it("keeps the explicit deep-tier default and sends no model choice when untouched", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();

    expect(screen.getByText("Default · deep tier")).toBeTruthy();
    expect(askBookMock.mock.calls[0][2]).toEqual({ history: [], researchTier: "deep" });
    expect(screen.getByTestId("talk-model-receipt").textContent).toBe(
      "Used system-provider · system-model",
    );
  });

  it("requests only the selected owner model reference and shows the actual server receipt", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [{
        id: "user-provider-a",
        provider_kind: "openai_compat",
        model_id: "model-a",
        display_name: "My model",
        base_url: null,
        enabled: true,
        key_present: true,
        registered: true,
        route_eligible: true,
      }],
      count: 1,
      stale_registered: [],
      source: "test",
    });
    askBookMock.mockResolvedValue(answer({
      model_receipt: {
        authority: "owner_byot",
        requested_provider_id: "user-provider-a",
        requested_model_id: "model-a",
        actual_provider_id: "routed-provider",
        actual_model_id: "actual-model",
        authority_digest: "not-rendered",
      },
    }));

    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: "My model · model-a" }));
    fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), { target: { value: "question" } });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Page seven discusses entanglement.");

    expect(askBookMock.mock.calls[0][2].modelChoice).toEqual({
      authority: "user_model",
      provider_id: "user-provider-a",
      model_id: "model-a",
    });
    expect(askBookMock.mock.calls[0][2].operationId).toMatch(/^talk-/);
    const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
    expect(stored.branches[0].messages[0].operation_id).toBe(
      askBookMock.mock.calls[0][2].operationId,
    );
    expect(screen.getByTestId("talk-model-receipt").textContent).toBe(
      "Used routed-provider · actual-model",
    );
    expect(screen.queryByText(/not-rendered/)).toBeNull();
  });

  it("marks an ineligible inventory row unavailable and does not select it", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [{
        id: "user-stale",
        provider_kind: "anthropic",
        model_id: "old-model",
        display_name: "Old model",
        base_url: null,
        enabled: true,
        key_present: true,
        registered: true,
        route_eligible: false,
      }],
      count: 1,
      stale_registered: [],
      source: "test",
    });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    const option = await screen.findByRole("option", { name: "Old model · unavailable" });
    fireEvent.click(option);
    expect(screen.getAllByText("Default · deep tier").length).toBeGreaterThan(0);
    expect(screen.queryByText(/Requested:/)).toBeNull();
  });

  it("supports keyboard-only model selection and leaves focus on the question when opened", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [{
        id: "user-keyboard",
        provider_kind: "openai_compat",
        model_id: "keyboard-model",
        display_name: "Keyboard model",
        base_url: null,
        enabled: true,
        key_present: true,
        registered: true,
        route_eligible: true,
      }],
      count: 1,
      stale_registered: [],
      source: "test",
    });
    const user = userEvent.setup();
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    await user.click(screen.getByTestId("talk-to-book-bookmark"));
    const question = screen.getByRole("textbox", { name: "Question for this book" });
    expect(document.activeElement).toBe(question);
    await user.tab({ shift: true });
    await user.keyboard("{Enter}{ArrowDown}{Enter}");
    expect(await screen.findByText("Requested: Keyboard model · keyboard-model")).toBeTruthy();
  });

  it("invalidates a rejected selection, refreshes inventory, announces the error, and focuses recovery", async () => {
    const eligible = {
      id: "user-gone",
      provider_kind: "openai_compat",
      model_id: "gone-model",
      display_name: "Gone model",
      base_url: null,
      enabled: true,
      key_present: true,
      registered: true,
      route_eligible: true,
    };
    fetchUserModelsMock
      .mockResolvedValueOnce({ models: [eligible], count: 1, stale_registered: [], source: "test" })
      .mockResolvedValueOnce({ models: [], count: 0, stale_registered: [], source: "test" });
    askBookMock.mockRejectedValue(new SelectedBookModelUnavailableError());
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: "Gone model · gone-model" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));

    expect((await screen.findByRole("alert")).textContent).toContain("no longer available");
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("combobox").textContent).toContain("Default · deep tier");
    await waitFor(() => expect(document.activeElement).toBe(
      screen.getByRole("combobox").querySelector("button"),
    ));
  });

  it("keeps a lost-response operation through reload and blocks another selected dispatch", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [eligibleModel], count: 1, stale_registered: [], source: "test",
    });
    askBookMock.mockRejectedValue(new Error("network connection lost"));
    getBookModelOperationMock.mockResolvedValue({ state: "unknown" });
    const { unmount } = render(
      <TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />,
    );
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "lost question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(/provider outcome is not confirmed/i)).toBeTruthy();
    expect(screen.getByText("clear").hasAttribute("disabled")).toBe(true);
    const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
    expect(stored.branches[0].messages[0].operation_id).toMatch(/^talk-/);
    expect(stored.branches[0].messages[0].model_operation_state).toBe("unknown");
    unmount();

    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(await screen.findByText(/provider outcome is not confirmed/i)).toBeTruthy();
    await waitFor(() => expect(fetchUserModelsMock.mock.calls.length).toBeGreaterThan(1));
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "must not dispatch" },
    });
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(true);
    expect(askBookMock).toHaveBeenCalledTimes(1);
  });

  it("manually reconciles settlement without recalling the provider", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [eligibleModel], count: 1, stale_registered: [], source: "test",
    });
    askBookMock.mockRejectedValue(new Error("response lost after provider call"));
    getBookModelOperationMock.mockResolvedValue({ state: "settlement_pending" });
    reconcileBookModelOperationMock.mockResolvedValue({ state: "settled" });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "settlement question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/settlement is pending/i);
    fireEvent.click(screen.getByRole("button", { name: "Reconcile" }));
    expect(await screen.findByText(/operation settled, but its answer response was lost/i)).toBeTruthy();
    expect(reconcileBookModelOperationMock).toHaveBeenCalledTimes(1);
    expect(askBookMock).toHaveBeenCalledTimes(1);
  });

  it("releases a provably unsent prepared operation before allowing retry", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [eligibleModel], count: 1, stale_registered: [], source: "test",
    });
    askBookMock.mockRejectedValue(new Error("request status lost"));
    getBookModelOperationMock.mockResolvedValue({ state: "prepared" });
    cancelBookModelOperationMock.mockResolvedValue({ state: "cancelled" });
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "prepared question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(/reserved but not sent/i);
    fireEvent.click(screen.getByRole("button", { name: "Release reservation" }));
    await waitFor(() => expect(screen.queryByText(/reserved but not sent/i)).toBeNull());
    expect(cancelBookModelOperationMock).toHaveBeenCalledTimes(1);
    const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
    expect(stored.branches[0].messages).toEqual([]);
  });

  it("abandons a phantom operation only after repeated 404 checks and explicit confirmation", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [eligibleModel], count: 1, stale_registered: [], source: "test",
    });
    askBookMock.mockRejectedValueOnce(new TypeError("fetch failed before reaching server"));
    getBookModelOperationMock.mockRejectedValue(new BookModelOperationNotFoundError());
    let now = 1_700_000_000_000;
    const nowMock = vi.spyOn(Date, "now").mockImplementation(() => now);
    const confirmMock = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "never arrived" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(getBookModelOperationMock.mock.calls.length).toBeGreaterThanOrEqual(1));
    expect(screen.queryByRole("button", { name: "Abandon unsent request" })).toBeNull();
    now += 4_000;
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    const abandon = await screen.findByRole("button", { name: "Abandon unsent request" });
    fireEvent.click(abandon);
    expect(confirmMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("never arrived")).toBeTruthy();

    confirmMock.mockReturnValue(true);
    fireEvent.click(abandon);
    await waitFor(() => expect(screen.queryByText("never arrived")).toBeNull());
    expect(askBookMock).toHaveBeenCalledTimes(1);
    expect(getBookModelOperationMock.mock.calls.length).toBeGreaterThanOrEqual(2);
    expect(reconcileBookModelOperationMock).not.toHaveBeenCalled();
    expect(cancelBookModelOperationMock).not.toHaveBeenCalled();
    await waitFor(() => expect(document.activeElement).toBe(
      screen.getByRole("textbox", { name: "Question for this book" }),
    ));
    confirmMock.mockRestore();
    nowMock.mockRestore();
  });

  it("never offers abandonment after the server reports an existing sent operation", async () => {
    fetchUserModelsMock.mockResolvedValue({
      models: [eligibleModel], count: 1, stale_registered: [], source: "test",
    });
    askBookMock.mockRejectedValue(new Error("response lost"));
    let operationExists = false;
    getBookModelOperationMock.mockImplementation(() => operationExists
      ? Promise.resolve({ state: "sent" })
      : Promise.reject(new BookModelOperationNotFoundError()));
    let now = 1_700_000_000_000;
    const nowMock = vi.spyOn(Date, "now").mockImplementation(() => now);
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    await waitFor(() => expect(fetchUserModelsMock).toHaveBeenCalled());
    fireEvent.click(screen.getByRole("combobox").querySelector("button") as HTMLButtonElement);
    fireEvent.click(await screen.findByRole("option", { name: /Reconcile model/ }));
    fireEvent.change(screen.getByRole("textbox", { name: "Question for this book" }), {
      target: { value: "sent question" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(getBookModelOperationMock.mock.calls.length).toBeGreaterThanOrEqual(1));
    now += 4_000;
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    await screen.findByRole("button", { name: "Abandon unsent request" });
    operationExists = true;
    fireEvent.click(screen.getByRole("button", { name: "Check status" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Abandon unsent request" })).toBeNull());
    expect(screen.getByText(/provider outcome is not confirmed/i)).toBeTruthy();
    expect(askBookMock).toHaveBeenCalledTimes(1);
    nowMock.mockRestore();
  });

  it("accepts a legacy response that omits model_receipt", async () => {
    askBookMock.mockResolvedValue(answer({ model_receipt: undefined }));
    await openAndAsk();
    expect(screen.queryByTestId("talk-model-receipt")).toBeNull();
  });

  it("uses a 390px-safe full-width panel and mobile touch targets", () => {
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    const bookmark = screen.getByTestId("talk-to-book-bookmark");
    expect(bookmark.className).toContain("min-h-11");
    fireEvent.click(bookmark);
    const panel = screen.getByTestId("talk-to-book");
    expect(panel.className).toContain("left-3");
    expect(panel.className).toContain("right-3");
    expect(panel.className).toContain("sm:w-96");
    expect(screen.getByRole("button", { name: "Close" }).className).toContain("min-h-11");
    expect(screen.getByRole("button", { name: "Ask" }).className).toContain("min-h-11");
  });

  it("answers cite pages and a citation click jumps the reader to that page", async () => {
    askBookMock.mockResolvedValue(answer());
    const jump = vi.fn();
    await openAndAsk(jump);

    // The citation chip shows the 1-based page; clicking jumps to the 0-based
    // page index (REUSES the reader's setPageIndex via onJumpToPage).
    const chip = screen.getByRole("button", { name: "p.7" });
    fireEvent.click(chip);
    expect(jump).toHaveBeenCalledWith(6);
  });

  it("an unresolved page is shown honestly (no fabricated page, no jump)", async () => {
    askBookMock.mockResolvedValue(answer({ citations: [cite({ page_index: null, page_resolved: false })] }));
    const jump = vi.fn();
    await openAndAsk(jump);
    expect(screen.getByText("in the book (page not pinpointed)")).toBeTruthy();
    expect(jump).not.toHaveBeenCalled();
  });

  it("continues the multi-turn conversation, sending prior turns as history", async () => {
    askBookMock
      .mockResolvedValueOnce(answer({ answer: "First answer." }))
      .mockResolvedValueOnce(answer({ answer: "Second answer, building on the first." }));
    await openAndAsk(vi.fn(), "first question", "First answer.");

    fireEvent.change(screen.getByPlaceholderText("Ask about this book…"), {
      target: { value: "what about that?" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText("Second answer, building on the first.");

    // The second call carries the first turn as history (multi-turn memory).
    const secondCallOpts = askBookMock.mock.calls[1][2];
    expect(secondCallOpts.history).toHaveLength(1);
    expect(secondCallOpts.history[0]).toEqual({
      question: "first question",
      answer: "First answer.",
    });
    // Both turns are visible in the thread.
    expect(screen.getByText("First answer.")).toBeTruthy();
  });

  it("branches a tangent off a turn ('what about that?')", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    // Fork a tangent from the first answer.
    fireEvent.click(screen.getByRole("button", { name: "↳ what about that?" }));
    // A branch picker appears with the trunk + the new tangent.
    await screen.findByTestId("talk-branches");
    expect(screen.getByRole("button", { name: "main" })).toBeTruthy();
    expect(screen.getByTestId("talk-model-receipt").textContent).toContain("system-provider");
    const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
    expect(stored.branches[1].messages[0].model_receipt.actual_model_id).toBe("system-model");
  });

  it("reset removes persisted receipts and operation identities with the thread", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    fireEvent.click(screen.getByText("clear"));
    await waitFor(() => {
      const stored = JSON.parse(window.sessionStorage.getItem("antiek.read.talk.doc-x") ?? "{}");
      expect(stored.branches[0].messages).toEqual([]);
    });
  });

  it("persists the conversation across a re-mount (the bookmark carries it)", async () => {
    askBookMock.mockResolvedValue(answer({ answer: "A persisted answer." }));
    const { unmount } = await openAndAsk(vi.fn(), "a question", "A persisted answer.");
    expect(screen.getByText("A persisted answer.")).toBeTruthy();
    unmount();

    // Re-mount the SAME book: the bookmark shows the prior turn count, and the
    // thread is restored from session state (not refetched).
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    expect(screen.getByTestId("talk-turn-count").textContent).toBe("1");
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText("A persisted answer.")).toBeTruthy();
    expect(screen.getByTestId("talk-model-receipt").textContent).toBe(
      "Used system-provider · system-model",
    );
  });

  it("migrates an old stored message whose receipt and operation id are absent", () => {
    window.sessionStorage.setItem("antiek.read.talk.doc-x", JSON.stringify({
      active_branch_id: "trunk",
      branches: [{
        branch_id: "trunk",
        forked_from: null,
        messages: [{
          id: "old-turn",
          question: "old question",
          answer: "old answer",
          citations: [],
          grounded: true,
        }],
      }],
    }));
    render(<TalkToBook documentId="doc-x" title="A Book" onJumpToPage={vi.fn()} />);
    fireEvent.click(screen.getByTestId("talk-to-book-bookmark"));
    expect(screen.getByText("old answer")).toBeTruthy();
    expect(screen.queryByTestId("talk-model-receipt")).toBeNull();
  });

  it("mounts a read-aloud control for the answer (M3 wiring)", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    const readAloud = screen.getByTestId("read-aloud");
    expect(readAloud.getAttribute("data-text")).toBe("Page seven discusses entanglement.");
  });

  it("an ungrounded answer is labelled honestly", async () => {
    askBookMock.mockResolvedValue(
      answer({ answer: "No readable text here.", citations: [], grounded: false }),
    );
    await openAndAsk(vi.fn(), "anything", "No readable text here.");
    expect(screen.getByText(/isn’t grounded in the book’s text/)).toBeTruthy();
  });

  it("captures a one-tap judgment and persists its completed state", async () => {
    askBookMock.mockResolvedValue(answer());
    await openAndAsk();
    fireEvent.click(screen.getByRole("button", { name: "Mark answer good" }));
    await screen.findByText("Marked good");
    expect(judgeBookAnswerMock).toHaveBeenCalledWith("doc-x", "evt-answer-1", "good");
  });

  it("delivers an uncaptured answer without offering a broken rating action", async () => {
    askBookMock.mockResolvedValue(answer({
      answer_id: null,
      capture_status: "unavailable",
    }));
    await openAndAsk();
    expect(screen.queryByRole("button", { name: "Mark answer good" })).toBeNull();
    expect(screen.getByText(/rating is unavailable because its evidence record could not be saved/)).toBeTruthy();
  });
});
