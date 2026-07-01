import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import DeliverablePreview, {
  CREATION_DELIVERABLE_REFRESH_EVENT,
} from "./DeliverablePreview";

const getDeliverableMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  getDeliverable: getDeliverableMock,
}));

function deliverable(
  title: string,
  proseText: string | null = null,
  deliverableId = "del-1",
) {
  return {
    deliverable_id: deliverableId,
    title,
    deliverable_kind: "research_memo",
    status: "draft",
    investigation_root_id: null,
    sections: [
      {
        section_id: "section-1",
        deliverable_id: deliverableId,
        parent_section_id: null,
        section_index: 0,
        title: "Opening claim",
        prose_text: proseText,
        prose_provenance: null,
        block_count: 2,
      },
    ],
  };
}

function deferredDeliverable(title: string, deliverableId = "del-1") {
  let resolve!: () => void;
  const ready = new Promise<void>((done) => {
    resolve = done;
  });
  return {
    promise: ready.then(() =>
      deliverable(title, `${title} prose.`, deliverableId),
    ),
    resolve,
  };
}

describe("DeliverablePreview", () => {
  beforeEach(() => {
    getDeliverableMock.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the export-shaped section preview for the selected deliverable", async () => {
    getDeliverableMock.mockResolvedValue(
      deliverable("Memo draft", "First paragraph.\n\nSecond paragraph."),
    );

    render(<DeliverablePreview deliverableId="del-1" />);

    expect(await screen.findByText("Memo draft")).toBeTruthy();
    expect(screen.getByText("Opening claim")).toBeTruthy();
    expect(screen.getByText("First paragraph.")).toBeTruthy();
    expect(screen.getByText("Second paragraph.")).toBeTruthy();
    expect(screen.getByText("2 source blocks")).toBeTruthy();
  });

  it("refreshes only for matching deliverable refresh events", async () => {
    getDeliverableMock
      .mockResolvedValueOnce(deliverable("Before refresh", "Old prose."))
      .mockResolvedValueOnce(deliverable("After refresh", "New prose."));

    render(<DeliverablePreview deliverableId="del-1" />);

    expect(await screen.findByText("Before refresh")).toBeTruthy();

    window.dispatchEvent(
      new CustomEvent(CREATION_DELIVERABLE_REFRESH_EVENT, {
        detail: { deliverableId: "other-deliverable" },
      }),
    );
    expect(getDeliverableMock).toHaveBeenCalledTimes(1);

    window.dispatchEvent(
      new CustomEvent(CREATION_DELIVERABLE_REFRESH_EVENT, {
        detail: { deliverableId: "del-1" },
      }),
    );

    expect(await screen.findByText("After refresh")).toBeTruthy();
    expect(screen.getByText("New prose.")).toBeTruthy();
    expect(getDeliverableMock).toHaveBeenCalledTimes(2);
  });

  it("keeps the newest preview when deliverable responses complete out of order", async () => {
    const stale = deferredDeliverable("Stale preview");
    const fresh = deferredDeliverable("Fresh preview", "del-2");
    getDeliverableMock.mockReturnValueOnce(stale.promise).mockReturnValueOnce(fresh.promise);

    const rendered = render(<DeliverablePreview deliverableId="del-1" />);
    rendered.rerender(<DeliverablePreview deliverableId="del-2" />);

    fresh.resolve();
    expect(await screen.findByText("Fresh preview")).toBeTruthy();

    stale.resolve();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(screen.queryByText("Stale preview")).toBeNull();
  });
});
