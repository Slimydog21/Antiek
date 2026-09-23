/**
 * BlockCard.test.tsx — DRW block-canvas M1 acceptance.
 *
 * Pins the criteria:
 *  - an insight block and a question block render VISUALLY DISTINCT (asserted
 *    by the kind data-attribute + the kind label), from real node types;
 *  - clicking a block opens its detail (the SPR-04 seam) carrying the node;
 *  - the §9 provenance affordance is reachable (read source when grounded;
 *    an honest "no source on record" when not) — never a raw id leak.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import BlockCard from "./BlockCard";
import type { DistilledNode } from "../../../lib/api";

afterEach(() => cleanup());

function insight(extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id: "i1",
    kind: "insight",
    text: "GPUs gate scale.",
    confidence: "high",
    source_document_id: "doc-1",
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
    ...extra,
  };
}
function question(extra: Partial<DistilledNode> = {}): DistilledNode {
  return {
    node_id: "q1",
    kind: "question",
    text: "What is the moat?",
    confidence: null,
    source_document_id: null,
    refinement_count: 0,
    escalated: false,
    reserved_child_investigation_id: null,
    ...extra,
  };
}

describe("BlockCard — kind distinction (M1)", () => {
  it("renders an insight and a question with distinct kind markers", () => {
    const { rerender } = render(<BlockCard node={insight()} />);
    const card = screen.getByText("GPUs gate scale.").closest("[data-block-card]")!;
    expect(card.getAttribute("data-block-card")).toBe("insight");
    expect(screen.getByText("insight")).toBeTruthy();

    rerender(<BlockCard node={question()} />);
    const qCard = screen.getByText("What is the moat?").closest("[data-block-card]")!;
    expect(qCard.getAttribute("data-block-card")).toBe("question");
    expect(screen.getByText("question")).toBeTruthy();
  });
});

describe("BlockCard — click-to-detail seam (M1 / SPR-04)", () => {
  it("clicking the body opens detail with the node", () => {
    const onOpenDetail = vi.fn();
    render(<BlockCard node={insight()} onOpenDetail={onOpenDetail} />);
    fireEvent.click(screen.getByRole("button", { name: "Open block detail" }));
    expect(onOpenDetail).toHaveBeenCalledTimes(1);
    expect(onOpenDetail.mock.calls[0][0].node_id).toBe("i1");
  });

  it("is inert (no detail target) when no handler is given", () => {
    render(<BlockCard node={insight()} />);
    expect(screen.queryByRole("button", { name: "Open block detail" })).toBeNull();
  });
});

describe("BlockCard — provenance affordance (M1 / §9)", () => {
  it("surfaces a read-source control when the node is grounded, never the raw id", () => {
    const onCiteSource = vi.fn();
    render(<BlockCard node={insight({ source_document_id: "doc-1" })} onCiteSource={onCiteSource} />);
    const cite = screen.getByRole("button", { name: "read source" });
    fireEvent.click(cite);
    expect(onCiteSource).toHaveBeenCalledTimes(1);
    expect(onCiteSource.mock.calls[0][0].node_id).toBe("i1");
    expect(onCiteSource.mock.calls[0][1]).toEqual(
      expect.objectContaining({ left: expect.any(Number), top: expect.any(Number) }),
    );
    // The raw document id must never appear as a label.
    expect(screen.queryByText("doc-1")).toBeNull();
  });

  it("says 'no source on record' honestly when ungrounded", () => {
    render(<BlockCard node={question({ source_document_id: null })} />);
    expect(screen.getByText("no source on record")).toBeTruthy();
  });

  it("does not expose an action for a whitespace-only source identity", () => {
    render(<BlockCard node={question({ source_document_id: "   " })} onCiteSource={vi.fn()} />);
    expect(screen.queryByRole("button", { name: "read source" })).toBeNull();
    expect(screen.getByText("no source on record")).toBeTruthy();
  });

  it("shows 'grounded in a source' when grounded but no cite handler", () => {
    render(<BlockCard node={insight({ source_document_id: "doc-1" })} />);
    expect(screen.getByText("grounded in a source")).toBeTruthy();
    expect(screen.queryByText("doc-1")).toBeNull();
  });
});

describe("BlockCard — escalation marker", () => {
  it("badges an escalated question 'needs more research'", () => {
    render(<BlockCard node={question({ escalated: true })} />);
    expect(screen.getByText("needs more research")).toBeTruthy();
  });
});
