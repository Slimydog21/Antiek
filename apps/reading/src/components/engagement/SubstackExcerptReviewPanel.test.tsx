import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ConfirmedCollectiveUnit } from "../../api/engagement";
import { SubstackExcerptReviewPanel } from "./SubstackExcerptReviewPanel";

const reviewCollectiveSubstackExcerpt = vi.hoisted(() => vi.fn());
const confirmCollectiveSubstackExcerpt = vi.hoisted(() => vi.fn());

vi.mock("../../api/engagement", () => ({
  reviewCollectiveSubstackExcerpt,
  confirmCollectiveSubstackExcerpt,
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const collective = {
  collective_unit_id: `cunit_${"a".repeat(24)}`,
  preview_sha256: "b".repeat(64),
  state: "confirmed",
  html: "<article>unit</article>",
  view_format: "html",
  material: {
    source_session_ids: [`fsess_${"1".repeat(16)}`],
    prompt_block: "prompt",
    unit: {
      collective_id: "col_1",
      spawn_ids: [],
      asset_ids: ["asset"],
      investigation_ids: [],
      twin_units: [],
      source_references: [
        {
          ref_id: `sref_${"2".repeat(16)}`,
          kind: "substack",
          raw: "https://antiek.substack.com/p/research",
          canonical_url: "https://antiek.substack.com/p/research",
        },
      ],
      view_format: "html",
      spawn_count: 0,
      twin_count: 0,
      ref_count: 1,
      prompt_block: "prompt",
    },
  },
} satisfies ConfirmedCollectiveUnit;

function fillValidReview(): void {
  fireEvent.change(screen.getByTestId("substack-review-text"), {
    target: { value: 'A & B "private"' },
  });
  const inputs = screen.getAllByRole("textbox");
  fireEvent.change(inputs[1], { target: { value: "c".repeat(64) } });
  const numberInputs = screen.getAllByRole("spinbutton");
  fireEvent.change(numberInputs[0], { target: { value: "1000" } });
  fireEvent.change(numberInputs[1], { target: { value: "100" } });
  const checks = screen.getAllByRole("checkbox");
  fireEvent.click(checks[0]);
  fireEvent.click(checks[1]);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((next) => { resolve = next; });
  return { promise, resolve };
}

describe("SubstackExcerptReviewPanel", () => {
  it("requires separate affirmations, renders text inertly, and clears it after confirmation", async () => {
    reviewCollectiveSubstackExcerpt.mockResolvedValue({
      review_id: `sureview_${"3".repeat(24)}`,
      review_preview_sha256: "4".repeat(64),
      selection_text: 'A & B "private"',
      excerpt_bytes: 15,
      expires_at_ms: 60_000,
      publication_execution_enabled: false,
    });
    confirmCollectiveSubstackExcerpt.mockResolvedValue({
      receipt_id: `suer_${"5".repeat(24)}`,
      publication_execution_enabled: false,
      requires_manifest_v2: true,
    });
    render(<SubstackExcerptReviewPanel collective={collective} />);
    const reviewButton = screen.getByTestId("review-substack-excerpt") as HTMLButtonElement;
    expect(reviewButton.disabled).toBe(true);
    fireEvent.change(screen.getByTestId("substack-review-text"), {
      target: { value: 'A & B "private"' },
    });
    const inputs = screen.getAllByRole("textbox");
    fireEvent.change(inputs[1], { target: { value: "c".repeat(64) } });
    const numberInputs = screen.getAllByRole("spinbutton");
    fireEvent.change(numberInputs[0], { target: { value: "1000" } });
    fireEvent.change(numberInputs[1], { target: { value: "100" } });
    const checks = screen.getAllByRole("checkbox");
    fireEvent.click(checks[0]);
    expect(reviewButton.disabled).toBe(true);
    fireEvent.click(checks[1]);
    expect(reviewButton.disabled).toBe(false);
    fireEvent.click(reviewButton);
    const preview = await screen.findByTestId("substack-review-preview");
    expect(preview.textContent).toContain('A & B "private"');
    expect(preview.querySelector("script")).toBeNull();
    fireEvent.click(screen.getByTestId("confirm-substack-excerpt"));
    await waitFor(() => expect(screen.getByTestId("confirmed-substack-review")).toBeTruthy());
    expect((screen.getByTestId("substack-review-text") as HTMLTextAreaElement).value).toBe("");
    expect(screen.getByTestId("confirmed-substack-review").textContent).toContain(
      "execution unavailable",
    );
  });

  it("invalidates an in-flight review without leaving the panel busy", async () => {
    const pending = deferred<Record<string, unknown>>();
    reviewCollectiveSubstackExcerpt.mockReturnValue(pending.promise);
    render(<SubstackExcerptReviewPanel collective={collective} />);
    fillValidReview();
    const button = screen.getByTestId("review-substack-excerpt") as HTMLButtonElement;
    fireEvent.click(button);
    fireEvent.change(screen.getByTestId("substack-review-text"), {
      target: { value: "Changed while pending" },
    });
    expect(button.disabled).toBe(false);
    await act(async () => {
      pending.resolve({
        review_id: `sureview_${"3".repeat(24)}`,
        review_preview_sha256: "4".repeat(64),
        selection_text: "stale",
        excerpt_bytes: 5,
        expires_at_ms: 60_000,
      });
      await pending.promise;
    });
    expect(screen.queryByTestId("substack-review-preview")).toBeNull();
    expect(button.disabled).toBe(false);
  });

  it("refreshes durable authority when an in-flight confirmation becomes stale", async () => {
    reviewCollectiveSubstackExcerpt.mockResolvedValue({
      review_id: `sureview_${"3".repeat(24)}`,
      review_preview_sha256: "4".repeat(64),
      selection_text: "private",
      excerpt_bytes: 7,
      expires_at_ms: 60_000,
    });
    const pending = deferred<Record<string, unknown>>();
    confirmCollectiveSubstackExcerpt.mockReturnValue(pending.promise);
    const refresh = vi.fn().mockResolvedValue(undefined);
    render(
      <SubstackExcerptReviewPanel collective={collective} onAuthorityRefresh={refresh} />,
    );
    fillValidReview();
    fireEvent.click(screen.getByTestId("review-substack-excerpt"));
    await screen.findByTestId("substack-review-preview");
    fireEvent.click(screen.getByTestId("confirm-substack-excerpt"));
    fireEvent.change(screen.getByTestId("substack-review-text"), {
      target: { value: "Changed during confirmation" },
    });
    await act(async () => {
      pending.resolve({
        receipt_id: `suer_${"5".repeat(24)}`,
        publication_execution_enabled: false,
        requires_manifest_v2: true,
      });
      await pending.promise;
    });
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("confirmed-substack-review")).toBeNull();
    expect((screen.getByTestId("review-substack-excerpt") as HTMLButtonElement).disabled).toBe(false);
  });

  it("preserves replacement edits when only saved live authority status refreshes", () => {
    const view = render(<SubstackExcerptReviewPanel collective={collective} />);
    fillValidReview();
    fireEvent.change(screen.getByTestId("substack-review-text"), {
      target: { value: "Replacement draft survives status refresh" },
    });
    const refreshed = {
      ...collective,
      substack_excerpt_reviews: [
        {
          overlay_id: `csubrev_${"6".repeat(24)}`,
          ref_id: `sref_${"2".repeat(16)}`,
          authorization_state: "active",
        },
      ],
    } as unknown as ConfirmedCollectiveUnit;
    view.rerender(<SubstackExcerptReviewPanel collective={refreshed} />);
    expect((screen.getByTestId("substack-review-text") as HTMLTextAreaElement).value).toBe(
      "Replacement draft survives status refresh",
    );
    expect(screen.getByTestId("saved-substack-reviews").textContent).toContain(
      "authority active",
    );
    expect((screen.getByTestId("review-substack-excerpt") as HTMLButtonElement).disabled).toBe(
      false,
    );
  });
});
