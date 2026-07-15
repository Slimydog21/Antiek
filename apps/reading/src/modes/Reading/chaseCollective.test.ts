import { describe, expect, it } from "vitest";

import type { InvestigationSummary } from "../../lib/api";
import {
  completedReadingChases,
  reconcileChaseSelection,
  toggleChaseSelection,
} from "./chaseCollective";

function investigation(
  investigationId: string,
  status: InvestigationSummary["status"],
  parent = "read-book-1",
): InvestigationSummary {
  return {
    investigation_id: investigationId,
    question: `Question ${investigationId}`,
    status,
    parent_investigation_id: parent,
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
  };
}

describe("reading chase collective", () => {
  it("keeps only completed chases from this book in document order", () => {
    const result = completedReadingChases(
      [
        investigation("chase-b", "completed"),
        investigation("chase-live", "in_progress"),
        investigation("chase-other", "completed", "read-other"),
        investigation("chase-a", "completed"),
      ],
      "read-book-1",
    );
    expect(result.map((item) => item.investigationId)).toEqual(["chase-b", "chase-a"]);
  });

  it("defaults untouched selection to all, but preserves a touched empty selection", () => {
    expect(reconcileChaseSelection(["a", "b"], [], false)).toEqual(["a", "b"]);
    expect(reconcileChaseSelection(["a", "b"], [], true)).toEqual([]);
  });

  it("toggles selections in stable available order rather than click order", () => {
    expect(toggleChaseSelection(["a", "b", "c"], ["c"], "a")).toEqual(["a", "c"]);
  });
});
