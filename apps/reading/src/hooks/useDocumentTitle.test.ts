/**
 * useDocumentTitle.test.ts — the window-title-as-status-surface pure logic
 * (herdr transfer P1, strategy 27).
 */
import { describe, expect, it } from "vitest";

import { computeDocumentTitle } from "./useDocumentTitle";
import type { InvestigationSummary } from "../lib/api";

function inv(
  id: string,
  status: InvestigationSummary["status"],
  question: string | null = null,
  completedAt: string | null = null,
): InvestigationSummary {
  return {
    investigation_id: id,
    question,
    status,
    started_at: null,
    completed_at: completedAt,
    cost_usd_total: 0,
    parent_investigation_id: null,
  };
}

const neverSeen = () => null;
const seenAt = (iso: string) => (_id: string) => iso;

describe("computeDocumentTitle", () => {
  it("shows the active investigation and its state word on /inv/:id", () => {
    const list = [inv("a", "in_progress", "Why do bees dance?")];
    expect(computeDocumentTitle(list, "/inv/a", neverSeen)).toBe(
      "Why do bees dance? — working — Antiek",
    );
  });

  it("falls back to Antiek for an unknown /inv/:id", () => {
    expect(computeDocumentTitle([inv("a", "completed")], "/inv/nope", neverSeen)).toBe("Antiek");
  });

  it("counts blocked researches on non-investigation routes", () => {
    const list = [inv("a", "failed"), inv("b", "in_progress"), inv("c", "failed")];
    expect(computeDocumentTitle(list, "/", neverSeen)).toBe("2 need attention — Antiek");
  });

  it("counts unseen completions when nothing is blocked", () => {
    const list = [
      inv("a", "completed", null, "2026-08-13T10:00:00Z"),
      inv("b", "completed", null, "2026-08-13T10:00:00Z"),
    ];
    expect(computeDocumentTitle(list, "/", neverSeen)).toBe("2 unread — Antiek");
  });

  it("seen completions do not count as unread", () => {
    const list = [inv("a", "completed", null, "2026-08-13T10:00:00Z")];
    expect(computeDocumentTitle(list, "/", seenAt("2026-08-13T11:00:00Z"))).toBe("Antiek");
  });

  it("blocked outranks unread in the title", () => {
    const list = [
      inv("a", "failed"),
      inv("b", "completed", null, "2026-08-13T10:00:00Z"),
    ];
    expect(computeDocumentTitle(list, "/", neverSeen)).toBe("1 need attention — Antiek");
  });

  it("an empty list yields the plain title", () => {
    expect(computeDocumentTitle([], "/", neverSeen)).toBe("Antiek");
  });
});
